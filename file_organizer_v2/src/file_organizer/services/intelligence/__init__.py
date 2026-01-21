"""
Intelligence services for learning user preferences and patterns.

This module provides intelligent learning capabilities that adapt to user
behavior and preferences over time.
"""

from file_organizer.services.intelligence.preference_tracker import (
    PreferenceTracker,
    Preference,
    PreferenceType,
    PreferenceMetadata,
    Correction,
    CorrectionType,
    create_tracker,
    track_file_move,
    track_file_rename,
    track_category_change,
)
from file_organizer.services.intelligence.preference_store import (
    PreferenceStore,
    DirectoryPreference,
    SchemaVersion,
)
from file_organizer.services.intelligence.directory_prefs import DirectoryPrefs
from file_organizer.services.intelligence.conflict_resolver import ConflictResolver
from file_organizer.services.intelligence.confidence import (
    ConfidenceEngine,
    UsageRecord,
    PatternUsageData,
)
from file_organizer.services.intelligence.scoring import (
    PatternScorer,
    ScoredPattern,
    ScoreAnalyzer,
)
from file_organizer.services.intelligence.pattern_extractor import (
    NamingPatternExtractor,
    NamingPattern,
    PatternElement,
)
from file_organizer.services.intelligence.naming_analyzer import (
    NamingAnalyzer,
    NameStructure,
)
from file_organizer.services.intelligence.folder_learner import FolderPreferenceLearner
from file_organizer.services.intelligence.feedback_processor import FeedbackProcessor
from file_organizer.services.intelligence.pattern_learner import PatternLearner

__all__ = [
    "PreferenceTracker",
    "Preference",
    "PreferenceType",
    "PreferenceMetadata",
    "Correction",
    "CorrectionType",
    "create_tracker",
    "track_file_move",
    "track_file_rename",
    "track_category_change",
    "PreferenceStore",
    "DirectoryPreference",
    "SchemaVersion",
    "DirectoryPrefs",
    "ConflictResolver",
    "ConfidenceEngine",
    "UsageRecord",
    "PatternUsageData",
    "PatternScorer",
    "ScoredPattern",
    "ScoreAnalyzer",
    "NamingPatternExtractor",
    "NamingPattern",
    "PatternElement",
    "NamingAnalyzer",
    "NameStructure",
    "FolderPreferenceLearner",
    "FeedbackProcessor",
    "PatternLearner",
]
