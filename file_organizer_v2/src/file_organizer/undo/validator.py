"""
Operation validator for undo/redo operations.

This module provides validation logic to ensure undo/redo operations
can be safely executed without conflicts.
"""

import hashlib
import logging
import os
import shutil
from pathlib import Path
from typing import Optional

from ..history.models import Operation, OperationType, OperationStatus
from .models import ValidationResult, Conflict, ConflictType

logger = logging.getLogger(__name__)


class OperationValidator:
    """
    Validates operations before undo/redo execution.

    This class performs comprehensive checks to ensure operations
    can be safely executed, including file integrity, path availability,
    and conflict detection.
    """

    def __init__(self, trash_dir: Optional[Path] = None):
        """
        Initialize the validator.

        Args:
            trash_dir: Directory for deleted files. Defaults to ~/.file_organizer/trash/
        """
        if trash_dir is None:
            trash_dir = Path.home() / ".file_organizer" / "trash"
        self.trash_dir = trash_dir
        self.trash_dir.mkdir(parents=True, exist_ok=True)

    def validate_undo(self, operation: Operation) -> ValidationResult:
        """
        Validate an undo operation.

        Args:
            operation: Operation to validate

        Returns:
            ValidationResult indicating if undo can proceed
        """
        conflicts = []
        warnings = []

        # Check operation status
        if operation.status == OperationStatus.ROLLED_BACK:
            return ValidationResult(
                can_proceed=False,
                error_message="Operation has already been rolled back"
            )

        if operation.status == OperationStatus.FAILED:
            warnings.append("Operation originally failed, undo may not restore original state")

        # Validate based on operation type
        if operation.operation_type == OperationType.MOVE:
            conflicts.extend(self._validate_undo_move(operation))
        elif operation.operation_type == OperationType.RENAME:
            conflicts.extend(self._validate_undo_rename(operation))
        elif operation.operation_type == OperationType.DELETE:
            conflicts.extend(self._validate_undo_delete(operation))
        elif operation.operation_type == OperationType.COPY:
            conflicts.extend(self._validate_undo_copy(operation))
        elif operation.operation_type == OperationType.CREATE:
            conflicts.extend(self._validate_undo_create(operation))
        else:
            return ValidationResult(
                can_proceed=False,
                error_message=f"Unknown operation type: {operation.operation_type}"
            )

        # Determine if we can proceed
        can_proceed = len(conflicts) == 0
        error_message = None if can_proceed else f"Found {len(conflicts)} conflicts preventing undo"

        return ValidationResult(
            can_proceed=can_proceed,
            conflicts=conflicts,
            warnings=warnings,
            error_message=error_message
        )

    def validate_redo(self, operation: Operation) -> ValidationResult:
        """
        Validate a redo operation.

        Args:
            operation: Operation to validate

        Returns:
            ValidationResult indicating if redo can proceed
        """
        conflicts = []
        warnings = []

        # Check operation status - must be rolled back to redo
        if operation.status != OperationStatus.ROLLED_BACK:
            return ValidationResult(
                can_proceed=False,
                error_message="Can only redo operations that have been rolled back"
            )

        # Validate based on operation type (similar to original operation)
        if operation.operation_type == OperationType.MOVE:
            conflicts.extend(self._validate_redo_move(operation))
        elif operation.operation_type == OperationType.RENAME:
            conflicts.extend(self._validate_redo_rename(operation))
        elif operation.operation_type == OperationType.DELETE:
            conflicts.extend(self._validate_redo_delete(operation))
        elif operation.operation_type == OperationType.COPY:
            conflicts.extend(self._validate_redo_copy(operation))
        elif operation.operation_type == OperationType.CREATE:
            conflicts.extend(self._validate_redo_create(operation))
        else:
            return ValidationResult(
                can_proceed=False,
                error_message=f"Unknown operation type: {operation.operation_type}"
            )

        can_proceed = len(conflicts) == 0
        error_message = None if can_proceed else f"Found {len(conflicts)} conflicts preventing redo"

        return ValidationResult(
            can_proceed=can_proceed,
            conflicts=conflicts,
            warnings=warnings,
            error_message=error_message
        )

    def _validate_undo_move(self, operation: Operation) -> list[Conflict]:
        """Validate undo of a move operation (move file back to source)."""
        conflicts = []

        # Destination should exist (current location)
        if not self.check_path_exists(operation.destination_path):
            conflicts.append(Conflict(
                conflict_type=ConflictType.FILE_MISSING,
                path=str(operation.destination_path),
                description="File has been moved or deleted since operation",
                expected="File exists at destination",
                actual="File not found"
            ))
        else:
            # Check file integrity
            if operation.file_hash and not self.check_file_integrity(
                operation.destination_path, operation.file_hash
            ):
                conflicts.append(Conflict(
                    conflict_type=ConflictType.HASH_MISMATCH,
                    path=str(operation.destination_path),
                    description="File has been modified since operation",
                    expected=f"Hash: {operation.file_hash[:16]}...",
                    actual="Different hash"
                ))

        # Source location should be available
        if not self.check_path_available(operation.source_path):
            conflicts.append(Conflict(
                conflict_type=ConflictType.PATH_OCCUPIED,
                path=str(operation.source_path),
                description="Source path is now occupied by another file",
                expected="Path available",
                actual="Path occupied"
            ))

        # Check parent directory exists
        if not operation.source_path.parent.exists():
            conflicts.append(Conflict(
                conflict_type=ConflictType.PARENT_MISSING,
                path=str(operation.source_path.parent),
                description="Parent directory no longer exists",
                expected="Parent exists",
                actual="Parent missing"
            ))

        return conflicts

    def _validate_undo_rename(self, operation: Operation) -> list[Conflict]:
        """Validate undo of a rename operation (rename back to original)."""
        conflicts = []

        # New name should exist (current name)
        if not self.check_path_exists(operation.destination_path):
            conflicts.append(Conflict(
                conflict_type=ConflictType.FILE_MISSING,
                path=str(operation.destination_path),
                description="File has been renamed or deleted since operation",
                expected="File exists with new name",
                actual="File not found"
            ))
        else:
            # Check file integrity
            if operation.file_hash and not self.check_file_integrity(
                operation.destination_path, operation.file_hash
            ):
                conflicts.append(Conflict(
                    conflict_type=ConflictType.HASH_MISMATCH,
                    path=str(operation.destination_path),
                    description="File has been modified since operation",
                    expected=f"Hash: {operation.file_hash[:16]}...",
                    actual="Different hash"
                ))

        # Old name should be available
        if not self.check_path_available(operation.source_path):
            conflicts.append(Conflict(
                conflict_type=ConflictType.PATH_OCCUPIED,
                path=str(operation.source_path),
                description="Original name is now used by another file",
                expected="Path available",
                actual="Path occupied"
            ))

        return conflicts

    def _validate_undo_delete(self, operation: Operation) -> list[Conflict]:
        """Validate undo of a delete operation (restore from trash)."""
        conflicts = []

        # Find file in trash
        trash_path = self._get_trash_path(operation)
        if not trash_path or not trash_path.exists():
            conflicts.append(Conflict(
                conflict_type=ConflictType.FILE_MISSING,
                path=str(operation.source_path),
                description="File not found in trash, may have been permanently deleted",
                expected="File in trash",
                actual="File not in trash"
            ))
        else:
            # Check file integrity
            if operation.file_hash and not self.check_file_integrity(trash_path, operation.file_hash):
                conflicts.append(Conflict(
                    conflict_type=ConflictType.HASH_MISMATCH,
                    path=str(trash_path),
                    description="File in trash has been modified",
                    expected=f"Hash: {operation.file_hash[:16]}...",
                    actual="Different hash"
                ))

        # Original location should be available
        if not self.check_path_available(operation.source_path):
            conflicts.append(Conflict(
                conflict_type=ConflictType.PATH_OCCUPIED,
                path=str(operation.source_path),
                description="Original location is now occupied by another file",
                expected="Path available",
                actual="Path occupied"
            ))

        # Check parent directory exists
        if not operation.source_path.parent.exists():
            conflicts.append(Conflict(
                conflict_type=ConflictType.PARENT_MISSING,
                path=str(operation.source_path.parent),
                description="Parent directory no longer exists",
                expected="Parent exists",
                actual="Parent missing"
            ))

        return conflicts

    def _validate_undo_copy(self, operation: Operation) -> list[Conflict]:
        """Validate undo of a copy operation (delete the copy)."""
        conflicts = []

        # Copy should exist
        if not self.check_path_exists(operation.destination_path):
            conflicts.append(Conflict(
                conflict_type=ConflictType.FILE_MISSING,
                path=str(operation.destination_path),
                description="Copy has already been deleted",
                expected="Copy exists",
                actual="Copy not found"
            ))
        else:
            # Verify it's the same file (hash check)
            if operation.file_hash and not self.check_file_integrity(
                operation.destination_path, operation.file_hash
            ):
                conflicts.append(Conflict(
                    conflict_type=ConflictType.HASH_MISMATCH,
                    path=str(operation.destination_path),
                    description="Copy has been modified, may not be safe to delete",
                    expected=f"Hash: {operation.file_hash[:16]}...",
                    actual="Different hash"
                ))

        return conflicts

    def _validate_undo_create(self, operation: Operation) -> list[Conflict]:
        """Validate undo of a create operation (delete the created file)."""
        conflicts = []

        # Created file should exist
        if not self.check_path_exists(operation.source_path):
            conflicts.append(Conflict(
                conflict_type=ConflictType.FILE_MISSING,
                path=str(operation.source_path),
                description="Created file has already been deleted",
                expected="File exists",
                actual="File not found"
            ))

        return conflicts

    def _validate_redo_move(self, operation: Operation) -> list[Conflict]:
        """Validate redo of a move operation (move file to destination again)."""
        conflicts = []

        # Source should exist again (was moved back during undo)
        if not self.check_path_exists(operation.source_path):
            conflicts.append(Conflict(
                conflict_type=ConflictType.FILE_MISSING,
                path=str(operation.source_path),
                description="Source file not found",
                expected="File at source",
                actual="File not found"
            ))

        # Destination should be available
        if not self.check_path_available(operation.destination_path):
            conflicts.append(Conflict(
                conflict_type=ConflictType.PATH_OCCUPIED,
                path=str(operation.destination_path),
                description="Destination path is now occupied",
                expected="Path available",
                actual="Path occupied"
            ))

        return conflicts

    def _validate_redo_rename(self, operation: Operation) -> list[Conflict]:
        """Validate redo of a rename operation."""
        return self._validate_redo_move(operation)  # Same logic

    def _validate_redo_delete(self, operation: Operation) -> list[Conflict]:
        """Validate redo of a delete operation (delete file again)."""
        conflicts = []

        # File should exist again (was restored during undo)
        if not self.check_path_exists(operation.source_path):
            conflicts.append(Conflict(
                conflict_type=ConflictType.FILE_MISSING,
                path=str(operation.source_path),
                description="File not found at original location",
                expected="File exists",
                actual="File not found"
            ))

        return conflicts

    def _validate_redo_copy(self, operation: Operation) -> list[Conflict]:
        """Validate redo of a copy operation (create copy again)."""
        conflicts = []

        # Source should still exist
        if not self.check_path_exists(operation.source_path):
            conflicts.append(Conflict(
                conflict_type=ConflictType.FILE_MISSING,
                path=str(operation.source_path),
                description="Source file no longer exists",
                expected="Source exists",
                actual="Source not found"
            ))

        # Destination should be available
        if not self.check_path_available(operation.destination_path):
            conflicts.append(Conflict(
                conflict_type=ConflictType.PATH_OCCUPIED,
                path=str(operation.destination_path),
                description="Destination path is now occupied",
                expected="Path available",
                actual="Path occupied"
            ))

        return conflicts

    def _validate_redo_create(self, operation: Operation) -> list[Conflict]:
        """Validate redo of a create operation (create file again)."""
        conflicts = []

        # Path should be available
        if not self.check_path_available(operation.source_path):
            conflicts.append(Conflict(
                conflict_type=ConflictType.PATH_OCCUPIED,
                path=str(operation.source_path),
                description="Path is now occupied",
                expected="Path available",
                actual="Path occupied"
            ))

        return conflicts

    def check_file_integrity(self, path: Path, expected_hash: str) -> bool:
        """
        Check if file hash matches expected value.

        Args:
            path: Path to file
            expected_hash: Expected SHA256 hash

        Returns:
            True if hash matches, False otherwise
        """
        try:
            if not path.exists() or not path.is_file():
                return False

            sha256_hash = hashlib.sha256()
            with open(path, "rb") as f:
                for byte_block in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(byte_block)

            actual_hash = sha256_hash.hexdigest()
            return actual_hash == expected_hash
        except Exception as e:
            logger.warning(f"Failed to check file integrity for {path}: {e}")
            return False

    def check_path_exists(self, path: Path) -> bool:
        """
        Check if path exists.

        Args:
            path: Path to check

        Returns:
            True if path exists, False otherwise
        """
        return path.exists()

    def check_path_available(self, path: Path) -> bool:
        """
        Check if path is available (doesn't exist).

        Args:
            path: Path to check

        Returns:
            True if path is available, False otherwise
        """
        return not path.exists()

    def check_conflicts(self, operation: Operation, is_undo: bool = True) -> list[Conflict]:
        """
        Check for conflicts in an operation.

        Args:
            operation: Operation to check
            is_undo: Whether this is an undo (True) or redo (False)

        Returns:
            List of conflicts found
        """
        if is_undo:
            result = self.validate_undo(operation)
        else:
            result = self.validate_redo(operation)
        return result.conflicts

    def _get_trash_path(self, operation: Operation) -> Optional[Path]:
        """
        Get the trash path for a deleted file.

        Args:
            operation: Delete operation

        Returns:
            Path in trash or None if not found
        """
        # Trash path format: trash_dir / operation_id / filename
        if operation.id:
            trash_path = self.trash_dir / str(operation.id) / operation.source_path.name
            if trash_path.exists():
                return trash_path

        # Fallback: search by filename
        filename = operation.source_path.name
        for item in self.trash_dir.rglob(filename):
            if item.is_file():
                return item

        return None
