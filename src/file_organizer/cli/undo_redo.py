"""CLI commands for undo/redo operations.

This module provides command-line interface for undoing and redoing
file operations. Delegates to ``undo_history`` module for preview
and execution logic.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from ..undo.undo_manager import UndoManager
from ..undo.viewer import HistoryViewer
from . import undo_history

logger = logging.getLogger(__name__)


def undo_command(
    operation_id: int | None = None,
    transaction_id: str | None = None,
    dry_run: bool = False,
    verbose: bool = False,
) -> int:
    """Undo file operations.

    Delegates to ``undo_history`` module for preview and execution logic.

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

    manager = None
    try:
        manager = UndoManager()
        transaction_id = undo_history.normalize_transaction_id(transaction_id)

        # Dry run mode - delegate to preview helpers
        if dry_run:
            if transaction_id is not None:
                result = undo_history.preview_undo_transaction(manager, transaction_id)
            elif operation_id is not None:
                result = undo_history.preview_undo_operation(manager, operation_id)
            else:
                result = undo_history.preview_undo_last(manager)

            if result == 0:
                print("\nRun without --dry-run to actually undo")
            return result

        # Actual undo - delegate to execution helper
        return undo_history.execute_undo(manager, operation_id, transaction_id)

    except Exception as e:
        logger.error(f"Undo command failed: {e}", exc_info=True)
        print(f"✗ Error: {e}")
        return 1
    finally:
        if manager is not None:
            manager.close()


def redo_command(
    operation_id: int | None = None, dry_run: bool = False, verbose: bool = False
) -> int:
    """Redo file operations.

    Delegates to ``undo_history`` module for preview and execution logic.

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

    manager = None
    try:
        manager = UndoManager()

        # Dry run mode - delegate to preview helpers
        if dry_run:
            if operation_id is not None:
                result = undo_history.preview_redo_operation(manager, operation_id)
            else:
                result = undo_history.preview_redo_last(manager)

            if result == 0:
                print("\nRun without --dry-run to actually redo")
            return result

        # Actual redo - delegate to execution helper
        return undo_history.execute_redo(manager, operation_id)

    except Exception as e:
        logger.error(f"Redo command failed: {e}", exc_info=True)
        print(f"✗ Error: {e}")
        return 1
    finally:
        if manager is not None:
            manager.close()


def history_command(
    limit: int = 10,
    operation_type: str | None = None,
    status: str | None = None,
    since: str | None = None,
    until: str | None = None,
    search: str | None = None,
    transaction: str | None = None,
    operation_id: int | None = None,
    stats: bool = False,
    verbose: bool = False,
) -> int:
    """View operation history.

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
                limit=limit,
            )
        else:
            viewer.show_recent_operations(limit=limit)

        return 0

    except Exception as e:
        logger.error(f"History command failed: {e}", exc_info=True)
        print(f"✗ Error: {e}")
        return 1
    finally:
        if "viewer" in locals():
            viewer.close()


def main_undo() -> None:
    """Main entry point for undo command."""
    import argparse

    parser = argparse.ArgumentParser(description="Undo file operations")
    parser.add_argument("--operation-id", type=int, help="Specific operation ID to undo")
    parser.add_argument("--transaction-id", help="Transaction ID to undo")
    parser.add_argument("--dry-run", action="store_true", help="Preview without executing")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()

    sys.exit(
        undo_command(
            operation_id=args.operation_id,
            transaction_id=args.transaction_id,
            dry_run=args.dry_run,
            verbose=args.verbose,
        )
    )


def main_redo() -> None:
    """Main entry point for redo command."""
    import argparse

    parser = argparse.ArgumentParser(description="Redo file operations")
    parser.add_argument("--operation-id", type=int, help="Specific operation ID to redo")
    parser.add_argument("--dry-run", action="store_true", help="Preview without executing")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()

    sys.exit(
        redo_command(operation_id=args.operation_id, dry_run=args.dry_run, verbose=args.verbose)
    )


def main_history() -> None:
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

    sys.exit(
        history_command(
            limit=args.limit,
            operation_type=args.operation_type,
            status=args.status,
            since=args.since,
            until=args.until,
            search=args.search,
            transaction=args.transaction,
            operation_id=args.operation_id,
            stats=args.stats,
            verbose=args.verbose,
        )
    )


if __name__ == "__main__":
    # Determine which command based on script name
    script_name = Path(sys.argv[0]).stem
    if "undo" in script_name:
        main_undo()
    elif "redo" in script_name:
        main_redo()
    else:
        main_history()
