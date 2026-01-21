"""
Transaction context manager for batch operations.

This module provides a context manager for grouping related file operations
into atomic transactions that can be committed or rolled back.
"""

import logging
from typing import Optional, Dict, Any
from pathlib import Path

from .tracker import OperationHistory
from .models import OperationType, OperationStatus

logger = logging.getLogger(__name__)


class OperationTransaction:
    """
    Context manager for batch file operations.

    This class provides transaction support for grouping related operations
    together. All operations within a transaction share the same transaction ID
    and can be committed or rolled back as a unit.

    Example:
        with OperationTransaction(history) as txn:
            txn.log_move(src1, dest1)
            txn.log_move(src2, dest2)
            # Automatically commits on successful exit
            # Automatically rolls back on exception
    """

    def __init__(self, history: OperationHistory, metadata: Optional[Dict[str, Any]] = None):
        """
        Initialize transaction context manager.

        Args:
            history: OperationHistory instance to use for logging
            metadata: Additional metadata about the transaction
        """
        self.history = history
        self.metadata = metadata or {}
        self.transaction_id: Optional[str] = None
        self._committed = False
        self._rolled_back = False

    def __enter__(self) -> 'OperationTransaction':
        """
        Enter transaction context.

        Returns:
            Self for method chaining
        """
        self.transaction_id = self.history.start_transaction(self.metadata)
        logger.debug(f"Entered transaction {self.transaction_id}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Exit transaction context.

        Automatically commits on success or rolls back on exception.

        Args:
            exc_type: Exception type if an exception occurred
            exc_val: Exception value if an exception occurred
            exc_tb: Exception traceback if an exception occurred
        """
        if exc_type is not None:
            # Exception occurred, rollback
            if not self._rolled_back:
                logger.warning(f"Transaction {self.transaction_id} failed with {exc_type.__name__}: {exc_val}")
                self.rollback()
        else:
            # Success, commit
            if not self._committed and not self._rolled_back:
                self.commit()

        logger.debug(f"Exited transaction {self.transaction_id}")

    def log_operation(
        self,
        operation_type: OperationType,
        source_path: Path,
        destination_path: Optional[Path] = None,
        metadata: Optional[Dict[str, Any]] = None,
        status: OperationStatus = OperationStatus.COMPLETED,
        error_message: Optional[str] = None
    ) -> int:
        """
        Log an operation within this transaction.

        Args:
            operation_type: Type of operation
            source_path: Source file path
            destination_path: Destination file path (for move/rename/copy)
            metadata: Additional metadata
            status: Operation status
            error_message: Error message if operation failed

        Returns:
            Operation ID
        """
        if self.transaction_id is None:
            raise RuntimeError("Cannot log operation outside of transaction context")

        return self.history.log_operation(
            operation_type=operation_type,
            source_path=source_path,
            destination_path=destination_path,
            metadata=metadata,
            transaction_id=self.transaction_id,
            status=status,
            error_message=error_message
        )

    def log_move(self, source_path: Path, destination_path: Path, metadata: Optional[Dict[str, Any]] = None) -> int:
        """
        Log a move operation.

        Args:
            source_path: Source file path
            destination_path: Destination file path
            metadata: Additional metadata

        Returns:
            Operation ID
        """
        return self.log_operation(
            operation_type=OperationType.MOVE,
            source_path=source_path,
            destination_path=destination_path,
            metadata=metadata
        )

    def log_rename(self, source_path: Path, destination_path: Path, metadata: Optional[Dict[str, Any]] = None) -> int:
        """
        Log a rename operation.

        Args:
            source_path: Source file path
            destination_path: Destination file path
            metadata: Additional metadata

        Returns:
            Operation ID
        """
        return self.log_operation(
            operation_type=OperationType.RENAME,
            source_path=source_path,
            destination_path=destination_path,
            metadata=metadata
        )

    def log_delete(self, source_path: Path, metadata: Optional[Dict[str, Any]] = None) -> int:
        """
        Log a delete operation.

        Args:
            source_path: Source file path
            metadata: Additional metadata

        Returns:
            Operation ID
        """
        return self.log_operation(
            operation_type=OperationType.DELETE,
            source_path=source_path,
            metadata=metadata
        )

    def log_copy(self, source_path: Path, destination_path: Path, metadata: Optional[Dict[str, Any]] = None) -> int:
        """
        Log a copy operation.

        Args:
            source_path: Source file path
            destination_path: Destination file path
            metadata: Additional metadata

        Returns:
            Operation ID
        """
        return self.log_operation(
            operation_type=OperationType.COPY,
            source_path=source_path,
            destination_path=destination_path,
            metadata=metadata
        )

    def log_create(self, source_path: Path, metadata: Optional[Dict[str, Any]] = None) -> int:
        """
        Log a create operation.

        Args:
            source_path: Source file path
            metadata: Additional metadata

        Returns:
            Operation ID
        """
        return self.log_operation(
            operation_type=OperationType.CREATE,
            source_path=source_path,
            metadata=metadata
        )

    def log_failed_operation(
        self,
        operation_type: OperationType,
        source_path: Path,
        error_message: str,
        destination_path: Optional[Path] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        Log a failed operation.

        Args:
            operation_type: Type of operation
            source_path: Source file path
            error_message: Error message describing the failure
            destination_path: Destination file path (for move/rename/copy)
            metadata: Additional metadata

        Returns:
            Operation ID
        """
        return self.log_operation(
            operation_type=operation_type,
            source_path=source_path,
            destination_path=destination_path,
            metadata=metadata,
            status=OperationStatus.FAILED,
            error_message=error_message
        )

    def commit(self) -> bool:
        """
        Commit the transaction, marking it as completed.

        Returns:
            True if successful, False otherwise
        """
        if self._committed:
            logger.warning(f"Transaction {self.transaction_id} already committed")
            return False

        if self._rolled_back:
            logger.warning(f"Cannot commit rolled back transaction {self.transaction_id}")
            return False

        if self.transaction_id is None:
            logger.warning("Cannot commit transaction outside of context")
            return False

        success = self.history.commit_transaction(self.transaction_id)
        if success:
            self._committed = True
            logger.info(f"Transaction {self.transaction_id} committed")
        return success

    def rollback(self) -> bool:
        """
        Rollback the transaction, marking all operations as rolled back.

        Returns:
            True if successful, False otherwise
        """
        if self._rolled_back:
            logger.warning(f"Transaction {self.transaction_id} already rolled back")
            return False

        if self._committed:
            logger.warning(f"Cannot rollback committed transaction {self.transaction_id}")
            return False

        if self.transaction_id is None:
            logger.warning("Cannot rollback transaction outside of context")
            return False

        success = self.history.rollback_transaction(self.transaction_id)
        if success:
            self._rolled_back = True
            logger.info(f"Transaction {self.transaction_id} rolled back")
        return success

    def get_transaction_id(self) -> Optional[str]:
        """
        Get the current transaction ID.

        Returns:
            Transaction ID or None if outside context
        """
        return self.transaction_id
