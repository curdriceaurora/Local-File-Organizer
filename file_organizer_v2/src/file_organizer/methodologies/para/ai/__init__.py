"""
PARA AI Module

AI-powered smart suggestions for PARA categorization including:
- Feature extraction from files and content
- Intelligent suggestion engine combining heuristics and learned patterns
- Feedback collection and pattern learning
- PARA-aware file organization and movement

All AI features are privacy-first and work locally without cloud APIs.
The Ollama/TextModel integration is optional - everything works without it.
"""

from __future__ import annotations

from .feature_extractor import (
    FeatureExtractor,
    MetadataFeatures,
    StructuralFeatures,
    TextFeatures,
)
from .feedback import (
    AccuracyStats,
    FeedbackCollector,
    FeedbackEvent,
    LearnedRule,
    PatternLearner,
)
from .file_mover import (
    MoveResult,
    MoveSuggestion,
    OrganizationReport,
    PARAFileMover,
)
from .suggestion_engine import (
    PARASuggestion,
    PARASuggestionEngine,
)

__all__ = [
    # Feature extraction
    "FeatureExtractor",
    "TextFeatures",
    "MetadataFeatures",
    "StructuralFeatures",
    # Suggestion engine
    "PARASuggestion",
    "PARASuggestionEngine",
    # Feedback and learning
    "FeedbackEvent",
    "FeedbackCollector",
    "PatternLearner",
    "AccuracyStats",
    "LearnedRule",
    # File mover
    "MoveSuggestion",
    "MoveResult",
    "OrganizationReport",
    "PARAFileMover",
]
