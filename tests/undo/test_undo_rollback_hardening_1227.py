"""WP-2.2 write/undo-path hardening (#1227).

Durable, symlink-refusing, inode-verified rollback moves
(``RollbackExecutor._durable_move``) plus transactional, concurrency-safe
undo/redo status flips (the B3 write/commit race) in ``UndoManager``.

Full cross-device crash-safe ``durable_move`` and journal-backed crash recovery
are WP-1.2b (#1248); this slice delivers the symlink-refusal, inode-anti-swap,
directory-fsync, and double-apply-guard guarantees the undo path needs now.
"""

from __future__ import annotations

import errno
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from file_organizer.history.models import Operation, OperationStatus, OperationType
from file_organizer.history.tracker import OperationHistory
from file_organizer.undo.rollback import RollbackExecutor
from file_organizer.undo.undo_manager import UndoManager
from file_organizer.undo.validator import OperationValidator

pytestmark = [pytest.mark.unit, pytest.mark.ci]

posix_only = pytest.mark.skipif(
    sys.platform == "win32", reason="symlink/inode hardening is POSIX-focused"
)


def _executor(tmp_path: Path) -> RollbackExecutor:
    return RollbackExecutor(validator=OperationValidator(trash_dir=tmp_path / "trash"))


def _manager(tmp_path: Path) -> UndoManager:
    history = OperationHistory(db_path=tmp_path / "history.db")
    validator = OperationValidator(trash_dir=tmp_path / "trash")
    return UndoManager(
        history=history,
        validator=validator,
        executor=RollbackExecutor(validator=validator),
    )


# --------------------------------------------------------------------------- #
# _durable_move
# --------------------------------------------------------------------------- #


def test_durable_move_preserves_inode_same_fs(tmp_path: Path) -> None:
    """A same-filesystem move uses os.replace, preserving the inode and content
    and creating the destination parent."""
    ex = _executor(tmp_path)
    src = tmp_path / "a.txt"
    src.write_text("body")
    ino_before = src.stat().st_ino
    dst = tmp_path / "sub" / "b.txt"

    ex._durable_move(src, dst)

    assert not src.exists()
    assert dst.read_text() == "body"
    assert dst.stat().st_ino == ino_before


@posix_only
def test_durable_move_refuses_symlink_source(tmp_path: Path) -> None:
    """A symlinked source is refused (anti-swap) instead of being dereferenced
    into the destination."""
    secret = tmp_path / "secret.txt"
    secret.write_text("secret")
    link = tmp_path / "link.txt"
    link.symlink_to(secret)
    ex = _executor(tmp_path)
    dst = tmp_path / "restored.txt"

    with pytest.raises(OSError, match="symlink"):
        ex._durable_move(link, dst)

    assert not dst.exists()  # nothing moved
    assert secret.read_text() == "secret"  # victim untouched
    assert link.is_symlink()  # link not consumed


@posix_only
def test_rollback_move_refuses_symlinked_destination(tmp_path: Path) -> None:
    """If the recorded move destination was swapped for a symlink, rollback
    refuses rather than moving the link's target into the source location."""
    ex = _executor(tmp_path)
    source = tmp_path / "source.txt"
    outside = tmp_path / "outside.txt"
    outside.write_text("attacker")
    dest = tmp_path / "dest.txt"
    dest.symlink_to(outside)
    op = Operation(
        id=1,
        operation_type=OperationType.MOVE,
        timestamp=datetime.now(tz=UTC),
        source_path=source,
        destination_path=dest,
        status=OperationStatus.COMPLETED,
    )

    assert ex.rollback_move(op) is False
    assert not source.exists()  # attacker's file NOT moved to source
    assert outside.read_text() == "attacker"


