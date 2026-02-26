"""Tests for AudioTranscriber class."""

from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# We need to mock faster_whisper before importing the module under test,
# because it's imported at module level.
mock_faster_whisper = MagicMock()
sys.modules.setdefault("faster_whisper", mock_faster_whisper)

from file_organizer.models.audio_transcriber import (  # noqa: E402
    AudioTranscriber,
    ComputeType,
    LanguageDetection,
    ModelSize,
    TranscriptionOptions,
    TranscriptionResult,
    TranscriptionSegment,
)

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_model_cache() -> None:
    """Clear the class-level model cache before each test."""
    AudioTranscriber._model_cache.clear()


@pytest.fixture
def mock_whisper_model() -> MagicMock:
    """Create a mock WhisperModel."""
    return MagicMock()


@pytest.fixture
def tmp_audio_file(tmp_path: Path) -> Path:
    """Create a temporary dummy audio file."""
    audio_file = tmp_path / "test_audio.wav"
    audio_file.write_bytes(b"\x00" * 100)
    return audio_file


@pytest.fixture
def make_transcriber():
    """Factory fixture that builds an AudioTranscriber with device detection mocked."""

    def _make(
        model_size: ModelSize | str = ModelSize.BASE,
        device: str = "cpu",
        compute_type: ComputeType | str = ComputeType.FLOAT32,
        cache_dir: Path | None = None,
        num_workers: int = 1,
    ) -> AudioTranscriber:
        with patch.object(AudioTranscriber, "_detect_device", return_value=device):
            return AudioTranscriber(
                model_size=model_size,
                device=device,
                compute_type=compute_type,
                cache_dir=cache_dir,
                num_workers=num_workers,
            )

    return _make


def _make_segment(
    start: float = 0.0,
    end: float = 1.0,
    text: str = " Hello world ",
    avg_logprob: float = -0.3,
    words: list[Any] | None = None,
) -> MagicMock:
    """Helper: build a mock segment returned by faster-whisper."""
    seg = MagicMock()
    seg.start = start
    seg.end = end
    seg.text = text
    seg.avg_logprob = avg_logprob
    if words is None:
        w = MagicMock()
        w.word = "Hello"
        w.start = 0.0
        w.end = 0.5
        w.probability = 0.95
        words = [w]
    seg.words = words
    return seg


def _make_transcribe_info(
    language: str = "en",
    language_probability: float = 0.98,
    duration: float = 5.0,
) -> MagicMock:
    """Helper: build a mock info object returned by model.transcribe."""
    info = MagicMock()
    info.language = language
    info.language_probability = language_probability
    info.duration = duration
    return info


# ---------------------------------------------------------------------------
# Enum tests
# ---------------------------------------------------------------------------


class TestModelSize:
    """Tests for ModelSize enum."""

    def test_all_values(self) -> None:
        assert ModelSize.TINY.value == "tiny"
        assert ModelSize.BASE.value == "base"
        assert ModelSize.SMALL.value == "small"
        assert ModelSize.MEDIUM.value == "medium"
        assert ModelSize.LARGE_V3.value == "large-v3"


class TestComputeType:
    """Tests for ComputeType enum."""

    def test_all_values(self) -> None:
        assert ComputeType.FLOAT16.value == "float16"
        assert ComputeType.INT8.value == "int8"
        assert ComputeType.FLOAT32.value == "float32"
        assert ComputeType.INT8_FLOAT32.value == "int8_float32"
        assert ComputeType.AUTO.value == "auto"
        assert ComputeType.DEFAULT.value == "default"
        assert ComputeType.INT16.value == "int16"
        assert ComputeType.BFLOAT16.value == "bfloat16"
        assert ComputeType.INT8_FLOAT16.value == "int8_float16"
        assert ComputeType.INT8_BFLOAT16.value == "int8_bfloat16"


# ---------------------------------------------------------------------------
# Dataclass tests
# ---------------------------------------------------------------------------


