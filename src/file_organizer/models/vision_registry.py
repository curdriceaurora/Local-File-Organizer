"""Vision model registry - domain-specific metadata for vision models.

Extends :class:`~file_organizer.models.registry.ModelInfo` with
vision-specific fields like supported image formats and resolution.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from file_organizer.models.registry import ModelInfo


@dataclass
class VisionModelInfo(ModelInfo):
    """Metadata for an image/vision-processing model.

    Extends :class:`ModelInfo` with fields relevant to image
    understanding workloads.

    Attributes:
        supported_formats: Image file extensions the model handles.
        max_resolution: Maximum ``(width, height)`` in pixels.
    """

    supported_formats: list[str] = field(
        default_factory=lambda: ["jpg", "jpeg", "png", "gif", "bmp", "tiff"],
    )
    max_resolution: tuple[int, int] = (2048, 2048)


VISION_MODELS: list[VisionModelInfo] = [
    VisionModelInfo(
        name="qwen2.5vl:7b-q4_K_M",
        model_type="vision",
        size="6.0 GB",
        quantization="q4_K_M",
        description="Default vision model - image & video understanding.",
        supported_formats=["jpg", "jpeg", "png", "gif", "bmp", "tiff", "webp"],
        max_resolution=(2048, 2048),
    ),
    VisionModelInfo(
        name="llava:7b-v1.6-q4_K_M",
        model_type="vision",
        size="4.7 GB",
        quantization="q4_K_M",
        description="Alternative vision model - LLaVA v1.6.",
        supported_formats=["jpg", "jpeg", "png", "gif", "bmp"],
        max_resolution=(1344, 1344),
    ),
]
