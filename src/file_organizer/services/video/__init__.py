"""
Video Processing Services

This module provides video file processing capabilities including:
- Scene detection and analysis
- Video metadata extraction
- Frame extraction
- Video format detection
"""

from __future__ import annotations

from .metadata_extractor import VideoMetadata, VideoMetadataExtractor, resolution_label
from .organizer import VideoOrganizer, is_screen_recording
from .scene_detector import Scene, SceneDetectionResult, SceneDetector

__all__ = [
    "SceneDetector",
    "Scene",
    "SceneDetectionResult",
    "VideoMetadata",
    "VideoMetadataExtractor",
    "VideoOrganizer",
    "is_screen_recording",
    "resolution_label",
]
