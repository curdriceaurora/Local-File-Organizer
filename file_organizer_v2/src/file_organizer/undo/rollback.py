"""
Rollback executor for file operations.

This module executes rollback operations for undo/redo,
handling all operation types and transaction management.
"""

import logging
import shutil
from pathlib import Path
from typing import List, Optional

from ..history.models import Operation, OperationType, OperationStatus
from .validator import OperationValidator
from .models import RollbackResult

logger = logging.getLogger(__name__)


class RollbackExecutor:
    """
    Executes rollback operations for undo/redo.

    This class handles the actual file system operations required
    to undo or redo file operations.
    """

    def __init__(self, validator: Optional[OperationValidator] = None):
        """
        Initialize rollback executor.

        Args:
            validator: Operation validator
        """
        self.validator = validator or OperationValidator()
        self.trash_dir = self.validator.trash_dir

    def rollback_operation(self, operation: Operation) -> bool:
        """
        Rollback a single operation (undo).

        Args:
            operation: Operation to rollback

        Returns:
            True if successful, False otherwise
        """
        try:
            if operation.operation_type == OperationType.MOVE:
                return self.rollback_move(operation)
            elif operation.operation_type == OperationType.RENAME:
                return self.rollback_rename(operation)
            elif operation.operation_type == OperationType.DELETE:
                return self.rollback_delete(operation)
            elif operation.operation_type == OperationType.COPY:
                return self.rollback_copy(operation)
            elif operation.operation_type == OperationType.CREATE:
                return self.rollback_create(operation)
            else:
                logger.error(f"Unknown operation type: {operation.operation_type}")
                return False
        except Exception as e:
            logger.error(f"Failed to rollback operation {operation.id}: {e}", exc_info=True)
            return False

    def redo_operation(self, operation: Operation) -> bool:
        """
        Redo an operation (forward execution).

        Args:
            operation: Operation to redo

        Returns:
            True if successful, False otherwise
        """
        try:
            if operation.operation_type == OperationType.MOVE:
                return self.redo_move(operation)
            elif operation.operation_type == OperationType.RENAME:
                return self.redo_rename(operation)
            elif operation.operation_type == OperationType.DELETE:
                return self.redo_delete(operation)
            elif operation.operation_type == OperationType.COPY:
                return self.redo_copy(operation)
            elif operation.operation_type == OperationType.CREATE:
                return self.redo_create(operation)
            else:
                logger.error(f"Unknown operation type: {operation.operation_type}")
                return False
        except Exception as e:
            logger.error(f"Failed to redo operation {operation.id}: {e}", exc_info=True)
            return False

    def rollback_move(self, operation: Operation) -> bool:
        """
        Rollback a move operation (move file back to source).

        Args:
            operation: Move operation to rollback

        Returns:
            True if successful, False otherwise
        """
        source = operation.source_path
        destination = operation.destination_path

        logger.info(f"Rolling back move: {destination} -> {source}")

        try:
            # Ensure parent directory exists
            source.parent.mkdir(parents=True, exist_ok=True)

            # Move file back
            shutil.move(str(destination), str(source))

            logger.info(f"Successfully rolled back move operation {operation.id}")
            return True
        except Exception as e:
            logger.error(f"Failed to rollback move operation {operation.id}: {e}")
            return False

    def rollback_rename(self, operation: Operation) -> bool:
        """
        Rollback a rename operation (rename back to original).

        Args:
            operation: Rename operation to rollback

        Returns:
            True if successful, False otherwise
        """
        old_name = operation.source_path
        new_name = operation.destination_path

        logger.info(f"Rolling back rename: {new_name} -> {old_name}")

        try:
            # Rename back
            new_name.rename(old_name)

            logger.info(f"Successfully rolled back rename operation {operation.id}")
            return True
        except Exception as e:
            logger.error(f"Failed to rollback rename operation {operation.id}: {e}")
            return False

    def rollback_delete(self, operation: Operation) -> bool:
        """
        Rollback a delete operation (restore from trash).

        Args:
            operation: Delete operation to rollback

        Returns:
            True if successful, False otherwise
        """
        original_path = operation.source_path
        trash_path = self.validator._get_trash_path(operation)

        if not trash_path or not trash_path.exists():
            logger.error(f"File not found in trash for operation {operation.id}")
            return False

        logger.info(f"Rolling back delete: restoring {original_path} from trash")

        try:
            # Ensure parent directory exists
            original_path.parent.mkdir(parents=True, exist_ok=True)

            # Restore from trash
            shutil.move(str(trash_path), str(original_path))

            # Clean up trash directory for this operation
            if trash_path.parent.name == str(operation.id):
                try:
                    trash_path.parent.rmdir()
                except OSError:
                    pass  # Directory not empty or other issue

            logger.info(f"Successfully rolled back delete operation {operation.id}")
            return True
        except Exception as e:
            logger.error(f"Failed to rollback delete operation {operation.id}: {e}")
            return False

    def rollback_copy(self, operation: Operation) -> bool:
        """
        Rollback a copy operation (delete the copy).

        Args:
            operation: Copy operation to rollback

        Returns:
            True if successful, False otherwise
        """
        copy_path = operation.destination_path

        logger.info(f"Rolling back copy: deleting {copy_path}")

        try:
            # Move to trash instead of permanent delete
            trash_path = self._move_to_trash(copy_path, operation.id)

            logger.info(f"Successfully rolled back copy operation {operation.id}")
            return True
        except Exception as e:
            logger.error(f"Failed to rollback copy operation {operation.id}: {e}")
            return False

    def rollback_create(self, operation: Operation) -> bool:
        """
        Rollback a create operation (delete the created file).

        Args:
            operation: Create operation to rollback

        Returns:
            True if successful, False otherwise
        """
        created_path = operation.source_path

        logger.info(f"Rolling back create: deleting {created_path}")

        try:
            # Move to trash instead of permanent delete
            trash_path = self._move_to_trash(created_path, operation.id)

            logger.info(f"Successfully rolled back create operation {operation.id}")
            return True
        except Exception as e:
            logger.error(f"Failed to rollback create operation {operation.id}: {e}")
            return False

    def redo_move(self, operation: Operation) -> bool:
        """
        Redo a move operation (move file to destination again).

        Args:
            operation: Move operation to redo

        Returns:
            True if successful, False otherwise
        """
        source = operation.source_path
        destination = operation.destination_path

        logger.info(f"Redoing move: {source} -> {destination}")

        try:
            # Ensure parent directory exists
            destination.parent.mkdir(parents=True, exist_ok=True)

            # Move file
            shutil.move(str(source), str(destination))

            logger.info(f"Successfully redid move operation {operation.id}")
            return True
        except Exception as e:
            logger.error(f"Failed to redo move operation {operation.id}: {e}")
            return False

    def redo_rename(self, operation: Operation) -> bool:
        """
        Redo a rename operation.

        Args:
            operation: Rename operation to redo

        Returns:
            True if successful, False otherwise
        """
        old_name = operation.source_path
        new_name = operation.destination_path

        logger.info(f"Redoing rename: {old_name} -> {new_name}")

        try:
            # Rename
            old_name.rename(new_name)

            logger.info(f"Successfully redid rename operation {operation.id}")
            return True
        except Exception as e:
            logger.error(f"Failed to redo rename operation {operation.id}: {e}")
            return False

    def redo_delete(self, operation: Operation) -> bool:
        """
        Redo a delete operation (delete file again).

        Args:
            operation: Delete operation to redo

        Returns:
            True if successful, False otherwise
        """
        file_path = operation.source_path

        logger.info(f"Redoing delete: {file_path}")

        try:
            # Move to trash
            trash_path = self._move_to_trash(file_path, operation.id)

            logger.info(f"Successfully redid delete operation {operation.id}")
            return True
        except Exception as e:
            logger.error(f"Failed to redo delete operation {operation.id}: {e}")
            return False

    def redo_copy(self, operation: Operation) -> bool:
        """
        Redo a copy operation (create copy again).

        Args:
            operation: Copy operation to redo

        Returns:
            True if successful, False otherwise
        """
        source = operation.source_path
        destination = operation.destination_path

        logger.info(f"Redoing copy: {source} -> {destination}")

        try:
            # Ensure parent directory exists
            destination.parent.mkdir(parents=True, exist_ok=True)

            # Copy file
            if source.is_file():
                shutil.copy2(str(source), str(destination))
            elif source.is_dir():
                shutil.copytree(str(source), str(destination))
            else:
                logger.error(f"Source path is neither file nor directory: {source}")
                return False

            logger.info(f"Successfully redid copy operation {operation.id}")
            return True
        except Exception as e:
            logger.error(f"Failed to redo copy operation {operation.id}: {e}")
            return False

    def redo_create(self, operation: Operation) -> bool:
        """
        Redo a create operation (create file again).

        Args:
            operation: Create operation to redo

        Returns:
            True if successful, False otherwise
        """
        file_path = operation.source_path

        logger.info(f"Redoing create: {file_path}")

        try:
            # Ensure parent directory exists
            file_path.parent.mkdir(parents=True, exist_ok=True)

            # Create empty file or directory
            if operation.metadata.get('is_dir'):
                file_path.mkdir(parents=True, exist_ok=True)
            else:
                file_path.touch()

            logger.info(f"Successfully redid create operation {operation.id}")
            return True
        except Exception as e:
            logger.error(f"Failed to redo create operation {operation.id}: {e}")
            return False

    def rollback_transaction(
        self,
        transaction_id: str,
        operations: List[Operation]
    ) -> RollbackResult:
        """
        Rollback an entire transaction atomically.

        Args:
            transaction_id: Transaction ID
            operations: List of operations in transaction

        Returns:
            RollbackResult with details
        """
        logger.info(f"Rolling back transaction {transaction_id} with {len(operations)} operations")

        rolled_back = 0
        failed = 0
        errors = []
        warnings = []

        # Rollback operations in reverse order
        for operation in reversed(operations):
            try:
                success = self.rollback_operation(operation)
                if success:
                    rolled_back += 1
                else:
                    failed += 1
                    errors.append((operation.id, "Rollback operation returned False"))
            except Exception as e:
                failed += 1
                errors.append((operation.id, str(e)))
                logger.error(
                    f"Failed to rollback operation {operation.id} in transaction {transaction_id}: {e}"
                )

                # For atomic rollback, stop on first failure
                warnings.append(
                    f"Transaction rollback stopped at operation {operation.id}. "
                    f"{rolled_back} operations rolled back, {len(operations) - rolled_back - 1} pending."
                )
                break

        success = failed == 0
        result = RollbackResult(
            success=success,
            operations_rolled_back=rolled_back,
            operations_failed=failed,
            errors=errors,
            warnings=warnings
        )

        if success:
            logger.info(
                f"Successfully rolled back transaction {transaction_id}: "
                f"{rolled_back} operations"
            )
        else:
            logger.error(
                f"Failed to rollback transaction {transaction_id}: "
                f"{rolled_back} succeeded, {failed} failed"
            )

        return result

    def _move_to_trash(self, file_path: Path, operation_id: Optional[int] = None) -> Path:
        """
        Move a file to trash.

        Args:
            file_path: File to move to trash
            operation_id: Operation ID for organizing trash

        Returns:
            Path in trash
        """
        # Create trash directory
        if operation_id:
            trash_dir = self.trash_dir / str(operation_id)
        else:
            import uuid
            trash_dir = self.trash_dir / str(uuid.uuid4())

        trash_dir.mkdir(parents=True, exist_ok=True)

        # Move to trash
        trash_path = trash_dir / file_path.name
        shutil.move(str(file_path), str(trash_path))

        logger.debug(f"Moved {file_path} to trash: {trash_path}")
        return trash_path
