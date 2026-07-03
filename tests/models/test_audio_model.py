"""Tests for AudioModel - the faster-whisper transcription model (issue #44)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from file_organizer.models.audio_model import (
    VALID_MODEL_SIZES,
    AudioModel,
    parse_model_size,
)
from file_organizer.models.base import DeviceType, ModelConfig, ModelType

_AVAILABLE_FLAG = "file_organizer.models.audio_model._FASTER_WHISPER_AVAILABLE"
_TRANSCRIBER_CLS = "file_organizer.services.audio.transcriber.AudioTranscriber"


def _audio_config(name: str = "tiny", **kwargs) -> ModelConfig:
    return ModelConfig(name=name, model_type=ModelType.AUDIO, **kwargs)


def _fake_transcription_result(text: str = "hello world"):
    """Build a real TranscriptionResult so attribute access matches production."""
    from file_organizer.services.audio.transcriber import (
        Segment,
        TranscriptionOptions,
        TranscriptionResult,
    )

    return TranscriptionResult(
        text=text,
        segments=[Segment(id=0, start=0.0, end=1.0, text=text)],
        language="en",
        language_confidence=0.99,
        duration=1.0,
        options=TranscriptionOptions(),
    )


@pytest.mark.unit
@pytest.mark.ci
class TestParseModelSize:
    """Model name normalization (plan item 1.6)."""

    @pytest.mark.parametrize("size", VALID_MODEL_SIZES)
    def test_bare_sizes_accepted(self, size: str) -> None:
        assert parse_model_size(size) == size

    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("whisper:base", "base"),
            ("whisper-small", "small"),
            ("faster-whisper-large-v3", "large-v3"),
            ("WHISPER:TINY", "tiny"),
            ("  medium ", "medium"),
        ],
    )
    def test_prefixed_and_cased_names_normalized(self, name: str, expected: str) -> None:
        assert parse_model_size(name) == expected

    @pytest.mark.parametrize("name", ["", "huge", "whisper:huge", "distil-whisper-large-v3"])
    def test_invalid_names_rejected(self, name: str) -> None:
        with pytest.raises(ValueError, match="Invalid Whisper model name"):
            parse_model_size(name)


@pytest.mark.unit
@pytest.mark.ci
class TestAudioModelConstruction:
    """Constructor validation."""

    @patch(_AVAILABLE_FLAG, True)
    def test_construct_with_audio_type(self) -> None:
        model = AudioModel(_audio_config("whisper:base"))
        assert model.model_size == "base"
        assert not model.is_initialized

    @patch(_AVAILABLE_FLAG, True)
    def test_rejects_non_audio_model_type(self) -> None:
        config = ModelConfig(name="tiny", model_type=ModelType.TEXT)
        with pytest.raises(ValueError, match="Expected AUDIO model type"):
            AudioModel(config)

    @patch(_AVAILABLE_FLAG, True)
    def test_rejects_unknown_model_size(self) -> None:
        with pytest.raises(ValueError, match="Invalid Whisper model name"):
            AudioModel(_audio_config("not-a-size"))

    @patch(_AVAILABLE_FLAG, False)
    def test_missing_faster_whisper_raises_import_error(self) -> None:
        """Graceful degradation: a clear install hint, not a crash later."""
        with pytest.raises(ImportError, match=r"local-file-organizer\[audio\]"):
            AudioModel(_audio_config())


@pytest.mark.unit
@pytest.mark.ci
@patch(_AVAILABLE_FLAG, True)
class TestAudioModelLifecycle:
    """initialize / generate / transcribe / cleanup with a mocked transcriber."""

    def _initialized_model(self, mock_transcriber_cls: MagicMock, **config_kwargs) -> AudioModel:
        model = AudioModel(_audio_config(**config_kwargs))
        model.initialize()
        return model

    @patch(_TRANSCRIBER_CLS)
    def test_initialize_loads_transcriber(self, mock_cls: MagicMock) -> None:
        model = self._initialized_model(mock_cls, name="whisper:small")
        assert model.is_initialized
        mock_cls.assert_called_once()
        _, kwargs = mock_cls.call_args
        assert kwargs["model_size"].value == "small"

    @patch(_TRANSCRIBER_CLS)
    def test_initialize_is_idempotent(self, mock_cls: MagicMock) -> None:
        model = self._initialized_model(mock_cls)
        model.initialize()
        assert mock_cls.call_count == 1

    @patch(_TRANSCRIBER_CLS)
    def test_generate_returns_transcript_text(self, mock_cls: MagicMock) -> None:
        mock_cls.return_value.transcribe.return_value = _fake_transcription_result("a transcript")
        model = self._initialized_model(mock_cls)
        assert model.generate("sample.wav") == "a transcript"

    @patch(_TRANSCRIBER_CLS)
    def test_transcribe_returns_full_result_with_segments(self, mock_cls: MagicMock) -> None:
        mock_cls.return_value.transcribe.return_value = _fake_transcription_result()
        model = self._initialized_model(mock_cls)
        result = model.transcribe("sample.wav")
        assert result.text == "hello world"
        assert len(result.segments) == 1
        assert result.language == "en"

    @patch(_TRANSCRIBER_CLS)
    def test_transcribe_forwards_language_option(self, mock_cls: MagicMock) -> None:
        mock_cls.return_value.transcribe.return_value = _fake_transcription_result()
        model = self._initialized_model(mock_cls)
        model.transcribe("sample.wav", language="de")
        _, options = mock_cls.return_value.transcribe.call_args[0]
        assert options.language == "de"

    def test_generate_before_initialize_raises(self) -> None:
        model = AudioModel(_audio_config())
        with pytest.raises(RuntimeError, match="not initialized"):
            model.generate("sample.wav")

    @patch(_TRANSCRIBER_CLS)
    def test_cleanup_unloads_model(self, mock_cls: MagicMock) -> None:
        model = self._initialized_model(mock_cls)
        model.cleanup()
        mock_cls.return_value.unload_model.assert_called_once()
        assert not model.is_initialized
        with pytest.raises(RuntimeError, match="not initialized"):
            model.generate("sample.wav")

    @patch(_TRANSCRIBER_CLS)
    def test_safe_cleanup_after_generate(self, mock_cls: MagicMock) -> None:
        """The benchmark path: initialize -> generate -> safe_cleanup."""
        mock_cls.return_value.transcribe.return_value = _fake_transcription_result()
        model = self._initialized_model(mock_cls)
        model.generate("sample.wav")
        model.safe_cleanup()
        assert not model.is_initialized


@pytest.mark.unit
@pytest.mark.ci
@patch(_AVAILABLE_FLAG, True)
class TestDeviceAndComputeSelection:
    """Device auto-detection and compute-type defaults (plan items 1.1, 4.2)."""

    @patch(_TRANSCRIBER_CLS)
    def test_explicit_cpu_uses_int8(self, mock_cls: MagicMock) -> None:
        model = AudioModel(_audio_config(device=DeviceType.CPU))
        model.initialize()
        _, kwargs = mock_cls.call_args
        assert kwargs["device"] == "cpu"
        assert kwargs["compute_type"].value == "int8"

    @patch(_TRANSCRIBER_CLS)
    def test_explicit_cuda_uses_float16(self, mock_cls: MagicMock) -> None:
        model = AudioModel(_audio_config(device=DeviceType.CUDA))
        model.initialize()
        _, kwargs = mock_cls.call_args
        assert kwargs["device"] == "cuda"
        assert kwargs["compute_type"].value == "float16"

    @patch(_TRANSCRIBER_CLS)
    def test_mps_falls_back_to_cpu(self, mock_cls: MagicMock) -> None:
        """CTranslate2 has no MPS backend; Apple Silicon must not crash."""
        model = AudioModel(_audio_config(device=DeviceType.MPS))
        model.initialize()
        _, kwargs = mock_cls.call_args
        assert kwargs["device"] == "cpu"

    @patch(_TRANSCRIBER_CLS)
    def test_auto_without_cuda_resolves_to_cpu(self, mock_cls: MagicMock) -> None:
        model = AudioModel(_audio_config(device=DeviceType.AUTO))
        with patch.object(model, "_resolve_device", wraps=model._resolve_device):
            fake_torch = MagicMock()
            fake_torch.cuda.is_available.return_value = False
            with patch.dict("sys.modules", {"torch": fake_torch}):
                model.initialize()
        _, kwargs = mock_cls.call_args
        assert kwargs["device"] == "cpu"

    @patch(_TRANSCRIBER_CLS)
    def test_auto_with_cuda_resolves_to_cuda(self, mock_cls: MagicMock) -> None:
        model = AudioModel(_audio_config(device=DeviceType.AUTO))
        fake_torch = MagicMock()
        fake_torch.cuda.is_available.return_value = True
        with patch.dict("sys.modules", {"torch": fake_torch}):
            model.initialize()
        _, kwargs = mock_cls.call_args
        assert kwargs["device"] == "cuda"

    @patch(_TRANSCRIBER_CLS)
    def test_compute_type_override_via_extra_params(self, mock_cls: MagicMock) -> None:
        model = AudioModel(
            _audio_config(device=DeviceType.CPU, extra_params={"compute_type": "float32"})
        )
        model.initialize()
        _, kwargs = mock_cls.call_args
        assert kwargs["compute_type"].value == "float32"


@pytest.mark.unit
@pytest.mark.ci
class TestDefaultConfig:
    """get_default_config contract (plan item 1.4)."""

    def test_default_config_shape(self) -> None:
        config = AudioModel.get_default_config()
        assert config.name == "whisper:base"
        assert config.model_type == ModelType.AUDIO
        assert config.framework == "faster-whisper"
        assert config.temperature == 0.0

    def test_default_config_custom_name(self) -> None:
        config = AudioModel.get_default_config("whisper:large-v3")
        assert config.name == "whisper:large-v3"
