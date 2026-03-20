"""Integration tests for undo/rollback.py — RollbackExecutor branch coverage.

Covers uncovered branches in:
  - rollback_operation: all OperationType dispatches + unknown type + exception
  - redo_operation: all OperationType dispatches + unknown type + exception
  - rollback_rename: None destination branch
  - rollback_delete: file not in trash branch
  - rollback_copy: None destination + exception
  - rollback_create: filesystem operations
  - redo_move: None destination branch
  - redo_rename: None destination branch
  - redo_delete: success path
  - redo_copy: None destination + directory source + missing source branch
  - redo_create: directory + file creation
  - rollback_transaction: failure/exception path
  - _move_to_trash: None operation_id branch
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from file_organizer.history.models import Operation, OperationStatus, OperationType
from file_organizer.undo.rollback import RollbackExecutor

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _op(
    op_type: OperationType,
    src: Path,
    dest: Path | None = None,
    op_id: int = 1,
    metadata: dict | None = None,
) -> Operation:
    return Operation(
        id=op_id,
        operation_type=op_type,
        timestamp=datetime.now(UTC),
        source_path=src,
        destination_path=dest,
        status=OperationStatus.COMPLETED,
        metadata=metadata or {},
    )


# ---------------------------------------------------------------------------
# rollback_operation — dispatch branches
# ---------------------------------------------------------------------------


class TestRollbackOperationDispatch:
    def test_unknown_type_returns_false(self, tmp_path: Path) -> None:
        executor = RollbackExecutor(validator=None)
        op = _op(OperationType.MOVE, tmp_path / "src.txt")
        op.operation_type = "unknown_type"  # type: ignore[assignment]
        assert executor.rollback_operation(op) is False

    def test_move_dispatch(self, tmp_path: Path) -> None:
        executor = RollbackExecutor(validator=None)
        dest = tmp_path / "dest.txt"
        dest.write_text("hello")
        src = tmp_path / "src_dir" / "src.txt"
        src.parent.mkdir()
        op = _op(OperationType.MOVE, src, dest)
        result = executor.rollback_operation(op)
        assert result is True
        assert src.exists()
        assert not dest.exists()

    def test_rename_dispatch_success(self, tmp_path: Path) -> None:
        executor = RollbackExecutor(validator=None)
        new_name = tmp_path / "new.txt"
        new_name.write_text("content")
        old_name = tmp_path / "old.txt"
        op = _op(OperationType.RENAME, old_name, new_name)
        result = executor.rollback_operation(op)
        assert result is True
        assert old_name.exists()
        assert not new_name.exists()

    def test_copy_dispatch_none_dest_returns_false(self, tmp_path: Path) -> None:
        executor = RollbackExecutor(validator=None)
        op = _op(OperationType.COPY, tmp_path / "src.txt", None)
        assert executor.rollback_operation(op) is False

    def test_create_dispatch(self, tmp_path: Path) -> None:
        executor = RollbackExecutor(validator=None)
        f = tmp_path / "created.txt"
        f.write_text("exists")
        op = _op(OperationType.CREATE, f)
        result = executor.rollback_operation(op)
        assert result is True
        # file moved to trash, no longer at original path
        assert not f.exists()

    def test_exception_in_dispatch_returns_false(self, tmp_path: Path) -> None:
        executor = RollbackExecutor(validator=None)
        op = _op(OperationType.MOVE, tmp_path / "src.txt", None)
        # destination is None → shutil.move will fail
        result = executor.rollback_operation(op)
        assert result is False


# ---------------------------------------------------------------------------
# redo_operation — dispatch branches
# ---------------------------------------------------------------------------


class TestRedoOperationDispatch:
    def test_unknown_type_returns_false(self, tmp_path: Path) -> None:
        executor = RollbackExecutor(validator=None)
        op = _op(OperationType.MOVE, tmp_path / "src.txt")
        op.operation_type = "unknown_type"  # type: ignore[assignment]
        assert executor.redo_operation(op) is False

    def test_rename_dispatch(self, tmp_path: Path) -> None:
        executor = RollbackExecutor(validator=None)
        old_name = tmp_path / "old.txt"
        old_name.write_text("content")
        new_name = tmp_path / "new.txt"
        op = _op(OperationType.RENAME, old_name, new_name)
        result = executor.redo_operation(op)
        assert result is True
        assert new_name.exists()

    def test_delete_dispatch(self, tmp_path: Path) -> None:
        executor = RollbackExecutor(validator=None)
        f = tmp_path / "to_delete.txt"
        f.write_text("data")
        op = _op(OperationType.DELETE, f)
        result = executor.redo_operation(op)
        assert result is True
        assert not f.exists()

    def test_copy_dispatch_none_dest_returns_false(self, tmp_path: Path) -> None:
        executor = RollbackExecutor(validator=None)
        op = _op(OperationType.COPY, tmp_path / "src.txt", None)
        assert executor.redo_operation(op) is False

    def test_create_dispatch(self, tmp_path: Path) -> None:
        executor = RollbackExecutor(validator=None)
        f = tmp_path / "new_file.txt"
        op = _op(OperationType.CREATE, f)
        result = executor.redo_operation(op)
        assert result is True
        assert f.exists()

    def test_exception_returns_false(self, tmp_path: Path) -> None:
        executor = RollbackExecutor(validator=None)
        op = _op(OperationType.MOVE, tmp_path / "missing.txt", None)
        assert executor.redo_operation(op) is False


# ---------------------------------------------------------------------------
# rollback_rename
# ---------------------------------------------------------------------------


class TestRollbackRename:
    def test_none_destination_returns_false(self, tmp_path: Path) -> None:
        executor = RollbackExecutor(validator=None)
        op = _op(OperationType.RENAME, tmp_path / "old.txt", None)
        assert executor.rollback_rename(op) is False

    def test_successful_rename(self, tmp_path: Path) -> None:
        executor = RollbackExecutor(validator=None)
        new_name = tmp_path / "new.txt"
        new_name.write_text("data")
        old_name = tmp_path / "old.txt"
        op = _op(OperationType.RENAME, old_name, new_name)
        assert executor.rollback_rename(op) is True
        assert old_name.exists()

    def test_failure_returns_false(self, tmp_path: Path) -> None:
        executor = RollbackExecutor(validator=None)
        # new_name doesn't exist → rename fails
        op = _op(OperationType.RENAME, tmp_path / "old.txt", tmp_path / "ghost.txt")
        assert executor.rollback_rename(op) is False


# ---------------------------------------------------------------------------
# rollback_delete
# ---------------------------------------------------------------------------


class TestRollbackDelete:
    def test_file_not_in_trash_returns_false(self, tmp_path: Path) -> None:
        trash = tmp_path / "trash"
        trash.mkdir()
        from file_organizer.undo.validator import OperationValidator

        v = OperationValidator(trash_dir=trash)
        executor = RollbackExecutor(validator=v)
        op = _op(OperationType.DELETE, tmp_path / "src" / "deleted.txt", op_id=99)
        assert executor.rollback_delete(op) is False

    def test_successful_restore_from_trash(self, tmp_path: Path) -> None:
        trash = tmp_path / "trash"
        trash.mkdir()
        from file_organizer.undo.validator import OperationValidator

        v = OperationValidator(trash_dir=trash)
        executor = RollbackExecutor(validator=v)

        # Pre-populate trash at the expected path
        trash_subdir = trash / "5"
        trash_subdir.mkdir()
        (trash_subdir / "deleted.txt").write_text("content")

        src = tmp_path / "src_dir"
        src.mkdir()
        src_file = src / "deleted.txt"
        op = _op(OperationType.DELETE, src_file, op_id=5)
        result = executor.rollback_delete(op)
        assert result is True
        assert src_file.exists()


# ---------------------------------------------------------------------------
# rollback_copy
# ---------------------------------------------------------------------------


class TestRollbackCopy:
    def test_none_destination_returns_false(self, tmp_path: Path) -> None:
        executor = RollbackExecutor(validator=None)
        op = _op(OperationType.COPY, tmp_path / "orig.txt", None)
        assert executor.rollback_copy(op) is False

    def test_copy_does_not_exist_returns_false(self, tmp_path: Path) -> None:
        executor = RollbackExecutor(validator=None)
        op = _op(OperationType.COPY, tmp_path / "orig.txt", tmp_path / "missing_copy.txt")
        # copy doesn't exist → shutil.move fails
        assert executor.rollback_copy(op) is False

    def test_successful_copy_rollback(self, tmp_path: Path) -> None:
        executor = RollbackExecutor(validator=None)
        copy_path = tmp_path / "copy.txt"
        copy_path.write_text("copy content")
        op = _op(OperationType.COPY, tmp_path / "orig.txt", copy_path)
        result = executor.rollback_copy(op)
        assert result is True
        assert not copy_path.exists()


# ---------------------------------------------------------------------------
# rollback_create
# ---------------------------------------------------------------------------


class TestRollbackCreate:
    def test_file_not_exists_returns_false(self, tmp_path: Path) -> None:
        executor = RollbackExecutor(validator=None)
        op = _op(OperationType.CREATE, tmp_path / "ghost.txt")
        assert executor.rollback_create(op) is False

    def test_successful_create_rollback(self, tmp_path: Path) -> None:
        executor = RollbackExecutor(validator=None)
        f = tmp_path / "created.txt"
        f.write_text("exists")
        op = _op(OperationType.CREATE, f)
        result = executor.rollback_create(op)
        assert result is True
        assert not f.exists()


# ---------------------------------------------------------------------------
# redo_move
# ---------------------------------------------------------------------------


class TestRedoMove:
    def test_none_destination_returns_false(self, tmp_path: Path) -> None:
        executor = RollbackExecutor(validator=None)
        op = _op(OperationType.MOVE, tmp_path / "src.txt", None)
        assert executor.redo_move(op) is False

    def test_successful_redo_move(self, tmp_path: Path) -> None:
        executor = RollbackExecutor(validator=None)
        src = tmp_path / "src.txt"
        src.write_text("content")
        dest = tmp_path / "subdir" / "dest.txt"
        op = _op(OperationType.MOVE, src, dest)
        assert executor.redo_move(op) is True
        assert dest.exists()
        assert not src.exists()

    def test_failure_returns_false(self, tmp_path: Path) -> None:
        executor = RollbackExecutor(validator=None)
        # src doesn't exist
        op = _op(OperationType.MOVE, tmp_path / "ghost.txt", tmp_path / "out.txt")
        assert executor.redo_move(op) is False


# ---------------------------------------------------------------------------
# redo_rename
# ---------------------------------------------------------------------------


class TestRedoRename:
    def test_none_destination_returns_false(self, tmp_path: Path) -> None:
        executor = RollbackExecutor(validator=None)
        op = _op(OperationType.RENAME, tmp_path / "old.txt", None)
        assert executor.redo_rename(op) is False

    def test_successful_redo_rename(self, tmp_path: Path) -> None:
        executor = RollbackExecutor(validator=None)
        old = tmp_path / "old.txt"
        old.write_text("data")
        new = tmp_path / "new.txt"
        op = _op(OperationType.RENAME, old, new)
        assert executor.redo_rename(op) is True
        assert new.exists()

    def test_failure_returns_false(self, tmp_path: Path) -> None:
        executor = RollbackExecutor(validator=None)
        # source doesn't exist
        op = _op(OperationType.RENAME, tmp_path / "ghost.txt", tmp_path / "new.txt")
        assert executor.redo_rename(op) is False


# ---------------------------------------------------------------------------
# redo_delete
# ---------------------------------------------------------------------------


class TestRedoDelete:
    def test_successful_redo_delete(self, tmp_path: Path) -> None:
        executor = RollbackExecutor(validator=None)
        f = tmp_path / "to_delete.txt"
        f.write_text("data")
        op = _op(OperationType.DELETE, f)
        assert executor.redo_delete(op) is True
        assert not f.exists()

    def test_failure_returns_false(self, tmp_path: Path) -> None:
        executor = RollbackExecutor(validator=None)
        # file doesn't exist → shutil.move fails
        op = _op(OperationType.DELETE, tmp_path / "ghost.txt")
        assert executor.redo_delete(op) is False


# ---------------------------------------------------------------------------
# redo_copy
# ---------------------------------------------------------------------------


class TestRedoCopy:
    def test_none_destination_returns_false(self, tmp_path: Path) -> None:
        executor = RollbackExecutor(validator=None)
        op = _op(OperationType.COPY, tmp_path / "src.txt", None)
        assert executor.redo_copy(op) is False

    def test_copy_file_success(self, tmp_path: Path) -> None:
        executor = RollbackExecutor(validator=None)
        src = tmp_path / "src.txt"
        src.write_text("content")
        dest = tmp_path / "subdir" / "dest.txt"
        op = _op(OperationType.COPY, src, dest)
        assert executor.redo_copy(op) is True
        assert dest.exists()
        assert src.exists()  # source preserved

    def test_copy_directory_success(self, tmp_path: Path) -> None:
        executor = RollbackExecutor(validator=None)
        src = tmp_path / "srcdir"
        src.mkdir()
        (src / "file.txt").write_text("hello")
        dest = tmp_path / "destdir"
        op = _op(OperationType.COPY, src, dest)
        assert executor.redo_copy(op) is True
        assert dest.exists()
        assert (dest / "file.txt").exists()

    def test_copy_neither_file_nor_dir_returns_false(self, tmp_path: Path) -> None:
        executor = RollbackExecutor(validator=None)
        # source doesn't exist at all → neither file nor dir
        op = _op(OperationType.COPY, tmp_path / "ghost.txt", tmp_path / "dest.txt")
        assert executor.redo_copy(op) is False

    def test_failure_returns_false(self, tmp_path: Path) -> None:
        executor = RollbackExecutor(validator=None)
        src = tmp_path / "src.txt"
        src.write_text("data")
        # dest is a read-only directory location that can't be written
        dest = tmp_path / "src.txt" / "impossible.txt"
        op = _op(OperationType.COPY, src, dest)
        assert executor.redo_copy(op) is False


# ---------------------------------------------------------------------------
# redo_create
# ---------------------------------------------------------------------------


class TestRedoCreate:
    def test_create_file(self, tmp_path: Path) -> None:
        executor = RollbackExecutor(validator=None)
        f = tmp_path / "new_file.txt"
        op = _op(OperationType.CREATE, f)
        assert executor.redo_create(op) is True
        assert f.exists()

    def test_create_directory(self, tmp_path: Path) -> None:
        executor = RollbackExecutor(validator=None)
        d = tmp_path / "new_dir"
        op = _op(OperationType.CREATE, d, metadata={"is_dir": True})
        assert executor.redo_create(op) is True
        assert d.is_dir()

    def test_failure_returns_false(self, tmp_path: Path) -> None:
        executor = RollbackExecutor(validator=None)
        # Path inside a non-directory → mkdir fails
        existing_file = tmp_path / "file.txt"
        existing_file.write_text("data")
        impossible = existing_file / "child.txt"
        op = _op(OperationType.CREATE, impossible)
        assert executor.redo_create(op) is False


# ---------------------------------------------------------------------------
# rollback_transaction
# ---------------------------------------------------------------------------


class TestRollbackTransaction:
    def test_all_succeed(self, tmp_path: Path) -> None:
        executor = RollbackExecutor(validator=None)
        dest1 = tmp_path / "d1.txt"
        dest1.write_text("one")
        src1 = tmp_path / "subdir1" / "s1.txt"
        src1.parent.mkdir()

        dest2 = tmp_path / "d2.txt"
        dest2.write_text("two")
        src2 = tmp_path / "subdir2" / "s2.txt"
        src2.parent.mkdir()

        ops = [
            _op(OperationType.MOVE, src1, dest1, op_id=1),
            _op(OperationType.MOVE, src2, dest2, op_id=2),
        ]
        result = executor.rollback_transaction("txn1", ops)
        assert result.success is True
        assert result.operations_rolled_back == 2

    def test_one_failure_stops_transaction(self, tmp_path: Path) -> None:
        executor = RollbackExecutor(validator=None)
        dest1 = tmp_path / "d1.txt"
        dest1.write_text("one")
        src1 = tmp_path / "subdir1" / "s1.txt"
        src1.parent.mkdir()

        # Second op will fail (destination doesn't exist)
        ops = [
            _op(OperationType.MOVE, src1, dest1, op_id=1),
            _op(OperationType.MOVE, tmp_path / "ghost.txt", None, op_id=2),
        ]
        result = executor.rollback_transaction("txn2", ops)
        assert result.success is False

    def test_empty_operations_succeeds(self, tmp_path: Path) -> None:
        executor = RollbackExecutor(validator=None)
        result = executor.rollback_transaction("txn_empty", [])
        assert result.success is True
        assert result.operations_rolled_back == 0


# ---------------------------------------------------------------------------
# _move_to_trash
# ---------------------------------------------------------------------------


class TestMoveToTrash:
    def test_with_operation_id(self, tmp_path: Path) -> None:
        executor = RollbackExecutor(validator=None)
        f = tmp_path / "file.txt"
        f.write_text("data")
        trash_path = executor._move_to_trash(f, operation_id=42)
        assert trash_path.exists()
        assert not f.exists()
        assert "42" in str(trash_path)

    def test_without_operation_id_uses_uuid(self, tmp_path: Path) -> None:
        executor = RollbackExecutor(validator=None)
        f = tmp_path / "file2.txt"
        f.write_text("data")
        trash_path = executor._move_to_trash(f, operation_id=None)
        assert trash_path.exists()
        assert not f.exists()
