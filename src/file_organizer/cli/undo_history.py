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


def normalize_transaction_id(transaction_id: str | None) -> str | None:
    """Normalize transaction ids so blank values are treated as absent."""
    if transaction_id is None:
        return None
    normalized = transaction_id.strip()
    return normalized or None


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


# ------------------------------------------------------------------
# Dry-run preview helpers
# ------------------------------------------------------------------


def preview_undo_operation(manager: UndoManager, operation_id: int) -> int:
    """Preview undoing a specific operation (dry-run mode).

    Args:
        manager: Undo manager instance.
        operation_id: ID of operation to preview.

    Returns:
        Exit code (0 for success, 1 for failure).
    """
    can_undo, reason = can_undo_operation(manager, operation_id)
    if can_undo:
        operations = get_undo_stack(manager)
        op = find_operation_in_stack(operations, operation_id)
        if op:
            print(f"\nWould undo operation {operation_id}:")
            print(format_operation_summary(op))
            print("\n✓ This operation can be safely undone")
            return 0
        else:
            print(f"Operation {operation_id} not found")
            return 1
    else:
        print(f"\n✗ Cannot undo operation {operation_id}: {reason}")
        return 1


def preview_undo_transaction(manager: UndoManager, transaction_id: str) -> int:
    """Preview undoing a transaction (dry-run mode).

    Args:
        manager: Undo manager instance.
        transaction_id: ID of transaction to preview.

    Returns:
        Exit code (0 for success, 1 for failure).
    """
    normalized_transaction_id = normalize_transaction_id(transaction_id)
    if normalized_transaction_id is None:
        print("Transaction ID must not be empty")
        return 1

    print(f"\nWould undo transaction {normalized_transaction_id}")
    transaction = manager.history.get_transaction(normalized_transaction_id)
    if transaction:
        operations = manager.history.get_operations(transaction_id=normalized_transaction_id)
        print(format_transaction_summary(normalized_transaction_id, operations))
        return 0
    else:
        print(f"Transaction {normalized_transaction_id} not found")
        return 1


def preview_undo_last(manager: UndoManager) -> int:
    """Preview undoing the last operation (dry-run mode).

    Args:
        manager: Undo manager instance.

    Returns:
        Exit code (0 for success, 1 for failure).
    """
    operations = get_undo_stack(manager)
    if operations:
        op = operations[0]
        print(f"\nWould undo last operation ({op.id}):")
        print(format_operation_summary(op))
        return 0
    else:
        print("No operations to undo")
        return 1


def preview_redo_operation(manager: UndoManager, operation_id: int) -> int:
    """Preview redoing a specific operation (dry-run mode).

    Args:
        manager: Undo manager instance.
        operation_id: ID of operation to preview.

    Returns:
        Exit code (0 for success, 1 for failure).
    """
    can_redo, reason = can_redo_operation(manager, operation_id)
    if can_redo:
        operations = get_redo_stack(manager)
        op = find_operation_in_stack(operations, operation_id)
        if op:
            print(f"\nWould redo operation {operation_id}:")
            print(format_operation_summary(op))
            print("\n✓ This operation can be safely redone")
            return 0
        else:
            print(f"Operation {operation_id} not found in redo stack")
            return 1
    else:
        print(f"\n✗ Cannot redo operation {operation_id}: {reason}")
        return 1


def preview_redo_last(manager: UndoManager) -> int:
    """Preview redoing the last operation (dry-run mode).

    Args:
        manager: Undo manager instance.

    Returns:
        Exit code (0 for success, 1 for failure).
    """
    operations = get_redo_stack(manager)
    if operations:
        op = operations[0]
        print(f"\nWould redo last operation ({op.id}):")
        print(format_operation_summary(op))
        return 0
    else:
        print("No operations to redo")
        return 1


# ------------------------------------------------------------------
# Execution helpers
# ------------------------------------------------------------------


def execute_undo(
    manager: UndoManager,
    operation_id: int | None = None,
    transaction_id: str | None = None,
) -> int:
    """Execute undo operation.

    Args:
        manager: Undo manager instance.
        operation_id: Specific operation ID to undo (optional).
        transaction_id: Transaction ID to undo (optional).

    Returns:
        Exit code (0 for success, 1 for failure).
    """
    normalized_transaction_id = normalize_transaction_id(transaction_id)
    if normalized_transaction_id is not None:
        print(f"Undoing transaction {normalized_transaction_id}...")
        success = manager.undo_transaction(normalized_transaction_id)
    elif operation_id is not None:
        print(f"Undoing operation {operation_id}...")
        success = manager.undo_operation(operation_id)
    else:
        print("Undoing last operation...")
        success = manager.undo_last_operation()

    if success:
        print("✓ Undo successful")
        return 0
    else:
        print("✗ Undo failed")
        return 1


def execute_redo(manager: UndoManager, operation_id: int | None = None) -> int:
    """Execute redo operation.

    Args:
        manager: Undo manager instance.
        operation_id: Specific operation ID to redo (optional).

    Returns:
        Exit code (0 for success, 1 for failure).
    """
    if operation_id is not None:
        print(f"Redoing operation {operation_id}...")
        success = manager.redo_operation(operation_id)
    else:
        print("Redoing last operation...")
        success = manager.redo_last_operation()

    if success:
        print("✓ Redo successful")
        return 0
    else:
        print("✗ Redo failed")
        return 1
