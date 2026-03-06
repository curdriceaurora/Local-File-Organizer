"""Extended tests for UndoManager.

Covers undo/redo operations, transaction handling, can_undo/can_redo,
stack management, and context manager.
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from file_organizer.history.models import Operation, OperationStatus, OperationType
from file_organizer.undo.models import RollbackResult, ValidationResult


@pytest.mark.unit
class TestUndoManager(unittest.TestCase):
    """Test cases for UndoManager."""

    def _make_manager(self):
        """Create UndoManager with mocked deps."""
        from file_organizer.undo.undo_manager import UndoManager

        history = MagicMock()
        validator = MagicMock()
        executor = MagicMock()
        mgr = UndoManager(
            history=history,
            validator=validator,
            executor=executor,
            max_stack_size=100,
        )
        return mgr, history, validator, executor

    def _make_op(self, op_id=1, status=OperationStatus.COMPLETED, op_type=OperationType.MOVE):
        return Operation(
            id=op_id,
            operation_type=op_type,
            timestamp=datetime.now(tz=UTC),
            source_path=MagicMock(),
            destination_path=MagicMock(),
            status=status,
        )

    # --- undo_last_operation ---

    def test_undo_last_no_operations(self):
        mgr, history, validator, executor = self._make_manager()
        history.get_operations.return_value = []
        self.assertFalse(mgr.undo_last_operation())

    def test_undo_last_success(self):
        mgr, history, validator, executor = self._make_manager()
        op = self._make_op()
        history.get_operations.side_effect = [
            [op],  # for undo_last_operation
            [op],  # for undo_operation
        ]
        validator.validate_undo.return_value = ValidationResult(can_proceed=True)
        executor.rollback_operation.return_value = True

        result = mgr.undo_last_operation()
        self.assertTrue(result)

    # --- undo_operation ---

    def test_undo_operation_not_found(self):
        mgr, history, validator, executor = self._make_manager()
        history.get_operations.return_value = []
        self.assertFalse(mgr.undo_operation(999))

    def test_undo_operation_already_rolled_back(self):
        mgr, history, validator, executor = self._make_manager()
        op = self._make_op(status=OperationStatus.ROLLED_BACK)
        history.get_operations.return_value = [op]
        self.assertFalse(mgr.undo_operation(1))

    def test_undo_operation_validation_fails(self):
        mgr, history, validator, executor = self._make_manager()
        op = self._make_op()
        history.get_operations.return_value = [op]
        validator.validate_undo.return_value = ValidationResult(
            can_proceed=False, error_message="conflict"
        )
        self.assertFalse(mgr.undo_operation(1))

    def test_undo_operation_with_warnings(self):
        mgr, history, validator, executor = self._make_manager()
        op = self._make_op()
        history.get_operations.return_value = [op]
        validator.validate_undo.return_value = ValidationResult(
            can_proceed=True, warnings=["some warning"]
        )
        executor.rollback_operation.return_value = True
        self.assertTrue(mgr.undo_operation(1))

    def test_undo_operation_executor_fails(self):
        mgr, history, validator, executor = self._make_manager()
        op = self._make_op()
        history.get_operations.return_value = [op]
        validator.validate_undo.return_value = ValidationResult(can_proceed=True)
        executor.rollback_operation.return_value = False
        self.assertFalse(mgr.undo_operation(1))

    # --- undo_transaction ---

    def test_undo_transaction_not_found(self):
        mgr, history, validator, executor = self._make_manager()
        history.get_transaction.return_value = None
        self.assertFalse(mgr.undo_transaction("txn-1"))

    def test_undo_transaction_no_operations(self):
        mgr, history, validator, executor = self._make_manager()
        history.get_transaction.return_value = MagicMock()
        history.get_operations.return_value = []
        self.assertFalse(mgr.undo_transaction("txn-1"))

    def test_undo_transaction_validation_fails(self):
        mgr, history, validator, executor = self._make_manager()
        history.get_transaction.return_value = MagicMock()
        op = self._make_op()
        history.get_operations.return_value = [op]
        validator.validate_undo.return_value = ValidationResult(
            can_proceed=False, error_message="bad"
        )
        self.assertFalse(mgr.undo_transaction("txn-1"))

    def test_undo_transaction_success(self):
        mgr, history, validator, executor = self._make_manager()
        history.get_transaction.return_value = MagicMock()
        op = self._make_op()
        history.get_operations.return_value = [op]
        validator.validate_undo.return_value = ValidationResult(can_proceed=True)
        executor.rollback_transaction.return_value = RollbackResult(
            success=True, operations_rolled_back=1
        )
        self.assertTrue(mgr.undo_transaction("txn-1"))

    def test_undo_transaction_rollback_fails(self):
        mgr, history, validator, executor = self._make_manager()
        history.get_transaction.return_value = MagicMock()
        op = self._make_op()
        history.get_operations.return_value = [op]
        validator.validate_undo.return_value = ValidationResult(can_proceed=True)
        executor.rollback_transaction.return_value = RollbackResult(
            success=False, operations_rolled_back=0, operations_failed=1
        )
        self.assertFalse(mgr.undo_transaction("txn-1"))

    # --- redo_last_operation ---

    def test_redo_last_no_operations(self):
        mgr, history, validator, executor = self._make_manager()
        history.get_operations.return_value = []
        self.assertFalse(mgr.redo_last_operation())

    def test_redo_last_success(self):
        mgr, history, validator, executor = self._make_manager()
        op = self._make_op(status=OperationStatus.ROLLED_BACK)
        history.get_operations.side_effect = [
            [op],  # for redo_last
            [op],  # for redo_operation
        ]
        validator.validate_redo.return_value = ValidationResult(can_proceed=True)
        executor.redo_operation.return_value = True
        self.assertTrue(mgr.redo_last_operation())

    # --- redo_operation ---

    def test_redo_operation_not_found(self):
        mgr, history, validator, executor = self._make_manager()
        history.get_operations.return_value = []
        self.assertFalse(mgr.redo_operation(999))

    def test_redo_operation_not_rolled_back(self):
        mgr, history, validator, executor = self._make_manager()
        op = self._make_op(status=OperationStatus.COMPLETED)
        history.get_operations.return_value = [op]
        self.assertFalse(mgr.redo_operation(1))

    def test_redo_operation_validation_fails(self):
        mgr, history, validator, executor = self._make_manager()
        op = self._make_op(status=OperationStatus.ROLLED_BACK)
        history.get_operations.return_value = [op]
        validator.validate_redo.return_value = ValidationResult(
            can_proceed=False, error_message="conflict"
        )
        self.assertFalse(mgr.redo_operation(1))

    def test_redo_operation_with_warnings(self):
        mgr, history, validator, executor = self._make_manager()
        op = self._make_op(status=OperationStatus.ROLLED_BACK)
        history.get_operations.return_value = [op]
        validator.validate_redo.return_value = ValidationResult(can_proceed=True, warnings=["warn"])
        executor.redo_operation.return_value = True
        self.assertTrue(mgr.redo_operation(1))

    def test_redo_operation_executor_fails(self):
        mgr, history, validator, executor = self._make_manager()
        op = self._make_op(status=OperationStatus.ROLLED_BACK)
        history.get_operations.return_value = [op]
        validator.validate_redo.return_value = ValidationResult(can_proceed=True)
        executor.redo_operation.return_value = False
        self.assertFalse(mgr.redo_operation(1))

    # --- redo_transaction ---

    def test_redo_transaction_no_ops(self):
        mgr, history, validator, executor = self._make_manager()
        history.get_operations.return_value = []
        self.assertFalse(mgr.redo_transaction("txn-1"))

    def test_redo_transaction_validation_fails(self):
        mgr, history, validator, executor = self._make_manager()
        op = self._make_op(status=OperationStatus.ROLLED_BACK)
        history.get_operations.return_value = [op]
        validator.validate_redo.return_value = ValidationResult(
            can_proceed=False, error_message="bad"
        )
        self.assertFalse(mgr.redo_transaction("txn-1"))

    def test_redo_transaction_success(self):
        mgr, history, validator, executor = self._make_manager()
        op = self._make_op(status=OperationStatus.ROLLED_BACK)
        history.get_operations.return_value = [op]
        validator.validate_redo.return_value = ValidationResult(can_proceed=True)
        executor.redo_operation.return_value = True
        self.assertTrue(mgr.redo_transaction("txn-1"))

    def test_redo_transaction_redo_fails(self):
        mgr, history, validator, executor = self._make_manager()
        op = self._make_op(status=OperationStatus.ROLLED_BACK)
        history.get_operations.return_value = [op]
        validator.validate_redo.return_value = ValidationResult(can_proceed=True)
        executor.redo_operation.return_value = False
        self.assertFalse(mgr.redo_transaction("txn-1"))

    def test_redo_transaction_exception(self):
        mgr, history, validator, executor = self._make_manager()
        op = self._make_op(status=OperationStatus.ROLLED_BACK)
        history.get_operations.return_value = [op]
        validator.validate_redo.return_value = ValidationResult(can_proceed=True)
        executor.redo_operation.side_effect = RuntimeError("boom")
        self.assertFalse(mgr.redo_transaction("txn-1"))

    # --- can_undo / can_redo ---

    def test_can_undo_not_found(self):
        mgr, history, validator, executor = self._make_manager()
        history.get_operations.return_value = []
        can, reason = mgr.can_undo(999)
        self.assertFalse(can)
        self.assertIn("not found", reason)

    def test_can_undo_already_rolled_back(self):
        mgr, history, validator, executor = self._make_manager()
        op = self._make_op(status=OperationStatus.ROLLED_BACK)
        history.get_operations.return_value = [op]
        can, reason = mgr.can_undo(1)
        self.assertFalse(can)
        self.assertIn("already been rolled back", reason)

    def test_can_undo_yes(self):
        mgr, history, validator, executor = self._make_manager()
        op = self._make_op()
        history.get_operations.return_value = [op]
        validator.validate_undo.return_value = ValidationResult(can_proceed=True)
        can, reason = mgr.can_undo(1)
        self.assertTrue(can)

    def test_can_undo_no(self):
        mgr, history, validator, executor = self._make_manager()
        op = self._make_op()
        history.get_operations.return_value = [op]
        validator.validate_undo.return_value = ValidationResult(
            can_proceed=False, error_message="conflict"
        )
        can, reason = mgr.can_undo(1)
        self.assertFalse(can)

    def test_can_redo_not_found(self):
        mgr, history, validator, executor = self._make_manager()
        history.get_operations.return_value = []
        can, reason = mgr.can_redo(999)
        self.assertFalse(can)

    def test_can_redo_not_rolled_back(self):
        mgr, history, validator, executor = self._make_manager()
        op = self._make_op(status=OperationStatus.COMPLETED)
        history.get_operations.return_value = [op]
        can, reason = mgr.can_redo(1)
        self.assertFalse(can)

    def test_can_redo_yes(self):
        mgr, history, validator, executor = self._make_manager()
        op = self._make_op(status=OperationStatus.ROLLED_BACK)
        history.get_operations.return_value = [op]
        validator.validate_redo.return_value = ValidationResult(can_proceed=True)
        can, reason = mgr.can_redo(1)
        self.assertTrue(can)

    def test_can_redo_no(self):
        mgr, history, validator, executor = self._make_manager()
        op = self._make_op(status=OperationStatus.ROLLED_BACK)
        history.get_operations.return_value = [op]
        validator.validate_redo.return_value = ValidationResult(
            can_proceed=False, error_message="conflict"
        )
        can, reason = mgr.can_redo(1)
        self.assertFalse(can)

    # --- stacks ---

    def test_get_undo_stack(self):
        mgr, history, validator, executor = self._make_manager()
        ops = [self._make_op()]
        history.get_operations.return_value = ops
        result = mgr.get_undo_stack()
        self.assertEqual(result, ops)

    def test_get_redo_stack(self):
        mgr, history, validator, executor = self._make_manager()
        ops = [self._make_op(status=OperationStatus.ROLLED_BACK)]
        history.get_operations.return_value = ops
        result = mgr.get_redo_stack()
        self.assertEqual(result, ops)

    def test_clear_redo_stack(self):
        mgr, history, validator, executor = self._make_manager()
        # Should not raise
        mgr.clear_redo_stack()

    # --- context manager and close ---

    def test_close(self):
        mgr, history, validator, executor = self._make_manager()
        mgr.close()
        history.close.assert_called_once()

    def test_context_manager(self):
        from file_organizer.undo.undo_manager import UndoManager

        history = MagicMock()
        validator = MagicMock()
        executor = MagicMock()
        with UndoManager(history=history, validator=validator, executor=executor) as mgr:
            self.assertIsNotNone(mgr)
        history.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
