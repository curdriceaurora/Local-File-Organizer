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
from file_organizer.services.intelligence.directory_prefs import DirectoryPrefs
from file_organizer.services.intelligence.conflict_resolver import ConflictResolver

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
    "DirectoryPrefs",
    "ConflictResolver",
]
