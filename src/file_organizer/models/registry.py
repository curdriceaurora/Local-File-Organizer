"""Model registry - catalogue of available AI models.

Provides a static catalogue of known models for file organization,
with their types, sizes, and descriptions.  Acts as a **facade** over
the domain-specific registries (text, vision, audio) so callers that
don't need domain metadata can continue to use the unified
``AVAILABLE_MODELS`` list.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass


@dataclass
class ModelInfo:
    """Metadata about an available AI model.

    Args:
        name: Ollama model tag (e.g. ``qwen2.5:3b-instruct-q4_K_M``).
        model_type: Category - ``text``, ``vision``, or ``audio``.
        size: Approximate download size (e.g. ``"1.9 GB"``).
        quantization: Quantization level (e.g. ``"q4_K_M"``).
        description: Short human-readable description.
        installed: Whether the model is currently available locally.
    """

    name: str
    model_type: str
    size: str
    quantization: str
    description: str
    installed: bool = False


def get_text_models() -> list[ModelInfo]:
    """Return a deep copy of all registered text models with domain metadata.

    Returns a copy so that callers cannot mutate the shared registry state.
    """
    from file_organizer.models.text_registry import TEXT_MODELS

    return copy.deepcopy(list(TEXT_MODELS))


def get_vision_models() -> list[ModelInfo]:
    """Return a deep copy of all registered vision models with domain metadata.

    Returns a copy so that callers cannot mutate the shared registry state.
    """
    from file_organizer.models.vision_registry import VISION_MODELS

    return copy.deepcopy(list(VISION_MODELS))


def get_audio_models() -> list[ModelInfo]:
    """Return a deep copy of all registered audio models with domain metadata.

    Returns a copy so that callers cannot mutate the shared registry state.
    """
    from file_organizer.models.audio_registry import AUDIO_MODELS

    return copy.deepcopy(list(AUDIO_MODELS))


def get_all_models() -> list[ModelInfo]:
    """Return all models across all domains."""
    return get_text_models() + get_vision_models() + get_audio_models()


# Backward-compatible static list — populated from domain registries.
AVAILABLE_MODELS: list[ModelInfo] = get_all_models()
