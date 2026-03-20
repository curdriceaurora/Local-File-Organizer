"""Integration tests for deduplication backup service.

Covers:
  - services/deduplication/backup.py — BackupManager
"""

from __future__ import annotations

from pathlib import Path

import pytest

from file_organizer.services.deduplication.backup import BackupManager

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# BackupManager — fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def backup_mgr(tmp_path: Path) -> BackupManager:
    return BackupManager(base_dir=tmp_path)


def _make_file(path: Path, content: bytes = b"hello backup") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


# ---------------------------------------------------------------------------
# BackupManager — init
# ---------------------------------------------------------------------------


class TestBackupManagerInit:
    def test_default_init(self) -> None:
        bm = BackupManager()
        assert bm is not None

    def test_custom_base_dir(self, tmp_path: Path) -> None:
        bm = BackupManager(base_dir=tmp_path)
        assert bm is not None

    def test_backup_dir_name_set(self, backup_mgr: BackupManager) -> None:
        assert BackupManager.BACKUP_DIR_NAME is not None
        assert len(BackupManager.BACKUP_DIR_NAME) > 0

    def test_manifest_file_set(self, backup_mgr: BackupManager) -> None:
        assert BackupManager.MANIFEST_FILE is not None


# ---------------------------------------------------------------------------
# BackupManager — create_backup
# ---------------------------------------------------------------------------


class TestBackupManagerCreate:
    def test_create_backup_returns_path(self, backup_mgr: BackupManager, tmp_path: Path) -> None:
        f = _make_file(tmp_path / "original.txt")
        backup_path = backup_mgr.create_backup(f)
        assert isinstance(backup_path, Path)

    def test_backup_file_exists(self, backup_mgr: BackupManager, tmp_path: Path) -> None:
        f = _make_file(tmp_path / "data.pdf", b"pdf content")
        backup_path = backup_mgr.create_backup(f)
        assert backup_path.exists()

    def test_backup_content_matches(self, backup_mgr: BackupManager, tmp_path: Path) -> None:
        content = b"important data"
        f = _make_file(tmp_path / "important.txt", content)
        backup_path = backup_mgr.create_backup(f)
        assert backup_path.read_bytes() == content

    def test_backup_different_from_original(
        self, backup_mgr: BackupManager, tmp_path: Path
    ) -> None:
        f = _make_file(tmp_path / "file.txt")
        backup_path = backup_mgr.create_backup(f)
        assert backup_path != f

    def test_multiple_backups_of_same_file(self, backup_mgr: BackupManager, tmp_path: Path) -> None:
        f = _make_file(tmp_path / "doc.txt")
        b1 = backup_mgr.create_backup(f)
        f.write_bytes(b"updated content")
        b2 = backup_mgr.create_backup(f)
        # Should create two separate backups
        assert b1.exists()
        assert b2.exists()


# ---------------------------------------------------------------------------
# BackupManager — list_backups
# ---------------------------------------------------------------------------


class TestBackupManagerList:
    def test_list_backups_empty(self, backup_mgr: BackupManager) -> None:
        result = backup_mgr.list_backups()
        assert result == []

    def test_list_backups_after_create(self, backup_mgr: BackupManager, tmp_path: Path) -> None:
        f = _make_file(tmp_path / "file.txt")
        backup_mgr.create_backup(f)
        result = backup_mgr.list_backups()
        assert len(result) >= 1

    def test_list_backups_entries_are_dicts(
        self, backup_mgr: BackupManager, tmp_path: Path
    ) -> None:
        f = _make_file(tmp_path / "file.txt")
        backup_mgr.create_backup(f)
        result = backup_mgr.list_backups()
        for entry in result:
            assert "exists" in entry

    def test_list_multiple_backups(self, backup_mgr: BackupManager, tmp_path: Path) -> None:
        for i in range(3):
            f = _make_file(tmp_path / f"file{i}.txt", f"content {i}".encode())
            backup_mgr.create_backup(f)
        result = backup_mgr.list_backups()
        assert len(result) >= 3


