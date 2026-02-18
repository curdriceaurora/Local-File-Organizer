"""
Video Processing Services

This module provides video file processing capabilities including:
- Scene detection and analysis
- Video metadata extraction
- Frame extraction
- Video format detection
"""

from __future__ import annotations

from .scene_detector import Scene, SceneDetectionResult, SceneDetector

__all__ = [
    "SceneDetector",
    "Scene",
    "SceneDetectionResult",
]
