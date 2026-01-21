"""
Data models for undo/redo operations.

This module defines data structures for validation results, rollback results,
and conflict detection.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from enum import Enum


class ConflictType(str, Enum):
    """Types of conflicts that can occur during undo/redo."""
    FILE_MODIFIED = "file_modified"  # File was modified after operation
    FILE_MISSING = "file_missing"  # Expected file doesn't exist
    PATH_OCCUPIED = "path_occupied"  # Target path is already occupied
    PERMISSION_DENIED = "permission_denied"  # Insufficient permissions
    DISK_SPACE = "disk_space"  # Insufficient disk space
    PARENT_MISSING = "parent_missing"  # Parent directory doesn't exist
    HASH_MISMATCH = "hash_mismatch"  # File hash doesn't match expected


@dataclass
class Conflict:
    """
    Represents a conflict detected during validation.

    Attributes:
        conflict_type: Type of conflict
        path: Path where conflict occurred
        description: Human-readable description
        expected: Expected state
        actual: Actual state
    """
    conflict_type: ConflictType
    path: str
    description: str
    expected: Optional[str] = None
    actual: Optional[str] = None

    def __str__(self) -> str:
        """String representation of conflict."""
        msg = f"{self.conflict_type.value}: {self.path} - {self.description}"
        if self.expected and self.actual:
            msg += f" (expected: {self.expected}, actual: {self.actual})"
        return msg


@dataclass
class ValidationResult:
    """
    Result of validating an undo/redo operation.

    Attributes:
        can_proceed: Whether the operation can safely proceed
        conflicts: List of conflicts detected
        warnings: List of non-critical warnings
        error_message: Primary error message if validation failed
    """
    can_proceed: bool
    conflicts: List[Conflict] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    error_message: Optional[str] = None

    def __bool__(self) -> bool:
        """Allow ValidationResult to be used in boolean context."""
        return self.can_proceed

    def __str__(self) -> str:
        """String representation of validation result."""
        if self.can_proceed:
            result = "✓ Validation passed"
            if self.warnings:
                result += f" ({len(self.warnings)} warnings)"
        else:
            result = f"✗ Validation failed: {self.error_message}"
            if self.conflicts:
                result += f"\n  Conflicts: {len(self.conflicts)}"
                for conflict in self.conflicts[:3]:  # Show first 3
                    result += f"\n    - {conflict}"
                if len(self.conflicts) > 3:
                    result += f"\n    ... and {len(self.conflicts) - 3} more"
        return result


@dataclass
class RollbackResult:
    """
    Result of executing a rollback operation.

    Attributes:
        success: Whether the overall rollback succeeded
        operations_rolled_back: Number of operations successfully rolled back
        operations_failed: Number of operations that failed
        errors: List of (operation_id, error_message) tuples
        warnings: List of non-critical warnings
    """
    success: bool
    operations_rolled_back: int = 0
    operations_failed: int = 0
    errors: List[Tuple[int, str]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        """Allow RollbackResult to be used in boolean context."""
        return self.success

    def __str__(self) -> str:
        """String representation of rollback result."""
        if self.success:
            result = f"✓ Rollback successful: {self.operations_rolled_back} operations"
        else:
            result = f"✗ Rollback failed: {self.operations_rolled_back} succeeded, {self.operations_failed} failed"
            if self.errors:
                result += "\n  Errors:"
                for op_id, error in self.errors[:3]:  # Show first 3
                    result += f"\n    - Operation {op_id}: {error}"
                if len(self.errors) > 3:
                    result += f"\n    ... and {len(self.errors) - 3} more errors"
        if self.warnings:
            result += f"\n  Warnings: {len(self.warnings)}"
        return result
