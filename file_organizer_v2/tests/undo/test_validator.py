"""
Unit tests for OperationValidator.

Tests validation logic for undo/redo operations.
"""

import shutil
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from file_organizer.history.models import Operation, OperationStatus, OperationType
from file_organizer.undo.models import ConflictType
from file_organizer.undo.validator import OperationValidator


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
            timestamp=datetime.utcnow(),
            source_path=self.source_file,
            destination_path=self.dest_file,
            status=OperationStatus.COMPLETED
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
            timestamp=datetime.utcnow(),
            source_path=self.source_file,
            destination_path=self.dest_file,
            status=OperationStatus.COMPLETED
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
            timestamp=datetime.utcnow(),
            source_path=self.source_file,
            destination_path=self.dest_file,
            status=OperationStatus.COMPLETED
        )

        # Move file to destination
        shutil.move(str(self.source_file), str(self.dest_file))

        # Recreate source (occupied)
        self.source_file.write_text("new content")

        # Validate undo
        result = self.validator.validate_undo(operation)

        self.assertFalse(result.can_proceed)
        self.assertTrue(any(c.conflict_type == ConflictType.PATH_OCCUPIED for c in result.conflicts))

    def test_validate_undo_rename_success(self):
        """Test successful validation of rename undo."""
        operation = Operation(
            id=1,
            operation_type=OperationType.RENAME,
            timestamp=datetime.utcnow(),
            source_path=self.source_file,
            destination_path=self.dest_file,
            status=OperationStatus.COMPLETED
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
            timestamp=datetime.utcnow(),
            source_path=self.source_file,
            status=OperationStatus.COMPLETED
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
            timestamp=datetime.utcnow(),
            source_path=self.source_file,
            status=OperationStatus.COMPLETED
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
            timestamp=datetime.utcnow(),
            source_path=self.source_file,
            destination_path=self.dest_file,
            status=OperationStatus.COMPLETED
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
            timestamp=datetime.utcnow(),
            source_path=self.source_file,
            destination_path=self.dest_file,
            status=OperationStatus.ROLLED_BACK
        )

        result = self.validator.validate_undo(operation)

        self.assertFalse(result.can_proceed)
        self.assertIn("already been rolled back", result.error_message)

    def test_validate_redo_success(self):
        """Test successful validation of redo."""
        operation = Operation(
            id=1,
            operation_type=OperationType.MOVE,
            timestamp=datetime.utcnow(),
            source_path=self.source_file,
            destination_path=self.dest_file,
            status=OperationStatus.ROLLED_BACK
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
            timestamp=datetime.utcnow(),
            source_path=self.source_file,
            destination_path=self.dest_file,
            status=OperationStatus.COMPLETED
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


if __name__ == '__main__':
    unittest.main()
