"""Tests for file_organizer.cli.undo_redo module.

Tests the function-based undo/redo/history CLI commands including:
- undo_command (dry-run, operation_id, transaction_id, actual undo)
- redo_command (dry-run, operation_id, actual redo)
- history_command (stats, transaction, operation_id, filters, recent)
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.cli.undo_redo import (
    history_command,
    main_history,
    main_redo,
    main_undo,
    redo_command,
    undo_command,
)

pytestmark = [pytest.mark.unit]


def _make_operation(op_id=1, op_type="move", src="/a/file.txt", dst="/b/file.txt"):
    """Create a mock operation object."""
    op = MagicMock()
    op.id = op_id
    op.operation_type = MagicMock()
    op.operation_type.value = op_type
    op.source_path = Path(src)
    op.destination_path = Path(dst) if dst else None
    return op


# ============================================================================
# Undo Command Tests
# ============================================================================


@pytest.mark.unit
class TestUndoCommand:
    """Tests for undo_command."""

    def test_undo_last_operation_success(self, capsys):
        mock_mgr = MagicMock()
        mock_mgr.undo_last_operation.return_value = True
        with patch("file_organizer.cli.undo_redo.UndoManager", return_value=mock_mgr):
            result = undo_command()
        assert result == 0
        captured = capsys.readouterr()
        assert "Undo successful" in captured.out

    def test_undo_last_operation_failure(self, capsys):
        mock_mgr = MagicMock()
        mock_mgr.undo_last_operation.return_value = False
        with patch("file_organizer.cli.undo_redo.UndoManager", return_value=mock_mgr):
            result = undo_command()
        assert result == 1
        captured = capsys.readouterr()
        assert "Undo failed" in captured.out

    def test_undo_specific_operation(self, capsys):
        mock_mgr = MagicMock()
        mock_mgr.undo_operation.return_value = True
        with patch("file_organizer.cli.undo_redo.UndoManager", return_value=mock_mgr):
            result = undo_command(operation_id=42)
        assert result == 0
        mock_mgr.undo_operation.assert_called_once_with(42)

    def test_undo_transaction(self, capsys):
        mock_mgr = MagicMock()
        mock_mgr.undo_transaction.return_value = True
        with patch("file_organizer.cli.undo_redo.UndoManager", return_value=mock_mgr):
            result = undo_command(transaction_id="tx-123")
        assert result == 0
        mock_mgr.undo_transaction.assert_called_once_with("tx-123")

    def test_undo_dry_run_with_operation_id_can_undo(self, capsys):
        mock_mgr = MagicMock()
        mock_mgr.can_undo.return_value = (True, "")
        op = _make_operation(op_id=5)
        mock_mgr.get_undo_stack.return_value = [op]
        with patch("file_organizer.cli.undo_redo.UndoManager", return_value=mock_mgr):
            result = undo_command(operation_id=5, dry_run=True)
        assert result == 0
        captured = capsys.readouterr()
        assert "Would undo operation 5" in captured.out
        assert "can be safely undone" in captured.out

    def test_undo_dry_run_with_operation_id_cannot_undo(self, capsys):
        mock_mgr = MagicMock()
        mock_mgr.can_undo.return_value = (False, "File deleted")
        with patch("file_organizer.cli.undo_redo.UndoManager", return_value=mock_mgr):
            result = undo_command(operation_id=5, dry_run=True)
        assert result == 1
        captured = capsys.readouterr()
        assert "Cannot undo" in captured.out
        assert "File deleted" in captured.out

    def test_undo_dry_run_with_operation_id_not_found(self, capsys):
        mock_mgr = MagicMock()
        mock_mgr.can_undo.return_value = (True, "")
        mock_mgr.get_undo_stack.return_value = []  # Operation not in stack
        with patch("file_organizer.cli.undo_redo.UndoManager", return_value=mock_mgr):
            result = undo_command(operation_id=999, dry_run=True)
        assert result == 1
        captured = capsys.readouterr()
        assert "not found" in captured.out

    def test_undo_dry_run_with_transaction_id(self, capsys):
        mock_mgr = MagicMock()
        mock_transaction = MagicMock()
        mock_mgr.history.get_transaction.return_value = mock_transaction
        ops = [_make_operation(op_id=i) for i in range(3)]
        mock_mgr.history.get_operations.return_value = ops
        with patch("file_organizer.cli.undo_redo.UndoManager", return_value=mock_mgr):
            result = undo_command(transaction_id="tx-abc", dry_run=True)
        assert result == 0
        captured = capsys.readouterr()
        assert "Would undo transaction tx-abc" in captured.out
        assert "Operations: 3" in captured.out

    def test_undo_dry_run_transaction_not_found(self, capsys):
        mock_mgr = MagicMock()
        mock_mgr.history.get_transaction.return_value = None
        with patch("file_organizer.cli.undo_redo.UndoManager", return_value=mock_mgr):
            result = undo_command(transaction_id="tx-missing", dry_run=True)
        assert result == 1
        captured = capsys.readouterr()
        assert "not found" in captured.out

    def test_undo_dry_run_last_operation(self, capsys):
        mock_mgr = MagicMock()
        op = _make_operation(op_id=10)
        mock_mgr.get_undo_stack.return_value = [op]
        with patch("file_organizer.cli.undo_redo.UndoManager", return_value=mock_mgr):
            result = undo_command(dry_run=True)
        assert result == 0
        captured = capsys.readouterr()
        assert "Would undo last operation" in captured.out

    def test_undo_dry_run_no_operations(self, capsys):
        mock_mgr = MagicMock()
        mock_mgr.get_undo_stack.return_value = []
        with patch("file_organizer.cli.undo_redo.UndoManager", return_value=mock_mgr):
            result = undo_command(dry_run=True)
        assert result == 1
        captured = capsys.readouterr()
        assert "No operations to undo" in captured.out

    def test_undo_dry_run_transaction_many_operations(self, capsys):
        """Test that dry-run truncates display after 5 operations."""
        mock_mgr = MagicMock()
        mock_transaction = MagicMock()
        mock_mgr.history.get_transaction.return_value = mock_transaction
        ops = [_make_operation(op_id=i) for i in range(8)]
        mock_mgr.history.get_operations.return_value = ops
        with patch("file_organizer.cli.undo_redo.UndoManager", return_value=mock_mgr):
            result = undo_command(transaction_id="tx-big", dry_run=True)
        assert result == 0
        captured = capsys.readouterr()
        assert "and 3 more" in captured.out

    def test_undo_exception(self, capsys):
        with patch(
            "file_organizer.cli.undo_redo.UndoManager",
            side_effect=RuntimeError("db error"),
        ):
            result = undo_command()
        assert result == 1
        captured = capsys.readouterr()
        assert "Error" in captured.out

    def test_undo_verbose_flag(self, capsys):
        mock_mgr = MagicMock()
        mock_mgr.undo_last_operation.return_value = True
        with patch("file_organizer.cli.undo_redo.UndoManager", return_value=mock_mgr):
            result = undo_command(verbose=True)
        assert result == 0

    def test_undo_manager_close_called(self):
        mock_mgr = MagicMock()
        mock_mgr.undo_last_operation.return_value = True
        with patch("file_organizer.cli.undo_redo.UndoManager", return_value=mock_mgr):
            undo_command()
        mock_mgr.close.assert_called_once()

    def test_undo_manager_close_called_on_error(self):
        mock_mgr = MagicMock()
        mock_mgr.undo_last_operation.side_effect = RuntimeError("fail")
        with patch("file_organizer.cli.undo_redo.UndoManager", return_value=mock_mgr):
            undo_command()
        mock_mgr.close.assert_called_once()

    def test_undo_dry_run_operation_without_destination(self, capsys):
        mock_mgr = MagicMock()
        op = _make_operation(op_id=5, dst=None)
        mock_mgr.can_undo.return_value = (True, "")
        mock_mgr.get_undo_stack.return_value = [op]
        with patch("file_organizer.cli.undo_redo.UndoManager", return_value=mock_mgr):
            result = undo_command(operation_id=5, dry_run=True)
        assert result == 0
        captured = capsys.readouterr()
        assert "Destination" not in captured.out


# ============================================================================
# Redo Command Tests
# ============================================================================


@pytest.mark.unit
class TestRedoCommand:
    """Tests for redo_command."""

    def test_redo_last_operation_success(self, capsys):
        mock_mgr = MagicMock()
        mock_mgr.redo_last_operation.return_value = True
        with patch("file_organizer.cli.undo_redo.UndoManager", return_value=mock_mgr):
            result = redo_command()
        assert result == 0
        captured = capsys.readouterr()
        assert "Redo successful" in captured.out

    def test_redo_last_operation_failure(self, capsys):
        mock_mgr = MagicMock()
        mock_mgr.redo_last_operation.return_value = False
        with patch("file_organizer.cli.undo_redo.UndoManager", return_value=mock_mgr):
            result = redo_command()
        assert result == 1
        captured = capsys.readouterr()
        assert "Redo failed" in captured.out

    def test_redo_specific_operation(self, capsys):
        mock_mgr = MagicMock()
        mock_mgr.redo_operation.return_value = True
        with patch("file_organizer.cli.undo_redo.UndoManager", return_value=mock_mgr):
            result = redo_command(operation_id=42)
        assert result == 0
        mock_mgr.redo_operation.assert_called_once_with(42)

    def test_redo_dry_run_with_operation_id_can_redo(self, capsys):
        mock_mgr = MagicMock()
        mock_mgr.can_redo.return_value = (True, "")
        op = _make_operation(op_id=7)
        mock_mgr.get_redo_stack.return_value = [op]
        with patch("file_organizer.cli.undo_redo.UndoManager", return_value=mock_mgr):
            result = redo_command(operation_id=7, dry_run=True)
        assert result == 0
        captured = capsys.readouterr()
        assert "Would redo operation 7" in captured.out
        assert "can be safely redone" in captured.out

    def test_redo_dry_run_with_operation_id_cannot_redo(self, capsys):
        mock_mgr = MagicMock()
        mock_mgr.can_redo.return_value = (False, "File exists")
        with patch("file_organizer.cli.undo_redo.UndoManager", return_value=mock_mgr):
            result = redo_command(operation_id=7, dry_run=True)
        assert result == 1
        captured = capsys.readouterr()
        assert "Cannot redo" in captured.out
        assert "File exists" in captured.out

    def test_redo_dry_run_operation_not_in_redo_stack(self, capsys):
        mock_mgr = MagicMock()
        mock_mgr.can_redo.return_value = (True, "")
        mock_mgr.get_redo_stack.return_value = []
        with patch("file_organizer.cli.undo_redo.UndoManager", return_value=mock_mgr):
            result = redo_command(operation_id=999, dry_run=True)
        assert result == 1
        captured = capsys.readouterr()
        assert "not found in redo stack" in captured.out

    def test_redo_dry_run_last_operation(self, capsys):
        mock_mgr = MagicMock()
        op = _make_operation(op_id=15)
        mock_mgr.get_redo_stack.return_value = [op]
        with patch("file_organizer.cli.undo_redo.UndoManager", return_value=mock_mgr):
            result = redo_command(dry_run=True)
        assert result == 0
        captured = capsys.readouterr()
        assert "Would redo last operation" in captured.out

    def test_redo_dry_run_no_operations(self, capsys):
        mock_mgr = MagicMock()
        mock_mgr.get_redo_stack.return_value = []
        with patch("file_organizer.cli.undo_redo.UndoManager", return_value=mock_mgr):
            result = redo_command(dry_run=True)
        assert result == 1
        captured = capsys.readouterr()
        assert "No operations to redo" in captured.out

    def test_redo_exception(self, capsys):
        with patch(
            "file_organizer.cli.undo_redo.UndoManager",
            side_effect=RuntimeError("db error"),
        ):
            result = redo_command()
        assert result == 1
        captured = capsys.readouterr()
        assert "Error" in captured.out

    def test_redo_manager_close_called(self):
        mock_mgr = MagicMock()
        mock_mgr.redo_last_operation.return_value = True
        with patch("file_organizer.cli.undo_redo.UndoManager", return_value=mock_mgr):
            redo_command()
        mock_mgr.close.assert_called_once()

    def test_redo_verbose_flag(self, capsys):
        mock_mgr = MagicMock()
        mock_mgr.redo_last_operation.return_value = True
        with patch("file_organizer.cli.undo_redo.UndoManager", return_value=mock_mgr):
            result = redo_command(verbose=True)
        assert result == 0

    def test_redo_dry_run_operation_without_destination(self, capsys):
        mock_mgr = MagicMock()
        op = _make_operation(op_id=7, dst=None)
        mock_mgr.can_redo.return_value = (True, "")
        mock_mgr.get_redo_stack.return_value = [op]
        with patch("file_organizer.cli.undo_redo.UndoManager", return_value=mock_mgr):
            result = redo_command(operation_id=7, dry_run=True)
        assert result == 0
        captured = capsys.readouterr()
        assert "Destination" not in captured.out


# ============================================================================
# History Command Tests
# ============================================================================


@pytest.mark.unit
class TestHistoryCommand:
    """Tests for history_command."""

    def test_show_recent_operations(self):
        mock_viewer = MagicMock()
        with patch("file_organizer.cli.undo_redo.HistoryViewer", return_value=mock_viewer):
            result = history_command()
        assert result == 0
        mock_viewer.show_recent_operations.assert_called_once_with(limit=10)
        mock_viewer.close.assert_called_once()

    def test_show_recent_with_custom_limit(self):
        mock_viewer = MagicMock()
        with patch("file_organizer.cli.undo_redo.HistoryViewer", return_value=mock_viewer):
            result = history_command(limit=50)
        assert result == 0
        mock_viewer.show_recent_operations.assert_called_once_with(limit=50)

    def test_show_statistics(self):
        mock_viewer = MagicMock()
        with patch("file_organizer.cli.undo_redo.HistoryViewer", return_value=mock_viewer):
            result = history_command(stats=True)
        assert result == 0
        mock_viewer.show_statistics.assert_called_once()

    def test_show_transaction_details(self):
        mock_viewer = MagicMock()
        with patch("file_organizer.cli.undo_redo.HistoryViewer", return_value=mock_viewer):
            result = history_command(transaction="tx-abc")
        assert result == 0
        mock_viewer.show_transaction_details.assert_called_once_with("tx-abc")

    def test_show_operation_details(self):
        mock_viewer = MagicMock()
        with patch("file_organizer.cli.undo_redo.HistoryViewer", return_value=mock_viewer):
            result = history_command(operation_id=42)
        assert result == 0
        mock_viewer.show_operation_details.assert_called_once_with(42)

    def test_filtered_operations_by_type(self):
        mock_viewer = MagicMock()
        with patch("file_organizer.cli.undo_redo.HistoryViewer", return_value=mock_viewer):
            result = history_command(operation_type="move")
        assert result == 0
        mock_viewer.display_filtered_operations.assert_called_once_with(
            operation_type="move",
            status=None,
            since=None,
            until=None,
            search=None,
            limit=10,
        )

    def test_filtered_operations_by_search(self):
        mock_viewer = MagicMock()
        with patch("file_organizer.cli.undo_redo.HistoryViewer", return_value=mock_viewer):
            result = history_command(search="document")
        assert result == 0
        mock_viewer.display_filtered_operations.assert_called_once()
        call_kwargs = mock_viewer.display_filtered_operations.call_args[1]
        assert call_kwargs["search"] == "document"

    def test_filtered_operations_by_status(self):
        mock_viewer = MagicMock()
        with patch("file_organizer.cli.undo_redo.HistoryViewer", return_value=mock_viewer):
            result = history_command(status="completed")
        assert result == 0
        mock_viewer.display_filtered_operations.assert_called_once()
        call_kwargs = mock_viewer.display_filtered_operations.call_args[1]
        assert call_kwargs["status"] == "completed"

    def test_filtered_operations_date_range(self):
        mock_viewer = MagicMock()
        with patch("file_organizer.cli.undo_redo.HistoryViewer", return_value=mock_viewer):
            result = history_command(since="2024-01-01", until="2024-12-31")
        assert result == 0
        mock_viewer.display_filtered_operations.assert_called_once()
        call_kwargs = mock_viewer.display_filtered_operations.call_args[1]
        assert call_kwargs["since"] == "2024-01-01"
        assert call_kwargs["until"] == "2024-12-31"

    def test_exception_handling(self, capsys):
        with patch(
            "file_organizer.cli.undo_redo.HistoryViewer",
            side_effect=RuntimeError("db error"),
        ):
            result = history_command()
        assert result == 1
        captured = capsys.readouterr()
        assert "Error" in captured.out

    def test_verbose_flag(self):
        mock_viewer = MagicMock()
        with patch("file_organizer.cli.undo_redo.HistoryViewer", return_value=mock_viewer):
            result = history_command(verbose=True)
        assert result == 0

    def test_stats_priority_over_other_options(self):
        """Stats flag takes precedence over transaction/operation_id."""
        mock_viewer = MagicMock()
        with patch("file_organizer.cli.undo_redo.HistoryViewer", return_value=mock_viewer):
            result = history_command(stats=True, transaction="tx-abc")
        assert result == 0
        mock_viewer.show_statistics.assert_called_once()
        mock_viewer.show_transaction_details.assert_not_called()

    def test_transaction_priority_over_operation_id(self):
        """Transaction takes precedence over operation_id."""
        mock_viewer = MagicMock()
        with patch("file_organizer.cli.undo_redo.HistoryViewer", return_value=mock_viewer):
            result = history_command(transaction="tx-abc", operation_id=42)
        assert result == 0
        mock_viewer.show_transaction_details.assert_called_once_with("tx-abc")
        mock_viewer.show_operation_details.assert_not_called()


# ============================================================================
# Entry Point Tests
# ============================================================================


@pytest.mark.unit
class TestMainUndo:
    """Tests for main_undo entry point."""

    def test_main_undo_default(self):
        """Test main_undo parses args and calls undo_command."""
        with (
            patch("sys.argv", ["undo"]),
            patch("file_organizer.cli.undo_redo.undo_command", return_value=0) as mock_cmd,
            pytest.raises(SystemExit) as exc_info,
        ):
            main_undo()
        assert exc_info.value.code == 0
        mock_cmd.assert_called_once_with(
            operation_id=None, transaction_id=None, dry_run=False, verbose=False
        )

    def test_main_undo_with_options(self):
        """Test main_undo with operation-id and dry-run flags."""
        with (
            patch("sys.argv", ["undo", "--operation-id", "42", "--dry-run", "--verbose"]),
            patch("file_organizer.cli.undo_redo.undo_command", return_value=0) as mock_cmd,
            pytest.raises(SystemExit) as exc_info,
        ):
            main_undo()
        assert exc_info.value.code == 0
        mock_cmd.assert_called_once_with(
            operation_id=42, transaction_id=None, dry_run=True, verbose=True
        )

    def test_main_undo_with_transaction_id(self):
        """Test main_undo with transaction-id flag."""
        with (
            patch("sys.argv", ["undo", "--transaction-id", "tx-abc"]),
            patch("file_organizer.cli.undo_redo.undo_command", return_value=0) as mock_cmd,
            pytest.raises(SystemExit) as exc_info,
        ):
            main_undo()
        assert exc_info.value.code == 0
        mock_cmd.assert_called_once_with(
            operation_id=None, transaction_id="tx-abc", dry_run=False, verbose=False
        )


@pytest.mark.unit
class TestMainRedo:
    """Tests for main_redo entry point."""

    def test_main_redo_default(self):
        """Test main_redo parses args and calls redo_command."""
        with (
            patch("sys.argv", ["redo"]),
            patch("file_organizer.cli.undo_redo.redo_command", return_value=0) as mock_cmd,
            pytest.raises(SystemExit) as exc_info,
        ):
            main_redo()
        assert exc_info.value.code == 0
        mock_cmd.assert_called_once_with(operation_id=None, dry_run=False, verbose=False)

    def test_main_redo_with_options(self):
        """Test main_redo with operation-id and dry-run flags."""
        with (
            patch("sys.argv", ["redo", "--operation-id", "7", "--dry-run", "-v"]),
            patch("file_organizer.cli.undo_redo.redo_command", return_value=0) as mock_cmd,
            pytest.raises(SystemExit) as exc_info,
        ):
            main_redo()
        assert exc_info.value.code == 0
        mock_cmd.assert_called_once_with(operation_id=7, dry_run=True, verbose=True)


@pytest.mark.unit
class TestMainHistory:
    """Tests for main_history entry point."""

    def test_main_history_default(self):
        """Test main_history parses args and calls history_command."""
        with (
            patch("sys.argv", ["history"]),
            patch("file_organizer.cli.undo_redo.history_command", return_value=0) as mock_cmd,
            pytest.raises(SystemExit) as exc_info,
        ):
            main_history()
        assert exc_info.value.code == 0
        mock_cmd.assert_called_once_with(
            limit=10,
            operation_type=None,
            status=None,
            since=None,
            until=None,
            search=None,
            transaction=None,
            operation_id=None,
            stats=False,
            verbose=False,
        )

    def test_main_history_with_stats(self):
        """Test main_history with --stats flag."""
        with (
            patch("sys.argv", ["history", "--stats", "--verbose"]),
            patch("file_organizer.cli.undo_redo.history_command", return_value=0) as mock_cmd,
            pytest.raises(SystemExit) as exc_info,
        ):
            main_history()
        assert exc_info.value.code == 0
        mock_cmd.assert_called_once_with(
            limit=10,
            operation_type=None,
            status=None,
            since=None,
            until=None,
            search=None,
            transaction=None,
            operation_id=None,
            stats=True,
            verbose=True,
        )

    def test_main_history_with_filters(self):
        """Test main_history with various filter options."""
        with (
            patch(
                "sys.argv",
                [
                    "history",
                    "--limit",
                    "25",
                    "--type",
                    "move",
                    "--status",
                    "completed",
                    "--since",
                    "2024-01-01",
                    "--until",
                    "2024-12-31",
                    "--search",
                    "documents",
                    "--transaction",
                    "tx-abc",
                    "--operation-id",
                    "42",
                ],
            ),
            patch("file_organizer.cli.undo_redo.history_command", return_value=0) as mock_cmd,
            pytest.raises(SystemExit) as exc_info,
        ):
            main_history()
        assert exc_info.value.code == 0
        mock_cmd.assert_called_once_with(
            limit=25,
            operation_type="move",
            status="completed",
            since="2024-01-01",
            until="2024-12-31",
            search="documents",
            transaction="tx-abc",
            operation_id=42,
            stats=False,
            verbose=False,
        )

    def test_main_history_nonzero_exit(self):
        """Test main_history propagates nonzero exit code."""
        with (
            patch("sys.argv", ["history"]),
            patch("file_organizer.cli.undo_redo.history_command", return_value=1),
            pytest.raises(SystemExit) as exc_info,
        ):
            main_history()
        assert exc_info.value.code == 1
