"""Model registry — catalogue of available AI models.

Provides a static catalogue of known Ollama models for file
organization, with their types, sizes, and descriptions.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ModelInfo:
    """Metadata about an available AI model.

    Args:
        name: Ollama model tag (e.g. ``qwen2.5:3b-instruct-q4_K_M``).
        model_type: Category — ``text``, ``vision``, or ``audio``.
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


# Static catalogue of recommended models.
AVAILABLE_MODELS: list[ModelInfo] = [
    ModelInfo(
        name="qwen2.5:3b-instruct-q4_K_M",
        model_type="text",
        size="1.9 GB",
        quantization="q4_K_M",
        description="Default text model — fast file description & naming.",
    ),
    ModelInfo(
        name="qwen2.5:7b-instruct-q4_K_M",
        model_type="text",
        size="4.4 GB",
        quantization="q4_K_M",
        description="Larger text model — higher quality, slower.",
    ),
    ModelInfo(
        name="qwen2.5vl:7b-q4_K_M",
        model_type="vision",
        size="6.0 GB",
        quantization="q4_K_M",
        description="Default vision model — image & video understanding.",
    ),
    ModelInfo(
        name="llava:7b-v1.6-q4_K_M",
        model_type="vision",
        size="4.7 GB",
        quantization="q4_K_M",
        description="Alternative vision model — LLaVA v1.6.",
    ),
    ModelInfo(
        name="whisper:base",
        model_type="audio",
        size="0.1 GB",
        quantization="fp16",
        description="Audio transcription — base accuracy.",
    ),
    ModelInfo(
        name="whisper:small",
        model_type="audio",
        size="0.5 GB",
        quantization="fp16",
        description="Audio transcription — better accuracy.",
    ),
]
