"""Processing services for different file types."""

from __future__ import annotations

from file_organizer.services.misplacement_detector import (
    ContextAnalysis,
    MisplacedFile,
    MisplacementDetector,
)
from file_organizer.services.pattern_analyzer import (
    ContentCluster,
    LocationPattern,
    NamingPattern,
    PatternAnalysis,
    PatternAnalyzer,
)
from file_organizer.services.smart_suggestions import (
    ConfidenceScorer,
    SuggestionEngine,
)
from file_organizer.services.suggestion_feedback import (
    FeedbackEntry,
    LearningStats,
    SuggestionFeedback,
)
from file_organizer.services.text_processor import ProcessedFile, TextProcessor
from file_organizer.services.vision_processor import ProcessedImage, VisionProcessor

__all__ = [
    "TextProcessor",
    "ProcessedFile",
    "VisionProcessor",
    "ProcessedImage",
    "PatternAnalyzer",
    "PatternAnalysis",
    "NamingPattern",
    "LocationPattern",
    "ContentCluster",
    "SuggestionEngine",
    "ConfidenceScorer",
    "MisplacementDetector",
    "MisplacedFile",
    "ContextAnalysis",
    "SuggestionFeedback",
    "FeedbackEntry",
    "LearningStats",
]