def test_durable_move_detects_inode_swap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A same-fs rename must preserve the inode; a simulated post-move identity
    mismatch (a swap) is detected and refused."""
    import file_organizer.undo.rollback as rb

    ex = _executor(tmp_path)
    src = tmp_path / "a.txt"
    src.write_text("x")
    dst = tmp_path / "b.txt"

    real_lstat = rb.os.lstat

    class _FakeStat:
        def __init__(self, wrapped: object) -> None:
            self._wrapped = wrapped

        def __getattr__(self, name: str) -> object:
            return getattr(self._wrapped, name)

        @property
        def st_dev(self) -> int:
            return 4242

        @property
        def st_ino(self) -> int:
            return 999999  # differs from the real source identity -> "swap"

    def fake_lstat(path: object, *a: object, **k: object) -> object:
        stat_result = real_lstat(path, *a, **k)
        try:
            is_post_move_dst = Path(path) == dst and not src.exists()
        except TypeError:
            is_post_move_dst = False
        if is_post_move_dst:
            return _FakeStat(stat_result)  # post-move dst lstat -> mismatched identity
        return stat_result

    monkeypatch.setattr(rb.os, "lstat", fake_lstat)

    with pytest.raises(OSError, match="inode swap"):
        ex._durable_move(src, dst)


def test_rollback_and_redo_rename_use_durable_move(tmp_path: Path) -> None:
    """rollback_rename / redo_rename route through the hardened move."""
    ex = _executor(tmp_path)
    old = tmp_path / "old.txt"
    new = tmp_path / "new.txt"
    old.write_text("c")
    new_from_rename = old.rename(new) or new  # perform the rename forward
    op = Operation(
        id=1,
        operation_type=OperationType.RENAME,
        timestamp=datetime.now(tz=UTC),
        source_path=old,
        destination_path=new,
        status=OperationStatus.COMPLETED,
    )
    assert ex.rollback_rename(op) is True
    assert old.read_text() == "c" and not new.exists()
    assert ex.redo_rename(op) is True
    assert new.read_text() == "c" and not old.exists()
    _ = new_from_rename


def test_rollback_move_without_destination_returns_false(tmp_path: Path) -> None:
    """A move operation with no destination cannot be rolled back."""
    ex = _executor(tmp_path)
    op = Operation(
        id=1,
        operation_type=OperationType.MOVE,
        timestamp=datetime.now(tz=UTC),
        source_path=tmp_path / "s.txt",
        destination_path=None,
        status=OperationStatus.COMPLETED,
    )
    assert ex.rollback_move(op) is False


def test_rollback_delete_restores_from_trash(tmp_path: Path) -> None:
    """rollback_delete restores a trashed file via the hardened move."""
    trash_dir = tmp_path / "trash"
    ex = RollbackExecutor(validator=OperationValidator(trash_dir=trash_dir))
    original = tmp_path / "doc.txt"
    # Stage the file in trash under <op_id>/<name> as the validator expects.
    op_trash = trash_dir / "1"
    op_trash.mkdir(parents=True)
    (op_trash / "doc.txt").write_text("trashed body")
    op = Operation(
        id=1,
        operation_type=OperationType.DELETE,
        timestamp=datetime.now(tz=UTC),
        source_path=original,
        status=OperationStatus.COMPLETED,
    )
    assert ex.rollback_delete(op) is True
    assert original.read_text() == "trashed body"


def test_rollback_copy_moves_copy_to_trash(tmp_path: Path) -> None:
    """rollback_copy sends the copy to trash via the hardened _move_to_trash."""
    ex = _executor(tmp_path)
    copy_path = tmp_path / "copy.txt"
    copy_path.write_text("copy")
    op = Operation(
        id=7,
        operation_type=OperationType.COPY,
        timestamp=datetime.now(tz=UTC),
        source_path=tmp_path / "orig.txt",
        destination_path=copy_path,
        status=OperationStatus.COMPLETED,
    )
    assert ex.rollback_copy(op) is True
    assert not copy_path.exists()
    assert (tmp_path / "trash" / "7" / "copy.txt").read_text() == "copy"


def test_move_to_trash_without_operation_id_uses_uuid(tmp_path: Path) -> None:
    """_move_to_trash without an operation id files under a uuid subdir and
    still routes through the hardened move."""
    ex = _executor(tmp_path)
    f = tmp_path / "x.txt"
    f.write_text("data")

    trash_path = ex._move_to_trash(f)

    assert trash_path.read_text() == "data"
    assert not f.exists()
    assert trash_path.parent.parent == (tmp_path / "trash")


def test_durable_move_cross_device_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When os.replace raises EXDEV the move falls back to shutil.move (and the
    same-fs inode check is skipped)."""
    import file_organizer.undo.rollback as rb

    ex = _executor(tmp_path)
    src = tmp_path / "a.txt"
    src.write_text("payload")
    dst = tmp_path / "b.txt"

    def fake_replace(s: object, d: object) -> None:
        raise OSError(errno.EXDEV, "cross-device link")

    monkeypatch.setattr(rb.os, "replace", fake_replace)

    ex._durable_move(src, dst)

    assert dst.read_text() == "payload"
    assert not src.exists()


def test_durable_move_exdev_symlink_swap_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the source is swapped for a symlink between the initial check and the
    EXDEV cross-device fallback, the re-check refuses it (no shutil.move deref)."""
    import stat as stat_mod

    import file_organizer.undo.rollback as rb

    ex = _executor(tmp_path)
    src = tmp_path / "a.txt"
    src.write_text("x")
    dst = tmp_path / "b.txt"

    real_lstat = rb.os.lstat
    calls = {"n": 0}

    class _SymlinkStat:
        st_mode = stat_mod.S_IFLNK | 0o777
        st_dev = 1
        st_ino = 1

    def fake_lstat(path: object, *a: object, **k: object) -> object:
        calls["n"] += 1
        if calls["n"] == 1:  # initial source check → real (regular)
            return real_lstat(path, *a, **k)
        return _SymlinkStat()  # EXDEV re-check → simulated symlink swap

    def fake_replace(s: object, d: object) -> None:
        raise OSError(errno.EXDEV, "cross-device link")

    monkeypatch.setattr(rb.os, "lstat", fake_lstat)
    monkeypatch.setattr(rb.os, "replace", fake_replace)

    with pytest.raises(OSError, match="symlink"):
        ex._durable_move(src, dst)
    assert not dst.exists()


def test_durable_move_reraises_non_exdev_replace_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A non-EXDEV os.replace failure propagates (no silent cross-device path)."""
    import file_organizer.undo.rollback as rb

    ex = _executor(tmp_path)
    src = tmp_path / "a.txt"
    src.write_text("x")
    dst = tmp_path / "b.txt"

    def fake_replace(s: object, d: object) -> None:
        raise OSError(errno.EACCES, "permission denied")

    monkeypatch.setattr(rb.os, "replace", fake_replace)

    with pytest.raises(OSError, match="permission denied"):
        ex._durable_move(src, dst)


