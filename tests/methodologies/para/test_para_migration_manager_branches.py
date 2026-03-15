"""Tests for PARA migration_manager uncovered branches.

Targets: analyze_source failure path, execute_migration error/skip paths,
_create_backup edge cases, rollback, list_backups, verify_backup,
generate_preview with >20 files.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.methodologies.para.categories import PARACategory
from file_organizer.methodologies.para.migration_manager import (
    BackupIntegrityError,
    MigrationFile,
    MigrationPlan,
    PARAMigrationManager,
    RollbackError,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def manager(tmp_path: Path) -> PARAMigrationManager:
    """Create a migration manager with mocked path manager."""
    with patch("file_organizer.methodologies.para.migration_manager.PathManager") as pm_cls:
        pm = MagicMock()
        pm.data_dir = tmp_path / "data"
        pm.data_dir.mkdir(parents=True, exist_ok=True)
        pm_cls.return_value = pm
        mgr = PARAMigrationManager()
    return mgr


class TestAnalyzeSource:
    """Cover analyze_source edge cases — lines 120, 200-202."""

    def test_analyze_source_categorize_failure(
        self, manager: PARAMigrationManager, tmp_path: Path
    ) -> None:
        """Files that fail categorization are skipped (line 200-202)."""
        src = tmp_path / "source"
        src.mkdir()
        (src / "file.txt").write_text("hello")

        manager.heuristic_engine.evaluate = MagicMock(side_effect=RuntimeError("eval fail"))
        plan = manager.analyze_source(src, tmp_path / "target")
        assert plan.total_count == 0

    def test_analyze_source_with_extension_filter(
        self, manager: PARAMigrationManager, tmp_path: Path
    ) -> None:
        """Extension filter skips non-matching files (line 164)."""
        src = tmp_path / "source"
        src.mkdir()
        (src / "a.txt").write_text("text")
        (src / "b.pdf").write_text("pdf")
        plan = manager.analyze_source(src, tmp_path / "target", file_extensions=[".txt"])
        # Only .txt files should be analyzed
        for mf in plan.files:
            assert mf.source_path.suffix == ".txt"


class TestExecuteMigration:
    """Cover execute_migration branches — lines 284-286, 340-341, 350-351."""

    def test_execute_migration_skip_existing_target(
        self, manager: PARAMigrationManager, tmp_path: Path
    ) -> None:
        """Target already exists => file skipped (line 250-253)."""
        target_path = tmp_path / "target" / "file.txt"
        target_path.parent.mkdir(parents=True)
        target_path.write_text("existing")

        plan = MigrationPlan(
            files=[
                MigrationFile(
                    source_path=tmp_path / "source.txt",
                    target_category=PARACategory.PROJECT,
                    target_path=target_path,
                    confidence=0.9,
                )
            ],
            total_count=1,
            by_category={PARACategory.PROJECT: 1},
            estimated_size=100,
            created_at=datetime.now(UTC),
        )

        report = manager.execute_migration(plan, dry_run=False, create_backup=False)
        assert len(report.skipped) == 1

    def test_execute_migration_move_failure(
        self, manager: PARAMigrationManager, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """File that fails to move is recorded as failed (lines 284-286)."""
        src = tmp_path / "source.txt"
        src.write_text("hello")
        bad_target = tmp_path / "target" / "file.txt"

        import shutil

        def _raise_permission(*_a: object, **_k: object) -> None:
            raise PermissionError("injected move failure")

        monkeypatch.setattr(shutil, "move", _raise_permission)

        plan = MigrationPlan(
            files=[
                MigrationFile(
                    source_path=src,
                    target_category=PARACategory.RESOURCE,
                    target_path=bad_target,
                    confidence=0.8,
                )
            ],
            total_count=1,
            by_category={PARACategory.RESOURCE: 1},
            estimated_size=5,
            created_at=datetime.now(UTC),
        )

        report = manager.execute_migration(plan, dry_run=False, create_backup=False)
        assert len(report.failed) == 1
        assert report.success is False


class TestRollback:
    """Cover rollback branches — lines 374-376, 417, 425-430, 457, 494, 501-503, 506."""

    def test_rollback_missing_backup_dir(self, manager: PARAMigrationManager) -> None:
        """Rollback raises when backup dir doesn't exist."""
        with pytest.raises(RollbackError, match="not found"):
            manager.rollback("nonexistent_backup")

    def test_rollback_missing_manifest(self, manager: PARAMigrationManager) -> None:
        """Rollback raises when manifest is missing."""
        backup_dir = manager.backup_root / "bad_backup"
        backup_dir.mkdir(parents=True)
        with pytest.raises(RollbackError, match="manifest not found"):
            manager.rollback("bad_backup")

    def test_rollback_restore_failure(
        self, manager: PARAMigrationManager, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Rollback with restore failure raises RollbackError."""
        import shutil

        backup_dir = manager.backup_root / "test_backup"
        backup_dir.mkdir(parents=True)

        # Create a backup file
        backup_file = backup_dir / "file.txt"
        backup_file.write_text("backup content")

        # Use a real tmp_path target so mkdir succeeds, but monkeypatch shutil.copy2
        # to simulate a failure deterministically on all platforms.
        restore_target = str(tmp_path / "restore" / "path.txt")

        def _raise_permission(*_a: object, **_k: object) -> None:
            raise PermissionError("injected copy failure")

        monkeypatch.setattr(shutil, "copy2", _raise_permission)

        file_hash = PARAMigrationManager._calculate_file_hash(backup_file)
        manifest_data = {
            "backup_id": "test_backup",
            "migration_id": "migration_1",
            "created_at": "2025-01-01T00:00:00Z",
            "files_backed_up": 1,
            "total_size": 14,
            "checksum": PARAMigrationManager._calculate_manifest_checksum(
                [
                    {
                        "original_path": restore_target,
                        "hash": file_hash,
                        "backup_path": str(backup_file),
                    }
                ]
            ),
            "source_root": str(tmp_path),
            "status": "created",
            "file_entries": [
                {
                    "original_path": restore_target,
                    "backup_path": str(backup_file),
                    "size": 14,
                    "hash": file_hash,
                    "category": "project",
                    "confidence": 0.9,
                }
            ],
        }

        manifest_file = backup_dir / "manifest.json"
        with open(manifest_file, "w") as f:
            json.dump(manifest_data, f)

        with pytest.raises(RollbackError):
            manager.rollback("test_backup")


class TestListBackups:
    """Cover list_backups — lines 535, 539, 547-548."""

    def test_list_backups_empty(self, manager: PARAMigrationManager) -> None:
        result = manager.list_backups()
        assert result == []

    def test_list_backups_with_valid_manifests(self, manager: PARAMigrationManager) -> None:
        backup_dir = manager.backup_root / "backup_1"
        backup_dir.mkdir(parents=True)
        manifest = {"backup_id": "backup_1", "status": "created"}
        with open(backup_dir / "manifest.json", "w") as f:
            json.dump(manifest, f)

        result = manager.list_backups()
        assert len(result) == 1
        assert result[0]["backup_id"] == "backup_1"

    def test_list_backups_skips_non_dirs(self, manager: PARAMigrationManager) -> None:
        """Files in backup root are skipped (line 539)."""
        (manager.backup_root / "stray_file.txt").write_text("not a backup")
        result = manager.list_backups()
        assert result == []

    def test_list_backups_bad_manifest(self, manager: PARAMigrationManager) -> None:
        """Corrupted manifest is skipped (lines 547-548)."""
        backup_dir = manager.backup_root / "bad_backup"
        backup_dir.mkdir(parents=True)
        (backup_dir / "manifest.json").write_text("not json{{{")
        result = manager.list_backups()
        assert result == []


class TestVerifyBackup:
    """Cover verify_backup — lines 566, 570, 601, 607."""

    def test_verify_backup_missing_id(self, manager: PARAMigrationManager) -> None:
        with pytest.raises(BackupIntegrityError, match="not found"):
            manager.verify_backup("nonexistent")

    def test_verify_backup_missing_manifest(self, manager: PARAMigrationManager) -> None:
        backup_dir = manager.backup_root / "no_manifest"
        backup_dir.mkdir(parents=True)
        with pytest.raises(BackupIntegrityError, match="manifest not found"):
            manager.verify_backup("no_manifest")

    def test_verify_backup_checksum_mismatch(self, manager: PARAMigrationManager) -> None:
        """Checksum mismatch raises integrity error (line 601, 607)."""
        backup_dir = manager.backup_root / "bad_checksum"
        backup_dir.mkdir(parents=True)
        manifest = {
            "checksum": "wrong",
            "file_entries": [],
        }
        with open(backup_dir / "manifest.json", "w") as f:
            json.dump(manifest, f)
        with pytest.raises(BackupIntegrityError):
            manager.verify_backup("bad_checksum")


class TestGeneratePreview:
    """Cover generate_preview — lines 716."""

    def test_generate_preview_more_than_20(
        self, manager: PARAMigrationManager, tmp_path: Path
    ) -> None:
        files = [
            MigrationFile(
                source_path=Path(f"/src/file{i}.txt"),
                target_category=PARACategory.RESOURCE,
                target_path=Path(f"/dst/file{i}.txt"),
                confidence=0.7,
            )
            for i in range(25)
        ]
        plan = MigrationPlan(
            files=files,
            total_count=25,
            by_category={PARACategory.RESOURCE: 25},
            estimated_size=1000,
            created_at=datetime.now(UTC),
        )
        preview = manager.generate_preview(plan)
        assert "... and 5 more files" in preview

    def test_generate_preview_zero_files(self, manager: PARAMigrationManager) -> None:
        plan = MigrationPlan(
            files=[],
            total_count=0,
            by_category={PARACategory.PROJECT: 0},
            estimated_size=0,
            created_at=datetime.now(UTC),
        )
        preview = manager.generate_preview(plan)
        assert "Total files: 0" in preview
