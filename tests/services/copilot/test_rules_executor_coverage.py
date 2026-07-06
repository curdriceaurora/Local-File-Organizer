"""Tests to verify edge cases and coverage for copilot rules executor and actions."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from file_organizer.history.tracker import OperationHistory
from file_organizer.services.copilot.rules.actions import ConflictStrategy, copy_file
from file_organizer.services.copilot.rules.executor import (
    PostMutationError,
    RuleExecutor,
)
from file_organizer.services.copilot.rules.models import (
    ActionType,
    ConditionType,
    Rule,
    RuleAction,
    RuleCondition,
    RuleSet,
)
from file_organizer.undo import UndoManager

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


def test_copy_file_exclusive_creation_exists(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("hello", encoding="utf-8")
    dest = tmp_path / "dest.txt"
    dest.write_text("already exists", encoding="utf-8")

    # If os.open throws FileExistsError, copy_file should return a skipped LinkResult
    with patch("os.open", side_effect=FileExistsError("exists")):
        res = copy_file(source, dest, ConflictStrategy.SKIP)
        assert res.skipped is True
        assert res.reason == "exists"


@pytest.mark.skipif(
    sys.platform == "win32", reason="copy_file uses SafeDir, whose Windows port is deferred (#264)"
)
def test_copy_file_exception_cleanup(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("hello", encoding="utf-8")
    dest = tmp_path / "dest.txt"

    # Simulate copy failure to ensure cleanup works
    with patch("shutil.copyfileobj", side_effect=OSError("copy failed")):
        with pytest.raises(OSError, match="copy failed"):
            copy_file(source, dest, ConflictStrategy.SKIP)
        assert not dest.exists()


def test_watch_rejects_non_positive_interval(tmp_path: Path) -> None:
    executor = RuleExecutor(undo_manager=_manager(tmp_path))
    rs = _rule(ActionType.COPY, "dest")
    with pytest.raises(ValueError, match="interval_seconds must be positive"):
        executor.watch(rs, tmp_path, interval_seconds=0.0)


def test_path_traversal_absolute_destination(tmp_path: Path) -> None:
    executor = RuleExecutor(undo_manager=_manager(tmp_path))
    abs_dest = str(tmp_path.resolve() / "escapes")
    rs = _rule(ActionType.COPY, abs_dest)
    source = tmp_path / "note.txt"
    source.write_text("hello", encoding="utf-8")

    result = executor.apply(rs, tmp_path)
    assert result.failed_count == 1
    assert "Absolute path not allowed" in result.results[0].message


def test_path_traversal_escaping_base(tmp_path: Path) -> None:
    executor = RuleExecutor(undo_manager=_manager(tmp_path))
    # escapes base_dir using relative traversal
    rs = _rule(ActionType.COPY, "../../../escaped")
    source = tmp_path / "note.txt"
    source.write_text("hello", encoding="utf-8")

    result = executor.apply(rs, tmp_path)
    assert result.failed_count == 1
    assert "Path traversal detected" in result.results[0].message


def test_post_mutation_failure_rollback_move(tmp_path: Path) -> None:
    mgr = _manager(tmp_path)
    executor = RuleExecutor(undo_manager=mgr)
    rs = _rule(ActionType.MOVE, "moved")
    source = tmp_path / "note.txt"
    source.write_text("hello", encoding="utf-8")

    # Mock log_operation to raise an error
    with patch.object(mgr.history, "log_operation", side_effect=RuntimeError("db error")):
        with pytest.raises(PostMutationError, match="db error"):
            executor.apply(rs, tmp_path)

        # The filesystem mutation should be rolled back: source still exists, destination doesn't
        assert source.exists()
        assert not (tmp_path / "moved" / "note.txt").exists()


@pytest.mark.skipif(
    sys.platform == "win32", reason="copy apply uses SafeDir, whose Windows port is deferred (#264)"
)
def test_post_mutation_failure_rollback_copy(tmp_path: Path) -> None:
    mgr = _manager(tmp_path)
    executor = RuleExecutor(undo_manager=mgr)
    rs = _rule(ActionType.COPY, "copied")
    source = tmp_path / "note.txt"
    source.write_text("hello", encoding="utf-8")

    # Mock log_operation to raise an error
    with patch.object(mgr.history, "log_operation", side_effect=RuntimeError("db error")):
        with pytest.raises(PostMutationError, match="db error"):
            executor.apply(rs, tmp_path)

        # The copied file should be unlinked
        assert source.exists()
        assert not (tmp_path / "copied" / "note.txt").exists()


def test_post_mutation_failure_rollback_delete(tmp_path: Path) -> None:
    mgr = _manager(tmp_path)
    executor = RuleExecutor(undo_manager=mgr)
    rs = _rule(ActionType.DELETE, "")
    source = tmp_path / "note.txt"
    source.write_text("hello", encoding="utf-8")

    # Mock log_operation to raise an error
    with patch.object(mgr.history, "log_operation", side_effect=RuntimeError("db error")):
        with pytest.raises(PostMutationError, match="db error"):
            executor.apply(rs, tmp_path)

        # The deleted file should be moved back to the original source location
        assert source.exists()
        assert source.read_text(encoding="utf-8") == "hello"
