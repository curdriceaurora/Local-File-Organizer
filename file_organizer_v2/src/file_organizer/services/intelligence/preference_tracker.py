"""
Preference Tracking System - Core Module

This module implements the core preference tracking engine that learns from user
corrections and changes. It tracks user behavior, stores preferences with metadata,
and provides real-time preference updates with thread-safe operations.

Features:
- Track file moves, renames, and category override corrections
- In-memory preference management with metadata
- Thread-safe operations using locks
- Preference confidence and frequency tracking
- Real-time preference updates
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Dict, List, Optional, Tuple
from enum import Enum
import hashlib


class PreferenceType(Enum):
    """Types of preferences that can be tracked."""
    FOLDER_MAPPING = "folder_mapping"
    NAMING_PATTERN = "naming_pattern"
    CATEGORY_OVERRIDE = "category_override"
    FILE_EXTENSION = "file_extension"
    CUSTOM = "custom"


class CorrectionType(Enum):
    """Types of corrections that can be tracked."""
    FILE_MOVE = "file_move"
    FILE_RENAME = "file_rename"
    CATEGORY_CHANGE = "category_change"
    FOLDER_CREATION = "folder_creation"
    MANUAL_OVERRIDE = "manual_override"


@dataclass
class PreferenceMetadata:
    """Metadata associated with a preference."""
    created: datetime
    updated: datetime
    confidence: float = 0.5  # Initial confidence 0.5
    frequency: int = 1  # Number of times this preference was observed
    last_used: Optional[datetime] = None
    source: str = "user_correction"  # Source of the preference

    def to_dict(self) -> dict:
        """Convert metadata to dictionary."""
        return {
            "created": self.created.isoformat(),
            "updated": self.updated.isoformat(),
            "confidence": self.confidence,
            "frequency": self.frequency,
            "last_used": self.last_used.isoformat() if self.last_used else None,
            "source": self.source
        }

    @staticmethod
    def from_dict(data: dict) -> "PreferenceMetadata":
        """Create metadata from dictionary."""
        return PreferenceMetadata(
            created=datetime.fromisoformat(data["created"]),
            updated=datetime.fromisoformat(data["updated"]),
            confidence=data.get("confidence", 0.5),
            frequency=data.get("frequency", 1),
            last_used=datetime.fromisoformat(data["last_used"]) if data.get("last_used") else None,
            source=data.get("source", "user_correction")
        )


@dataclass
class Preference:
    """A tracked preference with its metadata."""
    preference_type: PreferenceType
    key: str  # Identifier for the preference (e.g., file pattern, category name)
    value: any  # The preference value
    metadata: PreferenceMetadata
    context: Dict[str, any] = field(default_factory=dict)  # Additional context

    def to_dict(self) -> dict:
        """Convert preference to dictionary."""
        return {
            "preference_type": self.preference_type.value,
            "key": self.key,
            "value": self.value,
            "metadata": self.metadata.to_dict(),
            "context": self.context
        }

    @staticmethod
    def from_dict(data: dict) -> "Preference":
        """Create preference from dictionary."""
        return Preference(
            preference_type=PreferenceType(data["preference_type"]),
            key=data["key"],
            value=data["value"],
            metadata=PreferenceMetadata.from_dict(data["metadata"]),
            context=data.get("context", {})
        )


@dataclass
class Correction:
    """A user correction that informs preferences."""
    correction_type: CorrectionType
    source: Path
    destination: Path
    timestamp: datetime
    context: Dict[str, any] = field(default_factory=dict)

    def get_pattern_key(self) -> str:
        """Generate a unique key for this correction pattern."""
        # Create a key based on the correction pattern
        key_parts = [
            self.correction_type.value,
            str(self.source.suffix.lower()) if self.source.suffix else "no_ext",
            str(self.destination.parent.name) if self.destination.parent else "root"
        ]
        return "|".join(key_parts)

    def to_dict(self) -> dict:
        """Convert correction to dictionary."""
        return {
            "correction_type": self.correction_type.value,
            "source": str(self.source),
            "destination": str(self.destination),
            "timestamp": self.timestamp.isoformat(),
            "context": self.context
        }


class PreferenceTracker:
    """
    Core preference tracking engine that learns from user corrections.

    This class manages in-memory preferences with thread-safe operations,
    tracks user corrections, and maintains preference metadata including
    confidence scores and usage frequency.
    """

    def __init__(self):
        """Initialize the preference tracker."""
        self._lock = RLock()  # Reentrant lock for thread safety
        self._preferences: Dict[str, List[Preference]] = {}  # Key -> List of preferences
        self._corrections: List[Correction] = []  # History of corrections
        self._statistics = {
            "total_corrections": 0,
            "total_preferences": 0,
            "successful_applications": 0,
            "failed_applications": 0
        }

    def track_correction(
        self,
        source: Path,
        destination: Path,
        correction_type: CorrectionType,
        context: Optional[Dict[str, any]] = None
    ) -> None:
        """
        Track a user correction and update preferences accordingly.

        Args:
            source: Original file path
            destination: New file path after user correction
            correction_type: Type of correction made
            context: Additional context about the correction
        """
        with self._lock:
            now = datetime.now(timezone.utc)

            # Create correction record
            correction = Correction(
                correction_type=correction_type,
                source=source,
                destination=destination,
                timestamp=now,
                context=context or {}
            )

            self._corrections.append(correction)
            self._statistics["total_corrections"] += 1

            # Extract and update preferences based on correction type
            self._extract_preferences_from_correction(correction)

    def _extract_preferences_from_correction(self, correction: Correction) -> None:
        """
        Extract and update preferences from a correction.

        This method analyzes the correction and updates relevant preferences.
        Must be called within a lock.
        """
        now = datetime.now(timezone.utc)
        pattern_key = correction.get_pattern_key()

        # Determine preference type based on correction type
        if correction.correction_type == CorrectionType.FILE_MOVE:
            pref_type = PreferenceType.FOLDER_MAPPING
            pref_key = pattern_key
            pref_value = str(correction.destination.parent)

        elif correction.correction_type == CorrectionType.FILE_RENAME:
            pref_type = PreferenceType.NAMING_PATTERN
            pref_key = pattern_key
            pref_value = correction.destination.name

        elif correction.correction_type == CorrectionType.CATEGORY_CHANGE:
            pref_type = PreferenceType.CATEGORY_OVERRIDE
            pref_key = pattern_key
            pref_value = correction.context.get("new_category", "unknown")

        else:
            # For other types, create a custom preference
            pref_type = PreferenceType.CUSTOM
            pref_key = pattern_key
            pref_value = {
                "destination": str(correction.destination),
                "source": str(correction.source)
            }

        # Check if preference already exists
        existing_pref = self._find_preference(pref_type, pref_key)

        if existing_pref:
            # Update existing preference
            existing_pref.metadata.updated = now
            existing_pref.metadata.frequency += 1
            existing_pref.metadata.last_used = now

            # Increase confidence based on frequency (cap at 0.95)
            confidence_increase = min(0.05, (1.0 - existing_pref.metadata.confidence) * 0.1)
            existing_pref.metadata.confidence = min(0.95,
                existing_pref.metadata.confidence + confidence_increase)

            # Update value if it changed
            if existing_pref.value != pref_value:
                existing_pref.value = pref_value
                existing_pref.context["value_changed"] = True
        else:
            # Create new preference
            metadata = PreferenceMetadata(
                created=now,
                updated=now,
                confidence=0.5,  # Start with medium confidence
                frequency=1,
                last_used=now,
                source="user_correction"
            )

            preference = Preference(
                preference_type=pref_type,
                key=pref_key,
                value=pref_value,
                metadata=metadata,
                context={
                    "correction_type": correction.correction_type.value,
                    "source_extension": correction.source.suffix.lower()
                }
            )

            # Add to preferences
            storage_key = self._get_storage_key(pref_type, pref_key)
            if storage_key not in self._preferences:
                self._preferences[storage_key] = []
            self._preferences[storage_key].append(preference)
            self._statistics["total_preferences"] += 1

    def _find_preference(
        self,
        preference_type: PreferenceType,
        key: str
    ) -> Optional[Preference]:
        """
        Find an existing preference by type and key.

        Must be called within a lock.
        """
        storage_key = self._get_storage_key(preference_type, key)
        prefs = self._preferences.get(storage_key, [])

        for pref in prefs:
            if pref.preference_type == preference_type and pref.key == key:
                return pref

        return None

    def _get_storage_key(self, preference_type: PreferenceType, key: str) -> str:
        """Generate a storage key for a preference."""
        return f"{preference_type.value}:{key}"

    def get_preference(
        self,
        file_path: Path,
        preference_type: PreferenceType,
        context: Optional[Dict[str, any]] = None
    ) -> Optional[Preference]:
        """
        Get a preference for a given file path and type.

        Args:
            file_path: Path to the file
            preference_type: Type of preference to retrieve
            context: Additional context for matching

        Returns:
            The best matching preference or None
        """
        with self._lock:
            # For folder mapping preferences, match by extension and correction type
            # Not by current parent directory, since we want to learn where to move files
            if preference_type == PreferenceType.FOLDER_MAPPING:
                extension = file_path.suffix.lower() if file_path.suffix else "no_ext"

                # Find all folder mapping preferences for this extension
                matching_prefs = []
                for storage_key, prefs_list in self._preferences.items():
                    if not storage_key.startswith("folder_mapping:"):
                        continue
                    for pref in prefs_list:
                        if pref.preference_type == PreferenceType.FOLDER_MAPPING:
                            # Check if this preference matches the extension
                            if pref.context.get("source_extension") == extension:
                                matching_prefs.append(pref)

                if not matching_prefs:
                    return None

                # Return the preference with highest confidence
                best_pref = max(matching_prefs, key=lambda p: p.metadata.confidence)
                best_pref.metadata.last_used = datetime.now(timezone.utc)
                return best_pref

            # For other preference types, use exact pattern matching
            pattern_parts = [
                preference_type.value,
                file_path.suffix.lower() if file_path.suffix else "no_ext",
                file_path.parent.name if file_path.parent else "root"
            ]
            pattern_key = "|".join(pattern_parts)

            storage_key = self._get_storage_key(preference_type, pattern_key)
            prefs = self._preferences.get(storage_key, [])

            if not prefs:
                return None

            # Return the preference with highest confidence
            best_pref = max(prefs, key=lambda p: p.metadata.confidence)

            # Update last used timestamp
            best_pref.metadata.last_used = datetime.now(timezone.utc)

            return best_pref

    def get_all_preferences(
        self,
        preference_type: Optional[PreferenceType] = None
    ) -> List[Preference]:
        """
        Get all preferences, optionally filtered by type.

        Args:
            preference_type: Optional type filter

        Returns:
            List of preferences
        """
        with self._lock:
            all_prefs = []
            for prefs_list in self._preferences.values():
                all_prefs.extend(prefs_list)

            if preference_type:
                all_prefs = [p for p in all_prefs
                           if p.preference_type == preference_type]

            return all_prefs

    def update_preference_confidence(
        self,
        preference: Preference,
        success: bool
    ) -> None:
        """
        Update preference confidence based on application success.

        Args:
            preference: The preference that was applied
            success: Whether the application was successful
        """
        with self._lock:
            now = datetime.now(timezone.utc)

            if success:
                # Increase confidence (cap at 0.98)
                preference.metadata.confidence = min(0.98,
                    preference.metadata.confidence + 0.05)
                preference.metadata.last_used = now
                self._statistics["successful_applications"] += 1
            else:
                # Decrease confidence (floor at 0.1)
                preference.metadata.confidence = max(0.1,
                    preference.metadata.confidence - 0.1)
                self._statistics["failed_applications"] += 1

            preference.metadata.updated = now

    def get_statistics(self) -> dict:
        """
        Get statistics about tracked preferences.

        Returns:
            Dictionary with statistics
        """
        with self._lock:
            stats = self._statistics.copy()
            stats["unique_preferences"] = len(self._preferences)
            stats["total_correction_history"] = len(self._corrections)

            # Calculate average confidence
            all_prefs = self.get_all_preferences()
            if all_prefs:
                avg_confidence = sum(p.metadata.confidence for p in all_prefs) / len(all_prefs)
                stats["average_confidence"] = round(avg_confidence, 3)
            else:
                stats["average_confidence"] = 0.0

            return stats

    def clear_preferences(self, preference_type: Optional[PreferenceType] = None) -> int:
        """
        Clear preferences, optionally filtered by type.

        Args:
            preference_type: Optional type filter

        Returns:
            Number of preferences cleared
        """
        with self._lock:
            if preference_type is None:
                # Clear all preferences
                count = sum(len(prefs) for prefs in self._preferences.values())
                self._preferences.clear()
                self._corrections.clear()
                self._statistics["total_preferences"] = 0
                return count
            else:
                # Clear only preferences of specific type
                count = 0
                keys_to_remove = []

                for storage_key, prefs_list in self._preferences.items():
                    filtered_prefs = [p for p in prefs_list
                                    if p.preference_type != preference_type]
                    count += len(prefs_list) - len(filtered_prefs)

                    if not filtered_prefs:
                        keys_to_remove.append(storage_key)
                    else:
                        self._preferences[storage_key] = filtered_prefs

                for key in keys_to_remove:
                    del self._preferences[key]

                self._statistics["total_preferences"] -= count
                return count

    def export_data(self) -> dict:
        """
        Export all preference data for persistence.

        Returns:
            Dictionary with all preferences and metadata
        """
        with self._lock:
            return {
                "preferences": {
                    key: [p.to_dict() for p in prefs]
                    for key, prefs in self._preferences.items()
                },
                "corrections": [c.to_dict() for c in self._corrections],
                "statistics": self._statistics.copy(),
                "exported_at": datetime.now(timezone.utc).isoformat()
            }

    def import_data(self, data: dict) -> None:
        """
        Import preference data from persistence.

        Args:
            data: Dictionary with preference data
        """
        with self._lock:
            # Clear existing data
            self._preferences.clear()
            self._corrections.clear()

            # Import preferences
            for key, prefs_list in data.get("preferences", {}).items():
                self._preferences[key] = [
                    Preference.from_dict(p) for p in prefs_list
                ]

            # Import corrections
            for corr_data in data.get("corrections", []):
                correction = Correction(
                    correction_type=CorrectionType(corr_data["correction_type"]),
                    source=Path(corr_data["source"]),
                    destination=Path(corr_data["destination"]),
                    timestamp=datetime.fromisoformat(corr_data["timestamp"]),
                    context=corr_data.get("context", {})
                )
                self._corrections.append(correction)

            # Import statistics
            if "statistics" in data:
                self._statistics.update(data["statistics"])

    def get_corrections_for_file(self, file_path: Path) -> List[Correction]:
        """
        Get all corrections related to a specific file.

        Args:
            file_path: Path to the file

        Returns:
            List of corrections
        """
        with self._lock:
            return [
                c for c in self._corrections
                if c.source == file_path or c.destination == file_path
            ]

    def get_recent_corrections(self, limit: int = 10) -> List[Correction]:
        """
        Get the most recent corrections.

        Args:
            limit: Maximum number of corrections to return

        Returns:
            List of recent corrections
        """
        with self._lock:
            sorted_corrections = sorted(
                self._corrections,
                key=lambda c: c.timestamp,
                reverse=True
            )
            return sorted_corrections[:limit]


# Convenience functions for common operations

def create_tracker() -> PreferenceTracker:
    """Create a new preference tracker instance."""
    return PreferenceTracker()


def track_file_move(
    tracker: PreferenceTracker,
    source: Path,
    destination: Path,
    context: Optional[Dict[str, any]] = None
) -> None:
    """
    Convenience function to track a file move correction.

    Args:
        tracker: PreferenceTracker instance
        source: Original file path
        destination: New file path
        context: Additional context
    """
    tracker.track_correction(
        source=source,
        destination=destination,
        correction_type=CorrectionType.FILE_MOVE,
        context=context
    )


def track_file_rename(
    tracker: PreferenceTracker,
    source: Path,
    destination: Path,
    context: Optional[Dict[str, any]] = None
) -> None:
    """
    Convenience function to track a file rename correction.

    Args:
        tracker: PreferenceTracker instance
        source: Original file path
        destination: New file path
        context: Additional context
    """
    tracker.track_correction(
        source=source,
        destination=destination,
        correction_type=CorrectionType.FILE_RENAME,
        context=context
    )


def track_category_change(
    tracker: PreferenceTracker,
    file_path: Path,
    old_category: str,
    new_category: str,
    context: Optional[Dict[str, any]] = None
) -> None:
    """
    Convenience function to track a category change correction.

    Args:
        tracker: PreferenceTracker instance
        file_path: Path to the file
        old_category: Original category
        new_category: New category
        context: Additional context
    """
    ctx = context or {}
    ctx.update({
        "old_category": old_category,
        "new_category": new_category
    })

    tracker.track_correction(
        source=file_path,
        destination=file_path,  # Same path for category change
        correction_type=CorrectionType.CATEGORY_CHANGE,
        context=ctx
    )
