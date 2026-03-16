"""Unit tests for ProviderRegistry — registration, dispatch, and error handling."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from file_organizer.models.base import ModelConfig, ModelType
from file_organizer.models.provider_registry import (
    ProviderRegistry,
    _register_builtins,
    _registry,
    register_provider,
)

pytestmark = [pytest.mark.unit, pytest.mark.ci]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def fresh_registry() -> ProviderRegistry:
    """Return a new, empty ProviderRegistry (isolated from builtins)."""
    return ProviderRegistry()


@pytest.fixture()
def text_config() -> ModelConfig:
    return ModelConfig(name="test-model", model_type=ModelType.TEXT, provider="ollama")


@pytest.fixture()
def vision_config() -> ModelConfig:
    return ModelConfig(name="test-model", model_type=ModelType.VISION, provider="ollama")


# ---------------------------------------------------------------------------
# Module-level singleton: built-in providers
# ---------------------------------------------------------------------------


class TestBuiltinRegistration:
    def test_registered_providers_includes_ollama(self) -> None:
        assert "ollama" in _registry.registered_providers

    def test_registered_providers_includes_openai(self) -> None:
        assert "openai" in _registry.registered_providers

    def test_registered_providers_includes_llama_cpp(self) -> None:
        assert "llama_cpp" in _registry.registered_providers

    def test_registered_providers_is_sorted(self) -> None:
        providers = _registry.registered_providers
        assert providers == sorted(providers)


# ---------------------------------------------------------------------------
# ProviderRegistry.register()
# ---------------------------------------------------------------------------


class TestRegister:
    def test_register_text_factory(self, fresh_registry: ProviderRegistry) -> None:
        factory = MagicMock()
        fresh_registry.register("custom", text_factory=factory)
        assert "custom" in fresh_registry.registered_providers

    def test_register_vision_factory(self, fresh_registry: ProviderRegistry) -> None:
        factory = MagicMock()
        fresh_registry.register("custom", vision_factory=factory)
        assert "custom" in fresh_registry.registered_providers

    def test_register_both_factories(self, fresh_registry: ProviderRegistry) -> None:
        tf = MagicMock()
        vf = MagicMock()
        fresh_registry.register("both", text_factory=tf, vision_factory=vf)
        assert "both" in fresh_registry.registered_providers

    def test_register_neither_raises(self, fresh_registry: ProviderRegistry) -> None:
        with pytest.raises(ValueError, match="text_factory or vision_factory"):
            fresh_registry.register("empty")

    def test_register_overwrites_existing(self, fresh_registry: ProviderRegistry) -> None:
        factory_a = MagicMock(return_value="model_a")
        factory_b = MagicMock(return_value="model_b")
        cfg = ModelConfig(name="x", model_type=ModelType.TEXT, provider="p")
        fresh_registry.register("p", text_factory=factory_a)
        fresh_registry.register("p", text_factory=factory_b)
        fresh_registry.get_text_model(cfg)
        factory_b.assert_called_once_with(cfg)
        factory_a.assert_not_called()


# ---------------------------------------------------------------------------
# ProviderRegistry.get_text_model()
# ---------------------------------------------------------------------------


class TestGetTextModel:
    def test_dispatches_to_registered_text_factory(self, fresh_registry: ProviderRegistry) -> None:
        mock_model = MagicMock()
        factory = MagicMock(return_value=mock_model)
        cfg = ModelConfig(name="m", model_type=ModelType.TEXT, provider="myp")
        fresh_registry.register("myp", text_factory=factory)

        result = fresh_registry.get_text_model(cfg)

        factory.assert_called_once_with(cfg)
        assert result is mock_model

    def test_unknown_provider_raises_value_error(self, fresh_registry: ProviderRegistry) -> None:
        cfg = ModelConfig(name="m", model_type=ModelType.TEXT, provider="unknown")
        with pytest.raises(ValueError, match="Unknown provider"):
            fresh_registry.get_text_model(cfg)

    def test_error_message_includes_provider_name(self, fresh_registry: ProviderRegistry) -> None:
        cfg = ModelConfig(name="m", model_type=ModelType.TEXT, provider="unknown")
        cfg.provider = "xyzzy"  # type: ignore[assignment]
        with pytest.raises(ValueError, match="xyzzy"):
            fresh_registry.get_text_model(cfg)

    def test_error_message_lists_registered_providers(
        self, fresh_registry: ProviderRegistry
    ) -> None:
        fresh_registry.register("alpha", text_factory=MagicMock())
        cfg = ModelConfig(name="m", model_type=ModelType.TEXT, provider="alpha")
        cfg.provider = "missing"  # type: ignore[assignment]
        with pytest.raises(ValueError, match="alpha"):
            fresh_registry.get_text_model(cfg)

    def test_dispatches_ollama_to_text_model(self, text_config: ModelConfig) -> None:
        with patch("file_organizer.models.text_model.OLLAMA_AVAILABLE", True):
            model = _registry.get_text_model(text_config)
        from file_organizer.models.text_model import TextModel

        assert isinstance(model, TextModel)

    def test_dispatches_llama_cpp_to_llama_cpp_text_model(self) -> None:
        cfg = ModelConfig(
            name="llama-cpp",
            model_type=ModelType.TEXT,
            provider="llama_cpp",
            model_path="/fake/model.gguf",
        )
        with patch("file_organizer.models.llama_cpp_text_model.LLAMA_CPP_AVAILABLE", True):
            model = _registry.get_text_model(cfg)
        from file_organizer.models.llama_cpp_text_model import LlamaCppTextModel

        assert isinstance(model, LlamaCppTextModel)


# ---------------------------------------------------------------------------
# ProviderRegistry.get_vision_model()
# ---------------------------------------------------------------------------


class TestGetVisionModel:
    def test_dispatches_to_registered_vision_factory(
        self, fresh_registry: ProviderRegistry
    ) -> None:
        mock_model = MagicMock()
        factory = MagicMock(return_value=mock_model)
        cfg = ModelConfig(name="m", model_type=ModelType.VISION, provider="vp")
        fresh_registry.register("vp", vision_factory=factory)

        result = fresh_registry.get_vision_model(cfg)

        factory.assert_called_once_with(cfg)
        assert result is mock_model

    def test_unknown_provider_raises_value_error(self, fresh_registry: ProviderRegistry) -> None:
        cfg = ModelConfig(name="m", model_type=ModelType.VISION, provider="nope")
        with pytest.raises(ValueError, match="Unknown provider"):
            fresh_registry.get_vision_model(cfg)

    def test_llama_cpp_has_no_vision_factory(self) -> None:
        """llama_cpp vision is deferred to Phase 2 — registry should have no factory."""
        cfg = ModelConfig(
            name="llama-cpp",
            model_type=ModelType.VISION,
            provider="llama_cpp",
            model_path="/fake/model.gguf",
        )
        with pytest.raises(ValueError, match="llama_cpp"):
            _registry.get_vision_model(cfg)

    def test_dispatches_ollama_to_vision_model(self, vision_config: ModelConfig) -> None:
        with patch("file_organizer.models.vision_model.OLLAMA_AVAILABLE", True):
            model = _registry.get_vision_model(vision_config)
        from file_organizer.models.vision_model import VisionModel

        assert isinstance(model, VisionModel)


# ---------------------------------------------------------------------------
# register_provider() convenience wrapper
# ---------------------------------------------------------------------------


class TestRegisterProviderFunction:
    def test_registers_on_singleton_via_convenience_function(self) -> None:
        factory = MagicMock(return_value=MagicMock())
        cfg = ModelConfig(name="m", model_type=ModelType.TEXT, provider="convenience_test_mp")

        # Isolate from the global singleton so this test does not leak state.
        _registry._reset_for_testing()
        try:
            register_provider("convenience_test_mp", text_factory=factory)

            result = _registry.get_text_model(cfg)
            factory.assert_called_once_with(cfg)
            assert result is factory.return_value
        finally:
            # Restore built-in providers so tests running after this one are unaffected
            # (pytest-randomly may execute this test before TestBuiltinRegistration).
            _register_builtins()
