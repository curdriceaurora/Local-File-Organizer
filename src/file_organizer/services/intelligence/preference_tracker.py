"""Preference Tracking System - Core Module.

This module implements the core preference tracking engine that learns from user
corrections and changes. It tracks user behavior, stores preferences with metadata,
and provides real-time preference updates with thread-safe operations.

Storage backend (Epic D / D5, issue #157): the tracker delegates persistence to
a :class:`~services.intelligence.preference_storage.PreferenceStorage` instance
injected via the keyword-only ``storage`` argument. The default
(``PreferenceTracker()``) wires up :class:`InMemoryPreferenceStorage`, preserving
the original in-process behavior; ``PreferenceTracker(storage=
SqlitePreferenceStorage(db_path))`` swaps in SQLite without changing any
public method signature.

Features:
- Track file moves, renames, and category override corrections
- Pluggable storage backend via the ``PreferenceStorage`` Protocol
- Thread-safe operations using locks (storage backends own their own locking)
- Preference confidence and frequency tracking
- Real-time preference updates
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from threading import RLock
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .preference_storage import PreferenceStorage


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
    last_used: datetime | None = None
    source: str = "user_correction"  # Source of the preference

    def to_dict(self) -> dict[str, Any]:
        """Convert metadata to dictionary."""
        return {
            "created": self.created.isoformat(),
            "updated": self.updated.isoformat(),
            "confidence": self.confidence,
            "frequency": self.frequency,
            "last_used": self.last_used.isoformat() if self.last_used else None,
            "source": self.source,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> PreferenceMetadata:
        """Create metadata from dictionary."""
        return PreferenceMetadata(
            created=datetime.fromisoformat(data["created"]),
            updated=datetime.fromisoformat(data["updated"]),
            confidence=data.get("confidence", 0.5),
            frequency=data.get("frequency", 1),
            last_used=datetime.fromisoformat(data["last_used"]) if data.get("last_used") else None,
            source=data.get("source", "user_correction"),
        )


@dataclass
class Preference:
    """A tracked preference with its metadata."""

    preference_type: PreferenceType
    key: str  # Identifier for the preference (e.g., file pattern, category name)
    value: Any  # The preference value
    metadata: PreferenceMetadata
    context: dict[str, Any] = field(default_factory=dict)  # Additional context

    def to_dict(self) -> dict[str, Any]:
        """Convert preference to dictionary."""
        return {
            "preference_type": self.preference_type.value,
            "key": self.key,
            "value": self.value,
            "metadata": self.metadata.to_dict(),
            "context": self.context,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> Preference:
        """Create preference from dictionary."""
        return Preference(
            preference_type=PreferenceType(data["preference_type"]),
            key=data["key"],
            value=data["value"],
            metadata=PreferenceMetadata.from_dict(data["metadata"]),
            context=data.get("context", {}),
        )


@dataclass
class Correction:
    """A user correction that informs preferences."""

    correction_type: CorrectionType
    source: Path
    destination: Path
    timestamp: datetime
    context: dict[str, Any] = field(default_factory=dict)

    def get_pattern_key(self) -> str:
        """Generate a unique key for this correction pattern."""
        # Create a key based on the correction pattern
        key_parts = [
            self.correction_type.value,
            str(self.source.suffix.lower()) if self.source.suffix else "no_ext",
            str(self.destination.parent.name) if self.destination.parent else "root",
        ]
        return "|".join(key_parts)

    def to_dict(self) -> dict[str, Any]:
        """Convert correction to dictionary."""
        return {
            "correction_type": self.correction_type.value,
            "source": str(self.source),
            "destination": str(self.destination),
            "timestamp": self.timestamp.isoformat(),
            "context": self.context,
        }


class PreferenceTracker:
    """Core preference tracking engine that learns from user corrections.

    Domain orchestrator over a :class:`PreferenceStorage` backend. The tracker
    keeps the correction → preference extraction logic and the best-match
    selection by file extension; the backend handles persistence (in-memory
    or SQLite).
    """

    def __init__(self, *, storage: PreferenceStorage | None = None) -> None:
        """Initialize with an optional storage backend.

        Args:
            storage: Storage backend implementing :class:`PreferenceStorage`.
                Keyword-only for consistency with ``TrashGC.__init__`` (F8.1)
                and to make the dependency-injection intent self-documenting
                at the call site. ``None`` (the default) constructs an
                :class:`InMemoryPreferenceStorage`, preserving the original
                in-process behavior.
        """
        # Local import: PreferenceStorage / InMemoryPreferenceStorage live in
        # ``preference_storage`` which itself imports the dataclasses defined
        # in this module. A top-level import would create a cycle.
        from .preference_storage import InMemoryPreferenceStorage

        self._storage: PreferenceStorage = (
            storage if storage is not None else InMemoryPreferenceStorage()
        )
        # Tracker-level lock guards the read-then-write sequence in
        # ``_extract_preferences_from_correction`` (F3 / Codex P1 on PR
        # #207). The storage backend has its own RLock for individual
        # ops, but its lock is released between ``find_preferences`` and
        # ``save_preference`` — without this tracker-level guard, two
        # concurrent ``track_correction`` calls for the same pattern can
        # both see "no existing preference" and overwrite each other.
        self._tracker_lock = RLock()

    def track_correction(
        self,
        source: Path,
        destination: Path,
        correction_type: CorrectionType,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Track a user correction and update preferences accordingly.

        Args:
            source: Original file path
            destination: New file path after user correction
            correction_type: Type of correction made
            context: Additional context about the correction
        """
        now = datetime.now(UTC)
        correction = Correction(
            correction_type=correction_type,
            source=source,
            destination=destination,
            timestamp=now,
            context=context or {},
        )
        # Tracker-level lock spans save_correction + extract → save_preference.
        # Without it, two concurrent track_correction calls for the same
        # pattern can both observe "no existing preference" and overwrite
        # each other's frequency=1 record. (Codex P1 on PR #207.)
        with self._tracker_lock:
            self._storage.save_correction(correction)
            self._extract_preferences_from_correction(correction)

    def _extract_preferences_from_correction(self, correction: Correction) -> None:
        """Extract / update a preference from ``correction`` via the storage backend.

        Domain logic — derives the preference type and value from the
        correction shape and either creates a fresh preference or updates the
        existing one (frequency + confidence boost capped at 0.95).
        """
        now = datetime.now(UTC)
        pattern_key = correction.get_pattern_key()

        pref_value: Any
        if correction.correction_type == CorrectionType.FILE_MOVE:
            pref_type = PreferenceType.FOLDER_MAPPING
            pref_value = str(correction.destination.parent)
        elif correction.correction_type == CorrectionType.FILE_RENAME:
            pref_type = PreferenceType.NAMING_PATTERN
            pref_value = correction.destination.name
        elif correction.correction_type == CorrectionType.CATEGORY_CHANGE:
            pref_type = PreferenceType.CATEGORY_OVERRIDE
            pref_value = correction.context.get("new_category", "unknown")
        else:
            pref_type = PreferenceType.CUSTOM
            pref_value = {
                "destination": str(correction.destination),
                "source": str(correction.source),
            }

        existing_list = self._storage.find_preferences(pref_type, key=pattern_key)
        existing = existing_list[0] if existing_list else None

        if existing is not None:
            # Update existing preference in place — frequency + capped confidence boost.
            existing.metadata.updated = now
            existing.metadata.frequency += 1
            existing.metadata.last_used = now
            confidence_increase = min(0.05, (1.0 - existing.metadata.confidence) * 0.1)
            existing.metadata.confidence = min(
                0.95, existing.metadata.confidence + confidence_increase
            )
            if existing.value != pref_value:
                existing.value = pref_value
                existing.context["value_changed"] = True
            self._storage.save_preference(existing)
        else:
            metadata = PreferenceMetadata(
                created=now,
                updated=now,
                confidence=0.5,
                frequency=1,
                last_used=now,
                source="user_correction",
            )
            preference = Preference(
                preference_type=pref_type,
                key=pattern_key,
                value=pref_value,
                metadata=metadata,
                context={
                    "correction_type": correction.correction_type.value,
                    "source_extension": correction.source.suffix.lower(),
                },
            )
            self._storage.save_preference(preference)

    def get_preference(
        self,
        file_path: Path,
        preference_type: PreferenceType,
        context: dict[str, Any] | None = None,
    ) -> Preference | None:
        """Get a preference for a given file path and type.

        Args:
            file_path: Path to the file
            preference_type: Type of preference to retrieve
            context: Additional context for matching (currently unused;
                retained for forward compatibility)

        Returns:
            The best matching preference or None
        """
        del context  # reserved for future predicates
        if preference_type == PreferenceType.FOLDER_MAPPING:
            extension = file_path.suffix.lower() if file_path.suffix else "no_ext"
            all_folder = self._storage.find_preferences(PreferenceType.FOLDER_MAPPING)
            matching = [p for p in all_folder if p.context.get("source_extension") == extension]
            if not matching:
                return None
            best = max(matching, key=lambda p: p.metadata.confidence)
            # Persist the last_used update through the storage layer; the
            # in-memory backend would mutate-in-place anyway, but the SQLite
            # backend reconstructs a fresh dataclass on every find_preferences
            # so a bare attribute mutation here would be lost. (Per CodeRabbit
            # / Copilot review on PR #207.)
            best.metadata.last_used = datetime.now(UTC)
            self._storage.save_preference(best)
            return best

        prefix_map = {
            PreferenceType.FOLDER_MAPPING: CorrectionType.FILE_MOVE.value,
            PreferenceType.NAMING_PATTERN: CorrectionType.FILE_RENAME.value,
            PreferenceType.CATEGORY_OVERRIDE: CorrectionType.CATEGORY_CHANGE.value,
            PreferenceType.CUSTOM: CorrectionType.MANUAL_OVERRIDE.value,
        }
        prefix = prefix_map.get(preference_type, preference_type.value)
        pattern_parts = [
            prefix,
            file_path.suffix.lower() if file_path.suffix else "no_ext",
            file_path.parent.name if file_path.parent else "root",
        ]
        pattern_key = "|".join(pattern_parts)

        prefs = self._storage.find_preferences(preference_type, key=pattern_key)
        if not prefs:
            return None
        best = max(prefs, key=lambda p: p.metadata.confidence)
        # Persist last_used through storage so SQLite backend reflects the
        # change (the in-memory backend would mutate-in-place anyway).
        best.metadata.last_used = datetime.now(UTC)
        self._storage.save_preference(best)
        return best

    def get_all_preferences(
        self, preference_type: PreferenceType | None = None
    ) -> list[Preference]:
        """Return preferences, optionally filtered by type."""
        if preference_type is not None:
            return self._storage.find_preferences(preference_type)
        # All types — concat across the enum.
        results: list[Preference] = []
        for pt in PreferenceType:
            results.extend(self._storage.find_preferences(pt))
        return results

    def update_preference_confidence(self, preference: Preference, success: bool) -> None:
        """Adjust ``preference``'s confidence based on application success.

        Delegates to the storage backend, which applies the same delta
        (+0.05 cap 0.98 on success / -0.10 floor 0.10 on failure) for both
        in-memory and SQLite implementations.
        """
        self._storage.update_preference_confidence(preference, success)

    def get_statistics(self) -> dict[str, Any]:
        """Return aggregate statistics about tracked preferences."""
        return self._storage.get_statistics()

    def clear_preferences(self, preference_type: PreferenceType | None = None) -> int:
        """Clear preferences (all or by type). Returns the number cleared."""
        return self._storage.delete_preferences(preference_type)

    def export_data(self) -> dict[str, Any]:
        """Export all preference data for persistence."""
        return self._storage.export_data()

    def import_data(self, data: dict[str, Any]) -> None:
        """Import preference data, replacing current state."""
        self._storage.import_data(data)

    def get_corrections_for_file(self, file_path: Path) -> list[Correction]:
        """Get all corrections related to a specific file."""
        return self._storage.get_corrections_for_file(file_path)

    def get_recent_corrections(self, limit: int = 10) -> list[Correction]:
        """Get the most recent corrections, newest first."""
        return self._storage.get_recent_corrections(limit)


# Convenience functions for common operations


def create_tracker() -> PreferenceTracker:
    """Create a new preference tracker instance."""
    return PreferenceTracker()


def track_file_move(
    tracker: PreferenceTracker,
    source: Path,
    destination: Path,
    context: dict[str, Any] | None = None,
) -> None:
    """Convenience function to track a file move correction.

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
        context=context,
    )


def track_file_rename(
    tracker: PreferenceTracker,
    source: Path,
    destination: Path,
    context: dict[str, Any] | None = None,
) -> None:
    """Convenience function to track a file rename correction.

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
        context=context,
    )


def track_category_change(
    tracker: PreferenceTracker,
    file_path: Path,
    old_category: str,
    new_category: str,
    context: dict[str, Any] | None = None,
) -> None:
    """Convenience function to track a category change correction.

    Args:
        tracker: PreferenceTracker instance
        file_path: Path to the file
        old_category: Original category
        new_category: New category
        context: Additional context
    """
    ctx = context or {}
    ctx.update({"old_category": old_category, "new_category": new_category})

    tracker.track_correction(
        source=file_path,
        destination=file_path,  # Same path for category change
        correction_type=CorrectionType.CATEGORY_CHANGE,
        context=ctx,
    )
