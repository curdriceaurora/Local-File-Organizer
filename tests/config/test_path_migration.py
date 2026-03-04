"""Tests for path migration: legacy path detection and migration to canonical XDG structure."""

from __future__ import annotations

from pathlib import Path

import pytest

from file_organizer.config.path_migration import PathMigrator, detect_legacy_paths


@pytest.mark.unit
class TestDetectLegacyPaths:
    """Tests for detect_legacy_paths function."""

    def test_detect_no_legacy_paths(self, tmp_path: Path) -> None:
        """Test detection when no legacy paths exist."""
        home = tmp_path / "home"
        config_home = tmp_path / "config"
        data_home = tmp_path / "data"

        home.mkdir()
        config_home.mkdir()
        data_home.mkdir()

        legacy = detect_legacy_paths(home, config_home, data_home)

        assert legacy == []

    def test_detect_home_dot_file_organizer(self, tmp_path: Path) -> None:
        """Test detecting ~/.file-organizer legacy path."""
        home = tmp_path / "home"
        config_home = tmp_path / "config"
        data_home = tmp_path / "data"

        home.mkdir()
        config_home.mkdir()
        data_home.mkdir()

        # Create legacy path
        legacy_dir = home / ".file-organizer"
        legacy_dir.mkdir()

        detected = detect_legacy_paths(home, config_home, data_home)

        assert legacy_dir in detected

    def test_detect_home_file_underscore(self, tmp_path: Path) -> None:
        """Test detecting ~/.file_organizer legacy path."""
        home = tmp_path / "home"
        config_home = tmp_path / "config"
        data_home = tmp_path / "data"

        home.mkdir()
        config_home.mkdir()
        data_home.mkdir()

        # Create legacy path with underscore
        legacy_dir = home / ".file_organizer"
        legacy_dir.mkdir()

        detected = detect_legacy_paths(home, config_home, data_home)

        assert legacy_dir in detected

    def test_detect_config_home_variant(self, tmp_path: Path) -> None:
        """Test detecting ~/.config/file-organizer legacy path."""
        home = tmp_path / "home"
        config_home = tmp_path / "config"
        data_home = tmp_path / "data"

        home.mkdir()
        config_home.mkdir()
        data_home.mkdir()

        # Create legacy path in config_home
        legacy_dir = config_home / "file-organizer"
        legacy_dir.mkdir()

        detected = detect_legacy_paths(home, config_home, data_home)

        assert legacy_dir in detected

    def test_detect_multiple_legacy_paths(self, tmp_path: Path) -> None:
        """Test detecting multiple legacy paths."""
        home = tmp_path / "home"
        config_home = tmp_path / "config"
        data_home = tmp_path / "data"

        home.mkdir()
        config_home.mkdir()
        data_home.mkdir()

        # Create multiple legacy paths
        legacy1 = home / ".file-organizer"
        legacy1.mkdir()

        legacy2 = home / ".file_organizer"
        legacy2.mkdir()

        legacy3 = config_home / "file-organizer"
        legacy3.mkdir()

        detected = detect_legacy_paths(home, config_home, data_home)

        assert len(detected) == 3
        assert legacy1 in detected
        assert legacy2 in detected
        assert legacy3 in detected

    def test_detect_ignores_files(self, tmp_path: Path) -> None:
        """Test that detection ignores files (only directories)."""
        home = tmp_path / "home"
        config_home = tmp_path / "config"
        data_home = tmp_path / "data"

        home.mkdir()
        config_home.mkdir()
        data_home.mkdir()

        # Create file instead of directory
        (home / ".file-organizer").write_text("content")

        detected = detect_legacy_paths(home, config_home, data_home)

        # Should not detect files
        assert len(detected) == 0

    def test_detect_ignores_nonexistent(self, tmp_path: Path) -> None:
        """Test that detection ignores nonexistent paths."""
        home = tmp_path / "home"
        config_home = tmp_path / "config"
        data_home = tmp_path / "data"

        home.mkdir()
        config_home.mkdir()
        data_home.mkdir()

        # Don't create any legacy paths

        detected = detect_legacy_paths(home, config_home, data_home)

        assert detected == []


