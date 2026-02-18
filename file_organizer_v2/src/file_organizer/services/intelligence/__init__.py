"""
Intelligence services for learning user preferences and patterns.

This module provides intelligent learning capabilities that adapt to user
behavior and preferences over time.
"""

from __future__ import annotations

from file_organizer.services.intelligence.confidence import (
    ConfidenceEngine,
    PatternUsageData,
    UsageRecord,
)
from file_organizer.services.intelligence.conflict_resolver import ConflictResolver
from file_organizer.services.intelligence.directory_prefs import DirectoryPrefs
from file_organizer.services.intelligence.feedback_processor import FeedbackProcessor
from file_organizer.services.intelligence.folder_learner import FolderPreferenceLearner
from file_organizer.services.intelligence.naming_analyzer import (
    NameStructure,
    NamingAnalyzer,
)
from file_organizer.services.intelligence.pattern_extractor import (
    NamingPattern,
    NamingPatternExtractor,
    PatternElement,
)
from file_organizer.services.intelligence.pattern_learner import PatternLearner
from file_organizer.services.intelligence.preference_store import (
    DirectoryPreference,
    PreferenceStore,
    SchemaVersion,
)
from file_organizer.services.intelligence.preference_tracker import (
    Correction,
    CorrectionType,
    Preference,
    PreferenceMetadata,
    PreferenceTracker,
    PreferenceType,
    create_tracker,
    track_category_change,
    track_file_move,
    track_file_rename,
)
from file_organizer.services.intelligence.profile_exporter import ProfileExporter
from file_organizer.services.intelligence.profile_importer import ProfileImporter, ValidationResult
from file_organizer.services.intelligence.profile_manager import Profile, ProfileManager
from file_organizer.services.intelligence.profile_merger import MergeStrategy, ProfileMerger
from file_organizer.services.intelligence.profile_migrator import ProfileMigrator
from file_organizer.services.intelligence.scoring import (
    PatternScorer,
    ScoreAnalyzer,
    ScoredPattern,
)
from file_organizer.services.intelligence.template_manager import TemplateManager

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
    "Profile",
    "ProfileManager",
    "ProfileExporter",
    "ProfileImporter",
    "ValidationResult",
    "ProfileMigrator",
    "ProfileMerger",
    "MergeStrategy",
    "TemplateManager",
]
