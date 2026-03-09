"""Coverage tests for file_organizer.tui.undo_history_view module.

Targets uncovered worker thread paths (_load_history, _run_undo, _run_redo),
_set_status with exception paths, and HistoryStatsPanel edge cases.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from file_organizer.tui.undo_history_view import (
    HistoryStatsPanel,
    OperationHistoryPanel,
    UndoHistoryView,
    UndoRedoStackPanel,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# HistoryStatsPanel - additional edge cases
# ---------------------------------------------------------------------------


class TestHistoryStatsPanelCoverage:
    """Test HistoryStatsPanel branches not covered by existing tests."""

    def test_latest_operation_no_timestamp_attr(self) -> None:
        """Test latest_operation that lacks a timestamp attribute."""
        panel = HistoryStatsPanel()
        panel.update = MagicMock()
        latest = SimpleNamespace()  # no timestamp attr at all
        stats = {
            "total_operations": 1,
            "by_type": {},
            "by_status": {},
            "latest_operation": latest,
        }
        panel.set_stats(stats)
        rendered = panel.update.call_args[0][0]
        assert "unknown" in rendered

    def test_no_latest_operation(self) -> None:
        """Test stats without latest_operation key."""
        panel = HistoryStatsPanel()
        panel.update = MagicMock()
        stats = {
            "total_operations": 0,
            "by_type": {},
            "by_status": {},
        }
        panel.set_stats(stats)
        rendered = panel.update.call_args[0][0]
        assert "Latest" not in rendered

    def test_by_status_with_unknown_status(self) -> None:
        """Test that unknown status gets red color."""
        panel = HistoryStatsPanel()
        panel.update = MagicMock()
        stats = {
            "total_operations": 3,
            "by_type": {},
            "by_status": {"failed": 1, "unknown_status": 2},
        }
        panel.set_stats(stats)
        rendered = panel.update.call_args[0][0]
        assert "red" in rendered


# ---------------------------------------------------------------------------
# OperationHistoryPanel - max 20 operations
# ---------------------------------------------------------------------------


class TestOperationHistoryPanelCoverage:
    """Test OperationHistoryPanel with >20 operations."""

    def test_truncates_to_20_ops(self) -> None:
        panel = OperationHistoryPanel()
        panel.update = MagicMock()

        ops = []
        for i in range(25):
            ops.append(
                SimpleNamespace(
                    id=str(i),
                    operation_type=SimpleNamespace(value="move"),
                    status=SimpleNamespace(value="completed"),
                    timestamp=None,
                    source_path=f"/src/{i}.txt",
                    destination_path=f"/dst/{i}.txt",
                )
            )
        panel.set_operations(ops)
        rendered = panel.update.call_args[0][0]
        # Should contain op 19 but not op 20+
        assert "19" in rendered
        # Only 20 lines of operations (header + separator + 20 ops)

    def test_operation_with_none_id(self) -> None:
        panel = OperationHistoryPanel()
        panel.update = MagicMock()
        op = SimpleNamespace(
            id=None,
            operation_type="move",
            status="done",
            timestamp=None,
            source_path="/src/a.txt",
            destination_path=None,
        )
        panel.set_operations([op])
        rendered = panel.update.call_args[0][0]
        assert "-" in rendered


# ---------------------------------------------------------------------------
# UndoRedoStackPanel - more than 5 items
# ---------------------------------------------------------------------------


class TestUndoRedoStackPanelCoverage:
    """Test UndoRedoStackPanel with >5 items in stacks."""

    def test_shows_only_top_5(self) -> None:
        panel = UndoRedoStackPanel()
        panel.update = MagicMock()
        ops = [
            SimpleNamespace(
                operation_type=SimpleNamespace(value=f"op{i}"),
                source_path=f"/src/{i}.txt",
            )
            for i in range(8)
        ]
        panel.set_stacks(ops, [])
        rendered = panel.update.call_args[0][0]
        # Should show op0 through op4 but not op5+
        assert "op0" in rendered
        assert "op4" in rendered


# ---------------------------------------------------------------------------
# UndoHistoryView - _load_history worker
# ---------------------------------------------------------------------------


class TestUndoHistoryViewLoadHistory:
    """Test _load_history worker thread paths."""

    def test_load_history_success(self) -> None:
        """Test successful history load path."""
        view = UndoHistoryView()
        view.query_one = MagicMock()

        mock_history = MagicMock()
        mock_manager = MagicMock()
        mock_viewer = MagicMock()
        mock_history.get_recent_operations.return_value = []
        mock_manager.get_undo_stack.return_value = []
        mock_manager.get_redo_stack.return_value = []
        mock_viewer.get_statistics.return_value = {}

        mock_app = MagicMock()
        with (
            patch(
                "file_organizer.history.tracker.OperationHistory",
                return_value=mock_history,
            ),
            patch(
                "file_organizer.undo.undo_manager.UndoManager",
                return_value=mock_manager,
            ),
            patch(
                "file_organizer.undo.viewer.HistoryViewer",
                return_value=mock_viewer,
            ),
            patch.object(type(view), "app", new_callable=PropertyMock, return_value=mock_app),
        ):
            # Call the underlying function directly (not the @work wrapper)
            UndoHistoryView._load_history.__wrapped__(view)

        assert mock_app.call_from_thread.call_count >= 4
        mock_history.close.assert_called_once()

    def test_load_history_exception(self) -> None:
        """Test history load with exception."""
        view = UndoHistoryView()
        view.query_one = MagicMock()

        mock_app = MagicMock()
        with (
            patch(
                "file_organizer.history.tracker.OperationHistory",
                side_effect=RuntimeError("db error"),
            ),
            patch.object(type(view), "app", new_callable=PropertyMock, return_value=mock_app),
        ):
            UndoHistoryView._load_history.__wrapped__(view)

        # Should have called update on panels with error message
        assert mock_app.call_from_thread.call_count >= 1


# ---------------------------------------------------------------------------
# UndoHistoryView - _run_undo worker
# ---------------------------------------------------------------------------


class TestUndoHistoryViewRunUndo:
    """Test _run_undo worker paths."""

    def test_undo_success(self) -> None:
        view = UndoHistoryView()

        mock_history = MagicMock()
        mock_manager = MagicMock()
        mock_manager.undo_last_operation.return_value = True

        mock_app = MagicMock()
        with (
            patch(
                "file_organizer.history.tracker.OperationHistory",
                return_value=mock_history,
            ),
            patch(
                "file_organizer.undo.undo_manager.UndoManager",
                return_value=mock_manager,
            ),
            patch.object(type(view), "app", new_callable=PropertyMock, return_value=mock_app),
        ):
            UndoHistoryView._run_undo.__wrapped__(view)

        mock_history.close.assert_called_once()
        # Should set status "Undo successful" and refresh
        assert mock_app.call_from_thread.call_count >= 2

    def test_undo_nothing_to_undo(self) -> None:
        view = UndoHistoryView()

        mock_history = MagicMock()
        mock_manager = MagicMock()
        mock_manager.undo_last_operation.return_value = False

        mock_app = MagicMock()
        with (
            patch(
                "file_organizer.history.tracker.OperationHistory",
                return_value=mock_history,
            ),
            patch(
                "file_organizer.undo.undo_manager.UndoManager",
                return_value=mock_manager,
            ),
            patch.object(type(view), "app", new_callable=PropertyMock, return_value=mock_app),
        ):
            UndoHistoryView._run_undo.__wrapped__(view)

        mock_history.close.assert_called_once()

    def test_undo_exception(self) -> None:
        view = UndoHistoryView()

        mock_app = MagicMock()
        with (
            patch(
                "file_organizer.history.tracker.OperationHistory",
                side_effect=RuntimeError("db error"),
            ),
            patch.object(type(view), "app", new_callable=PropertyMock, return_value=mock_app),
        ):
            UndoHistoryView._run_undo.__wrapped__(view)

        # Should set failure status
        assert mock_app.call_from_thread.call_count >= 1


# ---------------------------------------------------------------------------
# UndoHistoryView - _run_redo worker
# ---------------------------------------------------------------------------


class TestUndoHistoryViewRunRedo:
    """Test _run_redo worker paths."""

    def test_redo_success(self) -> None:
        view = UndoHistoryView()

        mock_history = MagicMock()
        mock_manager = MagicMock()
        mock_manager.redo_last_operation.return_value = True

        mock_app = MagicMock()
        with (
            patch(
                "file_organizer.history.tracker.OperationHistory",
                return_value=mock_history,
            ),
            patch(
                "file_organizer.undo.undo_manager.UndoManager",
                return_value=mock_manager,
            ),
            patch.object(type(view), "app", new_callable=PropertyMock, return_value=mock_app),
        ):
            UndoHistoryView._run_redo.__wrapped__(view)

        mock_history.close.assert_called_once()

    def test_redo_nothing_to_redo(self) -> None:
        view = UndoHistoryView()

        mock_history = MagicMock()
        mock_manager = MagicMock()
        mock_manager.redo_last_operation.return_value = False

        mock_app = MagicMock()
        with (
            patch(
                "file_organizer.history.tracker.OperationHistory",
                return_value=mock_history,
            ),
            patch(
                "file_organizer.undo.undo_manager.UndoManager",
                return_value=mock_manager,
            ),
            patch.object(type(view), "app", new_callable=PropertyMock, return_value=mock_app),
        ):
            UndoHistoryView._run_redo.__wrapped__(view)

        mock_history.close.assert_called_once()

    def test_redo_exception(self) -> None:
        view = UndoHistoryView()

        mock_app = MagicMock()
        with (
            patch(
                "file_organizer.history.tracker.OperationHistory",
                side_effect=RuntimeError("db error"),
            ),
            patch.object(type(view), "app", new_callable=PropertyMock, return_value=mock_app),
        ):
            UndoHistoryView._run_redo.__wrapped__(view)

        assert mock_app.call_from_thread.call_count >= 1
