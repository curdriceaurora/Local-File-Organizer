"""
Undo/redo manager for file operations.

This module provides the main interface for undoing and redoing file operations,
managing undo/redo stacks, and coordinating validation and rollback.
"""

import logging
from pathlib import Path
from typing import Optional, List, Tuple

from ..history.tracker import OperationHistory
from ..history.models import Operation, OperationStatus, Transaction
from .validator import OperationValidator
from .rollback import RollbackExecutor
from .models import ValidationResult, RollbackResult

logger = logging.getLogger(__name__)


class UndoManager:
    """
    Main interface for undo/redo operations.

    This class manages undo/redo stacks, coordinates validation and rollback,
    and provides high-level methods for undoing and redoing operations.
    """

    def __init__(
        self,
        history: Optional[OperationHistory] = None,
        validator: Optional[OperationValidator] = None,
        executor: Optional[RollbackExecutor] = None,
        max_stack_size: int = 1000
    ):
        """
        Initialize undo manager.

        Args:
            history: Operation history tracker
            validator: Operation validator
            executor: Rollback executor
            max_stack_size: Maximum size of undo/redo stacks
        """
        self.history = history or OperationHistory()
        self.validator = validator or OperationValidator()
        self.executor = executor or RollbackExecutor(self.validator)
        self.max_stack_size = max_stack_size
        logger.info("Undo manager initialized")

    def undo_last_operation(self) -> bool:
        """
        Undo the last completed operation.

        Returns:
            True if successful, False otherwise
        """
        # Get last completed operation
        operations = self.history.get_operations(
            status=OperationStatus.COMPLETED,
            limit=1
        )

        if not operations:
            logger.info("No operations to undo")
            return False

        operation = operations[0]
        logger.info(f"Undoing last operation: {operation.id}")
        return self.undo_operation(operation.id)

    def undo_operation(self, operation_id: int) -> bool:
        """
        Undo a specific operation by ID.

        Args:
            operation_id: ID of operation to undo

        Returns:
            True if successful, False otherwise
        """
        # Get operation
        operations = self.history.get_operations(limit=self.max_stack_size)
        operation = next((op for op in operations if op.id == operation_id), None)

        if not operation:
            logger.error(f"Operation {operation_id} not found")
            return False

        # Check if already undone
        if operation.status == OperationStatus.ROLLED_BACK:
            logger.warning(f"Operation {operation_id} has already been rolled back")
            return False

        # Validate
        validation = self.validator.validate_undo(operation)
        if not validation.can_proceed:
            logger.error(f"Undo validation failed: {validation.error_message}")
            logger.debug(f"Conflicts: {validation.conflicts}")
            return False

        # Log warnings
        for warning in validation.warnings:
            logger.warning(warning)

        # Execute rollback
        success = self.executor.rollback_operation(operation)

        if success:
            # Update operation status
            self.history.db.execute_query(
                "UPDATE operations SET status = ? WHERE id = ?",
                (OperationStatus.ROLLED_BACK.value, operation_id)
            )
            self.history.db.get_connection().commit()
            logger.info(f"Successfully undid operation {operation_id}")

            # Clear redo stack (undo creates new timeline)
            self.clear_redo_stack()
        else:
            logger.error(f"Failed to undo operation {operation_id}")

        return success

    def undo_transaction(self, transaction_id: str) -> bool:
        """
        Undo an entire transaction atomically.

        Args:
            transaction_id: ID of transaction to undo

        Returns:
            True if successful, False otherwise
        """
        logger.info(f"Undoing transaction {transaction_id}")

        # Get transaction
        transaction = self.history.get_transaction(transaction_id)
        if not transaction:
            logger.error(f"Transaction {transaction_id} not found")
            return False

        # Get all operations in transaction
        operations = self.history.get_operations(
            transaction_id=transaction_id,
            status=OperationStatus.COMPLETED
        )

        if not operations:
            logger.warning(f"No operations to undo in transaction {transaction_id}")
            return False

        # Validate all operations first
        logger.debug(f"Validating {len(operations)} operations...")
        for operation in operations:
            validation = self.validator.validate_undo(operation)
            if not validation.can_proceed:
                logger.error(
                    f"Transaction validation failed at operation {operation.id}: "
                    f"{validation.error_message}"
                )
                return False

        # Execute rollback
        result = self.executor.rollback_transaction(transaction_id, operations)

        if result.success:
            logger.info(
                f"Successfully undid transaction {transaction_id}: "
                f"{result.operations_rolled_back} operations"
            )
            # Clear redo stack
            self.clear_redo_stack()
        else:
            logger.error(
                f"Failed to undo transaction {transaction_id}: "
                f"{result.operations_rolled_back} succeeded, {result.operations_failed} failed"
            )

        return result.success

    def redo_last_operation(self) -> bool:
        """
        Redo the last rolled back operation.

        Returns:
            True if successful, False otherwise
        """
        # Get last rolled back operation
        operations = self.history.get_operations(
            status=OperationStatus.ROLLED_BACK,
            limit=1
        )

        if not operations:
            logger.info("No operations to redo")
            return False

        operation = operations[0]
        logger.info(f"Redoing last operation: {operation.id}")
        return self.redo_operation(operation.id)

    def redo_operation(self, operation_id: int) -> bool:
        """
        Redo a specific operation by ID.

        Args:
            operation_id: ID of operation to redo

        Returns:
            True if successful, False otherwise
        """
        # Get operation
        operations = self.history.get_operations(limit=self.max_stack_size)
        operation = next((op for op in operations if op.id == operation_id), None)

        if not operation:
            logger.error(f"Operation {operation_id} not found")
            return False

        # Check if can redo
        if operation.status != OperationStatus.ROLLED_BACK:
            logger.warning(f"Operation {operation_id} is not in rolled back state")
            return False

        # Validate
        validation = self.validator.validate_redo(operation)
        if not validation.can_proceed:
            logger.error(f"Redo validation failed: {validation.error_message}")
            logger.debug(f"Conflicts: {validation.conflicts}")
            return False

        # Log warnings
        for warning in validation.warnings:
            logger.warning(warning)

        # Execute redo (forward the operation)
        success = self.executor.redo_operation(operation)

        if success:
            # Update operation status back to completed
            self.history.db.execute_query(
                "UPDATE operations SET status = ? WHERE id = ?",
                (OperationStatus.COMPLETED.value, operation_id)
            )
            self.history.db.get_connection().commit()
            logger.info(f"Successfully redid operation {operation_id}")
        else:
            logger.error(f"Failed to redo operation {operation_id}")

        return success

    def can_undo(self, operation_id: int) -> Tuple[bool, str]:
        """
        Check if an operation can be undone.

        Args:
            operation_id: ID of operation to check

        Returns:
            Tuple of (can_undo, reason)
        """
        # Get operation
        operations = self.history.get_operations(limit=self.max_stack_size)
        operation = next((op for op in operations if op.id == operation_id), None)

        if not operation:
            return (False, f"Operation {operation_id} not found")

        if operation.status == OperationStatus.ROLLED_BACK:
            return (False, "Operation has already been rolled back")

        # Validate
        validation = self.validator.validate_undo(operation)
        if validation.can_proceed:
            return (True, "Operation can be undone")
        else:
            return (False, validation.error_message or "Validation failed")

    def can_redo(self, operation_id: int) -> Tuple[bool, str]:
        """
        Check if an operation can be redone.

        Args:
            operation_id: ID of operation to check

        Returns:
            Tuple of (can_redo, reason)
        """
        # Get operation
        operations = self.history.get_operations(limit=self.max_stack_size)
        operation = next((op for op in operations if op.id == operation_id), None)

        if not operation:
            return (False, f"Operation {operation_id} not found")

        if operation.status != OperationStatus.ROLLED_BACK:
            return (False, "Can only redo operations that have been rolled back")

        # Validate
        validation = self.validator.validate_redo(operation)
        if validation.can_proceed:
            return (True, "Operation can be redone")
        else:
            return (False, validation.error_message or "Validation failed")

    def get_undo_stack(self) -> List[Operation]:
        """
        Get list of operations that can be undone.

        Returns:
            List of completed operations (undo stack)
        """
        return self.history.get_operations(
            status=OperationStatus.COMPLETED,
            limit=self.max_stack_size
        )

    def get_redo_stack(self) -> List[Operation]:
        """
        Get list of operations that can be redone.

        Returns:
            List of rolled back operations (redo stack)
        """
        return self.history.get_operations(
            status=OperationStatus.ROLLED_BACK,
            limit=self.max_stack_size
        )

    def clear_redo_stack(self) -> None:
        """
        Clear the redo stack.

        This is typically called after a new operation or undo,
        as they invalidate the redo timeline.
        """
        # Note: We don't actually delete rolled back operations from the database
        # as they're part of the history. Instead, the redo stack is just a view
        # of rolled back operations. If we wanted to truly clear it, we could
        # update the status to a special "redo_cleared" status.
        logger.debug("Redo stack cleared (new timeline created)")

    def close(self) -> None:
        """Close resources."""
        self.history.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