class TestTranscriptionSegment:
    """Tests for TranscriptionSegment dataclass."""

    def test_defaults(self) -> None:
        seg = TranscriptionSegment(start=0.0, end=1.0, text="hi", confidence=0.9)
        assert seg.speaker is None
        assert seg.words is None

    def test_with_optional_fields(self) -> None:
        words = [{"word": "hi", "start": 0.0, "end": 0.5, "confidence": 0.9}]
        seg = TranscriptionSegment(
            start=0.0, end=1.0, text="hi", confidence=0.9, speaker="A", words=words
        )
        assert seg.speaker == "A"
        assert seg.words == words


class TestLanguageDetection:
    """Tests for LanguageDetection dataclass."""

    def test_creation(self) -> None:
        ld = LanguageDetection(language="en", language_name="English", confidence=0.99)
        assert ld.language == "en"
        assert ld.language_name == "English"
        assert ld.confidence == 0.99


class TestTranscriptionResult:
    """Tests for TranscriptionResult dataclass."""

    def test_defaults(self) -> None:
        result = TranscriptionResult(
            text="hello",
            language="en",
            language_confidence=0.95,
            segments=[],
            duration=5.0,
            processing_time=1.0,
            model_size="base",
            device="cpu",
        )
        assert result.error is None

    def test_with_error(self) -> None:
        result = TranscriptionResult(
            text="",
            language="",
            language_confidence=0.0,
            segments=[],
            duration=0.0,
            processing_time=0.0,
            model_size="base",
            device="cpu",
            error="something went wrong",
        )
        assert result.error == "something went wrong"


class TestTranscriptionOptions:
    """Tests for TranscriptionOptions dataclass."""

    def test_defaults(self) -> None:
        opts = TranscriptionOptions()
        assert opts.language is None
        assert opts.word_timestamps is True
        assert opts.vad_filter is True
        assert opts.beam_size == 5
        assert opts.best_of == 5
        assert opts.temperature == 0.0
        assert opts.initial_prompt is None

    def test_custom(self) -> None:
        opts = TranscriptionOptions(language="fr", beam_size=3, temperature=0.5)
        assert opts.language == "fr"
        assert opts.beam_size == 3
        assert opts.temperature == 0.5


# ---------------------------------------------------------------------------
# AudioTranscriber initialization tests
# ---------------------------------------------------------------------------


class TestAudioTranscriberInit:
    """Tests for AudioTranscriber.__init__."""

    def test_init_with_enums(self, make_transcriber: Any) -> None:
        t = make_transcriber(model_size=ModelSize.SMALL, compute_type=ComputeType.INT8)
        assert t.model_size == "small"
        assert t.compute_type == "int8"

    def test_init_with_strings(self, make_transcriber: Any) -> None:
        t = make_transcriber(model_size="base", compute_type="float32")
        assert t.model_size == "base"
        assert t.compute_type == "float32"

    def test_init_invalid_model_size(self) -> None:
        with patch.object(AudioTranscriber, "_detect_device", return_value="cpu"):
            with pytest.raises(ValueError, match="Invalid model size"):
                AudioTranscriber(model_size="nonexistent", compute_type="float32")

    def test_init_invalid_compute_type(self) -> None:
        with patch.object(AudioTranscriber, "_detect_device", return_value="cpu"):
            with pytest.raises(ValueError, match="Invalid compute type"):
                AudioTranscriber(model_size="base", compute_type="float99")

    def test_model_not_loaded_at_init(self, make_transcriber: Any) -> None:
        t = make_transcriber()
        assert t.model is None
        assert t._model_loaded is False

    def test_cache_dir_and_workers(self, make_transcriber: Any, tmp_path: Path) -> None:
        t = make_transcriber(cache_dir=tmp_path, num_workers=4)
        assert t.cache_dir == tmp_path
        assert t.num_workers == 4


# ---------------------------------------------------------------------------
# Device detection tests
# ---------------------------------------------------------------------------


