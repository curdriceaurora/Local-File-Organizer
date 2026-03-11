"""Factory for creating AI model instances based on provider configuration.

Import note: ``OpenAITextModel`` and ``OpenAIVisionModel`` are imported lazily
inside each factory function so that the ``openai`` package (an optional cloud
dependency) is never loaded at module import time for Ollama-only users.
"""

from __future__ import annotations

from file_organizer.models.base import BaseModel, ModelConfig
from file_organizer.models.text_model import TextModel
from file_organizer.models.vision_model import VisionModel


def get_text_model(config: ModelConfig) -> BaseModel:
    """Return the appropriate text model for the given provider.

    Args:
        config: Model configuration, including ``provider`` field.

    Returns:
        A ``BaseModel`` instance: ``TextModel`` for ``"ollama"`` or
        ``OpenAITextModel`` for ``"openai"``.

    Raises:
        ValueError: If ``config.provider`` is not a recognised value.
    """
    if config.provider == "openai":
        # Lazy import: avoids loading the openai package for Ollama-only users.
        from file_organizer.models.openai_text_model import OpenAITextModel

        return OpenAITextModel(config)
    if config.provider == "ollama":
        return TextModel(config)
    raise ValueError(f"Unknown provider {config.provider!r}. Supported values: 'ollama', 'openai'.")


def get_vision_model(config: ModelConfig) -> BaseModel:
    """Return the appropriate vision model for the given provider.

    Args:
        config: Model configuration, including ``provider`` field.

    Returns:
        A ``BaseModel`` instance: ``VisionModel`` for ``"ollama"`` or
        ``OpenAIVisionModel`` for ``"openai"``.

    Raises:
        ValueError: If ``config.provider`` is not a recognised value.
    """
    if config.provider == "openai":
        # Lazy import: avoids loading the openai package for Ollama-only users.
        from file_organizer.models.openai_vision_model import OpenAIVisionModel

        return OpenAIVisionModel(config)
    if config.provider == "ollama":
        return VisionModel(config)
    raise ValueError(f"Unknown provider {config.provider!r}. Supported values: 'ollama', 'openai'.")
