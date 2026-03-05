"""Coverage tests for PreferenceStore — targets uncovered branches."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from file_organizer.services.intelligence.preference_store import (
    DirectoryPreference,
    PreferenceStore,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# DirectoryPreference
# ---------------------------------------------------------------------------


class TestDirectoryPreferenceFromDict:
    """Test DirectoryPreference.from_dict edge cases."""

    def test_from_dict_missing_fields_uses_defaults(self):
        """from_dict with empty dict should fill defaults."""
        pref = DirectoryPreference.from_dict({})
        assert pref.folder_mappings == {}
        assert pref.naming_patterns == {}
        assert pref.category_overrides == {}
        assert pref.confidence == 0.0
        assert pref.correction_count == 0
        # created/updated should be set to now-ish strings
        assert "T" in pref.created

    def test_from_dict_roundtrip(self):
        data = {
            "folder_mappings": {"a": "b"},
            "naming_patterns": {"p": "q"},
            "category_overrides": {"x": "y"},
            "created": "2025-01-01T00:00:00Z",
            "updated": "2025-06-01T00:00:00Z",
            "confidence": 0.9,
            "correction_count": 5,
        }
        pref = DirectoryPreference.from_dict(data)
        d = pref.to_dict()
        assert d["folder_mappings"] == {"a": "b"}
        assert d["confidence"] == 0.9
        assert d["correction_count"] == 5


# ---------------------------------------------------------------------------
# PreferenceStore – schema validation edge cases
# ---------------------------------------------------------------------------


class TestValidateSchema:
    def _make_store(self, tmp_path: Path) -> PreferenceStore:
        return PreferenceStore(storage_path=tmp_path / "prefs")

    def test_missing_required_field(self, tmp_path):
        store = self._make_store(tmp_path)
        data = {"version": "1.0", "user_id": "x"}  # missing two fields
        assert store._validate_schema(data) is False

    def test_invalid_version(self, tmp_path):
        store = self._make_store(tmp_path)
        data = {
            "version": "99.0",
            "user_id": "x",
            "global_preferences": {
                "folder_mappings": {},
                "naming_patterns": {},
                "category_overrides": {},
            },
            "directory_preferences": {},
        }
        assert store._validate_schema(data) is False

    def test_missing_global_pref_field(self, tmp_path):
        store = self._make_store(tmp_path)
        data = {
            "version": "1.0",
            "user_id": "x",
            "global_preferences": {"folder_mappings": {}},
            "directory_preferences": {},
        }
        assert store._validate_schema(data) is False

    def test_dir_prefs_not_dict(self, tmp_path):
        store = self._make_store(tmp_path)
        data = {
            "version": "1.0",
            "user_id": "x",
            "global_preferences": {
                "folder_mappings": {},
                "naming_patterns": {},
                "category_overrides": {},
            },
            "directory_preferences": "not a dict",
        }
        assert store._validate_schema(data) is False

    def test_dir_pref_entry_not_dict(self, tmp_path):
        store = self._make_store(tmp_path)
        data = {
            "version": "1.0",
            "user_id": "x",
            "global_preferences": {
                "folder_mappings": {},
                "naming_patterns": {},
                "category_overrides": {},
            },
            "directory_preferences": {"/some/path": "bad"},
        }
        assert store._validate_schema(data) is False

    def test_dir_pref_missing_fields(self, tmp_path):
        store = self._make_store(tmp_path)
        data = {
            "version": "1.0",
            "user_id": "x",
            "global_preferences": {
                "folder_mappings": {},
                "naming_patterns": {},
                "category_overrides": {},
            },
            "directory_preferences": {"/some/path": {"folder_mappings": {}, "naming_patterns": {}}},
        }
        assert store._validate_schema(data) is False

    def test_validate_raises_internally(self, tmp_path):
        store = self._make_store(tmp_path)
        # None causes TypeError on iteration
        assert store._validate_schema(None) is False


# ---------------------------------------------------------------------------
# load_preferences branches
# ---------------------------------------------------------------------------


class TestLoadPreferences:
    def _make_store(self, tmp_path: Path) -> PreferenceStore:
        return PreferenceStore(storage_path=tmp_path / "prefs")

    def test_load_corrupted_json_falls_back_to_backup(self, tmp_path):
        store = self._make_store(tmp_path)
        # Write corrupted primary
        store.preference_file.write_text("{bad json", encoding="utf-8")
        # No backup exists => defaults
        result = store.load_preferences()
        assert result is False
        assert store._loaded is True

    def test_load_invalid_schema_falls_back_to_backup(self, tmp_path):
        store = self._make_store(tmp_path)
        store.preference_file.write_text(json.dumps({"bad": "schema"}), encoding="utf-8")
        result = store.load_preferences()
        assert result is False
        assert store._loaded is True

    def test_load_with_valid_backup_after_invalid_primary(self, tmp_path):
        store = self._make_store(tmp_path)
        valid_data = store._create_empty_preferences()
        # Write invalid primary
        store.preference_file.write_text(json.dumps({"bad": "schema"}), encoding="utf-8")
        # Write valid backup
        store.backup_file.write_text(json.dumps(valid_data), encoding="utf-8")
        result = store.load_preferences()
        assert result is True

    def test_load_no_primary_valid_backup(self, tmp_path):
        store = self._make_store(tmp_path)
        valid_data = store._create_empty_preferences()
        store.backup_file.write_text(json.dumps(valid_data), encoding="utf-8")
        result = store.load_preferences()
        assert result is True

    def test_load_generic_exception(self, tmp_path):
        store = self._make_store(tmp_path)
        valid_data = store._create_empty_preferences()
        store.preference_file.write_text(json.dumps(valid_data), encoding="utf-8")
        with patch("builtins.open", side_effect=OSError("disk fail")):
            result = store.load_preferences()
        assert result is False
        assert store._loaded is True


# ---------------------------------------------------------------------------
# _try_load_backup branches
# ---------------------------------------------------------------------------


class TestTryLoadBackup:
    def _make_store(self, tmp_path: Path) -> PreferenceStore:
        return PreferenceStore(storage_path=tmp_path / "prefs")

    def test_backup_not_exists(self, tmp_path):
        store = self._make_store(tmp_path)
        result = store._try_load_backup()
        assert result is False
        assert store._loaded is True

    def test_backup_invalid_schema(self, tmp_path):
        store = self._make_store(tmp_path)
        store.backup_file.write_text(json.dumps({"bad": "schema"}), encoding="utf-8")
        result = store._try_load_backup()
        assert result is False

    def test_backup_exception_during_load(self, tmp_path):
        store = self._make_store(tmp_path)
        store.backup_file.write_text("not json", encoding="utf-8")
        result = store._try_load_backup()
        assert result is False


# ---------------------------------------------------------------------------
# save_preferences branches
# ---------------------------------------------------------------------------


class TestSavePreferences:
    def _make_store(self, tmp_path: Path) -> PreferenceStore:
        return PreferenceStore(storage_path=tmp_path / "prefs")

    def test_save_loads_first_if_not_loaded(self, tmp_path):
        store = self._make_store(tmp_path)
        assert store._loaded is False
        result = store.save_preferences()
        assert result is True
        assert store._loaded is True

    def test_save_failure(self, tmp_path):
        store = self._make_store(tmp_path)
        store.load_preferences()
        with patch("builtins.open", side_effect=OSError("disk fail")):
            result = store.save_preferences()
        assert result is False


# ---------------------------------------------------------------------------
# add_preference — update existing + correction_count
# ---------------------------------------------------------------------------


class TestAddPreference:
    def _make_store(self, tmp_path: Path) -> PreferenceStore:
        return PreferenceStore(storage_path=tmp_path / "prefs")

    def test_add_new_preference(self, tmp_path):
        store = self._make_store(tmp_path)
        store.load_preferences()
        p = tmp_path / "mydir"
        p.mkdir()
        store.add_preference(p, {"folder_mappings": {"a": "b"}, "confidence": 0.8})
        pref = store.get_preference(p, fallback_to_parent=False)
        assert pref is not None
        assert pref["folder_mappings"] == {"a": "b"}
        assert pref["confidence"] == 0.8

    def test_update_existing_preference_increments_correction(self, tmp_path):
        store = self._make_store(tmp_path)
        store.load_preferences()
        p = tmp_path / "mydir"
        p.mkdir()
        store.add_preference(p, {"folder_mappings": {"a": "b"}})
        store.add_preference(p, {"folder_mappings": {"a": "c"}, "correction_count": 1})
        pref = store.get_preference(p, fallback_to_parent=False)
        assert pref["correction_count"] == 2  # 1 original + 1 increment


# ---------------------------------------------------------------------------
# get_preference — parent fallback
# ---------------------------------------------------------------------------


class TestGetPreference:
    def _make_store(self, tmp_path: Path) -> PreferenceStore:
        return PreferenceStore(storage_path=tmp_path / "prefs")

    def test_fallback_to_parent(self, tmp_path):
        store = self._make_store(tmp_path)
        store.load_preferences()
        parent = tmp_path
        child = tmp_path / "sub"
        child.mkdir()
        store.add_preference(parent, {"folder_mappings": {"x": "y"}})
        pref = store.get_preference(child, fallback_to_parent=True)
        assert pref is not None

    def test_no_fallback_returns_global(self, tmp_path):
        store = self._make_store(tmp_path)
        store.load_preferences()
        child = tmp_path / "nonexistent"
        child.mkdir(exist_ok=True)
        pref = store.get_preference(child, fallback_to_parent=False)
        # Should return global preferences
        assert "folder_mappings" in pref


# ---------------------------------------------------------------------------
# update_confidence
# ---------------------------------------------------------------------------


class TestUpdateConfidence:
    def _make_store(self, tmp_path: Path) -> PreferenceStore:
        return PreferenceStore(storage_path=tmp_path / "prefs")

    def test_update_confidence_success(self, tmp_path):
        store = self._make_store(tmp_path)
        store.load_preferences()
        p = tmp_path / "mydir"
        p.mkdir()
        store.add_preference(p, {"confidence": 0.5})
        store.update_confidence(p, success=True)
        pref = store.get_preference(p, fallback_to_parent=False)
        assert pref["confidence"] > 0.5

    def test_update_confidence_failure(self, tmp_path):
        store = self._make_store(tmp_path)
        store.load_preferences()
        p = tmp_path / "mydir"
        p.mkdir()
        store.add_preference(p, {"confidence": 0.5})
        store.update_confidence(p, success=False)
        pref = store.get_preference(p, fallback_to_parent=False)
        assert pref["confidence"] < 0.5

    def test_update_confidence_nonexistent_path(self, tmp_path):
        store = self._make_store(tmp_path)
        store.load_preferences()
        p = tmp_path / "nope"
        p.mkdir()
        # Should not raise
        store.update_confidence(p, success=True)


# ---------------------------------------------------------------------------
# resolve_conflicts
# ---------------------------------------------------------------------------


class TestResolveConflicts:
    def _make_store(self, tmp_path: Path) -> PreferenceStore:
        return PreferenceStore(storage_path=tmp_path / "prefs")

    def test_empty_list(self, tmp_path):
        store = self._make_store(tmp_path)
        assert store.resolve_conflicts([]) == {}

    def test_single_item(self, tmp_path):
        store = self._make_store(tmp_path)
        pref = {"confidence": 0.8, "correction_count": 3}
        result = store.resolve_conflicts([pref])
        assert result == pref

    def test_multiple_picks_highest_score(self, tmp_path):
        store = self._make_store(tmp_path)
        prefs = [
            {"confidence": 0.2, "correction_count": 1, "updated": "2020-01-01T00:00:00Z"},
            {"confidence": 0.9, "correction_count": 10, "updated": "2025-12-01T00:00:00Z"},
        ]
        result = store.resolve_conflicts(prefs)
        assert result["confidence"] == 0.9


# ---------------------------------------------------------------------------
# _score_preference — bad date handling
# ---------------------------------------------------------------------------


class TestScorePreference:
    def _make_store(self, tmp_path: Path) -> PreferenceStore:
        return PreferenceStore(storage_path=tmp_path / "prefs")

    def test_score_with_invalid_date(self, tmp_path):
        store = self._make_store(tmp_path)
        pref = {"confidence": 0.5, "correction_count": 0, "updated": "bad-date"}
        score = store._score_preference(pref)
        # Should not raise, recency_score = 0.0
        assert score >= 0.0


# ---------------------------------------------------------------------------
# import_json branches
# ---------------------------------------------------------------------------


class TestImportJson:
    def _make_store(self, tmp_path: Path) -> PreferenceStore:
        return PreferenceStore(storage_path=tmp_path / "prefs")

    def test_import_nonexistent_file(self, tmp_path):
        store = self._make_store(tmp_path)
        result = store.import_json(tmp_path / "nope.json")
        assert result is False

    def test_import_invalid_json(self, tmp_path):
        store = self._make_store(tmp_path)
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("{bad json", encoding="utf-8")
        result = store.import_json(bad_file)
        assert result is False

    def test_import_invalid_schema(self, tmp_path):
        store = self._make_store(tmp_path)
        bad_file = tmp_path / "bad.json"
        bad_file.write_text(json.dumps({"no": "good"}), encoding="utf-8")
        result = store.import_json(bad_file)
        assert result is False

    def test_import_valid_with_existing_prefs_creates_timestamped_backup(self, tmp_path):
        store = self._make_store(tmp_path)
        store.load_preferences()
        store.save_preferences()  # creates primary file

        valid_data = store._create_empty_preferences()
        import_file = tmp_path / "import.json"
        import_file.write_text(json.dumps(valid_data), encoding="utf-8")
        result = store.import_json(import_file)
        assert result is True
        # Check timestamped backup was created
        backups = list(store.storage_path.glob("preferences.json.*.backup"))
        assert len(backups) >= 1


# ---------------------------------------------------------------------------
# export_json, get_statistics, clear, list
# ---------------------------------------------------------------------------


class TestMiscOperations:
    def _make_store(self, tmp_path: Path) -> PreferenceStore:
        return PreferenceStore(storage_path=tmp_path / "prefs")

    def test_export_json_success(self, tmp_path):
        store = self._make_store(tmp_path)
        store.load_preferences()
        out = tmp_path / "export.json"
        assert store.export_json(out) is True
        assert out.exists()

    def test_export_json_failure(self, tmp_path):
        store = self._make_store(tmp_path)
        store.load_preferences()
        with patch("builtins.open", side_effect=OSError("fail")):
            assert store.export_json(tmp_path / "nope.json") is False

    def test_get_statistics_empty(self, tmp_path):
        store = self._make_store(tmp_path)
        store.load_preferences()
        stats = store.get_statistics()
        assert stats["total_directories"] == 0
        assert stats["average_confidence"] == 0.0

    def test_get_statistics_with_data(self, tmp_path):
        store = self._make_store(tmp_path)
        store.load_preferences()
        p = tmp_path / "d"
        p.mkdir()
        store.add_preference(p, {"confidence": 0.8, "correction_count": 3})
        stats = store.get_statistics()
        assert stats["total_directories"] == 1
        assert stats["total_corrections"] == 3

    def test_clear_preferences(self, tmp_path):
        store = self._make_store(tmp_path)
        store.load_preferences()
        p = tmp_path / "d"
        p.mkdir()
        store.add_preference(p, {"confidence": 0.8})
        store.clear_preferences()
        assert store.get_statistics()["total_directories"] == 0

    def test_list_directory_preferences(self, tmp_path):
        store = self._make_store(tmp_path)
        store.load_preferences()
        p = tmp_path / "d"
        p.mkdir()
        store.add_preference(p, {"confidence": 0.8})
        items = store.list_directory_preferences()
        assert len(items) == 1
        assert isinstance(items[0], tuple)
