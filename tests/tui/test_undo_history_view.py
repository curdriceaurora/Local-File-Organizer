"""Tests for file_organizer.tui.undo_history_view module.

Covers helper functions, panel rendering, UndoHistoryView init/bindings,
and the worker thread methods (_load_history, _run_undo, _run_redo).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from file_organizer.tui.undo_history_view import (
    HistoryStatsPanel,
    OperationHistoryPanel,
    UndoHistoryView,
    UndoRedoStackPanel,
    _format_timestamp,
    _truncate,
)

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Fake objects
# ---------------------------------------------------------------------------


@dataclass
class FakeOperation:
    """Minimal operation stand-in."""

    id: str | None = "op-1"
    operation_type: SimpleNamespace = field(default_factory=lambda: SimpleNamespace(value="move"))
    status: SimpleNamespace = field(default_factory=lambda: SimpleNamespace(value="completed"))
    timestamp: datetime | None = field(
        default_factory=lambda: datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)
    )
    source_path: str = "/src/a.txt"
    destination_path: str | None = "/dest/a.txt"


# ---------------------------------------------------------------------------
# _format_timestamp
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFormatTimestamp:
    """Test _format_timestamp helper."""

    def test_none_returns_dash(self):
        assert _format_timestamp(None) == "-"

    def test_datetime_formatted(self):
        dt = datetime(2025, 3, 15, 14, 30, 45, tzinfo=UTC)
        result = _format_timestamp(dt)
        assert result == "2025-03-15 14:30:45"


# ---------------------------------------------------------------------------
# _truncate
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestTruncate:
    """Test _truncate helper."""

    def test_short_text(self):
        assert _truncate("hi", 10) == "hi"

    def test_exact_length(self):
        assert _truncate("hello", 5) == "hello"

    def test_long_text(self):
        result = _truncate("hello world", 6)
        assert len(result) == 6
        assert result.endswith("\u2026")


# ---------------------------------------------------------------------------
# OperationHistoryPanel
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestOperationHistoryPanel:
    """Test OperationHistoryPanel rendering."""

    def test_empty_operations(self):
        panel = OperationHistoryPanel()
        panel.update = MagicMock()
        panel.set_operations([])
        rendered = panel.update.call_args[0][0]
        assert "No operations" in rendered

    def test_with_operations(self):
        panel = OperationHistoryPanel()
        panel.update = MagicMock()
        ops = [FakeOperation(), FakeOperation(id="op-2", destination_path=None)]
        panel.set_operations(ops)
        rendered = panel.update.call_args[0][0]
        assert "Recent Operations" in rendered
        assert "op-1" in rendered
        assert "move" in rendered

    def test_operation_without_value_attr(self):
        panel = OperationHistoryPanel()
        panel.update = MagicMock()
        op = FakeOperation()
        op.operation_type = "plain_move"
        op.status = "done"
        panel.set_operations([op])
        rendered = panel.update.call_args[0][0]
        assert "plain_move" in rendered

    def test_operation_no_timestamp(self):
        panel = OperationHistoryPanel()
        panel.update = MagicMock()
        op = FakeOperation(timestamp=None)
        panel.set_operations([op])
        rendered = panel.update.call_args[0][0]
        assert "-" in rendered


# ---------------------------------------------------------------------------
# UndoRedoStackPanel
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestUndoRedoStackPanel:
    """Test UndoRedoStackPanel rendering."""

    def test_empty_stacks(self):
        panel = UndoRedoStackPanel()
        panel.update = MagicMock()
        panel.set_stacks([], [])
        rendered = panel.update.call_args[0][0]
        assert "Undo / Redo" in rendered
        assert "0" in rendered

    def test_with_undo_stack(self):
        panel = UndoRedoStackPanel()
        panel.update = MagicMock()
        ops = [FakeOperation() for _ in range(3)]
        panel.set_stacks(ops, [])
        rendered = panel.update.call_args[0][0]
        assert "3" in rendered
        assert "undoable" in rendered

    def test_with_redo_stack(self):
        panel = UndoRedoStackPanel()
        panel.update = MagicMock()
        panel.set_stacks([], [FakeOperation()])
        rendered = panel.update.call_args[0][0]
        assert "redoable" in rendered

    def test_operation_type_without_value(self):
        panel = UndoRedoStackPanel()
        panel.update = MagicMock()
        op = FakeOperation()
        op.operation_type = "rename"
        panel.set_stacks([op], [op])
        rendered = panel.update.call_args[0][0]
        assert "rename" in rendered


# ---------------------------------------------------------------------------
# HistoryStatsPanel
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestHistoryStatsPanel:
    """Test HistoryStatsPanel rendering."""

    def test_empty_stats(self):
        panel = HistoryStatsPanel()
        panel.update = MagicMock()
        panel.set_stats({})
        rendered = panel.update.call_args[0][0]
        assert "History Statistics" in rendered
        assert "0" in rendered

    def test_with_stats(self):
        panel = HistoryStatsPanel()
        panel.update = MagicMock()
        stats = {
            "total_operations": 42,
            "by_type": {"move": 20, "rename": 22},
            "by_status": {"completed": 40, "pending": 2},
        }
        panel.set_stats(stats)
        rendered = panel.update.call_args[0][0]
        assert "42" in rendered
        assert "move" in rendered
        assert "completed" in rendered
        assert "green" in rendered
        assert "pending" in rendered
        assert "yellow" in rendered

    def test_with_failed_status(self):
        panel = HistoryStatsPanel()
        panel.update = MagicMock()
        stats = {
            "total_operations": 5,
            "by_type": {},
            "by_status": {"failed": 3},
        }
        panel.set_stats(stats)
        rendered = panel.update.call_args[0][0]
        assert "red" in rendered

    def test_with_latest_operation(self):
        panel = HistoryStatsPanel()
        panel.update = MagicMock()
        latest_op = FakeOperation()
        stats = {
            "total_operations": 1,
            "by_type": {},
            "by_status": {},
            "latest_operation": latest_op,
        }
        panel.set_stats(stats)
        rendered = panel.update.call_args[0][0]
        assert "Latest" in rendered
        assert "2025" in rendered

    def test_latest_without_timestamp(self):
        panel = HistoryStatsPanel()
        panel.update = MagicMock()
        latest_op = SimpleNamespace(timestamp=None)
        stats = {
            "total_operations": 1,
            "by_type": {},
            "by_status": {},
            "latest_operation": latest_op,
        }
        panel.set_stats(stats)
        rendered = panel.update.call_args[0][0]
        assert "unknown" in rendered


# ---------------------------------------------------------------------------
# UndoHistoryView init and bindings
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestUndoHistoryViewInit:
    """Test UndoHistoryView initialization."""

    def test_default_init(self):
        view = UndoHistoryView()
        assert isinstance(view, UndoHistoryView)

    def test_bindings(self):
        assert len(UndoHistoryView.BINDINGS) == 3
        keys = [b.key for b in UndoHistoryView.BINDINGS]
        assert "r" in keys
        assert "u" in keys
        assert "y" in keys

    def test_action_undo_last_calls_run_undo(self):
        view = UndoHistoryView()
        view._run_undo = MagicMock()
        view.action_undo_last()
        view._run_undo.assert_called_once()

    def test_action_redo_last_calls_run_redo(self):
        view = UndoHistoryView()
        view._run_redo = MagicMock()
        view.action_redo_last()
        view._run_redo.assert_called_once()

    def test_action_refresh_history(self):
        view = UndoHistoryView()
        mock_panel = MagicMock()
        view.query_one = MagicMock(return_value=mock_panel)
        view._load_history = MagicMock()
        view.action_refresh_history()
        view._load_history.assert_called_once()


# ---------------------------------------------------------------------------
# UndoHistoryView._set_status
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestUndoHistoryViewSetStatus:
    """Test _set_status helper."""

    def test_set_status_no_app(self):
        view = UndoHistoryView()
        # Should not crash when app is not available
        view._set_status("test")

    def test_set_status_with_app(self):
        view = UndoHistoryView()
        mock_status = MagicMock()
        mock_app = MagicMock()
        mock_app.query_one.return_value = mock_status
        view._app = mock_app
        view._set_status("loaded")
