from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.services.intelligence.profile_manager import Profile, ProfileManager
from file_organizer.services.intelligence.profile_migrator import ProfileMigrator


@pytest.fixture
def mock_profile_manager():
    manager = MagicMock(spec=ProfileManager)
    manager.storage_path = Path("/mock/storage")
    return manager


@pytest.fixture
def sample_profile():
    profile = MagicMock(spec=Profile)
    profile.profile_name = "test_profile"
    profile.profile_version = "1.0"
    profile.description = "Test description"
    profile.preferences = {"global": {}, "directory_specific": {}}
    profile.learned_patterns = []
    profile.confidence_data = {}
    profile.to_dict.return_value = {
        "profile_name": "test_profile",
        "profile_version": "1.0",
        "description": "Test description",
        "preferences": {"global": {}, "directory_specific": {}},
        "learned_patterns": [],
        "confidence_data": {},
    }
    profile.validate.return_value = True
    return profile


class TestProfileMigrator:
    def test_init(self, mock_profile_manager):
        migrator = ProfileMigrator(mock_profile_manager)
        assert migrator.profile_manager is mock_profile_manager
        assert migrator.CURRENT_VERSION == "1.0"
        assert "1.0" in migrator.SUPPORTED_VERSIONS

    def test_get_current_timestamp(self, mock_profile_manager):
        migrator = ProfileMigrator(mock_profile_manager)
        timestamp = migrator._get_current_timestamp()
        assert timestamp.endswith("Z")
        assert "T" in timestamp

    def test_migrate_version_profile_not_found(self, mock_profile_manager):
        mock_profile_manager.get_profile.return_value = None
        migrator = ProfileMigrator(mock_profile_manager)

        assert migrator.migrate_version("missing", "2.0") is False

    def test_migrate_version_already_target(self, mock_profile_manager, sample_profile):
        mock_profile_manager.get_profile.return_value = sample_profile
        migrator = ProfileMigrator(mock_profile_manager)

        # Current version is 1.0, asking for 1.0
        assert migrator.migrate_version("test_profile", "1.0") is True

    def test_migrate_version_unsupported_target(self, mock_profile_manager, sample_profile):
        mock_profile_manager.get_profile.return_value = sample_profile
        migrator = ProfileMigrator(mock_profile_manager)

        assert migrator.migrate_version("test_profile", "invalid.version") is False

    @patch(
        "file_organizer.services.intelligence.profile_migrator.ProfileMigrator.backup_before_migration"
    )
    def test_migrate_version_backup_fails(self, mock_backup, mock_profile_manager, sample_profile):
        mock_profile_manager.get_profile.return_value = sample_profile
        mock_backup.return_value = None

        migrator = ProfileMigrator(mock_profile_manager)
        # We need a supported target version to get past that check, but it will fail at backup
        migrator.SUPPORTED_VERSIONS.append("2.0")

        assert migrator.migrate_version("test_profile", "2.0") is False

    @patch(
        "file_organizer.services.intelligence.profile_migrator.ProfileMigrator.backup_before_migration"
    )
    def test_migrate_version_no_path(self, mock_backup, mock_profile_manager, sample_profile):
        mock_profile_manager.get_profile.return_value = sample_profile
        mock_backup.return_value = Path("/mock/backup.json")

        migrator = ProfileMigrator(mock_profile_manager)
        migrator.SUPPORTED_VERSIONS.append("2.0")

        assert migrator.migrate_version("test_profile", "2.0") is False

    @patch(
        "file_organizer.services.intelligence.profile_migrator.ProfileMigrator.backup_before_migration"
    )
    @patch("file_organizer.services.intelligence.profile_migrator.Profile")
    def test_migrate_version_success(
        self, mock_profile_class, mock_backup, mock_profile_manager, sample_profile
    ):
        mock_profile_manager.get_profile.return_value = sample_profile
        mock_backup.return_value = Path("/mock/backup.json")
        mock_profile_manager.update_profile.return_value = True

        migrator = ProfileMigrator(mock_profile_manager)
        migrator.SUPPORTED_VERSIONS.append("2.0")

        # Setup migration func
        def mock_migration_func(data):
            data["migrated"] = True
            return data

        migrator.register_migration("1.0", "2.0", mock_migration_func)

        # Override _find_migration_path to return our custom path
        migrator._find_migration_path = MagicMock(return_value=["1.0->2.0"])

        # Setup mock validated profile
        mock_new_profile = MagicMock(spec=Profile)
        mock_new_profile.description = "Test description"
        mock_new_profile.preferences = {}
        mock_new_profile.learned_patterns = []
        mock_new_profile.confidence_data = {}
        mock_new_profile.validate.return_value = True
        mock_profile_class.from_dict.return_value = mock_new_profile

        assert migrator.migrate_version("test_profile", "2.0") is True
        mock_profile_manager.update_profile.assert_called_once()

    @patch(
        "file_organizer.services.intelligence.profile_migrator.ProfileMigrator.backup_before_migration"
    )
    @patch(
        "file_organizer.services.intelligence.profile_migrator.ProfileMigrator.rollback_migration"
    )
    def test_migrate_version_step_fails(
        self, mock_rollback, mock_backup, mock_profile_manager, sample_profile
    ):
        mock_profile_manager.get_profile.return_value = sample_profile
        mock_backup.return_value = Path("/mock/backup.json")

        migrator = ProfileMigrator(mock_profile_manager)
        migrator.SUPPORTED_VERSIONS.append("2.0")
        migrator._find_migration_path = MagicMock(return_value=["1.0->2.0"])

        # Missing migration func
        assert migrator.migrate_version("test_profile", "2.0") is False
        mock_rollback.assert_called_once_with("test_profile", mock_backup.return_value)

    def test_find_migration_path(self, mock_profile_manager):
        migrator = ProfileMigrator(mock_profile_manager)
        assert migrator._find_migration_path("1.0", "1.0") == []
        assert migrator._find_migration_path("1.0", "2.0") is None

    def test_backup_before_migration_success(self, mock_profile_manager, sample_profile, tmp_path):
        mock_profile_manager.storage_path = tmp_path
        migrator = ProfileMigrator(mock_profile_manager)

        backup_path = migrator.backup_before_migration(sample_profile)

        assert backup_path is not None
        assert backup_path.exists()
        assert "test_profile" in backup_path.name

    def test_backup_before_migration_failure(self, mock_profile_manager, sample_profile):
        # Force a failure by using an invalid storage path type
        mock_profile_manager.storage_path = None
        migrator = ProfileMigrator(mock_profile_manager)

        assert migrator.backup_before_migration(sample_profile) is None

    @patch("file_organizer.services.intelligence.profile_migrator.Profile")
    def test_rollback_migration(self, mock_profile_class, mock_profile_manager, tmp_path):
        migrator = ProfileMigrator(mock_profile_manager)

        backup_file = tmp_path / "backup.json"
        backup_file.write_text('{"profile_name": "test"}')

        mock_restored = MagicMock(spec=Profile)
        mock_restored.description = "Test description"
        mock_restored.preferences = {}
        mock_restored.learned_patterns = []
        mock_restored.confidence_data = {}
        mock_restored.validate.return_value = True
        mock_profile_class.from_dict.return_value = mock_restored
        mock_profile_manager.update_profile.return_value = True

        assert migrator.rollback_migration("test_profile", backup_file) is True

    def test_rollback_migration_file_not_found(self, mock_profile_manager, tmp_path):
        migrator = ProfileMigrator(mock_profile_manager)
        assert migrator.rollback_migration("test", tmp_path / "missing.json") is False

    def test_validate_migration_success(self, mock_profile_manager, sample_profile):
        mock_profile_manager.get_profile.return_value = sample_profile
        migrator = ProfileMigrator(mock_profile_manager)
        assert migrator.validate_migration("test_profile") is True

    def test_validate_migration_failure_not_found(self, mock_profile_manager):
        mock_profile_manager.get_profile.return_value = None
        migrator = ProfileMigrator(mock_profile_manager)
        assert migrator.validate_migration("test_profile") is False

    def test_get_migration_history(self, mock_profile_manager, sample_profile):
        history = [{"from_version": "0.9", "to_version": "1.0"}]
        sample_profile.to_dict.return_value["migration_history"] = history
        mock_profile_manager.get_profile.return_value = sample_profile

        migrator = ProfileMigrator(mock_profile_manager)
        assert migrator.get_migration_history("test") == history

    def test_get_migration_history_none(self, mock_profile_manager):
        mock_profile_manager.get_profile.return_value = None
        migrator = ProfileMigrator(mock_profile_manager)
        assert migrator.get_migration_history("test") is None

    def test_list_backups(self, mock_profile_manager, tmp_path):
        backup_dir = tmp_path / "migration_backups"
        backup_dir.mkdir()

        file1 = backup_dir / "test1.123_456.migration_backup.json"
        file2 = backup_dir / "test2.123_456.migration_backup.json"

        file1.write_text("{}")
        file2.write_text("{}")

        mock_profile_manager.storage_path = tmp_path
        migrator = ProfileMigrator(mock_profile_manager)

        backups = migrator.list_backups()
        assert len(backups) == 2

        filtered = migrator.list_backups("test1")
        assert len(filtered) == 1
        assert "test1" in filtered[0].name

    @patch(
        "file_organizer.services.intelligence.profile_migrator.ProfileMigrator.backup_before_migration"
    )
    @patch("file_organizer.services.intelligence.profile_migrator.Profile")
    @patch(
        "file_organizer.services.intelligence.profile_migrator.ProfileMigrator.rollback_migration"
    )
    def test_migrate_version_invalid_migrated_profile(
        self, mock_rollback, mock_profile_class, mock_backup, mock_profile_manager, sample_profile
    ):
        mock_profile_manager.get_profile.return_value = sample_profile
        mock_backup.return_value = Path("/mock/backup.json")

        migrator = ProfileMigrator(mock_profile_manager)
        migrator.SUPPORTED_VERSIONS.append("2.0")

        def mock_migration_func(data):
            return data

        migrator.register_migration("1.0", "2.0", mock_migration_func)
        migrator._find_migration_path = MagicMock(return_value=["1.0->2.0"])

        mock_new_profile = MagicMock()
        mock_new_profile.validate.return_value = False
        mock_profile_class.from_dict.return_value = mock_new_profile

        assert migrator.migrate_version("test_profile", "2.0") is False
        mock_rollback.assert_called_once()

    @patch(
        "file_organizer.services.intelligence.profile_migrator.ProfileMigrator.backup_before_migration"
    )
    @patch("file_organizer.services.intelligence.profile_migrator.Profile")
    @patch(
        "file_organizer.services.intelligence.profile_migrator.ProfileMigrator.rollback_migration"
    )
    def test_migrate_version_update_fails(
        self, mock_rollback, mock_profile_class, mock_backup, mock_profile_manager, sample_profile
    ):
        mock_profile_manager.get_profile.return_value = sample_profile
        mock_backup.return_value = Path("/mock/backup.json")
        mock_profile_manager.update_profile.return_value = False

        migrator = ProfileMigrator(mock_profile_manager)
        migrator.SUPPORTED_VERSIONS.append("2.0")
        migrator.register_migration("1.0", "2.0", lambda d: d)
        migrator._find_migration_path = MagicMock(return_value=["1.0->2.0"])

        mock_new_profile = MagicMock()
        mock_new_profile.validate.return_value = True
        mock_profile_class.from_dict.return_value = mock_new_profile

        assert migrator.migrate_version("test_profile", "2.0") is False
        mock_rollback.assert_called_once()

    def test_migrate_version_exception(self, mock_profile_manager):
        mock_profile_manager.get_profile.side_effect = Exception("Test Error")
        migrator = ProfileMigrator(mock_profile_manager)
        assert migrator.migrate_version("test", "2.0") is False

    @patch("file_organizer.services.intelligence.profile_migrator.Profile")
    def test_rollback_migration_invalid_backup(
        self, mock_profile_class, mock_profile_manager, tmp_path
    ):
        migrator = ProfileMigrator(mock_profile_manager)
        backup_file = tmp_path / "backup.json"
        backup_file.write_text("{}")

        mock_restored = MagicMock()
        mock_restored.validate.return_value = False
        mock_profile_class.from_dict.return_value = mock_restored

        assert migrator.rollback_migration("test", backup_file) is False

    def test_rollback_migration_exception(self, mock_profile_manager, tmp_path):
        migrator = ProfileMigrator(mock_profile_manager)
        backup_file = tmp_path / "backup.json"
        backup_file.write_text("invalid json")

        assert migrator.rollback_migration("test", backup_file) is False

    def test_validate_migration_invalid_profile(self, mock_profile_manager, sample_profile):
        sample_profile.validate.return_value = False
        mock_profile_manager.get_profile.return_value = sample_profile
        migrator = ProfileMigrator(mock_profile_manager)
        assert migrator.validate_migration("test") is False

    def test_validate_migration_unsupported_version(self, mock_profile_manager, sample_profile):
        sample_profile.profile_version = "99.0"
        mock_profile_manager.get_profile.return_value = sample_profile
        migrator = ProfileMigrator(mock_profile_manager)
        assert migrator.validate_migration("test") is False

    def test_validate_migration_invalid_preferences_type(
        self, mock_profile_manager, sample_profile
    ):
        sample_profile.preferences = []  # Not a dict
        mock_profile_manager.get_profile.return_value = sample_profile
        migrator = ProfileMigrator(mock_profile_manager)
        assert migrator.validate_migration("test") is False

    def test_validate_migration_missing_preference_keys(self, mock_profile_manager, sample_profile):
        sample_profile.preferences = {"global": {}}  # Missing directory_specific
        mock_profile_manager.get_profile.return_value = sample_profile
        migrator = ProfileMigrator(mock_profile_manager)
        assert migrator.validate_migration("test") is False

    def test_validate_migration_exception(self, mock_profile_manager):
        mock_profile_manager.get_profile.side_effect = Exception("Test Error")
        migrator = ProfileMigrator(mock_profile_manager)
        assert migrator.validate_migration("test") is False

    def test_list_backups_no_dir(self, mock_profile_manager, tmp_path):
        mock_profile_manager.storage_path = tmp_path / "nonexistent"
        migrator = ProfileMigrator(mock_profile_manager)
        assert migrator.list_backups() == []

    def test_list_backups_exception(self, mock_profile_manager):
        mock_profile_manager.storage_path = None
        migrator = ProfileMigrator(mock_profile_manager)
        assert migrator.list_backups() == []

    def test_get_migration_history_exception(self, mock_profile_manager):
        mock_profile_manager.get_profile.side_effect = Exception("Test Error")
        migrator = ProfileMigrator(mock_profile_manager)
        assert migrator.get_migration_history("test") is None

    def test_migrate_v1_to_v2(self, mock_profile_manager):
        migrator = ProfileMigrator(mock_profile_manager)
        assert migrator._migrate_v1_to_v2({}) is None
