"""
CLI commands for undo/redo operations.

This module provides command-line interface for undoing and redoing
file operations.
"""

import sys
import logging
from pathlib import Path
from typing import Optional

from ..undo.undo_manager import UndoManager
from ..undo.viewer import HistoryViewer

logger = logging.getLogger(__name__)


def undo_command(
    operation_id: Optional[int] = None,
    transaction_id: Optional[str] = None,
    dry_run: bool = False,
    verbose: bool = False
) -> int:
    """
    Undo file operations.

    Args:
        operation_id: Specific operation ID to undo
        transaction_id: Transaction ID to undo
        dry_run: Preview what would be undone without actually doing it
        verbose: Show detailed output

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    if verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    try:
        manager = UndoManager()

        # Dry run mode - show what would be undone
        if dry_run:
            if operation_id:
                can_undo, reason = manager.can_undo(operation_id)
                if can_undo:
                    operations = [op for op in manager.get_undo_stack() if op.id == operation_id]
                    if operations:
                        op = operations[0]
                        print(f"\nWould undo operation {operation_id}:")
                        print(f"  Type: {op.operation_type.value}")
                        print(f"  Source: {op.source_path}")
                        if op.destination_path:
                            print(f"  Destination: {op.destination_path}")
                        print(f"\n✓ This operation can be safely undone")
                    else:
                        print(f"Operation {operation_id} not found")
                        return 1
                else:
                    print(f"\n✗ Cannot undo operation {operation_id}: {reason}")
                    return 1
            elif transaction_id:
                print(f"\nWould undo transaction {transaction_id}")
                transaction = manager.history.get_transaction(transaction_id)
                if transaction:
                    operations = manager.history.get_operations(transaction_id=transaction_id)
                    print(f"  Operations: {len(operations)}")
                    for op in operations[:5]:  # Show first 5
                        print(f"    - {op.operation_type.value}: {op.source_path.name}")
                    if len(operations) > 5:
                        print(f"    ... and {len(operations) - 5} more")
                else:
                    print(f"Transaction {transaction_id} not found")
                    return 1
            else:
                # Show last operation
                operations = manager.get_undo_stack()
                if operations:
                    op = operations[0]
                    print(f"\nWould undo last operation ({op.id}):")
                    print(f"  Type: {op.operation_type.value}")
                    print(f"  Source: {op.source_path}")
                    if op.destination_path:
                        print(f"  Destination: {op.destination_path}")
                else:
                    print("No operations to undo")
                    return 1

            print("\nRun without --dry-run to actually undo")
            return 0

        # Actual undo
        if transaction_id:
            print(f"Undoing transaction {transaction_id}...")
            success = manager.undo_transaction(transaction_id)
        elif operation_id:
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

    except Exception as e:
        logger.error(f"Undo command failed: {e}", exc_info=True)
        print(f"✗ Error: {e}")
        return 1
    finally:
        if 'manager' in locals():
            manager.close()


def redo_command(
    operation_id: Optional[int] = None,
    dry_run: bool = False,
    verbose: bool = False
) -> int:
    """
    Redo file operations.

    Args:
        operation_id: Specific operation ID to redo
        dry_run: Preview what would be redone without actually doing it
        verbose: Show detailed output

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    if verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    try:
        manager = UndoManager()

        # Dry run mode
        if dry_run:
            if operation_id:
                can_redo, reason = manager.can_redo(operation_id)
                if can_redo:
                    operations = [op for op in manager.get_redo_stack() if op.id == operation_id]
                    if operations:
                        op = operations[0]
                        print(f"\nWould redo operation {operation_id}:")
                        print(f"  Type: {op.operation_type.value}")
                        print(f"  Source: {op.source_path}")
                        if op.destination_path:
                            print(f"  Destination: {op.destination_path}")
                        print(f"\n✓ This operation can be safely redone")
                    else:
                        print(f"Operation {operation_id} not found in redo stack")
                        return 1
                else:
                    print(f"\n✗ Cannot redo operation {operation_id}: {reason}")
                    return 1
            else:
                # Show last redoable operation
                operations = manager.get_redo_stack()
                if operations:
                    op = operations[0]
                    print(f"\nWould redo last operation ({op.id}):")
                    print(f"  Type: {op.operation_type.value}")
                    print(f"  Source: {op.source_path}")
                    if op.destination_path:
                        print(f"  Destination: {op.destination_path}")
                else:
                    print("No operations to redo")
                    return 1

            print("\nRun without --dry-run to actually redo")
            return 0

        # Actual redo
        if operation_id:
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

    except Exception as e:
        logger.error(f"Redo command failed: {e}", exc_info=True)
        print(f"✗ Error: {e}")
        return 1
    finally:
        if 'manager' in locals():
            manager.close()


