"""Verification tests for path migration and backwards compatibility."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from file_organizer.config.manager import ConfigManager
from file_organizer.config.path_manager import PathManager
from file_organizer.config.path_migration import PathMigrator, detect_legacy_paths
from file_organizer.config.schema import AppConfig
from file_organizer.services.intelligence.preference_store import PreferenceStore


def test_migration_detects_all_legacy_paths():
    """Migration should detect all three legacy path variants"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        config_home = tmp_path / ".config"
        data_home = tmp_path / ".local" / "share"

        # Create all three legacy path variants
        legacy_hyphen = tmp_path / ".file-organizer"
        legacy_underscore = tmp_path / ".file_organizer"
        legacy_config = config_home / "file-organizer"

        legacy_hyphen.mkdir()
        legacy_underscore.mkdir()
        legacy_config.mkdir(parents=True)

        # Create some test files
        (legacy_hyphen / "test.txt").write_text("legacy hyphen")
        (legacy_underscore / "test.txt").write_text("legacy underscore")
        (legacy_config / "test.txt").write_text("legacy config")

        # Detect should find all three
        detected = detect_legacy_paths(tmp_path, config_home, data_home)

        assert len(detected) == 3
        assert legacy_hyphen in detected
        assert legacy_underscore in detected
        assert legacy_config in detected


def test_migration_preserves_data_integrity():
    """Migration should preserve all file data without corruption"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        legacy_path = tmp_path / ".file-organizer"
        canonical_path = tmp_path / ".local" / "share" / "file-organizer"

        legacy_path.mkdir()

        # Create test files with specific content
        test_data = {
            "config.json": {"key": "value", "number": 42},
            "data.txt": "sample file content\nwith newlines",
            "subdir/nested.json": {"nested": {"data": [1, 2, 3]}},
        }

        for file_path, content in test_data.items():
            full_path = legacy_path / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)

            if isinstance(content, dict):
                full_path.write_text(json.dumps(content, indent=2))
            else:
                full_path.write_text(content)

        # Perform migration
        migrator = PathMigrator(legacy_path, canonical_path)
        migrator.migrate()

        # Verify all files exist and have correct content
        for file_path, content in test_data.items():
            migrated_file = canonical_path / file_path
            assert migrated_file.exists(), f"File {file_path} not migrated"

            if isinstance(content, dict):
                migrated_content = json.loads(migrated_file.read_text())
                assert migrated_content == content, f"Data mismatch in {file_path}"
            else:
                migrated_content = migrated_file.read_text()
                assert migrated_content == content, f"Content mismatch in {file_path}"


def test_migration_creates_timestamped_backup():
    """Migration should create a timestamped backup of original files"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        legacy_path = tmp_path / ".file-organizer"
        canonical_path = tmp_path / ".local" / "share" / "file-organizer"

        legacy_path.mkdir()
        (legacy_path / "important.txt").write_text("important data")

        migrator = PathMigrator(legacy_path, canonical_path)
        backup_path = migrator.backup_legacy_path()

        # Verify backup exists and has timestamp format
        assert backup_path.exists()
        assert ".backup." in backup_path.name
        assert (backup_path / "important.txt").exists()
        assert (backup_path / "important.txt").read_text() == "important data"


