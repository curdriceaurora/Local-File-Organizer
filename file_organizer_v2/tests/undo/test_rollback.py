"""
Unit tests for RollbackExecutor.

Tests rollback execution for all operation types.
"""

import unittest
import tempfile
import shutil
from pathlib import Path
from datetime import datetime

from file_organizer.history.models import Operation, OperationType, OperationStatus
from file_organizer.undo.rollback import RollbackExecutor
from file_organizer.undo.validator import OperationValidator


class TestRollbackExecutor(unittest.TestCase):
    """Test cases for RollbackExecutor."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_dir = Path(tempfile.mkdtemp())
        self.trash_dir = self.test_dir / "trash"
        self.validator = OperationValidator(trash_dir=self.trash_dir)
        self.executor = RollbackExecutor(validator=self.validator)

        # Create test files
        self.source_file = self.test_dir / "source.txt"
        self.dest_file = self.test_dir / "dest.txt"
        self.source_file.write_text("test content")

    def tearDown(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_rollback_move(self):
        """Test rollback of move operation."""
        # Create operation
        operation = Operation(
            id=1,
            operation_type=OperationType.MOVE,
            timestamp=datetime.utcnow(),
            source_path=self.source_file,
            destination_path=self.dest_file,
            status=OperationStatus.COMPLETED
        )

        # Perform move
        shutil.move(str(self.source_file), str(self.dest_file))

        # Rollback
        success = self.executor.rollback_move(operation)

        self.assertTrue(success)
        self.assertTrue(self.source_file.exists())
        self.assertFalse(self.dest_file.exists())

    def test_rollback_rename(self):
        """Test rollback of rename operation."""
        operation = Operation(
            id=1,
            operation_type=OperationType.RENAME,
            timestamp=datetime.utcnow(),
            source_path=self.source_file,
            destination_path=self.dest_file,
            status=OperationStatus.COMPLETED
        )

        # Perform rename
        self.source_file.rename(self.dest_file)

        # Rollback
        success = self.executor.rollback_rename(operation)

        self.assertTrue(success)
        self.assertTrue(self.source_file.exists())
        self.assertFalse(self.dest_file.exists())

    def test_rollback_delete(self):
        """Test rollback of delete operation."""
        operation = Operation(
            id=1,
            operation_type=OperationType.DELETE,
            timestamp=datetime.utcnow(),
            source_path=self.source_file,
            status=OperationStatus.COMPLETED
        )

        # Move to trash (simulating delete)
        trash_path = self.trash_dir / "1" / self.source_file.name
        trash_path.parent.mkdir(parents=True)
        shutil.move(str(self.source_file), str(trash_path))

        # Rollback (restore)
        success = self.executor.rollback_delete(operation)

        self.assertTrue(success)
        self.assertTrue(self.source_file.exists())
        self.assertFalse(trash_path.exists())

    def test_rollback_copy(self):
        """Test rollback of copy operation."""
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

        # Rollback (delete copy)
        success = self.executor.rollback_copy(operation)

        self.assertTrue(success)
        self.assertTrue(self.source_file.exists())
        # Copy should be in trash
        self.assertFalse(self.dest_file.exists())

    def test_rollback_create(self):
        """Test rollback of create operation."""
        created_file = self.test_dir / "created.txt"
        created_file.write_text("created content")

        operation = Operation(
            id=1,
            operation_type=OperationType.CREATE,
            timestamp=datetime.utcnow(),
            source_path=created_file,
            status=OperationStatus.COMPLETED
        )

        # Rollback (delete created file)
        success = self.executor.rollback_create(operation)

        self.assertTrue(success)
        # File should be in trash
        self.assertFalse(created_file.exists())

    def test_redo_move(self):
        """Test redo of move operation."""
        operation = Operation(
            id=1,
            operation_type=OperationType.MOVE,
            timestamp=datetime.utcnow(),
            source_path=self.source_file,
            destination_path=self.dest_file,
            status=OperationStatus.ROLLED_BACK
        )

        # File is at source (after rollback)
        # Redo the move
        success = self.executor.redo_move(operation)

        self.assertTrue(success)
        self.assertFalse(self.source_file.exists())
        self.assertTrue(self.dest_file.exists())

    def test_redo_rename(self):
        """Test redo of rename operation."""
        operation = Operation(
            id=1,
            operation_type=OperationType.RENAME,
            timestamp=datetime.utcnow(),
            source_path=self.source_file,
            destination_path=self.dest_file,
            status=OperationStatus.ROLLED_BACK
        )

        # File is at source (after rollback)
        # Redo the rename
        success = self.executor.redo_rename(operation)

        self.assertTrue(success)
        self.assertFalse(self.source_file.exists())
        self.assertTrue(self.dest_file.exists())

    def test_redo_delete(self):
        """Test redo of delete operation."""
        operation = Operation(
            id=1,
            operation_type=OperationType.DELETE,
            timestamp=datetime.utcnow(),
            source_path=self.source_file,
            status=OperationStatus.ROLLED_BACK
        )

        # File is restored (after rollback)
        # Redo the delete
        success = self.executor.redo_delete(operation)

        self.assertTrue(success)
        # File should be in trash
        self.assertFalse(self.source_file.exists())

    def test_redo_copy(self):
        """Test redo of copy operation."""
        operation = Operation(
            id=1,
            operation_type=OperationType.COPY,
            timestamp=datetime.utcnow(),
            source_path=self.source_file,
            destination_path=self.dest_file,
            status=OperationStatus.ROLLED_BACK
        )

        # Copy was deleted (after rollback)
        # Redo the copy
        success = self.executor.redo_copy(operation)

        self.assertTrue(success)
        self.assertTrue(self.source_file.exists())
        self.assertTrue(self.dest_file.exists())

    def test_rollback_transaction(self):
        """Test rollback of entire transaction."""
        # Create multiple operations
        operations = []

        # Operation 1: Move
        file1 = self.test_dir / "file1.txt"
        dest1 = self.test_dir / "dest1.txt"
        file1.write_text("content1")
        shutil.move(str(file1), str(dest1))
        operations.append(Operation(
            id=1,
            operation_type=OperationType.MOVE,
            timestamp=datetime.utcnow(),
            source_path=file1,
            destination_path=dest1,
            transaction_id="txn1",
            status=OperationStatus.COMPLETED
        ))

        # Operation 2: Rename
        file2 = self.test_dir / "file2.txt"
        dest2 = self.test_dir / "dest2.txt"
        file2.write_text("content2")
        file2.rename(dest2)
        operations.append(Operation(
            id=2,
            operation_type=OperationType.RENAME,
            timestamp=datetime.utcnow(),
            source_path=file2,
            destination_path=dest2,
            transaction_id="txn1",
            status=OperationStatus.COMPLETED
        ))

        # Rollback transaction
        result = self.executor.rollback_transaction("txn1", operations)

        self.assertTrue(result.success)
        self.assertEqual(result.operations_rolled_back, 2)
        self.assertEqual(result.operations_failed, 0)

        # Check files are back
        self.assertTrue(file1.exists())
        self.assertFalse(dest1.exists())
        self.assertTrue(file2.exists())
        self.assertFalse(dest2.exists())

    def test_rollback_transaction_partial_failure(self):
        """Test transaction rollback with partial failure."""
        operations = []

        # Operation 1: Move (will succeed)
        file1 = self.test_dir / "file1.txt"
        dest1 = self.test_dir / "dest1.txt"
        file1.write_text("content1")
        shutil.move(str(file1), str(dest1))
        operations.append(Operation(
            id=1,
            operation_type=OperationType.MOVE,
            timestamp=datetime.utcnow(),
            source_path=file1,
            destination_path=dest1,
            transaction_id="txn1",
            status=OperationStatus.COMPLETED
        ))

        # Operation 2: Move (will fail - file doesn't exist)
        file2 = self.test_dir / "file2.txt"
        dest2 = self.test_dir / "dest2.txt"
        operations.append(Operation(
            id=2,
            operation_type=OperationType.MOVE,
            timestamp=datetime.utcnow(),
            source_path=file2,
            destination_path=dest2,
            transaction_id="txn1",
            status=OperationStatus.COMPLETED
        ))

        # Rollback transaction (should stop at first failure)
        result = self.executor.rollback_transaction("txn1", operations)

        self.assertFalse(result.success)
        self.assertGreater(result.operations_failed, 0)


if __name__ == '__main__':
    unittest.main()
