"""
Video Processing Services

This module provides video file processing capabilities including:
- Scene detection and analysis
- Video metadata extraction
- Frame extraction
- Video format detection
"""

from .scene_detector import SceneDetector, Scene, SceneDetectionResult

__all__ = [
    "SceneDetector",
    "Scene",
    "SceneDetectionResult",
]
