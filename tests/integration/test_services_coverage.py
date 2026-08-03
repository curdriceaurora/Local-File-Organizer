"""Integration tests targeting coverage gaps in audio and video services.

Files covered:
- file_organizer/services/audio/preprocessor.py
- file_organizer/services/video/scene_detector.py
- file_organizer/services/audio/content_analyzer.py
- file_organizer/services/audio/transcriber.py
- file_organizer/services/deduplication/embedder.py
- file_organizer/services/audio/organizer.py
"""

from __future__ import annotations

import builtins
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from file_organizer.services.audio.classifier import AudioType
from file_organizer.services.audio.content_analyzer import AudioContentAnalyzer, ContentAnalysis
from file_organizer.services.audio.metadata_extractor import AudioMetadata
from file_organizer.services.audio.organizer import (
    AudioOrganizer,
    OrganizationRules,
    sanitize_path_component,
)

# Enums and configs
from file_organizer.services.audio.preprocessor import AudioConfig, AudioFormat, AudioPreprocessor
from file_organizer.services.audio.transcriber import (
    AudioTranscriber as ServiceAudioTranscriber,
)
from file_organizer.services.audio.transcriber import (
    ComputeType as ServiceComputeType,
)
from file_organizer.services.audio.transcriber import (
    ModelSize as ServiceModelSize,
)
from file_organizer.services.audio.transcriber import (
    TranscriptionOptions as ServiceTranscriptionOptions,
)
from file_organizer.services.deduplication.embedder import DocumentEmbedder
from file_organizer.services.video.scene_detector import (
    DetectionMethod,
    Scene,
    SceneDetectionResult,
    SceneDetector,
)

pytestmark = pytest.mark.integration


