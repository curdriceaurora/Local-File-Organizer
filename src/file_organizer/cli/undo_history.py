"""Operation history access and formatting for CLI commands.

Provides functions for querying undo/redo stacks, checking operation
validity, and formatting operation details for display. Extracted from
``undo_redo.py`` to separate history access from command execution.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..history.models import Operation
    from ..undo.undo_manager import UndoManager


def get_undo_stack(manager: UndoManager) -> list[Operation]:
    """Get list of operations that can be undone.

    Args:
        manager: Undo manager instance.

    Returns:
        List of completed operations (undo stack).
    """
    return manager.get_undo_stack()


def get_redo_stack(manager: UndoManager) -> list[Operation]:
    """Get list of operations that can be redone.

    Args:
        manager: Undo manager instance.

    Returns:
        List of rolled back operations (redo stack).
    """
    return manager.get_redo_stack()


def can_undo_operation(manager: UndoManager, operation_id: int) -> tuple[bool, str]:
    """Check if an operation can be undone.

    Args:
        manager: Undo manager instance.
        operation_id: ID of operation to check.

    Returns:
        Tuple of (can_undo, reason).
    """
    return manager.can_undo(operation_id)


def can_redo_operation(manager: UndoManager, operation_id: int) -> tuple[bool, str]:
    """Check if an operation can be redone.

    Args:
        manager: Undo manager instance.
        operation_id: ID of operation to check.

    Returns:
        Tuple of (can_redo, reason).
    """
    return manager.can_redo(operation_id)


def find_operation_in_stack(operations: list[Operation], operation_id: int) -> Operation | None:
    """Find an operation by ID in a stack.

    Args:
        operations: List of operations to search.
        operation_id: ID of operation to find.

    Returns:
        Operation if found, None otherwise.
    """
    for op in operations:
        if op.id == operation_id:
            return op
    return None


def format_operation_summary(operation: Operation) -> str:
    """Format operation details for display.

    Args:
        operation: Operation to format.

    Returns:
        Formatted string with operation details.
    """
    lines = [
        f"  Type: {operation.operation_type.value}",
        f"  Source: {operation.source_path}",
    ]
    if operation.destination_path:
        lines.append(f"  Destination: {operation.destination_path}")
    return "\n".join(lines)


def format_transaction_summary(
    transaction_id: str, operations: list[Operation], limit: int = 5
) -> str:
    """Format transaction details for display.

    Args:
        transaction_id: Transaction ID.
        operations: Operations in the transaction.
        limit: Maximum operations to show in detail.

    Returns:
        Formatted string with transaction details.
    """
    lines = [f"  Operations: {len(operations)}"]

    for op in operations[:limit]:
        lines.append(f"    - {op.operation_type.value}: {op.source_path.name}")

    if len(operations) > limit:
        lines.append(f"    ... and {len(operations) - limit} more")

    return "\n".join(lines)
