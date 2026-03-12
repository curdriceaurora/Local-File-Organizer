"""Audio model registry - domain-specific metadata for audio models.

Extends :class:`~file_organizer.models.registry.ModelInfo` with
audio-specific fields like supported formats and max duration.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from file_organizer.models.registry import ModelInfo


@dataclass
class AudioModelInfo(ModelInfo):
    """Metadata for an audio-processing model.

    Extends :class:`ModelInfo` with fields relevant to audio
    transcription and analysis workloads.

    Attributes:
        supported_formats: Audio file extensions the model handles.
        max_duration_seconds: Maximum audio duration in seconds.
    """

    supported_formats: list[str] = field(
        default_factory=lambda: ["wav", "mp3", "flac", "m4a", "ogg"],
    )
    max_duration_seconds: int = 3600


AUDIO_MODELS: list[AudioModelInfo] = [
    AudioModelInfo(
        name="whisper:base",
        model_type="audio",
        size="0.1 GB",
        quantization="fp16",
        description="Audio transcription - base accuracy.",
        supported_formats=["wav", "mp3", "flac", "m4a", "ogg"],
        max_duration_seconds=1800,
    ),
    AudioModelInfo(
        name="whisper:small",
        model_type="audio",
        size="0.5 GB",
        quantization="fp16",
        description="Audio transcription - better accuracy.",
        supported_formats=["wav", "mp3", "flac", "m4a", "ogg"],
        max_duration_seconds=3600,
    ),
]
