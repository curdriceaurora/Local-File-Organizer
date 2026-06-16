"""Integration tests for the undo subsystem.

Exercises real ``UndoManager`` / ``RollbackExecutor`` / ``OperationValidator`` /
``OperationHistory`` components wired together (mirroring
``tests/undo/test_undo_manager.py``) to cover failure, validation, and
concurrency-edge branches that the happy-path unit tests do not reach.

Targets:
  - undo/undo_manager.py: 122,127 (concurrent undo rowcount==0), 160-161
    (empty transaction), 168/172 (transaction validate_undo failure), 193
    (rollback_transaction returns failure), 227/231 (redo validate failure),
    245-249 (redo op returns False -> rollback), 250-253 (redo except path),
    312 (redo_operation warnings loop), 331/335 (concurrent redo rowcount==0).
  - undo/rollback.py: 71 (symlink refusal), 122 (rollback DELETE dispatch),
    130-132 (rollback_operation outer except), 157-159 (redo_operation outer
    except), 243-244 (rmdir OSError best-effort), 248-250 (rollback_delete
    outer except), 475-487 (rollback_transaction op raises -> break).
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest

from file_organizer.history.models import (
    Operation,
    OperationStatus,
    OperationType,
)
from file_organizer.history.tracker import OperationHistory
from file_organizer.undo.models import RollbackResult, ValidationResult
from file_organizer.undo.rollback import RollbackExecutor
from file_organizer.undo.undo_manager import UndoManager
from file_organizer.undo.validator import OperationValidator

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class _Components:
    """Bundle of real undo components plus their working directory."""

    def __init__(self, tmp_path: Path) -> None:
        self.dir = tmp_path
        self.history = OperationHistory(db_path=tmp_path / "h.db")
        self.validator = OperationValidator(trash_dir=tmp_path / "trash")
        self.executor = RollbackExecutor(validator=self.validator)
        self.manager = UndoManager(
            history=self.history,
            validator=self.validator,
            executor=self.executor,
        )

    def close(self) -> None:
        self.history.close()


@pytest.fixture()
def comps(tmp_path: Path) -> Iterator[_Components]:
    c = _Components(tmp_path)
    try:
        yield c
    finally:
        c.close()


def _log_move(comps: _Components, name: str) -> tuple[int, Path, Path]:
    """Create source, move it to dest, log a COMPLETED MOVE op. Returns id+paths."""
    src = comps.dir / f"{name}_src.txt"
    dst = comps.dir / f"{name}_dst.txt"
    src.write_text(f"content for {name}")
    shutil.move(str(src), str(dst))
    op_id = comps.history.log_operation(
        operation_type=OperationType.MOVE,
        source_path=src,
        destination_path=dst,
    )
    return op_id, src, dst


# ===========================================================================
# undo_manager.py
# ===========================================================================


class TestUndoTransaction:
    def test_undo_transaction_no_completed_ops_returns_false(self, comps: _Components) -> None:
        # 160-161: a transaction that exists but has no COMPLETED operations.
        txn_id = comps.history.start_transaction()
        comps.history.commit_transaction(txn_id)

        assert comps.manager.undo_transaction(txn_id) is False

    def test_undo_transaction_validate_failure_returns_false(self, comps: _Components) -> None:
        # 168/172: one op fails validate_undo (its moved file is gone), so the
        # whole transaction undo aborts before executing any rollback.
        txn_id = comps.history.start_transaction()
        src = comps.dir / "vt_src.txt"
        dst = comps.dir / "vt_dst.txt"
        src.write_text("data")
        shutil.move(str(src), str(dst))
        comps.history.log_operation(
            operation_type=OperationType.MOVE,
            source_path=src,
            destination_path=dst,
            transaction_id=txn_id,
        )
        comps.history.commit_transaction(txn_id)

        # Destination vanishes -> validate_undo_move reports FILE_MISSING.
        dst.unlink()

        assert comps.manager.undo_transaction(txn_id) is False
        # Op was NOT flipped to ROLLED_BACK (aborted at validation).
        ops = comps.history.get_operations(transaction_id=txn_id)
        assert ops[0].status == OperationStatus.COMPLETED

    def test_undo_transaction_rollback_failure_returns_false(
        self, comps: _Components, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 193: validation passes but rollback_transaction reports failure.
        txn_id = comps.history.start_transaction()
        src = comps.dir / "rf_src.txt"
        dst = comps.dir / "rf_dst.txt"
        src.write_text("data")
        shutil.move(str(src), str(dst))
        comps.history.log_operation(
            operation_type=OperationType.MOVE,
            source_path=src,
            destination_path=dst,
            transaction_id=txn_id,
        )
        comps.history.commit_transaction(txn_id)

        monkeypatch.setattr(
            comps.executor,
            "rollback_transaction",
            lambda _tid, _ops: RollbackResult(
                success=False, operations_rolled_back=0, operations_failed=1
            ),
        )

        assert comps.manager.undo_transaction(txn_id) is False


class TestRedoTransaction:
    def _rolled_back_txn(self, comps: _Components) -> tuple[str, Path, Path]:
        """Build a committed+undone single-op MOVE transaction. Returns ids/paths."""
        txn_id = comps.history.start_transaction()
        src = comps.dir / "rt_src.txt"
        dst = comps.dir / "rt_dst.txt"
        src.write_text("redo data")
        shutil.move(str(src), str(dst))
        comps.history.log_operation(
            operation_type=OperationType.MOVE,
            source_path=src,
            destination_path=dst,
            transaction_id=txn_id,
        )
        comps.history.commit_transaction(txn_id)
        assert comps.manager.undo_transaction(txn_id) is True
        # After undo, src exists again and dst is gone.
        return txn_id, src, dst

    def test_redo_transaction_validate_failure_returns_false(self, comps: _Components) -> None:
        # 227/231: redo validation fails because the source file is missing.
        txn_id, src, dst = self._rolled_back_txn(comps)
        src.unlink()  # source gone -> validate_redo_move FILE_MISSING

        assert comps.manager.redo_transaction(txn_id) is False

    def test_redo_transaction_op_returns_false_rolls_back(
        self, comps: _Components, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 245-249: redo_operation returns False -> conn.rollback() + return False.
        txn_id, src, dst = self._rolled_back_txn(comps)
        monkeypatch.setattr(comps.executor, "redo_operation", lambda _op: False)

        assert comps.manager.redo_transaction(txn_id) is False
        # Status unchanged (still rolled back) because the DB txn was rolled back.
        ops = comps.history.get_operations(transaction_id=txn_id)
        assert ops[0].status == OperationStatus.ROLLED_BACK

    def test_redo_transaction_op_raises_returns_false(
        self, comps: _Components, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 250-253: redo_operation raises -> except -> conn.rollback() + False.
        txn_id, src, dst = self._rolled_back_txn(comps)

        def _boom(_op: Operation) -> bool:
            raise RuntimeError("redo blew up")

        monkeypatch.setattr(comps.executor, "redo_operation", _boom)

        assert comps.manager.redo_transaction(txn_id) is False
        ops = comps.history.get_operations(transaction_id=txn_id)
        assert ops[0].status == OperationStatus.ROLLED_BACK


class TestUndoRedoConcurrentEdges:
    def test_undo_operation_concurrent_flip_returns_false(
        self, comps: _Components, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 122/127: rollback succeeds on the filesystem, but a concurrent undo
        # already flipped the row to ROLLED_BACK, so the conditional UPDATE
        # matches 0 rows and undo_operation reports False. Simulate by flipping
        # the DB status inside the (wrapped) rollback call.
        op_id, src, dst = _log_move(comps, "conc_undo")
        real_rollback = comps.executor.rollback_operation

        def _rollback_then_flip(operation: Operation) -> bool:
            ok = real_rollback(operation)
            # Pretend a concurrent undo committed first.
            comps.history.db.execute_query(
                "UPDATE operations SET status = ? WHERE id = ?",
                (OperationStatus.ROLLED_BACK.value, op_id),
            )
            comps.history.db.get_connection().commit()
            return ok

        monkeypatch.setattr(comps.executor, "rollback_operation", _rollback_then_flip)

        assert comps.manager.undo_operation(op_id) is False

    def test_redo_operation_concurrent_flip_returns_false(
        self, comps: _Components, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 331/335: redo succeeds, but a concurrent redo already flipped the row
        # to COMPLETED, so the conditional UPDATE matches 0 rows -> False.
        op_id, src, dst = _log_move(comps, "conc_redo")
        assert comps.manager.undo_operation(op_id) is True  # now ROLLED_BACK

        real_redo = comps.executor.redo_operation

        def _redo_then_flip(operation: Operation) -> bool:
            ok = real_redo(operation)
            comps.history.db.execute_query(
                "UPDATE operations SET status = ? WHERE id = ?",
                (OperationStatus.COMPLETED.value, op_id),
            )
            comps.history.db.get_connection().commit()
            return ok

        monkeypatch.setattr(comps.executor, "redo_operation", _redo_then_flip)

        assert comps.manager.redo_operation(op_id) is False

    def test_redo_operation_logs_validation_warnings(
        self, comps: _Components, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 312: redo_operation iterates validation.warnings. validate_redo never
        # emits warnings on its own, so inject a passing result that carries one.
        op_id, src, dst = _log_move(comps, "warn_redo")
        assert comps.manager.undo_operation(op_id) is True

        monkeypatch.setattr(
            comps.validator,
            "validate_redo",
            lambda _op: ValidationResult(can_proceed=True, warnings=["heads up: redo warning"]),
        )

        assert comps.manager.redo_operation(op_id) is True
        # Behavioral check: the operation was actually redone.
        assert dst.exists()
        assert not src.exists()


# ===========================================================================
# rollback.py
# ===========================================================================


def _make_op(
    op_type: OperationType,
    source: Path,
    destination: Path | None = None,
    op_id: int = 1,
    status: OperationStatus = OperationStatus.COMPLETED,
) -> Operation:
    """Build a hand-crafted Operation for direct executor calls."""
    from datetime import UTC, datetime

    return Operation(
        operation_type=op_type,
        timestamp=datetime.now(UTC),
        source_path=source,
        destination_path=destination,
        id=op_id,
        status=status,
    )


class TestDurableMoveSymlink:
    def test_durable_move_refuses_symlink_source(self, comps: _Components) -> None:
        # 71: a symlink source is refused outright.
        target = comps.dir / "real_target.txt"
        target.write_text("payload")
        link = comps.dir / "link_src.txt"
        os.symlink(target, link)
        dst = comps.dir / "moved.txt"

        with pytest.raises(OSError, match="symlink"):
            comps.executor._durable_move(link, dst)


class TestRollbackDispatch:
    def test_rollback_delete_restores_from_trash(self, comps: _Components) -> None:
        # 122: rollback_operation dispatches DELETE -> rollback_delete restores.
        original = comps.dir / "deleted.txt"
        original.write_text("deleted content")
        op_id = comps.history.log_operation(
            operation_type=OperationType.DELETE,
            source_path=original,
        )
        # Move the file to the per-op trash dir to mimic a prior delete.
        trash_sub = comps.validator.trash_dir / str(op_id)
        trash_sub.mkdir(parents=True, exist_ok=True)
        shutil.move(str(original), str(trash_sub / original.name))
        assert not original.exists()

        op = _make_op(OperationType.DELETE, original, op_id=op_id)
        assert comps.executor.rollback_operation(op) is True
        assert original.exists()
        assert original.read_text() == "deleted content"

    def test_rollback_operation_outer_except_returns_false(
        self, comps: _Components, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 130-132: a handler that raises is caught by the outer try -> False.
        def _boom(_op: Operation) -> bool:
            raise RuntimeError("handler exploded")

        monkeypatch.setattr(comps.executor, "rollback_move", _boom)
        op = _make_op(
            OperationType.MOVE,
            comps.dir / "x_src.txt",
            comps.dir / "x_dst.txt",
        )
        assert comps.executor.rollback_operation(op) is False

    def test_redo_operation_outer_except_returns_false(
        self, comps: _Components, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 157-159: redo handler that raises is caught by the outer try -> False.
        def _boom(_op: Operation) -> bool:
            raise RuntimeError("redo handler exploded")

        monkeypatch.setattr(comps.executor, "redo_move", _boom)
        op = _make_op(
            OperationType.MOVE,
            comps.dir / "y_src.txt",
            comps.dir / "y_dst.txt",
        )
        assert comps.executor.redo_operation(op) is False


class TestRollbackDeleteEdges:
    def test_rollback_delete_rmdir_oserror_is_best_effort(self, comps: _Components) -> None:
        # 243-244: trash subdir is named after the op id but still contains
        # another file after the restore, so rmdir raises OSError and is
        # swallowed; the restore itself still succeeds.
        original = comps.dir / "restore_me.txt"
        original.write_text("restore content")
        op_id = comps.history.log_operation(
            operation_type=OperationType.DELETE,
            source_path=original,
        )
        trash_sub = comps.validator.trash_dir / str(op_id)
        trash_sub.mkdir(parents=True, exist_ok=True)
        shutil.move(str(original), str(trash_sub / original.name))
        # Leftover sibling keeps the dir non-empty -> rmdir fails (best-effort).
        (trash_sub / "leftover.txt").write_text("still here")

        op = _make_op(OperationType.DELETE, original, op_id=op_id)
        assert comps.executor.rollback_operation(op) is True
        assert original.exists()
        # Trash subdir survived because rmdir failed and was ignored.
        assert trash_sub.exists()

    def test_rollback_delete_restore_failure_returns_false(self, comps: _Components) -> None:
        # 248-250: the trash entry is a symlink, so _durable_move refuses it and
        # rollback_delete's outer except returns False.
        original = comps.dir / "sym_restore.txt"
        real_payload = comps.dir / "payload.txt"
        real_payload.write_text("payload")
        op_id = 4242
        trash_sub = comps.validator.trash_dir / str(op_id)
        trash_sub.mkdir(parents=True, exist_ok=True)
        # The "trash file" is actually a symlink; exists() follows it (True),
        # but _durable_move lstat-refuses the symlink.
        os.symlink(real_payload, trash_sub / original.name)

        op = _make_op(OperationType.DELETE, original, op_id=op_id)
        assert comps.executor.rollback_operation(op) is False
        # Original was never restored.
        assert not original.exists()


class TestRollbackTransactionExecutor:
    def test_rollback_transaction_op_raises_breaks(
        self, comps: _Components, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 475-487: one operation's rollback raises -> failed++, warning, break,
        # and the overall result is unsuccessful.
        op = _make_op(
            OperationType.MOVE,
            comps.dir / "tx_src.txt",
            comps.dir / "tx_dst.txt",
            op_id=7,
        )

        def _boom(_operation: Operation) -> bool:
            raise RuntimeError("rollback raised")

        monkeypatch.setattr(comps.executor, "rollback_operation", _boom)

        result = comps.executor.rollback_transaction("txn-raise", [op])
        assert result.success is False
        assert result.operations_failed == 1
        assert result.operations_rolled_back == 0
        # The error was recorded for the offending op id.
        assert result.errors and result.errors[0][0] == 7
        # The stop-on-failure warning was appended.
        assert any("stopped at operation" in w for w in result.warnings)
