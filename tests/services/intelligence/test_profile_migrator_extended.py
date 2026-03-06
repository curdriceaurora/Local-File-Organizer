"""Extended tests for ProfileMigrator.

Covers migration paths with registered functions, validation edge cases,
rollback error paths, get_current_timestamp, _migrate_v1_to_v2 placeholder,
exception handling, and backup=False flow.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from file_organizer.services.intelligence.profile_manager import ProfileManager
from file_organizer.services.intelligence.profile_migrator import ProfileMigrator

pytestmark = [pytest.mark.unit]


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


def _set_profile_version(profile_manager, profile_name, version):
    """Helper to set a profile's version by writing directly to disk."""
    profile_path = profile_manager._get_profile_path(profile_name)
    with open(profile_path, encoding="utf-8") as f:
        data = json.load(f)
    data["profile_version"] = version
    with open(profile_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# _get_current_timestamp
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetCurrentTimestamp:
    """Tests for _get_current_timestamp method."""

    def test_returns_string(self, migrator):
        """Test returns an ISO timestamp string."""
        ts = migrator._get_current_timestamp()
        assert isinstance(ts, str)
        assert "T" in ts

    def test_ends_with_z(self, migrator):
        """Test timestamp ends with Z (UTC)."""
        ts = migrator._get_current_timestamp()
        assert ts.endswith("Z")


# ---------------------------------------------------------------------------
# migrate_version – successful migration with registered function
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMigrateVersionWithRegisteredFunction:
    """Tests covering the full successful migration path."""

    def test_successful_migration(self, migrator, profile_manager):
        """Test a successful migration through registered migration function."""
        profile_manager.create_profile("mig_test", "Migration test")
        _set_profile_version(profile_manager, "mig_test", "0.9")

        # Add 0.9 as supported
        migrator.SUPPORTED_VERSIONS = ["0.9", "1.0"]

        # Register migration function
        def migrate_0_9_to_1_0(data):
            data["preferences"]["global"]["migrated"] = True
            return data

        migrator.register_migration("0.9", "1.0", migrate_0_9_to_1_0)

        # Patch _find_migration_path to return the migration step
        with patch.object(migrator, "_find_migration_path", return_value=["0.9->1.0"]):
            result = migrator.migrate_version("mig_test", "1.0")

        assert result is True
        updated = profile_manager.get_profile("mig_test")
        assert updated is not None

    def test_migration_with_backup_false(self, migrator, profile_manager):
        """Test migration with backup=False skips backup creation."""
        profile_manager.create_profile("nobk_test", "No backup test")
        _set_profile_version(profile_manager, "nobk_test", "0.9")

        migrator.SUPPORTED_VERSIONS = ["0.9", "1.0"]

        def migrate_fn(data):
            return data

        migrator.register_migration("0.9", "1.0", migrate_fn)

        with patch.object(migrator, "_find_migration_path", return_value=["0.9->1.0"]):
            result = migrator.migrate_version("nobk_test", "1.0", backup=False)

        assert result is True

    def test_migration_step_function_not_found(self, migrator, profile_manager):
        """Test migration fails when migration function is not found for a step."""
        profile_manager.create_profile("step_fail", "Step fail test")
        _set_profile_version(profile_manager, "step_fail", "0.9")
        migrator.SUPPORTED_VERSIONS = ["0.9", "1.0"]

        # Do NOT register a function for "0.9->1.0"
        with patch.object(migrator, "_find_migration_path", return_value=["0.9->1.0"]):
            result = migrator.migrate_version("step_fail", "1.0", backup=False)

        assert result is False

    def test_migration_step_function_raises(self, migrator, profile_manager):
        """Test migration rolls back when migration function raises."""
        profile_manager.create_profile("exc_test", "Exception test")
        _set_profile_version(profile_manager, "exc_test", "0.9")
        migrator.SUPPORTED_VERSIONS = ["0.9", "1.0"]

        def bad_migration(data):
            raise ValueError("Migration failed")

        migrator.register_migration("0.9", "1.0", bad_migration)

        with patch.object(migrator, "_find_migration_path", return_value=["0.9->1.0"]):
            result = migrator.migrate_version("exc_test", "1.0")

        assert result is False

    def test_migration_step_raises_with_backup_triggers_rollback(self, migrator, profile_manager):
        """Test migration function exception triggers rollback when backup exists."""
        profile_manager.create_profile("rb_test", "Rollback test")
        _set_profile_version(profile_manager, "rb_test", "0.9")
        migrator.SUPPORTED_VERSIONS = ["0.9", "1.0"]

        def bad_migration(data):
            raise RuntimeError("boom")

        migrator.register_migration("0.9", "1.0", bad_migration)

        with (
            patch.object(migrator, "_find_migration_path", return_value=["0.9->1.0"]),
            patch.object(migrator, "rollback_migration") as mock_rollback,
        ):
            result = migrator.migrate_version("rb_test", "1.0", backup=True)

        assert result is False
        mock_rollback.assert_called_once()

    def test_migration_validation_fails_triggers_rollback(self, migrator, profile_manager):
        """Test that validation failure after migration triggers rollback."""
        profile_manager.create_profile("val_fail", "Validation fail")
        _set_profile_version(profile_manager, "val_fail", "0.9")
        migrator.SUPPORTED_VERSIONS = ["0.9", "1.0"]

        def bad_data_migration(data):
            # Return data that will fail Profile.validate()
            data["description"] = ""  # Empty description fails validation
            return data

        migrator.register_migration("0.9", "1.0", bad_data_migration)

        with (
            patch.object(migrator, "_find_migration_path", return_value=["0.9->1.0"]),
            patch.object(migrator, "rollback_migration") as mock_rollback,
        ):
            result = migrator.migrate_version("val_fail", "1.0", backup=True)

        assert result is False
        mock_rollback.assert_called_once()

    def test_migration_save_fails_triggers_rollback(self, migrator, profile_manager):
        """Test that save failure after migration triggers rollback."""
        profile_manager.create_profile("save_fail", "Save fail test")
        _set_profile_version(profile_manager, "save_fail", "0.9")
        migrator.SUPPORTED_VERSIONS = ["0.9", "1.0"]

        def identity_migration(data):
            return data

        migrator.register_migration("0.9", "1.0", identity_migration)

        with (
            patch.object(migrator, "_find_migration_path", return_value=["0.9->1.0"]),
            patch.object(profile_manager, "update_profile", return_value=False),
            patch.object(migrator, "rollback_migration") as mock_rollback,
        ):
            result = migrator.migrate_version("save_fail", "1.0", backup=True)

        assert result is False
        mock_rollback.assert_called_once()

    def test_migration_outer_exception(self, migrator):
        """Test migrate_version handles outer exception gracefully."""
        with patch.object(
            migrator.profile_manager, "get_profile", side_effect=RuntimeError("kaboom")
        ):
            result = migrator.migrate_version("any_profile", "1.0")
        assert result is False

    def test_backup_failure_aborts_migration(self, migrator, profile_manager):
        """Test that backup failure aborts migration."""
        profile_manager.create_profile("bk_fail", "Backup fail test")
        _set_profile_version(profile_manager, "bk_fail", "0.9")
        migrator.SUPPORTED_VERSIONS = ["0.9", "1.0"]

        with patch.object(migrator, "backup_before_migration", return_value=None):
            result = migrator.migrate_version("bk_fail", "1.0", backup=True)

        assert result is False


# ---------------------------------------------------------------------------
# validate_migration – additional edge cases
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestValidateMigrationExtended:
    """Additional validate_migration tests for coverage."""

    def test_unsupported_version(self, migrator, profile_manager):
        """Test validation fails for unsupported profile version."""
        profile_manager.create_profile("unsup_ver", "Unsupported version test")
        _set_profile_version(profile_manager, "unsup_ver", "99.0")

        result = migrator.validate_migration("unsup_ver")
        assert result is False

    def test_missing_global_key(self, migrator, profile_manager):
        """Test validation fails when preferences missing 'global' key."""
        profile_manager.create_profile("no_global", "No global key")
        profile_path = profile_manager._get_profile_path("no_global")
        with open(profile_path, encoding="utf-8") as f:
            data = json.load(f)
        data["preferences"] = {"directory_specific": {}}
        with open(profile_path, "w", encoding="utf-8") as f:
            json.dump(data, f)

        result = migrator.validate_migration("no_global")
        assert result is False

    def test_missing_directory_specific_key(self, migrator, profile_manager):
        """Test validation fails when preferences missing 'directory_specific' key."""
        profile_manager.create_profile("no_dir", "No directory_specific key")
        profile_path = profile_manager._get_profile_path("no_dir")
        with open(profile_path, encoding="utf-8") as f:
            data = json.load(f)
        data["preferences"] = {"global": {}}
        with open(profile_path, "w", encoding="utf-8") as f:
            json.dump(data, f)

        result = migrator.validate_migration("no_dir")
        assert result is False

    def test_validate_exception(self, migrator):
        """Test validate_migration handles exceptions gracefully."""
        with patch.object(
            migrator.profile_manager, "get_profile", side_effect=RuntimeError("error")
        ):
            result = migrator.validate_migration("any_profile")
        assert result is False

    def test_non_dict_preferences(self, migrator, profile_manager):
        """Test validation fails when preferences is not a dict."""
        profile_manager.create_profile("bad_prefs", "Bad preferences")
        profile_path = profile_manager._get_profile_path("bad_prefs")
        with open(profile_path, encoding="utf-8") as f:
            data = json.load(f)
        data["preferences"] = "not_a_dict"
        with open(profile_path, "w", encoding="utf-8") as f:
            json.dump(data, f)

        result = migrator.validate_migration("bad_prefs")
        assert result is False


# ---------------------------------------------------------------------------
# rollback_migration – additional edge cases
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRollbackMigrationExtended:
    """Additional rollback_migration tests for coverage."""

    def test_rollback_invalid_backup_data(self, migrator, profile_manager, temp_storage):
        """Test rollback fails when backup data is invalid JSON."""
        profile_manager.create_profile("rb_invalid", "Rollback invalid test")

        backup_file = temp_storage / "invalid_backup.json"
        with open(backup_file, "w", encoding="utf-8") as f:
            f.write("{not valid json")

        result = migrator.rollback_migration("rb_invalid", backup_file)
        assert result is False

    def test_rollback_backup_fails_validation(self, migrator, profile_manager, temp_storage):
        """Test rollback fails when backup profile doesn't validate."""
        profile_manager.create_profile("rb_noval", "Rollback no validation")

        # Create backup with invalid profile data (empty name)
        backup_file = temp_storage / "bad_backup.json"
        bad_data = {
            "profile_name": "",
            "description": "",
            "profile_version": "1.0",
            "preferences": {"global": {}, "directory_specific": {}},
        }
        with open(backup_file, "w", encoding="utf-8") as f:
            json.dump(bad_data, f)

        result = migrator.rollback_migration("rb_noval", backup_file)
        assert result is False

    def test_rollback_save_fails(self, migrator, profile_manager, temp_storage):
        """Test rollback returns False when save fails."""
        profile = profile_manager.create_profile("rb_save", "Rollback save fail")
        backup_path = migrator.backup_before_migration(profile)
        assert backup_path is not None

        with patch.object(profile_manager, "update_profile", return_value=False):
            result = migrator.rollback_migration("rb_save", backup_path)
        assert result is False

    def test_rollback_exception(self, migrator, profile_manager, temp_storage):
        """Test rollback handles exceptions gracefully."""
        profile_manager.create_profile("rb_exc", "Rollback exception")
        result = migrator.rollback_migration("rb_exc", Path("/nonexistent/backup.json"))
        assert result is False


# ---------------------------------------------------------------------------
# backup_before_migration – additional edge cases
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBackupExtended:
    """Additional backup_before_migration tests."""

    def test_backup_exception(self, migrator, profile_manager):
        """Test backup returns None on exception."""
        profile = profile_manager.create_profile("bk_exc", "Backup exception test")

        with patch("builtins.open", side_effect=PermissionError("denied")):
            result = migrator.backup_before_migration(profile)
        assert result is None


# ---------------------------------------------------------------------------
# get_migration_history – additional edge cases
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetMigrationHistoryExtended:
    """Additional get_migration_history tests."""

    def test_exception_returns_none(self, migrator):
        """Test get_migration_history returns None on exception."""
        with patch.object(
            migrator.profile_manager, "get_profile", side_effect=RuntimeError("error")
        ):
            result = migrator.get_migration_history("any_profile")
        assert result is None


# ---------------------------------------------------------------------------
# list_backups – additional edge cases
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestListBackupsExtended:
    """Additional list_backups tests."""

    def test_exception_returns_empty_list(self, migrator):
        """Test list_backups returns empty list on exception."""
        # Temporarily replace storage_path with a property that raises
        original_storage_path = migrator.profile_manager.storage_path
        migrator.profile_manager.storage_path = None  # Will cause TypeError on / operator
        try:
            result = migrator.list_backups()
        finally:
            migrator.profile_manager.storage_path = original_storage_path
        assert result == []


# ---------------------------------------------------------------------------
# _migrate_v1_to_v2 placeholder
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMigrateV1ToV2:
    """Tests for the _migrate_v1_to_v2 placeholder method."""

    def test_placeholder_returns_none(self, migrator):
        """Test that the placeholder migration returns None (pass statement)."""
        result = migrator._migrate_v1_to_v2({"profile_name": "test"})
        assert result is None


# ---------------------------------------------------------------------------
# register_migration
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRegisterMigrationExtended:
    """Additional register_migration tests."""

    def test_overwrite_existing_registration(self, migrator):
        """Test overwriting an existing migration registration."""

        def fn1(data):
            return data

        def fn2(data):
            return data

        migrator.register_migration("1.0", "2.0", fn1)
        migrator.register_migration("1.0", "2.0", fn2)

        assert migrator._migration_functions["1.0->2.0"] is fn2

    def test_multiple_registrations(self, migrator):
        """Test registering multiple different migration paths."""

        def fn1(data):
            return data

        def fn2(data):
            return data

        migrator.register_migration("1.0", "2.0", fn1)
        migrator.register_migration("2.0", "3.0", fn2)

        assert "1.0->2.0" in migrator._migration_functions
        assert "2.0->3.0" in migrator._migration_functions