# ---------------------------------------------------------------------------
# BackupManager — get_backup_info
# ---------------------------------------------------------------------------


class TestBackupManagerInfo:
    def test_get_info_for_valid_backup(self, backup_mgr: BackupManager, tmp_path: Path) -> None:
        f = _make_file(tmp_path / "data.txt")
        backup_path = backup_mgr.create_backup(f)
        info = backup_mgr.get_backup_info(backup_path)
        assert info is not None
        assert isinstance(info, dict)

    def test_get_info_nonexistent_returns_none(
        self, backup_mgr: BackupManager, tmp_path: Path
    ) -> None:
        result = backup_mgr.get_backup_info(tmp_path / "nonexistent.bak")
        assert result is None


# ---------------------------------------------------------------------------
# BackupManager — restore_backup
# ---------------------------------------------------------------------------


class TestBackupManagerRestore:
    def test_restore_to_target_path(self, backup_mgr: BackupManager, tmp_path: Path) -> None:
        content = b"restore me"
        f = _make_file(tmp_path / "original.txt", content)
        backup_path = backup_mgr.create_backup(f)

        target = tmp_path / "restored.txt"
        result = backup_mgr.restore_backup(backup_path, target)
        assert result.exists()
        assert result.read_bytes() == content

    def test_restore_to_original_path(self, backup_mgr: BackupManager, tmp_path: Path) -> None:
        f = _make_file(tmp_path / "original.txt", b"original")
        backup_path = backup_mgr.create_backup(f)
        # Overwrite original
        f.write_bytes(b"overwritten")
        # Restore to default (original location)
        result = backup_mgr.restore_backup(backup_path)
        assert result.exists()


# ---------------------------------------------------------------------------
# BackupManager — verify_backups
# ---------------------------------------------------------------------------


class TestBackupManagerVerify:
    def test_verify_empty_returns_list(self, backup_mgr: BackupManager) -> None:
        result = backup_mgr.verify_backups()
        assert result == []

    def test_verify_valid_backups_no_errors(
        self, backup_mgr: BackupManager, tmp_path: Path
    ) -> None:
        f = _make_file(tmp_path / "healthy.txt", b"good data")
        backup_mgr.create_backup(f)
        result = backup_mgr.verify_backups()
        # Healthy backups should produce empty list (no errors)
        assert result == []


# ---------------------------------------------------------------------------
# BackupManager — get_statistics
# ---------------------------------------------------------------------------


class TestBackupManagerStats:
    def test_statistics_empty(self, backup_mgr: BackupManager) -> None:
        stats = backup_mgr.get_statistics()
        assert stats["total_backups"] == 0

    def test_statistics_after_backup(self, backup_mgr: BackupManager, tmp_path: Path) -> None:
        f = _make_file(tmp_path / "data.txt", b"statistics test")
        backup_mgr.create_backup(f)
        stats = backup_mgr.get_statistics()
        assert stats["total_backups"] >= 1


# ---------------------------------------------------------------------------
# BackupManager — cleanup_old_backups
# ---------------------------------------------------------------------------


class TestBackupManagerCleanup:
    def test_cleanup_empty_returns_list(self, backup_mgr: BackupManager) -> None:
        result = backup_mgr.cleanup_old_backups()
        assert result == []

    def test_cleanup_age_zero_removes_all(self, backup_mgr: BackupManager, tmp_path: Path) -> None:
        f = _make_file(tmp_path / "old.txt")
        backup_mgr.create_backup(f)
        removed = backup_mgr.cleanup_old_backups(max_age_days=0)
        assert len(removed) >= 1

    def test_cleanup_large_age_keeps_backups(
        self, backup_mgr: BackupManager, tmp_path: Path
    ) -> None:
        f = _make_file(tmp_path / "recent.txt")
        backup_mgr.create_backup(f)
        removed = backup_mgr.cleanup_old_backups(max_age_days=365)
        # Recent backups should not be removed
        assert len(removed) == 0
