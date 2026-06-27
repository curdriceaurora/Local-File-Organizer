"""Tests for the copilot rule execution engine."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from file_organizer.history.models import Operation, OperationType
from file_organizer.history.tracker import OperationHistory
from file_organizer.services.copilot.rules.executor import RuleExecutor
from file_organizer.services.copilot.rules.models import (
    ActionType,
    ConditionType,
    Rule,
    RuleAction,
    RuleCondition,
    RuleSet,
)
from file_organizer.undo import UndoManager
from file_organizer.undo.rollback import RollbackExecutor
from file_organizer.undo.validator import OperationValidator

pytestmark = [pytest.mark.unit, pytest.mark.ci, pytest.mark.integration]


def _manager(tmp_path: Path) -> UndoManager:
    return UndoManager(history=OperationHistory(db_path=tmp_path / "history.db"))


def _rule(action: ActionType, destination: str) -> RuleSet:
    return RuleSet(
        name="default",
        rules=[
            Rule(
                name=f"{action.value}-txt",
                conditions=[RuleCondition(condition_type=ConditionType.EXTENSION, value=".txt")],
                action=RuleAction(action_type=action, destination=destination),
            )
        ],
    )


def test_apply_dry_run_uses_preview_matches_without_mutating(tmp_path: Path) -> None:
    source = tmp_path / "note.txt"
    source.write_text("hello", encoding="utf-8")

    result = RuleExecutor(undo_manager=_manager(tmp_path)).apply(
        _rule(ActionType.HARDLINK, "links"),
        tmp_path,
        dry_run=True,
    )

    assert result.skipped_count == 1
    assert result.results[0].message == "dry-run"
    assert source.exists()
    assert not (tmp_path / "links").exists()


def test_apply_skips_symlinked_inputs(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside.txt"
    outside.write_text("secret", encoding="utf-8")
    link = tmp_path / "link.txt"
    link.symlink_to(outside)

    result = RuleExecutor(undo_manager=_manager(tmp_path)).apply(
        _rule(ActionType.COPY, "links"),
        tmp_path,
    )

    assert result.applied_count == 0
    assert not (tmp_path / "links").exists()
    assert link.is_symlink()


def test_apply_hardlink_logs_undoable_operation(tmp_path: Path) -> None:
    source = tmp_path / "note.txt"
    source.write_text("hello", encoding="utf-8")
    manager = _manager(tmp_path)

    result = RuleExecutor(undo_manager=manager).apply(_rule(ActionType.HARDLINK, "links"), tmp_path)

    link = tmp_path / "links" / "note.txt"
    assert result.applied_count == 1
    assert link.exists()
    assert os.stat(source).st_ino == os.stat(link).st_ino
    operations = manager.history.get_operations(transaction_id=result.transaction_id)
    assert operations[0].operation_type == OperationType.HARDLINK


def test_apply_symlink_logs_undoable_operation(tmp_path: Path) -> None:
    source = tmp_path / "note.txt"
    source.write_text("hello", encoding="utf-8")
    manager = _manager(tmp_path)

    result = RuleExecutor(undo_manager=manager).apply(_rule(ActionType.SYMLINK, "links"), tmp_path)

    link = tmp_path / "links" / "note.txt"
    assert result.applied_count == 1
    assert link.is_symlink()
    assert link.resolve() == source
    operations = manager.history.get_operations(transaction_id=result.transaction_id)
    assert operations[0].operation_type == OperationType.SYMLINK


def test_apply_move_uses_resolved_directory_destination(tmp_path: Path) -> None:
    source = tmp_path / "note.txt"
    source.write_text("hello", encoding="utf-8")
    manager = _manager(tmp_path)

    result = RuleExecutor(undo_manager=manager).apply(_rule(ActionType.MOVE, "archive"), tmp_path)

    assert result.applied_count == 1
    assert not source.exists()
    assert (tmp_path / "archive" / "note.txt").read_text(encoding="utf-8") == "hello"


def test_link_actions_undo_and_redo_transaction(tmp_path: Path) -> None:
    for action_type in (ActionType.HARDLINK, ActionType.SYMLINK):
        case_dir = tmp_path / action_type.value
        case_dir.mkdir()
        source = case_dir / "note.txt"
        source.write_text("hello", encoding="utf-8")
        manager = _manager(case_dir)

        result = RuleExecutor(undo_manager=manager).apply(_rule(action_type, "links"), case_dir)
        link = case_dir / "links" / "note.txt"
        assert result.transaction_id is not None
        assert link.exists() or link.is_symlink()

        assert manager.undo_transaction(result.transaction_id) is True
        assert not link.exists() and not link.is_symlink()
        assert source.exists()

        assert manager.redo_transaction(result.transaction_id) is True
        assert link.exists() or link.is_symlink()
        if action_type == ActionType.HARDLINK:
            assert os.stat(source).st_ino == os.stat(link).st_ino
        else:
            assert link.is_symlink()
            assert link.resolve() == source


def test_watch_once_skips_existing_outputs_inside_destination_root(tmp_path: Path) -> None:
    source = tmp_path / "note.txt"
    source.write_text("hello", encoding="utf-8")
    manager = _manager(tmp_path)
    executor = RuleExecutor(undo_manager=manager)

    first = executor.watch(_rule(ActionType.HARDLINK, "links"), tmp_path, once=True)
    second = executor.watch(_rule(ActionType.HARDLINK, "links"), tmp_path, once=True)

    assert first.applied_count == 1
    assert second.applied_count == 0
    assert second.skipped_count == 2
    assert (tmp_path / "links" / "note.txt").exists()
    assert not (tmp_path / "links" / "links").exists()


def test_rollback_executor_handles_link_operation_types(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("hello", encoding="utf-8")
    hardlink = tmp_path / "hardlink.txt"
    symlink = tmp_path / "symlink.txt"
    os.link(source, hardlink)
    symlink.symlink_to(source)
    executor = RollbackExecutor(OperationValidator(trash_dir=tmp_path / "trash"))

    hardlink_op = Operation(
        id=1,
        operation_type=OperationType.HARDLINK,
        timestamp=datetime.now(UTC),
        source_path=source,
        destination_path=hardlink,
    )
    symlink_op = Operation(
        id=2,
        operation_type=OperationType.SYMLINK,
        timestamp=datetime.now(UTC),
        source_path=source,
        destination_path=symlink,
    )

    assert executor.rollback_operation(hardlink_op) is True
    assert executor.rollback_operation(symlink_op) is True
    assert source.exists()
    assert not hardlink.exists()
    assert not symlink.exists() and not symlink.is_symlink()

    assert executor.redo_operation(hardlink_op) is True
    assert executor.redo_operation(symlink_op) is True
    assert os.stat(source).st_ino == os.stat(hardlink).st_ino
    assert symlink.is_symlink()
    assert symlink.resolve() == source


def test_link_operation_error_branches(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("hello", encoding="utf-8")
    not_a_symlink = tmp_path / "plain.txt"
    not_a_symlink.write_text("plain", encoding="utf-8")
    executor = RollbackExecutor(OperationValidator(trash_dir=tmp_path / "trash"))

    missing_dest_op = Operation(
        id=3,
        operation_type=OperationType.HARDLINK,
        timestamp=datetime.now(UTC),
        source_path=source,
        destination_path=None,
    )
    replaced_symlink_op = Operation(
        id=4,
        operation_type=OperationType.SYMLINK,
        timestamp=datetime.now(UTC),
        source_path=source,
        destination_path=not_a_symlink,
    )

    assert executor.redo_operation(missing_dest_op) is False
    assert (
        executor.redo_operation(
            Operation(
                id=5,
                operation_type=OperationType.SYMLINK,
                timestamp=datetime.now(UTC),
                source_path=source,
                destination_path=None,
            )
        )
        is False
    )
    assert executor.rollback_operation(replaced_symlink_op) is False

    validation = executor.validator.validate_undo(replaced_symlink_op)
    assert validation.can_proceed is False
    assert validation.conflicts


def test_link_operation_exception_branches(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("hello", encoding="utf-8")
    hardlink_dest = tmp_path / "occupied-hardlink.txt"
    symlink_dest = tmp_path / "occupied-symlink.txt"
    hardlink_dest.write_text("occupied", encoding="utf-8")
    symlink_dest.write_text("occupied", encoding="utf-8")
    symlink = tmp_path / "symlink.txt"
    symlink.symlink_to(source)
    executor = RollbackExecutor(OperationValidator(trash_dir=tmp_path / "trash"))

    assert (
        executor.rollback_symlink(
            Operation(
                id=6,
                operation_type=OperationType.SYMLINK,
                timestamp=datetime.now(UTC),
                source_path=source,
                destination_path=None,
            )
        )
        is False
    )

    symlink.unlink()
    assert (
        executor.rollback_symlink(
            Operation(
                id=7,
                operation_type=OperationType.SYMLINK,
                timestamp=datetime.now(UTC),
                source_path=source,
                destination_path=symlink,
            )
        )
        is False
    )

    assert (
        executor.redo_hardlink(
            Operation(
                id=8,
                operation_type=OperationType.HARDLINK,
                timestamp=datetime.now(UTC),
                source_path=source,
                destination_path=hardlink_dest,
            )
        )
        is False
    )
    assert (
        executor.redo_symlink(
            Operation(
                id=9,
                operation_type=OperationType.SYMLINK,
                timestamp=datetime.now(UTC),
                source_path=source,
                destination_path=symlink_dest,
            )
        )
        is False
    )
