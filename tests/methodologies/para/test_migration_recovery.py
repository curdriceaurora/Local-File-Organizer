"""
Comprehensive tests for PARA migration recovery and backup system.

Tests backup creation, integrity verification, and rollback mechanisms.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from file_organizer.methodologies.para.categories import PARACategory
from file_organizer.methodologies.para.config import PARAConfig
from file_organizer.methodologies.para.detection.heuristics import (
    CategoryScore,
    HeuristicResult,
)
from file_organizer.methodologies.para.migration_manager import (
    BackupIntegrityError,
    MigrationFile,
    MigrationPlan,
    PARAMigrationManager,
    RollbackError,
)


@pytest.mark.unit
class TestMigrationBackupSystem:
    """Test backup creation and recovery functionality."""

    @pytest.fixture
    def temp_source(self):
        """Create temporary source directory with test files."""
        temp_path = Path(tempfile.mkdtemp())

        # Create test files with known content
        (temp_path / "project_plan.txt").write_text("Project plan content - test")
        (temp_path / "meeting_notes.txt").write_text("Meeting notes content")
        (temp_path / "reference_doc.pdf").write_text("PDF reference content")
        (temp_path / "old_file.txt").write_text("Old file content")

        # Create nested structure
        subdir = temp_path / "subdir"
        subdir.mkdir()
        (subdir / "nested_file.txt").write_text("Nested file content")

        yield temp_path

        # Cleanup
        if temp_path.exists():
            shutil.rmtree(temp_path)

    @pytest.fixture
    def temp_target(self):
        """Create temporary target directory."""
        temp_path = Path(tempfile.mkdtemp())
        yield temp_path

        # Cleanup
        if temp_path.exists():
            shutil.rmtree(temp_path)

    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return PARAConfig(
            project_dir="Projects",
            area_dir="Areas",
            resource_dir="Resources",
            archive_dir="Archive",
        )

    @pytest.fixture
    def migration_manager(
        self, config: PARAConfig, tmp_path: Path
    ) -> Generator[PARAMigrationManager, None, None]:
        """Create migration manager instance with isolated backup root."""
        manager = PARAMigrationManager(config)
        # Override backup_root to use tmp_path so parallel tests don't collide
        manager.backup_root = tmp_path / "migration-backups"
        manager.backup_root.mkdir(parents=True, exist_ok=True)
        yield manager

    def test_backup_creation(self, migration_manager, temp_source, temp_target):
        """Test backup creation for migration files."""
        # Keep temp_source alive during backup by storing a reference
        plan = migration_manager.analyze_source(temp_source, temp_target, recursive=True)

        # Create backup
        backup_id = migration_manager._create_backup(plan)

        assert backup_id is not None
        assert backup_id.startswith("backup_migration_")

        # Verify backup directory exists
        backup_dir = migration_manager.backup_root / backup_id
        assert backup_dir.exists()

        # Verify manifest file exists
        manifest_file = backup_dir / "manifest.json"
        assert manifest_file.exists()

        # Verify at least some files were backed up
        with open(manifest_file) as f:
            manifest = json.load(f)
        assert manifest["files_backed_up"] > 0

    def test_backup_integrity_verification(self, migration_manager, temp_source, temp_target):
        """Test backup integrity verification."""
        plan = migration_manager.analyze_source(temp_source, temp_target, recursive=True)
        backup_id = migration_manager._create_backup(plan)

        # Verify backup integrity
        assert migration_manager.verify_backup(backup_id)

    def test_backup_manifest_structure(self, migration_manager, temp_source, temp_target):
        """Test backup manifest structure and metadata."""
        plan = migration_manager.analyze_source(temp_source, temp_target, recursive=True)
        backup_id = migration_manager._create_backup(plan)

        backup_dir = migration_manager.backup_root / backup_id
        manifest_file = backup_dir / "manifest.json"

        with open(manifest_file) as f:
            manifest = json.load(f)

        # Verify manifest structure
        assert manifest["backup_id"] == backup_id
        assert manifest["files_backed_up"] > 0
        assert manifest["status"] == "created"
        assert manifest["checksum"] is not None
        assert len(manifest["file_entries"]) == manifest["files_backed_up"]

        # Verify file entries
        for entry in manifest["file_entries"]:
            assert "original_path" in entry
            assert "backup_path" in entry
            assert "hash" in entry
            assert "size" in entry
            assert "category" in entry
            assert "confidence" in entry

    def test_backup_file_hashing(self, migration_manager, temp_source, temp_target):
        """Test that backup files are correctly hashed."""
        plan = migration_manager.analyze_source(temp_source, temp_target, recursive=True)
        backup_id = migration_manager._create_backup(plan)

        backup_dir = migration_manager.backup_root / backup_id
        manifest_file = backup_dir / "manifest.json"

        with open(manifest_file) as f:
            manifest = json.load(f)

        # Verify hashes for each backed-up file
        for entry in manifest["file_entries"]:
            backup_path = Path(entry["backup_path"])
            assert backup_path.exists()

            # Recalculate hash
            actual_hash = migration_manager._calculate_file_hash(backup_path)
            assert actual_hash == entry["hash"]

    def test_list_backups(self, migration_manager, temp_source, temp_target):
        """Test listing available backups."""
        plan = migration_manager.analyze_source(temp_source, temp_target, recursive=True)

        # Create multiple backups
        backup_id1 = migration_manager._create_backup(plan)
        backup_id2 = migration_manager._create_backup(plan)

        # List backups
        backups = migration_manager.list_backups()

        assert len(backups) >= 2
        backup_ids = [b["backup_id"] for b in backups]
        assert backup_id1 in backup_ids
        assert backup_id2 in backup_ids

    def test_backup_corrupted_detection(self, migration_manager, temp_source, temp_target):
        """Test detection of corrupted backup files."""
        plan = migration_manager.analyze_source(temp_source, temp_target, recursive=True)
        backup_id = migration_manager._create_backup(plan)

        backup_dir = migration_manager.backup_root / backup_id

        # Corrupt a backup file
        for backup_file in backup_dir.glob("**/*.txt"):
            if backup_file.name != "manifest.json":
                with open(backup_file, "a") as f:
                    f.write("corrupted data")
                break

        # Verification should fail
        with pytest.raises(BackupIntegrityError):
            migration_manager.verify_backup(backup_id)

    def test_backup_manifest_checksum_verification(
        self, migration_manager, temp_source, temp_target
    ):
        """Test manifest checksum verification."""
        plan = migration_manager.analyze_source(temp_source, temp_target, recursive=True)
        backup_id = migration_manager._create_backup(plan)

        backup_dir = migration_manager.backup_root / backup_id
        manifest_file = backup_dir / "manifest.json"

        # Load manifest and verify checksum
        with open(manifest_file) as f:
            manifest_data = json.load(f)

        stored_checksum = manifest_data["checksum"]
        file_entries = manifest_data["file_entries"]
        calculated = migration_manager._calculate_manifest_checksum(file_entries)

        assert stored_checksum == calculated

    def test_rollback_basic(self, migration_manager, temp_source, temp_target):
        """Test basic rollback functionality."""
        # Create initial files
        original_file = temp_source / "test_file.txt"
        original_file.write_text("original content")

        plan = migration_manager.analyze_source(temp_source, temp_target, recursive=False)
        backup_id = migration_manager._create_backup(plan)

        # Simulate migration by moving the file
        migrated_location = temp_target / "Projects" / "test_file.txt"
        migrated_location.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(original_file), str(migrated_location))

        # Verify file is gone from source
        assert not original_file.exists()
        assert migrated_location.exists()

        # Perform rollback
        assert migration_manager.rollback(backup_id)

        # Verify file is restored
        assert original_file.exists()
        assert original_file.read_text() == "original content"

    def test_rollback_integrity_check(self, migration_manager, temp_source, temp_target):
        """Test rollback verifies integrity of restored files."""
        plan = migration_manager.analyze_source(temp_source, temp_target, recursive=True)
        backup_id = migration_manager._create_backup(plan)

        # Move files to simulate migration
        target_project = temp_target / "Projects"
        for source_file in temp_source.glob("*.txt"):
            target_file = target_project / source_file.name
            target_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source_file), str(target_file))

        # Perform rollback
        assert migration_manager.rollback(backup_id)

        # Verify the root-level .txt files (the ones that were moved) are restored
        for original_file in temp_source.glob("*.txt"):
            content = original_file.read_text()
            assert "content" in content.lower()

    def test_rollback_preserves_metadata(self, migration_manager, temp_source, temp_target):
        """Test rollback status in manifest is updated."""
        plan = migration_manager.analyze_source(temp_source, temp_target, recursive=True)
        backup_id = migration_manager._create_backup(plan)

        # Move files to simulate migration
        for source_file in temp_source.glob("*.txt"):
            target_file = temp_target / "Projects" / source_file.name
            target_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source_file), str(target_file))

        # Perform rollback
        migration_manager.rollback(backup_id)

        # Verify manifest is updated
        backup_dir = migration_manager.backup_root / backup_id
        manifest_file = backup_dir / "manifest.json"

        with open(manifest_file) as f:
            manifest = json.load(f)

        assert manifest["status"] == "restored"
        assert manifest["restored_at"] is not None

    def test_rollback_missing_backup(self, migration_manager):
        """Test rollback fails gracefully with missing backup."""
        with pytest.raises(RollbackError):
            migration_manager.rollback("backup_nonexistent")

    def test_rollback_partial_failure_handling(self, migration_manager, temp_source, temp_target):
        """Test rollback collects per-file failures and raises RollbackError at the end."""
        plan = migration_manager.analyze_source(temp_source, temp_target, recursive=True)
        backup_id = migration_manager._create_backup(plan)

        # Move files to simulate migration
        for source_file in temp_source.glob("*.txt"):
            target_file = temp_target / "Projects" / source_file.name
            target_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source_file), str(target_file))

        # Corrupt one entry's original_path to an impossible restore location so that
        # the per-file copy step fails.  The backup files themselves are untouched, so
        # the manifest integrity-verification step still passes; only the copy fails.
        backup_dir = migration_manager.backup_root / backup_id
        manifest_file = backup_dir / "manifest.json"

        with open(manifest_file) as f:
            manifest_data = json.load(f)

        if manifest_data.get("file_entries"):
            manifest_data["file_entries"][0]["original_path"] = "/dev/null/impossible/path.txt"
            with open(manifest_file, "w") as f:
                json.dump(manifest_data, f, indent=2)

        # Rollback must raise because one entry cannot be restored
        with pytest.raises(RollbackError):
            migration_manager.rollback(backup_id)

    def test_hash_consistency(self, migration_manager, temp_source):
        """Test file hash calculations are consistent."""
        test_file = temp_source / "hash_test.txt"
        test_file.write_text("test content for hashing")

        # Calculate hash multiple times
        hash1 = migration_manager._calculate_file_hash(test_file)
        hash2 = migration_manager._calculate_file_hash(test_file)
        hash3 = migration_manager._calculate_file_hash(test_file)

        # All should be identical
        assert hash1 == hash2 == hash3

    def test_hash_differs_for_different_content(self, migration_manager, temp_source):
        """Test file hashes differ for different content."""
        file1 = temp_source / "file1.txt"
        file2 = temp_source / "file2.txt"

        file1.write_text("content one")
        file2.write_text("content two")

        hash1 = migration_manager._calculate_file_hash(file1)
        hash2 = migration_manager._calculate_file_hash(file2)

        assert hash1 != hash2

    def test_manifest_checksum_calculation(self, migration_manager):
        """Test manifest checksum calculation."""
        file_entries = [
            {"original_path": "/path/to/file1.txt", "hash": "abc123"},
            {"original_path": "/path/to/file2.txt", "hash": "def456"},
            {"original_path": "/path/to/file3.txt", "hash": "ghi789"},
        ]

        checksum = migration_manager._calculate_manifest_checksum(file_entries)

        # Verify checksum is deterministic
        checksum2 = migration_manager._calculate_manifest_checksum(file_entries)
        assert checksum == checksum2

        # Verify it's different when entries change
        file_entries.append({"original_path": "/path/to/file4.txt", "hash": "jkl012"})
        checksum3 = migration_manager._calculate_manifest_checksum(file_entries)
        assert checksum != checksum3

    def test_execute_migration_with_backup(self, migration_manager, temp_source, temp_target):
        """Test migration execution creates backup."""
        plan = migration_manager.analyze_source(temp_source, temp_target, recursive=False)

        # Execute migration with backup
        report = migration_manager.execute_migration(plan, dry_run=False, create_backup=True)

        assert report.success
        assert len(report.migrated) > 0

        # Verify backup was created
        backups = migration_manager.list_backups()
        assert len(backups) > 0

    def test_execute_migration_dry_run_no_backup(self, migration_manager, temp_source, temp_target):
        """Test dry-run doesn't create backup."""
        plan = migration_manager.analyze_source(temp_source, temp_target, recursive=False)

        # Execute dry-run
        report = migration_manager.execute_migration(plan, dry_run=True, create_backup=True)

        assert report.success

        # Verify no backup was created
        backups = migration_manager.list_backups()
        assert len(backups) == 0


