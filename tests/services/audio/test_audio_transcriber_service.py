"""Tests for AudioTranscriber class.

Tests model initialization, device detection, lazy model loading,
transcription with segments, batch transcription, and model unloading.
External dependencies (faster-whisper, torch) are mocked.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.services.audio.transcriber import (
    AudioTranscriber,
    ComputeType,
    ModelSize,
    Segment,
    TranscriptionOptions,
    TranscriptionResult,
    WordTiming,
)

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def transcriber():
    """Create AudioTranscriber with mocked device detection."""
    with patch.object(AudioTranscriber, "_detect_device", return_value="cpu"):
        return AudioTranscriber(model_size=ModelSize.BASE, device="cpu")


@pytest.fixture
def audio_file(tmp_path):
    """Create a fake audio file."""
    p = tmp_path / "test.wav"
    p.write_bytes(b"fake audio data for testing")
    return p


def _make_mock_segment(seg_id=0, start=0.0, end=5.0, text="Hello world", words=None):
    """Helper to build a mock whisper segment."""
    seg = MagicMock()
    seg.id = seg_id
    seg.start = start
    seg.end = end
    seg.text = text
    seg.avg_logprob = -0.3
    seg.no_speech_prob = 0.05
    if words is not None:
        seg.words = words
    else:
        seg.words = []
    return seg


def _make_mock_info(language="en", language_probability=0.95, duration=10.0):
    """Helper to build a mock transcription info."""
    info = MagicMock()
    info.language = language
    info.language_probability = language_probability
    info.duration = duration
    return info


# ---------------------------------------------------------------------------
# Enum Tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestModelSize:
    """Tests for ModelSize enum."""

    def test_values(self):
        assert ModelSize.TINY == "tiny"
        assert ModelSize.BASE == "base"
        assert ModelSize.SMALL == "small"
        assert ModelSize.MEDIUM == "medium"
        assert ModelSize.LARGE_V2 == "large-v2"
        assert ModelSize.LARGE_V3 == "large-v3"


@pytest.mark.unit
class TestComputeType:
    """Tests for ComputeType enum."""

    def test_values(self):
        assert ComputeType.FLOAT16 == "float16"
        assert ComputeType.FLOAT32 == "float32"
        assert ComputeType.INT8 == "int8"
        assert ComputeType.INT8_FLOAT16 == "int8_float16"


# ---------------------------------------------------------------------------
# Dataclass Tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestTranscriptionOptions:
    """Tests for TranscriptionOptions dataclass."""

    def test_defaults(self):
        opts = TranscriptionOptions()
        assert opts.language is None
        assert opts.word_timestamps is False
        assert opts.beam_size == 5
        assert opts.best_of == 5
        assert opts.temperature == 0.0
        assert opts.vad_filter is True
        assert opts.initial_prompt is None
        assert opts.vad_parameters is None

    def test_custom(self):
        opts = TranscriptionOptions(
            language="fr",
            word_timestamps=True,
            beam_size=3,
            vad_filter=False,
        )
        assert opts.language == "fr"
        assert opts.word_timestamps is True
        assert opts.beam_size == 3
        assert opts.vad_filter is False


@pytest.mark.unit
class TestWordTiming:
    """Tests for WordTiming dataclass."""

    def test_fields(self):
        wt = WordTiming(word="hello", start=0.0, end=0.5, probability=0.95)
        assert wt.word == "hello"
        assert wt.start == 0.0
        assert wt.end == 0.5
        assert wt.probability == 0.95


@pytest.mark.unit
class TestSegmentDataclass:
    """Tests for Segment dataclass."""

    def test_defaults(self):
        seg = Segment(id=0, start=0.0, end=5.0, text="Hello")
        assert seg.words == []
        assert seg.avg_logprob == 0.0
        assert seg.no_speech_prob == 0.0

    def test_with_words(self):
        words = [WordTiming(word="hi", start=0.0, end=0.3, probability=0.9)]
        seg = Segment(id=1, start=0.0, end=1.0, text="Hi", words=words)
        assert len(seg.words) == 1


@pytest.mark.unit
class TestTranscriptionResult:
    """Tests for TranscriptionResult dataclass."""

    def test_fields(self):
        opts = TranscriptionOptions()
        result = TranscriptionResult(
            text="Hello world",
            segments=[],
            language="en",
            language_confidence=0.95,
            duration=10.0,
            options=opts,
        )
        assert result.text == "Hello world"
        assert result.language == "en"
        assert result.duration == 10.0


# ---------------------------------------------------------------------------
# AudioTranscriber Initialization
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAudioTranscriberInit:
    """Tests for AudioTranscriber initialization."""

    def test_default_values(self, transcriber):
        assert transcriber.model_size == ModelSize.BASE
        assert transcriber.device == "cpu"
        assert transcriber.compute_type == ComputeType.FLOAT16
        assert transcriber.cache_dir is None
        assert transcriber.num_workers == 1
        assert transcriber._model is None

    def test_custom_values(self):
        with patch.object(AudioTranscriber, "_detect_device", return_value="cpu"):
            t = AudioTranscriber(
                model_size=ModelSize.LARGE_V3,
                device="cpu",
                compute_type=ComputeType.FLOAT32,
                cache_dir=Path("/tmp/cache"),
                num_workers=4,
            )
        assert t.model_size == ModelSize.LARGE_V3
        assert t.compute_type == ComputeType.FLOAT32
        assert t.cache_dir == Path("/tmp/cache")
        assert t.num_workers == 4


# ---------------------------------------------------------------------------
# _detect_device
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDetectDevice:
    """Tests for _detect_device."""

    def test_explicit_device(self):
        with patch.object(AudioTranscriber, "_detect_device", return_value="cuda"):
            t = AudioTranscriber.__new__(AudioTranscriber)
            result = AudioTranscriber._detect_device(t, "cuda")
        assert result == "cuda"

    def test_auto_cuda(self):
        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = True

        with patch.dict("sys.modules", {"torch": mock_torch}):
            t = AudioTranscriber.__new__(AudioTranscriber)
            result = AudioTranscriber._detect_device(t, "auto")
        assert result == "cuda"

    def test_auto_mps(self):
        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = False
        mock_torch.backends.mps.is_available.return_value = True

        with patch.dict("sys.modules", {"torch": mock_torch}):
            t = AudioTranscriber.__new__(AudioTranscriber)
            result = AudioTranscriber._detect_device(t, "auto")
        assert result == "mps"

    def test_auto_cpu_no_torch(self):
        def fake_import(name, *args, **kwargs):
            if name == "torch":
                raise ImportError("no torch")
            return original_import(name, *args, **kwargs)

        import builtins

        original_import = builtins.__import__
        with patch("builtins.__import__", side_effect=fake_import):
            t = AudioTranscriber.__new__(AudioTranscriber)
            result = AudioTranscriber._detect_device(t, "auto")
        assert result == "cpu"

    def test_auto_cpu_no_gpu(self):
        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = False
        mock_torch.backends.mps.is_available.return_value = False

        with patch.dict("sys.modules", {"torch": mock_torch}):
            t = AudioTranscriber.__new__(AudioTranscriber)
            result = AudioTranscriber._detect_device(t, "auto")
        assert result == "cpu"


# ---------------------------------------------------------------------------
# _load_model
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLoadModel:
    """Tests for _load_model."""

    def test_lazy_load(self, transcriber):
        mock_whisper_model = MagicMock()
        mock_fw = MagicMock()
        mock_fw.WhisperModel.return_value = mock_whisper_model

        with patch.dict("sys.modules", {"faster_whisper": mock_fw}):
            model = transcriber._load_model()

        assert model is mock_whisper_model
        assert transcriber._model is mock_whisper_model

    def test_cached_model(self, transcriber):
        mock_model = MagicMock()
        transcriber._model = mock_model

        result = transcriber._load_model()
        assert result is mock_model

    def test_import_error(self, transcriber):
        def fake_import(name, *args, **kwargs):
            if "faster_whisper" in name:
                raise ImportError("no faster_whisper")
            return original_import(name, *args, **kwargs)

        import builtins

        original_import = builtins.__import__
        with patch("builtins.__import__", side_effect=fake_import):
            with pytest.raises(ImportError, match="faster-whisper is required"):
                transcriber._load_model()

    def test_model_load_error(self, transcriber):
        mock_fw = MagicMock()
        mock_fw.WhisperModel.side_effect = RuntimeError("model load error")

        with patch.dict("sys.modules", {"faster_whisper": mock_fw}):
            with pytest.raises(RuntimeError, match="model load error"):
                transcriber._load_model()

    def test_cache_dir_passed(self):
        with patch.object(AudioTranscriber, "_detect_device", return_value="cpu"):
            t = AudioTranscriber(
                model_size=ModelSize.TINY,
                device="cpu",
                cache_dir=Path("/tmp/models"),
            )

        mock_fw = MagicMock()
        with patch.dict("sys.modules", {"faster_whisper": mock_fw}):
            t._load_model()

        call_kwargs = mock_fw.WhisperModel.call_args
        assert call_kwargs[1]["download_root"] == "/tmp/models"


# ---------------------------------------------------------------------------
# transcribe
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestTranscribe:
    """Tests for transcribe method."""

    def test_file_not_found(self, transcriber):
        with pytest.raises(FileNotFoundError, match="Audio file not found"):
            transcriber.transcribe("/nonexistent/audio.wav")

    def test_basic_transcription(self, transcriber, audio_file):
        mock_seg = _make_mock_segment(0, 0.0, 5.0, " Hello world ")
        mock_info = _make_mock_info()

        mock_model = MagicMock()
        mock_model.transcribe.return_value = (iter([mock_seg]), mock_info)

        with patch.object(transcriber, "_load_model", return_value=mock_model):
            result = transcriber.transcribe(audio_file)

        assert isinstance(result, TranscriptionResult)
        assert result.text == "Hello world"
        assert result.language == "en"
        assert result.language_confidence == 0.95
        assert result.duration == 10.0
        assert len(result.segments) == 1
        assert result.segments[0].text == "Hello world"

    def test_default_options(self, transcriber, audio_file):
        mock_model = MagicMock()
        mock_model.transcribe.return_value = (iter([]), _make_mock_info())

        with patch.object(transcriber, "_load_model", return_value=mock_model):
            result = transcriber.transcribe(audio_file)

        assert isinstance(result.options, TranscriptionOptions)

    def test_custom_options(self, transcriber, audio_file):
        opts = TranscriptionOptions(
            language="fr",
            beam_size=3,
            word_timestamps=True,
            initial_prompt="Test prompt",
            vad_filter=True,
            vad_parameters={"threshold": 0.5},
        )

        mock_seg = _make_mock_segment()
        mock_word = MagicMock()
        mock_word.word = "Bonjour"
        mock_word.start = 0.0
        mock_word.end = 0.5
        mock_word.probability = 0.9
        mock_seg.words = [mock_word]

        mock_model = MagicMock()
        mock_model.transcribe.return_value = (iter([mock_seg]), _make_mock_info("fr", 0.98, 5.0))

        with patch.object(transcriber, "_load_model", return_value=mock_model):
            result = transcriber.transcribe(audio_file, options=opts)

        # Verify params were passed
        call_kwargs = mock_model.transcribe.call_args[1]
        assert call_kwargs["language"] == "fr"
        assert call_kwargs["beam_size"] == 3
        assert call_kwargs["word_timestamps"] is True
        assert call_kwargs["initial_prompt"] == "Test prompt"
        assert call_kwargs["vad_filter"] is True
        assert call_kwargs["vad_parameters"] == {"threshold": 0.5}

        assert result.language == "fr"

    def test_word_timestamps(self, transcriber, audio_file):
        mock_word = MagicMock()
        mock_word.word = "Hello"
        mock_word.start = 0.0
        mock_word.end = 0.5
        mock_word.probability = 0.92

        mock_seg = _make_mock_segment()
        mock_seg.words = [mock_word]

        mock_model = MagicMock()
        mock_model.transcribe.return_value = (iter([mock_seg]), _make_mock_info())

        opts = TranscriptionOptions(word_timestamps=True)

        with patch.object(transcriber, "_load_model", return_value=mock_model):
            result = transcriber.transcribe(audio_file, options=opts)

        assert len(result.segments[0].words) == 1
        assert result.segments[0].words[0].word == "Hello"
        assert result.segments[0].words[0].probability == 0.92

    def test_multiple_segments(self, transcriber, audio_file):
        seg1 = _make_mock_segment(0, 0.0, 3.0, " Hello ")
        seg2 = _make_mock_segment(1, 3.0, 6.0, " World ")

        mock_model = MagicMock()
        mock_model.transcribe.return_value = (iter([seg1, seg2]), _make_mock_info())

        with patch.object(transcriber, "_load_model", return_value=mock_model):
            result = transcriber.transcribe(audio_file)

        assert result.text == "Hello World"
        assert len(result.segments) == 2
        assert result.segments[0].id == 0
        assert result.segments[1].id == 1

    def test_transcription_error(self, transcriber, audio_file):
        mock_model = MagicMock()
        mock_model.transcribe.side_effect = RuntimeError("transcription failed")

        with patch.object(transcriber, "_load_model", return_value=mock_model):
            with pytest.raises(RuntimeError, match="transcription failed"):
                transcriber.transcribe(audio_file)

    def test_no_vad_filter(self, transcriber, audio_file):
        opts = TranscriptionOptions(vad_filter=False)

        mock_model = MagicMock()
        mock_model.transcribe.return_value = (iter([]), _make_mock_info())

        with patch.object(transcriber, "_load_model", return_value=mock_model):
            transcriber.transcribe(audio_file, options=opts)

        call_kwargs = mock_model.transcribe.call_args[1]
        assert "vad_filter" not in call_kwargs


# ---------------------------------------------------------------------------
# transcribe_batch
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestTranscribeBatch:
    """Tests for transcribe_batch."""

    def test_multiple_files(self, transcriber, tmp_path):
        f1 = tmp_path / "a.wav"
        f2 = tmp_path / "b.wav"
        f1.write_bytes(b"fake1")
        f2.write_bytes(b"fake2")

        mock_result = TranscriptionResult(
            text="test",
            segments=[],
            language="en",
            language_confidence=0.9,
            duration=5.0,
            options=TranscriptionOptions(),
        )

        with patch.object(transcriber, "transcribe", return_value=mock_result):
            results = transcriber.transcribe_batch([f1, f2])

        assert len(results) == 2

    def test_error_skipped(self, transcriber, tmp_path):
        f1 = tmp_path / "a.wav"
        f2 = tmp_path / "b.wav"
        f1.write_bytes(b"fake1")
        f2.write_bytes(b"fake2")

        mock_result = TranscriptionResult(
            text="test",
            segments=[],
            language="en",
            language_confidence=0.9,
            duration=5.0,
            options=TranscriptionOptions(),
        )

        def side_effect(path, options=None):
            if str(path) == str(f1):
                raise Exception("corrupt file")
            return mock_result

        with patch.object(transcriber, "transcribe", side_effect=side_effect):
            results = transcriber.transcribe_batch([f1, f2])

        assert len(results) == 1

    def test_empty_list(self, transcriber):
        results = transcriber.transcribe_batch([])
        assert results == []

    def test_shared_options(self, transcriber, tmp_path):
        f1 = tmp_path / "a.wav"
        f1.write_bytes(b"fake1")

        opts = TranscriptionOptions(language="de")
        mock_result = TranscriptionResult(
            text="test",
            segments=[],
            language="de",
            language_confidence=0.9,
            duration=5.0,
            options=opts,
        )

        with patch.object(transcriber, "transcribe", return_value=mock_result) as mock_t:
            transcriber.transcribe_batch([f1], options=opts)
            mock_t.assert_called_once_with(f1, opts)


# ---------------------------------------------------------------------------
# unload_model
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestUnloadModel:
    """Tests for unload_model."""

    def test_unload_loaded_model(self, transcriber):
        transcriber._model = MagicMock()
        transcriber.unload_model()
        assert transcriber._model is None

    def test_unload_no_model(self, transcriber):
        assert transcriber._model is None
        transcriber.unload_model()  # Should not raise
        assert transcriber._model is None
