"""
Audio Processing Services

This module provides audio file processing capabilities including:
- Audio transcription using Whisper models
- Audio format preprocessing and conversion
- Audio metadata extraction
- Audio utility functions
"""

from .metadata_extractor import AudioMetadata, AudioMetadataExtractor
from .preprocessor import AudioFormat, AudioPreprocessor
from .transcriber import AudioTranscriber, TranscriptionOptions, TranscriptionResult
from .utils import (
    convert_audio_format,
    get_audio_duration,
    normalize_audio,
    split_audio,
    validate_audio_file,
)

__all__ = [
    # Transcription
    "AudioTranscriber",
    "TranscriptionResult",
    "TranscriptionOptions",
    # Metadata
    "AudioMetadataExtractor",
    "AudioMetadata",
    # Preprocessing
    "AudioPreprocessor",
    "AudioFormat",
    # Utilities
    "get_audio_duration",
    "normalize_audio",
    "split_audio",
    "convert_audio_format",
    "validate_audio_file",
]
