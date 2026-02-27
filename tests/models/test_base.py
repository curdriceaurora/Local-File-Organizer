"""Tests for base model interfaces: ModelType, DeviceType, ModelConfig, BaseModel."""

from __future__ import annotations

from typing import Any

import pytest

from file_organizer.models.base import BaseModel, DeviceType, ModelConfig, ModelType


# --- Concrete stub for testing the ABC ---
class StubModel(BaseModel):  # type: ignore[misc]
    """Minimal concrete implementation of BaseModel for testing."""

    def __init__(self, config: ModelConfig) -> None:
        super().__init__(config)
        self.initialize_called = False
        self.cleanup_called = False

    def initialize(self) -> None:
        self.initialize_called = True
        self._initialized = True

    def generate(self, prompt: str, **kwargs: Any) -> str:
        return f"stub:{prompt}"

    def cleanup(self) -> None:
        self.cleanup_called = True
        self._initialized = False
        self.model = None


@pytest.fixture
def text_config() -> ModelConfig:
    return ModelConfig(name="test-model", model_type=ModelType.TEXT)


@pytest.mark.unit
class TestModelType:
    """Tests for ModelType enum."""

    def test_enum_values(self) -> None:
        """Test all ModelType enum members exist."""
        assert ModelType.TEXT.value == "text"
        assert ModelType.VISION.value == "vision"
        assert ModelType.AUDIO.value == "audio"
        assert ModelType.VIDEO.value == "video"

    def test_enum_count(self) -> None:
        """Test correct number of model types."""
        assert len(ModelType) == 4

    def test_from_value(self) -> None:
        """Test constructing enum from string value."""
        assert ModelType("text") == ModelType.TEXT
        assert ModelType("vision") == ModelType.VISION

    def test_invalid_value(self) -> None:
        """Test invalid enum value raises ValueError."""
        with pytest.raises(ValueError):
            ModelType("invalid")


@pytest.mark.unit
class TestDeviceType:
    """Tests for DeviceType enum."""

    def test_enum_values(self) -> None:
        """Test all DeviceType enum members exist."""
        assert DeviceType.AUTO.value == "auto"
        assert DeviceType.CPU.value == "cpu"
        assert DeviceType.CUDA.value == "cuda"
        assert DeviceType.MPS.value == "mps"
        assert DeviceType.METAL.value == "metal"

    def test_enum_count(self) -> None:
        """Test correct number of device types."""
        assert len(DeviceType) == 5

    def test_from_value(self) -> None:
        """Test constructing enum from string value."""
        assert DeviceType("cuda") == DeviceType.CUDA


@pytest.mark.unit
class TestModelConfig:
    """Tests for ModelConfig dataclass."""

    def test_default_values(self) -> None:
        """Test ModelConfig with only required fields uses correct defaults."""
        config = ModelConfig(name="test", model_type=ModelType.TEXT)
        assert config.name == "test"
        assert config.model_type == ModelType.TEXT
        assert config.quantization == "q4_k_m"
        assert config.device == DeviceType.AUTO
        assert config.temperature == 0.5
        assert config.max_tokens == 3000
        assert config.top_k == 3
        assert config.top_p == 0.3
        assert config.context_window == 4096
        assert config.batch_size == 1
        assert config.framework == "ollama"
        assert config.model_path is None
        assert config.local_path is None

    def test_post_init_none_extra_params(self) -> None:
        """Test extra_params defaults to empty dict via __post_init__."""
        config = ModelConfig(name="test", model_type=ModelType.TEXT)
        assert config.extra_params == {}
        assert isinstance(config.extra_params, dict)

    def test_post_init_preserves_existing_extra_params(self) -> None:
        """Test extra_params is preserved when explicitly set."""
        params = {"key": "value", "num": 42}
        config = ModelConfig(name="test", model_type=ModelType.TEXT, extra_params=params)
        assert config.extra_params == {"key": "value", "num": 42}

    def test_custom_values(self) -> None:
        """Test ModelConfig with all custom values."""
        config = ModelConfig(
            name="custom-model",
            model_type=ModelType.VISION,
            quantization="q8_0",
            device=DeviceType.CUDA,
            temperature=0.8,
            max_tokens=4096,
            top_k=10,
            top_p=0.9,
            context_window=8192,
            batch_size=4,
            framework="llama_cpp",
            model_path="/models/custom.gguf",
            local_path="/local/custom",
        )
        assert config.name == "custom-model"
        assert config.model_type == ModelType.VISION
        assert config.quantization == "q8_0"
        assert config.device == DeviceType.CUDA
        assert config.temperature == 0.8
        assert config.max_tokens == 4096
        assert config.framework == "llama_cpp"
        assert config.model_path == "/models/custom.gguf"
        assert config.local_path == "/local/custom"


@pytest.mark.unit
class TestBaseModel:
    """Tests for BaseModel abstract class via StubModel."""

    def test_init_stores_config(self, text_config: ModelConfig) -> None:
        """Test constructor stores config reference."""
        model = StubModel(text_config)
        assert model.config is text_config

    def test_init_not_initialized(self, text_config: ModelConfig) -> None:
        """Test model starts as not initialized."""
        model = StubModel(text_config)
        assert model.is_initialized is False
        assert model._initialized is False

    def test_init_model_is_none(self, text_config: ModelConfig) -> None:
        """Test model attribute starts as None."""
        model = StubModel(text_config)
        assert model.model is None

    def test_is_initialized_property(self, text_config: ModelConfig) -> None:
        """Test is_initialized property reflects _initialized state."""
        model = StubModel(text_config)
        assert model.is_initialized is False
        model._initialized = True
        assert model.is_initialized is True

    def test_context_manager_calls_initialize(self, text_config: ModelConfig) -> None:
        """Test __enter__ calls initialize when not initialized."""
        model = StubModel(text_config)
        with model as m:
            assert m is model
            assert m.initialize_called is True
            assert m.is_initialized is True

    def test_context_manager_calls_cleanup(self, text_config: ModelConfig) -> None:
        """Test __exit__ calls cleanup."""
        model = StubModel(text_config)
        with model:
            pass
        assert model.cleanup_called is True
        assert model.is_initialized is False

    def test_context_manager_skips_init_if_already_initialized(
        self, text_config: ModelConfig
    ) -> None:
        """Test __enter__ skips initialize when already initialized."""
        model = StubModel(text_config)
        model._initialized = True
        model.initialize_called = False  # reset tracker
        with model:
            assert model.initialize_called is False  # __enter__ skipped initialize()
        assert model.cleanup_called is True

    def test_repr(self, text_config: ModelConfig) -> None:
        """Test string representation format."""
        model = StubModel(text_config)
        result = repr(model)
        assert "StubModel(" in result
        assert "name=test-model" in result
        assert "framework=ollama" in result
        assert "initialized=False" in result

    def test_repr_after_initialize(self, text_config: ModelConfig) -> None:
        """Test repr reflects initialized state."""
        model = StubModel(text_config)
        model.initialize()
        result = repr(model)
        assert "initialized=True" in result

    def test_generate_returns_string(self, text_config: ModelConfig) -> None:
        """Test generate via stub returns expected format."""
        model = StubModel(text_config)
        assert model.generate("hello") == "stub:hello"
