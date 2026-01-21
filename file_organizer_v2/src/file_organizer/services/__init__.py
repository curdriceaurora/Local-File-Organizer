"""Processing services for different file types."""

from file_organizer.services.text_processor import TextProcessor, ProcessedFile
from file_organizer.services.vision_processor import VisionProcessor, ProcessedImage
from file_organizer.services.pattern_analyzer import (
    PatternAnalyzer,
    PatternAnalysis,
    NamingPattern,
    LocationPattern,
    ContentCluster,
)
from file_organizer.services.smart_suggestions import (
    SuggestionEngine,
    ConfidenceScorer,
)
from file_organizer.services.misplacement_detector import (
    MisplacementDetector,
    MisplacedFile,
    ContextAnalysis,
)
from file_organizer.services.suggestion_feedback import (
    SuggestionFeedback,
    FeedbackEntry,
    LearningStats,
)

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
