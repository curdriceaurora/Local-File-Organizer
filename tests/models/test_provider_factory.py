"""Unit tests for provider_factory — routes ModelConfig.provider to correct model class."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from file_organizer.models.base import ModelConfig, ModelType
from file_organizer.models.provider_factory import get_text_model, get_vision_model
from file_organizer.models.text_model import TextModel
from file_organizer.models.vision_model import VisionModel

pytestmark = [pytest.mark.unit, pytest.mark.ci]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def ollama_text_config() -> ModelConfig:
    return ModelConfig(name="qwen2.5:3b", model_type=ModelType.TEXT, provider="ollama")


@pytest.fixture()
def ollama_vision_config() -> ModelConfig:
    return ModelConfig(name="qwen2.5vl:7b", model_type=ModelType.VISION, provider="ollama")


@pytest.fixture()
def openai_text_config() -> ModelConfig:
    return ModelConfig(
        name="gpt-4o-mini",
        model_type=ModelType.TEXT,
        provider="openai",
        api_key="sk-test",
    )


@pytest.fixture()
def openai_vision_config() -> ModelConfig:
    return ModelConfig(
        name="gpt-4o-mini",
        model_type=ModelType.VISION,
        provider="openai",
        api_key="sk-test",
    )


@pytest.fixture()
def llama_cpp_text_config() -> ModelConfig:
    return ModelConfig(
        name="llama-cpp",
        model_type=ModelType.TEXT,
        provider="llama_cpp",
        model_path="/fake/model.gguf",
    )


@pytest.fixture()
def mlx_text_config() -> ModelConfig:
    return ModelConfig(
        name="mlx-lm",
        model_type=ModelType.TEXT,
        provider="mlx",
        model_path="mlx-community/Qwen2.5-3B-Instruct-4bit",
    )


# ---------------------------------------------------------------------------
# get_text_model
# ---------------------------------------------------------------------------


class TestGetTextModel:
    def test_ollama_provider_returns_text_model(self, ollama_text_config: ModelConfig) -> None:
        with patch("file_organizer.models.text_model.OLLAMA_AVAILABLE", True):
            model = get_text_model(ollama_text_config)

        assert isinstance(model, TextModel)
        assert model.config is ollama_text_config

    def test_openai_provider_returns_openai_text_model(
        self, openai_text_config: ModelConfig
    ) -> None:
        with patch("file_organizer.models.openai_text_model.OPENAI_AVAILABLE", True):
            model = get_text_model(openai_text_config)

        # Import here to avoid eager loading in module scope
        from file_organizer.models.openai_text_model import OpenAITextModel

        assert isinstance(model, OpenAITextModel)
        assert model.config is openai_text_config

    def test_llama_cpp_provider_returns_llama_cpp_text_model(
        self, llama_cpp_text_config: ModelConfig
    ) -> None:
        with patch("file_organizer.models.llama_cpp_text_model.LLAMA_CPP_AVAILABLE", True):
            model = get_text_model(llama_cpp_text_config)

        from file_organizer.models.llama_cpp_text_model import LlamaCppTextModel

        assert isinstance(model, LlamaCppTextModel)
        assert model.config is llama_cpp_text_config

    def test_mlx_provider_returns_mlx_text_model(self, mlx_text_config: ModelConfig) -> None:
        with patch("file_organizer.models.mlx_text_model.MLX_LM_AVAILABLE", True):
            model = get_text_model(mlx_text_config)

        from file_organizer.models.mlx_text_model import MLXTextModel

        assert isinstance(model, MLXTextModel)
        assert model.config is mlx_text_config

    def test_unknown_provider_raises_value_error(self) -> None:
        # mypy would catch this at type time; we test the runtime guard too
        bad_config = ModelConfig(
            name="some-model",
            model_type=ModelType.TEXT,
            provider="ollama",  # start valid then mutate for test
        )
        bad_config.provider = "anthropic"  # type: ignore[assignment]

        with pytest.raises(ValueError, match="Unknown provider"):
            get_text_model(bad_config)

    def test_unknown_provider_error_mentions_registered_providers(self) -> None:
        bad_config = ModelConfig(name="x", model_type=ModelType.TEXT, provider="ollama")
        bad_config.provider = "invalid"  # type: ignore[assignment]

        # All built-in providers should appear in the error message
        with pytest.raises(ValueError) as exc_info:
            get_text_model(bad_config)
        error_msg = str(exc_info.value)
        assert "ollama" in error_msg
        assert "openai" in error_msg
        assert "llama_cpp" in error_msg
        assert "mlx" in error_msg
        assert "claude" in error_msg


# ---------------------------------------------------------------------------
# get_vision_model
# ---------------------------------------------------------------------------


class TestGetVisionModel:
    def test_ollama_provider_returns_vision_model(self, ollama_vision_config: ModelConfig) -> None:
        with patch("file_organizer.models.vision_model.OLLAMA_AVAILABLE", True):
            model = get_vision_model(ollama_vision_config)

        assert isinstance(model, VisionModel)
        assert model.config is ollama_vision_config

    def test_openai_provider_returns_openai_vision_model(
        self, openai_vision_config: ModelConfig
    ) -> None:
        with patch("file_organizer.models.openai_vision_model.OPENAI_AVAILABLE", True):
            model = get_vision_model(openai_vision_config)

        from file_organizer.models.openai_vision_model import OpenAIVisionModel

        assert isinstance(model, OpenAIVisionModel)
        assert model.config is openai_vision_config

    def test_unknown_provider_raises_value_error(self) -> None:
        bad_config = ModelConfig(name="x", model_type=ModelType.VISION, provider="ollama")
        bad_config.provider = "google"  # type: ignore[assignment]

        with pytest.raises(ValueError, match="Unknown provider"):
            get_vision_model(bad_config)

    def test_llama_cpp_vision_raises_value_error(self) -> None:
        """llama_cpp has no vision factory in Phase 1."""
        vision_cfg = ModelConfig(
            name="llama-cpp",
            model_type=ModelType.VISION,
            provider="llama_cpp",
            model_path="/fake/model.gguf",
        )
        with pytest.raises(ValueError, match="llama_cpp"):
            get_vision_model(vision_cfg)

    def test_mlx_vision_raises_value_error(self) -> None:
        """mlx has no vision factory in Phase 3."""
        vision_cfg = ModelConfig(
            name="mlx-lm",
            model_type=ModelType.VISION,
            provider="mlx",
            model_path="mlx-community/Qwen2.5-3B-Instruct-4bit",
        )
        with pytest.raises(ValueError, match="mlx"):
            get_vision_model(vision_cfg)
