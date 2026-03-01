"""
Comprehensive tests for PARA migration recovery and backup system.

Tests backup creation, integrity verification, and rollback mechanisms.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest

from file_organizer.methodologies.para.config import PARAConfig
from file_organizer.methodologies.para.migration_manager import (
    BackupIntegrityError,
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

    def test_backup_manifest_checksum_verification(self, migration_manager, temp_source, temp_target):
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
