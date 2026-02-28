"""Extended unit tests for RollbackExecutor.

Covers rollback_operation/redo_operation dispatch, redo_create,
_move_to_trash, and exception paths not covered by the existing
test_rollback.py.
"""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.history.models import Operation, OperationStatus, OperationType
from file_organizer.undo.rollback import RollbackExecutor
from file_organizer.undo.validator import OperationValidator

pytestmark = [pytest.mark.unit]


@pytest.fixture()
def env(tmp_path):
    """Provide a clean test environment with executor."""
    trash_dir = tmp_path / "trash"
    validator = OperationValidator(trash_dir=trash_dir)
    executor = RollbackExecutor(validator=validator)
    return tmp_path, trash_dir, executor


def _op(
    op_type: OperationType,
    source: Path,
    destination: Path | None = None,
    *,
    op_id: int = 1,
    status: OperationStatus = OperationStatus.COMPLETED,
    metadata: dict | None = None,
    txn_id: str | None = None,
) -> Operation:
    return Operation(
        id=op_id,
        operation_type=op_type,
        timestamp=datetime.now(tz=UTC),
        source_path=source,
        destination_path=destination,
        status=status,
        metadata=metadata or {},
        transaction_id=txn_id,
    )


# ---------------------------------------------------------------------------
# rollback_operation dispatch
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRollbackOperationDispatch:
    """Test rollback_operation routes to correct handler."""

    def test_dispatch_move(self, env):
        tmp_path, _, executor = env
        src = tmp_path / "a.txt"
        dst = tmp_path / "b.txt"
        src.write_text("x")
        shutil.move(str(src), str(dst))
        op = _op(OperationType.MOVE, src, dst)
        assert executor.rollback_operation(op) is True
        assert src.exists()

    def test_dispatch_unknown_type(self, env):
        _, _, executor = env
        op = MagicMock()
        op.operation_type = "UNKNOWN_TYPE"
        op.id = 99
        result = executor.rollback_operation(op)
        assert result is False

    def test_dispatch_exception_caught(self, env):
        _, _, executor = env
        op = _op(OperationType.MOVE, Path("/nope"), Path("/nope2"))
        # rollback_move will fail because file doesn't exist → returns False
        result = executor.rollback_operation(op)
        assert result is False


# ---------------------------------------------------------------------------
# redo_operation dispatch
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRedoOperationDispatch:
    """Test redo_operation routes to correct handler."""

    def test_dispatch_move(self, env):
        tmp_path, _, executor = env
        src = tmp_path / "a.txt"
        dst = tmp_path / "b.txt"
        src.write_text("x")
        op = _op(OperationType.MOVE, src, dst, status=OperationStatus.ROLLED_BACK)
        assert executor.redo_operation(op) is True
        assert dst.exists()

    def test_dispatch_unknown_type(self, env):
        _, _, executor = env
        op = MagicMock()
        op.operation_type = "BAD"
        op.id = 99
        result = executor.redo_operation(op)
        assert result is False

    def test_dispatch_exception_caught(self, env):
        _, _, executor = env
        op = _op(OperationType.RENAME, Path("/nope"), Path("/nope2"), status=OperationStatus.ROLLED_BACK)
        result = executor.redo_operation(op)
        assert result is False


# ---------------------------------------------------------------------------
# redo_create
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRedoCreate:
    """Test redo_create handler."""

    def test_redo_create_file(self, env):
        tmp_path, _, executor = env
        target = tmp_path / "new.txt"
        op = _op(OperationType.CREATE, target, status=OperationStatus.ROLLED_BACK)
        assert executor.redo_create(op) is True
        assert target.exists()

    def test_redo_create_directory(self, env):
        tmp_path, _, executor = env
        target = tmp_path / "new_dir"
        op = _op(
            OperationType.CREATE,
            target,
            status=OperationStatus.ROLLED_BACK,
            metadata={"is_dir": True},
        )
        assert executor.redo_create(op) is True
        assert target.is_dir()

    def test_redo_create_exception(self, env):
        _, _, executor = env
        # Provide a path whose parent can't be created
        target = Path("/dev/null/impossible/file.txt")
        op = _op(OperationType.CREATE, target, status=OperationStatus.ROLLED_BACK)
        result = executor.redo_create(op)
        assert result is False


# ---------------------------------------------------------------------------
# redo_copy
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRedoCopy:
    """Test redo_copy handler."""

    def test_redo_copy_file(self, env):
        tmp_path, _, executor = env
        src = tmp_path / "src.txt"
        dst = tmp_path / "dst.txt"
        src.write_text("data")
        op = _op(OperationType.COPY, src, dst, status=OperationStatus.ROLLED_BACK)
        assert executor.redo_copy(op) is True
        assert dst.exists()
        assert dst.read_text() == "data"

    def test_redo_copy_directory(self, env):
        tmp_path, _, executor = env
        src = tmp_path / "src_dir"
        src.mkdir()
        (src / "child.txt").write_text("hi")
        dst = tmp_path / "dst_dir"
        op = _op(OperationType.COPY, src, dst, status=OperationStatus.ROLLED_BACK)
        assert executor.redo_copy(op) is True
        assert dst.is_dir()
        assert (dst / "child.txt").exists()

    def test_redo_copy_source_missing(self, env):
        tmp_path, _, executor = env
        src = tmp_path / "gone"
        dst = tmp_path / "dst"
        op = _op(OperationType.COPY, src, dst, status=OperationStatus.ROLLED_BACK)
        result = executor.redo_copy(op)
        assert result is False