class TestDetectDevice:
    """Tests for AudioTranscriber._detect_device."""

    def test_explicit_device_returned_as_is(self) -> None:
        t = AudioTranscriber.__new__(AudioTranscriber)
        assert t._detect_device("cpu") == "cpu"
        assert t._detect_device("cuda") == "cuda"
        assert t._detect_device("mps") == "mps"

    def test_auto_selects_cuda_when_available(self) -> None:
        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = True
        t = AudioTranscriber.__new__(AudioTranscriber)
        with patch.dict(sys.modules, {"torch": mock_torch}):
            assert t._detect_device("auto") == "cuda"

    def test_auto_selects_mps_when_cuda_unavailable(self) -> None:
        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = False
        mock_torch.backends.mps.is_available.return_value = True
        t = AudioTranscriber.__new__(AudioTranscriber)
        with patch.dict(sys.modules, {"torch": mock_torch}):
            assert t._detect_device("auto") == "mps"

    def test_auto_falls_back_to_cpu_when_no_gpu(self) -> None:
        t = AudioTranscriber.__new__(AudioTranscriber)
        # Simulate torch not installed
        with patch.dict(sys.modules, {"torch": None}):
            assert t._detect_device("auto") == "cpu"

    def test_auto_cpu_when_cuda_check_raises_import_error(self) -> None:
        """When torch is not installed at all, we fall back to cpu."""
        t = AudioTranscriber.__new__(AudioTranscriber)

        original_import = __builtins__.__import__ if hasattr(__builtins__, '__import__') else __import__

        def fake_import(name, *args, **kwargs):
            if name == "torch":
                raise ImportError("no torch")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            result = t._detect_device("auto")
        assert result == "cpu"


# ---------------------------------------------------------------------------
# Model loading tests
# ---------------------------------------------------------------------------


class TestLoadModel:
    """Tests for AudioTranscriber._load_model."""

    def test_load_model_success(self, make_transcriber: Any) -> None:
        t = make_transcriber()
        mock_model = MagicMock()
        with patch(
            "file_organizer.models.audio_transcriber.WhisperModel", return_value=mock_model
        ):
            model = t._load_model()
        assert model is mock_model

    def test_load_model_cached(self, make_transcriber: Any) -> None:
        t = make_transcriber()
        mock_model = MagicMock()
        cache_key = f"{t.model_size}_{t.device}_{t.compute_type}"
        AudioTranscriber._model_cache[cache_key] = mock_model

        result = t._load_model()
        assert result is mock_model

    def test_load_model_failure_raises_runtime_error(self, make_transcriber: Any) -> None:
        t = make_transcriber()
        with patch(
            "file_organizer.models.audio_transcriber.WhisperModel",
            side_effect=Exception("download failed"),
        ):
            with pytest.raises(RuntimeError, match="Model loading failed"):
                t._load_model()

    def test_load_model_with_cache_dir(self, make_transcriber: Any, tmp_path: Path) -> None:
        t = make_transcriber(cache_dir=tmp_path)
        mock_model = MagicMock()
        with patch(
            "file_organizer.models.audio_transcriber.WhisperModel", return_value=mock_model
        ) as mock_cls:
            t._load_model()
            _, kwargs = mock_cls.call_args
            assert kwargs["download_root"] == str(tmp_path)

    def test_load_model_without_cache_dir(self, make_transcriber: Any) -> None:
        t = make_transcriber(cache_dir=None)
        mock_model = MagicMock()
        with patch(
            "file_organizer.models.audio_transcriber.WhisperModel", return_value=mock_model
        ) as mock_cls:
            t._load_model()
            _, kwargs = mock_cls.call_args
            assert kwargs["download_root"] is None


# ---------------------------------------------------------------------------
# detect_language tests
# ---------------------------------------------------------------------------


