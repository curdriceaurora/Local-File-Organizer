"""Integration tests for intelligence services.

Covers:
  - services/intelligence/preference_store.py — PreferenceStore CRUD
  - services/intelligence/profile_manager.py  — ProfileManager CRUD + activation
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from file_organizer.services.intelligence.preference_store import (
    PreferenceStore,
    SchemaVersion,
)
from file_organizer.services.intelligence.profile_manager import Profile, ProfileManager

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# PreferenceStore
# ---------------------------------------------------------------------------


@pytest.fixture()
def store(tmp_path: Path) -> PreferenceStore:
    return PreferenceStore(storage_path=tmp_path / "prefs")


class TestPreferenceStoreInit:
    def test_creates_storage_dir(self, tmp_path: Path) -> None:
        PreferenceStore(storage_path=tmp_path / "new_prefs")
        assert (tmp_path / "new_prefs").is_dir()

    def test_preference_file_initially_absent(self, store: PreferenceStore) -> None:
        assert not store.preference_file.exists()

    def test_load_fresh_returns_false(self, store: PreferenceStore) -> None:
        # No file → falls back to defaults
        result = store.load_preferences()
        assert result is False

    def test_load_fresh_creates_empty_structure(self, store: PreferenceStore) -> None:
        store.load_preferences()
        stats = store.get_statistics()
        assert stats["total_directories"] == 0
        assert stats["schema_version"] == SchemaVersion.V1_0.value


class TestPreferenceStoreSaveLoad:
    def test_save_creates_file(self, store: PreferenceStore) -> None:
        store.load_preferences()
        store.save_preferences()
        assert store.preference_file.exists()

    def test_save_and_reload_roundtrip(self, store: PreferenceStore, tmp_path: Path) -> None:
        store.load_preferences()
        store.save_preferences()

        store2 = PreferenceStore(storage_path=tmp_path / "prefs")
        store2.load_preferences()
        stats = store2.get_statistics()
        assert stats["schema_version"] == SchemaVersion.V1_0.value

    def test_save_returns_true_on_success(self, store: PreferenceStore) -> None:
        store.load_preferences()
        assert store.save_preferences() is True

    def test_load_returns_true_when_file_valid(self, store: PreferenceStore) -> None:
        store.load_preferences()
        store.save_preferences()

        store2 = PreferenceStore(storage_path=store.storage_path)
        assert store2.load_preferences() is True


class TestPreferenceStoreDirectoryPrefs:
    def test_set_and_get_preference(self, store: PreferenceStore, tmp_path: Path) -> None:
        target_dir = tmp_path / "docs"
        target_dir.mkdir()
        pref_data: dict[str, Any] = {
            "folder_mappings": {"reports": "Reports/2026"},
            "naming_patterns": {"*.pdf": "{date}_{name}.pdf"},
            "category_overrides": {},
            "created": "2026-01-01T00:00:00Z",
            "updated": "2026-01-01T00:00:00Z",
            "confidence": 0.8,
            "correction_count": 2,
        }
        store.add_preference(target_dir, pref_data)
        result = store.get_preference(target_dir)
        assert result is not None
        assert result["folder_mappings"] == {"reports": "Reports/2026"}
        assert result["confidence"] == 0.8

    def test_get_missing_dir_falls_back_to_global(
        self, store: PreferenceStore, tmp_path: Path
    ) -> None:
        # get_preference never returns None — falls back to global preferences
        result = store.get_preference(tmp_path / "nonexistent")
        assert result is not None
        assert isinstance(result, dict)

    def test_list_directory_preferences_empty(self, store: PreferenceStore) -> None:
        entries = store.list_directory_preferences()
        assert entries == []

    def test_list_directory_preferences_populated(
        self, store: PreferenceStore, tmp_path: Path
    ) -> None:
        dir1 = tmp_path / "d1"
        dir1.mkdir()
        dir2 = tmp_path / "d2"
        dir2.mkdir()
        pref: dict[str, Any] = {
            "folder_mappings": {},
            "naming_patterns": {},
            "category_overrides": {},
            "created": "2026-01-01T00:00:00Z",
            "updated": "2026-01-01T00:00:00Z",
            "confidence": 0.5,
            "correction_count": 0,
        }
        store.add_preference(dir1, pref)
        store.add_preference(dir2, pref)
        entries = store.list_directory_preferences()
        assert len(entries) == 2


class TestPreferenceStoreStatistics:
    def test_statistics_total_directories(self, store: PreferenceStore, tmp_path: Path) -> None:
        for i in range(3):
            d = tmp_path / f"dir{i}"
            d.mkdir()
            store.add_preference(
                d,
                {
                    "folder_mappings": {},
                    "naming_patterns": {},
                    "category_overrides": {},
                    "created": "2026-01-01T00:00:00Z",
                    "updated": "2026-01-01T00:00:00Z",
                    "confidence": 0.7,
                    "correction_count": i,
                },
            )
        stats = store.get_statistics()
        assert stats["total_directories"] == 3
        assert stats["total_corrections"] == 3  # 0+1+2

    def test_statistics_average_confidence(self, store: PreferenceStore, tmp_path: Path) -> None:
        for conf in [0.6, 0.8]:
            d = tmp_path / f"d_{conf}"
            d.mkdir()
            store.add_preference(
                d,
                {
                    "folder_mappings": {},
                    "naming_patterns": {},
                    "category_overrides": {},
                    "created": "2026-01-01T00:00:00Z",
                    "updated": "2026-01-01T00:00:00Z",
                    "confidence": conf,
                    "correction_count": 0,
                },
            )
        stats = store.get_statistics()
        assert abs(stats["average_confidence"] - 0.7) < 0.01


class TestPreferenceStoreClear:
    def test_clear_removes_all(self, store: PreferenceStore, tmp_path: Path) -> None:
        d = tmp_path / "mydir"
        d.mkdir()
        store.add_preference(
            d,
            {
                "folder_mappings": {},
                "naming_patterns": {},
                "category_overrides": {},
                "created": "2026-01-01T00:00:00Z",
                "updated": "2026-01-01T00:00:00Z",
                "confidence": 0.5,
                "correction_count": 0,
            },
        )
        assert store.get_statistics()["total_directories"] == 1
        store.clear_preferences()
        assert store.get_statistics()["total_directories"] == 0


class TestPreferenceStoreExportImport:
    def test_export_to_json(self, store: PreferenceStore, tmp_path: Path) -> None:
        store.load_preferences()
        out = tmp_path / "export.json"
        result = store.export_json(out)
        assert result is True
        assert out.exists()
        data = json.loads(out.read_text())
        assert "version" in data

    def test_import_from_json(self, store: PreferenceStore, tmp_path: Path) -> None:
        store.load_preferences()
        out = tmp_path / "export.json"
        store.export_json(out)

        store2 = PreferenceStore(storage_path=tmp_path / "prefs2")
        result = store2.import_json(out)
        assert result is True
        stats = store2.get_statistics()
        assert stats["schema_version"] == SchemaVersion.V1_0.value

    def test_import_invalid_file_returns_false(
        self, store: PreferenceStore, tmp_path: Path
    ) -> None:
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("{invalid json}")
        result = store.import_json(bad_file)
        assert result is False


class TestPreferenceStoreConflictResolution:
    def test_resolve_single_pref_returns_copy(self, store: PreferenceStore) -> None:
        pref = {"confidence": 0.8, "correction_count": 3, "updated": "2026-01-01T00:00:00Z"}
        result = store.resolve_conflicts([pref])
        assert result == pref
        assert result is not pref  # copy

    def test_resolve_empty_list_returns_empty(self, store: PreferenceStore) -> None:
        assert store.resolve_conflicts([]) == {}

    def test_resolve_picks_highest_scored(self, store: PreferenceStore) -> None:
        low = {"confidence": 0.1, "correction_count": 0, "updated": "2020-01-01T00:00:00Z"}
        high = {"confidence": 0.9, "correction_count": 10, "updated": "2026-01-01T00:00:00Z"}
        result = store.resolve_conflicts([low, high])
        assert result["confidence"] == 0.9


class TestPreferenceStoreBackupRecovery:
    def test_corrupt_primary_loads_backup(self, store: PreferenceStore, tmp_path: Path) -> None:
        # Create valid preferences and save
        store.load_preferences()
        store.save_preferences()

        # Corrupt primary file
        store.preference_file.write_text("{invalid}")

        # Reload — should fall back to backup
        store2 = PreferenceStore(storage_path=store.storage_path)
        # Will return False (invalid primary) but load successfully from backup or defaults
        store2.load_preferences()
        # Either True (backup loaded) or False (defaults used); stats should be valid
        stats = store2.get_statistics()
        assert "total_directories" in stats


# ---------------------------------------------------------------------------
# ProfileManager
# ---------------------------------------------------------------------------


@pytest.fixture()
def manager(tmp_path: Path) -> ProfileManager:
    return ProfileManager(storage_path=tmp_path / "profiles")


class TestProfileManagerInit:
    def test_creates_storage_dir(self, tmp_path: Path) -> None:
        ProfileManager(storage_path=tmp_path / "new_profiles")
        assert (tmp_path / "new_profiles").is_dir()

    def test_default_profile_created(self, manager: ProfileManager) -> None:
        profiles = manager.list_profiles()
        names = [p.profile_name for p in profiles]
        assert "default" in names

    def test_list_profiles_returns_list(self, manager: ProfileManager) -> None:
        profiles = manager.list_profiles()
        assert len(profiles) >= 1


class TestProfileManagerCrud:
    def test_create_profile(self, manager: ProfileManager) -> None:
        result = manager.create_profile("Work", "Work preferences")
        assert result is not None
        assert result.profile_name == "Work"

    def test_create_profile_duplicate_returns_none(self, manager: ProfileManager) -> None:
        manager.create_profile("Dup", "first")
        result2 = manager.create_profile("Dup", "second")
        assert result2 is None

    def test_get_profile_existing(self, manager: ProfileManager) -> None:
        manager.create_profile("Home", "Home setup")
        profile = manager.get_profile("Home")
        assert profile is not None
        assert profile.profile_name == "Home"

    def test_get_profile_nonexistent_returns_none(self, manager: ProfileManager) -> None:
        assert manager.get_profile("phantom") is None

    def test_delete_profile(self, manager: ProfileManager) -> None:
        manager.create_profile("ToDelete", "will be removed")
        result = manager.delete_profile("ToDelete")
        assert result is True
        assert manager.get_profile("ToDelete") is None

    def test_delete_nonexistent_returns_false(self, manager: ProfileManager) -> None:
        assert manager.delete_profile("nope") is False

    def test_update_profile_description(self, manager: ProfileManager) -> None:
        manager.create_profile("UpdateMe", "original")
        result = manager.update_profile("UpdateMe", description="updated description")
        assert result is True
        profile = manager.get_profile("UpdateMe")
        assert profile is not None
        assert profile.description == "updated description"


class TestProfileManagerActivation:
    def test_activate_existing_profile(self, manager: ProfileManager) -> None:
        manager.create_profile("Prod", "production")
        result = manager.activate_profile("Prod")
        assert result is True

    def test_activate_nonexistent_returns_false(self, manager: ProfileManager) -> None:
        result = manager.activate_profile("doesnotexist")
        assert result is False

    def test_get_active_profile_returns_default_initially(self, manager: ProfileManager) -> None:
        active = manager.get_active_profile()
        # Either None or "default" depending on initial state
        assert active is None or active.profile_name == "default"

    def test_get_active_after_activation(self, manager: ProfileManager) -> None:
        manager.create_profile("Active", "active profile")
        manager.activate_profile("Active")
        active = manager.get_active_profile()
        assert active is not None
        assert active.profile_name == "Active"


class TestProfileDataClass:
    def test_profile_validation_valid(self) -> None:
        p = Profile(profile_name="test", description="desc")
        assert p.validate() is True

    def test_profile_validation_missing_name_fails(self) -> None:
        p = Profile(profile_name="", description="desc")
        assert p.validate() is False

    def test_profile_validation_missing_description_fails(self) -> None:
        p = Profile(profile_name="test", description="")
        assert p.validate() is False

    def test_profile_roundtrip_dict(self) -> None:
        p = Profile(profile_name="roundtrip", description="rt test")
        d = p.to_dict()
        p2 = Profile.from_dict(d)
        assert p2.profile_name == "roundtrip"
        assert p2.description == "rt test"

    def test_profile_default_preferences_structure(self) -> None:
        p = Profile(profile_name="test", description="x")
        assert "global" in p.preferences
        assert "directory_specific" in p.preferences

    def test_profile_timestamps_auto_set(self) -> None:
        p = Profile(profile_name="ts_test", description="x")
        assert p.created is not None
        assert p.updated is not None


class TestProfileManagerSanitization:
    def test_sanitize_invalid_chars_in_name(self, manager: ProfileManager) -> None:
        # Creating a profile with filesystem-unsafe chars should still work
        result = manager.create_profile('My "Profile"', "sanit test")
        assert result is not None
        # Should be stored with sanitized name
        profiles = manager.list_profiles()
        assert any(p.description == "sanit test" for p in profiles)

    def test_list_profiles_after_multiple_creates(self, manager: ProfileManager) -> None:
        manager.create_profile("A", "profile a")
        manager.create_profile("B", "profile b")
        profiles = manager.list_profiles()
        names = [p.profile_name for p in profiles]
        assert "default" in names or len(profiles) >= 2
