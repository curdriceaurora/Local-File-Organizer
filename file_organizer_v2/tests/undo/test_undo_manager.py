"""
Unit tests for UndoManager.

Tests high-level undo/redo management functionality.
"""

import shutil
import tempfile
import unittest
from pathlib import Path

from file_organizer.history.models import OperationStatus, OperationType
from file_organizer.history.tracker import OperationHistory
from file_organizer.undo.rollback import RollbackExecutor
from file_organizer.undo.undo_manager import UndoManager
from file_organizer.undo.validator import OperationValidator


class TestUndoManager(unittest.TestCase):
    """Test cases for UndoManager."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_dir = Path(tempfile.mkdtemp())
        self.db_path = self.test_dir / "test_history.db"
        self.trash_dir = self.test_dir / "trash"

        # Create components
        self.history = OperationHistory(db_path=self.db_path)
        self.validator = OperationValidator(trash_dir=self.trash_dir)
        self.executor = RollbackExecutor(validator=self.validator)
        self.manager = UndoManager(
            history=self.history,
            validator=self.validator,
            executor=self.executor
        )

        # Create test files
        self.source_file = self.test_dir / "source.txt"
        self.dest_file = self.test_dir / "dest.txt"
        self.source_file.write_text("test content")

    def tearDown(self):
        """Clean up test fixtures."""
        self.manager.close()
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_undo_last_operation(self):
        """Test undoing the last operation."""
        # Log a move operation
        shutil.move(str(self.source_file), str(self.dest_file))
        self.history.log_operation(
            operation_type=OperationType.MOVE,
            source_path=self.source_file,
            destination_path=self.dest_file
        )

        # Undo
        success = self.manager.undo_last_operation()

        self.assertTrue(success)
        self.assertTrue(self.source_file.exists())
        self.assertFalse(self.dest_file.exists())

        # Check operation status updated
        operations = self.history.get_operations(limit=1)
        self.assertEqual(operations[0].status, OperationStatus.ROLLED_BACK)

    def test_undo_operation_by_id(self):
        """Test undoing a specific operation."""
        # Log operation
        shutil.move(str(self.source_file), str(self.dest_file))
        op_id = self.history.log_operation(
            operation_type=OperationType.MOVE,
            source_path=self.source_file,
            destination_path=self.dest_file
        )

        # Undo by ID
        success = self.manager.undo_operation(op_id)

        self.assertTrue(success)
        self.assertTrue(self.source_file.exists())
        self.assertFalse(self.dest_file.exists())

    def test_undo_transaction(self):
        """Test undoing an entire transaction."""
        # Start transaction
        txn_id = self.history.start_transaction(metadata={"test": "transaction"})

        # Log multiple operations
        file1 = self.test_dir / "file1.txt"
        dest1 = self.test_dir / "dest1.txt"
        file1.write_text("content1")
        shutil.move(str(file1), str(dest1))
        self.history.log_operation(
            operation_type=OperationType.MOVE,
            source_path=file1,
            destination_path=dest1,
            transaction_id=txn_id
        )

        file2 = self.test_dir / "file2.txt"
        dest2 = self.test_dir / "dest2.txt"
        file2.write_text("content2")
        shutil.move(str(file2), str(dest2))
        self.history.log_operation(
            operation_type=OperationType.MOVE,
            source_path=file2,
            destination_path=dest2,
            transaction_id=txn_id
        )

        # Commit transaction
        self.history.commit_transaction(txn_id)

        # Undo transaction
        success = self.manager.undo_transaction(txn_id)

        self.assertTrue(success)
        self.assertTrue(file1.exists())
        self.assertFalse(dest1.exists())
        self.assertTrue(file2.exists())
        self.assertFalse(dest2.exists())

    def test_redo_last_operation(self):
        """Test redoing the last rolled back operation."""
        # Log and undo operation
        shutil.move(str(self.source_file), str(self.dest_file))
        self.history.log_operation(
            operation_type=OperationType.MOVE,
            source_path=self.source_file,
            destination_path=self.dest_file
        )
        self.manager.undo_last_operation()

        # Redo
        success = self.manager.redo_last_operation()

        self.assertTrue(success)
        self.assertFalse(self.source_file.exists())
        self.assertTrue(self.dest_file.exists())

        # Check status updated
        operations = self.history.get_operations(limit=1)
        self.assertEqual(operations[0].status, OperationStatus.COMPLETED)

    def test_redo_operation_by_id(self):
        """Test redoing a specific operation."""
        # Log and undo operation
        shutil.move(str(self.source_file), str(self.dest_file))
        op_id = self.history.log_operation(
            operation_type=OperationType.MOVE,
            source_path=self.source_file,
            destination_path=self.dest_file
        )
        self.manager.undo_operation(op_id)

        # Redo by ID
        success = self.manager.redo_operation(op_id)

        self.assertTrue(success)
        self.assertFalse(self.source_file.exists())
        self.assertTrue(self.dest_file.exists())

    def test_can_undo(self):
        """Test checking if operation can be undone."""
        # Log operation
        shutil.move(str(self.source_file), str(self.dest_file))
        op_id = self.history.log_operation(
            operation_type=OperationType.MOVE,
            source_path=self.source_file,
            destination_path=self.dest_file
        )

        can_undo, reason = self.manager.can_undo(op_id)

        self.assertTrue(can_undo)
        self.assertIn("can be undone", reason)

    def test_can_undo_already_rolled_back(self):
        """Test checking undo on already rolled back operation."""
        # Log and undo operation
        shutil.move(str(self.source_file), str(self.dest_file))
        op_id = self.history.log_operation(
            operation_type=OperationType.MOVE,
            source_path=self.source_file,
            destination_path=self.dest_file
        )
        self.manager.undo_operation(op_id)

        can_undo, reason = self.manager.can_undo(op_id)

        self.assertFalse(can_undo)
        self.assertIn("already been rolled back", reason)

    def test_can_redo(self):
        """Test checking if operation can be redone."""
        # Log and undo operation
        shutil.move(str(self.source_file), str(self.dest_file))
        op_id = self.history.log_operation(
            operation_type=OperationType.MOVE,
            source_path=self.source_file,
            destination_path=self.dest_file
        )
        self.manager.undo_operation(op_id)

        can_redo, reason = self.manager.can_redo(op_id)

        self.assertTrue(can_redo)
        self.assertIn("can be redone", reason)

    def test_can_redo_not_rolled_back(self):
        """Test checking redo on non-rolled-back operation."""
        # Log operation
        shutil.move(str(self.source_file), str(self.dest_file))
        op_id = self.history.log_operation(
            operation_type=OperationType.MOVE,
            source_path=self.source_file,
            destination_path=self.dest_file
        )

        can_redo, reason = self.manager.can_redo(op_id)

        self.assertFalse(can_redo)
        self.assertIn("rolled back", reason)

    def test_get_undo_stack(self):
        """Test getting undo stack."""
        # Log operations
        shutil.move(str(self.source_file), str(self.dest_file))
        self.history.log_operation(
            operation_type=OperationType.MOVE,
            source_path=self.source_file,
            destination_path=self.dest_file
        )

        undo_stack = self.manager.get_undo_stack()

        self.assertEqual(len(undo_stack), 1)
        self.assertEqual(undo_stack[0].status, OperationStatus.COMPLETED)

    def test_get_redo_stack(self):
        """Test getting redo stack."""
        # Log and undo operation
        shutil.move(str(self.source_file), str(self.dest_file))
        op_id = self.history.log_operation(
            operation_type=OperationType.MOVE,
            source_path=self.source_file,
            destination_path=self.dest_file
        )
        self.manager.undo_operation(op_id)

        redo_stack = self.manager.get_redo_stack()

        self.assertEqual(len(redo_stack), 1)
        self.assertEqual(redo_stack[0].status, OperationStatus.ROLLED_BACK)

    def test_undo_no_operations(self):
        """Test undo when no operations exist."""
        success = self.manager.undo_last_operation()

        self.assertFalse(success)

    def test_redo_no_operations(self):
        """Test redo when no rolled back operations exist."""
        success = self.manager.redo_last_operation()

        self.assertFalse(success)

    def test_undo_invalid_operation_id(self):
        """Test undo with invalid operation ID."""
        success = self.manager.undo_operation(99999)

        self.assertFalse(success)

    def test_redo_invalid_operation_id(self):
        """Test redo with invalid operation ID."""
        success = self.manager.redo_operation(99999)

        self.assertFalse(success)


if __name__ == '__main__':
    unittest.main()