def test_backwards_compatibility_default_paths():
    """Legacy default paths should still work for backwards compatibility"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        with patch.dict(os.environ, {"HOME": str(tmp_path)}):
            # Old code using DEFAULT_CONFIG_DIR should still work
            from file_organizer.config.manager import DEFAULT_CONFIG_DIR

            config_manager_old = ConfigManager(config_dir=DEFAULT_CONFIG_DIR)

            # Should be able to save and load config
            config = AppConfig(profile_name="test")
            config_manager_old.save(config, profile="test")

            # File should exist in legacy location
            assert (DEFAULT_CONFIG_DIR / "config.yaml").exists()

            # Should be able to load it back
            loaded = config_manager_old.load(profile="test")
            assert loaded.profile_name == "test"


def test_new_and_legacy_paths_coexist():
    """New XDG paths and legacy paths can coexist for migration period"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        # Set XDG_CONFIG_HOME to a custom location so PathManager uses
        # a different path from ConfigManager's hardcoded default
        custom_xdg = tmp_path / "custom-xdg-config"
        with patch.dict(
            os.environ,
            {
                "HOME": str(tmp_path),
                "XDG_CONFIG_HOME": str(custom_xdg),
            },
        ):
            # Create config in legacy path (hardcoded default)
            legacy_cm = ConfigManager()
            legacy_config = AppConfig(profile_name="legacy")
            legacy_cm.save(legacy_config, profile="legacy")

            # Create config in new XDG path (respects XDG_CONFIG_HOME)
            path_manager = PathManager()
            path_manager.ensure_directories()
            xdg_cm = ConfigManager(config_dir=path_manager.config_dir)
            xdg_config = AppConfig(profile_name="xdg")
            xdg_cm.save(xdg_config, profile="xdg")

            # Both should be accessible
            assert legacy_cm.load(profile="legacy").profile_name == "legacy"
            assert xdg_cm.load(profile="xdg").profile_name == "xdg"

            # Paths should be different when XDG_CONFIG_HOME is customized
            assert legacy_cm.config_dir != xdg_cm.config_dir


def test_migration_logging_creates_audit_trail():
    """Migration should create logs for audit and verification"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        legacy_path = tmp_path / ".file-organizer"
        canonical_path = tmp_path / ".local" / "share" / "file-organizer"

        legacy_path.mkdir()
        (legacy_path / "test.txt").write_text("test data")

        migrator = PathMigrator(legacy_path, canonical_path)
        migrator.migrate()
        migrator.finalize_migration()

        # Migration log should contain required information
        log = migrator.migration_log

        assert "timestamp" in log
        assert "from" in log
        assert "to" in log
        assert "status" in log
        assert "backup" in log
        assert log["from"] == str(legacy_path)
        assert log["to"] == str(canonical_path)
        assert log["status"] == "completed"


def test_config_manager_with_path_manager_production_workflow():
    """Test realistic production workflow with ConfigManager and PathManager"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        with patch.dict(os.environ, {"HOME": str(tmp_path)}):
            # Initialize with PathManager (production pattern)
            path_manager = PathManager()
            path_manager.ensure_directories()

            config_manager = ConfigManager(config_dir=path_manager.config_dir)

            # Create and save production config
            prod_config = AppConfig(profile_name="production", default_methodology="para")
            config_manager.save(prod_config, profile="production")

            # Simulate restart - load production config
            config_manager2 = ConfigManager(config_dir=path_manager.config_dir)
            loaded_config = config_manager2.load(profile="production")

            assert loaded_config.profile_name == "production"
            assert loaded_config.default_methodology == "para"


def test_preference_store_with_path_manager_production_workflow():
    """Test realistic production workflow with PreferenceStore and PathManager"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        with patch.dict(os.environ, {"HOME": str(tmp_path)}):
            # Initialize with PathManager (production pattern)
            path_manager = PathManager()
            path_manager.ensure_directories()

            storage_path = path_manager.data_dir / "preferences"
            pref_store = PreferenceStore(storage_path=storage_path)

            # Add and save preferences
            pref_store.add_preference(
                path=Path("/home/user/Documents"),
                preference_data={
                    "folder_mappings": {"important": "Archive"},
                    "naming_patterns": {"pattern_1": "*.pdf"},
                    "category_overrides": {"override_1": "Documents"},
                },
            )
            pref_store.save_preferences()

            # Simulate restart - load preferences
            pref_store2 = PreferenceStore(storage_path=storage_path)
            pref_store2.load_preferences()

            # Verify preferences were persisted
            dir_prefs = pref_store2.list_directory_preferences()
            assert len(dir_prefs) > 0
