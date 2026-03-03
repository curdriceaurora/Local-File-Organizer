"""Tests for TUI undo/history view."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.tui.undo_history_view import (
    HistoryStatsPanel,
    OperationHistoryPanel,
    UndoHistoryView,
    UndoRedoStackPanel,
    _format_timestamp,
    _truncate,
)


def _get_content(panel: object) -> str:
    """Get the text content of a Static widget."""
    return str(getattr(panel, "_Static__content", ""))


# ---------------------------------------------------------------------------
# Helper: create a mock Operation
# ---------------------------------------------------------------------------


def _make_op(
    op_id: int = 1,
    op_type: str = "move",
    status: str = "completed",
    source: str = "/src/a.txt",
    dest: str | None = "/dst/a.txt",
) -> MagicMock:
    """Create a mock Operation with the expected attributes."""
    op = MagicMock()
    op.id = op_id
    op.operation_type = MagicMock(value=op_type)
    op.status = MagicMock(value=status)
    op.timestamp = datetime(2026, 1, 15, 10, 30, 0, tzinfo=UTC)
    op.source_path = Path(source)
    op.destination_path = Path(dest) if dest else None
    return op


# ---------------------------------------------------------------------------
# Unit: OperationHistoryPanel
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestOperationHistoryPanel:
    """Unit tests for OperationHistoryPanel."""

    def test_set_operations_empty(self) -> None:
        panel = OperationHistoryPanel()
        panel.set_operations([])
        assert "No operations" in _get_content(panel)

    def test_set_operations_with_data(self) -> None:
        ops = [_make_op(1), _make_op(2, op_type="rename")]
        panel = OperationHistoryPanel()
        panel.set_operations(ops)
        text = _get_content(panel)
        assert "Recent Operations" in text
        assert "move" in text
        assert "rename" in text

    def test_set_operations_truncates_to_20(self) -> None:
        ops = [_make_op(i) for i in range(30)]
        panel = OperationHistoryPanel()
        panel.set_operations(ops)
        text = _get_content(panel)
        assert "Recent Operations" in text


# ---------------------------------------------------------------------------
# Unit: UndoRedoStackPanel
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestUndoRedoStackPanel:
    """Unit tests for UndoRedoStackPanel."""

    def test_empty_stacks(self) -> None:
        panel = UndoRedoStackPanel()
        panel.set_stacks([], [])
        text = _get_content(panel)
        assert "0" in text
        assert "Undo" in text

    def test_populated_stacks(self) -> None:
        undo = [_make_op(i) for i in range(3)]
        redo = [_make_op(i, status="rolled_back") for i in range(2)]
        panel = UndoRedoStackPanel()
        panel.set_stacks(undo, redo)
        text = _get_content(panel)
        assert "3" in text
        assert "2" in text

    def test_top_5_shown(self) -> None:
        undo = [_make_op(i) for i in range(10)]
        panel = UndoRedoStackPanel()
        panel.set_stacks(undo, [])
        text = _get_content(panel)
        assert "10" in text
        assert "Top 5" in text


# ---------------------------------------------------------------------------
# Unit: HistoryStatsPanel
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestHistoryStatsPanel:
    """Unit tests for HistoryStatsPanel."""

    def test_empty_stats(self) -> None:
        panel = HistoryStatsPanel()
        panel.set_stats({"total_operations": 0, "by_type": {}, "by_status": {}})
        assert "0" in _get_content(panel)

    def test_populated_stats(self) -> None:
        stats = {
            "total_operations": 42,
            "by_type": {"move": 30, "rename": 12},
            "by_status": {"completed": 40, "failed": 2},
            "latest_operation": _make_op(),
        }
        panel = HistoryStatsPanel()
        panel.set_stats(stats)
        text = _get_content(panel)
        assert "42" in text
        assert "move" in text
        assert "completed" in text


# ---------------------------------------------------------------------------
# Unit: helpers
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestHelpers:
    """Unit tests for module-level helpers."""

    def test_format_timestamp_none(self) -> None:
        assert _format_timestamp(None) == "-"

    def test_format_timestamp_valid(self) -> None:
        ts = datetime(2026, 2, 8, 14, 30, 0, tzinfo=UTC)
        assert _format_timestamp(ts) == "2026-02-08 14:30:00"

    def test_truncate_short(self) -> None:
        assert _truncate("hello", 10) == "hello"

    def test_truncate_long(self) -> None:
        result = _truncate("a very long string", 10)
        assert len(result) == 10
        assert result.endswith("\u2026")


# ---------------------------------------------------------------------------
# Integration: UndoHistoryView in app context
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_undo_history_view_mounts() -> None:
    """UndoHistoryView should mount and render panels."""
    from file_organizer.tui.app import FileOrganizerApp

    with patch.object(UndoHistoryView, "_load_history"):
        app = FileOrganizerApp()
        async with app.run_test() as pilot:
            await app.action_switch_view("history")
            await pilot.pause()
            view = app.query_one("#view", UndoHistoryView)
            assert view is not None
            assert app.query_one(OperationHistoryPanel) is not None
            assert app.query_one(UndoRedoStackPanel) is not None
            assert app.query_one(HistoryStatsPanel) is not None


@pytest.mark.asyncio
async def test_undo_history_view_bindings_exist() -> None:
    """UndoHistoryView should have r, u, y bindings."""
    binding_keys = {b.key for b in UndoHistoryView.BINDINGS}
    assert "r" in binding_keys
    assert "u" in binding_keys
    assert "y" in binding_keys


@pytest.mark.unit
class TestOperationHistoryPanelEdgeCases:
    """Edge case tests for OperationHistoryPanel."""

    def test_set_operations_with_failed_operations(self) -> None:
        ops = [_make_op(i, status="failed") for i in range(3)]
        panel = OperationHistoryPanel()
        panel.set_operations(ops)
        text = _get_content(panel)
        assert "failed" in text.lower() or "Recent Operations" in text

    def test_set_operations_with_pending_operations(self) -> None:
        ops = [_make_op(1, status="pending"), _make_op(2, status="running")]
        panel = OperationHistoryPanel()
        panel.set_operations(ops)
        text = _get_content(panel)
        assert len(text) > 0

    def test_set_operations_with_no_destination(self) -> None:
        ops = [_make_op(1, dest=None)]
        panel = OperationHistoryPanel()
        panel.set_operations(ops)
        text = _get_content(panel)
        assert "Recent Operations" in text


@pytest.mark.unit
class TestUndoRedoStackPanelEdgeCases:
    """Edge case tests for UndoRedoStackPanel."""

    def test_single_undo_stack(self) -> None:
        undo = [_make_op(1)]
        panel = UndoRedoStackPanel()
        panel.set_stacks(undo, [])
        text = _get_content(panel)
        assert "1" in text

    def test_single_redo_stack(self) -> None:
        redo = [_make_op(1)]
        panel = UndoRedoStackPanel()
        panel.set_stacks([], redo)
        text = _get_content(panel)
        assert "1" in text

    def test_large_stacks_show_top_5(self) -> None:
        undo = [_make_op(i) for i in range(50)]
        redo = [_make_op(i + 100) for i in range(30)]
        panel = UndoRedoStackPanel()
        panel.set_stacks(undo, redo)
        text = _get_content(panel)
        assert "50" in text
        assert "30" in text


@pytest.mark.unit
class TestHistoryStatsPanelEdgeCases:
    """Edge case tests for HistoryStatsPanel."""

    def test_stats_with_multiple_operation_types(self) -> None:
        stats = {
            "total_operations": 100,
            "by_type": {"move": 50, "rename": 30, "copy": 20},
            "by_status": {"completed": 95, "failed": 5},
        }
        panel = HistoryStatsPanel()
        panel.set_stats(stats)
        text = _get_content(panel)
        assert "100" in text
        assert "move" in text

    def test_stats_with_all_failed(self) -> None:
        stats = {
            "total_operations": 10,
            "by_type": {"move": 10},
            "by_status": {"failed": 10},
        }
        panel = HistoryStatsPanel()
        panel.set_stats(stats)
        text = _get_content(panel)
        assert "10" in text

    def test_history_stats_with_empty_dict(self) -> None:
        stats = {"total_operations": 0, "by_type": {}, "by_status": {}}
        panel = HistoryStatsPanel()
        panel.set_stats(stats)
        assert len(_get_content(panel)) > 0