class TestDetectLanguage:
    """Tests for AudioTranscriber.detect_language."""

    def test_detect_language_file_not_found(self, make_transcriber: Any) -> None:
        t = make_transcriber()
        with pytest.raises(FileNotFoundError, match="Audio file not found"):
            t.detect_language("/nonexistent/file.wav")

    def test_detect_language_english(
        self, make_transcriber: Any, tmp_audio_file: Path
    ) -> None:
        t = make_transcriber()
        info = _make_transcribe_info(language="en", language_probability=0.97)
        mock_model = MagicMock()
        mock_model.transcribe.return_value = (iter([]), info)

        with patch.object(t, "_load_model", return_value=mock_model):
            result = t.detect_language(tmp_audio_file)

        assert isinstance(result, LanguageDetection)
        assert result.language == "en"
        assert result.language_name == "English"
        assert result.confidence == 0.97

    def test_detect_language_unknown_maps_to_uppercase(
        self, make_transcriber: Any, tmp_audio_file: Path
    ) -> None:
        t = make_transcriber()
        info = _make_transcribe_info(language="xx", language_probability=0.50)
        mock_model = MagicMock()
        mock_model.transcribe.return_value = (iter([]), info)

        with patch.object(t, "_load_model", return_value=mock_model):
            result = t.detect_language(tmp_audio_file)

        assert result.language_name == "XX"

    def test_detect_language_known_languages(
        self, make_transcriber: Any, tmp_audio_file: Path
    ) -> None:
        """Verify several languages from the internal mapping."""
        for code, name in [("es", "Spanish"), ("fr", "French"), ("de", "German"),
                           ("zh", "Chinese"), ("ja", "Japanese"), ("ko", "Korean")]:
            t = make_transcriber()
            info = _make_transcribe_info(language=code, language_probability=0.90)
            mock_model = MagicMock()
            mock_model.transcribe.return_value = (iter([]), info)

            with patch.object(t, "_load_model", return_value=mock_model):
                result = t.detect_language(tmp_audio_file)

            assert result.language == code
            assert result.language_name == name

    def test_detect_language_skips_load_when_already_loaded(
        self, make_transcriber: Any, tmp_audio_file: Path
    ) -> None:
        t = make_transcriber()
        t._model_loaded = True
        mock_model = MagicMock()
        t.model = mock_model
        info = _make_transcribe_info()
        mock_model.transcribe.return_value = (iter([]), info)

        # Should NOT call _load_model
        with patch.object(t, "_load_model") as load_mock:
            t.detect_language(tmp_audio_file)
            load_mock.assert_not_called()

    def test_detect_language_failure(
        self, make_transcriber: Any, tmp_audio_file: Path
    ) -> None:
        t = make_transcriber()
        mock_model = MagicMock()
        mock_model.transcribe.side_effect = Exception("decode error")

        with patch.object(t, "_load_model", return_value=mock_model):
            with pytest.raises(RuntimeError, match="Language detection failed"):
                t.detect_language(tmp_audio_file)

    def test_detect_language_accepts_string_path(
        self, make_transcriber: Any, tmp_audio_file: Path
    ) -> None:
        t = make_transcriber()
        info = _make_transcribe_info(language="en", language_probability=0.99)
        mock_model = MagicMock()
        mock_model.transcribe.return_value = (iter([]), info)

        with patch.object(t, "_load_model", return_value=mock_model):
            result = t.detect_language(str(tmp_audio_file))

        assert result.language == "en"


# ---------------------------------------------------------------------------
# transcribe tests
# ---------------------------------------------------------------------------


