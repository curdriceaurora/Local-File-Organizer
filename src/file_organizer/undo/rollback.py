"""Rollback executor for file operations.

This module executes rollback operations for undo/redo,
handling all operation types and transaction management.
"""

from __future__ import annotations

import errno
import logging
import os
import shutil
import stat as stat_mod
from pathlib import Path

from ..history.models import Operation, OperationType
from ..utils.atomic_io import fsync_directory
from .models import RollbackResult
from .validator import OperationValidator

logger = logging.getLogger(__name__)


class RollbackExecutor:
    """Executes rollback operations for undo/redo.

    This class handles the actual file system operations required
    to undo or redo file operations.
    """

    def __init__(self, validator: OperationValidator | None = None):
        """Initialize rollback executor.

        Args:
            validator: Operation validator
        """
        self.validator = validator or OperationValidator()
        self.trash_dir = self.validator.trash_dir

    def _fsync_link_mutation(self, path: Path, operation_id: int) -> None:
        """Best-effort persistence after a completed link mutation."""
        try:
            fsync_directory(path)
        except OSError as exc:
            logger.warning(
                "Link mutation for operation %s succeeded, but directory fsync failed: %s",
                operation_id,
                exc,
                exc_info=True,
            )

    def _durable_move(self, src: Path, dst: Path) -> None:
        """Move *src* → *dst* durably, refusing symlinks and inode swaps.

        Hardening for the undo/rollback path (WP-2.2, #1227):

        - **Symlink refusal (anti-swap):** the source is ``lstat``-ed without
          following; if the recorded file was swapped for a symlink between the
          operation and this rollback, the move is refused (``S_ISLNK``) instead
          of dereferencing it into the restore location.
        - **Atomic same-filesystem rename:** ``os.replace`` moves the inode
          atomically; a cross-device move falls back to ``shutil.move``.
        - **Inode-swap verification:** a same-filesystem rename preserves the
          inode, so the file now at *dst* must carry the source's
          ``(st_dev, st_ino)``; a mismatch means it was swapped mid-move and is
          refused.
        - **Durability:** the destination directory is ``fsync``-ed so the
          rename survives a crash.

        Interim durability for the rollback path; the full cross-device
        crash-safe primitive (``undo/durable_move.py``) is WP-1.2b (#1248),
        which this helper will adopt once it lands.

        Raises:
            OSError: source is a symlink, an inode swap is detected, or the move
                itself fails.
        """
        src = Path(src)
        dst = Path(dst)

        src_stat = os.lstat(src)
        if stat_mod.S_ISLNK(src_stat.st_mode):
            raise OSError(f"refusing to move a symlink (possible swap): {src}")
        src_identity = (src_stat.st_dev, src_stat.st_ino)

        dst.parent.mkdir(parents=True, exist_ok=True)

        cross_device = False
        try:
            os.replace(src, dst)
        except OSError as exc:
            if exc.errno == errno.EXDEV:
                # Re-check the source immediately before the cross-device copy:
                # an attacker could have swapped it for a symlink since the
                # initial lstat, and shutil.move would dereference it.
                if stat_mod.S_ISLNK(os.lstat(src).st_mode):
                    raise OSError(f"refusing to move a symlink (possible swap): {src}") from exc
                cross_device = True
                shutil.move(str(src), str(dst))
            else:
                raise

        dst_stat = os.lstat(dst)
        if stat_mod.S_ISLNK(dst_stat.st_mode):
            raise OSError(f"destination is a symlink after move: {dst}")
        if not cross_device and (dst_stat.st_dev, dst_stat.st_ino) != src_identity:
            raise OSError(f"inode swap detected after rename to {dst}")

        # fsync the *containing* directory of each changed entry. fsync_directory
        # fsyncs ``path.parent``, so pass the file paths (dst/src), not their
        # parents, or we would flush the grandparent directory instead.
        fsync_directory(dst)
        if src.parent != dst.parent:
            try:
                fsync_directory(src)
            except OSError:  # pragma: no cover - best-effort source-dir flush
                logger.debug("Could not fsync source directory %s", src.parent)

    def rollback_operation(self, operation: Operation) -> bool:
        """Rollback a single operation (undo).

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
            elif operation.operation_type == OperationType.HARDLINK:
                return self.rollback_hardlink(operation)
            elif operation.operation_type == OperationType.SYMLINK:
                return self.rollback_symlink(operation)
            elif operation.operation_type == OperationType.CREATE:
                return self.rollback_create(operation)
            else:
                logger.error(f"Unknown operation type: {operation.operation_type}")
                return False
        except Exception as e:
            logger.error(f"Failed to rollback operation {operation.id}: {e}", exc_info=True)
            return False

    def redo_operation(self, operation: Operation) -> bool:
        """Redo an operation (forward execution).

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
            elif operation.operation_type == OperationType.HARDLINK:
                return self.redo_hardlink(operation)
            elif operation.operation_type == OperationType.SYMLINK:
                return self.redo_symlink(operation)
            elif operation.operation_type == OperationType.CREATE:
                return self.redo_create(operation)
            else:
                logger.error(f"Unknown operation type: {operation.operation_type}")
                return False
        except Exception as e:
            logger.error(f"Failed to redo operation {operation.id}: {e}", exc_info=True)
            return False

    def rollback_move(self, operation: Operation) -> bool:
        """Rollback a move operation (move file back to source).

        Args:
            operation: Move operation to rollback

        Returns:
            True if successful, False otherwise
        """
        source = operation.source_path
        destination = operation.destination_path

        if destination is None:
            logger.error("Cannot rollback move operation %s: no destination path", operation.id)
            return False

        logger.info(f"Rolling back move: {destination} -> {source}")

        try:
            # Move file back durably (symlink-refusing, inode-verified).
            self._durable_move(destination, source)

            logger.info(f"Successfully rolled back move operation {operation.id}")
            return True
        except Exception as e:
            logger.error(f"Failed to rollback move operation {operation.id}: {e}")
            return False

    def rollback_rename(self, operation: Operation) -> bool:
        """Rollback a rename operation (rename back to original).

        Args:
            operation: Rename operation to rollback

        Returns:
            True if successful, False otherwise
        """
        old_name = operation.source_path
        new_name = operation.destination_path

        if new_name is None:
            logger.error(f"Cannot rollback rename operation {operation.id}: no destination path")
            return False

        logger.info(f"Rolling back rename: {new_name} -> {old_name}")

        try:
            # Rename back durably (symlink-refusing, inode-verified).
            self._durable_move(new_name, old_name)

            logger.info(f"Successfully rolled back rename operation {operation.id}")
            return True
        except Exception as e:
            logger.error(f"Failed to rollback rename operation {operation.id}: {e}")
            return False

    def rollback_delete(self, operation: Operation) -> bool:
        """Rollback a delete operation (restore from trash).

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
            # Restore from trash durably (symlink-refusing, inode-verified).
            self._durable_move(trash_path, original_path)

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
        """Rollback a copy operation (delete the copy).

        Args:
            operation: Copy operation to rollback

        Returns:
            True if successful, False otherwise
        """
        copy_path = operation.destination_path

        if copy_path is None:
            logger.error(f"Cannot rollback copy operation {operation.id}: no destination path")
            return False

        logger.info(f"Rolling back copy: deleting {copy_path}")

        try:
            # Move to trash instead of permanent delete
            self._move_to_trash(copy_path, operation.id)

            logger.info(f"Successfully rolled back copy operation {operation.id}")
            return True
        except Exception as e:
            logger.error(f"Failed to rollback copy operation {operation.id}: {e}")
            return False

    def rollback_hardlink(self, operation: Operation) -> bool:
        """Rollback a hardlink operation by unlinking the link itself."""
        link_path = operation.destination_path

        if link_path is None:
            logger.error(f"Cannot rollback hardlink operation {operation.id}: no destination path")
            return False

        logger.info(f"Rolling back hardlink: deleting {link_path}")

        try:
            if link_path.is_symlink() or not link_path.exists():
                logger.error(
                    f"Refusing to rollback hardlink operation; destination is not a file: {link_path}"
                )
                return False
            if not operation.source_path.exists():
                logger.error(
                    f"Refusing to rollback hardlink operation; source is missing: {operation.source_path}"
                )
                return False
            source_stat = operation.source_path.stat()
            link_stat = link_path.stat()
            if (source_stat.st_dev, source_stat.st_ino) != (
                link_stat.st_dev,
                link_stat.st_ino,
            ):
                logger.error(
                    "Refusing to rollback hardlink operation; destination no longer "
                    f"matches source inode: {link_path}"
                )
                return False
            link_path.unlink()
            self._fsync_link_mutation(link_path, operation.id)
            logger.info(f"Successfully rolled back hardlink operation {operation.id}")
            return True
        except Exception as e:
            logger.error(f"Failed to rollback hardlink operation {operation.id}: {e}")
            return False

    def rollback_symlink(self, operation: Operation) -> bool:
        """Rollback a symlink operation by unlinking the link itself."""
        link_path = operation.destination_path

        if link_path is None:
            logger.error(f"Cannot rollback symlink operation {operation.id}: no destination path")
            return False

        logger.info(f"Rolling back symlink: deleting {link_path}")

        try:
            if not link_path.is_symlink():
                logger.error(
                    f"Refusing to rollback symlink operation; destination is not a symlink: {link_path}"
                )
                return False
            if link_path.resolve(strict=False) != operation.source_path.resolve(strict=False):
                logger.error(
                    "Refusing to rollback symlink operation; destination target no longer "
                    f"matches source: {link_path}"
                )
                return False
            link_path.unlink()
            self._fsync_link_mutation(link_path, operation.id)
            logger.info(f"Successfully rolled back symlink operation {operation.id}")
            return True
        except Exception as e:
            logger.error(f"Failed to rollback symlink operation {operation.id}: {e}")
            return False

    def rollback_create(self, operation: Operation) -> bool:
        """Rollback a create operation (delete the created file).

        Args:
            operation: Create operation to rollback

        Returns:
            True if successful, False otherwise
        """
        created_path = operation.source_path

        logger.info(f"Rolling back create: deleting {created_path}")

        try:
            # Move to trash instead of permanent delete
            self._move_to_trash(created_path, operation.id)

            logger.info(f"Successfully rolled back create operation {operation.id}")
            return True
        except Exception as e:
            logger.error(f"Failed to rollback create operation {operation.id}: {e}")
            return False

    def redo_move(self, operation: Operation) -> bool:
        """Redo a move operation (move file to destination again).

        Args:
            operation: Move operation to redo

        Returns:
            True if successful, False otherwise
        """
        source = operation.source_path
        destination = operation.destination_path

        if destination is None:
            logger.error(f"Cannot redo move operation {operation.id}: no destination path")
            return False

        logger.info(f"Redoing move: {source} -> {destination}")

        try:
            # Move file durably (symlink-refusing, inode-verified).
            self._durable_move(source, destination)

            logger.info(f"Successfully redid move operation {operation.id}")
            return True
        except Exception as e:
            logger.error(f"Failed to redo move operation {operation.id}: {e}")
            return False

    def redo_rename(self, operation: Operation) -> bool:
        """Redo a rename operation.

        Args:
            operation: Rename operation to redo

        Returns:
            True if successful, False otherwise
        """
        old_name = operation.source_path
        new_name = operation.destination_path

        if new_name is None:
            logger.error(f"Cannot redo rename operation {operation.id}: no destination path")
            return False

        logger.info(f"Redoing rename: {old_name} -> {new_name}")

        try:
            # Rename durably (symlink-refusing, inode-verified).
            self._durable_move(old_name, new_name)

            logger.info(f"Successfully redid rename operation {operation.id}")
            return True
        except Exception as e:
            logger.error(f"Failed to redo rename operation {operation.id}: {e}")
            return False

    def redo_delete(self, operation: Operation) -> bool:
        """Redo a delete operation (delete file again).

        Args:
            operation: Delete operation to redo

        Returns:
            True if successful, False otherwise
        """
        file_path = operation.source_path

        logger.info(f"Redoing delete: {file_path}")

        try:
            # Move to trash
            self._move_to_trash(file_path, operation.id)

            logger.info(f"Successfully redid delete operation {operation.id}")
            return True
        except Exception as e:
            logger.error(f"Failed to redo delete operation {operation.id}: {e}")
            return False

    def redo_copy(self, operation: Operation) -> bool:
        """Redo a copy operation (create copy again).

        Args:
            operation: Copy operation to redo

        Returns:
            True if successful, False otherwise
        """
        source = operation.source_path
        destination = operation.destination_path

        if destination is None:
            logger.error(f"Cannot redo copy operation {operation.id}: no destination path")
            return False

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

    def redo_hardlink(self, operation: Operation) -> bool:
        """Redo a hardlink operation."""
        source = operation.source_path
        destination = operation.destination_path

        if destination is None:
            logger.error(f"Cannot redo hardlink operation {operation.id}: no destination path")
            return False

        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.link(source, destination)
            self._fsync_link_mutation(destination, operation.id)
            logger.info(f"Successfully redid hardlink operation {operation.id}")
            return True
        except Exception as e:
            logger.error(f"Failed to redo hardlink operation {operation.id}: {e}")
            return False

    def redo_symlink(self, operation: Operation) -> bool:
        """Redo a symlink operation."""
        source = operation.source_path
        destination = operation.destination_path

        if destination is None:
            logger.error(f"Cannot redo symlink operation {operation.id}: no destination path")
            return False

        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.symlink_to(source)
            self._fsync_link_mutation(destination, operation.id)
            logger.info(f"Successfully redid symlink operation {operation.id}")
            return True
        except Exception as e:
            logger.error(f"Failed to redo symlink operation {operation.id}: {e}")
            return False

    def redo_create(self, operation: Operation) -> bool:
        """Redo a create operation (create file again).

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
            if operation.metadata.get("is_dir"):
                file_path.mkdir(parents=True, exist_ok=True)
            else:
                file_path.touch()

            logger.info(f"Successfully redid create operation {operation.id}")
            return True
        except Exception as e:
            logger.error(f"Failed to redo create operation {operation.id}: {e}")
            return False

    def rollback_transaction(
        self, transaction_id: str, operations: list[Operation]
    ) -> RollbackResult:
        """Rollback an entire transaction atomically.

        Args:
            transaction_id: Transaction ID
            operations: List of operations in transaction

        Returns:
            RollbackResult with details
        """
        logger.info(f"Rolling back transaction {transaction_id} with {len(operations)} operations")

        rolled_back = 0
        failed = 0
        errors: list[tuple[int, str]] = []
        warnings: list[str] = []

        # Rollback operations in reverse order
        for operation in reversed(operations):
            try:
                success = self.rollback_operation(operation)
                if success:
                    rolled_back += 1
                else:
                    failed += 1
                    errors.append((operation.id or 0, "Rollback operation returned False"))
            except Exception as e:
                failed += 1
                errors.append((operation.id or 0, str(e)))
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
            warnings=warnings,
        )

        if success:
            logger.info(
                f"Successfully rolled back transaction {transaction_id}: {rolled_back} operations"
            )
        else:
            logger.error(
                f"Failed to rollback transaction {transaction_id}: "
                f"{rolled_back} succeeded, {failed} failed"
            )

        return result

    def _move_to_trash(self, file_path: Path, operation_id: int | None = None) -> Path:
        """Move a file to trash.

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

        # Move to trash durably (symlink-refusing, inode-verified).
        trash_path = trash_dir / file_path.name
        self._durable_move(file_path, trash_path)

        logger.debug(f"Moved {file_path} to trash: {trash_path}")
        return trash_path