def history_command(
    limit: int = 10,
    operation_type: Optional[str] = None,
    status: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    search: Optional[str] = None,
    transaction: Optional[str] = None,
    operation_id: Optional[int] = None,
    stats: bool = False,
    verbose: bool = False
) -> int:
    """
    View operation history.

    Args:
        limit: Maximum number of operations to show
        operation_type: Filter by operation type
        status: Filter by status
        since: Filter by start date
        until: Filter by end date
        search: Search by path
        transaction: Show specific transaction
        operation_id: Show specific operation
        stats: Show statistics
        verbose: Show detailed output

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    if verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    try:
        viewer = HistoryViewer()

        if stats:
            viewer.show_statistics()
        elif transaction:
            viewer.show_transaction_details(transaction)
        elif operation_id:
            viewer.show_operation_details(operation_id)
        elif search or operation_type or status or since or until:
            viewer.display_filtered_operations(
                operation_type=operation_type,
                status=status,
                since=since,
                until=until,
                search=search,
                limit=limit
            )
        else:
            viewer.show_recent_operations(limit=limit)

        return 0

    except Exception as e:
        logger.error(f"History command failed: {e}", exc_info=True)
        print(f"✗ Error: {e}")
        return 1
    finally:
        if 'viewer' in locals():
            viewer.close()


def main_undo():
    """Main entry point for undo command."""
    import argparse

    parser = argparse.ArgumentParser(description="Undo file operations")
    parser.add_argument("--operation-id", type=int, help="Specific operation ID to undo")
    parser.add_argument("--transaction-id", help="Transaction ID to undo")
    parser.add_argument("--dry-run", action="store_true", help="Preview without executing")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()

    sys.exit(undo_command(
        operation_id=args.operation_id,
        transaction_id=args.transaction_id,
        dry_run=args.dry_run,
        verbose=args.verbose
    ))


def main_redo():
    """Main entry point for redo command."""
    import argparse

    parser = argparse.ArgumentParser(description="Redo file operations")
    parser.add_argument("--operation-id", type=int, help="Specific operation ID to redo")
    parser.add_argument("--dry-run", action="store_true", help="Preview without executing")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()

    sys.exit(redo_command(
        operation_id=args.operation_id,
        dry_run=args.dry_run,
        verbose=args.verbose
    ))


def main_history():
    """Main entry point for history command."""
    import argparse

    parser = argparse.ArgumentParser(description="View operation history")
    parser.add_argument("--limit", type=int, default=10, help="Maximum number of operations")
    parser.add_argument("--type", dest="operation_type", help="Filter by operation type")
    parser.add_argument("--status", help="Filter by status")
    parser.add_argument("--since", help="Filter by start date")
    parser.add_argument("--until", help="Filter by end date")
    parser.add_argument("--search", help="Search by path")
    parser.add_argument("--transaction", help="Show specific transaction")
    parser.add_argument("--operation-id", type=int, help="Show specific operation")
    parser.add_argument("--stats", action="store_true", help="Show statistics")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()

    sys.exit(history_command(
        limit=args.limit,
        operation_type=args.operation_type,
        status=args.status,
        since=args.since,
        until=args.until,
        search=args.search,
        transaction=args.transaction,
        operation_id=args.operation_id,
        stats=args.stats,
        verbose=args.verbose
    ))


if __name__ == "__main__":
    # Determine which command based on script name
    script_name = Path(sys.argv[0]).stem
    if "undo" in script_name:
        main_undo()
    elif "redo" in script_name:
        main_redo()
    else:
        main_history()
