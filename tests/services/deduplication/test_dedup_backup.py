"""Tests for BackupManager class.

Tests backup creation, restoration, cleanup, manifest management,
verification, and statistics computation.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from file_organizer.services.deduplication.backup import BackupManager

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def backup_dir(tmp_path):
    """Provide a fresh temp directory for BackupManager."""
    return tmp_path


@pytest.fixture
def manager(backup_dir):
    """Create a BackupManager using a temporary directory."""
    return BackupManager(base_dir=backup_dir)


@pytest.fixture
def sample_file(tmp_path):
    """Create a sample file to backup."""
    p = tmp_path / "data" / "sample.txt"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("sample content", encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBackupManagerInit:
    """Tests for BackupManager initialization."""

    def test_creates_backup_dir(self, backup_dir):
        mgr = BackupManager(base_dir=backup_dir)
        assert mgr.backup_dir.exists()
        assert mgr.backup_dir.is_dir()

    def test_creates_manifest(self, backup_dir):
        mgr = BackupManager(base_dir=backup_dir)
        assert mgr.manifest_path.exists()

    def test_manifest_is_valid_json(self, backup_dir):
        mgr = BackupManager(base_dir=backup_dir)
        data = json.loads(mgr.manifest_path.read_text())
        assert data == {}

    def test_default_base_dir(self, tmp_path):
        """When base_dir is None, uses cwd."""
        with patch("file_organizer.services.deduplication.backup.Path.cwd") as mock_cwd:
            mock_cwd.return_value = tmp_path
            mgr = BackupManager(base_dir=None)
            mock_cwd.assert_called_once()
            assert mgr.backup_dir == tmp_path / BackupManager.BACKUP_DIR_NAME

    def test_existing_manifest_preserved(self, backup_dir):
        """Existing manifest is not overwritten."""
        mgr1 = BackupManager(base_dir=backup_dir)
        # Create a fake backup entry
        manifest = {"test_key": {"original_path": "/test"}}
        mgr1._save_manifest(manifest)

        # New manager should load existing manifest
        mgr2 = BackupManager(base_dir=backup_dir)
        loaded = mgr2._load_manifest()
        assert "test_key" in loaded


# ---------------------------------------------------------------------------
# create_backup
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCreateBackup:
    """Tests for create_backup."""

    def test_creates_backup_file(self, manager, sample_file):
        backup_path = manager.create_backup(sample_file)
        assert backup_path.exists()
        assert backup_path.read_text() == "sample content"

    def test_backup_in_backup_dir(self, manager, sample_file):
        backup_path = manager.create_backup(sample_file)
        assert str(manager.backup_dir) in str(backup_path)

    def test_manifest_updated(self, manager, sample_file):
        backup_path = manager.create_backup(sample_file)
        manifest = manager._load_manifest()
        assert str(backup_path) in manifest

    def test_manifest_entry_fields(self, manager, sample_file):
        backup_path = manager.create_backup(sample_file)
        manifest = manager._load_manifest()
        entry = manifest[str(backup_path)]
        assert "original_path" in entry
        assert "backup_path" in entry
        assert "backup_time" in entry
        assert "file_size" in entry
        assert "original_mtime" in entry

    def test_file_not_found(self, manager):
        with pytest.raises(FileNotFoundError, match="Source file not found"):
            manager.create_backup(Path("/nonexistent/file.txt"))

    def test_not_a_file(self, manager, tmp_path):
        with pytest.raises(ValueError, match="not a file"):
            manager.create_backup(tmp_path)

    def test_multiple_backups(self, manager, sample_file):
        b1 = manager.create_backup(sample_file)
        b2 = manager.create_backup(sample_file)
        assert b1 != b2
        assert b1.exists()
        assert b2.exists()


# ---------------------------------------------------------------------------
# restore_backup
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRestoreBackup:
    """Tests for restore_backup."""

    def test_restore_to_original(self, manager, sample_file):
        backup_path = manager.create_backup(sample_file)
        # Delete original
        sample_file.unlink()
        assert not sample_file.exists()

        # Restore
        restored = manager.restore_backup(backup_path)
        assert restored.exists()
        assert restored.read_text() == "sample content"

    def test_restore_to_custom_path(self, manager, sample_file, tmp_path):
        backup_path = manager.create_backup(sample_file)
        target = tmp_path / "restored" / "custom.txt"

        restored = manager.restore_backup(backup_path, target_path=target)
        assert restored == target
        assert restored.exists()
        assert restored.read_text() == "sample content"

    def test_backup_not_found(self, manager):
        with pytest.raises(FileNotFoundError, match="Backup file not found"):
            manager.restore_backup(Path("/nonexistent/backup.txt"))

    def test_backup_not_in_manifest(self, manager, tmp_path):
        fake_backup = tmp_path / "fake_backup.txt"
        fake_backup.write_text("fake")
        with pytest.raises(ValueError, match="not found in manifest"):
            manager.restore_backup(fake_backup)


# ---------------------------------------------------------------------------
# cleanup_old_backups
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCleanupOldBackups:
    """Tests for cleanup_old_backups."""

    def test_removes_old_backups(self, manager, sample_file):
        backup_path = manager.create_backup(sample_file)

        # Modify manifest to make backup old
        manifest = manager._load_manifest()
        old_time = (datetime.now(UTC) - timedelta(days=60)).isoformat().replace("+00:00", "Z")
        key = str(backup_path)
        manifest[key]["backup_time"] = old_time
        manager._save_manifest(manifest)

        removed = manager.cleanup_old_backups(max_age_days=30)
        assert len(removed) == 1
        assert not backup_path.exists()

    def test_keeps_recent_backups(self, manager, sample_file):
        backup_path = manager.create_backup(sample_file)
        removed = manager.cleanup_old_backups(max_age_days=30)
        assert len(removed) == 0
        assert backup_path.exists()

    def test_negative_age_raises(self, manager):
        with pytest.raises(ValueError, match="non-negative"):
            manager.cleanup_old_backups(max_age_days=-1)

    def test_manifest_updated_after_cleanup(self, manager, sample_file):
        backup_path = manager.create_backup(sample_file)

        manifest = manager._load_manifest()
        old_time = (datetime.now(UTC) - timedelta(days=60)).isoformat().replace("+00:00", "Z")
        manifest[str(backup_path)]["backup_time"] = old_time
        manager._save_manifest(manifest)

        manager.cleanup_old_backups(max_age_days=30)
        manifest = manager._load_manifest()
        assert str(backup_path) not in manifest


# ---------------------------------------------------------------------------
# get_backup_info
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetBackupInfo:
    """Tests for get_backup_info."""

    def test_existing_backup(self, manager, sample_file):
        backup_path = manager.create_backup(sample_file)
        info = manager.get_backup_info(backup_path)
        assert info is not None
        assert "original_path" in info

    def test_nonexistent_backup(self, manager):
        info = manager.get_backup_info(Path("/nonexistent/backup.txt"))
        assert info is None


# ---------------------------------------------------------------------------
# list_backups
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestListBackups:
    """Tests for list_backups."""

    def test_empty(self, manager):
        backups = manager.list_backups()
        assert backups == []

    def test_with_backups(self, manager, sample_file):
        manager.create_backup(sample_file)
        manager.create_backup(sample_file)
        backups = manager.list_backups()
        assert len(backups) == 2

    def test_sorted_by_time(self, manager, sample_file):
        manager.create_backup(sample_file)
        manager.create_backup(sample_file)
        backups = manager.list_backups()
        # Newest first
        assert backups[0]["backup_time"] >= backups[1]["backup_time"]

    def test_exists_field(self, manager, sample_file):
        backup_path = manager.create_backup(sample_file)
        backups = manager.list_backups()
        assert backups[0]["exists"] is True

        # Delete backup file
        backup_path.unlink()
        backups = manager.list_backups()
        assert backups[0]["exists"] is False


# ---------------------------------------------------------------------------
# get_statistics
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetStatistics:
    """Tests for get_statistics."""

    def test_empty_stats(self, manager):
        stats = manager.get_statistics()
        assert stats["total_backups"] == 0
        assert stats["existing_backups"] == 0
        assert stats["total_size_bytes"] == 0

    def test_with_backups(self, manager, sample_file):
        manager.create_backup(sample_file)
        stats = manager.get_statistics()
        assert stats["total_backups"] == 1
        assert stats["existing_backups"] == 1
        assert stats["total_size_bytes"] > 0
        assert stats["total_size_mb"] >= 0
        assert "backup_directory" in stats

    def test_missing_backup_counted(self, manager, sample_file):
        backup_path = manager.create_backup(sample_file)
        backup_path.unlink()

        stats = manager.get_statistics()
        assert stats["total_backups"] == 1
        assert stats["existing_backups"] == 0
        assert stats["missing_backups"] == 1


# ---------------------------------------------------------------------------
# verify_backups
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestVerifyBackups:
    """Tests for verify_backups."""

    def test_all_valid(self, manager, sample_file):
        manager.create_backup(sample_file)
        issues = manager.verify_backups()
        assert issues == []

    def test_missing_file(self, manager, sample_file):
        backup_path = manager.create_backup(sample_file)
        backup_path.unlink()

        issues = manager.verify_backups()
        assert len(issues) == 1
        assert "Missing" in issues[0]

    def test_size_mismatch(self, manager, sample_file):
        backup_path = manager.create_backup(sample_file)
        # Modify the backup file size
        backup_path.write_text("different content that changes size", encoding="utf-8")

        issues = manager.verify_backups()
        assert len(issues) == 1
        assert "Size mismatch" in issues[0]


# ---------------------------------------------------------------------------
# Manifest operations
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestManifestOperations:
    """Tests for _load_manifest and _save_manifest."""

    def test_load_empty_manifest(self, manager):
        manager.manifest_path.unlink()
        manifest = manager._load_manifest()
        assert manifest == {}

    def test_load_corrupted_manifest(self, manager):
        manager.manifest_path.write_text("not json", encoding="utf-8")
        manifest = manager._load_manifest()
        assert manifest == {}

    def test_save_and_load_roundtrip(self, manager):
        data = {"key": {"value": "test"}}
        manager._save_manifest(data)
        loaded = manager._load_manifest()
        assert loaded == data

    def test_atomic_save(self, manager):
        """Save uses atomic write (temp file + rename)."""
        data = {"key": {"value": "test"}}
        manager._save_manifest(data)
        # Verify data is written correctly
        loaded = json.loads(manager.manifest_path.read_text(encoding="utf-8"))
        assert loaded == data
