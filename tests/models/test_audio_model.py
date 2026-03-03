"""Tests for audio model: AudioModel stub implementation and configuration."""

from __future__ import annotations

import pytest

from file_organizer.models.audio_model import AudioModel
from file_organizer.models.base import ModelConfig, ModelType


@pytest.mark.unit
class TestAudioModelInit:
    """Tests for AudioModel initialization."""

    def test_audio_model_init_valid(self) -> None:
        """Test creating AudioModel with valid AUDIO config."""
        config = ModelConfig(
            name="whisper-base",
            model_type=ModelType.AUDIO,
        )
        model = AudioModel(config)

        assert model.config == config
        assert model.config.name == "whisper-base"
        assert model.config.model_type == ModelType.AUDIO
        assert not model.is_initialized

    def test_audio_model_init_with_framework(self) -> None:
        """Test AudioModel with faster-whisper framework."""
        config = ModelConfig(
            name="whisper-large",
            model_type=ModelType.AUDIO,
            framework="faster-whisper",
        )
        model = AudioModel(config)

        assert model.config.framework == "faster-whisper"

    def test_audio_model_init_wrong_type_text(self) -> None:
        """Test AudioModel rejects TEXT model type."""
        config = ModelConfig(
            name="text-model",
            model_type=ModelType.TEXT,
        )
        with pytest.raises(ValueError, match="Expected AUDIO model type"):
            AudioModel(config)

    def test_audio_model_init_wrong_type_vision(self) -> None:
        """Test AudioModel rejects VISION model type."""
        config = ModelConfig(
            name="vision-model",
            model_type=ModelType.VISION,
        )
        with pytest.raises(ValueError, match="Expected AUDIO model type"):
            AudioModel(config)

    def test_audio_model_init_wrong_type_video(self) -> None:
        """Test AudioModel rejects VIDEO model type."""
        config = ModelConfig(
            name="video-model",
            model_type=ModelType.VIDEO,
        )
        with pytest.raises(ValueError, match="Expected AUDIO model type"):
            AudioModel(config)

    def test_audio_model_config_preserved(self) -> None:
        """Test that config is properly preserved."""
        config = ModelConfig(
            name="test-audio",
            model_type=ModelType.AUDIO,
            temperature=0.1,
            max_tokens=512,
        )
        model = AudioModel(config)

        assert model.config.name == "test-audio"
        assert model.config.temperature == 0.1
        assert model.config.max_tokens == 512


@pytest.mark.unit
class TestAudioModelInitialize:
    """Tests for AudioModel.initialize() method."""

    def test_initialize_sets_flag(self) -> None:
        """Test that initialize sets the initialized flag."""
        config = ModelConfig(
            name="whisper-base",
            model_type=ModelType.AUDIO,
        )
        model = AudioModel(config)

        assert not model.is_initialized
        model.initialize()
        assert model.is_initialized

    def test_initialize_multiple_calls(self) -> None:
        """Test that initialize can be called multiple times."""
        config = ModelConfig(
            name="whisper-base",
            model_type=ModelType.AUDIO,
        )
        model = AudioModel(config)

        model.initialize()
        assert model.is_initialized
        model.initialize()
        assert model.is_initialized


@pytest.mark.unit
class TestAudioModelGenerate:
    """Tests for AudioModel.generate() method."""

    def test_generate_not_implemented(self) -> None:
        """Test that generate raises NotImplementedError."""
        config = ModelConfig(
            name="whisper-base",
            model_type=ModelType.AUDIO,
        )
        model = AudioModel(config)

        with pytest.raises(NotImplementedError, match="Phase 3"):
            model.generate("audio.mp3")

    def test_generate_with_kwargs_not_implemented(self) -> None:
        """Test that generate with kwargs raises NotImplementedError."""
        config = ModelConfig(
            name="whisper-base",
            model_type=ModelType.AUDIO,
        )
        model = AudioModel(config)

        with pytest.raises(NotImplementedError):
            model.generate("audio.mp3", language="en", task="transcribe")

    def test_generate_before_initialize(self) -> None:
        """Test that generate fails before initialize."""
        config = ModelConfig(
            name="whisper-base",
            model_type=ModelType.AUDIO,
        )
        model = AudioModel(config)

        assert not model.is_initialized
        with pytest.raises(NotImplementedError):
            model.generate("audio.mp3")

    def test_generate_after_initialize(self) -> None:
        """Test that generate fails even after initialize."""
        config = ModelConfig(
            name="whisper-base",
            model_type=ModelType.AUDIO,
        )
        model = AudioModel(config)

        model.initialize()
        assert model.is_initialized
        with pytest.raises(NotImplementedError):
            model.generate("audio.mp3")


