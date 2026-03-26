"""Direct tests for file_organizer.cli.undo_history helper functions."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from file_organizer.cli import undo_history

pytestmark = [pytest.mark.ci, pytest.mark.unit]


def _make_operation(op_id: int = 1, op_type: str = "move", dst: str | None = "/dst/file.txt"):
    op = MagicMock()
    op.id = op_id
    op.operation_type = MagicMock()
    op.operation_type.value = op_type
    op.source_path = Path("/src/file.txt")
    op.destination_path = Path(dst) if dst else None
    return op


class TestUndoHistoryHelpers:
    def test_get_undo_stack_delegates(self) -> None:
        manager = MagicMock()
        manager.get_undo_stack.return_value = ["undo"]
        assert undo_history.get_undo_stack(manager) == ["undo"]

    def test_get_redo_stack_delegates(self) -> None:
        manager = MagicMock()
        manager.get_redo_stack.return_value = ["redo"]
        assert undo_history.get_redo_stack(manager) == ["redo"]

    def test_can_undo_operation_delegates(self) -> None:
        manager = MagicMock()
        manager.can_undo.return_value = (True, "")
        assert undo_history.can_undo_operation(manager, 4) == (True, "")

    def test_can_redo_operation_delegates(self) -> None:
        manager = MagicMock()
        manager.can_redo.return_value = (False, "blocked")
        assert undo_history.can_redo_operation(manager, 4) == (False, "blocked")

    def test_find_operation_in_stack_returns_match(self) -> None:
        op = _make_operation(op_id=9)
        assert undo_history.find_operation_in_stack([_make_operation(), op], 9) is op

    def test_find_operation_in_stack_returns_none_when_missing(self) -> None:
        assert undo_history.find_operation_in_stack([_make_operation(op_id=1)], 3) is None

    def test_format_operation_summary_with_destination(self) -> None:
        summary = undo_history.format_operation_summary(_make_operation())
        assert "Type: move" in summary
        assert "Destination:" in summary

    def test_format_operation_summary_without_destination(self) -> None:
        summary = undo_history.format_operation_summary(_make_operation(dst=None))
        assert "Destination:" not in summary

    def test_format_transaction_summary_truncates(self) -> None:
        ops = [_make_operation(op_id=index) for index in range(7)]
        summary = undo_history.format_transaction_summary("tx-1", ops, limit=5)
        assert "Operations: 7" in summary
        assert "... and 2 more" in summary

    def test_normalize_transaction_id(self) -> None:
        assert undo_history.normalize_transaction_id(None) is None
        assert undo_history.normalize_transaction_id("   ") is None
        assert undo_history.normalize_transaction_id(" tx-1 ") == "tx-1"


class TestUndoHistoryPreviewHelpers:
    def test_preview_undo_operation_success(self, capsys) -> None:
        manager = MagicMock()
        manager.can_undo.return_value = (True, "")
        manager.get_undo_stack.return_value = [_make_operation(op_id=5)]

        result = undo_history.preview_undo_operation(manager, 5)

        assert result == 0
        assert "Would undo operation 5" in capsys.readouterr().out

    def test_preview_undo_operation_not_found(self, capsys) -> None:
        manager = MagicMock()
        manager.can_undo.return_value = (True, "")
        manager.get_undo_stack.return_value = []

        result = undo_history.preview_undo_operation(manager, 99)

        assert result == 1
        assert "not found" in capsys.readouterr().out

    def test_preview_undo_operation_cannot_undo(self, capsys) -> None:
        manager = MagicMock()
        manager.can_undo.return_value = (False, "blocked")

        result = undo_history.preview_undo_operation(manager, 4)

        assert result == 1
        assert "Cannot undo operation 4" in capsys.readouterr().out

    def test_preview_undo_transaction_success(self, capsys) -> None:
        manager = MagicMock()
        manager.history.get_transaction.return_value = MagicMock()
        manager.history.get_operations.return_value = [_make_operation(op_id=1)]

        result = undo_history.preview_undo_transaction(manager, " tx-abc ")

        assert result == 0
        output = capsys.readouterr().out
        assert "Would undo transaction tx-abc" in output
        assert "Operations: 1" in output

    def test_preview_undo_transaction_rejects_blank_id(self, capsys) -> None:
        manager = MagicMock()

        result = undo_history.preview_undo_transaction(manager, "   ")

        assert result == 1
        assert "must not be empty" in capsys.readouterr().out

    def test_preview_undo_last(self, capsys) -> None:
        manager = MagicMock()
        manager.get_undo_stack.return_value = [_make_operation(op_id=8)]

        result = undo_history.preview_undo_last(manager)

        assert result == 0
        assert "Would undo last operation (8)" in capsys.readouterr().out

    def test_preview_undo_last_empty_stack(self, capsys) -> None:
        manager = MagicMock()
        manager.get_undo_stack.return_value = []

        result = undo_history.preview_undo_last(manager)

        assert result == 1
        assert "No operations to undo" in capsys.readouterr().out

    def test_preview_redo_operation_success(self, capsys) -> None:
        manager = MagicMock()
        manager.can_redo.return_value = (True, "")
        manager.get_redo_stack.return_value = [_make_operation(op_id=11)]

        result = undo_history.preview_redo_operation(manager, 11)

        assert result == 0
        assert "Would redo operation 11" in capsys.readouterr().out

    def test_preview_redo_operation_missing(self, capsys) -> None:
        manager = MagicMock()
        manager.can_redo.return_value = (True, "")
        manager.get_redo_stack.return_value = []

        result = undo_history.preview_redo_operation(manager, 11)

        assert result == 1
        assert "not found in redo stack" in capsys.readouterr().out

    def test_preview_redo_last(self, capsys) -> None:
        manager = MagicMock()
        manager.get_redo_stack.return_value = [_make_operation(op_id=14)]

        result = undo_history.preview_redo_last(manager)

        assert result == 0
        assert "Would redo last operation (14)" in capsys.readouterr().out

    def test_preview_redo_last_empty_stack(self, capsys) -> None:
        manager = MagicMock()
        manager.get_redo_stack.return_value = []

        result = undo_history.preview_redo_last(manager)

        assert result == 1
        assert "No operations to redo" in capsys.readouterr().out


class TestUndoHistoryExecuteHelpers:
    def test_execute_undo_transaction(self, capsys) -> None:
        manager = MagicMock()
        manager.undo_transaction.return_value = True

        result = undo_history.execute_undo(manager, transaction_id=" tx-1 ")

        assert result == 0
        manager.undo_transaction.assert_called_once_with("tx-1")
        assert "Undoing transaction tx-1" in capsys.readouterr().out

    def test_execute_undo_blank_transaction_falls_back_to_operation(self, capsys) -> None:
        manager = MagicMock()
        manager.undo_operation.return_value = True

        result = undo_history.execute_undo(manager, operation_id=7, transaction_id="   ")

        assert result == 0
        manager.undo_transaction.assert_not_called()
        manager.undo_operation.assert_called_once_with(7)
        assert "Undoing operation 7" in capsys.readouterr().out

    def test_execute_undo_last_operation(self, capsys) -> None:
        manager = MagicMock()
        manager.undo_last_operation.return_value = False

        result = undo_history.execute_undo(manager)

        assert result == 1
        assert "Undoing last operation" in capsys.readouterr().out

    def test_execute_redo_specific_operation(self, capsys) -> None:
        manager = MagicMock()
        manager.redo_operation.return_value = True

        result = undo_history.execute_redo(manager, operation_id=3)

        assert result == 0
        manager.redo_operation.assert_called_once_with(3)
        assert "Redoing operation 3" in capsys.readouterr().out

    def test_execute_redo_last_operation(self, capsys) -> None:
        manager = MagicMock()
        manager.redo_last_operation.return_value = False

        result = undo_history.execute_redo(manager)

        assert result == 1
        assert "Redoing last operation" in capsys.readouterr().out
