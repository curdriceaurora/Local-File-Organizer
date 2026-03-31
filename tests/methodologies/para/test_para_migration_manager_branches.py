"""Tests for PARA migration_manager uncovered branches.

Targets: analyze_source failure path, execute_migration error/skip paths,
_create_backup edge cases, rollback, list_backups, verify_backup,
generate_preview with >20 files.
"""

from __future__ import annotations

import json
import os
import shutil
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


class TestInitialization:
    """Cover __init__ branches — line 121."""

    def test_init_with_custom_heuristic_engine(self, tmp_path: Path) -> None:
        """Custom heuristic engine is used when provided."""
        with patch("file_organizer.methodologies.para.migration_manager.PathManager") as pm_cls:
            pm = MagicMock()
            pm.data_dir = tmp_path / "data"
            pm.data_dir.mkdir(parents=True, exist_ok=True)
            pm_cls.return_value = pm

            custom_engine = MagicMock()
            mgr = PARAMigrationManager(heuristic_engine=custom_engine)
            assert mgr.heuristic_engine is custom_engine


class TestAnalyzeSourceAdvanced:
    """Cover analyze_source advanced branches — lines 167-170, 180-183, 157."""

    def test_analyze_source_category_none_defaults_to_resource(
        self, manager: PARAMigrationManager, tmp_path: Path
    ) -> None:
        """When category is None, default to RESOURCE (line 167-170)."""
        src = tmp_path / "source"
        src.mkdir()
        (src / "file.txt").write_text("hello")

        result_mock = MagicMock()
        result_mock.recommended_category = None
        result_mock.overall_confidence = 0.5
        result_mock.scores = {}
        manager.heuristic_engine.evaluate = MagicMock(return_value=result_mock)

        plan = manager.analyze_source(src, tmp_path / "target")
        assert plan.total_count == 1
        assert plan.files[0].target_category == PARACategory.RESOURCE

    def test_analyze_source_with_category_reasoning(
        self, manager: PARAMigrationManager, tmp_path: Path
    ) -> None:
        """Category scores provide reasoning signals (line 180-183)."""
        src = tmp_path / "source"
        src.mkdir()
        (src / "file.txt").write_text("hello")

        result_mock = MagicMock()
        result_mock.recommended_category = PARACategory.PROJECT
        result_mock.overall_confidence = 0.9
        category_score = MagicMock()
        category_score.signals = ["signal1", "signal2"]
        result_mock.scores = {PARACategory.PROJECT: category_score}
        manager.heuristic_engine.evaluate = MagicMock(return_value=result_mock)

        plan = manager.analyze_source(src, tmp_path / "target")
        assert plan.total_count == 1
        assert plan.files[0].reasoning == ["signal1", "signal2"]

    def test_analyze_source_skips_directories(
        self, manager: PARAMigrationManager, tmp_path: Path
    ) -> None:
        """Directories are skipped during analysis (line 157)."""
        src = tmp_path / "source"
        src.mkdir()
        (src / "file.txt").write_text("hello")
        (src / "subdir").mkdir()  # Directory should be skipped

        result_mock = MagicMock()
        result_mock.recommended_category = PARACategory.PROJECT
        result_mock.overall_confidence = 0.9
        result_mock.scores = {}
        manager.heuristic_engine.evaluate = MagicMock(return_value=result_mock)

        plan = manager.analyze_source(src, tmp_path / "target")
        # Only 1 file should be in plan (directory skipped)
        assert plan.total_count == 1