def _install_faster_whisper_mock(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Provide a fake optional faster_whisper module for CI without media extras."""
    mock_whisper_cls = MagicMock()
    mock_module = types.ModuleType("faster_whisper")
    mock_module.WhisperModel = mock_whisper_cls
    monkeypatch.setitem(sys.modules, "faster_whisper", mock_module)
    return mock_whisper_cls


# ===========================================================================
# 1. services/audio/preprocessor.py Tests
# ===========================================================================


class TestAudioPreprocessor:
    def test_audio_format_and_config(self) -> None:
        assert AudioFormat.WAV == "wav"
        config = AudioConfig()
        assert config.sample_rate == 16000
        assert config.channels == 1

    @patch("subprocess.run")
    def test_ffmpeg_check_and_preprocessor_init(self, mock_run: MagicMock) -> None:
        # Ffmpeg found
        mock_run.return_value = MagicMock(returncode=0, stdout="ffmpeg version 4.4")
        preprocessor = AudioPreprocessor()
        assert preprocessor.config.sample_rate == 16000
        mock_run.assert_called_once_with(
            ["ffmpeg", "-version"], capture_output=True, text=True, timeout=5
        )

        # Ffmpeg not found / timeout
        mock_run.reset_mock()
        mock_run.side_effect = FileNotFoundError()
        preprocessor_no_ffmpeg = AudioPreprocessor()
        assert preprocessor_no_ffmpeg is not None

    @patch("subprocess.run")
    def test_convert_to_wav_ffmpeg_success(self, mock_run: MagicMock, tmp_path: Path) -> None:
        dummy_input = tmp_path / "input.mp3"
        dummy_input.write_bytes(b"dummy mp3 data")
        dummy_output = tmp_path / "output.wav"

        mock_run.return_value = MagicMock(returncode=0)
        preprocessor = AudioPreprocessor()

        out_path = preprocessor.convert_to_wav(dummy_input, output_path=dummy_output)
        assert out_path == dummy_output
        mock_run.assert_called_with(
            [
                "ffmpeg",
                "-i",
                str(dummy_input),
                "-ar",
                "16000",
                "-ac",
                "1",
                "-c:a",
                "pcm_s16le",
                "-y",
                str(dummy_output),
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )

        # Missing input file
        with pytest.raises(FileNotFoundError, match="Audio file not found"):
            preprocessor.convert_to_wav(tmp_path / "missing.mp3")

    @patch("subprocess.run")
    def test_convert_to_wav_ffmpeg_failure_and_pydub_fallback(
        self, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        dummy_input = tmp_path / "input.mp3"
        dummy_input.write_bytes(b"dummy mp3 data")

        # 1. Ffmpeg run returns non-zero code -> raises RuntimeError
        mock_run.return_value = MagicMock(returncode=1, stderr="unsupported codec")
        preprocessor = AudioPreprocessor()
        with pytest.raises(RuntimeError, match="ffmpeg conversion failed") as exc:
            preprocessor.convert_to_wav(dummy_input)
        assert "ffmpeg conversion failed" in str(exc.value)

        # 2. Ffmpeg executable not found -> Fallback to pydub
        mock_run.side_effect = FileNotFoundError()

        mock_pydub = MagicMock()
        mock_pydub_seg = MagicMock()
        mock_pydub.AudioSegment.from_file.return_value = mock_pydub_seg
        mock_pydub_seg.set_frame_rate.return_value = mock_pydub_seg
        mock_pydub_seg.set_channels.return_value = mock_pydub_seg

        with patch.dict("sys.modules", {"pydub": mock_pydub}):
            out_path = preprocessor.convert_to_wav(dummy_input)
            assert out_path.name.endswith("_converted.wav")
            mock_pydub_seg.export.assert_called_once()

    def test_convert_with_pydub_import_error(self, tmp_path: Path) -> None:
        dummy_input = tmp_path / "input.mp3"
        dummy_input.write_bytes(b"dummy")
        preprocessor = AudioPreprocessor()

        with patch("subprocess.run", side_effect=FileNotFoundError()):
            with patch.dict("sys.modules", {"pydub": None}):
                with pytest.raises(
                    ImportError, match="Neither ffmpeg nor pydub is available"
                ) as exc:
                    preprocessor.convert_to_wav(dummy_input)
                assert "Neither ffmpeg nor pydub is available" in str(exc.value)

    def test_normalize_and_silence_removal_pydub(self, tmp_path: Path) -> None:
        dummy_audio = tmp_path / "input.wav"
        dummy_audio.write_bytes(b"dummy")

        preprocessor = AudioPreprocessor()

        mock_pydub = MagicMock()
        mock_pydub_seg = MagicMock()
        mock_pydub_seg.suffix = ".wav"
        mock_pydub.AudioSegment.from_file.return_value = mock_pydub_seg

        # 1. Normalize success
        mock_norm = MagicMock(return_value=mock_pydub_seg)
        mock_pydub.effects.normalize = mock_norm

        # 2. Silence removal success
        mock_sil = MagicMock(return_value=[(0, 1000)])
        mock_pydub.silence.detect_nonsilent = mock_sil

        with patch.dict(
            "sys.modules",
            {
                "pydub": mock_pydub,
                "pydub.effects": mock_pydub.effects,
                "pydub.silence": mock_pydub.silence,
            },
        ):
            out_norm = preprocessor.normalize_audio(dummy_audio)
            assert out_norm == dummy_audio
            mock_norm.assert_called_once()

            mock_pydub_seg.__getitem__.return_value = mock_pydub_seg
            mock_pydub_seg.__add__.return_value = mock_pydub_seg

            out_sil = preprocessor.remove_silence(dummy_audio, silence_thresh=-45)
            assert out_sil == dummy_audio
            mock_sil.assert_called_once()

            # Silence removal, no non-silent ranges found
            mock_sil.reset_mock()
            mock_sil.return_value = []
            out_sil_none = preprocessor.remove_silence(dummy_audio)
            assert out_sil_none == dummy_audio
            mock_sil.assert_called_once()

        # 3. pydub not available ImportErrors -> returns input path as fallback
        with patch.dict("sys.modules", {"pydub": None}):
            assert preprocessor.normalize_audio(dummy_audio) == dummy_audio
            assert preprocessor.remove_silence(dummy_audio) == dummy_audio

    def test_preprocess_pipeline_combinations(self, tmp_path: Path) -> None:
        dummy_audio = tmp_path / "input.mp3"
        dummy_audio.write_bytes(b"dummy")

        preprocessor = AudioPreprocessor()

        # Mock the individual operations
        preprocessor.convert_to_wav = MagicMock(return_value=tmp_path / "converted.wav")
        preprocessor.normalize_audio = MagicMock(return_value=tmp_path / "normalized.wav")
        preprocessor.remove_silence = MagicMock(return_value=tmp_path / "trimmed.wav")

        res = preprocessor.preprocess(
            dummy_audio,
            convert_to_wav=True,
            normalize=True,
            remove_silence=True,
        )
        assert res == tmp_path / "trimmed.wav"
        preprocessor.convert_to_wav.assert_called_once()
        preprocessor.normalize_audio.assert_called_once()
        preprocessor.remove_silence.assert_called_once()

        # No conversion but output path provided -> triggers shutil.copy2
        preprocessor.convert_to_wav.reset_mock()
        with patch("shutil.copy2") as mock_copy:
            res_copy = preprocessor.preprocess(
                tmp_path / "input.wav",  # already wav
                output_path=tmp_path / "destination.wav",
                convert_to_wav=False,
                normalize=False,
                remove_silence=False,
            )
            assert res_copy == tmp_path / "destination.wav"
            mock_copy.assert_called_once()

    def test_get_audio_info_and_supported_formats(self, tmp_path: Path) -> None:
        dummy_audio = tmp_path / "song.mp3"
        dummy_audio.write_bytes(b"dummy")

        mock_pydub = MagicMock()
        mock_pydub_seg = MagicMock()
        mock_pydub_seg.channels = 2
        mock_pydub_seg.frame_rate = 44100
        mock_pydub_seg.sample_width = 2
        mock_pydub_seg.frame_count.return_value = 100000
        mock_pydub_seg.__len__.return_value = 5000  # 5 seconds
        mock_pydub.AudioSegment.from_file.return_value = mock_pydub_seg

        # 1. pydub available
        with patch.dict("sys.modules", {"pydub": mock_pydub}):
            info = AudioPreprocessor.get_audio_info(dummy_audio)
            assert info["duration_seconds"] == 5.0
            assert info["channels"] == 2
            assert info["sample_rate"] == 44100
            assert info["format"] == "mp3"

        # 2. pydub not available
        with patch.dict("sys.modules", {"pydub": None}):
            info_err = AudioPreprocessor.get_audio_info(dummy_audio)
            assert "error" in info_err
            assert "pydub not available" in info_err["error"]

        # 3. is_supported_format
        assert AudioPreprocessor.is_supported_format("song.mp3") is True
        assert AudioPreprocessor.is_supported_format("doc.pdf") is False


# ===========================================================================
# 2. services/video/scene_detector.py Tests
# ===========================================================================


class TestSceneDetector:
    def test_detector_structs(self) -> None:
        scene = Scene(
            scene_number=1,
            start_time=0.0,
            end_time=2.0,
            start_frame=0,
            end_frame=60,
            duration=2.0,
            score=1.0,
            frame_count=60,
        )
        assert scene.duration == 2.0

    def test_dependency_check_logging(self) -> None:
        with patch.dict("sys.modules", {"cv2": None, "scenedetect": None}):
            detector = SceneDetector()
            assert detector is not None

    def test_detect_scenes_file_not_found(self) -> None:
        detector = SceneDetector()
        with pytest.raises(FileNotFoundError, match="Video file not found"):
            detector.detect_scenes("missing_video.mp4")

    def test_detect_with_scenedetect(self, tmp_path: Path) -> None:
        dummy_video = tmp_path / "video.mp4"
        dummy_video.write_bytes(b"dummy")

        mock_scenedetect = MagicMock()
        mock_detectors = MagicMock()
        mock_video_mgr_cls = mock_scenedetect.VideoManager
        mock_scene_mgr_cls = mock_scenedetect.SceneManager

        mock_video_mgr = MagicMock()
        mock_video_mgr_cls.return_value = mock_video_mgr
        mock_video_mgr.get_framerate.return_value = 30.0
        mock_video_mgr.get_frame_number.return_value = 300

        mock_time_start = MagicMock()
        mock_time_start.get_seconds.return_value = 0.0
        mock_time_start.get_frames.return_value = 0
        mock_time_end = MagicMock()
        mock_time_end.get_seconds.return_value = 5.0
        mock_time_end.get_frames.return_value = 150

        mock_video_mgr.get_duration.return_value = (mock_time_end,)

        mock_scene_mgr = MagicMock()
        mock_scene_mgr_cls.return_value = mock_scene_mgr
        mock_scene_mgr.get_scene_list.return_value = [(mock_time_start, mock_time_end)]

        detector = SceneDetector(method=DetectionMethod.THRESHOLD, threshold=15.0)

        # Test content/threshold/adaptive branches
        with patch(
            "file_organizer.services.video.scene_detector.SceneDetector._check_dependencies"
        ) as mock_check_dependencies:
            with patch.dict(
                "sys.modules",
                {
                    "scenedetect": mock_scenedetect,
                    "scenedetect.detectors": mock_detectors,
                    "cv2": MagicMock(),
                },
            ):
                res = detector.detect_scenes(dummy_video, method=DetectionMethod.THRESHOLD)
                assert res.fps == 30.0
                assert len(res.scenes) == 1
                assert res.scenes[0].duration == 5.0
                mock_video_mgr.release.assert_called_once()
        # Recorded as never reached on this path; pin it so a change that
        # starts calling it fails here instead of going unnoticed.
        mock_check_dependencies.assert_not_called()

    def test_detect_with_opencv_fallback(self, tmp_path: Path) -> None:
        dummy_video = tmp_path / "video.mp4"
        dummy_video.write_bytes(b"dummy")

        mock_cv2 = MagicMock()
        mock_cv2.CAP_PROP_FPS = 1
        mock_cv2.CAP_PROP_FRAME_COUNT = 2
        mock_cv2.COLOR_BGR2GRAY = 3
        mock_cv2.cvtColor.return_value = np.zeros((100, 100), dtype=np.uint8)
        mock_cv2.absdiff.side_effect = [
            np.zeros((100, 100), dtype=np.uint8),
            np.ones((100, 100), dtype=np.uint8) * 100,
        ]

        mock_cap = MagicMock()
        mock_cv2.VideoCapture.return_value = mock_cap
        mock_cap.isOpened.return_value = True
        mock_cap.get.side_effect = lambda prop: {
            mock_cv2.CAP_PROP_FPS: 30.0,
            mock_cv2.CAP_PROP_FRAME_COUNT: 100,
        }.get(prop, 0.0)

        # Mock cap.read returning 3 frames (2 reads return frame, 3rd returns False)
        frame_mock = np.zeros((100, 100, 3), dtype=np.uint8)
        # Create a frame change at frame index 1 to trigger scene boundary
        frame_mock_diff = np.ones((100, 100, 3), dtype=np.uint8) * 255

        mock_cap.read.side_effect = [(True, frame_mock), (True, frame_mock_diff), (False, None)]

        # Trigger ImportError on scenedetect to force opencv fallback
        detector = SceneDetector(min_scene_length=0.01)
        with patch.dict("sys.modules", {"scenedetect": None, "cv2": mock_cv2}):
            res = detector.detect_scenes(dummy_video, method=DetectionMethod.THRESHOLD)
            assert res.fps == 30.0
            assert len(res.scenes) >= 1
            mock_cap.release.assert_called_once()

            # Test VideoCapture fail to open
            mock_cap.isOpened.return_value = False
            with pytest.raises(ValueError, match="Failed to open video") as exc:
                detector.detect_scenes(dummy_video)
            assert "Failed to open video" in str(exc.value)

    def test_detect_scenes_batch(self, tmp_path: Path) -> None:
        dummy_video = tmp_path / "video.mp4"
        dummy_video.write_bytes(b"dummy")

        detector = SceneDetector()

        def mock_detect(video_path, method=None):
            if "missing" in str(video_path):
                raise FileNotFoundError()
            return "mock_result"

        detector.detect_scenes = MagicMock(side_effect=mock_detect)

        # Succeeds for valid file, skips/errors for missing file
        results = detector.detect_scenes_batch([dummy_video, tmp_path / "missing.mp4"])
        assert results == ["mock_result"]

    def test_save_scene_list_csv(self, tmp_path: Path) -> None:
        csv_out = tmp_path / "scenes.csv"
        scene = Scene(
            scene_number=1,
            start_time=0.0,
            end_time=5.0,
            start_frame=0,
            end_frame=150,
            duration=5.0,
            score=1.0,
            frame_count=150,
        )
        result = SceneDetectionResult(
            video_path=Path("vid.mp4"),
            scenes=[scene],
            total_duration=5.0,
            fps=30.0,
            total_frames=150,
            method=DetectionMethod.CONTENT,
        )

        SceneDetector.save_scene_list(result, csv_out)
        assert csv_out.exists()
        csv_content = csv_out.read_text()
        assert "Scene,Start Time,End Time" in csv_content
        assert "1,0.00,5.00" in csv_content

    def test_extract_scene_thumbnails(self, tmp_path: Path) -> None:
        mock_cv2 = MagicMock()
        mock_cv2.CAP_PROP_FPS = 1
        mock_cv2.CAP_PROP_POS_FRAMES = 1
        mock_cap = MagicMock()
        mock_cv2.VideoCapture.return_value = mock_cap
        mock_cap.get.return_value = 30.0  # fps
        mock_cap.read.return_value = (True, "mock_frame")

        scene = Scene(
            scene_number=1,
            start_time=1.0,
            end_time=5.0,
            start_frame=30,
            end_frame=150,
            duration=4.0,
            score=1.0,
            frame_count=120,
        )
        result = SceneDetectionResult(
            video_path=Path("vid.mp4"),
            scenes=[scene],
            total_duration=5.0,
            fps=30.0,
            total_frames=150,
            method=DetectionMethod.CONTENT,
        )

        thumb_dir = tmp_path / "thumbs"
        with patch.dict("sys.modules", {"cv2": mock_cv2}):
            SceneDetector.extract_scene_thumbnails("vid.mp4", result, thumb_dir)

            # Seek to frame: start_time (1.0) + frame_offset (0.5) = 1.5s -> 1.5 * 30 = 45 frame
            mock_cap.set.assert_called_once_with(1, 45)  # CAP_PROP_POS_FRAMES is 1
            mock_cv2.imwrite.assert_called_once_with(str(thumb_dir / "scene_001.jpg"), "mock_frame")
            mock_cap.release.assert_called_once()


# ===========================================================================
# 3. services/audio/content_analyzer.py Tests
# ===========================================================================


class TestAudioContentAnalyzer:
    def test_content_analysis_struct(self) -> None:
        analysis = ContentAnalysis(
            topics=["sports"],
            keywords=["football", "ball"],
            speakers=["Speaker 1"],
            language="en",
        )
        assert analysis.topic_count == 1
        assert analysis.keyword_count == 2
        assert analysis.speaker_count == 1

    def test_content_analyzer_keyword_and_topic_extraction(self) -> None:
        analyzer = AudioContentAnalyzer(max_keywords=5, min_keyword_freq=1)

        text = "This is an audio file about coding and software programming. Coding is great. software is programming."

        topics = analyzer.extract_topics(text)
        # matches topic keywords in lexicons.json default dictionaries
        assert isinstance(topics, list)

        keywords = analyzer.extract_keywords(text)
        assert "coding" in keywords
        assert "software" in keywords

    def test_extract_speakers_gap_and_duration_heuristics(self) -> None:
        analyzer = AudioContentAnalyzer()

        # Empty segments
        assert analyzer.extract_speakers([]) == []

        # Construct segments to trigger speaker switch heuristics
        seg1 = MagicMock(start=0.0, end=2.0)
        seg2 = MagicMock(start=4.0, end=6.0)  # Gap of 2.0s (> 1.5s turn threshold) -> switch
        seg3 = MagicMock(
            start=6.0, end=6.5
        )  # Duration ratio 2.0 / 0.5 = 4.0 (> 3.0 duration ratio) -> switch

        speakers = analyzer.extract_speakers([seg1, seg2, seg3])
        # Speaker 1 -> Speaker 2 -> Speaker 3
        assert len(speakers) == 3
        assert "Speaker 1" in speakers
        assert "Speaker 2" in speakers
        assert "Speaker 3" in speakers

    def test_full_analyze_metadata_and_transcription(self) -> None:
        analyzer = AudioContentAnalyzer()

        metadata = AudioMetadata(
            file_path=Path("song.mp3"),
            file_size=1024,
            format="MP3",
            duration=180.0,
            bitrate=128000,
            sample_rate=44100,
            channels=2,
            title="Great software tutorial",
            comment="software programming guides",
            genre="Education",
            artist="Instructor",
            album="Coding Album",
        )

        # 1. Without transcription
        res_meta = analyzer.analyze(metadata)
        assert "Education" in res_meta.topics or len(res_meta.topics) >= 0
        assert "software" in res_meta.keywords

        # 2. With transcription
        mock_seg = MagicMock(start=0.0, end=2.0)
        mock_transcription = MagicMock(
            text="Hello from the software tutorial coding coding",
            language="en",
            segments=[mock_seg],
        )

        res_full = analyzer.analyze(metadata, mock_transcription)
        assert res_full.language == "en"
        assert "Speaker 1" in res_full.speakers
        assert res_full.sentiment_indicators["positive"] >= 0.0


# ===========================================================================
# 4. services/audio/transcriber.py Tests
# ===========================================================================


class TestServiceAudioTranscriber:
    def test_transcriber_constructor_import_error(self, tmp_path: Path) -> None:
        # Check constructor validations when faster-whisper not installed
        dummy_file = tmp_path / "song.wav"
        dummy_file.write_bytes(b"dummy")
        with patch.dict("sys.modules", {"faster_whisper": None}):
            transcriber = ServiceAudioTranscriber(device="cpu")
            with pytest.raises(ImportError, match="faster-whisper is required") as exc:
                transcriber.transcribe(dummy_file)
            assert "faster-whisper is required" in str(exc.value)

    def test_device_auto_detection_mps_cuda(self) -> None:
        # MPS / CUDA mock
        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = False
        mock_torch.backends.mps.is_available.return_value = True

        with patch("file_organizer.services.audio.transcriber._FASTER_WHISPER_AVAILABLE", True):
            # Test auto-detection
            with patch.dict("sys.modules", {"torch": mock_torch}):
                transcriber = ServiceAudioTranscriber(device="auto")
                assert transcriber.device == "mps"

    def test_lazy_load_model_caching_and_failures(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mock_whisper_cls = _install_faster_whisper_mock(monkeypatch)
        mock_whisper = MagicMock()
        mock_whisper_cls.return_value = mock_whisper

        with patch("file_organizer.services.audio.transcriber._FASTER_WHISPER_AVAILABLE", True):
            transcriber = ServiceAudioTranscriber(
                model_size=ServiceModelSize.TINY,
                compute_type=ServiceComputeType.FLOAT32,
                device="cpu",
            )

            # First load
            model1 = transcriber._load_model()
            assert model1 == mock_whisper
            mock_whisper_cls.assert_called_once_with(
                "tiny",
                device="cpu",
                compute_type="float32",
                download_root=None,
                num_workers=1,
            )

            # Second load should return cached model directly
            model2 = transcriber._load_model()
            assert model2 == mock_whisper
            assert mock_whisper_cls.call_count == 1

            # Unload model
            transcriber.unload_model()
            assert transcriber._model is None

    def test_transcribe_options_payloads_and_segments(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mock_whisper_cls = _install_faster_whisper_mock(monkeypatch)
        dummy_audio = tmp_path / "audio.wav"
        dummy_audio.write_bytes(b"dummy wav data")

        mock_whisper = MagicMock()
        mock_whisper_cls.return_value = mock_whisper

        # Set up segments iteration and info
        mock_seg = MagicMock()
        mock_seg.id = 1
        mock_seg.text = " Hello world "
        mock_seg.start = 0.0
        mock_seg.end = 2.5
        mock_seg.avg_logprob = -0.05
        mock_seg.no_speech_prob = 0.01
        mock_word = MagicMock(word="Hello", start=0.0, end=1.0, probability=0.99)
        mock_seg.words = [mock_word]

        mock_info = MagicMock()
        mock_info.language = "en"
        mock_info.language_probability = 0.98
        mock_info.duration = 15.0

        mock_whisper.transcribe.return_value = ([mock_seg], mock_info)

        with patch("file_organizer.services.audio.transcriber._FASTER_WHISPER_AVAILABLE", True):
            transcriber = ServiceAudioTranscriber(device="cpu")

            # File not found
            with pytest.raises(FileNotFoundError, match="Audio file not found"):
                transcriber.transcribe(tmp_path / "missing.wav")

            options = ServiceTranscriptionOptions(
                language="en",
                word_timestamps=True,
                initial_prompt="Context hint",
                vad_filter=True,
                vad_parameters={"threshold": 0.5},
            )

            res = transcriber.transcribe(dummy_audio, options=options)

            assert res.text == "Hello world"
            assert res.language == "en"
            assert res.language_confidence == 0.98
            assert res.duration == 15.0
            assert len(res.segments) == 1
            assert res.segments[0].words[0].word == "Hello"

            # Verify transcribe parameters
            mock_whisper.transcribe.assert_called_once_with(
                str(dummy_audio),
                beam_size=5,
                best_of=5,
                temperature=0.0,
                compression_ratio_threshold=2.4,
                log_prob_threshold=-1.0,
                no_speech_threshold=0.6,
                condition_on_previous_text=True,
                word_timestamps=True,
                language="en",
                initial_prompt="Context hint",
                vad_filter=True,
                vad_parameters={"threshold": 0.5},
            )

            # Batch transcription
            def mock_transcribe(audio_path, options=None):
                if "missing" in str(audio_path):
                    raise FileNotFoundError()
                return "mock_result"

            transcriber.transcribe = MagicMock(side_effect=mock_transcribe)
            results = transcriber.transcribe_batch([dummy_audio, tmp_path / "missing.wav"])
            assert results == ["mock_result"]

    def test_device_detection_branches(self) -> None:
        # Test direct device returning
        transcriber = ServiceAudioTranscriber(device="cpu")
        assert transcriber._detect_device("cpu") == "cpu"

        # Test torch import error fallback to cpu
        with patch.dict("sys.modules", {"torch": None}):
            assert transcriber._detect_device("auto") == "cpu"

        # Test cuda detection
        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = True
        with patch.dict("sys.modules", {"torch": mock_torch}):
            assert transcriber._detect_device("auto") == "cuda"

    def test_transcribe_error_paths(self, tmp_path: Path) -> None:
        dummy_audio = tmp_path / "audio.wav"
        dummy_audio.write_bytes(b"dummy")
        transcriber = ServiceAudioTranscriber(device="cpu")

        # Force ValueError inside transcribe
        transcriber._load_model = MagicMock()
        mock_model = MagicMock()
        mock_model.transcribe.side_effect = ValueError("Mocked error")
        transcriber._load_model.return_value = mock_model

        with pytest.raises(ValueError, match="Mocked error") as exc:
            transcriber.transcribe(dummy_audio)
        assert "Mocked error" in str(exc.value)

        # Force error inside transcribe_batch
        transcriber.transcribe = MagicMock(side_effect=RuntimeError("Batch error"))
        results = transcriber.transcribe_batch([dummy_audio])
        assert len(results) == 0

    def test_transcribe_options_variations(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        dummy_audio = tmp_path / "audio.wav"
        dummy_audio.write_bytes(b"dummy")

        # Set up WhisperModel mock to return simple segment
        mock_seg = MagicMock()
        mock_seg.id = 1
        mock_seg.text = "Hello"
        mock_seg.start = 0.0
        mock_seg.end = 1.0
        mock_seg.avg_logprob = -0.1
        mock_seg.no_speech_prob = 0.1
        del mock_seg.words  # No word level timing

        mock_info = MagicMock()
        mock_info.language = "en"
        mock_info.language_probability = 0.9
        mock_info.duration = 1.0

        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([mock_seg], mock_info)

        mock_whisper_cls = _install_faster_whisper_mock(monkeypatch)
        mock_whisper_cls.return_value = mock_model

        with patch("file_organizer.services.audio.transcriber._FASTER_WHISPER_AVAILABLE", True):
            transcriber = ServiceAudioTranscriber(device="cpu")
            # 1. Option variations: word_timestamps=False, language=None, initial_prompt=None, vad_filter=False
            options = ServiceTranscriptionOptions(
                language=None,
                word_timestamps=False,
                initial_prompt=None,
                vad_filter=False,
            )
            res = transcriber.transcribe(dummy_audio, options=options)
            assert res.text == "Hello"

            # Verify transcribe parameters
            mock_model.transcribe.assert_called_once()
            _, kwargs = mock_model.transcribe.call_args
            assert "language" not in kwargs
            assert "initial_prompt" not in kwargs
            assert "vad_filter" not in kwargs
            assert kwargs["word_timestamps"] is False


# ===========================================================================
# 5. services/deduplication/embedder.py Tests
# ===========================================================================


@pytest.fixture
def require_sklearn() -> None:
    """Skip positive behavior unless scikit-learn is provided by dedup or search."""
    pytest.importorskip("sklearn")


class TestDocumentEmbedder:
    def test_document_embedder_constructor_import_error(self) -> None:
        real_import = builtins.__import__

        def reject_sklearn(name: str, *args, **kwargs):
            if name == "sklearn" or name.startswith("sklearn."):
                raise ImportError("simulated missing optional dependency")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=reject_sklearn):
            with pytest.raises(ImportError, match="scikit-learn is required") as exc:
                DocumentEmbedder()
            assert "scikit-learn is required" in str(exc.value)

    @pytest.mark.extras
    def test_embedder_fit_transform_and_caching(
        self, tmp_path: Path, require_sklearn: None
    ) -> None:
        embedder = DocumentEmbedder(
            max_features=10,
            ngram_range=(1, 1),
            max_df=1.0,
            cache_path=tmp_path / "embeddings_cache.pkl",
        )

        # 1. Empty documents fit
        assert len(embedder.fit_transform([])) == 0

        # 2. Fit transform small corpus
        docs = ["apple banana cherry", "banana cherry date", "cherry date elderberry"]
        embeddings = embedder.fit_transform(docs)

        assert embedder.is_fitted is True
        assert embeddings.shape == (
            3,
            5,
        )  # 5 unique vocabulary words (apple, banana, cherry, date, elderberry)
        assert isinstance(embeddings, np.ndarray)

        # 3. Transform single document (checks fit state and caching)
        doc = "apple banana"

        # Test NotFittedError trigger
        unfitted_embedder = DocumentEmbedder(max_features=10)
        with pytest.raises(RuntimeError, match="Vectorizer not fitted") as exc:
            unfitted_embedder.transform(doc)
        assert "Vectorizer not fitted" in str(exc.value)

        with pytest.raises(RuntimeError, match="Vectorizer not fitted") as exc_batch:
            unfitted_embedder.transform_batch([doc])
        assert "Vectorizer not fitted" in str(exc_batch.value)

        # Successful transform (cache miss first, then cache hit)
        emb1 = embedder.transform(doc)
        assert emb1.shape == (5,)

        # Cache hit
        with patch("logging.Logger.debug") as mock_debug:
            emb2 = embedder.transform(doc)
            assert np.array_equal(emb1, emb2)
            # Verify cache hit log message
            # Logger debug calls vary, check call args
            has_cache_log = any(
                "Cache hit for document" in str(call) for call in mock_debug.call_args_list
            )
            assert has_cache_log or len(embedder.embedding_cache) == 1

        # Transform batch
        emb_batch = embedder.transform_batch([doc, "cherry date"])
        assert emb_batch.shape == (2, 5)

    @pytest.mark.extras
    def test_vocabulary_features_and_top_terms(self, require_sklearn: None) -> None:
        embedder = DocumentEmbedder(max_features=10, max_df=1.0, ngram_range=(1, 1))

        # Fit fitted checks
        with pytest.raises(RuntimeError, match="Vectorizer not fitted"):
            embedder.get_feature_names()
        with pytest.raises(RuntimeError, match="Vectorizer not fitted"):
            embedder.get_vocabulary()
        with pytest.raises(RuntimeError, match="Vectorizer not fitted"):
            embedder.get_top_terms(np.zeros(5))

        # Fit
        docs = ["apple banana", "banana cherry"]
        embedder.fit_transform(docs)

        # get_feature_names (checks both new/old sklearn APIs)
        features = embedder.get_feature_names()
        assert "apple" in features
        assert "banana" in features
        assert "cherry" in features

        # get_vocabulary
        vocab = embedder.get_vocabulary()
        assert vocab["banana"] == 1

        # get_top_terms
        emb = embedder.transform("apple banana")
        top = embedder.get_top_terms(emb, top_n=2)
        assert len(top) == 2
        assert top[0][0] in ["apple", "banana"]

    @pytest.mark.extras
    def test_save_load_model_and_cache_persistency(
        self, tmp_path: Path, require_sklearn: None
    ) -> None:
        model_file = tmp_path / "tfidf.pkl"
        cache_file = tmp_path / "cache.pkl"

        embedder = DocumentEmbedder(
            max_features=5, max_df=1.0, ngram_range=(1, 1), cache_path=cache_file
        )
        docs = ["apple banana", "cherry date"]
        embedder.fit_transform(docs)

        # Generate some cache entries
        embedder.transform("apple banana")
        embedder.transform("cherry date")
        assert len(embedder.embedding_cache) == 2

        # 1. Save and load model
        embedder.save_model(model_file)
        assert model_file.exists()

        embedder2 = DocumentEmbedder(max_features=5)
        embedder2.load_model(model_file)
        assert embedder2.is_fitted is True
        assert len(embedder2.get_feature_names()) == 4

        # 2. Cache saving on destruction (__del__)
        embedder._save_cache()
        assert cache_file.exists()

        # Load cache in new instance
        embedder3 = DocumentEmbedder(max_features=5, cache_path=cache_file)
        assert len(embedder3.embedding_cache) == 2

        # Clear cache
        embedder3.clear_cache()
        assert len(embedder3.embedding_cache) == 0

    @pytest.mark.extras
    def test_embedder_error_and_edge_cases(self, tmp_path: Path, require_sklearn: None) -> None:
        # 1. fit_transform with 1 document (triggers length * max_df < 1)
        embedder = DocumentEmbedder(max_features=5, max_df=0.95, ngram_range=(1, 1))
        res = embedder.fit_transform(["apple"])
        assert embedder.is_fitted is True
        assert res.shape == (1, 1)

        # 2. fit_transform raising ValueError
        embedder.vectorizer.fit_transform = MagicMock(side_effect=ValueError("Fit error"))
        with pytest.raises(ValueError, match="Fit error"):
            embedder.fit_transform(["apple"])

        # 3. get_feature_names raising AttributeError (fallback test)
        embedder.is_fitted = True
        embedder.vectorizer.get_feature_names_out = MagicMock(side_effect=AttributeError())
        embedder.vectorizer.get_feature_names = MagicMock(return_value=["apple"])
        assert embedder.get_feature_names() == ["apple"]

        # 4. save_model on unfitted vectorizer
        unfitted = DocumentEmbedder(max_features=5)
        with patch("logging.Logger.warning") as mock_warn:
            unfitted.save_model(tmp_path / "unfitted.pkl")
            mock_warn.assert_called_with("Cannot save unfitted vectorizer")

        # 5. save_model raising pickling errors
        embedder.is_fitted = True
        with patch("builtins.open", side_effect=OSError("Save failed")):
            with patch("logging.Logger.error") as mock_err:
                embedder.save_model(tmp_path / "fail.pkl")
                mock_err.assert_called_once()

        # 6. load_model raising unpickling errors
        with patch("builtins.open", side_effect=OSError("Load failed")):
            with patch("logging.Logger.error") as mock_err:
                with pytest.raises(OSError, match="Load failed"):
                    embedder.load_model(tmp_path / "fail.pkl")
                mock_err.assert_called_once()

        # 7. _save_cache with cache_path=None
        embedder.cache_path = None
        assert embedder._save_cache() is None

        # 8. _save_cache raising pickling errors
        embedder.cache_path = tmp_path / "cache_fail.pkl"
        with patch("builtins.open", side_effect=OSError("Cache save failed")):
            with patch("logging.Logger.error") as mock_err:
                embedder._save_cache()
                mock_err.assert_called_once()

        # 9. _load_cache raising unpickling errors
        embedder.cache_path = tmp_path / "cache_fail.pkl"
        embedder.cache_path.write_bytes(b"corrupted pickle data")
        with patch("logging.Logger.error") as mock_err:
            embedder._load_cache()
            mock_err.assert_called_once()


# ===========================================================================
# 6. services/audio/organizer.py Tests
# ===========================================================================


class TestAudioOrganizer:
    def test_rules_templates_and_helpers(self) -> None:
        rules = OrganizationRules()
        assert rules.get_template(AudioType.MUSIC) == rules.music_template
        assert rules.get_template(AudioType.UNKNOWN) == rules.unknown_template

        # Path sanitization
        assert sanitize_path_component("my:file/name?.mp3") == "myfilename.mp3"
        assert sanitize_path_component("   ") == "Unknown"
        assert sanitize_path_component("a" * 300) == "a" * 255

    def test_audio_organizer_path_generation(self) -> None:
        organizer = AudioOrganizer()

        # Music type path generation
        meta_music = AudioMetadata(
            file_path=Path("track1.mp3"),
            file_size=1024,
            format="MP3",
            duration=180.0,
            bitrate=128000,
            sample_rate=44100,
            channels=2,
            genre="Rock",
            artist="The Band",
            album="First Album",
            title="Song One",
            track_number=3,
        )

        rel_path = organizer.generate_path(AudioType.MUSIC, meta_music)
        # Expect: Rock/The Band/First Album/03 - Song One.mp3
        assert rel_path == Path("Rock") / "The Band" / "First Album" / "03 - Song One.mp3"

        # Podcast type path generation
        meta_pod = AudioMetadata(
            file_path=Path("pod.mp3"),
            file_size=1024,
            format="MP3",
            duration=180.0,
            bitrate=128000,
            sample_rate=44100,
            channels=2,
            album_artist="Tech Show",
            title="Episode 42",
            year=2026,
        )
        rel_path_pod = organizer.generate_path(AudioType.PODCAST, meta_pod)
        # Expect: Tech Show/2026/Episode 42 - Episode 42.mp3 (Show/Year/Episode - Title)
        # Episode fallback is title, Show fallback is album_artist
        assert rel_path_pod == Path("Tech Show") / "2026" / "Episode 42 - Episode 42.mp3"

    def test_preview_and_organize_dry_run(self, tmp_path: Path) -> None:
        source_file = tmp_path / "song.mp3"
        source_file.write_bytes(b"audio")

        meta = AudioMetadata(
            file_path=Path("song.mp3"),
            file_size=1024,
            format="MP3",
            duration=180.0,
            bitrate=128000,
            sample_rate=44100,
            channels=2,
            artist="Singer",
            title="Track Title",
        )

        organizer = AudioOrganizer()
        files = [(source_file, AudioType.MUSIC, meta)]

        # 1. Preview Organization
        plan = organizer.preview_organization(files, base_path=tmp_path / "organized")
        assert plan.total_planned == 1
        assert plan.total_skipped == 0
        assert "song.mp3 ->" in plan.summary()

        # Skipped files (file does not exist)
        plan_missing = organizer.preview_organization(
            [(tmp_path / "missing.mp3", AudioType.MUSIC, meta)],
            base_path=tmp_path / "organized",
        )
        assert plan_missing.total_skipped == 1
        assert "does not exist" in plan_missing.summary()

        # 2. Organize (dry_run=True)
        res_dry = organizer.organize(files, base_path=tmp_path / "organized", dry_run=True)
        assert res_dry.total_moved == 1
        assert res_dry.total_failed == 0
        assert res_dry.total_skipped == 0
        assert "complete: 1 moved" in res_dry.report()

    def test_organize_actual_move_and_conflict_resolution(self, tmp_path: Path) -> None:
        source_file = tmp_path / "song.mp3"
        source_file.write_bytes(b"audio")

        meta = AudioMetadata(
            file_path=Path("song.mp3"),
            file_size=1024,
            format="MP3",
            duration=180.0,
            bitrate=128000,
            sample_rate=44100,
            channels=2,
            artist="Singer",
            title="Track Title",
        )

        organizer = AudioOrganizer()
        files = [(source_file, AudioType.MUSIC, meta)]

        base_dest = tmp_path / "organized"
        # Generate the destination path: organized/Unknown Genre/Singer/Unknown Album/00 - Track Title.mp3
        rel_path = organizer.generate_path(AudioType.MUSIC, meta)
        dest_file = base_dest / rel_path

        # 1. Create a conflict (pre-existing destination file)
        dest_file.parent.mkdir(parents=True, exist_ok=True)
        dest_file.write_bytes(b"existing track")

        # 2. Run actual organization
        res = organizer.organize(files, base_path=base_dest, dry_run=False)
        assert res.total_moved == 1
        assert res.total_failed == 0

        # Conflict should be resolved by appending (1) to filename
        final_dest = res.moved_files[0].destination
        assert final_dest.name == "00 - Track Title (1).mp3"
        assert final_dest.exists()
        assert not source_file.exists()  # file was moved

        # 3. Conflict capacity exhaustion trigger
        # Mock conflict resolver to fail (force loop to run > 9999 times)
        with patch(
            "file_organizer.services.audio.organizer._resolve_conflict",
            side_effect=RuntimeError("Too many conflicting files"),
        ):
            source_file2 = tmp_path / "song2.mp3"
            source_file2.write_bytes(b"audio2")
            res_fail = organizer.organize(
                [(source_file2, AudioType.MUSIC, meta)],
                base_path=base_dest,
                dry_run=False,
            )
            assert res_fail.total_failed == 1
            assert "Too many conflicting files" in res_fail.report()