@pytest.mark.unit
class TestAudioModelCleanup:
    """Tests for AudioModel.cleanup() method."""

    def test_cleanup_unsets_flag(self) -> None:
        """Test that cleanup unsets the initialized flag."""
        config = ModelConfig(
            name="whisper-base",
            model_type=ModelType.AUDIO,
        )
        model = AudioModel(config)

        model.initialize()
        assert model.is_initialized
        model.cleanup()
        assert not model.is_initialized

    def test_cleanup_callable(self) -> None:
        """Test that cleanup is callable."""
        config = ModelConfig(
            name="whisper-base",
            model_type=ModelType.AUDIO,
        )
        model = AudioModel(config)

        model.initialize()
        # Cleanup should be callable without errors
        model.cleanup()
        assert not model.is_initialized

    def test_cleanup_without_initialize(self) -> None:
        """Test that cleanup works without initialize."""
        config = ModelConfig(
            name="whisper-base",
            model_type=ModelType.AUDIO,
        )
        model = AudioModel(config)

        assert not model.is_initialized
        model.cleanup()
        assert not model.is_initialized

    def test_cleanup_multiple_calls(self) -> None:
        """Test that cleanup can be called multiple times."""
        config = ModelConfig(
            name="whisper-base",
            model_type=ModelType.AUDIO,
        )
        model = AudioModel(config)

        model.initialize()
        model.cleanup()
        assert not model.is_initialized
        model.cleanup()
        assert not model.is_initialized


@pytest.mark.unit
class TestAudioModelGetDefaultConfig:
    """Tests for AudioModel.get_default_config() static method."""

    def test_default_config_creation(self) -> None:
        """Test creating default config."""
        config = AudioModel.get_default_config()

        assert config.name == "distil-whisper-large-v3"
        assert config.model_type == ModelType.AUDIO
        assert config.framework == "faster-whisper"

    def test_default_config_temperature(self) -> None:
        """Test default config has zero temperature."""
        config = AudioModel.get_default_config()

        assert config.temperature == 0.0

    def test_default_config_max_tokens(self) -> None:
        """Test default config has appropriate max_tokens."""
        config = AudioModel.get_default_config()

        assert config.max_tokens == 1000

    def test_default_config_custom_name(self) -> None:
        """Test creating default config with custom model name."""
        config = AudioModel.get_default_config(model_name="whisper-small")

        assert config.name == "whisper-small"
        assert config.model_type == ModelType.AUDIO

    def test_default_config_usable_for_model(self) -> None:
        """Test that default config can be used to create model."""
        config = AudioModel.get_default_config()
        model = AudioModel(config)

        assert model.config.name == "distil-whisper-large-v3"
        assert model.config.model_type == ModelType.AUDIO

    def test_default_config_framework(self) -> None:
        """Test that default config uses faster-whisper framework."""
        config = AudioModel.get_default_config()

        assert config.framework == "faster-whisper"

    def test_default_config_is_independent_copy(self) -> None:
        """Test that multiple calls create independent configs."""
        config1 = AudioModel.get_default_config("model1")
        config2 = AudioModel.get_default_config("model2")

        assert config1.name == "model1"
        assert config2.name == "model2"
        assert config1.model_type == config2.model_type


@pytest.mark.unit
class TestAudioModelLifecycle:
    """Tests for complete AudioModel lifecycle."""

    def test_full_lifecycle(self) -> None:
        """Test complete initialize-cleanup lifecycle."""
        config = AudioModel.get_default_config()
        model = AudioModel(config)

        # Check initial state
        assert not model.is_initialized

        # Initialize
        model.initialize()
        assert model.is_initialized

        # Cleanup
        model.cleanup()
        assert not model.is_initialized

    def test_multiple_lifecycle_cycles(self) -> None:
        """Test multiple init-cleanup cycles."""
        config = ModelConfig(
            name="test",
            model_type=ModelType.AUDIO,
        )
        model = AudioModel(config)

        for _ in range(3):
            assert not model.is_initialized
            model.initialize()
            assert model.is_initialized
            model.cleanup()
            assert not model.is_initialized

    def test_model_attribute_lifecycle(self) -> None:
        """Test model attribute during lifecycle."""
        config = ModelConfig(
            name="test",
            model_type=ModelType.AUDIO,
        )
        model = AudioModel(config)

        assert model.model is None
        model.initialize()
        assert model.is_initialized
        model.model = "test-model-object"
        assert model.model == "test-model-object"
        model.cleanup()
        assert not model.is_initialized
        # Model attribute is preserved after cleanup (cleanup only updates flag)
        assert model.model == "test-model-object"


@pytest.mark.unit
class TestAudioModelConfiguration:
    """Tests for AudioModel configuration options."""

    def test_config_with_extra_params(self) -> None:
        """Test AudioModel with extra parameters."""
        config = ModelConfig(
            name="whisper",
            model_type=ModelType.AUDIO,
            extra_params={"language": "en", "task": "transcribe"},
        )
        model = AudioModel(config)

        assert model.config.extra_params["language"] == "en"
        assert model.config.extra_params["task"] == "transcribe"

    def test_config_quantization(self) -> None:
        """Test AudioModel config quantization settings."""
        config = ModelConfig(
            name="whisper",
            model_type=ModelType.AUDIO,
            quantization="int8",
        )
        model = AudioModel(config)

        assert model.config.quantization == "int8"

    def test_config_device_cpu(self) -> None:
        """Test AudioModel with CPU device."""
        from file_organizer.models.base import DeviceType

        config = ModelConfig(
            name="whisper",
            model_type=ModelType.AUDIO,
            device=DeviceType.CPU,
        )
        model = AudioModel(config)

        assert model.config.device == DeviceType.CPU

    def test_config_context_window(self) -> None:
        """Test AudioModel context window configuration."""
        config = ModelConfig(
            name="whisper",
            model_type=ModelType.AUDIO,
            context_window=8192,
        )
        model = AudioModel(config)

        assert model.config.context_window == 8192
