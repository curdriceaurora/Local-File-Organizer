"""Factory for creating AI model instances based on provider configuration.

Delegates to the module-level :data:`~file_organizer.models.provider_registry._registry`
singleton so that new providers can be added by calling
:func:`~file_organizer.models.provider_registry.register_provider` without
modifying this file.

Built-in providers (registered at import time in ``provider_registry.py``):

- ``"ollama"``  — :class:`~file_organizer.models.text_model.TextModel` /
  :class:`~file_organizer.models.vision_model.VisionModel`
- ``"openai"``  — :class:`~file_organizer.models.openai_text_model.OpenAITextModel` /
  :class:`~file_organizer.models.openai_vision_model.OpenAIVisionModel`
- ``"llama_cpp"`` — :class:`~file_organizer.models.llama_cpp_text_model.LlamaCppTextModel`
  (text only; vision deferred to Phase 2)
- ``"claude"``   — :class:`~file_organizer.models.claude_text_model.ClaudeTextModel` /
  :class:`~file_organizer.models.claude_vision_model.ClaudeVisionModel`
"""

from __future__ import annotations

from file_organizer.models.base import BaseModel, ModelConfig
from file_organizer.models.provider_registry import _registry


def get_text_model(config: ModelConfig) -> BaseModel:
    """Return the appropriate text model for the given provider.

    Args:
        config: Model configuration, including ``provider`` field.

    Returns:
        A ``BaseModel`` instance selected by the registered factory for
        ``config.provider``.

    Raises:
        ValueError: If ``config.provider`` is not a recognised value.
    """
    return _registry.get_text_model(config)


def get_vision_model(config: ModelConfig) -> BaseModel:
    """Return the appropriate vision model for the given provider.

    Args:
        config: Model configuration, including ``provider`` field.

    Returns:
        A ``BaseModel`` instance selected by the registered factory for
        ``config.provider``.

    Raises:
        ValueError: If ``config.provider`` is not a recognised value or has
            no registered vision factory (e.g. ``"llama_cpp"`` in Phase 1).
    """
    return _registry.get_vision_model(config)