@pytest.mark.unit
class TestPathMigratorInit:
    """Tests for PathMigrator initialization."""

    def test_create_migrator(self, tmp_path: Path) -> None:
        """Test creating PathMigrator."""
        legacy = tmp_path / "legacy"
        canonical = tmp_path / "canonical"

        migrator = PathMigrator(legacy, canonical)

        assert migrator.legacy_path == legacy
        assert migrator.canonical_path == canonical
        assert migrator.backup_path is None
        assert migrator.migration_log == {}

    def test_migrator_paths_stored(self, tmp_path: Path) -> None:
        """Test that migrator stores paths correctly."""
        legacy = tmp_path / "legacy_path"
        canonical = tmp_path / "canonical_path"

        migrator = PathMigrator(legacy, canonical)

        assert migrator.legacy_path == legacy
        assert migrator.canonical_path == canonical


@pytest.mark.unit
class TestPathMigratorBackup:
    """Tests for PathMigrator.backup_legacy_path() method."""

    def test_backup_creates_directory(self, tmp_path: Path) -> None:
        """Test that backup creates backup directory."""
        legacy = tmp_path / "legacy"
        legacy.mkdir()
        canonical = tmp_path / "canonical"

        migrator = PathMigrator(legacy, canonical)
        backup = migrator.backup_legacy_path()

        assert backup.exists()
        assert backup.is_dir()

    def test_backup_path_stored(self, tmp_path: Path) -> None:
        """Test that backup path is stored in migrator."""
        legacy = tmp_path / "legacy"
        legacy.mkdir()
        canonical = tmp_path / "canonical"

        migrator = PathMigrator(legacy, canonical)
        backup = migrator.backup_legacy_path()

        assert migrator.backup_path == backup

    def test_backup_copies_files(self, tmp_path: Path) -> None:
        """Test that backup copies all files from legacy."""
        legacy = tmp_path / "legacy"
        legacy.mkdir()

        # Create test files
        (legacy / "file1.txt").write_text("content1")
        (legacy / "file2.txt").write_text("content2")
        subdir = legacy / "subdir"
        subdir.mkdir()
        (subdir / "file3.txt").write_text("content3")

        canonical = tmp_path / "canonical"

        migrator = PathMigrator(legacy, canonical)
        backup = migrator.backup_legacy_path()

        # Verify backup contains all files
        assert (backup / "file1.txt").exists()
        assert (backup / "file2.txt").exists()
        assert (backup / "subdir" / "file3.txt").exists()

    def test_backup_preserves_structure(self, tmp_path: Path) -> None:
        """Test that backup preserves directory structure."""
        legacy = tmp_path / "legacy"
        legacy.mkdir()

        # Create nested structure
        (legacy / "a" / "b" / "c").mkdir(parents=True)
        (legacy / "a" / "b" / "c" / "file.txt").write_text("content")

        canonical = tmp_path / "canonical"

        migrator = PathMigrator(legacy, canonical)
        backup = migrator.backup_legacy_path()

        # Verify structure is preserved
        assert (backup / "a" / "b" / "c" / "file.txt").exists()

    def test_backup_timestamp_unique(self, tmp_path: Path) -> None:
        """Test that backup timestamps are unique."""
        legacy = tmp_path / "legacy"
        legacy.mkdir()
        canonical = tmp_path / "canonical"

        migrator1 = PathMigrator(legacy, canonical)
        backup1 = migrator1.backup_legacy_path()

        migrator2 = PathMigrator(legacy, canonical)
        backup2 = migrator2.backup_legacy_path()

        # Backup paths should be different due to timestamps
        assert backup1 != backup2


