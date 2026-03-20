"""Tests for FolderPreferenceLearner.

Comprehensive tests covering folder tracking, preferred folder lookup,
confidence scoring, organization analysis, folder suggestions, stats,
old preference clearing, and persistence.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from file_organizer.services.intelligence.folder_learner import FolderPreferenceLearner

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_storage():
    """Create a temporary storage directory."""
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def learner(temp_storage):
    """Create a FolderPreferenceLearner with temp storage."""
    storage_file = temp_storage / "folder_prefs.json"
    return FolderPreferenceLearner(storage_path=storage_file)


@pytest.fixture
def populated_learner(learner, temp_storage):
    """Create a learner with pre-populated data."""
    docs_folder = temp_storage / "documents"
    docs_folder.mkdir()
    photos_folder = temp_storage / "photos"
    photos_folder.mkdir()

    # Track several choices
    for _ in range(5):
        learner.track_folder_choice(".pdf", docs_folder)
    for _ in range(3):
        learner.track_folder_choice(".jpg", photos_folder)
    learner.track_folder_choice(".pdf", photos_folder)  # Minority choice

    return learner


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestInit:
    """Tests for FolderPreferenceLearner initialization."""

    def test_default_storage(self, temp_storage):
        """Test initialization with explicit storage path."""
        storage_file = temp_storage / "prefs.json"
        learner = FolderPreferenceLearner(storage_path=storage_file)

        assert learner.storage_path == storage_file
        assert learner.total_choices == 0

    def test_creates_parent_directory(self, temp_storage):
        """Test that parent directory is created on init."""
        storage_file = temp_storage / "subdir" / "prefs.json"
        FolderPreferenceLearner(storage_path=storage_file)

        assert storage_file.parent.exists()

    def test_loads_existing_preferences(self, temp_storage):
        """Test loading preferences from existing file."""
        storage_file = temp_storage / "prefs.json"

        # Write some data first
        data = {
            "type_folder_map": {".pdf": {"/docs": 5}},
            "pattern_folder_map": {},
            "folder_metadata": {
                "/docs": {
                    "created": datetime.now(UTC).isoformat(),
                    "file_types": [".pdf"],
                    "last_used": datetime.now(UTC).isoformat(),
                    "usage_count": 5,
                }
            },
            "total_choices": 5,
        }
        with open(storage_file, "w") as f:
            json.dump(data, f)

        learner = FolderPreferenceLearner(storage_path=storage_file)

        assert learner.total_choices == 5
        assert ".pdf" in learner.type_folder_map

    def test_handles_corrupted_file(self, temp_storage):
        """Test graceful handling of corrupted storage file."""
        storage_file = temp_storage / "prefs.json"

        with open(storage_file, "w") as f:
            f.write("{corrupted json")

        # Should not raise, just start with empty data
        learner = FolderPreferenceLearner(storage_path=storage_file)
        assert learner.total_choices == 0


# ---------------------------------------------------------------------------
# track_folder_choice
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestTrackFolderChoice:
    """Tests for track_folder_choice method."""

    def test_basic_tracking(self, learner, temp_storage):
        """Test basic folder choice tracking."""
        folder = temp_storage / "documents"
        folder.mkdir()

        learner.track_folder_choice(".pdf", folder)

        assert ".pdf" in learner.type_folder_map
        folder_str = str(folder.resolve())
        assert folder_str in learner.type_folder_map[".pdf"]
        assert learner.type_folder_map[".pdf"][folder_str] == 1
        assert learner.total_choices == 1

    def test_multiple_tracking(self, learner, temp_storage):
        """Test tracking multiple choices increments counts."""
        folder = temp_storage / "docs"
        folder.mkdir()

        learner.track_folder_choice(".pdf", folder)
        learner.track_folder_choice(".pdf", folder)
        learner.track_folder_choice(".pdf", folder)

        folder_str = str(folder.resolve())
        assert learner.type_folder_map[".pdf"][folder_str] == 3
        assert learner.total_choices == 3

    def test_case_normalization(self, learner, temp_storage):
        """Test that file types are lowercased."""
        folder = temp_storage / "docs"
        folder.mkdir()

        learner.track_folder_choice(".PDF", folder)
        learner.track_folder_choice(".pdf", folder)

        folder_str = str(folder.resolve())
        assert ".pdf" in learner.type_folder_map
        assert learner.type_folder_map[".pdf"][folder_str] == 2

    def test_pattern_tracking_with_context(self, learner, temp_storage):
        """Test pattern-based tracking with context."""
        folder = temp_storage / "photos"
        folder.mkdir()

        context = {"pattern": "vacation"}
        learner.track_folder_choice(".jpg", folder, context)

        assert "vacation" in learner.pattern_folder_map
        folder_str = str(folder.resolve())
        assert folder_str in learner.pattern_folder_map["vacation"]

    def test_folder_metadata_creation(self, learner, temp_storage):
        """Test that folder metadata is created on first tracking."""
        folder = temp_storage / "docs"
        folder.mkdir()

        learner.track_folder_choice(".pdf", folder)

        folder_str = str(folder.resolve())
        assert folder_str in learner.folder_metadata
        meta = learner.folder_metadata[folder_str]
        assert "created" in meta
        assert "last_used" in meta
        assert meta["usage_count"] == 1
        assert ".pdf" in meta["file_types"]

    def test_folder_metadata_update(self, learner, temp_storage):
        """Test that folder metadata is updated on subsequent tracking."""
        folder = temp_storage / "docs"
        folder.mkdir()

        learner.track_folder_choice(".pdf", folder)
        learner.track_folder_choice(".txt", folder)

        folder_str = str(folder.resolve())
        meta = learner.folder_metadata[folder_str]
        assert meta["usage_count"] == 2
        assert ".pdf" in meta["file_types"]
        assert ".txt" in meta["file_types"]

    def test_persistence(self, learner, temp_storage):
        """Test that tracking persists to disk."""
        folder = temp_storage / "docs"
        folder.mkdir()

        learner.track_folder_choice(".pdf", folder)

        # Verify file was written
        assert learner.storage_path.exists()

        with open(learner.storage_path) as f:
            data = json.load(f)

        assert ".pdf" in data["type_folder_map"]


# ---------------------------------------------------------------------------
# get_preferred_folder
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetPreferredFolder:
    """Tests for get_preferred_folder method."""

    def test_no_data(self, learner):
        """Test with no tracked data."""
        result = learner.get_preferred_folder(".pdf")
        assert result is None

    def test_unknown_type(self, populated_learner):
        """Test with unknown file type."""
        result = populated_learner.get_preferred_folder(".xyz")
        assert result is None

    def test_confident_preference(self, populated_learner, temp_storage):
        """Test retrieval of confident preference."""
        # .pdf has 5/6 choices to documents => ~83% confidence
        result = populated_learner.get_preferred_folder(".pdf", confidence_threshold=0.6)

        assert result is not None
        docs_folder = temp_storage / "documents"
        assert result == docs_folder.resolve()

    def test_below_threshold(self, learner, temp_storage):
        """Test preference below confidence threshold."""
        folder_a = temp_storage / "folder_a"
        folder_a.mkdir()
        folder_b = temp_storage / "folder_b"
        folder_b.mkdir()

        learner.track_folder_choice(".txt", folder_a)
        learner.track_folder_choice(".txt", folder_b)

        # 50/50 split, below 0.6 threshold
        result = learner.get_preferred_folder(".txt", confidence_threshold=0.6)
        assert result is None

    def test_high_threshold(self, populated_learner):
        """Test with very high threshold."""
        # .jpg has 3/3 choices to photos => 100% confidence
        result = populated_learner.get_preferred_folder(".jpg", confidence_threshold=0.99)

        assert result is not None


# ---------------------------------------------------------------------------
# get_folder_confidence
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetFolderConfidence:
    """Tests for get_folder_confidence method."""

    def test_no_data(self, learner, temp_storage):
        """Test confidence with no tracked data."""
        folder = temp_storage / "docs"
        folder.mkdir()

        confidence = learner.get_folder_confidence(".pdf", folder)
        assert confidence == 0.0

    def test_known_mapping(self, populated_learner, temp_storage):
        """Test confidence for known mapping."""
        docs_folder = temp_storage / "documents"

        confidence = populated_learner.get_folder_confidence(".pdf", docs_folder)

        # 5 out of 6 total .pdf choices
        assert confidence == pytest.approx(5 / 6, abs=0.01)

    def test_unknown_folder(self, populated_learner, temp_storage):
        """Test confidence for unknown folder."""
        unknown = temp_storage / "unknown"
        unknown.mkdir()

        confidence = populated_learner.get_folder_confidence(".pdf", unknown)
        assert confidence == 0.0


# ---------------------------------------------------------------------------
# analyze_organization_patterns
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAnalyzeOrganizationPatterns:
    """Tests for analyze_organization_patterns method."""

    def test_empty_data(self, learner):
        """Test analysis with no data."""
        analysis = learner.analyze_organization_patterns()

        assert analysis["total_choices"] == 0
        assert analysis["file_types_tracked"] == 0
        assert analysis["folders_used"] == 0
        assert analysis["top_folders"] == []
        assert analysis["type_preferences"] == {}

    def test_populated_data(self, populated_learner):
        """Test analysis with populated data."""
        analysis = populated_learner.analyze_organization_patterns()

        assert analysis["total_choices"] == 9  # 5 + 3 + 1
        assert analysis["file_types_tracked"] == 2  # .pdf and .jpg
        assert analysis["folders_used"] == 2
        assert len(analysis["top_folders"]) == 2  # 2 folders used; cap is 10 but only 2 qualify

    def test_strong_type_preferences(self, populated_learner):
        """Test detection of strong type preferences."""
        analysis = populated_learner.analyze_organization_patterns()

        # .jpg has 100% confidence (3/3 to photos), should appear as strong preference
        assert ".jpg" in analysis["type_preferences"]
        assert analysis["type_preferences"][".jpg"]["confidence"] > 0.7


# ---------------------------------------------------------------------------
# suggest_folder_structure
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSuggestFolderStructure:
    """Tests for suggest_folder_structure method."""

    def test_no_data(self, learner):
        """Test suggestion with no learned data."""
        result = learner.suggest_folder_structure({"type": ".pdf"})
        assert result is None

    def test_type_based_suggestion(self, populated_learner, temp_storage):
        """Test type-based folder suggestion."""
        result = populated_learner.suggest_folder_structure({"type": ".pdf"}, min_confidence=0.5)

        assert result is not None
        docs_folder = temp_storage / "documents"
        assert result == docs_folder.resolve()

    def test_pattern_based_suggestion(self, learner, temp_storage):
        """Test pattern-based folder suggestion."""
        folder = temp_storage / "vacations"
        folder.mkdir()

        # Track with pattern context
        for _ in range(5):
            learner.track_folder_choice(".jpg", folder, {"pattern": "vacation"})

        # Suggest for a file with matching pattern in name
        result = learner.suggest_folder_structure(
            {"type": ".unknown", "name": "vacation_photo.jpg"}, min_confidence=0.5
        )

        assert result is not None

    def test_no_name_fallback(self, learner):
        """Test suggestion when name is not in file_info."""
        result = learner.suggest_folder_structure({"type": ".xyz"})
        assert result is None

    def test_low_confidence_pattern(self, learner, temp_storage):
        """Test that low-confidence pattern suggestions are rejected."""
        folder_a = temp_storage / "a"
        folder_a.mkdir()
        folder_b = temp_storage / "b"
        folder_b.mkdir()

        learner.track_folder_choice(".jpg", folder_a, {"pattern": "test"})
        learner.track_folder_choice(".jpg", folder_b, {"pattern": "test"})

        result = learner.suggest_folder_structure(
            {"type": ".unknown", "name": "test_file.jpg"}, min_confidence=0.8
        )

        assert result is None


# ---------------------------------------------------------------------------
# get_folder_stats
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetFolderStats:
    """Tests for get_folder_stats method."""

    def test_unknown_folder(self, learner, temp_storage):
        """Test stats for unknown folder."""
        folder = temp_storage / "unknown"
        folder.mkdir()

        stats = learner.get_folder_stats(folder)

        assert stats["exists"] is False
        assert stats["usage_count"] == 0
        assert stats["file_types"] == []

    def test_known_folder(self, populated_learner, temp_storage):
        """Test stats for known folder."""
        docs_folder = temp_storage / "documents"

        stats = populated_learner.get_folder_stats(docs_folder)

        assert stats["exists"] is True
        assert stats["usage_count"] == 5  # 5 .pdf choices
        assert ".pdf" in stats["file_types"]
        assert "created" in stats
        assert "last_used" in stats


# ---------------------------------------------------------------------------
# clear_old_preferences
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestClearOldPreferences:
    """Tests for clear_old_preferences method."""

    def test_clear_no_data(self, learner):
        """Test clearing with no data."""
        cleared = learner.clear_old_preferences(days=30)
        assert cleared == 0

    def test_clear_old_entries(self, learner, temp_storage):
        """Test clearing entries older than threshold."""
        folder = temp_storage / "old_folder"
        folder.mkdir()
        folder_str = str(folder.resolve())

        # Manually set old metadata
        old_time = (datetime.now(UTC) - timedelta(days=120)).isoformat()
        learner.type_folder_map[".pdf"][folder_str] = 3
        learner.folder_metadata[folder_str] = {
            "created": old_time,
            "file_types": {".pdf"},
            "last_used": old_time,
            "usage_count": 3,
        }
        learner.total_choices = 3

        cleared = learner.clear_old_preferences(days=90)

        assert cleared == 1
        assert folder_str not in learner.folder_metadata
        assert folder_str not in learner.type_folder_map[".pdf"]

    def test_keep_recent_entries(self, populated_learner):
        """Test that recent entries are kept."""

        cleared = populated_learner.clear_old_preferences(days=1)

        # All entries are recent, nothing should be cleared
        assert cleared == 0


# ---------------------------------------------------------------------------
# Persistence (_save_preferences / _load_preferences)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPersistence:
    """Tests for save/load persistence."""

    def test_save_and_reload(self, temp_storage):
        """Test that data survives save/reload cycle."""
        storage_file = temp_storage / "prefs.json"
        folder = temp_storage / "docs"
        folder.mkdir()

        # Create learner and track choices
        learner1 = FolderPreferenceLearner(storage_path=storage_file)
        learner1.track_folder_choice(".pdf", folder)
        learner1.track_folder_choice(".pdf", folder)

        # Create new learner from same storage
        learner2 = FolderPreferenceLearner(storage_path=storage_file)

        assert learner2.total_choices == 2
        folder_str = str(folder.resolve())
        assert learner2.type_folder_map[".pdf"][folder_str] == 2

    def test_save_converts_sets_to_lists(self, learner, temp_storage):
        """Test that sets are converted to lists in JSON."""
        folder = temp_storage / "docs"
        folder.mkdir()

        learner.track_folder_choice(".pdf", folder)

        # Read raw JSON
        with open(learner.storage_path) as f:
            data = json.load(f)

        # file_types should be a list (not a set)
        folder_str = str(folder.resolve())
        assert isinstance(data["folder_metadata"][folder_str]["file_types"], list)

    def test_load_converts_lists_to_sets(self, temp_storage):
        """Test that file_types lists are converted back to sets on load."""
        storage_file = temp_storage / "prefs.json"
        folder = temp_storage / "docs"
        folder.mkdir()

        learner1 = FolderPreferenceLearner(storage_path=storage_file)
        learner1.track_folder_choice(".pdf", folder)

        # Reload
        learner2 = FolderPreferenceLearner(storage_path=storage_file)

        folder_str = str(folder.resolve())
        assert isinstance(learner2.folder_metadata[folder_str]["file_types"], set)

    def test_nonexistent_storage_file(self, temp_storage):
        """Test initialization with nonexistent storage file."""
        storage_file = temp_storage / "nonexistent.json"

        learner = FolderPreferenceLearner(storage_path=storage_file)

        assert learner.total_choices == 0
        assert len(learner.type_folder_map) == 0
