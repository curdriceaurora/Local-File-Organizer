"""Coverage tests for RollbackExecutor — targets uncovered branches."""

from __future__ import annotations

from pathlib import Path

import pytest

from file_organizer.history.models import Operation, OperationType
from file_organizer.undo.rollback import RollbackExecutor

pytestmark = pytest.mark.unit


def _make_op(
    op_type: OperationType,
    src: Path,
    dest: Path | None = None,
    op_id: int = 1,
    metadata: dict | None = None,
) -> Operation:
    return Operation(
        id=op_id,
        operation_type=op_type,
        timestamp="2025-01-01T00:00:00Z",
        source_path=src,
        destination_path=dest,
        status="completed",
        metadata=metadata or {},
    )


@pytest.fixture()
def executor(tmp_path):
    ex = RollbackExecutor()
    ex.trash_dir = tmp_path / ".trash"
    ex.trash_dir.mkdir()
    ex.validator.trash_dir = ex.trash_dir
    return ex


# ---------------------------------------------------------------------------
# rollback_operation dispatch
# ---------------------------------------------------------------------------


class TestRollbackOperation:
    def test_rollback_move(self, executor, tmp_path):
        src = tmp_path / "src.txt"
        dest = tmp_path / "dest.txt"
        dest.write_text("content")
        op = _make_op(OperationType.MOVE, src, dest)
        result = executor.rollback_operation(op)
        assert result is True
        assert src.exists()

    def test_rollback_rename(self, executor, tmp_path):
        old = tmp_path / "old.txt"
        new = tmp_path / "new.txt"
        new.write_text("content")
        op = _make_op(OperationType.RENAME, old, new)
        result = executor.rollback_operation(op)
        assert result is True
        assert old.exists()

    def test_rollback_copy(self, executor, tmp_path):
        src = tmp_path / "src.txt"
        dest = tmp_path / "copy.txt"
        dest.write_text("content")
        op = _make_op(OperationType.COPY, src, dest)
        result = executor.rollback_operation(op)
        assert result is True
        assert not dest.exists()

    def test_rollback_create(self, executor, tmp_path):
        created = tmp_path / "created.txt"
        created.write_text("content")
        op = _make_op(OperationType.CREATE, created)
        result = executor.rollback_operation(op)
        assert result is True
        assert not created.exists()

    def test_rollback_delete_no_trash(self, executor, tmp_path):
        src = tmp_path / "deleted.txt"
        op = _make_op(OperationType.DELETE, src)
        result = executor.rollback_operation(op)
        assert result is False

    def test_rollback_unknown_type(self, executor, tmp_path):
        op = _make_op(OperationType.MOVE, tmp_path / "x")
        op.operation_type = "weird_type"
        result = executor.rollback_operation(op)
        assert result is False

    def test_rollback_exception(self, executor, tmp_path):
        op = _make_op(OperationType.MOVE, tmp_path / "x", tmp_path / "nonexistent")
        result = executor.rollback_operation(op)
        assert result is False


# ---------------------------------------------------------------------------
# redo_operation dispatch
# ---------------------------------------------------------------------------


class TestRedoOperation:
    def test_redo_move(self, executor, tmp_path):
        src = tmp_path / "src.txt"
        dest = tmp_path / "dest.txt"
        src.write_text("content")
        op = _make_op(OperationType.MOVE, src, dest)
        result = executor.redo_operation(op)
        assert result is True
        assert dest.exists()

    def test_redo_rename(self, executor, tmp_path):
        old = tmp_path / "old.txt"
        new = tmp_path / "new.txt"
        old.write_text("content")
        op = _make_op(OperationType.RENAME, old, new)
        result = executor.redo_operation(op)
        assert result is True
        assert new.exists()

    def test_redo_copy_file(self, executor, tmp_path):
        src = tmp_path / "src.txt"
        dest = tmp_path / "copy.txt"
        src.write_text("content")
        op = _make_op(OperationType.COPY, src, dest)
        result = executor.redo_operation(op)
        assert result is True
        assert dest.exists()

    def test_redo_copy_dir(self, executor, tmp_path):
        src = tmp_path / "srcdir"
        src.mkdir()
        (src / "f.txt").write_text("data")
        dest = tmp_path / "copydir"
        op = _make_op(OperationType.COPY, src, dest)
        result = executor.redo_operation(op)
        assert result is True
        assert dest.exists()

    def test_redo_copy_missing_source(self, executor, tmp_path):
        src = tmp_path / "missing"
        dest = tmp_path / "copy"
        op = _make_op(OperationType.COPY, src, dest)
        result = executor.redo_operation(op)
        assert result is False

    def test_redo_delete(self, executor, tmp_path):
        f = tmp_path / "to_delete.txt"
        f.write_text("content")
        op = _make_op(OperationType.DELETE, f)
        result = executor.redo_operation(op)
        assert result is True
        assert not f.exists()

    def test_redo_create_file(self, executor, tmp_path):
        f = tmp_path / "new_file.txt"
        op = _make_op(OperationType.CREATE, f, metadata={})
        result = executor.redo_operation(op)
        assert result is True
        assert f.exists()

    def test_redo_create_dir(self, executor, tmp_path):
        d = tmp_path / "new_dir"
        op = _make_op(OperationType.CREATE, d, metadata={"is_dir": True})
        result = executor.redo_operation(op)
        assert result is True
        assert d.is_dir()

    def test_redo_unknown_type(self, executor, tmp_path):
        op = _make_op(OperationType.MOVE, tmp_path / "x")
        op.operation_type = "weird"
        result = executor.redo_operation(op)
        assert result is False

    def test_redo_exception(self, executor, tmp_path):
        op = _make_op(OperationType.RENAME, tmp_path / "missing", tmp_path / "dest")
        result = executor.redo_operation(op)
        assert result is False


# ---------------------------------------------------------------------------
# rollback_transaction
# ---------------------------------------------------------------------------


class TestRollbackTransaction:
    def test_all_succeed(self, executor, tmp_path):
        dest1 = tmp_path / "d1.txt"
        dest1.write_text("a")
        dest2 = tmp_path / "d2.txt"
        dest2.write_text("b")
        ops = [
            _make_op(OperationType.MOVE, tmp_path / "s1", dest1, op_id=1),
            _make_op(OperationType.MOVE, tmp_path / "s2", dest2, op_id=2),
        ]
        result = executor.rollback_transaction("txn-1", ops)
        assert result.success is True
        assert result.operations_rolled_back == 2

    def test_partial_failure(self, executor, tmp_path):
        dest1 = tmp_path / "d1.txt"
        dest1.write_text("a")
        ops = [
            _make_op(OperationType.MOVE, tmp_path / "s1", dest1, op_id=1),
            _make_op(
                OperationType.MOVE,
                tmp_path / "missing_src",
                tmp_path / "missing_dest",
                op_id=2,
            ),
        ]
        # Operations are reversed, so missing one processes first
        result = executor.rollback_transaction("txn-2", ops)
        assert result.operations_failed >= 1


# ---------------------------------------------------------------------------
# _move_to_trash
# ---------------------------------------------------------------------------


class TestMoveToTrash:
    def test_with_operation_id(self, executor, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text("data")
        trash_path = executor._move_to_trash(f, operation_id=42)
        assert trash_path.exists()
        assert "42" in str(trash_path)

    def test_without_operation_id(self, executor, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text("data")
        trash_path = executor._move_to_trash(f)
        assert trash_path.exists()