class TestExecuteMigrationAdvanced:
    """Cover execute_migration with backup and timestamp preservation."""

    def test_execute_migration_with_backup_creation(
        self, manager: PARAMigrationManager, tmp_path: Path
    ) -> None:
        """Execute migration with backup creation (lines 239-240)."""
        src = tmp_path / "source.txt"
        src.write_text("content")
        target_path = tmp_path / "target" / "file.txt"

        plan = MigrationPlan(
            files=[
                MigrationFile(
                    source_path=src,
                    target_category=PARACategory.PROJECT,
                    target_path=target_path,
                    confidence=0.9,
                )
            ],
            total_count=1,
            by_category={PARACategory.PROJECT: 1},
            estimated_size=7,
            created_at=datetime.now(UTC),
        )

        report = manager.execute_migration(plan, dry_run=False, create_backup=True)
        assert len(report.migrated) == 1
        assert report.success is True
        # Verify backup was created
        backups = manager.list_backups()
        assert len(backups) >= 1

    def test_execute_migration_preserve_timestamps(
        self, manager: PARAMigrationManager, tmp_path: Path
    ) -> None:
        """Preserve file timestamps during migration (lines 256-268)."""
        import time

        src = tmp_path / "source.txt"
        src.write_text("content")

        # Set specific timestamps
        old_atime = time.time() - 10000
        old_mtime = time.time() - 10000
        os.utime(src, (old_atime, old_mtime))

        original_stat = src.stat()
        target_path = tmp_path / "target" / "file.txt"

        plan = MigrationPlan(
            files=[
                MigrationFile(
                    source_path=src,
                    target_category=PARACategory.PROJECT,
                    target_path=target_path,
                    confidence=0.9,
                )
            ],
            total_count=1,
            by_category={PARACategory.PROJECT: 1},
            estimated_size=7,
            created_at=datetime.now(UTC),
        )

        report = manager.execute_migration(
            plan, dry_run=False, create_backup=False, preserve_timestamps=True
        )
        assert report.success is True

        # Verify timestamps were preserved
        target_stat = target_path.stat()
        assert abs(target_stat.st_mtime - original_stat.st_mtime) < 1.0

    def test_execute_migration_dry_run_with_preserve_timestamps(
        self, manager: PARAMigrationManager, tmp_path: Path
    ) -> None:
        """Dry run doesn't preserve timestamps (lines 274-278)."""
        src = tmp_path / "source.txt"
        src.write_text("content")
        target_path = tmp_path / "target" / "file.txt"

        plan = MigrationPlan(
            files=[
                MigrationFile(
                    source_path=src,
                    target_category=PARACategory.PROJECT,
                    target_path=target_path,
                    confidence=0.9,
                )
            ],
            total_count=1,
            by_category={PARACategory.PROJECT: 1},
            estimated_size=7,
            created_at=datetime.now(UTC),
        )

        report = manager.execute_migration(
            plan, dry_run=True, create_backup=False, preserve_timestamps=True
        )
        assert len(report.migrated) == 1
        # Source file still exists in dry run
        assert src.exists()
        # Target doesn't exist in dry run
        assert not target_path.exists()

    def test_execute_migration_without_preserve_timestamps(
        self,
        manager: PARAMigrationManager,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Migration without timestamp preservation (lines 264-270)."""
        src = tmp_path / "source.txt"
        src.write_text("content")
        target_path = tmp_path / "target" / "file.txt"

        plan = MigrationPlan(
            files=[
                MigrationFile(
                    source_path=src,
                    target_category=PARACategory.PROJECT,
                    target_path=target_path,
                    confidence=0.9,
                )
            ],
            total_count=1,
            by_category={PARACategory.PROJECT: 1},
            estimated_size=7,
            created_at=datetime.now(UTC),
        )
        utime_calls: list[tuple[object, object]] = []

        original_utime = os.utime

        def track_utime(path: object, times: object) -> None:
            utime_calls.append((path, times))
            original_utime(path, times)

        monkeypatch.setattr(
            "file_organizer.methodologies.para.migration_manager.os.utime",
            track_utime,
        )

        report = manager.execute_migration(
            plan, dry_run=False, create_backup=False, preserve_timestamps=False
        )
        assert report.success is True
        assert len(report.migrated) == 1
        assert target_path.exists()
        assert utime_calls == []


class TestRollbackSuccessful:
    """Cover successful rollback — lines 482-518, 524."""

    def test_rollback_successful_completion(
        self, manager: PARAMigrationManager, tmp_path: Path
    ) -> None:
        """Successful rollback restores files and updates manifest."""
        # Create a migration and backup
        src = tmp_path / "source.txt"
        src.write_text("original content")
        target_path = tmp_path / "target" / "file.txt"

        plan = MigrationPlan(
            files=[
                MigrationFile(
                    source_path=src,
                    target_category=PARACategory.PROJECT,
                    target_path=target_path,
                    confidence=0.9,
                )
            ],
            total_count=1,
            by_category={PARACategory.PROJECT: 1},
            estimated_size=16,
            created_at=datetime.now(UTC),
        )

        # Execute with backup
        report = manager.execute_migration(plan, dry_run=False, create_backup=True)
        assert report.success is True

        # Get backup ID
        backups = manager.list_backups()
        assert len(backups) >= 1
        backup_id = backups[0]["backup_id"]

        # Modify the migrated file
        target_path.write_text("modified content")

        # Rollback
        result = manager.rollback(backup_id)
        assert result is True

        # Verify original file was restored
        assert src.exists()
        assert src.read_text() == "original content"

        # Verify manifest was updated
        updated_backups = manager.list_backups()
        manifest = next(b for b in updated_backups if b["backup_id"] == backup_id)
        assert manifest["status"] == "restored"
        assert "restored_at" in manifest

    def test_rollback_with_existing_target_backed_up(
        self, manager: PARAMigrationManager, tmp_path: Path
    ) -> None:
        """Rollback backs up existing file at target location (lines 482-487)."""
        backup_dir = manager.backup_root / "test_backup"
        backup_dir.mkdir(parents=True)

        # Create a backup file
        backup_file = backup_dir / "file.txt"
        backup_file.write_text("backup content")

        # Create existing file at restore location
        restore_target = tmp_path / "restore" / "path.txt"
        restore_target.parent.mkdir(parents=True)
        restore_target.write_text("existing migrated content")

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
                        "original_path": str(restore_target),
                        "hash": file_hash,
                        "backup_path": str(backup_file),
                    }
                ]
            ),
            "source_root": str(tmp_path),
            "status": "created",
            "file_entries": [
                {
                    "original_path": str(restore_target),
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

        # Rollback
        result = manager.rollback("test_backup")
        assert result is True

        # Verify the existing file was backed up with .migrated suffix
        migrated_files = list(restore_target.parent.glob(f"*.*.migrated{restore_target.suffix}"))
        assert len(migrated_files) == 1

        # Verify original content was restored
        assert restore_target.read_text() == "backup content"

    def test_rollback_with_hash_mismatch(
        self, manager: PARAMigrationManager, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Rollback raises RollbackError when restored file hash mismatches (line 494)."""
        backup_dir = manager.backup_root / "test_backup"
        backup_dir.mkdir(parents=True)

        backup_file = backup_dir / "file.txt"
        backup_file.write_text("backup content")

        restore_target = tmp_path / "restore" / "path.txt"

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
                        "original_path": str(restore_target),
                        "hash": file_hash,
                        "backup_path": str(backup_file),
                    }
                ]
            ),
            "source_root": str(tmp_path),
            "status": "created",
            "file_entries": [
                {
                    "original_path": str(restore_target),
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

        # Mock _calculate_file_hash to return wrong hash for restored file
        original_hash_fn = PARAMigrationManager._calculate_file_hash
        call_count = [0]

        def _mock_hash(file_path: Path) -> str:
            call_count[0] += 1
            # First call: backup file hash (should be correct)
            # Second call: restored file hash (should be wrong)
            if call_count[0] == 1:
                return original_hash_fn(file_path)
            else:
                return "wrong_hash_after_restore"

        monkeypatch.setattr(PARAMigrationManager, "_calculate_file_hash", staticmethod(_mock_hash))

        with pytest.raises(RollbackError, match="File integrity check failed"):
            manager.rollback("test_backup")

    def test_rollback_generic_exception_handling(
        self, manager: PARAMigrationManager, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Rollback wraps non-RollbackError exceptions (line 524)."""
        backup_dir = manager.backup_root / "test_backup"
        backup_dir.mkdir(parents=True)

        backup_file = backup_dir / "file.txt"
        backup_file.write_text("backup content")

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
                        "original_path": str(tmp_path / "file.txt"),
                        "hash": file_hash,
                        "backup_path": str(backup_file),
                    }
                ]
            ),
            "source_root": str(tmp_path),
            "status": "created",
            "file_entries": [
                {
                    "original_path": str(tmp_path / "file.txt"),
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

        # Inject a non-RollbackError exception during json.load
        def _failing_json_load(*args: object, **kwargs: object) -> object:
            # Raise a ValueError (not RollbackError or BackupIntegrityError)
            raise ValueError("injected JSON parsing error")

        monkeypatch.setattr(json, "load", _failing_json_load)

        with pytest.raises(RollbackError, match="Rollback operation failed"):
            manager.rollback("test_backup")


class TestListBackupsEdgeCases:
    """Cover list_backups edge cases — line 535, 542->537."""

    def test_list_backups_when_backup_root_missing(self, manager: PARAMigrationManager) -> None:
        """list_backups returns empty when backup_root doesn't exist (line 535)."""
        # Remove backup root
        if manager.backup_root.exists():
            shutil.rmtree(manager.backup_root)

        result = manager.list_backups()
        assert result == []

    def test_list_backups_with_directory_no_manifest(self, manager: PARAMigrationManager) -> None:
        """Directory without manifest.json is skipped (line 542->537)."""
        # Create a directory without manifest.json
        empty_dir = manager.backup_root / "empty_backup"
        empty_dir.mkdir(parents=True)

        result = manager.list_backups()
        assert result == []


class TestVerifyBackupEdgeCases:
    """Cover verify_backup exception handling and success — lines 577-578, 601, 607."""

    def test_verify_backup_successful(self, manager: PARAMigrationManager, tmp_path: Path) -> None:
        """Successful verify_backup returns True (lines 577-578)."""
        backup_dir = manager.backup_root / "good_backup"
        backup_dir.mkdir(parents=True)

        # Create a valid backup file
        backup_file = backup_dir / "file.txt"
        backup_file.write_text("backup content")

        file_hash = PARAMigrationManager._calculate_file_hash(backup_file)
        file_entries = [
            {
                "original_path": str(tmp_path / "original.txt"),
                "backup_path": str(backup_file),
                "size": 14,
                "hash": file_hash,
            }
        ]

        manifest = {
            "checksum": PARAMigrationManager._calculate_manifest_checksum(file_entries),
            "file_entries": file_entries,
        }

        with open(backup_dir / "manifest.json", "w") as f:
            json.dump(manifest, f)

        # Should return True for valid backup
        result = manager.verify_backup("good_backup")
        assert result is True

    def test_verify_backup_with_missing_backup_file(self, manager: PARAMigrationManager) -> None:
        """Verify backup fails when backup file is missing (lines 577-578, 642)."""
        backup_dir = manager.backup_root / "incomplete_backup"
        backup_dir.mkdir(parents=True)

        # Create manifest but no actual backup file
        file_entries = [
            {
                "original_path": "/some/path.txt",
                "backup_path": str(backup_dir / "missing.txt"),
                "size": 100,
                "hash": "fakehash123",
            }
        ]

        manifest = {
            "checksum": PARAMigrationManager._calculate_manifest_checksum(file_entries),
            "file_entries": file_entries,
        }

        with open(backup_dir / "manifest.json", "w") as f:
            json.dump(manifest, f)

        with pytest.raises(BackupIntegrityError, match="Backup file missing"):
            manager.verify_backup("incomplete_backup")

    def test_verify_backup_with_file_hash_mismatch(self, manager: PARAMigrationManager) -> None:
        """Verify backup fails when file hash doesn't match (line 648)."""
        backup_dir = manager.backup_root / "bad_hash_backup"
        backup_dir.mkdir(parents=True)

        # Create backup file
        backup_file = backup_dir / "file.txt"
        backup_file.write_text("actual content")

        # Create manifest with wrong hash
        file_entries = [
            {
                "original_path": "/some/path.txt",
                "backup_path": str(backup_file),
                "size": 14,
                "hash": "wrong_hash_value",
            }
        ]

        manifest = {
            "checksum": PARAMigrationManager._calculate_manifest_checksum(file_entries),
            "file_entries": file_entries,
        }

        with open(backup_dir / "manifest.json", "w") as f:
            json.dump(manifest, f)

        with pytest.raises(BackupIntegrityError, match="File hash mismatch"):
            manager.verify_backup("bad_hash_backup")

    def test_verify_backup_with_corrupt_manifest_json(self, manager: PARAMigrationManager) -> None:
        """verify_backup wraps JSON decode errors (lines 577-578)."""
        backup_dir = manager.backup_root / "corrupt_backup"
        backup_dir.mkdir(parents=True)

        # Create corrupted manifest JSON
        manifest_file = backup_dir / "manifest.json"
        manifest_file.write_text("{not valid json}")

        with pytest.raises(BackupIntegrityError, match="Backup integrity check failed"):
            manager.verify_backup("corrupt_backup")


class TestInternalVerifyBackup:
    """Cover _verify_backup method — lines 601, 607."""

    def test_verify_backup_internal_missing_file(
        self, manager: PARAMigrationManager, tmp_path: Path
    ) -> None:
        """_verify_backup raises when backup file is missing (line 601)."""
        from file_organizer.methodologies.para.migration_manager import BackupMetadata

        backup_dir = manager.backup_root / "test_backup"
        backup_dir.mkdir(parents=True)

        # Create metadata with a file that doesn't exist
        metadata = BackupMetadata(
            backup_id="test_backup",
            migration_id="migration_1",
            created_at=datetime.now(UTC),
            files_backed_up=1,
            total_size=100,
            checksum="test_checksum",
            source_root=tmp_path,
            status="created",
            file_entries=[
                {
                    "original_path": str(tmp_path / "original.txt"),
                    "backup_path": str(backup_dir / "missing.txt"),
                    "size": 100,
                    "hash": "fakehash",
                    "category": "project",
                    "confidence": 0.9,
                }
            ],
        )

        with pytest.raises(BackupIntegrityError, match="Backup file missing"):
            manager._verify_backup(backup_dir, metadata)

    def test_verify_backup_internal_hash_mismatch(
        self, manager: PARAMigrationManager, tmp_path: Path
    ) -> None:
        """_verify_backup raises when file hash mismatches (line 607)."""
        from file_organizer.methodologies.para.migration_manager import BackupMetadata

        backup_dir = manager.backup_root / "test_backup"
        backup_dir.mkdir(parents=True)

        # Create a backup file
        backup_file = backup_dir / "file.txt"
        backup_file.write_text("actual content")

        # Create metadata with wrong hash
        metadata = BackupMetadata(
            backup_id="test_backup",
            migration_id="migration_1",
            created_at=datetime.now(UTC),
            files_backed_up=1,
            total_size=14,
            checksum="test_checksum",
            source_root=tmp_path,
            status="created",
            file_entries=[
                {
                    "original_path": str(tmp_path / "original.txt"),
                    "backup_path": str(backup_file),
                    "size": 14,
                    "hash": "wrong_hash_value",
                    "category": "project",
                    "confidence": 0.9,
                }
            ],
        )

        with pytest.raises(BackupIntegrityError, match="File hash mismatch"):
            manager._verify_backup(backup_dir, metadata)


class TestCreateBackupEdgeCases:
    """Cover _create_backup edge cases — lines 336-337, 346-347, 372-374, 417, 425-430."""

    def test_create_backup_with_missing_source_file(
        self, manager: PARAMigrationManager, tmp_path: Path
    ) -> None:
        """Source file missing during backup is skipped (lines 336-337)."""
        missing_file = tmp_path / "missing.txt"

        plan = MigrationPlan(
            files=[
                MigrationFile(
                    source_path=missing_file,
                    target_category=PARACategory.PROJECT,
                    target_path=tmp_path / "target" / "file.txt",
                    confidence=0.9,
                )
            ],
            total_count=1,
            by_category={PARACategory.PROJECT: 1},
            estimated_size=100,
            created_at=datetime.now(UTC),
        )

        # This should not raise an exception, just skip the missing file
        backup_id = manager._create_backup(plan)
        assert backup_id is not None

        # Verify backup was created with no files
        backups = manager.list_backups()
        backup = next(b for b in backups if b["backup_id"] == backup_id)
        assert backup["files_backed_up"] == 0

    def test_create_backup_with_different_source_roots(
        self, manager: PARAMigrationManager, tmp_path: Path
    ) -> None:
        """Files from different paths trigger ValueError fallback (lines 346-347)."""
        # Create files in completely different paths
        src1 = tmp_path / "dir1" / "file1.txt"
        src1.parent.mkdir(parents=True)
        src1.write_text("content1")

        src2 = tmp_path / "dir2" / "subdir" / "file2.txt"
        src2.parent.mkdir(parents=True)
        src2.write_text("content2")

        plan = MigrationPlan(
            files=[
                MigrationFile(
                    source_path=src1,
                    target_category=PARACategory.PROJECT,
                    target_path=tmp_path / "target" / "file1.txt",
                    confidence=0.9,
                ),
                MigrationFile(
                    source_path=src2,
                    target_category=PARACategory.RESOURCE,
                    target_path=tmp_path / "target" / "file2.txt",
                    confidence=0.8,
                ),
            ],
            total_count=2,
            by_category={PARACategory.PROJECT: 1, PARACategory.RESOURCE: 1},
            estimated_size=200,
            created_at=datetime.now(UTC),
        )
        plan.source_root = src1.parent

        backup_id = manager._create_backup(plan)
        assert backup_id is not None

        backups = manager.list_backups()
        backup = next(b for b in backups if b["backup_id"] == backup_id)
        assert backup["files_backed_up"] == 2
        flattened_entry = next(
            entry for entry in backup["file_entries"] if entry["original_path"] == str(src2)
        )
        assert Path(flattened_entry["backup_path"]).name == src2.name

    def test_create_backup_file_copy_failure(
        self, manager: PARAMigrationManager, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Failed file backup is logged and skipped (lines 372-374)."""
        src = tmp_path / "source.txt"
        src.write_text("content")

        import shutil as shutil_module

        original_copy2 = shutil_module.copy2
        call_count = [0]

        def _failing_copy2(src_arg: object, dst_arg: object) -> object:
            call_count[0] += 1
            if call_count[0] == 1:
                # First call fails
                raise PermissionError("injected copy failure")
            return original_copy2(src_arg, dst_arg)

        monkeypatch.setattr(shutil_module, "copy2", _failing_copy2)

        plan = MigrationPlan(
            files=[
                MigrationFile(
                    source_path=src,
                    target_category=PARACategory.PROJECT,
                    target_path=tmp_path / "target" / "file.txt",
                    confidence=0.9,
                )
            ],
            total_count=1,
            by_category={PARACategory.PROJECT: 1},
            estimated_size=7,
            created_at=datetime.now(UTC),
        )

        backup_id = manager._create_backup(plan)
        assert backup_id is not None

        # Backup should be created but with 0 files
        backups = manager.list_backups()
        backup = next(b for b in backups if b["backup_id"] == backup_id)
        assert backup["files_backed_up"] == 0

    def test_create_backup_empty_plan_no_verification(
        self, manager: PARAMigrationManager, tmp_path: Path
    ) -> None:
        """Empty backup plan skips verification (line 417)."""
        plan = MigrationPlan(
            files=[],
            total_count=0,
            by_category={},
            estimated_size=0,
            created_at=datetime.now(UTC),
        )

        backup_id = manager._create_backup(plan)
        assert backup_id is not None

        backups = manager.list_backups()
        backup = next(b for b in backups if b["backup_id"] == backup_id)
        assert backup["files_backed_up"] == 0

    def test_create_backup_failure_cleanup(
        self, manager: PARAMigrationManager, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Backup failure cleans up partial backup directory (lines 425-430)."""
        src = tmp_path / "source.txt"
        src.write_text("content")

        plan = MigrationPlan(
            files=[
                MigrationFile(
                    source_path=src,
                    target_category=PARACategory.PROJECT,
                    target_path=tmp_path / "target" / "file.txt",
                    confidence=0.9,
                )
            ],
            total_count=1,
            by_category={PARACategory.PROJECT: 1},
            estimated_size=7,
            created_at=datetime.now(UTC),
        )

        # Inject failure in manifest writing by mocking open
        original_open = open

        def _failing_open(file_arg: object, *args: object, **kwargs: object) -> object:
            if isinstance(file_arg, Path) and file_arg.name == "manifest.json":
                raise OSError("injected manifest write failure")
            return original_open(file_arg, *args, **kwargs)

        monkeypatch.setattr("builtins.open", _failing_open)

        with pytest.raises(IOError, match="injected manifest write failure"):
            manager._create_backup(plan)

        # Verify backup directory was cleaned up
        backup_dirs = list(manager.backup_root.glob("backup_*"))
        assert backup_dirs == []

    def test_create_backup_cleanup_also_fails(
        self, manager: PARAMigrationManager, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Backup failure where cleanup also fails (lines 428-430)."""
        src = tmp_path / "source.txt"
        src.write_text("content")

        plan = MigrationPlan(
            files=[
                MigrationFile(
                    source_path=src,
                    target_category=PARACategory.PROJECT,
                    target_path=tmp_path / "target" / "file.txt",
                    confidence=0.9,
                )
            ],
            total_count=1,
            by_category={PARACategory.PROJECT: 1},
            estimated_size=7,
            created_at=datetime.now(UTC),
        )

        # Inject failure in both manifest writing and cleanup
        original_open = open

        def _failing_open(file_arg: object, *args: object, **kwargs: object) -> object:
            if isinstance(file_arg, Path) and file_arg.name == "manifest.json":
                raise OSError("injected manifest write failure")
            return original_open(file_arg, *args, **kwargs)

        def _failing_rmtree(*args: object, **kwargs: object) -> None:
            raise PermissionError("injected cleanup failure")

        monkeypatch.setattr("builtins.open", _failing_open)
        monkeypatch.setattr(shutil, "rmtree", _failing_rmtree)

        # When cleanup fails, the cleanup exception is raised (lines 428-430)
        with pytest.raises(PermissionError, match="injected cleanup failure"):
            manager._create_backup(plan)

    def test_create_backup_failure_backup_dir_deleted(
        self, manager: PARAMigrationManager, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Backup failure when backup_dir doesn't exist in cleanup (line 428->430)."""
        src = tmp_path / "source.txt"
        src.write_text("content")

        plan = MigrationPlan(
            files=[
                MigrationFile(
                    source_path=src,
                    target_category=PARACategory.PROJECT,
                    target_path=tmp_path / "target" / "file.txt",
                    confidence=0.9,
                )
            ],
            total_count=1,
            by_category={PARACategory.PROJECT: 1},
            estimated_size=7,
            created_at=datetime.now(UTC),
        )

        # Inject failure in manifest writing and delete backup_dir before cleanup
        original_open = open
        original_mkdir = Path.mkdir

        backup_dir_ref = [None]

        def _track_mkdir(self: Path, *args: object, **kwargs: object) -> None:
            result = original_mkdir(self, *args, **kwargs)
            if "backup_" in str(self):
                backup_dir_ref[0] = self
            return result

        def _failing_open(file_arg: object, *args: object, **kwargs: object) -> object:
            if isinstance(file_arg, Path) and file_arg.name == "manifest.json":
                # Delete backup_dir before raising exception
                if backup_dir_ref[0] and backup_dir_ref[0].exists():
                    shutil.rmtree(backup_dir_ref[0])
                raise OSError("injected manifest write failure")
            return original_open(file_arg, *args, **kwargs)

        monkeypatch.setattr(Path, "mkdir", _track_mkdir)
        monkeypatch.setattr("builtins.open", _failing_open)

        # Should raise original exception without trying to cleanup non-existent dir
        with pytest.raises(IOError, match="injected manifest write failure"):
            manager._create_backup(plan)