@pytest.mark.unit
class TestMigrationManagerEdgeCases:
    """Test edge cases and error scenarios for migration manager."""

    @pytest.fixture
    def temp_source(self):
        """Create temporary source directory with test files."""
        temp_path = Path(tempfile.mkdtemp())

        # Create test files
        (temp_path / "test_file.txt").write_text("test content")
        (temp_path / "document.pdf").write_text("pdf content")

        yield temp_path

        # Cleanup
        if temp_path.exists():
            shutil.rmtree(temp_path)

    @pytest.fixture
    def temp_target(self):
        """Create temporary target directory."""
        temp_path = Path(tempfile.mkdtemp())
        yield temp_path

        # Cleanup
        if temp_path.exists():
            shutil.rmtree(temp_path)

    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return PARAConfig(
            project_dir="Projects",
            area_dir="Areas",
            resource_dir="Resources",
            archive_dir="Archive",
        )

    @pytest.fixture
    def migration_manager(
        self, config: PARAConfig, tmp_path: Path
    ) -> Generator[PARAMigrationManager, None, None]:
        """Create migration manager instance with isolated backup root."""
        manager = PARAMigrationManager(config)
        manager.backup_root = tmp_path / "migration-backups"
        manager.backup_root.mkdir(parents=True, exist_ok=True)
        yield manager

    def test_migration_manager_with_custom_heuristic_engine(self, config, tmp_path):
        """Test migration manager with custom heuristic engine."""
        from file_organizer.methodologies.para.detection.heuristics import HeuristicEngine

        custom_engine = HeuristicEngine(enable_ai=False)
        manager = PARAMigrationManager(config, heuristic_engine=custom_engine)
        manager.backup_root = tmp_path / "migration-backups"
        manager.backup_root.mkdir(parents=True, exist_ok=True)

        assert manager.heuristic_engine is custom_engine

    def test_analyze_source_with_file_extensions_filter(
        self, migration_manager, temp_source, temp_target
    ):
        """Test analyzing source with file extension filter."""
        # Create files with different extensions
        (temp_source / "doc.txt").write_text("text file")
        (temp_source / "image.png").write_text("png file")
        (temp_source / "data.json").write_text('{"key": "value"}')

        # Analyze with txt filter only
        plan = migration_manager.analyze_source(
            temp_source, temp_target, recursive=False, file_extensions=[".txt"]
        )

        # Should only include .txt files
        file_names = [f.source_path.name for f in plan.files]
        assert set(file_names) == {"test_file.txt", "doc.txt"}

    def test_analyze_source_categorization_exception_handling(
        self, migration_manager, temp_source, temp_target, monkeypatch
    ):
        """Test that categorization exceptions are handled gracefully."""
        # Create a file that will cause an exception during categorization
        test_file = temp_source / "problematic.txt"
        test_file.write_text("test content")

        # Mock heuristic engine to raise an exception
        def mock_evaluate(file_path):
            raise ValueError("Simulated categorization error")

        monkeypatch.setattr(migration_manager.heuristic_engine, "evaluate", mock_evaluate)

        # Analyze should continue despite exceptions
        plan = migration_manager.analyze_source(temp_source, temp_target, recursive=False)

        # Plan should exist but with 0 files due to all failing
        assert plan.total_count == 0

    def test_execute_migration_preserve_timestamps(
        self, migration_manager, temp_source, temp_target
    ):
        """Test migration preserves file timestamps."""
        # Create a file with known timestamps
        test_file = temp_source / "timestamp_test.txt"
        test_file.write_text("content")

        # Set specific timestamps
        old_time = time.time() - 86400  # 1 day ago
        os.utime(test_file, (old_time, old_time))

        original_stat = test_file.stat()

        plan = migration_manager.analyze_source(temp_source, temp_target, recursive=False)

        # Find which migration entry corresponds to our test file
        test_migration = None
        for mf in plan.files:
            if mf.source_path == test_file:
                test_migration = mf
                break

        # Execute with preserve_timestamps=True
        report = migration_manager.execute_migration(
            plan, dry_run=False, create_backup=False, preserve_timestamps=True
        )

        assert report.success
        assert len(report.migrated) > 0

        # Find migrated file and check timestamps
        assert test_migration is not None, "Test file should be in migration plan"
        assert test_migration.target_path.exists(), "Migrated file should exist"
        migrated_stat = test_migration.target_path.stat()
        # Timestamps should be preserved (within 2 second tolerance for filesystem precision)
        assert abs(migrated_stat.st_mtime - original_stat.st_mtime) < 2

    def test_execute_migration_without_preserve_timestamps(
        self,
        migration_manager,
        temp_source,
        temp_target,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Test migration without preserving timestamps."""
        test_file = temp_source / "no_preserve_test.txt"
        test_file.write_text("content")

        plan = migration_manager.analyze_source(temp_source, temp_target, recursive=False)
        test_migration = next((f for f in plan.files if f.source_path == test_file), None)
        assert test_migration is not None
        utime_calls: list[tuple[object, object]] = []

        original_utime = os.utime

        def track_utime(path: object, times: object) -> None:
            utime_calls.append((path, times))
            original_utime(path, times)

        monkeypatch.setattr(
            "file_organizer.methodologies.para.migration_manager.os.utime",
            track_utime,
        )

        # Execute with preserve_timestamps=False
        report = migration_manager.execute_migration(
            plan, dry_run=False, create_backup=False, preserve_timestamps=False
        )

        assert report.success
        assert test_migration.target_path.exists()
        assert utime_calls == []

    def test_backup_with_missing_source_file(self, migration_manager, temp_source, temp_target):
        """Test backup handles missing source files gracefully."""
        plan = migration_manager.analyze_source(temp_source, temp_target, recursive=False)

        # Delete a source file before backup
        if plan.files:
            plan.files[0].source_path.unlink()

        # Backup should succeed but skip missing file
        backup_id = migration_manager._create_backup(plan)

        assert backup_id is not None

        # Verify backup was created
        backup_dir = migration_manager.backup_root / backup_id
        assert backup_dir.exists()

    def test_backup_with_relative_path_error(self, migration_manager, temp_source, temp_target):
        """Test backup handles ValueError when computing relative paths."""
        # Create a plan with files from different root paths
        file1 = temp_source / "file1.txt"
        file1.write_text("content 1")

        # Create another temp directory with a different root
        other_root = Path(tempfile.mkdtemp())
        file2 = other_root / "file2.txt"
        file2.write_text("content 2")

        try:
            # Create migration files from different roots
            migration_files = [
                MigrationFile(
                    source_path=file1,
                    target_category=PARACategory.PROJECT,
                    target_path=temp_target / "Projects" / "file1.txt",
                    confidence=0.8,
                    reasoning=["test"],
                ),
                MigrationFile(
                    source_path=file2,
                    target_category=PARACategory.PROJECT,
                    target_path=temp_target / "Projects" / "file2.txt",
                    confidence=0.8,
                    reasoning=["test"],
                ),
            ]

            plan = MigrationPlan(
                files=migration_files,
                total_count=2,
                by_category={PARACategory.PROJECT: 2},
                estimated_size=16,
                created_at=datetime.now(UTC),
            )

            # Backup should handle ValueError and fall back to file.name
            backup_id = migration_manager._create_backup(plan)
            assert backup_id is not None
            backups = migration_manager.list_backups()
            assert any(b["backup_id"] == backup_id for b in backups)

        finally:
            # Cleanup
            if other_root.exists():
                shutil.rmtree(other_root)

    def test_backup_file_copy_exception_handling(
        self, migration_manager, temp_source, temp_target, monkeypatch
    ):
        """Test backup handles file copy exceptions gracefully."""
        plan = migration_manager.analyze_source(temp_source, temp_target, recursive=False)

        # Mock shutil.copy2 to raise an exception
        original_copy2 = shutil.copy2
        call_count = [0]

        def mock_copy2(src, dst):
            call_count[0] += 1
            if call_count[0] == 1:  # Fail on first file
                raise OSError("Simulated copy error")
            return original_copy2(src, dst)

        monkeypatch.setattr(shutil, "copy2", mock_copy2)

        # Backup should continue despite exceptions
        backup_id = migration_manager._create_backup(plan)
        assert backup_id is not None
        backups = migration_manager.list_backups()
        assert any(b["backup_id"] == backup_id for b in backups)

    def test_backup_no_files_warning(self, migration_manager, temp_source, temp_target):
        """Test backup with no files generates warning."""
        # Create a file but make it disappear before backup
        test_file = temp_source / "disappearing.txt"
        test_file.write_text("content")

        plan = migration_manager.analyze_source(temp_source, temp_target, recursive=False)

        # Delete all source files before backup
        for file in temp_source.glob("**/*"):
            if file.is_file():
                file.unlink()

        # Should handle missing files and still create backup (files_backed_up == 0)
        backup_id = migration_manager._create_backup(plan)
        assert backup_id is not None
        backups = migration_manager.list_backups()
        backup_entry = next((b for b in backups if b["backup_id"] == backup_id), None)
        assert backup_entry is not None
        assert backup_entry["files_backed_up"] == 0

    def test_backup_creation_exception_cleanup(
        self, migration_manager, temp_source, temp_target, monkeypatch
    ):
        """Test backup creation cleans up on exception."""
        plan = migration_manager.analyze_source(temp_source, temp_target, recursive=False)

        # Mock to raise exception during manifest creation
        original_open = open

        def mock_open(file, *args, **kwargs):
            if "manifest.json" in str(file) and "w" in args:
                raise OSError("Simulated write error")
            return original_open(file, *args, **kwargs)

        monkeypatch.setattr("builtins.open", mock_open)

        # Should raise and cleanup
        with pytest.raises(OSError):
            migration_manager._create_backup(plan)

    def test_rollback_missing_manifest(self, migration_manager, tmp_path):
        """Test rollback fails when manifest is missing."""
        # Create backup directory without manifest
        backup_id = "backup_test_missing_manifest"
        backup_dir = migration_manager.backup_root / backup_id
        backup_dir.mkdir(parents=True, exist_ok=True)

        # Should raise RollbackError
        with pytest.raises(RollbackError, match="manifest not found"):
            migration_manager.rollback(backup_id)

    def test_rollback_file_integrity_failure_during_restore(
        self, migration_manager, temp_source, temp_target, monkeypatch
    ):
        """Test rollback detects integrity failure during restore."""
        plan = migration_manager.analyze_source(temp_source, temp_target, recursive=False)
        backup_id = migration_manager._create_backup(plan)

        # Move files to simulate migration
        for source_file in temp_source.glob("*.txt"):
            target_file = temp_target / "Projects" / source_file.name
            target_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source_file), str(target_file))

        # Mock hash calculation to simulate corruption after restore
        original_hash = migration_manager._calculate_file_hash
        call_count = [0]

        def mock_hash(file_path):
            call_count[0] += 1
            # Return different hash on second call (after restore)
            if call_count[0] % 2 == 0:
                return "corrupted_hash_" + str(call_count[0])
            return original_hash(file_path)

        monkeypatch.setattr(migration_manager, "_calculate_file_hash", mock_hash)

        # Rollback should fail due to integrity check
        with pytest.raises(RollbackError, match="File hash mismatch"):
            migration_manager.rollback(backup_id)

    def test_list_backups_with_no_backup_root(self, migration_manager, tmp_path):
        """Test listing backups when backup root doesn't exist."""
        # Remove backup root
        if migration_manager.backup_root.exists():
            shutil.rmtree(migration_manager.backup_root)

        # Should return empty list
        backups = migration_manager.list_backups()
        assert backups == []

    def test_list_backups_with_non_directory_entries(
        self, migration_manager, temp_source, temp_target
    ):
        """Test listing backups skips non-directory entries."""
        # Create a file in backup root
        dummy_file = migration_manager.backup_root / "dummy.txt"
        dummy_file.write_text("not a backup")

        # Create a valid backup
        plan = migration_manager.analyze_source(temp_source, temp_target, recursive=False)
        migration_manager._create_backup(plan)

        # Should only list valid backups
        backups = migration_manager.list_backups()
        assert len(backups) >= 1
        assert all("backup_id" in b for b in backups)

    def test_list_backups_with_corrupted_manifest(
        self, migration_manager, temp_source, temp_target
    ):
        """Test listing backups handles corrupted manifests gracefully."""
        # Create a backup
        plan = migration_manager.analyze_source(temp_source, temp_target, recursive=False)
        backup_id = migration_manager._create_backup(plan)

        # Corrupt the manifest
        manifest_file = migration_manager.backup_root / backup_id / "manifest.json"
        manifest_file.write_text("corrupted json {[")

        # Should skip corrupted backup
        backups = migration_manager.list_backups()
        # May still have other backups, so just verify no exception is raised
        assert isinstance(backups, list)
        assert backups == []  # Corrupted backup should be skipped

    def test_verify_backup_not_found(self, migration_manager):
        """Test verify_backup fails when backup doesn't exist."""
        with pytest.raises(BackupIntegrityError, match="Backup not found"):
            migration_manager.verify_backup("backup_nonexistent")

    def test_verify_backup_missing_manifest(self, migration_manager):
        """Test verify_backup fails when manifest is missing."""
        # Create backup directory without manifest
        backup_id = "backup_test_no_manifest"
        backup_dir = migration_manager.backup_root / backup_id
        backup_dir.mkdir(parents=True, exist_ok=True)

        with pytest.raises(BackupIntegrityError, match="manifest not found"):
            migration_manager.verify_backup(backup_id)

    def test_verify_backup_integrity_missing_file(
        self, migration_manager, temp_source, temp_target
    ):
        """Test backup integrity check detects missing backup files."""
        plan = migration_manager.analyze_source(temp_source, temp_target, recursive=False)
        backup_id = migration_manager._create_backup(plan)

        # Delete a backup file
        backup_dir = migration_manager.backup_root / backup_id
        for backup_file in backup_dir.glob("**/*.txt"):
            if backup_file.name != "manifest.json":
                backup_file.unlink()
                break

        # Verification should fail
        with pytest.raises(BackupIntegrityError, match="Backup file missing"):
            migration_manager.verify_backup(backup_id)

    def test_verify_backup_integrity_hash_mismatch_in_verify(
        self, migration_manager, temp_source, temp_target
    ):
        """Test backup integrity check detects hash mismatches in verify method."""
        plan = migration_manager.analyze_source(temp_source, temp_target, recursive=False)
        backup_id = migration_manager._create_backup(plan)

        backup_dir = migration_manager.backup_root / backup_id
        manifest_file = backup_dir / "manifest.json"

        # Load and modify manifest to have wrong hash
        with open(manifest_file) as f:
            manifest_data = json.load(f)

        if manifest_data.get("file_entries"):
            # Change file hash to trigger hash mismatch
            manifest_data["file_entries"][0]["hash"] = "wrong_hash_value"
            # Recalculate checksum with the new hash
            manifest_data["checksum"] = migration_manager._calculate_manifest_checksum(
                manifest_data["file_entries"]
            )
            with open(manifest_file, "w") as f:
                json.dump(manifest_data, f, indent=2)

        # Verification should fail due to hash mismatch
        with pytest.raises(BackupIntegrityError, match="File hash mismatch"):
            migration_manager.verify_backup(backup_id)

    def test_generate_preview(self, migration_manager, temp_source, temp_target):
        """Test migration plan preview generation."""
        # Create multiple files for better preview
        for i in range(25):
            (temp_source / f"file_{i}.txt").write_text(f"content {i}")

        plan = migration_manager.analyze_source(temp_source, temp_target, recursive=False)

        # Generate preview
        preview = migration_manager.generate_preview(plan)

        # Verify preview content
        assert "PARA Migration Plan" in preview
        assert "Total files:" in preview
        assert "Distribution by Category" in preview
        assert "Files" in preview

        # Should show first 20 files and indicate more
        if plan.total_count > 20:
            assert "and" in preview and "more files" in preview

    def test_generate_preview_with_few_files(self, migration_manager, temp_source, temp_target):
        """Test preview generation with less than 20 files."""
        plan = migration_manager.analyze_source(temp_source, temp_target, recursive=False)

        preview = migration_manager.generate_preview(plan)

        # Should not show "more files" message
        assert "PARA Migration Plan" in preview
        # With few files, should not have the "more files" indicator
        if plan.total_count <= 20:
            lines = preview.split("\n")
            more_files_lines = [line for line in lines if "more files" in line]
            assert len(more_files_lines) == 0

    def test_analyze_source_category_none_fallback(
        self, migration_manager, temp_source, temp_target, monkeypatch
    ):
        """Test that None category falls back to RESOURCE."""

        # Mock heuristic engine to return None category
        def mock_evaluate(file_path):
            return HeuristicResult(recommended_category=None, overall_confidence=0.0, scores={})

        monkeypatch.setattr(migration_manager.heuristic_engine, "evaluate", mock_evaluate)

        # Create a test file
        test_file = temp_source / "unknown.txt"
        test_file.write_text("unknown content")

        # Analyze should fall back to RESOURCE for None category
        plan = migration_manager.analyze_source(temp_source, temp_target, recursive=False)

        # Verify that files were categorized as RESOURCE
        if plan.files:
            assert plan.files[0].target_category == PARACategory.RESOURCE

    def test_analyze_source_reasoning_extraction(
        self, migration_manager, temp_source, temp_target, monkeypatch
    ):
        """Test reasoning extraction when category is in scores."""

        # Mock heuristic engine to return result with reasoning
        def mock_evaluate(file_path):
            return HeuristicResult(
                recommended_category=PARACategory.PROJECT,
                overall_confidence=0.9,
                scores={
                    PARACategory.PROJECT: CategoryScore(
                        category=PARACategory.PROJECT,
                        score=0.9,
                        confidence=0.9,
                        signals=["deadline", "active project"],
                    )
                },
            )

        monkeypatch.setattr(migration_manager.heuristic_engine, "evaluate", mock_evaluate)

        test_file = temp_source / "project.txt"
        test_file.write_text("project content")

        plan = migration_manager.analyze_source(temp_source, temp_target, recursive=False)

        # Verify reasoning was extracted
        if plan.files:
            assert len(plan.files[0].reasoning) > 0
            assert (
                "deadline" in plan.files[0].reasoning or "active project" in plan.files[0].reasoning
            )

    def test_execute_migration_target_already_exists(
        self, migration_manager, temp_source, temp_target
    ):
        """Test migration skips files when target already exists."""
        plan = migration_manager.analyze_source(temp_source, temp_target, recursive=False)

        # Pre-create target file to simulate existing file
        if plan.files:
            target_path = plan.files[0].target_path
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text("existing content")

            # Execute migration
            report = migration_manager.execute_migration(plan, dry_run=False, create_backup=False)

            # Verify file was skipped
            assert len(report.skipped) > 0
            assert plan.files[0].source_path in report.skipped

    def test_execute_migration_dry_run_logging(self, migration_manager, temp_source, temp_target):
        """Test dry run execution logs without moving files."""
        plan = migration_manager.analyze_source(temp_source, temp_target, recursive=False)

        # Get original file paths
        original_files = [f.source_path for f in plan.files if f.source_path.exists()]

        # Execute dry run
        report = migration_manager.execute_migration(plan, dry_run=True, create_backup=False)

        # Verify no files were actually moved
        for original_file in original_files:
            assert original_file.exists(), f"File {original_file} should still exist after dry run"

        # But report should show files that would be migrated
        assert len(report.migrated) > 0

    def test_rollback_restore_file_exception_handling(
        self, migration_manager, temp_source, temp_target, monkeypatch
    ):
        """Test rollback handles per-file restore exceptions."""
        plan = migration_manager.analyze_source(temp_source, temp_target, recursive=False)
        backup_id = migration_manager._create_backup(plan)

        # Move files to simulate migration
        for source_file in temp_source.glob("*.txt"):
            target_file = temp_target / "Projects" / source_file.name
            target_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source_file), str(target_file))

        # Mock shutil.copy2 to raise exception on restore
        original_copy2 = shutil.copy2
        call_count = [0]

        def mock_copy2(src, dst):
            call_count[0] += 1
            # Fail on first restore attempt
            if call_count[0] == 1:
                raise OSError("Simulated restore error")
            return original_copy2(src, dst)

        monkeypatch.setattr(shutil, "copy2", mock_copy2)

        # Rollback should collect errors and raise
        with pytest.raises(RollbackError, match=r"completed with.*failures"):
            migration_manager.rollback(backup_id)

    def test_verify_backup_missing_file_in_internal_method(
        self, migration_manager, temp_source, temp_target
    ):
        """Test _verify_backup_integrity detects missing files."""
        plan = migration_manager.analyze_source(temp_source, temp_target, recursive=False)
        backup_id = migration_manager._create_backup(plan)

        backup_dir = migration_manager.backup_root / backup_id
        manifest_file = backup_dir / "manifest.json"

        # Load manifest
        with open(manifest_file) as f:
            manifest_data = json.load(f)

        # Delete a backup file
        for entry in manifest_data.get("file_entries", []):
            backup_path = Path(entry["backup_path"])
            if backup_path.exists():
                backup_path.unlink()
                break

        # _verify_backup_integrity should detect missing file
        with pytest.raises(BackupIntegrityError, match="Backup file missing"):
            migration_manager._verify_backup_integrity(backup_dir, manifest_data)

    def test_verify_backup_hash_mismatch_in_internal_method(
        self, migration_manager, temp_source, temp_target
    ):
        """Test _verify_backup_integrity detects hash mismatches."""
        plan = migration_manager.analyze_source(temp_source, temp_target, recursive=False)
        backup_id = migration_manager._create_backup(plan)

        backup_dir = migration_manager.backup_root / backup_id
        manifest_file = backup_dir / "manifest.json"

        # Load manifest
        with open(manifest_file) as f:
            manifest_data = json.load(f)

        # Corrupt a backup file
        for entry in manifest_data.get("file_entries", []):
            backup_path = Path(entry["backup_path"])
            if backup_path.exists():
                with open(backup_path, "a") as f:
                    f.write("corrupted content")
                break

        # _verify_backup_integrity should detect hash mismatch
        with pytest.raises(BackupIntegrityError, match="File hash mismatch"):
            migration_manager._verify_backup_integrity(backup_dir, manifest_data)

    def test_analyze_source_none_category_no_scores(
        self, migration_manager, temp_source, temp_target, monkeypatch
    ):
        """Test None category fallback when RESOURCE not in scores."""

        # Mock heuristic engine to return None category with empty scores
        def mock_evaluate(file_path):
            return HeuristicResult(recommended_category=None, overall_confidence=0.0, scores={})

        monkeypatch.setattr(migration_manager.heuristic_engine, "evaluate", mock_evaluate)

        test_file = temp_source / "unknown.txt"
        test_file.write_text("unknown content")

        # Analyze should fall back to RESOURCE
        plan = migration_manager.analyze_source(temp_source, temp_target, recursive=False)

        # Verify files were categorized as RESOURCE with empty reasoning
        if plan.files:
            assert plan.files[0].target_category == PARACategory.RESOURCE
            # Since RESOURCE was not in original scores, reasoning should be empty
            assert len(plan.files[0].reasoning) == 0

    def test_backup_verify_missing_file_in_private_method(
        self, migration_manager, temp_source, temp_target
    ):
        """Test _verify_backup detects missing backup files."""
        from file_organizer.methodologies.para.migration_manager import BackupMetadata

        plan = migration_manager.analyze_source(temp_source, temp_target, recursive=False)
        backup_id = migration_manager._create_backup(plan)

        backup_dir = migration_manager.backup_root / backup_id
        manifest_file = backup_dir / "manifest.json"

        # Load manifest
        with open(manifest_file) as f:
            manifest_data = json.load(f)

        # Create BackupMetadata object
        manifest = BackupMetadata(
            backup_id=manifest_data["backup_id"],
            migration_id=manifest_data.get("migration_id", ""),
            created_at=datetime.now(UTC),
            files_backed_up=manifest_data["files_backed_up"],
            total_size=manifest_data["total_size"],
            checksum=manifest_data["checksum"],
            source_root=Path(manifest_data["source_root"]),
            status=manifest_data["status"],
            file_entries=manifest_data.get("file_entries", []),
        )

        # Delete a backup file
        for entry in manifest.file_entries:
            backup_path = Path(entry["backup_path"])
            if backup_path.exists():
                backup_path.unlink()
                break

        # _verify_backup should detect missing file
        with pytest.raises(BackupIntegrityError, match="Backup file missing"):
            migration_manager._verify_backup(backup_dir, manifest)

    def test_backup_verify_hash_mismatch_in_private_method(
        self, migration_manager, temp_source, temp_target
    ):
        """Test _verify_backup detects hash mismatches."""
        from file_organizer.methodologies.para.migration_manager import BackupMetadata

        plan = migration_manager.analyze_source(temp_source, temp_target, recursive=False)
        backup_id = migration_manager._create_backup(plan)

        backup_dir = migration_manager.backup_root / backup_id
        manifest_file = backup_dir / "manifest.json"

        # Load manifest
        with open(manifest_file) as f:
            manifest_data = json.load(f)

        # Corrupt a backup file
        for entry in manifest_data.get("file_entries", []):
            backup_path = Path(entry["backup_path"])
            if backup_path.exists():
                with open(backup_path, "a") as f:
                    f.write("corrupted data")
                break

        # Create BackupMetadata object
        manifest = BackupMetadata(
            backup_id=manifest_data["backup_id"],
            migration_id=manifest_data.get("migration_id", ""),
            created_at=datetime.now(UTC),
            files_backed_up=manifest_data["files_backed_up"],
            total_size=manifest_data["total_size"],
            checksum=manifest_data["checksum"],
            source_root=Path(manifest_data["source_root"]),
            status=manifest_data["status"],
            file_entries=manifest_data.get("file_entries", []),
        )

        # _verify_backup should detect hash mismatch
        with pytest.raises(BackupIntegrityError, match="File hash mismatch"):
            migration_manager._verify_backup(backup_dir, manifest)

    def test_execute_migration_exception_during_move(
        self, migration_manager, temp_source, temp_target, monkeypatch
    ):
        """Test migration handles exceptions during file move."""
        plan = migration_manager.analyze_source(temp_source, temp_target, recursive=False)

        # Mock shutil.move to raise exception
        def mock_move(src, dst):
            raise OSError("Simulated move error")

        monkeypatch.setattr(shutil, "move", mock_move)

        # Execute migration
        report = migration_manager.execute_migration(plan, dry_run=False, create_backup=False)

        # Should not succeed due to failures
        assert not report.success
        assert len(report.failed) > 0

    def test_rollback_file_corruption_after_restore(
        self, migration_manager, temp_source, temp_target, monkeypatch
    ):
        """Test rollback detects file corruption after restore (line 494)."""
        plan = migration_manager.analyze_source(temp_source, temp_target, recursive=False)
        backup_id = migration_manager._create_backup(plan)

        # Move files to simulate migration
        for source_file in temp_source.glob("*.txt"):
            target_file = temp_target / "Projects" / source_file.name
            target_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source_file), str(target_file))

        # Mock copy2 to succeed but then mock hash calculation to fail
        original_copy2 = shutil.copy2

        def mock_copy2(src, dst):
            result = original_copy2(src, dst)
            # Corrupt the file after copying
            with open(dst, "a") as f:
                f.write("corrupted")
            return result

        monkeypatch.setattr(shutil, "copy2", mock_copy2)

        # Rollback should fail due to integrity check after restore
        with pytest.raises(RollbackError):
            migration_manager.rollback(backup_id)

    def test_backup_creation_failure_with_cleanup(
        self, migration_manager, temp_source, temp_target, monkeypatch
    ):
        """Test backup creation cleanup on failure after backup_dir exists."""
        plan = migration_manager.analyze_source(temp_source, temp_target, recursive=False)

        # Track if backup_dir was created and cleaned up
        cleanup_verified = [False]
        original_rmtree = shutil.rmtree

        def tracked_rmtree(path, *args, **kwargs):
            cleanup_verified[0] = True
            return original_rmtree(path, *args, **kwargs)

        monkeypatch.setattr(shutil, "rmtree", tracked_rmtree)

        # Mock the _calculate_manifest_checksum to fail after files are backed up
        def mock_checksum(file_entries):
            raise RuntimeError("Simulated checksum calculation error")

        monkeypatch.setattr(migration_manager, "_calculate_manifest_checksum", mock_checksum)

        # Should raise and cleanup
        with pytest.raises(RuntimeError):
            migration_manager._create_backup(plan)

        # Verify cleanup was called
        assert cleanup_verified[0], "Backup directory should have been cleaned up"
