"""CLI commands for undo/redo operations.

This module provides command-line interface for undoing and redoing
file operations. Delegates to ``undo_history`` module for preview
and execution logic.
"""

from __future__ import annotations

import logging

from file_organizer.undo.undo_manager import UndoManager
from file_organizer.undo.viewer import HistoryViewer

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
