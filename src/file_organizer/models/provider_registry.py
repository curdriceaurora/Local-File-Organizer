"""In-process registry mapping provider names to lazy model factory callables.

The module-level :data:`_registry` singleton is populated at import time by
:func:`_register_builtins`.  Third-party code can add new providers at runtime
via :func:`register_provider` without modifying this file.

Built-in providers:

- ``"ollama"``    — :class:`~file_organizer.models.text_model.TextModel` /
  :class:`~file_organizer.models.vision_model.VisionModel`
- ``"openai"``   — :class:`~file_organizer.models.openai_text_model.OpenAITextModel` /
  :class:`~file_organizer.models.openai_vision_model.OpenAIVisionModel`
- ``"llama_cpp"`` — :class:`~file_organizer.models.llama_cpp_text_model.LlamaCppTextModel`
  (text only; vision deferred to Phase 2)
- ``"mlx"`` — :class:`~file_organizer.models.mlx_text_model.MLXTextModel`
  (text only; vision deferred to Phase 3)
- ``"claude"``   — :class:`~file_organizer.models.claude_text_model.ClaudeTextModel` /
  :class:`~file_organizer.models.claude_vision_model.ClaudeVisionModel`
"""

from __future__ import annotations

import threading
from collections.abc import Callable

from file_organizer.models.base import BaseModel, ModelConfig

TextModelFactory = Callable[[ModelConfig], BaseModel]
VisionModelFactory = Callable[[ModelConfig], BaseModel]


class ProviderRegistry:
    """Thread-safe registry mapping provider names to model factory callables.

    Factory callables are stored as plain callables (not class references) so
    that optional packages (openai, llama_cpp, mlx_lm) are imported lazily — only when
    a model instance is actually requested.
    """

    def __init__(self) -> None:
        """Initialize the registry with empty factory maps."""
        self._lock = threading.Lock()
        self._text_factories: dict[str, TextModelFactory] = {}
        self._vision_factories: dict[str, VisionModelFactory] = {}

    def register(
        self,
        name: str,
        *,
        text_factory: TextModelFactory | None = None,
        vision_factory: VisionModelFactory | None = None,
    ) -> None:
        """Register text and/or vision factories for a provider name.

        Args:
            name: Provider identifier (e.g. ``"ollama"``, ``"openai"``).
            text_factory: Callable that accepts a ``ModelConfig`` and returns a
                text ``BaseModel`` instance.
            vision_factory: Callable that accepts a ``ModelConfig`` and returns
                a vision ``BaseModel`` instance.

        Raises:
            ValueError: If neither ``text_factory`` nor ``vision_factory`` is
                provided.
        """
        if text_factory is None and vision_factory is None:
            raise ValueError(
                f"At least one of text_factory or vision_factory must be provided "
                f"when registering provider '{name}'"
            )
        with self._lock:
            if text_factory is not None:
                self._text_factories[name] = text_factory
            if vision_factory is not None:
                self._vision_factories[name] = vision_factory

    def get_text_model(self, config: ModelConfig) -> BaseModel:
        """Return a text model instance for the given provider config.

        Args:
            config: Model configuration.  ``config.provider`` selects the
                registered factory.

        Returns:
            A new ``BaseModel`` instance produced by the registered factory.

        Raises:
            ValueError: If ``config.provider`` is not registered.
        """
        with self._lock:
            factory = self._text_factories.get(config.provider)
            registered = sorted(self._text_factories) if factory is None else None
        if factory is None:
            raise ValueError(
                f"Unknown provider {config.provider!r}. Registered providers: {registered}."
            )
        return factory(config)

    def get_vision_model(self, config: ModelConfig) -> BaseModel:
        """Return a vision model instance for the given provider config.

        Args:
            config: Model configuration.  ``config.provider`` selects the
                registered factory.

        Returns:
            A new ``BaseModel`` instance produced by the registered factory.

        Raises:
            ValueError: If ``config.provider`` is not registered or has no
                vision factory (e.g. ``"llama_cpp"`` in Phase 1).
        """
        with self._lock:
            factory = self._vision_factories.get(config.provider)
            registered = sorted(self._vision_factories) if factory is None else None
        if factory is None:
            raise ValueError(
                f"Unknown provider {config.provider!r} (or no vision factory registered). "
                f"Providers with vision support: {registered}."
            )
        return factory(config)

    @property
    def registered_providers(self) -> list[str]:
        """Return a sorted list of all registered provider names."""
        with self._lock:
            return sorted(set(self._text_factories) | set(self._vision_factories))

    def _reset_for_testing(self) -> None:
        """Clear all registered factories.

        **For test use only.**  Resets the registry to an empty state so that
        test suites can register custom providers without polluting the
        singleton across tests.
        """
        with self._lock:
            self._text_factories.clear()
            self._vision_factories.clear()