class TestTranscribe:
    """Tests for AudioTranscriber.transcribe."""

    def test_transcribe_file_not_found(self, make_transcriber: Any) -> None:
        t = make_transcriber()
        with pytest.raises(FileNotFoundError, match="Audio file not found"):
            t.transcribe("/nonexistent/audio.wav")

    def test_transcribe_default_options(
        self, make_transcriber: Any, tmp_audio_file: Path
    ) -> None:
        t = make_transcriber()
        seg = _make_segment(start=0.0, end=2.0, text=" Hello world ", avg_logprob=-0.2)
        info = _make_transcribe_info(language="en", language_probability=0.98, duration=2.0)
        mock_model = MagicMock()
        mock_model.transcribe.return_value = (iter([seg]), info)

        with patch.object(t, "_load_model", return_value=mock_model):
            result = t.transcribe(tmp_audio_file)

        assert isinstance(result, TranscriptionResult)
        assert result.text == "Hello world"
        assert result.language == "en"
        assert result.language_confidence == 0.98
        assert result.duration == 2.0
        assert result.model_size == "base"
        assert result.device == "cpu"
        assert result.error is None
        assert len(result.segments) == 1
        assert result.segments[0].text == "Hello world"

    def test_transcribe_confidence_from_logprob(
        self, make_transcriber: Any, tmp_audio_file: Path
    ) -> None:
        t = make_transcriber()
        log_prob = -0.5
        seg = _make_segment(avg_logprob=log_prob)
        info = _make_transcribe_info()
        mock_model = MagicMock()
        mock_model.transcribe.return_value = (iter([seg]), info)

        with patch.object(t, "_load_model", return_value=mock_model):
            result = t.transcribe(tmp_audio_file)

        expected_confidence = math.exp(log_prob)
        assert abs(result.segments[0].confidence - expected_confidence) < 1e-6

    def test_transcribe_zero_logprob(
        self, make_transcriber: Any, tmp_audio_file: Path
    ) -> None:
        """When avg_logprob is 0 (falsy), confidence should be 0.0."""
        t = make_transcriber()
        seg = _make_segment(avg_logprob=0)
        info = _make_transcribe_info()
        mock_model = MagicMock()
        mock_model.transcribe.return_value = (iter([seg]), info)

        with patch.object(t, "_load_model", return_value=mock_model):
            result = t.transcribe(tmp_audio_file)

        assert result.segments[0].confidence == 0.0

    def test_transcribe_with_word_timestamps(
        self, make_transcriber: Any, tmp_audio_file: Path
    ) -> None:
        t = make_transcriber()
        w1 = MagicMock(word="Hello", start=0.0, end=0.3, probability=0.95)
        w2 = MagicMock(word="world", start=0.35, end=0.7, probability=0.92)
        seg = _make_segment(words=[w1, w2])
        info = _make_transcribe_info()
        mock_model = MagicMock()
        mock_model.transcribe.return_value = (iter([seg]), info)

        opts = TranscriptionOptions(word_timestamps=True)
        with patch.object(t, "_load_model", return_value=mock_model):
            result = t.transcribe(tmp_audio_file, options=opts)

        words = result.segments[0].words
        assert words is not None
        assert len(words) == 2
        assert words[0]["word"] == "Hello"
        assert words[1]["confidence"] == 0.92

    def test_transcribe_without_word_timestamps(
        self, make_transcriber: Any, tmp_audio_file: Path
    ) -> None:
        t = make_transcriber()
        seg = _make_segment()
        # Remove 'words' attribute to simulate word_timestamps=False
        del seg.words
        info = _make_transcribe_info()
        mock_model = MagicMock()
        mock_model.transcribe.return_value = (iter([seg]), info)

        opts = TranscriptionOptions(word_timestamps=False)
        with patch.object(t, "_load_model", return_value=mock_model):
            result = t.transcribe(tmp_audio_file, options=opts)

        assert result.segments[0].words is None

    def test_transcribe_multiple_segments(
        self, make_transcriber: Any, tmp_audio_file: Path
    ) -> None:
        t = make_transcriber()
        seg1 = _make_segment(start=0.0, end=2.0, text=" First segment. ")
        seg2 = _make_segment(start=2.0, end=4.0, text=" Second segment. ")
        info = _make_transcribe_info(duration=4.0)
        mock_model = MagicMock()
        mock_model.transcribe.return_value = (iter([seg1, seg2]), info)

        with patch.object(t, "_load_model", return_value=mock_model):
            result = t.transcribe(tmp_audio_file)

        assert result.text == "First segment. Second segment."
        assert len(result.segments) == 2
        assert result.segments[0].start == 0.0
        assert result.segments[1].start == 2.0

    def test_transcribe_custom_options_passed(
        self, make_transcriber: Any, tmp_audio_file: Path
    ) -> None:
        t = make_transcriber()
        seg = _make_segment()
        info = _make_transcribe_info()
        mock_model = MagicMock()
        mock_model.transcribe.return_value = (iter([seg]), info)

        opts = TranscriptionOptions(
            language="fr",
            beam_size=3,
            best_of=3,
            temperature=0.2,
            vad_filter=False,
            word_timestamps=False,
            initial_prompt="This is a lecture.",
        )
        with patch.object(t, "_load_model", return_value=mock_model):
            t.transcribe(tmp_audio_file, options=opts)

        _, kwargs = mock_model.transcribe.call_args
        assert kwargs["language"] == "fr"
        assert kwargs["beam_size"] == 3
        assert kwargs["best_of"] == 3
        assert kwargs["temperature"] == 0.2
        assert kwargs["vad_filter"] is False
        assert kwargs["word_timestamps"] is False
        assert kwargs["initial_prompt"] == "This is a lecture."

    def test_transcribe_skips_load_when_already_loaded(
        self, make_transcriber: Any, tmp_audio_file: Path
    ) -> None:
        t = make_transcriber()
        t._model_loaded = True
        mock_model = MagicMock()
        t.model = mock_model
        seg = _make_segment()
        info = _make_transcribe_info()
        mock_model.transcribe.return_value = (iter([seg]), info)

        with patch.object(t, "_load_model") as load_mock:
            t.transcribe(tmp_audio_file)
            load_mock.assert_not_called()

    def test_transcribe_failure(
        self, make_transcriber: Any, tmp_audio_file: Path
    ) -> None:
        t = make_transcriber()
        mock_model = MagicMock()
        mock_model.transcribe.side_effect = RuntimeError("corrupted file")

        with patch.object(t, "_load_model", return_value=mock_model):
            with pytest.raises(RuntimeError, match="Transcription failed"):
                t.transcribe(tmp_audio_file)

    def test_transcribe_accepts_string_path(
        self, make_transcriber: Any, tmp_audio_file: Path
    ) -> None:
        t = make_transcriber()
        seg = _make_segment()
        info = _make_transcribe_info()
        mock_model = MagicMock()
        mock_model.transcribe.return_value = (iter([seg]), info)

        with patch.object(t, "_load_model", return_value=mock_model):
            result = t.transcribe(str(tmp_audio_file))

        assert isinstance(result, TranscriptionResult)

    def test_transcribe_processing_time_positive(
        self, make_transcriber: Any, tmp_audio_file: Path
    ) -> None:
        t = make_transcriber()
        seg = _make_segment()
        info = _make_transcribe_info(duration=10.0)
        mock_model = MagicMock()
        mock_model.transcribe.return_value = (iter([seg]), info)

        with patch.object(t, "_load_model", return_value=mock_model):
            result = t.transcribe(tmp_audio_file)

        assert result.processing_time >= 0.0


