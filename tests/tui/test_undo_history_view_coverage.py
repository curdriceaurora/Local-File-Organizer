# ruff: noqa: E402
"""Unit and integration coverage tests for file_organizer.tui.undo_history_view.

Targets 100% statement and branch coverage for UndoHistoryView and its panels.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, PropertyMock, patch

import pytest


# 1. Mock textual.work decorator BEFORE importing UndoHistoryView
def mock_work_decorator(*args, **kwargs):
    if len(args) == 1 and callable(args[0]):
        return args[0]
    return lambda f: f


import textual

textual.work = mock_work_decorator

from textual.widgets import Static

from file_organizer.tui.undo_history_view import (
    HistoryStatsPanel,
    OperationHistoryPanel,
    UndoHistoryView,
    UndoRedoStackPanel,
    _format_timestamp,
    _truncate,
)

pytestmark = pytest.mark.unit


def _create_view_with_mocks() -> tuple[UndoHistoryView, dict[type[Static], MagicMock], MagicMock]:
    """Helper to create an UndoHistoryView with panels and app mocked."""
    view = UndoHistoryView()

    # Mock panels
    mock_hist_panel = MagicMock(spec=OperationHistoryPanel)
    mock_stack_panel = MagicMock(spec=UndoRedoStackPanel)
    mock_stats_panel = MagicMock(spec=HistoryStatsPanel)

    panels = {
        OperationHistoryPanel: mock_hist_panel,
        UndoRedoStackPanel: mock_stack_panel,
        HistoryStatsPanel: mock_stats_panel,
    }

    def mock_query_one(panel_type):
        return panels.get(panel_type, MagicMock())

    view.query_one = MagicMock(side_effect=mock_query_one)

    # Mock app property
    mock_app = MagicMock()
    app_prop = PropertyMock(return_value=mock_app)
    type(view).app = app_prop

    # Force call_from_thread to execute synchronously in tests
    mock_app.call_from_thread = lambda func, *args, **kwargs: func(*args, **kwargs)

    return view, panels, mock_app


# --- Panel Tests ---


def test_operation_history_panel_empty() -> None:
    """Verify OperationHistoryPanel behavior with no operations."""
    panel = OperationHistoryPanel()
    with patch.object(panel, "update") as mock_update:
        panel.set_operations([])
        mock_update.assert_called_once_with(
            "[b]Recent Operations[/b]\n\n  [dim]No operations recorded.[/dim]"
        )


def test_operation_history_panel_with_ops() -> None:
    """Verify OperationHistoryPanel with diverse operation properties."""
    panel = OperationHistoryPanel()

    # Op 1: All properties filled, uses Enum-like values
    op1 = MagicMock()
    op1.id = 101
    op1.operation_type = MagicMock()
    op1.operation_type.value = "move"
    op1.status = MagicMock()
    op1.status.value = "completed"
    op1.timestamp = datetime(2024, 6, 25, 12, 0, 0, tzinfo=UTC)
    op1.source_path = "/src/path/to/my/long_filename_1.txt"
    op1.destination_path = "/dest/path/to/my/long_filename_2.txt"

    # Op 2: Missing/raw properties, no destination
    op2 = MagicMock()
    op2.id = None
    op2.operation_type = "delete"
    op2.status = "failed"
    op2.timestamp = None
    op2.source_path = "short.txt"
    op2.destination_path = None

    with patch.object(panel, "update") as mock_update:
        panel.set_operations([op1, op2])
        markup = mock_update.call_args[0][0]
        assert "Recent Operations" in markup
        assert "101" in markup
        assert "move" in markup
        assert "completed" in markup
        assert "2024-06-25 12:00:00" in markup

        # Op 2 checks
        assert "-" in markup  # for missing id, timestamp, destination
        assert "delete" in markup
        assert "failed" in markup
        assert "short.txt" in markup


def test_undo_redo_stack_panel() -> None:
    """Verify UndoRedoStackPanel handles empty, populated, and Enum-based operations."""
    panel = UndoRedoStackPanel()

    # 1. Empty stacks
    with patch.object(panel, "update") as mock_update:
        panel.set_stacks([], [])
        markup = mock_update.call_args[0][0]
        assert "Undo stack: [cyan]0[/cyan] operations" in markup
        assert "Redo stack: [cyan]0[/cyan] operations" in markup
        assert "Top 5" not in markup

    # 2. Populated stacks
    op_undo = MagicMock()
    op_undo.operation_type = MagicMock()
    op_undo.operation_type.value = "rename"
    op_undo.source_path = "undo_src.txt"

    op_redo = MagicMock()
    op_redo.operation_type = "move"
    op_redo.source_path = "redo_src.txt"

    with patch.object(panel, "update") as mock_update:
        panel.set_stacks([op_undo], [op_redo])
        markup = mock_update.call_args[0][0]
        assert "Undo stack: [cyan]1[/cyan] operations" in markup
        assert "Top 5 undoable:" in markup
        assert "rename" in markup
        assert "undo_src.txt" in markup

        assert "Redo stack: [cyan]1[/cyan] operations" in markup
        assert "Top 5 redoable:" in markup
        assert "move" in markup
        assert "redo_src.txt" in markup


def test_history_stats_panel() -> None:
    """Verify HistoryStatsPanel displays statistics, types, status colors, and latest operation."""
    panel = HistoryStatsPanel()

    # 1. Empty stats
    with patch.object(panel, "update") as mock_update:
        panel.set_stats({})
        markup = mock_update.call_args[0][0]
        assert "Total operations: [cyan]0[/cyan]" in markup

    # 2. Detailed stats
    latest_op = MagicMock()
    latest_op.timestamp = datetime(2024, 6, 25, 15, 30, 0, tzinfo=UTC)

    stats = {
        "total_operations": 42,
        "by_type": {"move": 30, "delete": 12},
        "by_status": {"completed": 35, "pending": 5, "failed": 2},
        "latest_operation": latest_op,
    }

    with patch.object(panel, "update") as mock_update:
        panel.set_stats(stats)
        markup = mock_update.call_args[0][0]
        assert "Total operations: [cyan]42[/cyan]" in markup
        assert "move" in markup
        assert "30" in markup
        assert "delete" in markup
        assert "12" in markup

        # Color checks
        assert "[green]   35[/green]" in markup  # completed
        assert "[yellow]    5[/yellow]" in markup  # pending
        assert "[red]    2[/red]" in markup  # failed

        # Latest check
        assert "Latest: 2024-06-25 15:30:00" in markup

    # 3. Latest operation without timestamp
    latest_op_no_ts = MagicMock()
    latest_op_no_ts.timestamp = None
    stats["latest_operation"] = latest_op_no_ts

    with patch.object(panel, "update") as mock_update:
        panel.set_stats(stats)
        markup = mock_update.call_args[0][0]
        assert "Latest: unknown" in markup


# --- UndoHistoryView Tests ---


def test_undo_history_view_initialization() -> None:
    """Verify UndoHistoryView setup."""
    view = UndoHistoryView()
    assert isinstance(view, UndoHistoryView)


def test_undo_history_view_compose() -> None:
    """Verify widgets yielded by compose."""
    view = UndoHistoryView()
    widgets = list(view.compose())
    assert len(widgets) == 4
    assert widgets[0].id == "history-header"
    assert isinstance(widgets[1], OperationHistoryPanel)
    assert isinstance(widgets[2], UndoRedoStackPanel)
    assert isinstance(widgets[3], HistoryStatsPanel)


def test_undo_history_view_on_mount() -> None:
    """Verify on_mount triggers history load."""
    view, _, _ = _create_view_with_mocks()
    with patch.object(view, "_load_history") as mock_load:
        view.on_mount()
        mock_load.assert_called_once()


def test_undo_history_view_action_refresh_history() -> None:
    """Verify refresh action updates panels and triggers load."""
    view, panels, _ = _create_view_with_mocks()
    with patch.object(view, "_load_history") as mock_load:
        view.action_refresh_history()
        for panel in panels.values():
            panel.update.assert_called_once_with("[dim]Refreshing...[/dim]")
        mock_load.assert_called_once()


def test_undo_history_view_action_undo_redo() -> None:
    """Verify action bindings trigger appropriate background tasks."""
    view, _, _ = _create_view_with_mocks()
    with (
        patch.object(view, "_run_undo") as mock_undo,
        patch.object(view, "_run_redo") as mock_redo,
    ):
        view.action_undo_last()
        mock_undo.assert_called_once()

        view.action_redo_last()
        mock_redo.assert_called_once()


def test_undo_history_view_load_history_success() -> None:
    """Verify successful history loading parses stacks and stats."""
    view, panels, _ = _create_view_with_mocks()

    mock_history = MagicMock()
    mock_history.get_recent_operations.return_value = ["op1"]

    mock_manager = MagicMock()
    mock_manager.get_undo_stack.return_value = ["undo1"]
    mock_manager.get_redo_stack.return_value = ["redo1"]

    mock_viewer = MagicMock()
    mock_viewer.get_statistics.return_value = {"total_operations": 5}

    with (
        patch("file_organizer.history.tracker.OperationHistory", return_value=mock_history),
        patch("file_organizer.undo.undo_manager.UndoManager", return_value=mock_manager),
        patch("file_organizer.undo.viewer.HistoryViewer", return_value=mock_viewer),
        patch.object(view, "_set_status") as mock_status,
    ):
        view._load_history()

        mock_history.close.assert_called_once()
        panels[OperationHistoryPanel].set_operations.assert_called_once_with(["op1"])
        panels[UndoRedoStackPanel].set_stacks.assert_called_once_with(["undo1"], ["redo1"])
        panels[HistoryStatsPanel].set_stats.assert_called_once_with({"total_operations": 5})
        mock_status.assert_called_once_with("History loaded")


def test_undo_history_view_load_history_failure() -> None:
    """Verify load history exceptions update all panels with the error."""
    view, panels, _ = _create_view_with_mocks()

    with patch(
        "file_organizer.history.tracker.OperationHistory", side_effect=ValueError("DB locked")
    ):
        view._load_history()

        for panel in panels.values():
            panel.update.assert_called_once()
            assert "DB locked" in panel.update.call_args[0][0]


def test_undo_history_view_run_undo_success_with_op() -> None:
    """Verify run_undo when an operation is successfully undone."""
    view, _, _ = _create_view_with_mocks()

    mock_history = MagicMock()
    mock_manager = MagicMock()
    mock_manager.undo_last_operation.return_value = True

    with (
        patch("file_organizer.history.tracker.OperationHistory", return_value=mock_history),
        patch("file_organizer.undo.undo_manager.UndoManager", return_value=mock_manager),
        patch.object(view, "_set_status") as mock_status,
        patch.object(view, "action_refresh_history") as mock_refresh,
    ):
        view._run_undo()

        mock_history.close.assert_called_once()
        mock_status.assert_called_once_with("Undo successful")
        mock_refresh.assert_called_once()


def test_undo_history_view_run_undo_success_no_op() -> None:
    """Verify run_undo when there is nothing to undo."""
    view, _, _ = _create_view_with_mocks()

    mock_history = MagicMock()
    mock_manager = MagicMock()
    mock_manager.undo_last_operation.return_value = False

    with (
        patch("file_organizer.history.tracker.OperationHistory", return_value=mock_history),
        patch("file_organizer.undo.undo_manager.UndoManager", return_value=mock_manager),
        patch.object(view, "_set_status") as mock_status,
        patch.object(view, "action_refresh_history") as mock_refresh,
    ):
        view._run_undo()

        mock_status.assert_called_once_with("Nothing to undo")
        mock_refresh.assert_called_once()


def test_undo_history_view_run_undo_failure() -> None:
    """Verify run_undo handles database/execution errors."""
    view, _, _ = _create_view_with_mocks()

    with (
        patch(
            "file_organizer.history.tracker.OperationHistory", side_effect=RuntimeError("disk full")
        ),
        patch.object(view, "_set_status") as mock_status,
        patch.object(view, "action_refresh_history") as mock_refresh,
    ):
        view._run_undo()

        mock_status.assert_called_once_with("Undo failed: disk full")
        mock_refresh.assert_called_once()


def test_undo_history_view_run_redo_success_with_op() -> None:
    """Verify run_redo when an operation is successfully redone."""
    view, _, _ = _create_view_with_mocks()

    mock_history = MagicMock()
    mock_manager = MagicMock()
    mock_manager.redo_last_operation.return_value = True

    with (
        patch("file_organizer.history.tracker.OperationHistory", return_value=mock_history),
        patch("file_organizer.undo.undo_manager.UndoManager", return_value=mock_manager),
        patch.object(view, "_set_status") as mock_status,
        patch.object(view, "action_refresh_history") as mock_refresh,
    ):
        view._run_redo()

        mock_history.close.assert_called_once()
        mock_status.assert_called_once_with("Redo successful")
        mock_refresh.assert_called_once()


def test_undo_history_view_run_redo_success_no_op() -> None:
    """Verify run_redo when there is nothing to redo."""
    view, _, _ = _create_view_with_mocks()

    mock_history = MagicMock()
    mock_manager = MagicMock()
    mock_manager.redo_last_operation.return_value = False

    with (
        patch("file_organizer.history.tracker.OperationHistory", return_value=mock_history),
        patch("file_organizer.undo.undo_manager.UndoManager", return_value=mock_manager),
        patch.object(view, "_set_status") as mock_status,
        patch.object(view, "action_refresh_history") as mock_refresh,
    ):
        view._run_redo()

        mock_status.assert_called_once_with("Nothing to redo")
        mock_refresh.assert_called_once()


def test_undo_history_view_run_redo_failure() -> None:
    """Verify run_redo handles database/execution errors."""
    view, _, _ = _create_view_with_mocks()

    with (
        patch(
            "file_organizer.history.tracker.OperationHistory",
            side_effect=RuntimeError("connection dropped"),
        ),
        patch.object(view, "_set_status") as mock_status,
        patch.object(view, "action_refresh_history") as mock_refresh,
    ):
        view._run_redo()

        mock_status.assert_called_once_with("Redo failed: connection dropped")
        mock_refresh.assert_called_once()


def test_undo_history_view_status_bar_updates() -> None:
    """Verify status updates resolve cleanly or log on failure."""
    view, _, mock_app = _create_view_with_mocks()

    # 1. Success
    mock_status_bar = MagicMock()
    mock_app.query_one.return_value = mock_status_bar
    view._set_status("Loading history")
    mock_status_bar.set_status.assert_called_once_with("Loading history")

    # 2. Exception fallback
    mock_app.query_one.side_effect = Exception("No status bar")
    with patch("file_organizer.tui.undo_history_view.logger") as mock_logger:
        view._set_status("Loading history")
        mock_logger.debug.assert_called_once()


# --- Helper Function Tests ---


def test_format_timestamp_helper() -> None:
    """Verify datetime formatting helper handles None and valid dates."""
    assert _format_timestamp(None) == "-"
    dt = datetime(2025, 1, 15, 9, 45, 30, tzinfo=UTC)
    assert _format_timestamp(dt) == "2025-01-15 09:45:30"


def test_truncate_helper() -> None:
    """Verify string truncation helper."""
    assert _truncate("hello", 10) == "hello"
    assert _truncate("hello world", 5) == "hell\u2026"
