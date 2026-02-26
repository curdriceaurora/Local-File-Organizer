"""
Tests for ProfileMigrator

Tests profile version migration, backup/rollback, validation,
migration history, and custom migration registration.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import time
from pathlib import Path

import pytest

from file_organizer.services.intelligence.profile_manager import Profile, ProfileManager
from file_organizer.services.intelligence.profile_migrator import ProfileMigrator


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_storage():
    """Create temporary storage directory for tests."""
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def profile_manager(temp_storage):
    """Create ProfileManager with temporary storage."""
    return ProfileManager(storage_path=temp_storage / "profiles")


@pytest.fixture
def migrator(profile_manager):
    """Create ProfileMigrator backed by a temporary ProfileManager."""
    return ProfileMigrator(profile_manager)


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------


def test_init_empty_migration_functions(migrator):
    """Test that a new migrator starts with empty migration functions."""
    assert isinstance(migrator._migration_functions, dict)
    assert len(migrator._migration_functions) == 0


# ---------------------------------------------------------------------------
# migrate_version – profile not found
# ---------------------------------------------------------------------------


def test_migrate_version_profile_not_found(migrator):
    """Test migrate_version returns False when profile does not exist."""
    result = migrator.migrate_version("nonexistent", "1.0")
    assert result is False


# ---------------------------------------------------------------------------
# migrate_version – already at target version
# ---------------------------------------------------------------------------


def test_migrate_version_already_at_target(migrator, profile_manager):
    """Test migrate_version returns True when profile is already at target."""
    profile_manager.create_profile("test_profile", "Test")

    result = migrator.migrate_version("test_profile", "1.0")
    assert result is True


# ---------------------------------------------------------------------------
# migrate_version – unsupported target version
# ---------------------------------------------------------------------------


def test_migrate_version_unsupported_version(migrator, profile_manager):
    """Test migrate_version returns False for an unsupported target version."""
    profile_manager.create_profile("test_profile", "Test")

    result = migrator.migrate_version("test_profile", "99.0")
    assert result is False


# ---------------------------------------------------------------------------
# migrate_version – no migration path
# ---------------------------------------------------------------------------


def test_migrate_version_no_migration_path(migrator, profile_manager):
    """Test migrate_version returns False when no migration path exists."""
    profile_manager.create_profile("test_profile", "Test")
    # Manually set profile to a different version so a migration would be needed
    profile = profile_manager.get_profile("test_profile")
    profile_data = profile.to_dict()
    profile_data["profile_version"] = "0.5"
    # Write the modified profile directly
    profile_path = profile_manager._get_profile_path("test_profile")
    with open(profile_path, "w", encoding="utf-8") as f:
        json.dump(profile_data, f, indent=2, ensure_ascii=False)

    result = migrator.migrate_version("test_profile", "1.0", backup=False)
    assert result is False


# ---------------------------------------------------------------------------
# _find_migration_path
# ---------------------------------------------------------------------------


def test_find_migration_path_same_version(migrator):
    """Test _find_migration_path returns empty list for same version."""
    path = migrator._find_migration_path("1.0", "1.0")
    assert path == []


def test_find_migration_path_different_version_no_paths(migrator):
    """Test _find_migration_path returns None when no path registered."""
    path = migrator._find_migration_path("1.0", "2.0")
    assert path is None


# ---------------------------------------------------------------------------
# backup_before_migration
# ---------------------------------------------------------------------------


def test_backup_before_migration_creates_file(migrator, profile_manager):
    """Test that backup creates a JSON file in migration_backups/."""
    profile = profile_manager.create_profile("backup_test", "Backup test")

    backup_path = migrator.backup_before_migration(profile)
    assert backup_path is not None
    assert backup_path.exists()
    assert backup_path.suffix == ".json"
    assert "migration_backups" in str(backup_path.parent)

    # Verify contents
    with open(backup_path, encoding="utf-8") as f:
        data = json.load(f)
    assert data["profile_name"] == "backup_test"


# ---------------------------------------------------------------------------
# rollback_migration
# ---------------------------------------------------------------------------


def test_rollback_migration_restores_profile(migrator, profile_manager):
    """Test rollback reads backup and restores the profile."""
    profile = profile_manager.create_profile("rollback_test", "Original description")
    backup_path = migrator.backup_before_migration(profile)
    assert backup_path is not None

    # Modify the profile so we can verify rollback
    profile_manager.update_profile("rollback_test", description="Modified description")
    modified = profile_manager.get_profile("rollback_test")
    assert modified.description == "Modified description"

    # Rollback
    success = migrator.rollback_migration("rollback_test", backup_path)
    assert success is True

    restored = profile_manager.get_profile("rollback_test")
    assert restored.description == "Original description"


def test_rollback_migration_missing_backup(migrator, profile_manager):
    """Test rollback returns False when backup file does not exist."""
    profile_manager.create_profile("rollback_test2", "Test")

    result = migrator.rollback_migration("rollback_test2", Path("/nonexistent/backup.json"))
    assert result is False


# ---------------------------------------------------------------------------
# validate_migration
# ---------------------------------------------------------------------------


def test_validate_migration_valid_profile(migrator, profile_manager):
    """Test validate_migration returns True for a valid profile."""
    profile_manager.create_profile("valid_profile", "Valid")

    result = migrator.validate_migration("valid_profile")
    assert result is True


def test_validate_migration_missing_profile(migrator):
    """Test validate_migration returns False for a missing profile."""
    result = migrator.validate_migration("does_not_exist")
    assert result is False


def test_validate_migration_invalid_structure(migrator, profile_manager):
    """Test validate_migration returns False for invalid profile structure."""
    profile_manager.create_profile("invalid_profile", "Invalid")

    # Corrupt the profile by removing required keys
    profile_path = profile_manager._get_profile_path("invalid_profile")
    with open(profile_path, encoding="utf-8") as f:
        data = json.load(f)
    data["preferences"] = "not_a_dict"
    with open(profile_path, "w", encoding="utf-8") as f:
        json.dump(data, f)

    result = migrator.validate_migration("invalid_profile")
    assert result is False


# ---------------------------------------------------------------------------
# get_migration_history
# ---------------------------------------------------------------------------


def test_get_migration_history_no_history(migrator, profile_manager):
    """Test get_migration_history returns empty list for fresh profile."""
    profile_manager.create_profile("history_test", "History test")

    history = migrator.get_migration_history("history_test")
    assert history == []


def test_get_migration_history_missing_profile(migrator):
    """Test get_migration_history returns None for missing profile."""
    result = migrator.get_migration_history("nonexistent")
    assert result is None


# ---------------------------------------------------------------------------
# list_backups
# ---------------------------------------------------------------------------


def test_list_backups_empty(migrator):
    """Test list_backups returns empty list when no backups exist."""
    backups = migrator.list_backups()
    assert backups == []


def test_list_backups_with_backups(migrator, profile_manager):
    """Test list_backups returns sorted list of backup paths."""
    profile = profile_manager.create_profile("list_test", "List test")

    # Create two backups with a pause so timestamps differ
    path1 = migrator.backup_before_migration(profile)
    time.sleep(1.1)  # Ensure different second-level timestamp
    path2 = migrator.backup_before_migration(profile)
    assert path1 is not None
    assert path2 is not None

    backups = migrator.list_backups()
    assert len(backups) >= 2
    # Newest first
    assert backups[0].stat().st_mtime >= backups[1].stat().st_mtime


def test_list_backups_filter_by_name(migrator, profile_manager):
    """Test list_backups with profile_name filter returns only matching."""
    p1 = profile_manager.create_profile("alpha", "Alpha")
    p2 = profile_manager.create_profile("beta", "Beta")

    migrator.backup_before_migration(p1)
    migrator.backup_before_migration(p2)

    alpha_backups = migrator.list_backups(profile_name="alpha")
    for b in alpha_backups:
        assert b.name.startswith("alpha")


# ---------------------------------------------------------------------------
# register_migration
# ---------------------------------------------------------------------------


def test_register_migration_adds_function(migrator):
    """Test register_migration stores the function in the dict."""
    called = []

    def custom_migration(data):
        called.append(True)
        return data

    migrator.register_migration("1.0", "2.0", custom_migration)

    assert "1.0->2.0" in migrator._migration_functions
    assert migrator._migration_functions["1.0->2.0"] is custom_migration


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