@pytest.mark.unit
class TestPathMigratorMigrate:
    """Tests for PathMigrator.migrate() method."""

    def test_migrate_copies_files(self, tmp_path: Path) -> None:
        """Test that migrate copies files from legacy to canonical."""
        legacy = tmp_path / "legacy"
        legacy.mkdir()
        (legacy / "file1.txt").write_text("content1")
        (legacy / "file2.txt").write_text("content2")

        canonical = tmp_path / "canonical"

        migrator = PathMigrator(legacy, canonical)
        migrator.migrate()

        # Verify files are in canonical location
        assert (canonical / "file1.txt").exists()
        assert (canonical / "file2.txt").exists()
        assert (canonical / "file1.txt").read_text() == "content1"

    def test_migrate_creates_canonical_dir(self, tmp_path: Path) -> None:
        """Test that migrate creates canonical directory."""
        legacy = tmp_path / "legacy"
        legacy.mkdir()
        (legacy / "file.txt").write_text("content")

        canonical = tmp_path / "canonical"
        assert not canonical.exists()

        migrator = PathMigrator(legacy, canonical)
        migrator.migrate()

        assert canonical.exists()
        assert canonical.is_dir()

    def test_migrate_handles_nested_structure(self, tmp_path: Path) -> None:
        """Test that migrate handles nested directory structure."""
        legacy = tmp_path / "legacy"
        legacy.mkdir()
        (legacy / "a" / "b").mkdir(parents=True)
        (legacy / "a" / "b" / "file.txt").write_text("content")

        canonical = tmp_path / "canonical"

        migrator = PathMigrator(legacy, canonical)
        migrator.migrate()

        # Verify nested structure is preserved
        assert (canonical / "a" / "b" / "file.txt").exists()

    def test_migrate_nonexistent_legacy(self, tmp_path: Path) -> None:
        """Test that migrate handles nonexistent legacy path."""
        legacy = tmp_path / "nonexistent"
        canonical = tmp_path / "canonical"

        migrator = PathMigrator(legacy, canonical)

        # Should not raise
        migrator.migrate()

    def test_migrate_preserves_file_content(self, tmp_path: Path) -> None:
        """Test that migrate preserves file content."""
        legacy = tmp_path / "legacy"
        legacy.mkdir()

        content = "Test file content with special characters: !@#$%"
        (legacy / "test.txt").write_text(content)

        canonical = tmp_path / "canonical"

        migrator = PathMigrator(legacy, canonical)
        migrator.migrate()

        # Verify content is preserved
        assert (canonical / "test.txt").read_text() == content


@pytest.mark.unit
class TestPathMigratorLogging:
    """Tests for PathMigrator logging functionality."""

    def test_create_migration_log(self, tmp_path: Path) -> None:
        """Test creating migration log."""
        legacy = tmp_path / "legacy"
        canonical = tmp_path / "canonical"

        migrator = PathMigrator(legacy, canonical)
        log = migrator.create_migration_log()

        assert "timestamp" in log
        assert "from" in log
        assert "to" in log
        assert "status" in log

    def test_migration_log_contains_paths(self, tmp_path: Path) -> None:
        """Test that migration log contains correct paths."""
        legacy = tmp_path / "legacy"
        canonical = tmp_path / "canonical"

        migrator = PathMigrator(legacy, canonical)
        log = migrator.create_migration_log()

        assert log["from"] == str(legacy)
        assert log["to"] == str(canonical)

    def test_migration_log_status_pending(self, tmp_path: Path) -> None:
        """Test that migration log status is pending."""
        legacy = tmp_path / "legacy"
        canonical = tmp_path / "canonical"

        migrator = PathMigrator(legacy, canonical)
        log = migrator.create_migration_log()

        assert log["status"] == "pending"

    def test_migration_log_with_backup(self, tmp_path: Path) -> None:
        """Test migration log includes backup path."""
        legacy = tmp_path / "legacy"
        legacy.mkdir()
        canonical = tmp_path / "canonical"

        migrator = PathMigrator(legacy, canonical)
        migrator.backup_legacy_path()
        log = migrator.create_migration_log()

        assert "backup" in log
        assert log["backup"] is not None


@pytest.mark.unit
class TestPathMigratorFinalize:
    """Tests for PathMigrator.finalize_migration() method."""

    def test_finalize_does_not_raise(self, tmp_path: Path) -> None:
        """Test that finalize doesn't raise errors."""
        legacy = tmp_path / "legacy"
        canonical = tmp_path / "canonical"

        migrator = PathMigrator(legacy, canonical)

        # Should not raise
        migrator.finalize_migration()

    def test_finalize_callable(self, tmp_path: Path) -> None:
        """Test that finalize is callable."""
        legacy = tmp_path / "legacy"
        canonical = tmp_path / "canonical"

        migrator = PathMigrator(legacy, canonical)

        assert callable(migrator.finalize_migration)
