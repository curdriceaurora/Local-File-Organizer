"""Text model registry - domain-specific metadata for text models.

Extends :class:`~file_organizer.models.registry.ModelInfo` with
text-specific fields like context window and max tokens.
"""

from __future__ import annotations

from dataclasses import dataclass

from file_organizer.config.defaults import DEFAULT_TEXT_MODEL, DEFAULT_TEXT_MODEL_LARGE
from file_organizer.models.registry import ModelInfo


@dataclass
class TextModelInfo(ModelInfo):
    """Metadata for a text-processing model.

    Extends :class:`ModelInfo` with fields that matter for text
    generation and summarization workloads.

    Attributes:
        context_window: Maximum input context in tokens.
        max_tokens: Maximum output tokens per generation.
    """

    context_window: int = 4096
    max_tokens: int = 3000


TEXT_MODELS: list[TextModelInfo] = [
    TextModelInfo(
        name=DEFAULT_TEXT_MODEL,
        model_type="text",
        size="1.9 GB",
        quantization="q4_K_M",
        description="Default text model - fast file description & naming.",
        context_window=4096,
        max_tokens=3000,
    ),
    TextModelInfo(
        name=DEFAULT_TEXT_MODEL_LARGE,
        model_type="text",
        size="4.4 GB",
        quantization="q4_K_M",
        description="Larger text model - higher quality, slower.",
        context_window=8192,
        max_tokens=4096,
    ),
]