# ---------------------------------------------------------------------------
# Built-in factory helpers (lazy imports so optional packages load on demand)
# ---------------------------------------------------------------------------


def _ollama_text_factory(config: ModelConfig) -> BaseModel:
    """Lazy factory for Ollama text models.

    Args:
        config: Model configuration.

    Returns:
        A new ``TextModel`` instance.
    """
    from file_organizer.models.text_model import TextModel

    return TextModel(config)


def _ollama_vision_factory(config: ModelConfig) -> BaseModel:
    """Lazy factory for Ollama vision models.

    Args:
        config: Model configuration.

    Returns:
        A new ``VisionModel`` instance.
    """
    from file_organizer.models.vision_model import VisionModel

    return VisionModel(config)


def _openai_text_factory(config: ModelConfig) -> BaseModel:
    """Lazy factory for OpenAI text models.

    Args:
        config: Model configuration.

    Returns:
        A new ``OpenAITextModel`` instance.
    """
    from file_organizer.models.openai_text_model import OpenAITextModel

    return OpenAITextModel(config)


def _openai_vision_factory(config: ModelConfig) -> BaseModel:
    """Lazy factory for OpenAI vision models.

    Args:
        config: Model configuration.

    Returns:
        A new ``OpenAIVisionModel`` instance.
    """
    from file_organizer.models.openai_vision_model import OpenAIVisionModel

    return OpenAIVisionModel(config)


def _llama_cpp_text_factory(config: ModelConfig) -> BaseModel:
    """Lazy factory for llama.cpp text models.

    Args:
        config: Model configuration.

    Returns:
        A new ``LlamaCppTextModel`` instance.
    """
    from file_organizer.models.llama_cpp_text_model import LlamaCppTextModel

    return LlamaCppTextModel(config)


def _mlx_text_factory(config: ModelConfig) -> BaseModel:
    """Lazy factory for MLX text models on Apple Silicon.

    Args:
        config: Model configuration.

    Returns:
        A new ``MLXTextModel`` instance.
    """
    from file_organizer.models.mlx_text_model import MLXTextModel

    return MLXTextModel(config)


def _claude_text_factory(config: ModelConfig) -> BaseModel:
    """Return a ClaudeTextModel configured with the given ModelConfig."""
    from file_organizer.models.claude_text_model import ClaudeTextModel

    return ClaudeTextModel(config)


def _claude_vision_factory(config: ModelConfig) -> BaseModel:
    """Return a ClaudeVisionModel configured with the given ModelConfig."""
    from file_organizer.models.claude_vision_model import ClaudeVisionModel

    return ClaudeVisionModel(config)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_registry = ProviderRegistry()


def _register_builtins() -> None:
    """Populate the singleton registry with built-in providers."""
    _registry.register(
        "ollama",
        text_factory=_ollama_text_factory,
        vision_factory=_ollama_vision_factory,
    )
    _registry.register(
        "openai",
        text_factory=_openai_text_factory,
        vision_factory=_openai_vision_factory,
    )
    # llama_cpp: text only in Phase 1; vision factory added in Phase 2
    _registry.register(
        "llama_cpp",
        text_factory=_llama_cpp_text_factory,
    )
    # mlx: text only in Phase 2; vision factory added in Phase 3
    _registry.register(
        "mlx",
        text_factory=_mlx_text_factory,
    )
    # claude: both text and vision supported in Phase 1
    _registry.register(
        "claude",
        text_factory=_claude_text_factory,
        vision_factory=_claude_vision_factory,
    )


_register_builtins()


def register_provider(
    name: str,
    *,
    text_factory: TextModelFactory | None = None,
    vision_factory: VisionModelFactory | None = None,
) -> None:
    """Register a custom provider on the module-level singleton registry.

    Convenience wrapper around ``_registry.register()`` for third-party
    callers who don't want to import ``_registry`` directly.

    Args:
        name: Provider identifier.
        text_factory: Callable accepting a ``ModelConfig``, returning a
            text ``BaseModel``.
        vision_factory: Callable accepting a ``ModelConfig``, returning a
            vision ``BaseModel``.
    """
    _registry.register(name, text_factory=text_factory, vision_factory=vision_factory)
