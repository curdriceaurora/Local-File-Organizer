"""Integration tests for PARAMigrationManager.

Covers:
  - PARAMigrationManager.__init__
  - analyze_source — real files, produces MigrationPlan
  - generate_preview — non-empty string
  - execute_migration — dry_run=True vs dry_run=False
  - _create_backup — backup dir created, returns backup_id
  - list_backups — non-empty after backup
  - verify_backup — returns True for valid backup
  - rollback — files restored to original location
  - _calculate_file_hash — hash differs when content changes
  - Error paths: BackupIntegrityError / RollbackError on corrupt backup
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from file_organizer.methodologies.para.categories import PARACategory
from file_organizer.methodologies.para.config import PARAConfig
from file_organizer.methodologies.para.migration_manager import (
    BackupIntegrityError,
    MigrationFile,
    MigrationPlan,
    MigrationReport,
    PARAMigrationManager,
    RollbackError,
)

pytestmark = [pytest.mark.integration, pytest.mark.ci]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_manager(tmp_path: Path) -> PARAMigrationManager:
    """Create a PARAMigrationManager whose backup_root lives in tmp_path."""
    manager = PARAMigrationManager(
        config=PARAConfig(
            enable_temporal_heuristic=True,
            enable_content_heuristic=False,
            enable_structural_heuristic=True,
            enable_ai_heuristic=False,
        )
    )
    # Redirect backup_root into tmp_path so tests do not write to user data dir.
    manager.backup_root = tmp_path / "backups"
    manager.backup_root.mkdir(parents=True, exist_ok=True)
    return manager


def _make_plan(source_dir: Path, target_dir: Path) -> MigrationPlan:
    """Build a minimal MigrationPlan with two real files."""
    file_a = source_dir / "report.txt"
    file_b = source_dir / "notes.md"
    file_a.write_text("report content")
    file_b.write_text("notes content")

    files = [
        MigrationFile(
            source_path=file_a,
            target_category=PARACategory.RESOURCE,
            target_path=target_dir / "Resources" / "report.txt",
            confidence=0.80,
            reasoning=["keyword match"],
        ),
        MigrationFile(
            source_path=file_b,
            target_category=PARACategory.PROJECT,
            target_path=target_dir / "Projects" / "notes.md",
            confidence=0.70,
            reasoning=["filename pattern"],
        ),
    ]
    return MigrationPlan(
        files=files,
        total_count=len(files),
        by_category={
            PARACategory.RESOURCE: 1,
            PARACategory.PROJECT: 1,
        },
        estimated_size=sum(f.source_path.stat().st_size for f in files),
        created_at=datetime.now(UTC),
    )


# ---------------------------------------------------------------------------
# TestPARAMigrationManagerInit
# ---------------------------------------------------------------------------


class TestPARAMigrationManagerInit:
    """Tests for PARAMigrationManager construction."""

    def test_init_creates_instance(self, tmp_path: Path) -> None:
        """Manager is created without error and exposes expected attributes."""
        manager = _make_manager(tmp_path)
        assert manager.config is not None
        assert manager.heuristic_engine is not None
        assert manager.folder_generator is not None

    def test_backup_root_redirected_to_tmp(self, tmp_path: Path) -> None:
        """Redirected backup_root is the tmp_path subdirectory."""
        manager = _make_manager(tmp_path)
        assert manager.backup_root == tmp_path / "backups"
        assert manager.backup_root.exists()

    def test_init_with_explicit_config(self, tmp_path: Path) -> None:
        """Custom PARAConfig is respected by the manager."""
        config = PARAConfig(project_dir="MyProjects", resource_dir="MyResources")
        manager = PARAMigrationManager(config=config)
        manager.backup_root = tmp_path / "backups"
        manager.backup_root.mkdir(parents=True, exist_ok=True)
        assert manager.config.project_dir == "MyProjects"
        assert manager.config.resource_dir == "MyResources"


# ---------------------------------------------------------------------------
# TestAnalyzeSource
# ---------------------------------------------------------------------------


class TestAnalyzeSource:
    """Tests for analyze_source."""

    def test_returns_migration_plan_with_files(self, tmp_path: Path) -> None:
        """analyze_source returns a MigrationPlan that contains all scanned files."""
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        target_dir = tmp_path / "para"

        (source_dir / "alpha.txt").write_text("alpha content")
        (source_dir / "beta.md").write_text("beta content")
        (source_dir / "gamma.pdf").write_bytes(b"%PDF-1.4 fake pdf")

        manager = _make_manager(tmp_path)
        plan = manager.analyze_source(source_dir, target_dir)

        assert isinstance(plan, MigrationPlan)
        assert plan.total_count == len(plan.files)
        assert plan.total_count == 3
        assert plan.estimated_size >= 0

    def test_plan_files_have_required_fields(self, tmp_path: Path) -> None:
        """Each MigrationFile in the plan has source_path, target_category, and confidence."""
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        target_dir = tmp_path / "para"
        (source_dir / "doc.txt").write_text("document content")

        manager = _make_manager(tmp_path)
        plan = manager.analyze_source(source_dir, target_dir)

        assert len(plan.files) == 1
        mf = plan.files[0]
        assert mf.source_path == source_dir / "doc.txt"
        assert isinstance(mf.target_category, PARACategory)
        assert 0.0 <= mf.confidence <= 1.0

    def test_non_recursive_scan(self, tmp_path: Path) -> None:
        """With recursive=False only top-level files are included."""
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        target_dir = tmp_path / "para"
        subdir = source_dir / "sub"
        subdir.mkdir()
        (source_dir / "top.txt").write_text("top level")
        (subdir / "nested.txt").write_text("nested")

        manager = _make_manager(tmp_path)
        plan_flat = manager.analyze_source(source_dir, target_dir, recursive=False)
        plan_recursive = manager.analyze_source(source_dir, target_dir, recursive=True)

        assert plan_flat.total_count == 1
        assert plan_recursive.total_count == 2

    def test_extension_filter(self, tmp_path: Path) -> None:
        """file_extensions filter limits which files are included in the plan."""
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        target_dir = tmp_path / "para"
        (source_dir / "readme.md").write_text("readme")
        (source_dir / "data.csv").write_text("a,b,c")
        (source_dir / "image.png").write_bytes(b"\x89PNG fake")

        manager = _make_manager(tmp_path)
        plan = manager.analyze_source(source_dir, target_dir, file_extensions=[".md", ".csv"])

        assert plan.total_count == 2
        suffixes = {mf.source_path.suffix for mf in plan.files}
        assert ".png" not in suffixes

    def test_empty_source_dir(self, tmp_path: Path) -> None:
        """analyze_source on empty directory returns zero-file plan."""
        source_dir = tmp_path / "empty_source"
        source_dir.mkdir()
        target_dir = tmp_path / "para"

        manager = _make_manager(tmp_path)
        plan = manager.analyze_source(source_dir, target_dir)

        assert plan.total_count == 0
        assert plan.files == []


# ---------------------------------------------------------------------------
# TestGeneratePreview
# ---------------------------------------------------------------------------


class TestGeneratePreview:
    """Tests for generate_preview."""

    def test_returns_non_empty_string(self, tmp_path: Path) -> None:
        """generate_preview returns a non-empty string for a non-empty plan."""
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        (source_dir / "file.txt").write_text("content")

        manager = _make_manager(tmp_path)
        plan = manager.analyze_source(source_dir, tmp_path / "para")
        preview = manager.generate_preview(plan)

        assert len(preview) > 0

    def test_preview_contains_total_count(self, tmp_path: Path) -> None:
        """Preview string contains the total file count."""
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        (source_dir / "a.txt").write_text("a")
        (source_dir / "b.txt").write_text("b")

        manager = _make_manager(tmp_path)
        plan = manager.analyze_source(source_dir, tmp_path / "para")
        preview = manager.generate_preview(plan)

        assert "Total files: 2" in preview

    def test_preview_contains_para_header(self, tmp_path: Path) -> None:
        """Preview starts with the PARA Migration Plan header."""
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        (source_dir / "x.txt").write_text("x")

        manager = _make_manager(tmp_path)
        plan = manager.analyze_source(source_dir, tmp_path / "para")
        preview = manager.generate_preview(plan)

        assert "PARA Migration Plan" in preview

    def test_preview_for_empty_plan(self, tmp_path: Path) -> None:
        """generate_preview works without error for a zero-file plan."""
        plan = MigrationPlan(
            files=[],
            total_count=0,
            by_category={},
            estimated_size=0,
            created_at=datetime.now(UTC),
        )
        manager = _make_manager(tmp_path)
        preview = manager.generate_preview(plan)

        assert "Total files: 0" in preview


# ---------------------------------------------------------------------------
# TestExecuteMigration
# ---------------------------------------------------------------------------


class TestExecuteMigration:
    """Tests for execute_migration."""

    def test_dry_run_does_not_move_files(self, tmp_path: Path) -> None:
        """dry_run=True: source files remain in place after execute_migration."""
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        target_dir = tmp_path / "para"
        plan = _make_plan(source_dir, target_dir)

        manager = _make_manager(tmp_path)
        report = manager.execute_migration(plan, dry_run=True, create_backup=False)

        assert report.success is True
        assert len(report.migrated) == 2
        # Source files must still exist and target must NOT have been created
        for mf in plan.files:
            assert mf.source_path.exists(), f"Source file missing: {mf.source_path}"
            assert not mf.target_path.exists(), f"Dry-run created target: {mf.target_path}"

    def test_live_migration_moves_files(self, tmp_path: Path) -> None:
        """dry_run=False: files are physically moved to target locations."""
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        target_dir = tmp_path / "para"
        plan = _make_plan(source_dir, target_dir)

        manager = _make_manager(tmp_path)
        report = manager.execute_migration(plan, dry_run=False, create_backup=False)

        assert report.success is True
        for mf in plan.files:
            assert mf.target_path.exists(), f"Target file missing: {mf.target_path}"
            assert not mf.source_path.exists(), f"Source still present: {mf.source_path}"

    def test_report_fields_populated(self, tmp_path: Path) -> None:
        """MigrationReport fields are populated after execution."""
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        target_dir = tmp_path / "para"
        plan = _make_plan(source_dir, target_dir)

        manager = _make_manager(tmp_path)
        report = manager.execute_migration(plan, dry_run=True, create_backup=False)

        assert isinstance(report, MigrationReport)
        assert report.plan is plan
        assert isinstance(report.migrated, list)
        assert isinstance(report.failed, list)
        assert isinstance(report.skipped, list)
        assert report.duration_seconds >= 0.0

    def test_skip_on_existing_target(self, tmp_path: Path) -> None:
        """Files whose target already exists are added to skipped, not failed."""
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        target_dir = tmp_path / "para"
        plan = _make_plan(source_dir, target_dir)

        # Pre-create the target for one file
        target_file = plan.files[0].target_path
        target_file.parent.mkdir(parents=True, exist_ok=True)
        target_file.write_text("already here")

        manager = _make_manager(tmp_path)
        report = manager.execute_migration(plan, dry_run=False, create_backup=False)

        assert len(report.skipped) == 1
        assert report.skipped[0] == plan.files[0].source_path

    def test_live_migration_with_backup_creates_backup(self, tmp_path: Path) -> None:
        """dry_run=False with create_backup=True creates a backup entry."""
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        target_dir = tmp_path / "para"
        plan = _make_plan(source_dir, target_dir)

        manager = _make_manager(tmp_path)
        manager.execute_migration(plan, dry_run=False, create_backup=True)

        backups = manager.list_backups()
        assert len(backups) == 1


# ---------------------------------------------------------------------------
# TestCreateBackup
# ---------------------------------------------------------------------------


class TestCreateBackup:
    """Tests for _create_backup."""

    def test_returns_backup_id_string(self, tmp_path: Path) -> None:
        """_create_backup returns a non-empty string backup ID."""
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        target_dir = tmp_path / "para"
        plan = _make_plan(source_dir, target_dir)

        manager = _make_manager(tmp_path)
        backup_id = manager._create_backup(plan)

        assert isinstance(backup_id, str)
        assert len(backup_id) > 0

    def test_backup_dir_created(self, tmp_path: Path) -> None:
        """Backup directory is created under backup_root."""
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        target_dir = tmp_path / "para"
        plan = _make_plan(source_dir, target_dir)

        manager = _make_manager(tmp_path)
        backup_id = manager._create_backup(plan)

        backup_dir = manager.backup_root / backup_id
        assert backup_dir.exists()

    def test_manifest_json_written(self, tmp_path: Path) -> None:
        """manifest.json is written in the backup directory."""
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        target_dir = tmp_path / "para"
        plan = _make_plan(source_dir, target_dir)

        manager = _make_manager(tmp_path)
        backup_id = manager._create_backup(plan)

        manifest_path = manager.backup_root / backup_id / "manifest.json"
        assert manifest_path.exists()
        data = json.loads(manifest_path.read_text())
        assert data["backup_id"] == backup_id
        assert data["files_backed_up"] == 2

    def test_source_files_copied_into_backup(self, tmp_path: Path) -> None:
        """Source files are physically present inside the backup directory with identical content."""
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        target_dir = tmp_path / "para"
        plan = _make_plan(source_dir, target_dir)

        manager = _make_manager(tmp_path)
        backup_id = manager._create_backup(plan)

        backup_dir = manager.backup_root / backup_id
        backed_up_files = list(backup_dir.rglob("*"))
        # Exactly 2 data files (excluding manifest.json)
        data_files = [p for p in backed_up_files if p.is_file() and p.name != "manifest.json"]
        assert len(data_files) == 2
        # Backed-up file names match original source file names
        backed_up_names = {p.name for p in data_files}
        source_names = {mf.source_path.name for mf in plan.files}
        assert backed_up_names == source_names
        # Backed-up file content matches original
        for mf in plan.files:
            backed = next(p for p in data_files if p.name == mf.source_path.name)
            assert backed.read_text() == mf.source_path.read_text()


# ---------------------------------------------------------------------------
# TestListBackups
# ---------------------------------------------------------------------------


class TestListBackups:
    """Tests for list_backups."""

    def test_empty_before_any_backup(self, tmp_path: Path) -> None:
        """list_backups returns empty list before any backup is created."""
        manager = _make_manager(tmp_path)
        assert manager.list_backups() == []

    def test_non_empty_after_backup(self, tmp_path: Path) -> None:
        """list_backups returns one entry after one backup is created."""
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        target_dir = tmp_path / "para"
        plan = _make_plan(source_dir, target_dir)

        manager = _make_manager(tmp_path)
        backup_id = manager._create_backup(plan)

        backups = manager.list_backups()
        assert len(backups) == 1
        assert backups[0]["backup_id"] == backup_id

    def test_two_backups_listed(self, tmp_path: Path) -> None:
        """list_backups returns both entries when two backups exist."""
        manager = _make_manager(tmp_path)

        for i in range(2):
            source_dir = tmp_path / f"source_{i}"
            source_dir.mkdir()
            (source_dir / f"file_{i}.txt").write_text(f"content {i}")
            target_dir = tmp_path / f"para_{i}"
            plan = _make_plan(source_dir, target_dir)
            manager._create_backup(plan)

        assert len(manager.list_backups()) == 2


# ---------------------------------------------------------------------------
# TestVerifyBackup
# ---------------------------------------------------------------------------


class TestVerifyBackup:
    """Tests for verify_backup."""

    def test_valid_backup_returns_true(self, tmp_path: Path) -> None:
        """verify_backup returns True for a freshly created backup."""
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        target_dir = tmp_path / "para"
        plan = _make_plan(source_dir, target_dir)

        manager = _make_manager(tmp_path)
        backup_id = manager._create_backup(plan)

        result = manager.verify_backup(backup_id)
        assert result is True

    def test_missing_backup_raises_error(self, tmp_path: Path) -> None:
        """verify_backup raises BackupIntegrityError for a non-existent backup ID."""
        manager = _make_manager(tmp_path)
        with pytest.raises(BackupIntegrityError):
            manager.verify_backup("backup_nonexistent_id")

    def test_corrupt_manifest_raises_error(self, tmp_path: Path) -> None:
        """verify_backup raises BackupIntegrityError when manifest checksum is tampered."""
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        target_dir = tmp_path / "para"
        plan = _make_plan(source_dir, target_dir)

        manager = _make_manager(tmp_path)
        backup_id = manager._create_backup(plan)

        # Tamper with the manifest checksum
        manifest_path = manager.backup_root / backup_id / "manifest.json"
        data = json.loads(manifest_path.read_text())
        data["checksum"] = "0" * 64  # invalid checksum
        manifest_path.write_text(json.dumps(data))

        with pytest.raises(BackupIntegrityError):
            manager.verify_backup(backup_id)

    def test_corrupt_file_raises_error(self, tmp_path: Path) -> None:
        """verify_backup raises BackupIntegrityError when a backed-up file is modified."""
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        target_dir = tmp_path / "para"
        plan = _make_plan(source_dir, target_dir)

        manager = _make_manager(tmp_path)
        backup_id = manager._create_backup(plan)

        # Corrupt one of the backed-up files
        manifest_path = manager.backup_root / backup_id / "manifest.json"
        data = json.loads(manifest_path.read_text())
        first_backup_path = Path(data["file_entries"][0]["backup_path"])
        first_backup_path.write_text("CORRUPTED CONTENT XYZ")

        with pytest.raises(BackupIntegrityError):
            manager.verify_backup(backup_id)


# ---------------------------------------------------------------------------
# TestRollback
# ---------------------------------------------------------------------------


class TestRollback:
    """Tests for rollback."""

    def test_rollback_restores_files(self, tmp_path: Path) -> None:
        """After migration + rollback, source files exist at original paths."""
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        target_dir = tmp_path / "para"
        plan = _make_plan(source_dir, target_dir)

        manager = _make_manager(tmp_path)
        # Execute live migration (files moved to target_dir)
        report = manager.execute_migration(plan, dry_run=False, create_backup=True)
        assert report.success is True
        backup_id = manager.list_backups()[0]["backup_id"]

        # Verify files were moved
        for mf in plan.files:
            assert mf.target_path.exists()

        # Rollback
        result = manager.rollback(backup_id)
        assert result is True

        # Source files must be restored
        for mf in plan.files:
            assert mf.source_path.exists(), f"Source not restored: {mf.source_path}"

    def test_rollback_returns_true(self, tmp_path: Path) -> None:
        """rollback returns True when it succeeds."""
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        target_dir = tmp_path / "para"
        plan = _make_plan(source_dir, target_dir)

        manager = _make_manager(tmp_path)
        manager.execute_migration(plan, dry_run=False, create_backup=True)
        backup_id = manager.list_backups()[0]["backup_id"]

        result = manager.rollback(backup_id)
        assert result is True

    def test_rollback_nonexistent_backup_raises_error(self, tmp_path: Path) -> None:
        """rollback raises RollbackError for a backup ID that doesn't exist."""
        manager = _make_manager(tmp_path)
        with pytest.raises(RollbackError):
            manager.rollback("backup_does_not_exist")


