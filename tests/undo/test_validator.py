"""
Unit tests for OperationValidator.

Tests validation logic for undo/redo operations.
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

import pytest

from file_organizer.history.models import Operation, OperationStatus, OperationType
from file_organizer.undo.models import ConflictType
from file_organizer.undo.validator import OperationValidator


@pytest.mark.unit
class TestOperationValidator(unittest.TestCase):
    """Test cases for OperationValidator."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_dir = Path(tempfile.mkdtemp())
        self.trash_dir = self.test_dir / "trash"
        self.validator = OperationValidator(trash_dir=self.trash_dir)

        # Create test files
        self.source_file = self.test_dir / "source.txt"
        self.dest_file = self.test_dir / "dest.txt"
        self.source_file.write_text("test content")

    def tearDown(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_validate_undo_move_success(self):
        """Test successful validation of move undo."""
        # Create operation
        operation = Operation(
            id=1,
            operation_type=OperationType.MOVE,
            timestamp=datetime.now(tz=UTC),
            source_path=self.source_file,
            destination_path=self.dest_file,
            status=OperationStatus.COMPLETED,
        )

        # Move file to destination
        shutil.move(str(self.source_file), str(self.dest_file))

        # Validate undo
        result = self.validator.validate_undo(operation)

        self.assertTrue(result.can_proceed)
        self.assertEqual(len(result.conflicts), 0)

    def test_validate_undo_move_file_missing(self):
        """Test validation fails when destination file is missing."""
        operation = Operation(
            id=1,
            operation_type=OperationType.MOVE,
            timestamp=datetime.now(tz=UTC),
            source_path=self.source_file,
            destination_path=self.dest_file,
            status=OperationStatus.COMPLETED,
        )

        # Don't move file - destination doesn't exist
        result = self.validator.validate_undo(operation)

        self.assertFalse(result.can_proceed)
        self.assertTrue(any(c.conflict_type == ConflictType.FILE_MISSING for c in result.conflicts))

    def test_validate_undo_move_source_occupied(self):
        """Test validation fails when source path is occupied."""
        operation = Operation(
            id=1,
            operation_type=OperationType.MOVE,
            timestamp=datetime.now(tz=UTC),
            source_path=self.source_file,
            destination_path=self.dest_file,
            status=OperationStatus.COMPLETED,
        )

        # Move file to destination
        shutil.move(str(self.source_file), str(self.dest_file))

        # Recreate source (occupied)
        self.source_file.write_text("new content")

        # Validate undo
        result = self.validator.validate_undo(operation)

        self.assertFalse(result.can_proceed)
        self.assertTrue(
            any(c.conflict_type == ConflictType.PATH_OCCUPIED for c in result.conflicts)
        )

    def test_validate_undo_rename_success(self):
        """Test successful validation of rename undo."""
        operation = Operation(
            id=1,
            operation_type=OperationType.RENAME,
            timestamp=datetime.now(tz=UTC),
            source_path=self.source_file,
            destination_path=self.dest_file,
            status=OperationStatus.COMPLETED,
        )

        # Rename file
        self.source_file.rename(self.dest_file)

        # Validate undo
        result = self.validator.validate_undo(operation)

        self.assertTrue(result.can_proceed)
        self.assertEqual(len(result.conflicts), 0)

    def test_validate_undo_delete_success(self):
        """Test successful validation of delete undo."""
        operation = Operation(
            id=1,
            operation_type=OperationType.DELETE,
            timestamp=datetime.now(tz=UTC),
            source_path=self.source_file,
            status=OperationStatus.COMPLETED,
        )

        # Move to trash
        trash_path = self.trash_dir / "1" / self.source_file.name
        trash_path.parent.mkdir(parents=True)
        shutil.move(str(self.source_file), str(trash_path))

        # Validate undo
        result = self.validator.validate_undo(operation)

        self.assertTrue(result.can_proceed)
        self.assertEqual(len(result.conflicts), 0)

    def test_validate_undo_delete_not_in_trash(self):
        """Test validation fails when file not in trash."""
        operation = Operation(
            id=1,
            operation_type=OperationType.DELETE,
            timestamp=datetime.now(tz=UTC),
            source_path=self.source_file,
            status=OperationStatus.COMPLETED,
        )

        # Don't move to trash
        result = self.validator.validate_undo(operation)

        self.assertFalse(result.can_proceed)
        self.assertTrue(any(c.conflict_type == ConflictType.FILE_MISSING for c in result.conflicts))

    def test_validate_undo_copy_success(self):
        """Test successful validation of copy undo."""
        # Create copy
        shutil.copy(str(self.source_file), str(self.dest_file))

        operation = Operation(
            id=1,
            operation_type=OperationType.COPY,
            timestamp=datetime.now(tz=UTC),
            source_path=self.source_file,
            destination_path=self.dest_file,
            status=OperationStatus.COMPLETED,
        )

        # Validate undo
        result = self.validator.validate_undo(operation)

        self.assertTrue(result.can_proceed)
        self.assertEqual(len(result.conflicts), 0)

    def test_validate_undo_already_rolled_back(self):
        """Test validation fails for already rolled back operation."""
        operation = Operation(
            id=1,
            operation_type=OperationType.MOVE,
            timestamp=datetime.now(tz=UTC),
            source_path=self.source_file,
            destination_path=self.dest_file,
            status=OperationStatus.ROLLED_BACK,
        )

        result = self.validator.validate_undo(operation)

        self.assertFalse(result.can_proceed)
        self.assertIn("already been rolled back", result.error_message)

    def test_validate_redo_success(self):
        """Test successful validation of redo."""
        operation = Operation(
            id=1,
            operation_type=OperationType.MOVE,
            timestamp=datetime.now(tz=UTC),
            source_path=self.source_file,
            destination_path=self.dest_file,
            status=OperationStatus.ROLLED_BACK,
        )

        # File should be at source after rollback
        # Already at source in setup

        # Validate redo
        result = self.validator.validate_redo(operation)

        self.assertTrue(result.can_proceed)
        self.assertEqual(len(result.conflicts), 0)

    def test_validate_redo_not_rolled_back(self):
        """Test validation fails for redo of non-rolled-back operation."""
        operation = Operation(
            id=1,
            operation_type=OperationType.MOVE,
            timestamp=datetime.now(tz=UTC),
            source_path=self.source_file,
            destination_path=self.dest_file,
            status=OperationStatus.COMPLETED,
        )

        result = self.validator.validate_redo(operation)

        self.assertFalse(result.can_proceed)
        self.assertIn("rolled back", result.error_message)

    def test_check_file_integrity_match(self):
        """Test file integrity check with matching hash."""
        import hashlib

        content = b"test content"
        self.source_file.write_bytes(content)
        expected_hash = hashlib.sha256(content).hexdigest()

        result = self.validator.check_file_integrity(self.source_file, expected_hash)

        self.assertTrue(result)

    def test_check_file_integrity_mismatch(self):
        """Test file integrity check with mismatched hash."""
        self.source_file.write_text("test content")
        wrong_hash = "a" * 64

        result = self.validator.check_file_integrity(self.source_file, wrong_hash)

        self.assertFalse(result)

    def test_check_path_exists(self):
        """Test path existence check."""
        self.assertTrue(self.validator.check_path_exists(self.source_file))
        self.assertFalse(self.validator.check_path_exists(self.dest_file))

    def test_check_path_available(self):
        """Test path availability check."""
        self.assertFalse(self.validator.check_path_available(self.source_file))
        self.assertTrue(self.validator.check_path_available(self.dest_file))

    # --- Additional tests for uncovered lines ---

    def test_validate_undo_failed_operation_warning(self):
        """Test undo of a failed operation gives a warning."""
        operation = Operation(
            id=1,
            operation_type=OperationType.MOVE,
            timestamp=datetime.now(tz=UTC),
            source_path=self.source_file,
            destination_path=self.dest_file,
            status=OperationStatus.FAILED,
        )
        # Move the file so dest exists and source is available
        shutil.move(str(self.source_file), str(self.dest_file))
        result = self.validator.validate_undo(operation)
        self.assertTrue(len(result.warnings) > 0)
        self.assertIn("originally failed", result.warnings[0])

    def test_validate_undo_create_success(self):
        """Test undo of a create operation (delete created file)."""
        operation = Operation(
            id=1,
            operation_type=OperationType.CREATE,
            timestamp=datetime.now(tz=UTC),
            source_path=self.source_file,
            status=OperationStatus.COMPLETED,
        )
        result = self.validator.validate_undo(operation)
        self.assertTrue(result.can_proceed)

    def test_validate_undo_create_file_missing(self):
        """Test undo of create when file is already deleted."""
        missing = self.test_dir / "missing_created.txt"
        operation = Operation(
            id=1,
            operation_type=OperationType.CREATE,
            timestamp=datetime.now(tz=UTC),
            source_path=missing,
            status=OperationStatus.COMPLETED,
        )
        result = self.validator.validate_undo(operation)
        self.assertFalse(result.can_proceed)
        self.assertTrue(
            any(c.conflict_type == ConflictType.FILE_MISSING for c in result.conflicts)
        )

    def test_validate_redo_rename_success(self):
        """Test redo of a rename operation delegates to redo_move."""
        operation = Operation(
            id=1,
            operation_type=OperationType.RENAME,
            timestamp=datetime.now(tz=UTC),
            source_path=self.source_file,
            destination_path=self.dest_file,
            status=OperationStatus.ROLLED_BACK,
        )
        result = self.validator.validate_redo(operation)
        self.assertTrue(result.can_proceed)

    def test_validate_redo_delete_success(self):
        """Test redo of a delete operation (delete file again)."""
        operation = Operation(
            id=1,
            operation_type=OperationType.DELETE,
            timestamp=datetime.now(tz=UTC),
            source_path=self.source_file,
            status=OperationStatus.ROLLED_BACK,
        )
        result = self.validator.validate_redo(operation)
        self.assertTrue(result.can_proceed)

    def test_validate_redo_delete_file_missing(self):
        """Test redo of delete when file not found."""
        missing = self.test_dir / "missing.txt"
        operation = Operation(
            id=1,
            operation_type=OperationType.DELETE,
            timestamp=datetime.now(tz=UTC),
            source_path=missing,
            status=OperationStatus.ROLLED_BACK,
        )
        result = self.validator.validate_redo(operation)
        self.assertFalse(result.can_proceed)
        self.assertTrue(
            any(c.conflict_type == ConflictType.FILE_MISSING for c in result.conflicts)
        )

    def test_validate_redo_copy_success(self):
        """Test redo of a copy operation (copy file again)."""
        operation = Operation(
            id=1,
            operation_type=OperationType.COPY,
            timestamp=datetime.now(tz=UTC),
            source_path=self.source_file,
            destination_path=self.dest_file,
            status=OperationStatus.ROLLED_BACK,
        )
        result = self.validator.validate_redo(operation)
        self.assertTrue(result.can_proceed)

    def test_validate_redo_copy_source_missing(self):
        """Test redo copy when source is missing."""
        missing = self.test_dir / "missing.txt"
        operation = Operation(
            id=1,
            operation_type=OperationType.COPY,
            timestamp=datetime.now(tz=UTC),
            source_path=missing,
            destination_path=self.dest_file,
            status=OperationStatus.ROLLED_BACK,
        )
        result = self.validator.validate_redo(operation)
        self.assertFalse(result.can_proceed)
        self.assertTrue(
            any(c.conflict_type == ConflictType.FILE_MISSING for c in result.conflicts)
        )

    def test_validate_redo_copy_dest_occupied(self):
        """Test redo copy when destination is occupied."""
        self.dest_file.write_text("occupied")
        operation = Operation(
            id=1,
            operation_type=OperationType.COPY,
            timestamp=datetime.now(tz=UTC),
            source_path=self.source_file,
            destination_path=self.dest_file,
            status=OperationStatus.ROLLED_BACK,
        )
        result = self.validator.validate_redo(operation)
        self.assertFalse(result.can_proceed)
        self.assertTrue(
            any(c.conflict_type == ConflictType.PATH_OCCUPIED for c in result.conflicts)
        )

    def test_validate_redo_create_success(self):
        """Test redo of create operation (path available)."""
        new_file = self.test_dir / "new_file.txt"
        operation = Operation(
            id=1,
            operation_type=OperationType.CREATE,
            timestamp=datetime.now(tz=UTC),
            source_path=new_file,
            status=OperationStatus.ROLLED_BACK,
        )
        result = self.validator.validate_redo(operation)
        self.assertTrue(result.can_proceed)

    def test_validate_redo_create_path_occupied(self):
        """Test redo create when path is occupied."""
        operation = Operation(
            id=1,
            operation_type=OperationType.CREATE,
            timestamp=datetime.now(tz=UTC),
            source_path=self.source_file,
            status=OperationStatus.ROLLED_BACK,
        )
        result = self.validator.validate_redo(operation)
        self.assertFalse(result.can_proceed)
        self.assertTrue(
            any(c.conflict_type == ConflictType.PATH_OCCUPIED for c in result.conflicts)
        )

    def test_check_conflicts_undo(self):
        """Test check_conflicts delegates to validate_undo."""
        operation = Operation(
            id=1,
            operation_type=OperationType.MOVE,
            timestamp=datetime.now(tz=UTC),
            source_path=self.source_file,
            destination_path=self.dest_file,
            status=OperationStatus.COMPLETED,
        )
        # dest_file doesn't exist, so should find FILE_MISSING conflict
        conflicts = self.validator.check_conflicts(operation, is_undo=True)
        self.assertTrue(len(conflicts) > 0)

    def test_check_conflicts_redo(self):
        """Test check_conflicts delegates to validate_redo."""
        operation = Operation(
            id=1,
            operation_type=OperationType.MOVE,
            timestamp=datetime.now(tz=UTC),
            source_path=self.source_file,
            destination_path=self.dest_file,
            status=OperationStatus.ROLLED_BACK,
        )
        conflicts = self.validator.check_conflicts(operation, is_undo=False)
        self.assertEqual(len(conflicts), 0)

    def test_get_trash_path_fallback_search(self):
        """Test _get_trash_path falls back to search by filename."""
        # Create file in trash under a different op id
        other_dir = self.trash_dir / "other"
        other_dir.mkdir(parents=True)
        trash_file = other_dir / "source.txt"
        trash_file.write_text("content")

        operation = Operation(
            id=999,  # doesn't match the 'other' dir
            operation_type=OperationType.DELETE,
            timestamp=datetime.now(tz=UTC),
            source_path=self.source_file,
            status=OperationStatus.COMPLETED,
        )
        result = self.validator._get_trash_path(operation)
        self.assertIsNotNone(result)
        self.assertEqual(result.name, "source.txt")

    def test_get_trash_path_not_found(self):
        """Test _get_trash_path returns None when file not in trash."""
        operation = Operation(
            id=999,
            operation_type=OperationType.DELETE,
            timestamp=datetime.now(tz=UTC),
            source_path=self.test_dir / "nonexistent.txt",
            status=OperationStatus.COMPLETED,
        )
        result = self.validator._get_trash_path(operation)
        self.assertIsNone(result)

    def test_validate_undo_move_hash_mismatch(self):
        """Test undo move detects hash mismatch at destination."""
        shutil.move(str(self.source_file), str(self.dest_file))
        operation = Operation(
            id=1,
            operation_type=OperationType.MOVE,
            timestamp=datetime.now(tz=UTC),
            source_path=self.test_dir / "original.txt",
            destination_path=self.dest_file,
            status=OperationStatus.COMPLETED,
            file_hash="a" * 64,  # Wrong hash
        )
        result = self.validator.validate_undo(operation)
        self.assertTrue(
            any(c.conflict_type == ConflictType.HASH_MISMATCH for c in result.conflicts)
        )

    def test_validate_undo_move_parent_missing(self):
        """Test undo move detects missing parent directory."""
        shutil.move(str(self.source_file), str(self.dest_file))
        missing_parent = self.test_dir / "nonexistent_dir" / "file.txt"
        operation = Operation(
            id=1,
            operation_type=OperationType.MOVE,
            timestamp=datetime.now(tz=UTC),
            source_path=missing_parent,
            destination_path=self.dest_file,
            status=OperationStatus.COMPLETED,
        )
        result = self.validator.validate_undo(operation)
        self.assertTrue(
            any(c.conflict_type == ConflictType.PARENT_MISSING for c in result.conflicts)
        )

    def test_validate_undo_delete_parent_missing(self):
        """Test undo delete detects missing parent directory."""
        # Put file in trash
        trash_path = self.trash_dir / "1" / self.source_file.name
        trash_path.parent.mkdir(parents=True)
        shutil.copy(str(self.source_file), str(trash_path))

        missing_parent = self.test_dir / "nonexistent_dir" / "file.txt"
        operation = Operation(
            id=1,
            operation_type=OperationType.DELETE,
            timestamp=datetime.now(tz=UTC),
            source_path=missing_parent,
            status=OperationStatus.COMPLETED,
        )
        result = self.validator.validate_undo(operation)
        self.assertTrue(
            any(c.conflict_type == ConflictType.PARENT_MISSING for c in result.conflicts)
        )

    def test_check_file_integrity_nonexistent(self):
        """Test file integrity check for nonexistent file."""
        result = self.validator.check_file_integrity(
            self.test_dir / "no_such_file.txt", "abc"
        )
        self.assertFalse(result)

    def test_check_file_integrity_directory(self):
        """Test file integrity check for a directory (not a file)."""
        result = self.validator.check_file_integrity(self.test_dir, "abc")
        self.assertFalse(result)

    def test_validate_undo_rename_hash_mismatch(self):
        """Test undo rename detects hash mismatch."""
        self.source_file.rename(self.dest_file)
        operation = Operation(
            id=1,
            operation_type=OperationType.RENAME,
            timestamp=datetime.now(tz=UTC),
            source_path=self.test_dir / "original_name.txt",
            destination_path=self.dest_file,
            status=OperationStatus.COMPLETED,
            file_hash="b" * 64,
        )
        result = self.validator.validate_undo(operation)
        self.assertTrue(
            any(c.conflict_type == ConflictType.HASH_MISMATCH for c in result.conflicts)
        )

    def test_validate_undo_copy_hash_mismatch(self):
        """Test undo copy detects hash mismatch."""
        shutil.copy(str(self.source_file), str(self.dest_file))
        # Now modify the copy
        self.dest_file.write_text("modified content")
        operation = Operation(
            id=1,
            operation_type=OperationType.COPY,
            timestamp=datetime.now(tz=UTC),
            source_path=self.source_file,
            destination_path=self.dest_file,
            status=OperationStatus.COMPLETED,
            file_hash="c" * 64,
        )
        result = self.validator.validate_undo(operation)
        self.assertTrue(
            any(c.conflict_type == ConflictType.HASH_MISMATCH for c in result.conflicts)
        )

    def test_validate_undo_delete_hash_mismatch_in_trash(self):
        """Test undo delete detects hash mismatch for file in trash."""
        trash_path = self.trash_dir / "1" / self.source_file.name
        trash_path.parent.mkdir(parents=True)
        shutil.copy(str(self.source_file), str(trash_path))

        # Remove source so path is available
        self.source_file.unlink()

        operation = Operation(
            id=1,
            operation_type=OperationType.DELETE,
            timestamp=datetime.now(tz=UTC),
            source_path=self.test_dir / "source.txt",
            status=OperationStatus.COMPLETED,
            file_hash="d" * 64,
        )
        result = self.validator.validate_undo(operation)
        self.assertTrue(
            any(c.conflict_type == ConflictType.HASH_MISMATCH for c in result.conflicts)
        )

    def test_init_default_trash_dir(self):
        """Test validator initializes with default trash dir."""
        validator = OperationValidator(trash_dir=None)
        expected = Path.home() / ".file_organizer" / "trash"
        self.assertEqual(validator.trash_dir, expected)


if __name__ == "__main__":
    unittest.main()