def test_durable_move_refuses_symlinked_destination_after_move(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the destination is a symlink after the move (post-move swap), it is
    refused rather than trusted."""
    import stat as stat_mod

    import file_organizer.undo.rollback as rb

    ex = _executor(tmp_path)
    src = tmp_path / "a.txt"
    src.write_text("x")
    dst = tmp_path / "b.txt"

    real_lstat = rb.os.lstat

    class _SymlinkStat:
        st_mode = stat_mod.S_IFLNK | 0o777

    def fake_lstat(path: object, *a: object, **k: object) -> object:
        if str(path) == str(src):
            return real_lstat(path, *a, **k)
        return _SymlinkStat()  # post-move dst → looks like a symlink

    monkeypatch.setattr(rb.os, "lstat", fake_lstat)

    with pytest.raises(OSError, match="symlink after move"):
        ex._durable_move(src, dst)


# --------------------------------------------------------------------------- #
# UndoManager transactional status flips (race B3)
# --------------------------------------------------------------------------- #


def test_undo_then_redo_flip_status(tmp_path: Path) -> None:
    """Happy path: the conditional status flips still transition the operation
    COMPLETED → ROLLED_BACK → COMPLETED across undo/redo."""
    mgr = _manager(tmp_path)
    try:
        src = tmp_path / "s.txt"
        src.write_text("c")
        dst = tmp_path / "d.txt"
        shutil.move(str(src), str(dst))
        op_id = mgr.history.log_operation(
            operation_type=OperationType.MOVE, source_path=src, destination_path=dst
        )

        assert mgr.undo_operation(op_id) is True
        assert src.exists() and not dst.exists()
        op = next(o for o in mgr.history.get_operations(limit=10) if o.id == op_id)
        assert op.status == OperationStatus.ROLLED_BACK
        assert op_id not in {o.id for o in mgr.get_undo_stack()}

        assert mgr.redo_operation(op_id) is True
        assert dst.exists() and not src.exists()
        op = next(o for o in mgr.history.get_operations(limit=10) if o.id == op_id)
        assert op.status == OperationStatus.COMPLETED
    finally:
        mgr.close()


def test_undo_guard_skips_duplicate_flip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """If a concurrent undo flips the row to ROLLED_BACK between load and the
    conditional UPDATE, the guard (rowcount == 0) returns False rather than
    double-counting the undo."""
    mgr = _manager(tmp_path)
    try:
        src = tmp_path / "s.txt"
        src.write_text("c")
        dst = tmp_path / "d.txt"
        shutil.move(str(src), str(dst))
        op_id = mgr.history.log_operation(
            operation_type=OperationType.MOVE, source_path=src, destination_path=dst
        )

        real_rollback = mgr.executor.rollback_operation

        def racing_rollback(operation: Operation) -> bool:
            ok = real_rollback(operation)
            # Simulate a concurrent undo committing the status flip first.
            mgr.history.db.execute_query(
                "UPDATE operations SET status = ? WHERE id = ?",
                (OperationStatus.ROLLED_BACK.value, op_id),
            )
            mgr.history.db.get_connection().commit()
            return ok

        monkeypatch.setattr(mgr.executor, "rollback_operation", racing_rollback)

        assert mgr.undo_operation(op_id) is False
    finally:
        mgr.close()


def test_redo_guard_skips_duplicate_flip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The redo status flip is likewise guarded: a concurrent redo that flips
    the row to COMPLETED first makes the conditional UPDATE match no rows, so
    redo_operation returns False instead of double-counting."""
    mgr = _manager(tmp_path)
    try:
        src = tmp_path / "s.txt"
        src.write_text("c")
        dst = tmp_path / "d.txt"
        shutil.move(str(src), str(dst))
        op_id = mgr.history.log_operation(
            operation_type=OperationType.MOVE, source_path=src, destination_path=dst
        )
        assert mgr.undo_operation(op_id) is True  # now ROLLED_BACK, file at src

        real_redo = mgr.executor.redo_operation

        def racing_redo(operation: Operation) -> bool:
            ok = real_redo(operation)
            mgr.history.db.execute_query(
                "UPDATE operations SET status = ? WHERE id = ?",
                (OperationStatus.COMPLETED.value, op_id),
            )
            mgr.history.db.get_connection().commit()
            return ok

        monkeypatch.setattr(mgr.executor, "redo_operation", racing_redo)

        assert mgr.redo_operation(op_id) is False
    finally:
        mgr.close()