# ---------------------------------------------------------------------------
# redo_delete
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRedoDelete:
    """Test redo_delete handler."""

    def test_redo_delete_success(self, env):
        tmp_path, _, executor = env
        src = tmp_path / "del.txt"
        src.write_text("bye")
        op = _op(OperationType.DELETE, src, status=OperationStatus.ROLLED_BACK)
        assert executor.redo_delete(op) is True
        assert not src.exists()

    def test_redo_delete_file_missing(self, env):
        tmp_path, _, executor = env
        src = tmp_path / "gone.txt"
        op = _op(OperationType.DELETE, src, status=OperationStatus.ROLLED_BACK)
        result = executor.redo_delete(op)
        assert result is False


# ---------------------------------------------------------------------------
# _move_to_trash
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMoveToTrash:
    """Test the _move_to_trash helper."""

    def test_with_operation_id(self, env):
        tmp_path, trash_dir, executor = env
        f = tmp_path / "a.txt"
        f.write_text("data")
        trash_path = executor._move_to_trash(f, operation_id=42)
        assert not f.exists()
        assert trash_path.exists()
        assert "42" in str(trash_path.parent.name)

    def test_without_operation_id(self, env):
        tmp_path, trash_dir, executor = env
        f = tmp_path / "b.txt"
        f.write_text("data")
        trash_path = executor._move_to_trash(f, operation_id=None)
        assert not f.exists()
        assert trash_path.exists()
        # Should use a UUID-based directory
        assert trash_path.parent.parent == trash_dir


# ---------------------------------------------------------------------------
# rollback_delete edge cases
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRollbackDeleteEdgeCases:
    """Test rollback_delete with trash path issues."""

    def test_trash_path_missing(self, env):
        tmp_path, _, executor = env
        src = tmp_path / "lost.txt"
        op = _op(OperationType.DELETE, src)
        with patch.object(executor.validator, "_get_trash_path", return_value=None):
            result = executor.rollback_delete(op)
        assert result is False

    def test_trash_file_not_exists(self, env):
        tmp_path, trash_dir, executor = env
        src = tmp_path / "lost.txt"
        op = _op(OperationType.DELETE, src)
        fake_trash = trash_dir / "1" / "lost.txt"
        with patch.object(executor.validator, "_get_trash_path", return_value=fake_trash):
            result = executor.rollback_delete(op)
        assert result is False


# ---------------------------------------------------------------------------
# rollback_transaction edge cases
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRollbackTransactionEdges:
    """Test rollback_transaction with exception in operation."""

    def test_exception_during_rollback_stops(self, env):
        tmp_path, _, executor = env

        # Create two operations; second will raise
        file1 = tmp_path / "f1.txt"
        file1.write_text("x")
        dst1 = tmp_path / "d1.txt"
        shutil.move(str(file1), str(dst1))

        ops = [
            _op(OperationType.MOVE, file1, dst1, op_id=1, txn_id="txn"),
            _op(OperationType.MOVE, Path("/nonexistent"), Path("/also_nonexistent"), op_id=2, txn_id="txn"),
        ]

        # Reversed: op2 runs first (fails), then stops
        result = executor.rollback_transaction("txn", ops)
        assert not result.success
        assert result.operations_failed > 0


# ---------------------------------------------------------------------------
# Default validator
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDefaultValidator:
    """Test that executor creates a default validator when none given."""

    def test_default_validator(self):
        executor = RollbackExecutor()
        assert executor.validator is not None
        assert hasattr(executor, "trash_dir")


# ---------------------------------------------------------------------------
# rollback_move / rollback_rename exception paths
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRollbackExceptionPaths:
    """Test exception handling in rollback methods."""

    def test_rollback_move_exception(self, env):
        tmp_path, _, executor = env
        op = _op(OperationType.MOVE, tmp_path / "a", tmp_path / "b")
        # No files exist → shutil.move will raise
        result = executor.rollback_move(op)
        assert result is False

    def test_rollback_rename_exception(self, env):
        tmp_path, _, executor = env
        op = _op(OperationType.RENAME, tmp_path / "a", tmp_path / "b")
        result = executor.rollback_rename(op)
        assert result is False

    def test_rollback_copy_exception(self, env):
        tmp_path, _, executor = env
        op = _op(OperationType.COPY, tmp_path / "a", tmp_path / "nonexistent.txt")
        result = executor.rollback_copy(op)
        assert result is False

    def test_rollback_create_exception(self, env):
        _, _, executor = env
        op = _op(OperationType.CREATE, Path("/dev/null/impossible"))
        result = executor.rollback_create(op)
        assert result is False