# ---------------------------------------------------------------------------
# Static / utility method tests
# ---------------------------------------------------------------------------


class TestStaticMethods:
    """Tests for static and class methods."""

    def test_get_supported_formats(self) -> None:
        formats = AudioTranscriber.get_supported_formats()
        assert isinstance(formats, list)
        assert "wav" in formats
        assert "mp3" in formats
        assert "flac" in formats
        assert "m4a" in formats
        assert "ogg" in formats
        assert "webm" in formats
        assert "opus" in formats
        assert len(formats) == 7

    def test_clear_cache(self, make_transcriber: Any) -> None:
        t = make_transcriber()
        cache_key = f"{t.model_size}_{t.device}_{t.compute_type}"
        AudioTranscriber._model_cache[cache_key] = MagicMock()
        t.model = MagicMock()
        t._model_loaded = True

        t.clear_cache()

        assert cache_key not in AudioTranscriber._model_cache
        assert t.model is None
        assert t._model_loaded is False

    def test_clear_cache_when_not_cached(self, make_transcriber: Any) -> None:
        """Clearing cache when key does not exist should not raise."""
        t = make_transcriber()
        t.clear_cache()
        assert t.model is None
        assert t._model_loaded is False

    def test_clear_all_caches(self, make_transcriber: Any) -> None:
        AudioTranscriber._model_cache["key1"] = MagicMock()
        AudioTranscriber._model_cache["key2"] = MagicMock()

        AudioTranscriber.clear_all_caches()

        assert len(AudioTranscriber._model_cache) == 0
