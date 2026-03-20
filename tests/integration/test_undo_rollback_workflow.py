"""Integration tests for undo/redo rollback execution and validation.

Covers:
  - undo/rollback.py  (RollbackExecutor)
  - undo/validator.py (OperationValidator)
  - undo/undo_manager.py (UndoManager)

Tests operate on real files in tmp_path and use a per-test trash dir so no
interaction with user home occurs.  The autouse _isolate_user_env fixture in
conftest.py already redirects HOME/XDG vars.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from file_organizer.history.models import Operation, OperationStatus, OperationType
from file_organizer.history.tracker import OperationHistory
from file_organizer.undo.models import ConflictType
from file_organizer.undo.rollback import RollbackExecutor
from file_organizer.undo.undo_manager import UndoManager
from file_organizer.undo.validator import OperationValidator

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_operation(
    op_type: OperationType,
    src: Path,
    dst: Path | None = None,
    *,
    op_id: int = 1,
    status: OperationStatus = OperationStatus.COMPLETED,
    metadata: dict | None = None,
    file_hash: str | None = None,
    error_message: str | None = None,
) -> Operation:
    from datetime import UTC, datetime

    return Operation(
        id=op_id,
        operation_type=op_type,
        timestamp=datetime.now(UTC),
        source_path=src,
        destination_path=dst,
        file_hash=file_hash,
        metadata=metadata or {},
        transaction_id=None,
        status=status,
        error_message=error_message,
    )


# ---------------------------------------------------------------------------
# OperationValidator
# ---------------------------------------------------------------------------


class TestOperationValidator:
    """Integration tests for OperationValidator."""

    @pytest.fixture()
    def validator(self, tmp_path: Path) -> OperationValidator:
        return OperationValidator(trash_dir=tmp_path / "trash")

    def test_validate_undo_move_can_proceed(
        self, validator: OperationValidator, tmp_path: Path
    ) -> None:
        src_dir = tmp_path / "src"
        src_dir.mkdir(parents=True)  # parent must exist for undo to restore
        src = src_dir / "a.txt"
        dst = tmp_path / "dst" / "a.txt"
        dst.parent.mkdir(parents=True)
        dst.write_text("hello")

        op = _make_operation(OperationType.MOVE, src, dst)
        result = validator.validate_undo(op)
        assert result.can_proceed
        assert len(result.conflicts) == 0

    def test_validate_undo_move_missing_destination(
        self, validator: OperationValidator, tmp_path: Path
    ) -> None:
        src = tmp_path / "src" / "a.txt"
        dst = tmp_path / "dst" / "a.txt"  # doesn't exist

        op = _make_operation(OperationType.MOVE, src, dst)
        result = validator.validate_undo(op)
        assert not result.can_proceed
        conflict_types = {c.conflict_type for c in result.conflicts}
        assert ConflictType.FILE_MISSING in conflict_types

    def test_validate_undo_move_source_occupied(
        self, validator: OperationValidator, tmp_path: Path
    ) -> None:
        src = tmp_path / "a.txt"
        src.write_text("existing")  # src already exists → conflict
        dst = tmp_path / "dst" / "a.txt"
        dst.parent.mkdir()
        dst.write_text("moved")

        op = _make_operation(OperationType.MOVE, src, dst)
        result = validator.validate_undo(op)
        assert not result.can_proceed
        conflict_types = {c.conflict_type for c in result.conflicts}
        assert ConflictType.PATH_OCCUPIED in conflict_types

    def test_validate_undo_rolled_back_operation(
        self, validator: OperationValidator, tmp_path: Path
    ) -> None:
        op = _make_operation(
            OperationType.MOVE,
            tmp_path / "src.txt",
            tmp_path / "dst.txt",
            status=OperationStatus.ROLLED_BACK,
        )
        result = validator.validate_undo(op)
        assert not result.can_proceed
        assert "already been rolled back" in (result.error_message or "")

    def test_validate_undo_failed_operation_warns(
        self, validator: OperationValidator, tmp_path: Path
    ) -> None:
        dst = tmp_path / "dst.txt"
        dst.write_text("data")
        op = _make_operation(
            OperationType.MOVE,
            tmp_path / "src.txt",
            dst,
            status=OperationStatus.FAILED,
        )
        result = validator.validate_undo(op)
        # Failed ops can still be attempted but generate warnings
        assert len(result.warnings) > 0

    def test_validate_undo_copy_can_proceed(
        self, validator: OperationValidator, tmp_path: Path
    ) -> None:
        copy = tmp_path / "copy.txt"
        copy.write_text("copy content")

        op = _make_operation(OperationType.COPY, tmp_path / "orig.txt", copy)
        result = validator.validate_undo(op)
        assert result.can_proceed

    def test_validate_undo_rename_can_proceed(
        self, validator: OperationValidator, tmp_path: Path
    ) -> None:
        new_name = tmp_path / "new.txt"
        new_name.write_text("renamed")

        op = _make_operation(OperationType.RENAME, tmp_path / "old.txt", new_name)
        result = validator.validate_undo(op)
        assert result.can_proceed

    def test_validate_undo_create_can_proceed(
        self, validator: OperationValidator, tmp_path: Path
    ) -> None:
        created = tmp_path / "new_file.txt"
        created.write_text("created")

        op = _make_operation(OperationType.CREATE, created)
        result = validator.validate_undo(op)
        assert result.can_proceed

    def test_validate_redo_move_can_proceed(
        self, validator: OperationValidator, tmp_path: Path
    ) -> None:
        src = tmp_path / "src.txt"
        src.write_text("data")
        dst = tmp_path / "dst" / "out.txt"

        # redo requires the op to be in ROLLED_BACK status
        op = _make_operation(OperationType.MOVE, src, dst, status=OperationStatus.ROLLED_BACK)
        result = validator.validate_redo(op)
        assert result.can_proceed

    def test_validate_redo_move_source_missing(
        self, validator: OperationValidator, tmp_path: Path
    ) -> None:
        src = tmp_path / "nonexistent.txt"
        dst = tmp_path / "dst.txt"

        op = _make_operation(OperationType.MOVE, src, dst, status=OperationStatus.ROLLED_BACK)
        result = validator.validate_redo(op)
        assert not result.can_proceed
        conflict_types = {c.conflict_type for c in result.conflicts}
        assert ConflictType.FILE_MISSING in conflict_types


# ---------------------------------------------------------------------------
# RollbackExecutor
# ---------------------------------------------------------------------------


class TestRollbackExecutor:
    """Integration tests for RollbackExecutor filesystem operations."""

    @pytest.fixture()
    def executor(self, tmp_path: Path) -> RollbackExecutor:
        validator = OperationValidator(trash_dir=tmp_path / "trash")
        return RollbackExecutor(validator)

    def test_rollback_move_restores_file(self, executor: RollbackExecutor, tmp_path: Path) -> None:
        src = tmp_path / "source" / "file.txt"
        dst = tmp_path / "dest" / "file.txt"
        dst.parent.mkdir(parents=True)
        dst.write_text("original content")

        op = _make_operation(OperationType.MOVE, src, dst)
        result = executor.rollback_move(op)

        assert result is True
        assert src.exists()
        assert src.read_text() == "original content"
        assert not dst.exists()

    def test_rollback_rename_restores_original_name(
        self, executor: RollbackExecutor, tmp_path: Path
    ) -> None:
        old_name = tmp_path / "original.txt"
        new_name = tmp_path / "renamed.txt"
        new_name.write_text("data")

        op = _make_operation(OperationType.RENAME, old_name, new_name)
        result = executor.rollback_rename(op)

        assert result is True
        assert old_name.exists()
        assert not new_name.exists()

    def test_rollback_copy_moves_to_trash(self, executor: RollbackExecutor, tmp_path: Path) -> None:
        copy = tmp_path / "copy.txt"
        copy.write_text("copied content")

        op = _make_operation(OperationType.COPY, tmp_path / "orig.txt", copy, op_id=42)
        result = executor.rollback_copy(op)

        assert result is True
        assert not copy.exists()
        # File should be in trash
        trash_file = executor.trash_dir / "42" / "copy.txt"
        assert trash_file.exists()

    def test_rollback_create_moves_to_trash(
        self, executor: RollbackExecutor, tmp_path: Path
    ) -> None:
        created = tmp_path / "created.txt"
        created.write_text("new content")

        op = _make_operation(OperationType.CREATE, created, op_id=99)
        result = executor.rollback_create(op)

        assert result is True
        assert not created.exists()
        trash_file = executor.trash_dir / "99" / "created.txt"
        assert trash_file.exists()

    def test_rollback_move_fails_gracefully_if_file_missing(
        self, executor: RollbackExecutor, tmp_path: Path
    ) -> None:
        src = tmp_path / "src" / "missing.txt"
        dst = tmp_path / "dst" / "missing.txt"  # doesn't exist

        op = _make_operation(OperationType.MOVE, src, dst)
        result = executor.rollback_move(op)
        assert result is False

    def test_rollback_rename_fails_gracefully_if_no_destination(
        self, executor: RollbackExecutor, tmp_path: Path
    ) -> None:
        op = _make_operation(OperationType.RENAME, tmp_path / "old.txt", dst=None)
        result = executor.rollback_rename(op)
        assert result is False

    def test_rollback_copy_fails_gracefully_if_no_destination(
        self, executor: RollbackExecutor, tmp_path: Path
    ) -> None:
        op = _make_operation(OperationType.COPY, tmp_path / "orig.txt", dst=None)
        result = executor.rollback_copy(op)
        assert result is False

    def test_redo_move(self, executor: RollbackExecutor, tmp_path: Path) -> None:
        src = tmp_path / "file.txt"
        src.write_text("to move")
        dst = tmp_path / "out" / "file.txt"

        op = _make_operation(OperationType.MOVE, src, dst)
        result = executor.redo_move(op)

        assert result is True
        assert dst.exists()
        assert not src.exists()

    def test_redo_rename(self, executor: RollbackExecutor, tmp_path: Path) -> None:
        old = tmp_path / "old.txt"
        old.write_text("content")
        new = tmp_path / "new.txt"

        op = _make_operation(OperationType.RENAME, old, new)
        result = executor.redo_rename(op)

        assert result is True
        assert new.exists()
        assert not old.exists()

    def test_redo_copy_file(self, executor: RollbackExecutor, tmp_path: Path) -> None:
        src = tmp_path / "src.txt"
        src.write_text("content to copy")
        dst = tmp_path / "copies" / "copy.txt"

        op = _make_operation(OperationType.COPY, src, dst)
        result = executor.redo_copy(op)

        assert result is True
        assert src.exists()
        assert dst.exists()
        assert dst.read_text() == "content to copy"

    def test_redo_create_file(self, executor: RollbackExecutor, tmp_path: Path) -> None:
        file_path = tmp_path / "sub" / "new.txt"

        op = _make_operation(OperationType.CREATE, file_path, metadata={"is_dir": False})
        result = executor.redo_create(op)

        assert result is True
        assert file_path.exists()
        assert file_path.is_file()

    def test_redo_create_directory(self, executor: RollbackExecutor, tmp_path: Path) -> None:
        dir_path = tmp_path / "newdir"

        op = _make_operation(OperationType.CREATE, dir_path, metadata={"is_dir": True})
        result = executor.redo_create(op)

        assert result is True
        assert dir_path.exists()
        assert dir_path.is_dir()

    def test_rollback_transaction_all_succeed(
        self, executor: RollbackExecutor, tmp_path: Path
    ) -> None:
        # Create two files at their "destination" positions
        dst1 = tmp_path / "dst1.txt"
        dst2 = tmp_path / "dst2.txt"
        dst1.write_text("file1")
        dst2.write_text("file2")

        src1 = tmp_path / "sub1" / "src1.txt"
        src2 = tmp_path / "sub2" / "src2.txt"

        ops = [
            _make_operation(OperationType.MOVE, src1, dst1, op_id=1),
            _make_operation(OperationType.MOVE, src2, dst2, op_id=2),
        ]
        result = executor.rollback_transaction("txn-abc", ops)

        assert result.success is True
        assert result.operations_rolled_back == 2
        assert result.operations_failed == 0
        assert src1.exists()
        assert src2.exists()

    def test_rollback_transaction_stops_on_failure(
        self, executor: RollbackExecutor, tmp_path: Path
    ) -> None:
        # First op will succeed (dst exists)
        dst1 = tmp_path / "dst1.txt"
        dst1.write_text("data")
        src1 = tmp_path / "sub" / "src1.txt"

        # Second op will fail (dst doesn't exist)
        src2 = tmp_path / "sub" / "src2.txt"
        dst2 = tmp_path / "dst2.txt"  # missing

        ops = [
            _make_operation(OperationType.MOVE, src1, dst1, op_id=1),
            _make_operation(OperationType.MOVE, src2, dst2, op_id=2),
        ]
        # rollback_transaction reverses order: op2 first (fails), stops
        result = executor.rollback_transaction("txn-xyz", ops)

        # At least one failure
        assert result.success is False
        assert result.operations_failed > 0

    def test_rollback_operation_dispatches_all_types(
        self, executor: RollbackExecutor, tmp_path: Path
    ) -> None:
        """rollback_operation() dispatches correctly for each OperationType."""
        # MOVE: create dst, expect src restored
        dst = tmp_path / "moved.txt"
        dst.write_text("data")
        src = tmp_path / "src" / "moved.txt"
        assert executor.rollback_operation(_make_operation(OperationType.MOVE, src, dst)) is True

        # RENAME: create new_name, expect old_name restored
        old = tmp_path / "old.txt"
        new = tmp_path / "new.txt"
        new.write_text("renamed")
        assert executor.rollback_operation(_make_operation(OperationType.RENAME, old, new)) is True

        # COPY: create copy, expect it moved to trash
        copy = tmp_path / "copy.txt"
        copy.write_text("copy")
        assert (
            executor.rollback_operation(
                _make_operation(OperationType.COPY, tmp_path / "o.txt", copy, op_id=10)
            )
            is True
        )

        # CREATE: create file, expect it moved to trash
        created = tmp_path / "created.txt"
        created.write_text("new")
        assert (
            executor.rollback_operation(_make_operation(OperationType.CREATE, created, op_id=11))
            is True
        )


# ---------------------------------------------------------------------------
# UndoManager
# ---------------------------------------------------------------------------


class TestUndoManager:
    """Integration tests for UndoManager coordinating history + rollback."""

    @pytest.fixture()
    def undo_mgr(self, tmp_path: Path) -> UndoManager:
        history = OperationHistory(tmp_path / "history.db")
        validator = OperationValidator(trash_dir=tmp_path / "trash")
        executor = RollbackExecutor(validator)
        return UndoManager(history=history, validator=validator, executor=executor)

    def test_undo_last_operation_no_operations(self, undo_mgr: UndoManager) -> None:
        result = undo_mgr.undo_last_operation()
        assert result is False

    def test_undo_last_move_restores_file(self, undo_mgr: UndoManager, tmp_path: Path) -> None:
        src_dir = tmp_path / "src"
        src_dir.mkdir(parents=True)  # src parent must exist for validator
        src = src_dir / "file.txt"
        dst = tmp_path / "dst" / "file.txt"
        dst.parent.mkdir(parents=True)
        dst.write_text("hello world")

        # Log the move
        op_id = undo_mgr.history.log_operation(OperationType.MOVE, src, dst)

        result = undo_mgr.undo_last_operation()
        assert result is True
        assert src.exists()
        assert src.read_text() == "hello world"

        # Operation should now be marked rolled_back
        ops = undo_mgr.history.get_operations(status=OperationStatus.ROLLED_BACK)
        assert any(op.id == op_id for op in ops)

    def test_undo_specific_operation_id(self, undo_mgr: UndoManager, tmp_path: Path) -> None:
        src = tmp_path / "src.txt"
        dst = tmp_path / "dst.txt"
        dst.write_text("content")

        op_id = undo_mgr.history.log_operation(OperationType.MOVE, src, dst)
        result = undo_mgr.undo_operation(op_id)
        assert result is True
        assert src.exists()

    def test_undo_nonexistent_operation_id(self, undo_mgr: UndoManager) -> None:
        result = undo_mgr.undo_operation(99999)
        assert result is False

    def test_undo_already_rolled_back_is_rejected(
        self, undo_mgr: UndoManager, tmp_path: Path
    ) -> None:
        src = tmp_path / "src.txt"
        dst = tmp_path / "dst.txt"
        dst.write_text("x")

        op_id = undo_mgr.history.log_operation(
            OperationType.MOVE,
            src,
            dst,
            status=OperationStatus.ROLLED_BACK,
        )
        result = undo_mgr.undo_operation(op_id)
        assert result is False

    def test_redo_last_operation(self, undo_mgr: UndoManager, tmp_path: Path) -> None:
        src = tmp_path / "redo_src.txt"
        src.write_text("redo me")
        dst = tmp_path / "redo_dst" / "out.txt"

        undo_mgr.history.log_operation(
            OperationType.MOVE,
            src,
            dst,
            status=OperationStatus.ROLLED_BACK,
        )
        result = undo_mgr.redo_last_operation()
        assert result is True
        assert dst.exists()

    def test_redo_last_operation_no_operations(self, undo_mgr: UndoManager) -> None:
        result = undo_mgr.redo_last_operation()
        assert result is False

    def test_undo_transaction(self, undo_mgr: UndoManager, tmp_path: Path) -> None:
        # Set up two files in their destination positions
        dst1 = tmp_path / "dst1.txt"
        dst2 = tmp_path / "dst2.txt"
        dst1.write_text("file1")
        dst2.write_text("file2")

        # Source parent dirs must exist for the validator to allow undo
        (tmp_path / "src1").mkdir()
        (tmp_path / "src2").mkdir()
        src1 = tmp_path / "src1" / "dst1.txt"
        src2 = tmp_path / "src2" / "dst2.txt"

        # Start transaction, log two moves
        txn_id = undo_mgr.history.start_transaction({"batch": "test"})
        undo_mgr.history.log_operation(OperationType.MOVE, src1, dst1, transaction_id=txn_id)
        undo_mgr.history.log_operation(OperationType.MOVE, src2, dst2, transaction_id=txn_id)
        undo_mgr.history.commit_transaction(txn_id)

        result = undo_mgr.undo_transaction(txn_id)
        assert result is True
        assert src1.exists()
        assert src2.exists()