# ---------------------------------------------------------------------------
# TestCalculateFileHash
# ---------------------------------------------------------------------------


class TestCalculateFileHash:
    """Tests for _calculate_file_hash."""

    def test_hash_is_hex_string(self, tmp_path: Path) -> None:
        """_calculate_file_hash returns a hex string of correct SHA-256 length."""
        file_path = tmp_path / "sample.txt"
        file_path.write_text("sample content")
        result = PARAMigrationManager._calculate_file_hash(file_path)

        assert isinstance(result, str)
        assert len(result) == 64
        # All hex characters
        int(result, 16)

    def test_same_content_same_hash(self, tmp_path: Path) -> None:
        """Two files with identical content produce the same hash."""
        file_a = tmp_path / "a.txt"
        file_b = tmp_path / "b.txt"
        file_a.write_text("identical content")
        file_b.write_text("identical content")

        assert PARAMigrationManager._calculate_file_hash(
            file_a
        ) == PARAMigrationManager._calculate_file_hash(file_b)

    def test_different_content_different_hash(self, tmp_path: Path) -> None:
        """Changing file content changes the hash."""
        file_path = tmp_path / "mutable.txt"
        file_path.write_text("original content")
        hash_before = PARAMigrationManager._calculate_file_hash(file_path)

        file_path.write_text("modified content")
        hash_after = PARAMigrationManager._calculate_file_hash(file_path)

        assert hash_before != hash_after

    def test_empty_file_has_deterministic_hash(self, tmp_path: Path) -> None:
        """Empty file produces the known SHA-256 hash for empty input."""
        empty_file = tmp_path / "empty.txt"
        empty_file.write_bytes(b"")
        result = PARAMigrationManager._calculate_file_hash(empty_file)
        # SHA-256 of empty input is a known constant
        assert result == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
