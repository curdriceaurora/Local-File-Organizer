"""Integration-focused coverage tests for AudioModel."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from file_organizer.models.audio_model import AudioModel, parse_model_size
from file_organizer.models.base import DeviceType, ModelConfig, ModelType

pytestmark = [pytest.mark.integration]

_AVAILABLE_FLAG = "file_organizer.models.audio_model._FASTER_WHISPER_AVAILABLE"
_TRANSCRIBER_CLS = "file_organizer.services.audio.transcriber.AudioTranscriber"


def _audio_config(name: str = "whisper:base", **kwargs: object) -> ModelConfig:
    return ModelConfig(name=name, model_type=ModelType.AUDIO, **kwargs)


class TestAudioModelIntegrationFloor:
    @patch(_AVAILABLE_FLAG, True)
    def test_parse_model_size_accepts_supported_names(self) -> None:
        assert parse_model_size("base") == "base"
        assert parse_model_size("whisper:tiny") == "tiny"
        assert parse_model_size("faster-whisper-large-v3") == "large-v3"

    @patch(_AVAILABLE_FLAG, True)
    def test_parse_model_size_rejects_invalid_name(self) -> None:
        with pytest.raises(ValueError, match="Invalid Whisper model name"):
            parse_model_size("whisper:invalid")

    @patch(_AVAILABLE_FLAG, False)
    def test_constructor_raises_when_audio_extra_missing(self) -> None:
        with pytest.raises(ImportError, match="local-file-organizer\\[audio\\]"):
            AudioModel(_audio_config())

    @patch(_AVAILABLE_FLAG, True)
    def test_constructor_rejects_wrong_model_type(self) -> None:
        with pytest.raises(ValueError, match="Expected AUDIO model type"):
            AudioModel(ModelConfig(name="whisper:base", model_type=ModelType.TEXT))

    @patch(_AVAILABLE_FLAG, True)
    @patch(_TRANSCRIBER_CLS)
    def test_initialize_auto_device_without_torch_uses_cpu(self, mock_cls: MagicMock) -> None:
        model = AudioModel(_audio_config(device=DeviceType.AUTO))
        with patch(
            "file_organizer.models.audio_model.importlib.import_module", side_effect=ImportError
        ):
            model.initialize()

        assert model.is_initialized
        _, kwargs = mock_cls.call_args
        assert kwargs["device"] == "cpu"
        assert kwargs["compute_type"].value == "int8"

    @patch(_AVAILABLE_FLAG, True)
    @patch(_TRANSCRIBER_CLS)
    def test_initialize_mps_falls_back_to_cpu(self, mock_cls: MagicMock) -> None:
        model = AudioModel(_audio_config(device=DeviceType.MPS))
        model.initialize()

        _, kwargs = mock_cls.call_args
        assert kwargs["device"] == "cpu"

    @patch(_AVAILABLE_FLAG, True)
    @patch(_TRANSCRIBER_CLS)
    def test_transcribe_requires_initialize(self, mock_cls: MagicMock) -> None:
        model = AudioModel(_audio_config())
        with pytest.raises(RuntimeError, match="Model not initialized"):
            model.transcribe("clip.wav")
        mock_cls.assert_not_called()  # uninitialized transcribe must not construct the backend

    @patch(_AVAILABLE_FLAG, True)
    @patch(_TRANSCRIBER_CLS)
    def test_transcribe_forwards_options_and_cleanup_unloads(self, mock_cls: MagicMock) -> None:
        model = AudioModel(_audio_config(extra_params={"cache_dir": "hf-cache"}))
        fake_result = MagicMock()
        mock_cls.return_value.transcribe.return_value = fake_result

        model.initialize()
        result = model.transcribe("clip.wav", language="en", word_timestamps=True, beam_size=3)
        model.cleanup()

        assert result is fake_result
        options = mock_cls.return_value.transcribe.call_args.args[1]
        assert options.language == "en"
        assert options.word_timestamps is True
        assert options.beam_size == 3
        mock_cls.return_value.unload_model.assert_called_once()
        assert model.is_initialized is False

    @patch(_AVAILABLE_FLAG, True)
    @patch(_TRANSCRIBER_CLS)
    def test_get_default_config_shape(self, mock_cls: MagicMock) -> None:
        cfg = AudioModel.get_default_config("whisper:small")
        assert cfg.name == "whisper:small"
        assert cfg.model_type == ModelType.AUDIO
        assert cfg.framework == "faster-whisper"
        assert cfg.temperature == 0.0
        mock_cls.assert_not_called()  # config shape is static; no backend construction
