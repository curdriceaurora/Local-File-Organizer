"""
Tests for PreferenceTracker

Tests preference tracking, correction recording, confidence updates,
export/import round-trips, and convenience wrapper functions.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tracker():
    """Create a fresh PreferenceTracker instance."""
    return PreferenceTracker()


# ---------------------------------------------------------------------------
# PreferenceMetadata round-trip
# ---------------------------------------------------------------------------


def test_preference_metadata_to_dict_and_from_dict():
    """Test PreferenceMetadata serialization round-trip."""
    now = datetime.now(UTC)
    meta = PreferenceMetadata(
        created=now,
        updated=now,
        confidence=0.75,
        frequency=3,
        last_used=now,
        source="user_correction",
    )
    data = meta.to_dict()
    restored = PreferenceMetadata.from_dict(data)

    assert restored.confidence == meta.confidence
    assert restored.frequency == meta.frequency
    assert restored.source == meta.source
    assert restored.created == meta.created
    assert restored.updated == meta.updated
    assert restored.last_used == meta.last_used


def test_preference_metadata_from_dict_defaults():
    """Test PreferenceMetadata.from_dict fills defaults for missing keys."""
    now = datetime.now(UTC)
    data = {"created": now.isoformat(), "updated": now.isoformat()}
    meta = PreferenceMetadata.from_dict(data)

    assert meta.confidence == 0.5
    assert meta.frequency == 1
    assert meta.last_used is None
    assert meta.source == "user_correction"


# ---------------------------------------------------------------------------
# Preference round-trip
# ---------------------------------------------------------------------------


def test_preference_to_dict_and_from_dict():
    """Test Preference serialization round-trip."""
    now = datetime.now(UTC)
    meta = PreferenceMetadata(created=now, updated=now)
    pref = Preference(
        preference_type=PreferenceType.FOLDER_MAPPING,
        key="test_key",
        value="/some/folder",
        metadata=meta,
        context={"extra": "data"},
    )
    data = pref.to_dict()
    restored = Preference.from_dict(data)

    assert restored.preference_type == PreferenceType.FOLDER_MAPPING
    assert restored.key == "test_key"
    assert restored.value == "/some/folder"
    assert restored.context == {"extra": "data"}
    assert restored.metadata.confidence == meta.confidence


# ---------------------------------------------------------------------------
# Correction.get_pattern_key
# ---------------------------------------------------------------------------


def test_correction_get_pattern_key_with_extension():
    """Test pattern key generation for a file with an extension."""
    correction = Correction(
        correction_type=CorrectionType.FILE_MOVE,
        source=Path("/docs/report.pdf"),
        destination=Path("/archive/2024/report.pdf"),
        timestamp=datetime.now(UTC),
    )
    key = correction.get_pattern_key()

    assert key == "file_move|.pdf|2024"


def test_correction_get_pattern_key_no_extension():
    """Test pattern key generation for a file without an extension."""
    correction = Correction(
        correction_type=CorrectionType.FILE_RENAME,
        source=Path("/tmp/Makefile"),
        destination=Path("/build/Makefile"),
        timestamp=datetime.now(UTC),
    )
    key = correction.get_pattern_key()

    assert key == "file_rename|no_ext|build"


# ---------------------------------------------------------------------------
# PreferenceTracker init
# ---------------------------------------------------------------------------


def test_tracker_init_empty(tracker):
    """Test that a new tracker starts with empty state."""
    assert tracker.get_all_preferences() == []
    assert tracker.get_recent_corrections() == []
    stats = tracker.get_statistics()
    assert stats["total_corrections"] == 0
    assert stats["total_preferences"] == 0


# ---------------------------------------------------------------------------
# track_correction – FILE_MOVE
# ---------------------------------------------------------------------------


def test_track_correction_file_move(tracker):
    """Test tracking a FILE_MOVE correction creates a FOLDER_MAPPING preference."""
    tracker.track_correction(
        source=Path("/downloads/photo.jpg"),
        destination=Path("/pictures/vacation/photo.jpg"),
        correction_type=CorrectionType.FILE_MOVE,
    )

    prefs = tracker.get_all_preferences(PreferenceType.FOLDER_MAPPING)
    assert len(prefs) == 1
    assert prefs[0].value == str(Path("/pictures/vacation"))
    assert prefs[0].metadata.confidence == 0.5
    assert prefs[0].metadata.frequency == 1


# ---------------------------------------------------------------------------
# track_correction – FILE_RENAME
# ---------------------------------------------------------------------------


def test_track_correction_file_rename(tracker):
    """Test tracking a FILE_RENAME correction creates a NAMING_PATTERN preference."""
    tracker.track_correction(
        source=Path("/docs/old_name.txt"),
        destination=Path("/docs/new_name.txt"),
        correction_type=CorrectionType.FILE_RENAME,
    )

    prefs = tracker.get_all_preferences(PreferenceType.NAMING_PATTERN)
    assert len(prefs) == 1
    assert prefs[0].value == "new_name.txt"


# ---------------------------------------------------------------------------
# track_correction – CATEGORY_CHANGE
# ---------------------------------------------------------------------------


def test_track_correction_category_change(tracker):
    """Test tracking a CATEGORY_CHANGE correction creates a CATEGORY_OVERRIDE preference."""
    tracker.track_correction(
        source=Path("/files/readme.md"),
        destination=Path("/files/readme.md"),
        correction_type=CorrectionType.CATEGORY_CHANGE,
        context={"old_category": "misc", "new_category": "documentation"},
    )

    prefs = tracker.get_all_preferences(PreferenceType.CATEGORY_OVERRIDE)
    assert len(prefs) == 1
    assert prefs[0].value == "documentation"


# ---------------------------------------------------------------------------
# track_correction – default (FOLDER_CREATION, MANUAL_OVERRIDE)
# ---------------------------------------------------------------------------


def test_track_correction_default_type(tracker):
    """Test tracking other correction types creates a CUSTOM preference."""
    tracker.track_correction(
        source=Path("/a/file.log"),
        destination=Path("/b/file.log"),
        correction_type=CorrectionType.FOLDER_CREATION,
    )

    prefs = tracker.get_all_preferences(PreferenceType.CUSTOM)
    assert len(prefs) == 1
    assert isinstance(prefs[0].value, dict)
    assert "destination" in prefs[0].value
    assert "source" in prefs[0].value


# ---------------------------------------------------------------------------
# _extract_preferences_from_correction – confidence update on repeat
# ---------------------------------------------------------------------------


def test_repeated_correction_increases_confidence(tracker):
    """Test that repeating the same correction increases confidence."""
    for _ in range(5):
        tracker.track_correction(
            source=Path("/downloads/report.pdf"),
            destination=Path("/archive/reports/report.pdf"),
            correction_type=CorrectionType.FILE_MOVE,
        )

    prefs = tracker.get_all_preferences(PreferenceType.FOLDER_MAPPING)
    assert len(prefs) == 1
    assert prefs[0].metadata.frequency == 5
    assert prefs[0].metadata.confidence > 0.5
    # Confidence should never exceed cap of 0.95 from _extract_preferences_from_correction
    assert prefs[0].metadata.confidence <= 0.95


# ---------------------------------------------------------------------------
# get_preference – FOLDER_MAPPING lookup
# ---------------------------------------------------------------------------


def test_get_preference_folder_mapping(tracker):
    """Test getting a FOLDER_MAPPING preference by extension match."""
    tracker.track_correction(
        source=Path("/downloads/image.png"),
        destination=Path("/pictures/image.png"),
        correction_type=CorrectionType.FILE_MOVE,
    )

    pref = tracker.get_preference(Path("/other/photo.png"), PreferenceType.FOLDER_MAPPING)
    assert pref is not None
    assert pref.value == str(Path("/pictures"))


def test_get_preference_folder_mapping_no_match(tracker):
    """Test get_preference returns None when no matching extension exists."""
    tracker.track_correction(
        source=Path("/downloads/image.png"),
        destination=Path("/pictures/image.png"),
        correction_type=CorrectionType.FILE_MOVE,
    )

    pref = tracker.get_preference(Path("/docs/readme.txt"), PreferenceType.FOLDER_MAPPING)
    assert pref is None


# ---------------------------------------------------------------------------
# get_all_preferences – with and without type filter
# ---------------------------------------------------------------------------


def test_get_all_preferences_unfiltered(tracker):
    """Test getting all preferences without filter."""
    tracker.track_correction(
        source=Path("/a/f.txt"),
        destination=Path("/b/f.txt"),
        correction_type=CorrectionType.FILE_MOVE,
    )
    tracker.track_correction(
        source=Path("/a/g.txt"),
        destination=Path("/a/renamed.txt"),
        correction_type=CorrectionType.FILE_RENAME,
    )

    all_prefs = tracker.get_all_preferences()
    assert len(all_prefs) == 2


def test_get_all_preferences_filtered(tracker):
    """Test getting preferences filtered by type."""
    tracker.track_correction(
        source=Path("/a/f.txt"),
        destination=Path("/b/f.txt"),
        correction_type=CorrectionType.FILE_MOVE,
    )
    tracker.track_correction(
        source=Path("/a/g.txt"),
        destination=Path("/a/renamed.txt"),
        correction_type=CorrectionType.FILE_RENAME,
    )

    folder_prefs = tracker.get_all_preferences(PreferenceType.FOLDER_MAPPING)
    assert len(folder_prefs) == 1
    assert folder_prefs[0].preference_type == PreferenceType.FOLDER_MAPPING


# ---------------------------------------------------------------------------
# update_preference_confidence
# ---------------------------------------------------------------------------


def test_update_preference_confidence_success(tracker):
    """Test that success increases confidence capped at 0.98."""
    tracker.track_correction(
        source=Path("/a/f.pdf"),
        destination=Path("/b/f.pdf"),
        correction_type=CorrectionType.FILE_MOVE,
    )
    pref = tracker.get_all_preferences()[0]
    original = pref.metadata.confidence

    tracker.update_preference_confidence(pref, success=True)

    assert pref.metadata.confidence > original
    assert pref.metadata.confidence <= 0.98

    stats = tracker.get_statistics()
    assert stats["successful_applications"] == 1


def test_update_preference_confidence_failure(tracker):
    """Test that failure decreases confidence with floor at 0.1."""
    tracker.track_correction(
        source=Path("/a/f.pdf"),
        destination=Path("/b/f.pdf"),
        correction_type=CorrectionType.FILE_MOVE,
    )
    pref = tracker.get_all_preferences()[0]
    original = pref.metadata.confidence

    tracker.update_preference_confidence(pref, success=False)

    assert pref.metadata.confidence < original
    assert pref.metadata.confidence >= 0.1

    stats = tracker.get_statistics()
    assert stats["failed_applications"] == 1


def test_update_preference_confidence_cap_and_floor(tracker):
    """Test that confidence stays within [0.1, 0.98] boundaries."""
    tracker.track_correction(
        source=Path("/a/f.pdf"),
        destination=Path("/b/f.pdf"),
        correction_type=CorrectionType.FILE_MOVE,
    )
    pref = tracker.get_all_preferences()[0]

    # Drive confidence up
    for _ in range(50):
        tracker.update_preference_confidence(pref, success=True)
    assert pref.metadata.confidence <= 0.98

    # Drive confidence down
    for _ in range(50):
        tracker.update_preference_confidence(pref, success=False)
    assert pref.metadata.confidence >= 0.1


# ---------------------------------------------------------------------------
# get_statistics
# ---------------------------------------------------------------------------


def test_get_statistics_empty(tracker):
    """Test statistics on an empty tracker."""
    stats = tracker.get_statistics()
    assert stats["total_corrections"] == 0
    assert stats["total_preferences"] == 0
    assert stats["average_confidence"] == 0.0


def test_get_statistics_populated(tracker):
    """Test statistics after tracking corrections."""
    tracker.track_correction(
        source=Path("/a/f.txt"),
        destination=Path("/b/f.txt"),
        correction_type=CorrectionType.FILE_MOVE,
    )
    tracker.track_correction(
        source=Path("/a/g.pdf"),
        destination=Path("/c/g.pdf"),
        correction_type=CorrectionType.FILE_MOVE,
    )

    stats = tracker.get_statistics()
    assert stats["total_corrections"] == 2
    assert stats["total_preferences"] == 2
    assert stats["total_correction_history"] == 2
    assert stats["average_confidence"] > 0


# ---------------------------------------------------------------------------
# clear_preferences
# ---------------------------------------------------------------------------


def test_clear_preferences_all(tracker):
    """Test clearing all preferences."""
    tracker.track_correction(
        source=Path("/a/f.txt"),
        destination=Path("/b/f.txt"),
        correction_type=CorrectionType.FILE_MOVE,
    )
    tracker.track_correction(
        source=Path("/a/g.txt"),
        destination=Path("/a/renamed.txt"),
        correction_type=CorrectionType.FILE_RENAME,
    )

    cleared = tracker.clear_preferences()
    assert cleared == 2
    assert tracker.get_all_preferences() == []


def test_clear_preferences_by_type(tracker):
    """Test clearing preferences filtered by type."""
    tracker.track_correction(
        source=Path("/a/f.txt"),
        destination=Path("/b/f.txt"),
        correction_type=CorrectionType.FILE_MOVE,
    )
    tracker.track_correction(
        source=Path("/a/g.txt"),
        destination=Path("/a/renamed.txt"),
        correction_type=CorrectionType.FILE_RENAME,
    )

    cleared = tracker.clear_preferences(PreferenceType.FOLDER_MAPPING)
    assert cleared == 1

    remaining = tracker.get_all_preferences()
    assert len(remaining) == 1
    assert remaining[0].preference_type == PreferenceType.NAMING_PATTERN


# ---------------------------------------------------------------------------
# export_data / import_data round-trip
# ---------------------------------------------------------------------------


def test_export_import_round_trip(tracker):
    """Test that export then import restores the same state."""
    tracker.track_correction(
        source=Path("/a/f.txt"),
        destination=Path("/b/f.txt"),
        correction_type=CorrectionType.FILE_MOVE,
    )
    tracker.track_correction(
        source=Path("/a/g.pdf"),
        destination=Path("/c/g.pdf"),
        correction_type=CorrectionType.FILE_MOVE,
    )

    exported = tracker.export_data()
    assert "preferences" in exported
    assert "corrections" in exported
    assert "statistics" in exported
    assert "exported_at" in exported

    # Import into a fresh tracker
    new_tracker = PreferenceTracker()
    new_tracker.import_data(exported)

    assert len(new_tracker.get_all_preferences()) == 2
    assert len(new_tracker.get_recent_corrections()) == 2


# ---------------------------------------------------------------------------
# get_corrections_for_file
# ---------------------------------------------------------------------------


def test_get_corrections_for_file_source_match(tracker):
    """Test getting corrections that match by source path."""
    src = Path("/downloads/file.txt")
    tracker.track_correction(
        source=src,
        destination=Path("/docs/file.txt"),
        correction_type=CorrectionType.FILE_MOVE,
    )

    corrections = tracker.get_corrections_for_file(src)
    assert len(corrections) == 1
    assert corrections[0].source == src


def test_get_corrections_for_file_destination_match(tracker):
    """Test getting corrections that match by destination path."""
    dst = Path("/archive/report.pdf")
    tracker.track_correction(
        source=Path("/docs/report.pdf"),
        destination=dst,
        correction_type=CorrectionType.FILE_MOVE,
    )

    corrections = tracker.get_corrections_for_file(dst)
    assert len(corrections) == 1
    assert corrections[0].destination == dst


def test_get_corrections_for_file_no_match(tracker):
    """Test getting corrections for a file with no related corrections."""
    tracker.track_correction(
        source=Path("/a/x.txt"),
        destination=Path("/b/x.txt"),
        correction_type=CorrectionType.FILE_MOVE,
    )

    corrections = tracker.get_corrections_for_file(Path("/unrelated/z.txt"))
    assert corrections == []


# ---------------------------------------------------------------------------
# get_recent_corrections
# ---------------------------------------------------------------------------


def test_get_recent_corrections_ordering_and_limit(tracker):
    """Test that recent corrections are ordered newest-first and respect limit."""
    for i in range(5):
        tracker.track_correction(
            source=Path(f"/a/file{i}.txt"),
            destination=Path(f"/b/file{i}.txt"),
            correction_type=CorrectionType.FILE_MOVE,
        )

    recent = tracker.get_recent_corrections(limit=3)
    assert len(recent) == 3

    # Newest first: timestamps should be non-increasing
    for j in range(len(recent) - 1):
        assert recent[j].timestamp >= recent[j + 1].timestamp


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------


def test_create_tracker():
    """Test create_tracker returns a valid PreferenceTracker."""
    t = create_tracker()
    assert isinstance(t, PreferenceTracker)
    assert t.get_all_preferences() == []


def test_track_file_move_convenience():
    """Test the track_file_move convenience function."""
    t = create_tracker()
    track_file_move(t, Path("/a/f.jpg"), Path("/b/f.jpg"))

    prefs = t.get_all_preferences(PreferenceType.FOLDER_MAPPING)
    assert len(prefs) == 1


def test_track_file_rename_convenience():
    """Test the track_file_rename convenience function."""
    t = create_tracker()
    track_file_rename(t, Path("/a/old.txt"), Path("/a/new.txt"))

    prefs = t.get_all_preferences(PreferenceType.NAMING_PATTERN)
    assert len(prefs) == 1


def test_track_category_change_convenience():
    """Test the track_category_change convenience function."""
    t = create_tracker()
    track_category_change(t, Path("/f/readme.md"), "misc", "docs")

    prefs = t.get_all_preferences(PreferenceType.CATEGORY_OVERRIDE)
    assert len(prefs) == 1
    assert prefs[0].value == "docs"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
