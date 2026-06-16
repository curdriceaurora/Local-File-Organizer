"""F7 tests for ``src/undo/durable_move.py``.

Hardening roadmap #159 F7 — undo rollback durability. The helper
is *atomic on same-device* and *durable + idempotent on cross-device*
(EXDEV). Tests lock both branches + the recovery sweep that cleans
up after a crash mid-move.
"""

from __future__ import annotations

import errno
import json
import logging
import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.ci, pytest.mark.integration]


@contextmanager
def _capture_durable_move_warnings() -> Iterator[list[logging.LogRecord]]:
    """Collect WARNING+ records from the durable_move logger, immune to global
    logging state.

    ``caplog`` installs a handler on the root logger and relies on propagation;
    under xdist another test in the same shard can leak ``logging.disable()`` or
    toggle this logger's level/propagation, leaving ``caplog.records`` empty even
    though the warning fired (#1257). Attaching a handler directly to the target
    logger and clearing any global disable makes the assertion deterministic.
    """
    target = logging.getLogger("file_organizer.undo.durable_move")
    records: list[logging.LogRecord] = []

    class _Collector(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = _Collector(level=logging.WARNING)
    prev_disable = logging.root.manager.disable
    prev_level = target.level
    prev_disabled = target.disabled
    logging.disable(logging.NOTSET)
    target.addHandler(handler)
    target.setLevel(logging.WARNING)
    target.disabled = False
    try:
        yield records
    finally:
        target.removeHandler(handler)
        target.setLevel(prev_level)
        target.disabled = prev_disabled
        logging.disable(prev_disable)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestDurableMoveSameDevice:
    """Same-device moves use ``os.replace`` — truly atomic."""

    def test_basic_move(self, tmp_path: Path) -> None:
        from file_organizer.undo.durable_move import durable_move

        src = tmp_path / "src.txt"
        dst = tmp_path / "dst.txt"
        src.write_text("payload")
        journal = tmp_path / "move.journal"

        durable_move(src, dst, journal=journal)

        assert not src.exists()
        assert dst.read_text() == "payload"

    def test_move_to_nested_destination(self, tmp_path: Path) -> None:
        """Destination's parent directory may not exist; helper
        creates it (matches ``shutil.move`` semantics callers relied
        on pre-F7)."""
        from file_organizer.undo.durable_move import durable_move

        src = tmp_path / "src.txt"
        src.write_text("x")
        dst = tmp_path / "nested" / "deep" / "dst.txt"
        journal = tmp_path / "move.journal"

        durable_move(src, dst, journal=journal)
        assert dst.exists()

    def test_same_device_does_not_append_journal(self, tmp_path: Path) -> None:
        """Same-device renames are truly atomic — no journal entry
        needed. Keeping the journal empty on the happy path keeps the
        recovery sweep fast even after millions of successful
        operations."""
        from file_organizer.undo.durable_move import durable_move

        src = tmp_path / "a.txt"
        dst = tmp_path / "b.txt"
        src.write_text("x")
        journal = tmp_path / "move.journal"

        durable_move(src, dst, journal=journal)

        # Journal either doesn't exist or is empty after a clean
        # same-device move.
        if journal.exists():
            assert journal.read_text().strip() == ""

    def test_same_device_preserves_symlink_identity(self, tmp_path: Path) -> None:
        """Round-9 INV-2b: same-device move of a symlink must leave a
        symlink at dst — NOT dereference and copy the target's bytes.
        ``os.replace`` already does this natively on POSIX (symlinks
        are first-class file-system entities to ``rename(2)``); this
        test locks down the contract so a future refactor that
        accidentally adds a ``stat`` follow before the rename can't
        regress it without breaking the test.

        Companion to ``test_cross_device_preserves_symlink_identity``
        which covers the EXDEV branch.
        """
        if os.name == "nt":
            pytest.skip("POSIX symlinks")
        from file_organizer.undo.durable_move import durable_move

        target = tmp_path / "target.txt"
        target.write_text("target bytes")
        src = tmp_path / "link.txt"
        src.symlink_to(target)
        dst = tmp_path / "moved-link.txt"
        journal = tmp_path / "move.journal"

        durable_move(src, dst, journal=journal)

        assert dst.is_symlink(), (
            "same-device move of a symlink must land a symlink at dst "
            "(round-9 INV-2b — locks down the os.replace contract)"
        )
        assert os.readlink(dst) == str(target)
        assert not src.is_symlink() and not src.exists()
        assert target.read_text() == "target bytes"

    def test_preserves_file_contents_and_permissions(self, tmp_path: Path) -> None:
        """File contents + mode bits survive the move (pre-F7 behavior
        via ``shutil.move``)."""
        from file_organizer.undo.durable_move import durable_move

        if os.name == "nt":
            pytest.skip("POSIX mode bits")
        src = tmp_path / "src.bin"
        dst = tmp_path / "dst.bin"
        payload = bytes(range(256))
        src.write_bytes(payload)
        os.chmod(src, 0o640)
        journal = tmp_path / "move.journal"

        durable_move(src, dst, journal=journal)

        assert dst.read_bytes() == payload
        mode = dst.stat().st_mode & 0o777
        assert mode == 0o640, f"expected 0o640 to survive, got {mode:#o}"


# ---------------------------------------------------------------------------
# Cross-device (EXDEV) simulation
# ---------------------------------------------------------------------------


class TestDurableMoveCrossDevice:
    """EXDEV branch: copy-fsync-replace with a journal.

    Real cross-device moves require two mount points, which isn't
    practical in tests. We simulate by monkeypatching ``os.replace``
    to raise ``OSError(EXDEV)`` on the first call so the helper falls
    through to the copy path.
    """

    def _force_exdev(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Make ``os.replace`` raise EXDEV once to trigger the
        cross-device path. Subsequent calls pass through to the
        real implementation so the sweep/cleanup helpers still work.
        """
        real_replace = os.replace
        state = {"triggered": False}

        def exdev_once(src, dst):  # type: ignore[no-untyped-def]
            if not state["triggered"]:
                state["triggered"] = True
                raise OSError(errno.EXDEV, "Cross-device link", str(src))
            return real_replace(src, dst)

        monkeypatch.setattr("file_organizer.undo.durable_move.os.replace", exdev_once)

    def test_cross_device_copy_completes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Happy-path EXDEV: helper falls back to copy+fsync+unlink
        and leaves the destination with the source's contents."""
        from file_organizer.undo.durable_move import durable_move

        self._force_exdev(monkeypatch)

        src = tmp_path / "src.txt"
        dst = tmp_path / "dst.txt"
        src.write_text("cross-device payload")
        journal = tmp_path / "move.journal"

        durable_move(src, dst, journal=journal)

        assert not src.exists()
        assert dst.read_text() == "cross-device payload"

    def test_cross_device_journal_reaches_done_state(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """After a successful EXDEV move, the journal entry for the
        operation reaches ``state: done``. A subsequent ``sweep`` is
        a no-op."""
        from file_organizer.undo.durable_move import durable_move, sweep

        self._force_exdev(monkeypatch)
        src = tmp_path / "s.txt"
        dst = tmp_path / "d.txt"
        src.write_text("x")
        journal = tmp_path / "move.journal"

        durable_move(src, dst, journal=journal)

        entries = _read_journal(journal)
        assert entries, "journal must contain at least one entry on EXDEV"
        assert entries[-1]["state"] == "done"
        # Sweep is a no-op on done entries.
        sweep(journal)
        assert dst.read_text() == "x"

    def test_cross_device_preserves_symlink_identity(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Codex P1 PRRT_kwDOR_Rkws59gnab: EXDEV symlink moves must
        preserve the symlink itself — NOT dereference and copy the
        target's bytes. The pre-F7 ``shutil.move`` does this; the F7
        helper must match.
        """
        if os.name == "nt":
            pytest.skip("POSIX symlinks")
        from file_organizer.undo.durable_move import durable_move

        self._force_exdev(monkeypatch)
        target = tmp_path / "target.txt"
        target.write_text("target bytes")
        src = tmp_path / "link.txt"
        src.symlink_to(target)
        dst = tmp_path / "moved-link.txt"
        journal = tmp_path / "move.journal"

        durable_move(src, dst, journal=journal)

        # dst is now a symlink (not a regular file), pointing at the
        # same target. Reading through it still yields target bytes,
        # but the identity check is what matters.
        assert dst.is_symlink(), (
            "EXDEV move of a symlink must land a symlink at dst; "
            "shutil.copyfile dereferences and produces a regular file "
            "(codex P1 PRRT_kwDOR_Rkws59gnab)"
        )
        assert os.readlink(dst) == str(target), (
            f"symlink target must be preserved; got {os.readlink(dst)!r}"
        )
        # Original symlink is gone; target itself is untouched.
        assert not src.is_symlink() and not src.exists()
        assert target.read_text() == "target bytes"

    def test_cross_device_preserves_dangling_symlink(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Dangling symlinks (target doesn't exist) are legitimate
        file-system entries — ``shutil.move`` preserves them on EXDEV.
        ``shutil.copyfile`` on a dangling symlink raises
        ``FileNotFoundError`` because it tries to open the target, so
        the old implementation would have destroyed the entry entirely.
        The readlink-based path handles this correctly.
        """
        if os.name == "nt":
            pytest.skip("POSIX symlinks")
        from file_organizer.undo.durable_move import durable_move

        self._force_exdev(monkeypatch)
        src = tmp_path / "dangling.txt"
        # Target deliberately does NOT exist.
        src.symlink_to(tmp_path / "nonexistent.txt")
        dst = tmp_path / "moved-dangling.txt"
        journal = tmp_path / "move.journal"

        durable_move(src, dst, journal=journal)

        assert dst.is_symlink(), "dangling symlink must land as a symlink at dst"
        assert os.readlink(dst) == str(tmp_path / "nonexistent.txt")
        assert not src.is_symlink() and not os.path.lexists(src)

    def test_cross_device_symlink_clears_stale_tmp(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If a prior crashed attempt left a stale tmp symlink at the
        exact PID-suffixed path, the new attempt removes it and
        proceeds — covers the defensive ``os.path.lexists`` branch
        in the EXDEV symlink path.
        """
        if os.name == "nt":
            pytest.skip("POSIX symlinks")
        from file_organizer.undo.durable_move import durable_move

        self._force_exdev(monkeypatch)
        target = tmp_path / "target.txt"
        target.write_text("t")
        src = tmp_path / "link.txt"
        src.symlink_to(target)
        dst = tmp_path / "dst.txt"

        # Pre-create a stale tmp at the exact same name the symlink
        # branch generates. Matches the ``f".{dst.name}.{pid}.symlink.tmp"``
        # format in ``_durable_cross_device_move``.
        stale = dst.parent / f".{dst.name}.{os.getpid()}.symlink.tmp"
        stale.symlink_to(tmp_path / "something-unrelated")
        assert os.path.lexists(stale)

        durable_move(src, dst, journal=tmp_path / "j.journal")

        assert dst.is_symlink()
        assert os.readlink(dst) == str(target)
        # Stale tmp is gone (either cleaned up pre-symlink or swept
        # by os.replace).
        assert not os.path.lexists(stale)

    def test_cross_device_fsyncs_src_parent_after_unlink(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Codex P2 PRRT_kwDOR_Rkws59gnah: after unlinking ``src`` in
        the EXDEV path, ``src.parent`` must be fsynced BEFORE the
        ``done`` journal entry is appended. Otherwise a power loss in
        that window could let ``src`` reappear on reboot while the
        journal records ``done`` — sweep drops the entry and skips
        cleanup, leaving a phantom copy on disk.

        Instrumented by capturing every ``fsync_directory`` call and
        asserting ``src.parent`` was fsynced AFTER the ``os.unlink(src)``
        but before the final ``_append_journal`` with state=done.
        """
        from file_organizer.undo import durable_move as dm

        self._force_exdev(monkeypatch)

        fsync_calls: list[tuple[str, Path]] = []  # (stage, path)
        unlinked: list[Path] = []
        journaled_done: list[int] = []  # indices into fsync_calls

        real_fsync = dm.fsync_directory
        real_unlink = os.unlink
        real_append = dm._append_journal

        def tracking_fsync(path):  # type: ignore[no-untyped-def]
            fsync_calls.append(("fsync", Path(path)))
            real_fsync(path)

        def tracking_unlink(p, *a, **k):  # type: ignore[no-untyped-def]
            unlinked.append(Path(p))
            fsync_calls.append(("unlink", Path(p)))
            return real_unlink(p, *a, **k)

        def tracking_append(journal, payload):  # type: ignore[no-untyped-def]
            if payload.get("state") == "done":
                journaled_done.append(len(fsync_calls))
            return real_append(journal, payload)

        monkeypatch.setattr("file_organizer.undo.durable_move.fsync_directory", tracking_fsync)
        monkeypatch.setattr("file_organizer.undo.durable_move.os.unlink", tracking_unlink)
        monkeypatch.setattr("file_organizer.undo.durable_move._append_journal", tracking_append)

        src = tmp_path / "src.txt"
        dst = tmp_path / "dst.txt"
        src.write_text("x")
        journal = tmp_path / "move.journal"

        dm.durable_move(src, dst, journal=journal)

        # Find the unlink(src) event and the fsync(src) that must
        # follow it, and verify both happen before state=done was
        # journaled.
        unlink_idx = next(
            i for i, (stage, p) in enumerate(fsync_calls) if stage == "unlink" and p == src
        )
        post_unlink_src_fsync = [
            i
            for i, (stage, p) in enumerate(fsync_calls)
            if i > unlink_idx and stage == "fsync" and p == src
        ]
        assert post_unlink_src_fsync, (
            f"fsync_directory(src) must be called after os.unlink(src) "
            f"(codex P2 PRRT_kwDOR_Rkws59gnah). call trace: {fsync_calls}"
        )
        done_idx = journaled_done[0]
        assert post_unlink_src_fsync[0] < done_idx, (
            f"fsync_directory(src) must happen BEFORE state=done is journaled; "
            f"src fsync at {post_unlink_src_fsync[0]}, done at {done_idx}; "
            f"trace: {fsync_calls}"
        )


# ---------------------------------------------------------------------------
# Recovery sweep — crash simulation
# ---------------------------------------------------------------------------


class TestDurableMoveSweep:
    """``sweep(journal)`` at CLI startup completes or rolls back
    interrupted EXDEV moves based on the last journal state.
    """

    def test_sweep_noop_on_empty_journal(self, tmp_path: Path) -> None:
        """Missing or empty journal → sweep is a no-op."""
        from file_organizer.undo.durable_move import sweep

        sweep(tmp_path / "nonexistent.journal")  # no raise

        journal = tmp_path / "empty.journal"
        journal.write_text("")
        sweep(journal)

    def test_sweep_started_state_retains_entry_and_preserves_paths(self, tmp_path: Path) -> None:
        """Codex P1 PRRT_kwDOR_Rkws59gbdD + PRRT_kwDOR_Rkws59g2Ex:
        ``started`` is AMBIGUOUS — a crash between ``os.replace`` and
        the ``copied`` journal append leaves a ``started`` entry with
        dst already overwritten. Sweep must:

        - NEVER unlink dst (data-loss in the "crashed before replace"
          sub-case)
        - NEVER unlink src (data-loss in the same sub-case if dst was
          never replaced)
        - RETAIN the journal entry so the next sweep / operator /
          retry can reconcile (dropping it would lose recovery
          metadata and potentially orphan files permanently)
        """
        from file_organizer.undo.durable_move import sweep

        src = tmp_path / "src.txt"
        dst = tmp_path / "dst.txt"
        src.write_text("intact source")
        dst.write_text("legitimate pre-existing destination")
        journal = tmp_path / "move.journal"
        _write_journal(
            journal,
            [{"op": "move", "src": str(src), "dst": str(dst), "state": "started"}],
        )

        sweep(journal)

        # Both paths preserved unchanged — sweep didn't destroy anything.
        assert src.read_text() == "intact source"
        assert dst.read_text() == "legitimate pre-existing destination", (
            "started-state sweep must not destroy a legitimate dst; "
            "this was the codex P1 data-loss path"
        )
        # Entry RETAINED so the next sweep / retry / operator can
        # reconcile (codex P1 PRRT_kwDOR_Rkws59g2Ex — retry metadata).
        entries = _read_journal(journal)
        assert len(entries) == 1, (
            f"started entry must be retained for ambiguity resolution; got {entries}"
        )
        assert entries[0]["state"] == "started"
        assert entries[0]["src"] == str(src)
        assert entries[0]["dst"] == str(dst)

    def test_sweep_completes_copied_state(self, tmp_path: Path) -> None:
        """State ``copied`` = crash after destination fsync but
        before source unlink. Destination is complete; finish the
        operation by unlinking the source.
        """
        from file_organizer.undo.durable_move import sweep

        src = tmp_path / "src.txt"
        dst = tmp_path / "dst.txt"
        src.write_text("leftover source")
        dst.write_text("complete destination")
        journal = tmp_path / "move.journal"
        _write_journal(
            journal,
            [{"op": "move", "src": str(src), "dst": str(dst), "state": "copied"}],
        )

        sweep(journal)

        # Source removed; destination preserved.
        assert not src.exists(), "copied-state src must be unlinked on sweep"
        assert dst.read_text() == "complete destination"
        assert _read_journal(journal) == []

    def test_sweep_copied_state_retains_when_dst_missing(self, tmp_path: Path) -> None:
        """Codex P1 PRRT_kwDOR_Rkws59hGWW: if an out-of-band actor
        removed ``dst`` between the ``copied`` journal write and the
        next sweep (operator cleanup, another process, backup
        restore), sweep MUST NOT unlink ``src`` — that would destroy
        the last remaining copy. The entry is retained for operator
        or next-pass reconciliation instead.
        """
        from file_organizer.undo.durable_move import sweep

        src = tmp_path / "src.txt"
        src.write_text("last remaining copy")
        dst = tmp_path / "dst.txt"  # deliberately absent — removed between journal + sweep
        journal = tmp_path / "move.journal"
        _write_journal(
            journal,
            [{"op": "move", "src": str(src), "dst": str(dst), "state": "copied"}],
        )

        sweep(journal)

        # Source preserved (data not destroyed), entry retained.
        assert src.read_text() == "last remaining copy", (
            "copied-state sweep must not unlink src when dst is missing; "
            "this was a data-loss path (codex P1 PRRT_kwDOR_Rkws59hGWW)"
        )
        entries = _read_journal(journal)
        assert len(entries) == 1 and entries[0]["state"] == "copied", (
            f"entry must be retained for reconciliation; got {entries}"
        )

    def test_sweep_retains_entries_with_unknown_op(self, tmp_path: Path) -> None:
        """Codex P2 PRRT_kwDOR_Rkws59hdFb: the journal is shared —
        ``op`` field is reserved for future ``"copy"``, ``"symlink"``
        etc. Sweep must NEVER apply move semantics to a non-``move``
        op (would data-loss on downgrade from a binary that wrote
        the newer op). Retain for a future handler.
        """
        from file_organizer.undo.durable_move import sweep

        src = tmp_path / "src.txt"
        dst = tmp_path / "dst.txt"
        src.write_text("original")
        dst.write_text("pre-existing")
        journal = tmp_path / "move.journal"
        _write_journal(
            journal,
            [
                # Future op type sweep doesn't understand.
                {
                    "op": "mirror",
                    "src": str(src),
                    "dst": str(dst),
                    "state": "copied",
                },
            ],
        )

        sweep(journal)

        # Neither path touched (crucial: the copied-state move branch
        # would have unlinked src — that MUST NOT happen here).
        assert src.read_text() == "original", (
            "sweep must not apply move semantics to op='mirror'; "
            "unlinking src would be data loss (codex P2 PRRT_kwDOR_Rkws59hdFb)"
        )
        assert dst.read_text() == "pre-existing"
        # Entry retained for a future binary that knows ``mirror``.
        entries = _read_journal(journal)
        assert len(entries) == 1 and entries[0]["op"] == "mirror"

    def test_sweep_copied_state_tolerates_fsync_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Unusual filesystems can raise ``OSError`` from directory
        fsync. Sweep logs it and continues — the unlink itself
        succeeded, and the next sweep pass would notice if the entry
        hadn't persisted. This is a defensive branch but worth
        locking down so a future refactor doesn't accidentally turn
        a non-fatal log into a retry.
        """
        from file_organizer.undo import durable_move as dm

        src = tmp_path / "src.txt"
        dst = tmp_path / "dst.txt"
        src.write_text("x")
        dst.write_text("y")
        journal = tmp_path / "move.journal"
        _write_journal(
            journal,
            [{"op": "move", "src": str(src), "dst": str(dst), "state": "copied"}],
        )

        # First fsync (journal fd in sweep locked body) succeeds; the
        # second fsync (src.parent after unlink) raises. We detect
        # the call by path: only the src.parent fsync targets src.
        real_fsync = dm.fsync_directory

        def flaky_fsync(path):  # type: ignore[no-untyped-def]
            if Path(path) == src:
                raise OSError(5, "fsync failed on exotic fs")
            real_fsync(path)

        monkeypatch.setattr("file_organizer.undo.durable_move.fsync_directory", flaky_fsync)

        # Must not raise — sweep tolerates the fsync failure.
        dm.sweep(journal)

        # Reconciliation still completed: src was unlinked and entry
        # dropped from the journal (the fsync failure is non-fatal).
        assert not src.exists()
        assert _read_journal(journal) == []

    def test_sweep_copied_state_fsyncs_src_parent_after_unlink(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Codex P2 PRRT_kwDOR_Rkws59hT9b: parallel to the in-line
        post-unlink fsync in ``_durable_cross_device_move`` (gnah):
        the sweep's copied-state reconciliation also unlinks ``src``,
        and that unlink must be fsynced to disk BEFORE sweep truncates
        the journal entry. Otherwise a power loss between the unlink
        and the truncate could let ``src`` reappear on reboot while
        the recovery record is already gone — no retry metadata, no
        way to know there's a phantom file to clean up.

        Instruments fsync_directory to verify the order:
        unlink(src) → fsync(src.parent) → return True → sweep truncate.
        """
        from file_organizer.undo import durable_move as dm

        src = tmp_path / "src.txt"
        dst = tmp_path / "dst.txt"
        src.write_text("leftover")
        dst.write_text("complete")
        journal = tmp_path / "move.journal"
        _write_journal(
            journal,
            [{"op": "move", "src": str(src), "dst": str(dst), "state": "copied"}],
        )

        trace: list[tuple[str, Path]] = []
        real_fsync = dm.fsync_directory
        real_unlink = Path.unlink

        def tracking_fsync(path):  # type: ignore[no-untyped-def]
            trace.append(("fsync", Path(path)))
            real_fsync(path)

        def tracking_unlink(self, *a, **k):  # type: ignore[no-untyped-def]
            trace.append(("unlink", Path(self)))
            return real_unlink(self, *a, **k)

        monkeypatch.setattr("file_organizer.undo.durable_move.fsync_directory", tracking_fsync)
        monkeypatch.setattr(Path, "unlink", tracking_unlink)

        dm.sweep(journal)

        # The sweep flock-body itself fsyncs the journal fd; we care
        # about the ordering of src's unlink vs the subsequent
        # fsync_directory(src).
        unlink_ix = next(i for i, (stage, p) in enumerate(trace) if stage == "unlink" and p == src)
        post_unlink_fsync = [
            i
            for i, (stage, p) in enumerate(trace)
            if i > unlink_ix and stage == "fsync" and p == src
        ]
        assert post_unlink_fsync, (
            f"copied-state sweep must fsync_directory(src) AFTER "
            f"os.unlink(src) (codex P2 PRRT_kwDOR_Rkws59hT9b); trace: {trace}"
        )

    def test_sweep_copied_state_accepts_symlink_dst(self, tmp_path: Path) -> None:
        """``os.path.lexists(dst)`` (not ``dst.exists()``) is used so a
        dangling-symlink dst still counts as present — the symlink
        itself is the thing we committed to via ``os.replace`` in the
        symlink-preserving EXDEV branch.
        """
        if os.name == "nt":
            pytest.skip("POSIX symlinks")
        from file_organizer.undo.durable_move import sweep

        src = tmp_path / "src.txt"
        src.write_text("src")
        dst = tmp_path / "dst-link.txt"
        # Dangling symlink (target doesn't exist). `dst.exists()` → False,
        # but `os.path.lexists(dst)` → True.
        dst.symlink_to(tmp_path / "nonexistent-target.txt")
        journal = tmp_path / "move.journal"
        _write_journal(
            journal,
            [{"op": "move", "src": str(src), "dst": str(dst), "state": "copied"}],
        )

        sweep(journal)

        # dst still present (the symlink itself); src removed as normal.
        assert dst.is_symlink(), "dangling symlink dst must satisfy the presence check"
        assert not src.exists()
        assert _read_journal(journal) == []

    def test_sweep_ignores_done_entries(self, tmp_path: Path) -> None:
        """``done`` entries were logged for audit/observability but
        are already complete. Sweep leaves src/dst as-is and clears
        the journal."""
        from file_organizer.undo.durable_move import sweep

        journal = tmp_path / "move.journal"
        _write_journal(
            journal,
            [
                {
                    "op": "move",
                    "src": str(tmp_path / "old.txt"),
                    "dst": str(tmp_path / "new.txt"),
                    "state": "done",
                }
            ],
        )

        # Neither path exists on disk — sweep must not raise about
        # missing files on a done entry.
        sweep(journal)
        assert _read_journal(journal) == []

    def test_sweep_retains_failed_entries(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Codex P1 PRRT_kwDOR_Rkws59fwMK: if
        ``_complete_or_rollback`` logs an ``OSError`` and can't
        finish (transient lock / permission denied), sweep must
        retain the entry so the next startup retries. Without this,
        a single failed sweep strands the operation forever.
        """
        from file_organizer.undo.durable_move import sweep

        # Two entries: one that succeeds (done), one that fails on
        # src.unlink during the copied-state reconciliation.
        # (Previously the failing entry was ``started`` + dst.unlink;
        # that scenario no longer applies now that started-state sweep
        # leaves dst alone — codex P1 PRRT_kwDOR_Rkws59gbdD.)
        journal = tmp_path / "move.journal"
        good_src = tmp_path / "good-src.txt"
        good_dst = tmp_path / "good-dst.txt"
        bad_src = tmp_path / "bad-src.txt"
        bad_dst = tmp_path / "bad-dst.txt"
        bad_src.write_text("leftover after copied")
        # bad_dst MUST exist so sweep passes the codex P1
        # PRRT_kwDOR_Rkws59hGWW dst-present check and reaches the
        # src.unlink attempt (which is what the monkeypatched Path.unlink
        # intercepts to simulate an OSError).
        bad_dst.write_text("complete destination")
        _write_journal(
            journal,
            [
                {
                    "op": "move",
                    "src": str(good_src),
                    "dst": str(good_dst),
                    "state": "done",
                },
                {
                    "op": "move",
                    "src": str(bad_src),
                    "dst": str(bad_dst),
                    "state": "copied",
                },
            ],
        )

        real_unlink = Path.unlink

        def failing_unlink(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            if str(self) == str(bad_src):
                raise OSError(13, "simulated permission denied")
            return real_unlink(self, *args, **kwargs)

        monkeypatch.setattr(Path, "unlink", failing_unlink)

        sweep(journal)

        # Failed entry retained for retry.
        entries = _read_journal(journal)
        assert any(e["src"] == str(bad_src) for e in entries), (
            f"failed sweep entry must be retained; journal: {entries}"
        )
        # Successful (done) entry dropped.
        assert not any(e["src"] == str(good_src) for e in entries), (
            "successfully reconciled entry must be dropped"
        )

    def test_sweep_is_idempotent(self, tmp_path: Path) -> None:
        """Sweeping twice is safe — the same retained ``started``
        entry survives both passes without raising. Uses a ``done``
        entry alongside to verify sweep makes progress (drops done,
        retains ambiguous started) on each pass."""
        from file_organizer.undo.durable_move import sweep

        journal = tmp_path / "move.journal"
        src = tmp_path / "src.txt"
        src.write_text("x")
        dst = tmp_path / "dst.txt"
        _write_journal(
            journal,
            [
                # One ambiguous entry retained across sweeps.
                {"op": "move", "src": str(src), "dst": str(dst), "state": "started"},
                # One done entry dropped on first sweep, no-op on second.
                {
                    "op": "move",
                    "src": str(tmp_path / "d_src"),
                    "dst": str(tmp_path / "d_dst"),
                    "state": "done",
                },
            ],
        )

        sweep(journal)
        # After pass 1: started retained, done dropped.
        after_first = _read_journal(journal)
        assert len(after_first) == 1 and after_first[0]["state"] == "started"

        sweep(journal)  # must not raise
        # After pass 2: same started entry still there (still ambiguous).
        after_second = _read_journal(journal)
        assert after_second == after_first, (
            "idempotent sweeps must not accumulate or lose the retained entry"
        )

    def test_sweep_tolerates_missing_files(self, tmp_path: Path) -> None:
        """A journal entry for paths that no longer exist on disk
        doesn't crash the sweep. Uses ``copied`` with dst missing —
        which hits the codex P1 PRRT_kwDOR_Rkws59hGWW guard: the
        entry is RETAINED (not cleared) because unlinking src when
        dst is gone would destroy the last copy. Sweep must not
        raise for the missing files.
        """
        from file_organizer.undo.durable_move import sweep

        src = tmp_path / "gone_src.txt"
        dst = tmp_path / "gone_dst.txt"  # deliberately absent
        journal = tmp_path / "move.journal"
        _write_journal(
            journal,
            [{"op": "move", "src": str(src), "dst": str(dst), "state": "copied"}],
        )

        sweep(journal)  # must not raise

        # Entry retained per codex P1 PRRT_kwDOR_Rkws59hGWW — dst is
        # missing so sweep refuses to unlink src (even though src is
        # also missing here). The retain-on-dst-missing contract is
        # state-based, not content-aware.
        entries = _read_journal(journal)
        assert len(entries) == 1 and entries[0]["state"] == "copied"


# ---------------------------------------------------------------------------
# Atomic failure modes
# ---------------------------------------------------------------------------


class TestDurableMoveFailureModes:
    """Failure modes: missing source, permission errors, crash
    during copy, etc."""

    def test_sweep_unlocked_body_started_retains_entry(self, tmp_path: Path) -> None:
        """``_sweep_unlocked_body`` (Windows/no-fcntl fallback) shares
        the same started-state contract as the locked path: never
        unlink either path AND retain the entry (codex P1
        PRRT_kwDOR_Rkws59gbdD + PRRT_kwDOR_Rkws59g2Ex). Exercised
        directly since the real platform gate uses ``os.name`` at
        module level and can't be cleanly monkeypatched from tests
        (the module captures ``os`` at import time).
        """
        from file_organizer.undo.durable_move import _sweep_unlocked_body

        journal = tmp_path / "move.journal"
        src = tmp_path / "src.txt"
        dst = tmp_path / "dst.txt"
        src.write_text("intact")
        dst.write_text("legitimate pre-existing")
        _write_journal(
            journal,
            [{"op": "move", "src": str(src), "dst": str(dst), "state": "started"}],
        )

        _sweep_unlocked_body(journal)

        # Both paths preserved; entry retained for reconciliation.
        assert src.read_text() == "intact"
        assert dst.read_text() == "legitimate pre-existing"
        entries = _read_journal(journal)
        assert len(entries) == 1 and entries[0]["state"] == "started", (
            f"unlocked sweep must retain started entry; got {entries}"
        )

    def test_sweep_unlocked_body_retains_failed_entry(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``_sweep_unlocked_body`` retains failed entries for retry
        (matches the POSIX-locked path contract). Uses a ``copied``
        entry since started-state reconciliation no longer unlinks
        anything (codex P1 PRRT_kwDOR_Rkws59gbdD).

        Coderabbit round-10: ``bad_dst`` MUST exist on disk so sweep
        passes the codex hGWW dst-present check and reaches the
        ``src.unlink`` attempt — otherwise the dst-missing guard
        retains the entry first and the monkeypatched failing_unlink
        never runs (false-pass).
        """
        from file_organizer.undo.durable_move import _sweep_unlocked_body

        journal = tmp_path / "move.journal"
        bad_src = tmp_path / "bad-src.txt"
        bad_dst = tmp_path / "bad-dst.txt"
        bad_src.write_text("x")
        # bad_dst MUST exist so sweep doesn't short-circuit on the
        # dst-missing guard before reaching the monkeypatched unlink.
        bad_dst.write_text("complete destination")
        _write_journal(
            journal,
            [{"op": "move", "src": str(bad_src), "dst": str(bad_dst), "state": "copied"}],
        )

        real_unlink = Path.unlink
        unlink_calls: list[Path] = []

        def failing_unlink(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            unlink_calls.append(Path(self))
            if str(self) == str(bad_src):
                raise OSError(13, "simulated")
            return real_unlink(self, *args, **kwargs)

        monkeypatch.setattr(Path, "unlink", failing_unlink)

        _sweep_unlocked_body(journal)

        # Verify the failing_unlink path was actually exercised — proves
        # the dst-present guard was passed and the OSError-retain branch
        # is what kept the entry (not the dst-missing short-circuit).
        assert bad_src in unlink_calls, (
            f"failing_unlink must have been invoked on bad_src; "
            f"if absent, the dst-missing guard short-circuited and the "
            f"OSError-retain branch was never tested. Calls: {unlink_calls}"
        )
        entries = _read_journal(journal)
        assert any(e["src"] == str(bad_src) for e in entries)

    def test_sweep_unlocked_body_missing_journal_is_noop(self, tmp_path: Path) -> None:
        """``_sweep_unlocked_body`` returns silently when the journal
        disappears between sweep()'s ``exists()`` check and the
        ``read_text()`` call (TOCTOU race, Codex P2 review finding
        on PR #255).  Simulated by passing a path that doesn't exist."""
        from file_organizer.undo.durable_move import _sweep_unlocked_body

        journal = tmp_path / "vanished.journal"
        # journal never created — simulates the race where the file
        # disappears after exists() but before read_text()
        _sweep_unlocked_body(journal)  # must not raise

    def test_sweep_unlocked_body_size_cap_skips_compaction(self, tmp_path: Path) -> None:
        """``_sweep_unlocked_body`` applies the §6.6 size cap: journals
        larger than _MAX_JOURNAL_SIZE_BYTES emit a WARNING and are not
        compacted (parallel to the locked-body guard)."""
        from file_organizer.undo.durable_move import _sweep_unlocked_body

        journal = tmp_path / "big.journal"
        # Each entry ~4 KiB; 4500 × 4 KiB ≈ 18 MiB > 16 MiB cap.
        entry_line = (
            '{"op":"move","src":"/a","dst":"/b","state":"done","_padding":"' + "x" * 4096 + '"}\n'
        )
        journal.write_text(entry_line * 4500, encoding="utf-8")
        size_before = journal.stat().st_size
        assert size_before > 16 * 1024 * 1024

        with _capture_durable_move_warnings() as records:
            _sweep_unlocked_body(journal)

        assert journal.stat().st_size == size_before, (
            "unlocked sweep must not compact oversized journal"
        )
        assert any("exceeds size cap" in r.getMessage() for r in records), (
            "expected size-cap WARNING in log"
        )

    def test_normalized_path_str_does_not_follow_symlinks(self, tmp_path: Path) -> None:
        """Codex P1 PRRT_kwDOR_Rkws59gRpv: a symlink must journal as
        itself, not its target. Otherwise a crash during the
        post-replace unlink would unlink the target instead of the
        symlink on sweep recovery.
        """
        from file_organizer.undo.durable_move import _normalized_path_str

        target = tmp_path / "target.txt"
        target.write_text("real content")
        link = tmp_path / "link.txt"
        link.symlink_to(target)

        normalized = _normalized_path_str(link)
        # Must preserve the symlink path — NOT resolve to the target.
        # Use normcase for comparison: _normalized_path_str applies normcase
        # (lowercases on Windows), so str(link) and normalized differ in case
        # on Windows even though they point at the same path.
        assert normalized == os.path.normcase(str(link)), (
            f"symlink path normalization must not follow the link; "
            f"got {normalized!r}, expected {os.path.normcase(str(link))!r}"
        )
        assert normalized != os.path.normcase(str(target)), (
            "normalization must not resolve the symlink to its target"
        )
        # Sanity: target's normalized form is still itself.
        assert _normalized_path_str(target) == os.path.normcase(str(target))

    def test_normalized_path_still_resolves_relative_paths(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Normalization still handles the coderabbit
        PRRT_kwDOR_Rkws59fzVv concern: relative / redundant paths
        collapse to the absolute form, even without following
        symlinks."""
        from file_organizer.undo.durable_move import _normalized_path_str

        monkeypatch.chdir(tmp_path)
        # ``./sub/../target.txt`` should collapse to ``<tmp_path>/target.txt``.
        # ``os.path.normcase`` is a no-op on POSIX (where this test runs),
        # so we assert against the exact ``str(tmp_path / "target.txt")``.
        # On Windows the assertion uses normcase on both sides.
        result = _normalized_path_str(Path("./sub/../target.txt"))
        expected = os.path.normcase(str(tmp_path / "target.txt"))
        assert result == expected, result

    def test_normalized_path_case_folds_on_windows(self) -> None:
        """Codex P2 PRRT_kwDOR_Rkws59hp2G: ``_normalized_path_str``
        applies ``os.path.normcase`` so Windows case-insensitive
        paths normalize identically. Without this, a journal entry
        recorded for ``C:\\foo`` and a query for ``c:\\foo`` would
        miss each other and trash GC could delete a path that an
        active rollback move depended on.

        On POSIX, ``os.path.normcase`` is the identity function — we
        verify that contract here so the call is safe on all
        platforms. The Windows case-fold itself is exercised by
        construction of the helper (the call is unconditional).
        """
        from file_organizer.undo.durable_move import _normalized_path_str

        # POSIX no-op contract: a mixed-case path normalizes to itself.
        if os.name != "nt":
            mixed = _normalized_path_str(Path("/Tmp/MixedCase/File.TXT"))
            assert mixed == "/Tmp/MixedCase/File.TXT", (
                "os.path.normcase must be a no-op on POSIX so the wrapper "
                "doesn't break case-sensitive paths"
            )
        else:  # pragma: no cover - exercised on Windows CI only
            # Windows: case-fold to lowercase + normalize separators.
            mixed_a = _normalized_path_str(Path("C:/Foo/Bar.txt"))
            mixed_b = _normalized_path_str(Path("c:/foo/BAR.TXT"))
            assert mixed_a == mixed_b, (
                "Windows case-insensitive paths must normalize identically "
                "(codex hp2G); journal lookups depend on it"
            )

    def test_directory_source_raises_is_a_directory(self, tmp_path: Path) -> None:
        """Coderabbit PRRT_kwDOR_Rkws59fzVo: directory inputs must be
        rejected up front with ``IsADirectoryError``, not silently
        handled differently by the same-device and EXDEV paths.
        """
        from file_organizer.undo.durable_move import durable_move

        src_dir = tmp_path / "src_dir"
        src_dir.mkdir()
        (src_dir / "inside.txt").write_text("x")

        with pytest.raises(IsADirectoryError, match="directory"):
            durable_move(src_dir, tmp_path / "dst", journal=tmp_path / "j")
        # Directory and contents are untouched.
        assert (src_dir / "inside.txt").exists()

    def test_missing_source_raises_file_not_found(self, tmp_path: Path) -> None:
        from file_organizer.undo.durable_move import durable_move

        with pytest.raises(FileNotFoundError):
            durable_move(
                tmp_path / "ghost.txt",
                tmp_path / "dst.txt",
                journal=tmp_path / "j.log",
            )

    def test_non_exdev_os_replace_error_propagates(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Permission errors (or any OSError other than EXDEV) from
        ``os.replace`` on the fast path must propagate to the caller —
        we only fall through to the durable path on EXDEV."""
        from file_organizer.undo.durable_move import durable_move

        def deny_replace(src, dst):  # type: ignore[no-untyped-def]
            raise PermissionError("not allowed")

        monkeypatch.setattr("file_organizer.undo.durable_move.os.replace", deny_replace)

        src = tmp_path / "src.txt"
        src.write_text("x")
        with pytest.raises(PermissionError):
            durable_move(src, tmp_path / "dst.txt", journal=tmp_path / "j")

    def test_copystat_failure_is_non_fatal(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A ``copystat`` failure in the EXDEV path is logged at
        DEBUG and the move still completes with default mode."""
        from file_organizer.undo.durable_move import durable_move

        # Force EXDEV
        def always_exdev(src, dst):  # type: ignore[no-untyped-def]
            raise OSError(errno.EXDEV, "Cross-device link")

        # Sabotage copystat
        def broken_copystat(src, dst, **kwargs):  # type: ignore[no-untyped-def]
            raise OSError("copystat failed")

        real_replace = os.replace
        call_count = {"n": 0}

        def exdev_then_real(src, dst):  # type: ignore[no-untyped-def]
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise OSError(errno.EXDEV, "EXDEV", str(src))
            return real_replace(src, dst)

        monkeypatch.setattr("file_organizer.undo.durable_move.os.replace", exdev_then_real)
        monkeypatch.setattr("file_organizer.undo.durable_move.shutil.copystat", broken_copystat)

        src = tmp_path / "src.txt"
        dst = tmp_path / "dst.txt"
        src.write_text("payload")
        durable_move(src, dst, journal=tmp_path / "j")
        # Move still completed.
        assert dst.read_text() == "payload"
        assert not src.exists()

    def test_exdev_source_already_gone(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """FileNotFoundError from the final source unlink is swallowed
        (source was already gone — treat the move as complete)."""
        from file_organizer.undo.durable_move import durable_move

        real_replace = os.replace
        real_unlink = os.unlink
        call_count = {"replace": 0}

        def exdev_then_real(src, dst):  # type: ignore[no-untyped-def]
            call_count["replace"] += 1
            if call_count["replace"] == 1:
                raise OSError(errno.EXDEV, "EXDEV", str(src))
            return real_replace(src, dst)

        def unlink_missing(p):  # type: ignore[no-untyped-def]
            # Let the temp-file cleanup path go through, but raise
            # FileNotFoundError for the source unlink at the end of
            # _durable_cross_device_move.
            if str(p).endswith("src.txt"):
                raise FileNotFoundError(2, "gone")
            return real_unlink(p)

        monkeypatch.setattr("file_organizer.undo.durable_move.os.replace", exdev_then_real)
        monkeypatch.setattr("file_organizer.undo.durable_move.os.unlink", unlink_missing)

        src = tmp_path / "src.txt"
        dst = tmp_path / "dst.txt"
        src.write_text("payload")
        # Must not raise — source-already-gone is benign.
        durable_move(src, dst, journal=tmp_path / "j")
        assert dst.read_text() == "payload"

    def test_sweep_copied_source_unlink_failure_retained(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """STATE_COPIED + source unlink OSError → entry retained
        (covers the copied-branch failure path symmetric to the
        started-branch one)."""
        from file_organizer.undo.durable_move import _sweep_unlocked_body

        src = tmp_path / "leftover-src.txt"
        dst = tmp_path / "final-dst.txt"
        src.write_text("still here")
        journal = tmp_path / "move.journal"
        _write_journal(
            journal,
            [{"op": "move", "src": str(src), "dst": str(dst), "state": "copied"}],
        )

        real_unlink = Path.unlink

        def deny_unlink(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            if str(self) == str(src):
                raise OSError(13, "denied")
            return real_unlink(self, *args, **kwargs)

        monkeypatch.setattr(Path, "unlink", deny_unlink)

        _sweep_unlocked_body(journal)

        entries = _read_journal(journal)
        assert any(e["src"] == str(src) for e in entries), (
            "copied-state unlink failure must retain entry"
        )

    def test_read_journal_drops_malformed_lines(self, tmp_path: Path) -> None:
        """Lines that can't parse as JSON, or parse as the wrong
        shape, are logged + dropped (not treated as valid entries).

        Coderabbit PRRT_kwDOR_Rkws59gscQ: the production helper
        returns typed ``_JournalEntry`` objects while the local test
        helper of the same name returns ``list[dict]``. Alias the
        import so the two call sites can't be confused.
        """
        from file_organizer.undo.durable_move import _read_journal as _prod_read_journal

        journal = tmp_path / "corrupt.journal"
        journal.write_text(
            "\n".join(
                [
                    "not json at all",
                    json.dumps({"op": "move"}),  # missing fields
                    json.dumps({"op": "move", "src": 1, "dst": "x", "state": "done"}),  # wrong type
                    json.dumps({"op": "move", "src": "a", "dst": "b", "state": "done"}),  # ok
                ]
            )
            + "\n"
        )
        entries = _prod_read_journal(journal)
        assert len(entries) == 1
        assert entries[0].state == "done"

    def test_crash_between_started_and_copied_leaves_recoverable_state(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Simulate crash during EXDEV copy: raise an exception from
        the copy step after the journal has been written. The journal
        must retain the ``started`` entry so sweep can clean up."""
        from file_organizer.undo.durable_move import durable_move

        # Force EXDEV then make the copy fail.
        def always_exdev(src, dst):  # type: ignore[no-untyped-def]
            raise OSError(errno.EXDEV, "Cross-device link", str(src))

        monkeypatch.setattr("file_organizer.undo.durable_move.os.replace", always_exdev)

        def bad_copyfile(src, dst, *args, **kwargs):  # type: ignore[no-untyped-def]
            raise OSError("simulated copy crash")

        monkeypatch.setattr("file_organizer.undo.durable_move.shutil.copyfile", bad_copyfile)

        src = tmp_path / "src.txt"
        dst = tmp_path / "dst.txt"
        src.write_text("payload")
        journal = tmp_path / "move.journal"

        with pytest.raises(OSError, match="simulated copy crash"):
            durable_move(src, dst, journal=journal)

        # Journal must have a started entry so sweep can clean up.
        entries = _read_journal(journal)
        assert any(e["state"] == "started" for e in entries), (
            f"started entry must persist after copy crash; got {entries}"
        )


# ---------------------------------------------------------------------------
# Round-3 P1 regression tests
# ---------------------------------------------------------------------------


class TestStartedStateDoesNotUnlinkDestination:
    """Codex P1 PRRT_kwDOR_Rkws59gbdD.

    Belt-and-suspenders coverage for the started-state invariant:
    ``sweep`` must never unlink ``dst`` when reconciling a ``started``
    entry, because the EXDEV path writes the journal BEFORE the copy
    begins. ``dst`` may be a legitimate pre-existing file that our
    transaction never touched.
    """

    def test_started_sweep_preserves_dst_contents_byte_for_byte(self, tmp_path: Path) -> None:
        """Detailed byte-equality check — not just ``dst.exists()``.

        Guards against future "clever" rollback logic that might,
        say, truncate dst to zero instead of unlinking it.
        """
        from file_organizer.undo.durable_move import sweep

        src = tmp_path / "src.txt"
        dst = tmp_path / "dst.txt"
        src.write_bytes(b"source bytes")
        original_dst_bytes = b"pre-existing dst content \x00 with \xff NUL + binary"
        dst.write_bytes(original_dst_bytes)
        journal = tmp_path / "move.journal"
        _write_journal(
            journal,
            [{"op": "move", "src": str(src), "dst": str(dst), "state": "started"}],
        )

        sweep(journal)

        assert dst.read_bytes() == original_dst_bytes, (
            "started-state sweep must preserve dst byte-for-byte "
            "(codex P1 PRRT_kwDOR_Rkws59gbdD data-loss path)"
        )
        assert src.read_bytes() == b"source bytes"

    def test_started_sweep_tolerates_absent_dst(self, tmp_path: Path) -> None:
        """If dst never existed (common case), sweep still doesn't
        raise. Entry is retained (same ambiguity class as the
        dst-exists case; codex P1 PRRT_kwDOR_Rkws59g2Ex) so operator
        or retry can reconcile.
        """
        from file_organizer.undo.durable_move import sweep

        src = tmp_path / "src.txt"
        src.write_text("x")
        dst = tmp_path / "never_existed.txt"  # deliberately absent
        journal = tmp_path / "move.journal"
        _write_journal(
            journal,
            [{"op": "move", "src": str(src), "dst": str(dst), "state": "started"}],
        )

        sweep(journal)  # must not raise

        assert src.read_text() == "x"
        assert not dst.exists()
        # Retained for reconciliation (same invariant as dst-exists case).
        entries = _read_journal(journal)
        assert len(entries) == 1 and entries[0]["state"] == "started"

    def test_started_entry_persists_across_multiple_sweeps(self, tmp_path: Path) -> None:
        """Codex P1 PRRT_kwDOR_Rkws59g2Ex: a ``started`` entry is
        AMBIGUOUS — we don't know if ``os.replace`` completed before
        the crash. Sweep retains it so the next startup (or a retry
        that logs new started/copied/done) can supersede it. The
        entry must NEVER silently disappear across sweeps.
        """
        from file_organizer.undo.durable_move import sweep

        src = tmp_path / "ambig-src.txt"
        dst = tmp_path / "ambig-dst.txt"
        src.write_text("src")
        dst.write_text("dst")
        journal = tmp_path / "move.journal"
        _write_journal(
            journal,
            [{"op": "move", "src": str(src), "dst": str(dst), "state": "started"}],
        )

        # Sweep 5 times; entry must survive every pass.
        for pass_num in range(5):
            sweep(journal)
            entries = _read_journal(journal)
            assert len(entries) == 1 and entries[0]["state"] == "started", (
                f"pass {pass_num}: started entry must survive every sweep; got {entries}"
            )

        # A later successful retry supersedes the started entry with
        # copied/done; sweep then drops the stale record.
        _write_journal(
            journal,
            [
                {"op": "move", "src": str(src), "dst": str(dst), "state": "started"},
                {"op": "move", "src": str(src), "dst": str(dst), "state": "done"},
            ],
        )
        sweep(journal)
        assert _read_journal(journal) == [], (
            "a later done entry for the same (src,dst) must supersede the ambiguous started record"
        )


class TestAppendJournalFlockCoordination:
    """Codex P1 PRRT_kwDOR_Rkws59gbdH.

    ``sweep()`` holds ``fcntl.flock(LOCK_EX)`` during the read-
    modify-truncate cycle. ``_append_journal`` MUST acquire the same
    advisory lock before writing — otherwise sweep can truncate away
    a freshly-appended ``started`` record, losing crash-recovery
    metadata.
    """

    def test_append_journal_blocks_while_sweep_holds_flock(self, tmp_path: Path) -> None:
        """Core invariant: an ``_append_journal`` call issued while
        sweep (or any other holder) has ``LOCK_EX`` on the journal's
        lock file blocks until the lock is released. Proves the appender
        respects the same advisory lock sweep uses.

        Step 4 update: lock subject is ``<journal>.lock`` (stable
        inode), not ``<journal>`` itself. Pre-step-4 this test held
        ``LOCK_EX`` on the journal file directly.
        """
        fcntl = pytest.importorskip("fcntl")
        import threading
        import time

        from file_organizer.undo.durable_move import _append_journal, _lock_path

        journal = tmp_path / "move.journal"
        # Pre-create empty journal + empty lock file. Journal stays
        # empty so the downstream "exactly 1 appended line" assertion
        # holds; lock file gets the held LOCK_EX below.
        journal.write_text("")
        lock = _lock_path(journal)
        lock.touch()

        # Acquire LOCK_EX on the LOCK FILE in the main thread — mimics
        # sweep holding the lock during its read-modify-write cycle.
        holder = open(lock, "r+", encoding="utf-8")
        fcntl.flock(holder.fileno(), fcntl.LOCK_EX)

        # ``appender_entered`` is set IMMEDIATELY before the
        # _append_journal call — eliminates the coderabbit
        # PRRT_kwDOR_Rkws59gscT false-positive path where a slow CI
        # runner just never scheduled the appender thread within the
        # timeout. If this event fires then the remaining
        # ``append_done.wait(...)`` is a real invariant: thread is
        # running, is about to flock, MUST block on LOCK_EX.
        appender_entered = threading.Event()
        append_done = threading.Event()
        append_error: list[BaseException] = []

        def _appender() -> None:
            appender_entered.set()
            try:
                _append_journal(
                    journal,
                    {"op": "move", "src": "/a", "dst": "/b", "state": "started"},
                )
            except BaseException as exc:  # pragma: no cover - failure surface
                append_error.append(exc)
            finally:
                append_done.set()

        t = threading.Thread(target=_appender, daemon=True)
        t.start()

        # Confirm the appender thread actually ran — disambiguates
        # "blocked on flock" (intended) from "never scheduled"
        # (false pass on shared CI runners).
        assert appender_entered.wait(timeout=5.0), (
            "appender thread never scheduled — test environment issue"
        )

        # Thread reached _append_journal and is now in (or about to
        # enter) the open() + flock() sequence. Without flock
        # coordination it would finish in microseconds; with flock,
        # it blocks on LOCK_EX while our holder still has it.
        assert not append_done.wait(timeout=0.5), (
            "_append_journal must block while another holder has LOCK_EX "
            "(codex P1 PRRT_kwDOR_Rkws59gbdH)"
        )
        # Journal still empty — appender has not written its line.
        assert journal.read_text() == ""

        # Release the lock; appender should now complete promptly.
        fcntl.flock(holder.fileno(), fcntl.LOCK_UN)
        holder.close()
        assert append_done.wait(timeout=5.0), "appender never completed after flock release"
        t.join(timeout=2.0)
        assert append_error == [], f"appender raised: {append_error}"

        # Allow a brief moment for the append to flush (fsync is
        # synchronous, but scheduling can vary on shared CI runners).
        deadline = time.monotonic() + 2.0
        lines: list[str] = []
        while time.monotonic() < deadline:
            lines = [line for line in journal.read_text().splitlines() if line]
            if lines:
                break
        assert len(lines) == 1, f"expected 1 appended line, got {lines}"
        assert '"state": "started"' in lines[0]

    def test_append_journal_writes_when_no_holder(self, tmp_path: Path) -> None:
        """Baseline: with no competing lock holder, the flock-aware
        appender still writes the line + flushes + fsyncs (i.e. the
        non-blocking path works)."""
        pytest.importorskip("fcntl")

        from file_organizer.undo.durable_move import _append_journal

        journal = tmp_path / "move.journal"
        _append_journal(journal, {"op": "move", "src": "/x", "dst": "/y", "state": "done"})

        lines = [line for line in journal.read_text().splitlines() if line]
        assert len(lines) == 1
        assert '"state": "done"' in lines[0]


# ---------------------------------------------------------------------------
# Round-10 regression tests
# ---------------------------------------------------------------------------


class TestDirectoryMoveCoordination:
    """Coderabbit round-10 (Major): directory restores previously
    bypassed the F8 coordination channel — ``shutil.move`` doesn't
    write to the journal, so concurrent trash GC could delete a
    directory mid-restore. ``directory_move`` wraps the call in
    ``op="dir_move"`` started/done entries so
    :func:`is_path_in_flight` sees the path as in-flight.
    """

    def test_directory_move_writes_started_done_pair(self, tmp_path: Path) -> None:
        """The wrapper writes exactly two journal entries: started
        before the move, done after."""
        from file_organizer.undo.durable_move import directory_move

        src = tmp_path / "src_dir"
        src.mkdir()
        (src / "inside.txt").write_text("content")
        dst = tmp_path / "dst_dir"
        journal = tmp_path / "move.journal"

        directory_move(src, dst, journal=journal)

        # Move completed.
        assert dst.is_dir() and (dst / "inside.txt").read_text() == "content"
        assert not src.exists()
        # Journal contains exactly the started → done pair.
        entries = _read_journal(journal)
        assert len(entries) == 2
        assert entries[0]["op"] == "dir_move"
        assert entries[0]["state"] == "started"
        assert entries[1]["op"] == "dir_move"
        assert entries[1]["state"] == "done"

    def test_directory_move_marks_path_in_flight_during_move(self, tmp_path: Path) -> None:
        """Codex hdFb / coderabbit round-10: while
        :func:`directory_move` is mid-shutil.move, both src and dst
        must register as in-flight via :func:`is_path_in_flight`.
        Without this, trash GC could delete src or dst between the
        started entry and the move's completion.

        Implementation note — deterministic synchronisation:
        The original spin-loop was racy on py3.12 fast runners: if the
        GIL handed the move thread enough time to complete
        ``directory_move`` before the observer thread was ever scheduled,
        ``move_done`` was already set and the observer exited with
        ``False``.

        Fix: patch ``undo.durable_move.shutil.move`` so that the real
        filesystem move pauses at the point *after* the "started" journal
        entry is written but *before* bytes are copied on disk.  Two
        events (``move_entered``, ``observer_done``) create a
        rendezvous:

        1. Patched move fires ``move_entered``  ← started entry is
           already committed at this point.
        2. Observer wakes, checks ``is_path_in_flight`` — must be True.
        3. Observer fires ``observer_done``.
        4. Patched move proceeds with the real ``shutil.move``.

        This is fully deterministic regardless of thread scheduling.
        """
        import shutil as _shutil
        import threading
        from unittest.mock import patch

        from file_organizer.undo.durable_move import directory_move, is_path_in_flight

        src = tmp_path / "src_dir"
        src.mkdir()
        for i in range(5):
            (src / f"file_{i}.txt").write_text("x" * 64)
        dst = tmp_path / "dst_dir"
        journal = tmp_path / "move.journal"

        move_entered = threading.Event()
        observer_done = threading.Event()
        observations: list[bool] = []

        # Capture the real shutil.move BEFORE patching so _hooked_move
        # does not recurse (both _shutil and undo.durable_move.shutil
        # point at the same module object; patching one patches both).
        _real_move = _shutil.move

        def _hooked_move(*args: object, **kwargs: object) -> object:
            # ``_append_journal(journal, {state: started})`` has already
            # run before shutil.move is called — signal the observer.
            move_entered.set()
            # Wait for observer to sample before the move completes and
            # the "done" entry overwrites the "started" entry.
            # observer_done is guaranteed to be set via finally in observer,
            # so this will not block forever even if the observer raises.
            observer_done.wait(timeout=5)
            return _real_move(*args, **kwargs)  # type: ignore[arg-type]

        def observer() -> None:
            try:
                # If move_entered times out the rendezvous is broken;
                # record False so the main assertion fails with a clear
                # message rather than an IndexError on an empty list.
                if move_entered.wait(timeout=5):
                    result = is_path_in_flight(src, journal=journal) or is_path_in_flight(
                        dst, journal=journal
                    )
                    observations.append(result)
                else:
                    observations.append(False)
            finally:
                # Always release _hooked_move so the patched move is
                # never stuck waiting until its own timeout.
                observer_done.set()

        t = threading.Thread(target=observer, daemon=True)
        t.start()
        with patch("file_organizer.undo.durable_move.shutil.move", _hooked_move):
            directory_move(src, dst, journal=journal)
        t.join(timeout=5)
        assert not t.is_alive(), "observer thread did not terminate within 5 seconds"

        assert observations and observations[0] is True, (
            "is_path_in_flight must see the directory as in-flight while "
            "directory_move is running (round-10 F8 coordination)"
        )
        # After the move completes the in-flight marker is cleared
        # (done entry supersedes started).
        assert is_path_in_flight(src, journal=journal) is False
        assert is_path_in_flight(dst, journal=journal) is False

    def test_directory_move_writes_done_even_if_move_fails(self, tmp_path: Path) -> None:
        """If shutil.move raises, the wrapper still writes ``done`` so
        the in-flight marker is released. The exception propagates;
        callers must reconcile partial on-disk state themselves
        (directory moves are non-recoverable from sweep)."""
        from file_organizer.undo.durable_move import directory_move, is_path_in_flight

        src = tmp_path / "src_dir"
        src.mkdir()
        (src / "f.txt").write_text("x")
        # Use a path that shutil.move will reject (parent doesn't
        # exist would normally be created by us, so use a destination
        # under a file).
        blocker = tmp_path / "blocker"
        blocker.write_text("not a dir")
        dst = blocker / "child" / "dst_dir"
        journal = tmp_path / "move.journal"

        with pytest.raises((OSError, FileNotFoundError, NotADirectoryError)):
            directory_move(src, dst, journal=journal)

        # done was still written (released in-flight marker).
        entries = _read_journal(journal)
        assert any(e["state"] == "done" for e in entries), (
            f"directory_move must write done in the finally block even when "
            f"shutil.move raises; got entries: {entries}"
        )
        assert is_path_in_flight(src, journal=journal) is False


class TestSweepDirMoveHandling:
    """Sweep handles ``op="dir_move"`` entries by dropping them
    (with a warning if state != done). Move semantics MUST NOT
    apply since shutil.move is non-atomic and non-idempotent.
    """

    def test_sweep_drops_dir_move_done(self, tmp_path: Path) -> None:
        from file_organizer.undo.durable_move import sweep

        src = tmp_path / "src_dir"
        src.mkdir()
        dst = tmp_path / "dst_dir"
        journal = tmp_path / "move.journal"
        _write_journal(
            journal,
            [{"op": "dir_move", "src": str(src), "dst": str(dst), "state": "done"}],
        )

        sweep(journal)
        assert _read_journal(journal) == []
        # Disk state untouched.
        assert src.is_dir() and not dst.exists()

    def test_sweep_drops_dir_move_started_with_warning(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A stranded ``dir_move`` started entry (move crashed) is
        dropped — sweep can't safely retry shutil.move. The warning
        prompts operator inspection of the on-disk state."""
        from file_organizer.undo.durable_move import sweep

        src = tmp_path / "src_dir"
        src.mkdir()
        dst = tmp_path / "dst_dir"
        journal = tmp_path / "move.journal"
        _write_journal(
            journal,
            [{"op": "dir_move", "src": str(src), "dst": str(dst), "state": "started"}],
        )

        with caplog.at_level("WARNING", logger="file_organizer.undo.durable_move"):
            sweep(journal)
        # Entry dropped (in-flight marker released).
        assert _read_journal(journal) == []
        # Disk state is whatever shutil.move left it — sweep doesn't
        # touch either path. We just verify the warning fired.
        assert any("dir_move entry" in r.getMessage() for r in caplog.records), (
            f"warning must mention the dir_move entry; got "
            f"{[r.getMessage() for r in caplog.records]}"
        )

    def test_sweep_drops_dir_move_done_silently(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """§5.3 / §9.5 lock-in: ``dir_move done`` is dropped silently
        (no WARNING). Started entries warn so operators investigate
        the on-disk state; done entries are routine coordination
        completion and don't need operator attention."""
        from file_organizer.undo.durable_move import sweep

        src = tmp_path / "src_dir"
        src.mkdir()
        dst = tmp_path / "dst_dir"
        journal = tmp_path / "move.journal"
        _write_journal(
            journal,
            [{"op": "dir_move", "src": str(src), "dst": str(dst), "state": "done"}],
        )

        with caplog.at_level("WARNING", logger="file_organizer.undo.durable_move"):
            sweep(journal)

        assert _read_journal(journal) == []
        # No WARNING-level records about dir_move from sweep — only
        # filter for sweep messages mentioning dir_move so other
        # subsystem warnings (if any) don't cause spurious failures.
        sweep_warnings = [
            r
            for r in caplog.records
            if r.levelname == "WARNING"
            and "dir_move" in r.getMessage()
            and r.name == "file_organizer.undo.durable_move"
        ]
        assert sweep_warnings == [], (
            "dir_move done must drop SILENTLY (§5.3); WARNING is reserved "
            f"for non-done states. Observed: {[r.getMessage() for r in sweep_warnings]}"
        )

    def test_sweep_does_not_apply_move_semantics_to_dir_move(self, tmp_path: Path) -> None:
        """A ``dir_move`` entry in a ``copied`` state must NOT trigger
        ``src.unlink`` (move-semantics for op=move). Belt-and-
        suspenders against a future refactor accidentally collapsing
        the op-dispatch."""
        from file_organizer.undo.durable_move import sweep

        src = tmp_path / "must-survive.txt"
        src.write_text("must not be unlinked")
        dst = tmp_path / "elsewhere.txt"
        dst.write_text("dst content")
        journal = tmp_path / "move.journal"
        # Synthetic: copied state on a dir_move op shouldn't appear
        # in practice (dir_move only writes started/done) but the
        # sweep code path must defend against it.
        _write_journal(
            journal,
            [{"op": "dir_move", "src": str(src), "dst": str(dst), "state": "copied"}],
        )

        sweep(journal)

        assert src.read_text() == "must not be unlinked", (
            "dir_move must NEVER trigger src.unlink even in unexpected states"
        )
        assert dst.read_text() == "dst content"


class TestIsPathInFlightSharedLock:
    """Codex P2 PRRT_kwDOR_Rkws59ir1P: ``is_path_in_flight`` must
    acquire ``LOCK_SH`` so it cannot return False while a writer is
    mid-append. Without this, F8 trash GC can delete a path that's
    about to be marked in-flight.
    """

    def test_is_path_in_flight_blocks_while_writer_holds_lock_ex(self, tmp_path: Path) -> None:
        """Hold ``LOCK_EX`` on the LOCK FILE from main thread; the
        reader thread's ``is_path_in_flight`` call must block until
        the lock is released.

        Step 4 update: lock subject is ``<journal>.lock`` (stable
        inode), not ``<journal>`` itself. Pre-step-4 this test held
        ``LOCK_EX`` on the journal file directly — that no longer
        coordinates with readers/writers under the new protocol.
        """
        fcntl = pytest.importorskip("fcntl")
        import threading

        from file_organizer.undo.durable_move import _append_journal, _lock_path, is_path_in_flight

        journal = tmp_path / "move.journal"
        # Pre-populate so the lock file exists for the holder's open().
        _append_journal(journal, {"op": "move", "src": "/a", "dst": "/b", "state": "done"})

        # Hold LOCK_EX on the LOCK FILE from the main thread (simulates
        # an active _append_journal mid-write).
        holder = open(_lock_path(journal), "a", encoding="utf-8")
        fcntl.flock(holder.fileno(), fcntl.LOCK_EX)

        reader_entered = threading.Event()
        reader_done = threading.Event()
        result_holder: list[bool | None] = [None]

        def _reader() -> None:
            reader_entered.set()
            try:
                result_holder[0] = is_path_in_flight(Path("/x"), journal=journal)
            finally:
                reader_done.set()

        t = threading.Thread(target=_reader, daemon=True)
        t.start()

        assert reader_entered.wait(timeout=5.0), "reader never scheduled"
        # Reader must block on LOCK_SH while we hold LOCK_EX.
        assert not reader_done.wait(timeout=0.5), (
            "is_path_in_flight must block while another holder has LOCK_EX "
            "(codex P2 PRRT_kwDOR_Rkws59ir1P); without the shared lock, GC "
            "could observe a stale journal mid-append and delete an "
            "in-flight path."
        )

        # Release; reader should now complete.
        fcntl.flock(holder.fileno(), fcntl.LOCK_UN)
        holder.close()
        assert reader_done.wait(timeout=5.0), "reader never completed"
        t.join(timeout=2)
        # Result is False because /x is not in the (single done) entry.
        assert result_holder[0] is False


# ---------------------------------------------------------------------------
# F7.1 journal schema v2 — parser + rejection-rule coverage
# (tracks #201, docs/internal/F7-1-journal-protocol-design.md §4, §9.1)
# ---------------------------------------------------------------------------


class TestJournalSchemaV2Parser:
    """F7.1 step 1: parser accepts v1 and v2 records, preserves unknown-op
    raw lines, and rejects each §4.1 malformed case with a WARNING log.
    """

    def test_v1_record_no_schema_field_accepted(self, tmp_path: Path) -> None:
        """A v1 record (no ``schema`` field) must still parse — PR #197
        back-compat. The resulting entry has ``schema == 1``, ``op_id is
        None``, ``tmp_path is None``."""
        from file_organizer.undo.durable_move import _parse_journal_text

        line = json.dumps({"op": "move", "src": "/a", "dst": "/b", "state": "done"})
        entries = _parse_journal_text(line + "\n")

        assert len(entries) == 1
        e = entries[0]
        assert e.op == "move"
        assert e.src == "/a"
        assert e.dst == "/b"
        assert e.state == "done"
        assert e.schema == 1
        assert e.op_id is None
        assert e.tmp_path is None

    def test_v2_known_op_record_round_trips(self, tmp_path: Path) -> None:
        """v2 record with all known-op fields round-trips through parse →
        serialize → parse and preserves every field."""
        from file_organizer.undo.durable_move import _parse_journal_text, _serialize_entry

        src = str(tmp_path / "source.txt")
        dst = str(tmp_path / "dest.txt")
        tmp = str(tmp_path / "tmp-file.tmp")
        src_line = json.dumps(
            {
                "schema": 2,
                "op": "move",
                "op_id": "abc123",
                "src": src,
                "dst": dst,
                "state": "started",
                "tmp_path": tmp,
                "ts": 1714000000.5,
                "host_pid": 12345,
            }
        )
        parsed = _parse_journal_text(src_line + "\n")
        assert len(parsed) == 1
        e = parsed[0]
        assert e.schema == 2
        assert e.op_id == "abc123"
        assert e.tmp_path == tmp
        assert e.ts == 1714000000.5
        assert e.host_pid == 12345

        # Re-parse the serialized form — must produce an identical entry.
        reparsed = _parse_journal_text(_serialize_entry(e) + "\n")
        assert len(reparsed) == 1
        assert reparsed[0] == e

    def test_non_object_json_rejected(self, tmp_path: Path) -> None:
        """§4.1 rule 2 (codex iy4w): JSON that parses but isn't an object
        (null, list, scalar, string) is logged + skipped, not AttributeError.
        Covers BOTH ``_parse_journal_text`` AND ``_read_journal`` — the
        round-8 fix missed ``_read_journal`` per the #201 body."""
        from file_organizer.undo.durable_move import _parse_journal_text, _read_journal

        corrupt = "\n".join(
            [
                "null",
                "[]",
                '"bare string"',
                "42",
                json.dumps({"op": "move", "src": "/a", "dst": "/b", "state": "done"}),
            ]
        )
        journal = tmp_path / "corrupt.journal"
        journal.write_text(corrupt + "\n")

        # Parser via text: 4 rejects + 1 accept.
        via_text = _parse_journal_text(corrupt)
        assert len(via_text) == 1
        assert via_text[0].op == "move"

        # Parser via file: same contract, no AttributeError from the
        # pre-F7.1 _read_journal missing-dict-guard bug.
        via_file = _read_journal(journal)
        assert len(via_file) == 1
        assert via_file[0].op == "move"

    def test_missing_required_field_rejected(self) -> None:
        """§4.1 rule 3: missing op/src/dst/state logged + skipped."""
        from file_organizer.undo.durable_move import _parse_journal_text

        corrupt = "\n".join(
            [
                json.dumps({"op": "move"}),  # missing src, dst, state
                json.dumps({"src": "/a", "dst": "/b", "state": "done"}),  # missing op
                json.dumps({"op": "move", "src": "/a"}),  # missing dst, state
                json.dumps({"op": "move", "src": "/a", "dst": "/b", "state": "done"}),  # ok
            ]
        )
        entries = _parse_journal_text(corrupt + "\n")
        assert len(entries) == 1
        assert entries[0].op == "move"

    def test_oversized_line_rejected(self) -> None:
        """§4.1 rule 7: line >64 KiB rejected to prevent pathological payloads."""
        from file_organizer.undo.durable_move import _parse_journal_text

        good = json.dumps({"op": "move", "src": "/a", "dst": "/b", "state": "done"})
        huge = json.dumps(
            {
                "op": "move",
                "src": "/a",
                "dst": "/b",
                "state": "done",
                "_padding": "x" * (65 * 1024),
            }
        )
        entries = _parse_journal_text(huge + "\n" + good + "\n")
        assert len(entries) == 1
        assert entries[0].src == "/a"

    def test_v2_known_op_missing_op_id_rejected(self) -> None:
        """§4.1 rule 8: v2 writer always emits op_id; a known-op v2 record
        missing it is corrupt/external input and MUST be rejected (not
        silently collapsed with v1 identity)."""
        from file_organizer.undo.durable_move import _parse_journal_text

        corrupt = json.dumps(
            {
                "schema": 2,
                "op": "move",
                # op_id missing — parse-time reject
                "src": "/a",
                "dst": "/b",
                "state": "done",
            }
        )
        ok = json.dumps(
            {
                "schema": 2,
                "op": "move",
                "op_id": "legit",
                "src": "/c",
                "dst": "/d",
                "state": "done",
            }
        )
        entries = _parse_journal_text(corrupt + "\n" + ok + "\n")
        assert len(entries) == 1
        assert entries[0].op_id == "legit"

    def test_v2_move_started_missing_tmp_path_rejected(self) -> None:
        """§4.1 rule 9: v2 ``move started`` without ``tmp_path`` is
        rejected — the tmp-exists invariant (§7.1) depends on every
        such record carrying the field. Without it sweep could
        misinfer post-replace and unlink src (data loss)."""
        from file_organizer.undo.durable_move import _parse_journal_text

        corrupt = json.dumps(
            {
                "schema": 2,
                "op": "move",
                "op_id": "abc",
                "src": "/a",
                "dst": "/b",
                "state": "started",
                # tmp_path missing — parse-time reject for v2 move started
            }
        )
        # Same record but copied/done — no tmp_path required.
        ok_copied = json.dumps(
            {
                "schema": 2,
                "op": "move",
                "op_id": "def",
                "src": "/c",
                "dst": "/d",
                "state": "copied",
            }
        )
        entries = _parse_journal_text(corrupt + "\n" + ok_copied + "\n")
        assert len(entries) == 1
        assert entries[0].state == "copied"

    def test_unknown_op_preserves_raw_line(self) -> None:
        """§4.2: unknown-op records preserve the FULL raw JSON line on
        ``_raw`` so compaction re-serializes them verbatim. A future
        binary with a handler for the op receives all fields the writer
        persisted, NOT just the v2 parser's known core."""
        from file_organizer.undo.durable_move import _parse_journal_text, _serialize_entry

        future_record = {
            "schema": 3,
            "op": "future_copy",
            "op_id": "xyz",
            "src": "/a",
            "dst": "/b",
            "state": "started",
            "future_field_1": "content-hash-abc",
            "future_field_2": {"nested": [1, 2, 3]},
        }
        raw_line = json.dumps(future_record)
        entries = _parse_journal_text(raw_line + "\n")

        assert len(entries) == 1
        e = entries[0]
        assert e.op == "future_copy"
        assert e._raw == raw_line

        # Compaction writes the entry back — must equal the original
        # raw line, NOT a v2-projected subset.
        serialized = _serialize_entry(e)
        # Allow for whitespace/key-ordering differences via re-parse.
        assert json.loads(serialized) == future_record

    def test_known_op_unknown_future_field_ignored(self) -> None:
        """§4.2: for KNOWN ops, extra JSON fields are ignored (no _raw).
        Those ops have a stable schema we control; extras are noise."""
        from file_organizer.undo.durable_move import _parse_journal_text

        line = json.dumps(
            {
                "schema": 2,
                "op": "move",
                "op_id": "abc",
                "src": "/a",
                "dst": "/b",
                "state": "done",
                "experimental_field": "should-be-dropped",
            }
        )
        entries = _parse_journal_text(line + "\n")
        assert len(entries) == 1
        # Known-op entries don't retain _raw — field is a clean None.
        assert entries[0]._raw is None

    def test_malformed_json_still_rejected(self) -> None:
        """§4.1 rule 1: JSON parse errors logged + skipped (pre-F7.1
        behavior preserved)."""
        from file_organizer.undo.durable_move import _parse_journal_text

        corrupt = "\n".join(
            [
                "not json at all",
                "{broken",
                json.dumps({"op": "move", "src": "/a", "dst": "/b", "state": "done"}),
            ]
        )
        entries = _parse_journal_text(corrupt + "\n")
        assert len(entries) == 1

    def test_hash16_is_stable(self) -> None:
        """``_hash16`` (§3.1 rule 4) is stable: same input → same output.
        Used for unknown-op collapse-key identity so future ops don't
        silently conflate."""
        from file_organizer.undo.durable_move import _hash16

        raw = '{"op":"future","op_id":"x","src":"/a","dst":"/b","state":"done"}'
        h = _hash16(raw)
        assert len(h) == 16
        assert _hash16(raw) == h  # deterministic
        # Different content → different hash.
        assert _hash16(raw.replace('"done"', '"started"')) != h


# ---------------------------------------------------------------------------
# F7.1 step 5: atomic journal compaction
# (tracks #201, docs/internal/F7-1-journal-protocol-design.md §6.2–6.6)
# ---------------------------------------------------------------------------


class TestAtomicCompaction:
    """Step 5 / coderabbit round-10 major: sweep no longer truncates the
    live journal. Instead it writes retained entries to a compact-tmp,
    fsyncs, then ``os.replace``s the journal — atomic on POSIX. A
    crash mid-compaction leaves either the OLD journal intact OR the
    NEW journal complete; never a zero-bytes-with-pending-entries state.
    """

    def test_compaction_replaces_journal_via_tmp_not_truncate(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Sweep with retained entries must use ``os.replace`` (the
        compact-tmp path), not ``fh.truncate`` on the live journal."""
        from file_organizer.undo.durable_move import _append_journal, sweep

        journal = tmp_path / "move.journal"
        # Two entries: one will be retained (copied + dst missing), one will be
        # dropped (done).
        src_keep = tmp_path / "kept-src.txt"
        src_keep.write_text("x")
        dst_missing = tmp_path / "missing-dst.txt"  # deliberately absent
        _append_journal(
            journal,
            {"op": "move", "src": str(src_keep), "dst": str(dst_missing), "state": "copied"},
        )
        _append_journal(journal, {"op": "move", "src": "/a", "dst": "/b", "state": "done"})

        # Track os.replace calls — must be invoked at least once with
        # the compact-tmp → journal swap.
        replace_calls: list[tuple[str, str]] = []
        real_replace = os.replace

        def tracking_replace(src, dst):  # type: ignore[no-untyped-def]
            replace_calls.append((str(src), str(dst)))
            return real_replace(src, dst)

        monkeypatch.setattr("file_organizer.undo.durable_move.os.replace", tracking_replace)

        # Inode change is the observable proof of replace (vs in-place
        # truncate, which would preserve inode).
        journal_inode_before = journal.stat().st_ino

        sweep(journal)

        replace_targets = [dst for _src, dst in replace_calls]
        assert str(journal) in replace_targets, (
            f"sweep must os.replace the journal as part of compaction; "
            f"replace calls were: {replace_calls}"
        )
        assert journal.stat().st_ino != journal_inode_before, (
            "journal inode must change post-compaction (proof of os.replace, not in-place truncate)"
        )
        from file_organizer.undo.durable_move import _read_journal

        entries = _read_journal(journal)
        assert len(entries) == 1
        assert entries[0].src == str(src_keep)

    def test_compaction_crash_mid_replace_preserves_journal(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Step 5 crash safety: if ``os.replace`` raises (simulated
        mid-compaction crash), the original journal content survives
        intact — no zero-bytes-with-pending-entries window."""
        from file_organizer.undo.durable_move import _append_journal, sweep

        journal = tmp_path / "move.journal"
        src_keep = tmp_path / "src.txt"
        src_keep.write_text("x")
        dst_missing = tmp_path / "missing.txt"
        _append_journal(
            journal,
            {"op": "move", "src": str(src_keep), "dst": str(dst_missing), "state": "copied"},
        )
        _append_journal(journal, {"op": "move", "src": "/a", "dst": "/b", "state": "done"})
        original_content = journal.read_text()
        original_lines = [line for line in original_content.splitlines() if line]
        assert len(original_lines) == 2

        # Simulate crash: os.replace raises mid-compaction.
        def failing_replace(src, dst):  # type: ignore[no-untyped-def]
            raise OSError(28, "simulated disk full mid-replace")

        monkeypatch.setattr("file_organizer.undo.durable_move.os.replace", failing_replace)

        with pytest.raises(OSError, match="simulated"):
            sweep(journal)

        # Journal content unchanged — both original entries survive.
        post_crash = journal.read_text()
        assert post_crash == original_content, (
            "crash mid-replace must preserve the journal exactly; "
            "the compact-tmp + os.replace pattern guarantees no "
            "zero-bytes-with-pending-entries window"
        )

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="compact-tmp cleanup uses _atomic_compact_journal (POSIX only); "
        "_sweep_unlocked_body on Windows uses atomic_write_with and never "
        "creates the <journal>.<pid>.compact.tmp file this test depends on",
    )
    def test_compaction_stale_tmp_from_prior_crashed_sweep(self, tmp_path: Path) -> None:
        """§6.4: if a prior crashed sweep left a compact-tmp on disk,
        the next sweep removes it once and retries."""
        from file_organizer.undo.durable_move import _append_journal, sweep

        journal = tmp_path / "move.journal"
        src_keep = tmp_path / "kept.txt"
        src_keep.write_text("x")
        dst_missing = tmp_path / "missing.txt"
        _append_journal(
            journal,
            {"op": "move", "src": str(src_keep), "dst": str(dst_missing), "state": "copied"},
        )

        # Simulate stale tmp from a prior crashed sweep — same path the
        # current sweep would generate.
        stale_tmp = tmp_path / f"move.journal.{os.getpid()}.compact.tmp"
        stale_tmp.write_text("garbage from a prior crash\n")
        assert stale_tmp.exists()

        # Sweep must succeed despite the stale tmp.
        sweep(journal)
        assert not stale_tmp.exists(), "sweep must clean up stale compact-tmp"

    def test_compaction_size_cap_skips_oversized_journal(self, tmp_path: Path) -> None:
        """§6.6: journals >16 MiB trigger a WARNING and skip
        compaction (belt-and-suspenders; steady-state journals are
        bounded by in-flight count). Sweep returns early without
        rewriting."""
        from file_organizer.undo.durable_move import sweep

        journal = tmp_path / "move.journal"
        # Build a journal whose total size exceeds the 16 MiB cap.
        entry_template = json.dumps(
            {
                "op": "move",
                "src": "/a",
                "dst": "/b",
                "state": "done",
                "_padding": "x" * 4096,
            }
        )
        # Each entry ~4 KiB; 4500 entries ~18 MiB.
        with open(journal, "w") as fh:
            for _ in range(4500):
                fh.write(entry_template + "\n")
        size_before = journal.stat().st_size
        assert size_before > 16 * 1024 * 1024

        with _capture_durable_move_warnings() as records:
            sweep(journal)

        # Journal still oversized (sweep skipped compaction).
        assert journal.stat().st_size == size_before
        msgs = [r.getMessage() for r in records]
        assert any("size cap" in m.lower() for m in msgs), f"expected size-cap WARNING; got {msgs}"

    def test_compaction_empty_retained_clears_journal(self, tmp_path: Path) -> None:
        """When sweep reconciles every entry to drop, the journal is
        cleared (truncated to empty via the compact-tmp + replace path,
        not in-place truncation)."""
        from file_organizer.undo.durable_move import _append_journal, sweep

        journal = tmp_path / "move.journal"
        _append_journal(journal, {"op": "move", "src": "/a", "dst": "/b", "state": "done"})
        _append_journal(journal, {"op": "move", "src": "/c", "dst": "/d", "state": "done"})

        sweep(journal)

        # Journal exists but is empty.
        assert journal.exists()
        assert journal.read_text().strip() == ""


# ---------------------------------------------------------------------------
# F7.1 step 4: lock-file extraction
# (tracks #201, docs/internal/F7-1-journal-protocol-design.md §6.1, §6.5)
# ---------------------------------------------------------------------------


class TestJournalLockFile:
    """Step 4 / round-1 review blocking fix: all flock operations acquire
    on a sibling ``<journal>.lock`` file with a stable inode, NOT on
    ``<journal>`` directly. Required for step 5's atomic compaction —
    ``os.replace`` on the journal must not invalidate locks held by
    concurrent appenders.
    """

    def test_lock_path_alongside_journal(self, tmp_path: Path) -> None:
        """The lock subject is ``<journal>.lock`` in the same directory."""
        from file_organizer.undo.durable_move import _lock_path

        journal = tmp_path / "move.journal"
        assert _lock_path(journal) == tmp_path / "move.journal.lock"

    def test_append_creates_lock_file_at_stable_path(self, tmp_path: Path) -> None:
        """First append creates both the journal AND the lock file. The
        lock file is then NEVER unlinked or replaced by normal protocol
        operations."""
        pytest.importorskip("fcntl")
        from file_organizer.undo.durable_move import _append_journal, _lock_path

        journal = tmp_path / "move.journal"
        lock = _lock_path(journal)

        _append_journal(journal, {"op": "move", "src": "/a", "dst": "/b", "state": "done"})

        assert journal.exists()
        assert lock.exists()
        # Capture the lock file's inode — subsequent operations must
        # preserve it (the round-1 review blocking concern).
        lock_inode_before = lock.stat().st_ino

        # Several more appends + a sweep — lock inode must not change.
        _append_journal(journal, {"op": "move", "src": "/c", "dst": "/d", "state": "done"})
        from file_organizer.undo.durable_move import sweep

        sweep(journal)

        assert lock.exists(), "lock file must persist across protocol ops"
        assert lock.stat().st_ino == lock_inode_before, (
            "lock file inode must be stable across appends + sweep — "
            "if it changes, concurrent flock holders lose coordination "
            "(round-1 review blocking concern)"
        )

    def test_append_blocks_while_lock_ex_held_on_lock_file(self, tmp_path: Path) -> None:
        """Acquiring ``LOCK_EX`` on ``<journal>.lock`` (NOT on
        ``<journal>``) blocks ``_append_journal``. Proves the appender
        coordinates on the new lock file."""
        fcntl = pytest.importorskip("fcntl")
        import threading

        from file_organizer.undo.durable_move import _append_journal, _lock_path

        journal = tmp_path / "move.journal"
        # Pre-populate so the lock file exists.
        _append_journal(journal, {"op": "move", "src": "/a", "dst": "/b", "state": "done"})
        lock = _lock_path(journal)

        # Hold LOCK_EX on the lock file from the main thread.
        holder = open(lock, "r+", encoding="utf-8")
        fcntl.flock(holder.fileno(), fcntl.LOCK_EX)

        appender_entered = threading.Event()
        append_done = threading.Event()

        def _appender() -> None:
            appender_entered.set()
            try:
                _append_journal(journal, {"op": "move", "src": "/x", "dst": "/y", "state": "done"})
            finally:
                append_done.set()

        t = threading.Thread(target=_appender, daemon=True)
        t.start()

        assert appender_entered.wait(timeout=5.0), "appender never scheduled"
        # Appender must block on the lock file's LOCK_EX.
        assert not append_done.wait(timeout=0.5), (
            "_append_journal must block while LOCK_EX is held on the lock "
            "file (step-4 lock-file extraction)"
        )

        # Release; appender completes.
        fcntl.flock(holder.fileno(), fcntl.LOCK_UN)
        holder.close()
        assert append_done.wait(timeout=5.0)
        t.join(timeout=2)

    def test_is_path_in_flight_blocks_on_lock_file_lock_ex(self, tmp_path: Path) -> None:
        """Reader takes ``LOCK_SH`` on the lock file; LOCK_EX held on
        the lock file blocks the reader. Same plumbing as step 4 for
        the appender."""
        fcntl = pytest.importorskip("fcntl")
        import threading

        from file_organizer.undo.durable_move import _append_journal, _lock_path, is_path_in_flight

        journal = tmp_path / "move.journal"
        _append_journal(journal, {"op": "move", "src": "/a", "dst": "/b", "state": "done"})
        lock = _lock_path(journal)

        holder = open(lock, "r+", encoding="utf-8")
        fcntl.flock(holder.fileno(), fcntl.LOCK_EX)

        reader_done = threading.Event()
        result: list[bool | None] = [None]

        def _reader() -> None:
            try:
                result[0] = is_path_in_flight(Path("/x"), journal=journal)
            finally:
                reader_done.set()

        t = threading.Thread(target=_reader, daemon=True)
        t.start()

        assert not reader_done.wait(timeout=0.5), (
            "is_path_in_flight must block while LOCK_EX held on lock file"
        )
        fcntl.flock(holder.fileno(), fcntl.LOCK_UN)
        holder.close()
        assert reader_done.wait(timeout=5.0)
        t.join(timeout=2)
        assert result[0] is False

    def test_replace_journal_under_held_lock_does_not_break_appender(self, tmp_path: Path) -> None:
        """Round-1 review blocking case: a sweep that would
        ``os.replace`` the journal underneath a held lock MUST NOT
        invalidate concurrent appenders' coordination. With the lock
        on a separate ``<journal>.lock`` file (whose inode never
        changes), an appender that holds LOCK_EX on the lock file is
        unaffected by an inode swap on the journal itself.

        This test simulates the dangerous sequence:
            1. Appender T1 acquires LOCK_EX on the lock file (mid-write).
            2. Compaction (T2) `os.replace`s the journal with a new inode.
            3. T1 writes to its (still-open) journal fd — but if step 4
               had been done correctly, T1's append should land in the
               *new* journal because the appender opens via the journal
               path on each call (subsequent appender T3 is the proxy).
            4. T3 (a fresh appender) appends after the swap — must land
               in the new journal.

        Step 4 only proves the lock subject is independent of the
        journal inode. Step 5's atomic compaction will exercise the
        full os.replace path.
        """
        pytest.importorskip("fcntl")
        from file_organizer.undo.durable_move import _append_journal, _lock_path, _read_journal

        journal = tmp_path / "move.journal"
        _append_journal(journal, {"op": "move", "src": "/a", "dst": "/b", "state": "done"})
        lock = _lock_path(journal)
        original_lock_inode = lock.stat().st_ino

        # Simulate compaction: write a new file, os.replace the journal.
        new_journal_content = (
            json.dumps({"op": "move", "src": "/c", "dst": "/d", "state": "done"}) + "\n"
        )
        new_tmp = tmp_path / "move.journal.compact.tmp"
        new_tmp.write_text(new_journal_content)
        os.replace(new_tmp, journal)

        # Lock file's inode must not have changed — it's a separate file.
        assert lock.stat().st_ino == original_lock_inode

        # New appender works against the new journal inode + same lock file.
        _append_journal(journal, {"op": "move", "src": "/e", "dst": "/f", "state": "done"})

        # Journal contains the post-replace content + the new append.
        entries = _read_journal(journal)
        srcs = {e.src for e in entries}
        assert "/c" in srcs and "/e" in srcs


# ---------------------------------------------------------------------------
# F7.1 step 2: pure planner `plan_recovery_actions`
# (tracks #201, docs/internal/F7-1-journal-protocol-design.md §8.1, §9)
# ---------------------------------------------------------------------------


class TestPlanRecoveryActions:
    """Planner is pure: computes a list of :class:`_PlannedAction` from a
    list of :class:`_JournalEntry` + an optional ``fs_observer``, with zero
    disk mutation. Sweep's ``_apply_planned_actions`` executor performs the
    mutations. Step 2 preserves PR #197 behavior; step 3 changes the collapse
    key; step 6 adds tmp_path disambiguation.
    """

    def test_planner_is_pure_no_disk_mutation(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Planning on a journal containing a COPIED entry with dst present
        on disk MUST NOT unlink src during the plan step. The planner is
        pure; mutations happen only in the executor."""
        from file_organizer.undo.durable_move import _JournalEntry, plan_recovery_actions

        src = tmp_path / "src.txt"
        dst = tmp_path / "dst.txt"
        src.write_text("must not be unlinked by planner")
        dst.write_text("complete destination")

        # Instrument Path.unlink and fsync_directory — if the planner
        # touches either, the test fails.
        calls: list[tuple[str, object]] = []
        real_unlink = Path.unlink

        def tracking_unlink(self: Path, *a: object, **k: object) -> None:
            calls.append(("unlink", self))
            return real_unlink(self, *a, **k)

        monkeypatch.setattr(Path, "unlink", tracking_unlink)
        monkeypatch.setattr(
            "file_organizer.undo.durable_move.fsync_directory",
            lambda p: calls.append(("fsync", p)),
        )

        entries = [
            _JournalEntry(op="move", src=str(src), dst=str(dst), state="copied"),
        ]
        plan = plan_recovery_actions(entries)

        assert calls == [], (
            f"planner must not mutate disk (§8.1 pure-planner contract); observed: {calls}"
        )
        assert len(plan) == 1
        # Planner decided "unlink src, drop entry" based on the real
        # lexists(dst) observation — but DIDN'T execute yet.
        assert plan[0].verb == "unlink_src_then_drop"
        # src is still on disk — executor hasn't run.
        assert src.read_text() == "must not be unlinked by planner"

    def test_planner_deterministic(self, tmp_path: Path) -> None:
        """Given the same inputs + fs_observer, planner returns the same plan
        twice. Required by the §8.1 CLI/sweep parity contract."""
        from file_organizer.undo.durable_move import _JournalEntry, plan_recovery_actions

        src = tmp_path / "s.txt"
        dst = tmp_path / "d.txt"
        src.write_text("x")
        dst.write_text("y")
        entries = [
            _JournalEntry(op="move", src=str(src), dst=str(dst), state="copied"),
            _JournalEntry(
                op="dir_move",
                src=str(tmp_path / "dir_a"),
                dst=str(tmp_path / "dir_b"),
                state="started",
            ),
            _JournalEntry(op="move", src="/x", dst="/y", state="done"),
        ]
        plan1 = plan_recovery_actions(entries)
        plan2 = plan_recovery_actions(entries)
        assert plan1 == plan2

    def test_planner_fs_observer_stub(self) -> None:
        """Planner accepts a custom ``fs_observer`` so tests can exercise
        the §5.1 recovery-state-table rows without setting up real files.
        This is also what ``fo undo recover`` uses for the "what WOULD
        sweep do" preview."""
        from file_organizer.undo.durable_move import _JournalEntry, plan_recovery_actions

        entries = [
            _JournalEntry(op="move", src="/a", dst="/b", state="copied"),
        ]
        # fs_observer says dst does NOT exist → §5.1 COPIED+dst-missing row → retain.
        plan = plan_recovery_actions(entries, fs_observer=lambda _p: False)
        assert len(plan) == 1
        assert plan[0].verb == "retain"

        # Same entry but fs_observer says dst exists → unlink_src_then_drop.
        plan_present = plan_recovery_actions(entries, fs_observer=lambda _p: True)
        assert plan_present[0].verb == "unlink_src_then_drop"

    def test_planner_verb_matrix(self) -> None:
        """PR #197 behavior at step 2: each (op, state, dst-present)
        combination produces the expected verb. Table mirrors the
        pre-step-6 subset of §5.1."""
        from file_organizer.undo.durable_move import _JournalEntry, plan_recovery_actions

        # (op, state, dst_present) -> expected verb
        cases: list[tuple[str, str, bool, str]] = [
            ("move", "started", True, "retain"),
            ("move", "started", False, "retain"),
            ("move", "copied", True, "unlink_src_then_drop"),
            ("move", "copied", False, "retain"),
            ("move", "done", True, "drop"),
            ("move", "done", False, "drop"),
            # §5.1 row "known-op unknown state" applies to ``move``: retain
            # + warn so a future binary that knows the new state can still
            # resolve the entry, and is_path_in_flight() keeps protecting
            # the path. CodeRabbit PRRT_kwDOR_Rkws59lDD8.
            ("move", "unknown_state", True, "retain"),
            ("dir_move", "started", True, "drop"),
            ("dir_move", "done", True, "drop"),
            # dir_move overrides the generic unknown-state retain because
            # §5.3 makes dir_move coordination-only — sweep can't safely
            # retry shutil.move regardless of state, so dropping releases
            # the in-flight marker.
            ("dir_move", "unknown_state", True, "drop"),
            ("future_op", "started", True, "retain"),  # unknown op retain
            ("future_op", "done", True, "retain"),  # unknown op retain
        ]
        for op, state, dst_present, expected in cases:
            entries = [_JournalEntry(op=op, src="/s", dst="/d", state=state)]
            # Bind dst_present at lambda-creation time so each iteration
            # captures its own value (B023).
            plan = plan_recovery_actions(
                entries, fs_observer=lambda _p, present=dst_present: present
            )
            assert len(plan) == 1
            assert plan[0].verb == expected, (
                f"op={op} state={state} dst_present={dst_present}: "
                f"expected verb={expected}, got {plan[0].verb}"
            )

    def test_planner_collapse_key_separates_ops(self) -> None:
        """Step 3 / codex iy4u: collapse key includes ``op`` so same paths
        in different ops cannot mask each other. The pre-fix behavior
        (PR #197 step 2) was: ``dir_move done`` would overwrite ``move
        started``, dropping the move's recovery metadata. Now both
        identities survive the collapse and produce independent plans.
        """
        from file_organizer.undo.durable_move import _JournalEntry, plan_recovery_actions

        entries = [
            _JournalEntry(op="move", src="/a", dst="/b", state="started"),
            _JournalEntry(op="dir_move", src="/a", dst="/b", state="started"),
            _JournalEntry(op="dir_move", src="/a", dst="/b", state="done"),
        ]
        plan = plan_recovery_actions(entries, fs_observer=lambda _p: False)
        # Two identities now: move (retained as ambiguous) + dir_move
        # (collapses to done, dropped).
        assert len(plan) == 2
        verb_by_op = {a.entry.op: a.verb for a in plan}
        assert verb_by_op["move"] == "retain"
        assert verb_by_op["dir_move"] == "drop"

    def test_planner_collapse_key_separates_v2_op_ids(self) -> None:
        """§3.1 rule 1: v2 ``(op, op_id)`` identity. Two retries of the
        same move with different op_ids stay distinct so a superseding
        retry's ``done`` cannot erase an older retained ``started``."""
        from file_organizer.undo.durable_move import _JournalEntry, plan_recovery_actions

        # Same paths, same op, different op_id → distinct identities.
        entries = [
            _JournalEntry(
                op="move",
                src="/a",
                dst="/b",
                state="started",
                schema=2,
                op_id="attempt-1",
                tmp_path="/a.tmp",
            ),
            _JournalEntry(
                op="move",
                src="/a",
                dst="/b",
                state="done",
                schema=2,
                op_id="attempt-2",
            ),
        ]
        plan = plan_recovery_actions(entries, fs_observer=lambda _p: False)
        assert len(plan) == 2
        # Both identities present; attempt-1's recovery metadata survives.
        op_ids = {a.entry.op_id for a in plan}
        assert op_ids == {"attempt-1", "attempt-2"}

    def test_planner_collapse_key_v2_progression_collapses_same_op_id(self) -> None:
        """§3.2: within a single op_id, states progress and collapse —
        a later ``done`` for the SAME op_id supersedes earlier
        started/copied entries (the legitimate collapse case)."""
        from file_organizer.undo.durable_move import _JournalEntry, plan_recovery_actions

        entries = [
            _JournalEntry(
                op="move",
                src="/a",
                dst="/b",
                state="started",
                schema=2,
                op_id="single",
                tmp_path="/a.tmp",
            ),
            _JournalEntry(
                op="move",
                src="/a",
                dst="/b",
                state="copied",
                schema=2,
                op_id="single",
            ),
            _JournalEntry(
                op="move",
                src="/a",
                dst="/b",
                state="done",
                schema=2,
                op_id="single",
            ),
        ]
        plan = plan_recovery_actions(entries, fs_observer=lambda _p: True)
        # Single identity collapses to the latest state: done → drop.
        assert len(plan) == 1
        assert plan[0].entry.state == "done"
        assert plan[0].verb == "drop"

    def test_planner_collapse_key_v1_v2_never_collide(self) -> None:
        """§3.1 ``v1`` / ``v2`` discriminator: a v1 record and a v2
        record with the same ``(op, src, dst)`` get distinct identities,
        so v2 cannot mask v1 retain metadata or vice-versa."""
        from file_organizer.undo.durable_move import _JournalEntry, plan_recovery_actions

        entries = [
            # v1 record — no op_id, no schema.
            _JournalEntry(op="move", src="/a", dst="/b", state="copied"),
            # v2 record — explicit op_id.
            _JournalEntry(
                op="move",
                src="/a",
                dst="/b",
                state="copied",
                schema=2,
                op_id="abc",
            ),
        ]
        plan = plan_recovery_actions(entries, fs_observer=lambda _p: True)
        assert len(plan) == 2

    def test_planner_collapse_key_unknown_op_uses_raw_hash(self) -> None:
        """§3.1 rule 4: unknown-op identity uses ``_hash16(_raw)`` so
        future ops with semantically-distinct payloads don't conflate.
        Two unknown-op entries with the same paths but different raw
        lines produce distinct identities and BOTH retain."""
        from file_organizer.undo.durable_move import _JournalEntry, plan_recovery_actions

        entries = [
            _JournalEntry(
                op="future_copy",
                src="/a",
                dst="/b",
                state="started",
                schema=3,
                _raw='{"schema":3,"op":"future_copy","src":"/a","dst":"/b","state":"started","content_hash":"aaa"}',
            ),
            _JournalEntry(
                op="future_copy",
                src="/a",
                dst="/b",
                state="started",
                schema=3,
                _raw='{"schema":3,"op":"future_copy","src":"/a","dst":"/b","state":"started","content_hash":"bbb"}',
            ),
        ]
        plan = plan_recovery_actions(entries, fs_observer=lambda _p: False)
        # Both records survive — _hash16 differs per raw payload, so the
        # collapse key separates them. A future binary's handler decides
        # via its own field semantics.
        assert len(plan) == 2
        for action in plan:
            assert action.verb == "retain"

    def test_executor_applies_unlink_src_then_drop(self, tmp_path: Path) -> None:
        """Executor's ``unlink_src_then_drop`` verb: unlinks src, fsyncs
        src.parent, returns empty retained list."""
        from file_organizer.undo.durable_move import (
            _apply_planned_actions,
            _JournalEntry,
            plan_recovery_actions,
        )

        src = tmp_path / "src.txt"
        dst = tmp_path / "dst.txt"
        src.write_text("leftover")
        dst.write_text("complete")
        entries = [_JournalEntry(op="move", src=str(src), dst=str(dst), state="copied")]
        plan = plan_recovery_actions(entries)
        retained = _apply_planned_actions(plan)

        assert retained == []  # dropped
        assert not src.exists()  # unlinked
        assert dst.read_text() == "complete"  # untouched

    def test_executor_retain_does_not_mutate(self, tmp_path: Path) -> None:
        """Executor's ``retain`` verb: no disk mutation, entry returned
        in retained list."""
        from file_organizer.undo.durable_move import (
            _apply_planned_actions,
            _JournalEntry,
            plan_recovery_actions,
        )

        src = tmp_path / "src.txt"
        dst = tmp_path / "dst.txt"  # deliberately absent → COPIED retains
        src.write_text("must survive")
        entry = _JournalEntry(op="move", src=str(src), dst=str(dst), state="copied")
        plan = plan_recovery_actions([entry])
        retained = _apply_planned_actions(plan)

        assert retained == [entry]
        assert src.read_text() == "must survive"
        assert not dst.exists()

    def test_executor_drop_does_not_mutate(self, tmp_path: Path) -> None:
        """Executor's ``drop`` verb: no disk mutation, entry dropped."""
        from file_organizer.undo.durable_move import (
            _apply_planned_actions,
            _JournalEntry,
            plan_recovery_actions,
        )

        src = tmp_path / "src.txt"
        dst = tmp_path / "dst.txt"
        src.write_text("untouched")
        dst.write_text("untouched")
        entry = _JournalEntry(op="move", src=str(src), dst=str(dst), state="done")
        plan = plan_recovery_actions([entry])
        retained = _apply_planned_actions(plan)

        assert retained == []
        assert src.read_text() == "untouched"
        assert dst.read_text() == "untouched"

    def test_executor_os_error_on_unlink_retains(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Preserves PR #197 round-5 behavior: OSError during unlink_src
        retains the entry (transient permission / lock is retry-eligible).
        The PLANNER produces ``unlink_src_then_drop`` optimistically; the
        EXECUTOR downgrades to retain when the unlink raises."""
        from file_organizer.undo.durable_move import (
            _apply_planned_actions,
            _JournalEntry,
            plan_recovery_actions,
        )

        src = tmp_path / "src.txt"
        dst = tmp_path / "dst.txt"
        src.write_text("x")
        dst.write_text("y")
        entry = _JournalEntry(op="move", src=str(src), dst=str(dst), state="copied")
        plan = plan_recovery_actions([entry])
        assert plan[0].verb == "unlink_src_then_drop"

        real_unlink = Path.unlink

        def failing_unlink(self: Path, *a: object, **k: object) -> None:
            if str(self) == str(src):
                raise OSError(13, "simulated permission denied")
            return real_unlink(self, *a, **k)

        monkeypatch.setattr(Path, "unlink", failing_unlink)

        retained = _apply_planned_actions(plan)
        assert retained == [entry], (
            "transient OSError on unlink must fall back to retain so the "
            "next sweep can retry (codex fwMK, PR #197 round-5)"
        )
        assert src.exists()  # unlink raised → src survives


class TestIsPathInFlightCollapseIdentity:
    """§3.1 / step 3 codex iy4u: ``is_path_in_flight`` MUST collapse by
    the operation identity, not by ``(src, dst)`` alone. Path-keyed
    collapse re-introduces the iy4u masking bug for the F8 trash-GC
    coordination path.

    Concrete failure mode without identity-keyed collapse: a
    ``move /a /b started`` followed by a ``dir_move /a /b done`` for
    the same paths would let the dir_move done supersede the move
    started under ``(src, dst)`` reduction. ``is_path_in_flight(/a)``
    would then return ``False`` during the move's copy → replace
    window, and trash GC could delete /a out from under it. The
    identity-keyed collapse keeps both records distinct.
    """

    def test_separate_ops_on_same_paths_dont_mask(self, tmp_path: Path) -> None:
        """``move started`` + ``dir_move done`` on identical paths:
        ``is_path_in_flight`` must still see the move's STARTED entry
        and return True."""
        from file_organizer.undo.durable_move import _append_journal, is_path_in_flight

        journal = tmp_path / "move.journal"
        # Use tmp_path-relative paths so Path(src) resolves correctly on Windows.
        src = str(tmp_path / "a")
        dst = str(tmp_path / "b")
        # NB: writer-side dir_move uses v1 envelope; move uses v2.
        # Different ops → different §3.1 identities even with same
        # (src, dst), so the dir_move done can NOT mask the move started.
        _append_journal(
            journal,
            {"op": "move", "src": src, "dst": dst, "state": "started"},
        )
        _append_journal(
            journal,
            {"op": "dir_move", "src": src, "dst": dst, "state": "done"},
        )
        # Without identity-keyed collapse, the dir_move done would
        # overwrite the move started under (src, dst) and this would
        # falsely return False.
        assert is_path_in_flight(Path(src), journal=journal) is True
        assert is_path_in_flight(Path(dst), journal=journal) is True

    def test_v2_op_id_distinct_attempts_dont_mask(self, tmp_path: Path) -> None:
        """Two v2 ``move`` retries on the same paths but different
        op_ids stay distinct under identity collapse — a later
        attempt's done can NOT mask an earlier attempt's started."""
        from file_organizer.undo.durable_move import _append_journal, is_path_in_flight

        journal = tmp_path / "move.journal"
        # Use tmp_path-relative paths so Path(src) resolves correctly on Windows.
        src = str(tmp_path / "a")
        dst = str(tmp_path / "b")
        tmp = str(tmp_path / "a.tmp")
        # Attempt 1: still in flight (started).
        _append_journal(
            journal,
            {
                "schema": 2,
                "op": "move",
                "op_id": "attempt-1",
                "src": src,
                "dst": dst,
                "tmp_path": tmp,
                "state": "started",
            },
        )
        # Attempt 2: completed.
        _append_journal(
            journal,
            {
                "schema": 2,
                "op": "move",
                "op_id": "attempt-2",
                "src": src,
                "dst": dst,
                "state": "done",
            },
        )
        # Attempt 1's started must still be visible — its op_id keeps
        # it distinct from attempt 2's done under §3.1 collapse.
        assert is_path_in_flight(Path(src), journal=journal) is True


class TestStartedTmpPathDisambiguation:
    """Step 6 / §7.1: v2 ``move started`` records carry ``tmp_path``;
    sweep observes ``lexists(tmp_path)`` to disambiguate pre-replace
    (tmp present) from post-replace (tmp absent) crashes.

    The tmp-exists invariant (§7.1) is what makes tmp-absent ⇒
    post-replace inference safe. Step 6 enforces that invariant on the
    write path and consumes it in the planner.
    """

    def test_planner_v2_started_tmp_present_drops_tmp(self) -> None:
        """§5.1 row: v2 ``move started`` + ``lexists(tmp_path) == True``
        ⇒ pre-replace crash. ``os.replace`` never ran; tmp is an orphan
        copy. Verb: ``drop_tmp_then_drop`` (executor unlinks tmp, drops
        the entry; src remains untouched as the canonical copy)."""
        from file_organizer.undo.durable_move import _JournalEntry, plan_recovery_actions

        entry = _JournalEntry(
            op="move",
            src="/a",
            dst="/b",
            state="started",
            schema=2,
            op_id="op-pre",
            tmp_path="/path/to/.b.42.tmp",
        )
        # fs_observer reports tmp present.
        plan = plan_recovery_actions([entry], fs_observer=lambda p: p == "/path/to/.b.42.tmp")
        assert len(plan) == 1
        assert plan[0].verb == "drop_tmp_then_drop"

    def test_planner_v2_started_tmp_absent_unlinks_src(self) -> None:
        """§5.1 row: v2 ``move started`` + ``lexists(tmp_path) == False``
        + ``lexists(dst) == True`` ⇒ post-replace crash confirmed.
        ``os.replace`` consumed tmp into dst; the only thing left is to
        unlink src. Verb: ``unlink_src_then_drop`` (same as the COPIED
        row — sweep finishes by removing the now-redundant source).

        The dst-present check is the codex lCbU data-loss guard: tmp
        absent alone is NOT proof that replace ran. See
        ``test_planner_v2_started_tmp_absent_dst_absent_retains`` for
        the negative case.
        """
        from file_organizer.undo.durable_move import _JournalEntry, plan_recovery_actions

        entry = _JournalEntry(
            op="move",
            src="/a",
            dst="/b",
            state="started",
            schema=2,
            op_id="op-post",
            tmp_path="/path/to/.b.42.tmp",
        )

        # fs_observer: tmp absent, dst PRESENT (the proof of post-replace).
        def fs(p: str) -> bool:
            return p == "/b"

        plan = plan_recovery_actions([entry], fs_observer=fs)
        assert len(plan) == 1
        assert plan[0].verb == "unlink_src_then_drop"

    def test_planner_v2_started_tmp_absent_dst_absent_retains(self) -> None:
        """Codex P1 PRRT_kwDOR_Rkws59lCbU: when v2 STARTED has tmp absent
        AND dst also absent, sweep MUST NOT plan ``unlink_src_then_drop``
        — that would destroy the last remaining copy on disk if dst was
        cleaned out-of-band after a crash. Mirrors the codex hGWW
        dst-presence guard on the COPIED row.

        Rationale: tmp absent is NOT proof that ``os.replace`` ran. Tmp
        could also be absent if an operator manually cleaned it. If dst
        is then also absent, src is the canonical copy — unlinking it
        is data loss. Retain instead so the next sweep / operator can
        resolve.
        """
        from file_organizer.undo.durable_move import _JournalEntry, plan_recovery_actions

        entry = _JournalEntry(
            op="move",
            src="/a",
            dst="/b",
            state="started",
            schema=2,
            op_id="op-x",
            tmp_path="/path/to/.b.42.tmp",
        )
        # fs_observer: BOTH tmp and dst absent.
        plan = plan_recovery_actions([entry], fs_observer=lambda _p: False)
        assert len(plan) == 1
        assert plan[0].verb == "retain", (
            f"v2 STARTED + tmp absent + dst absent must retain (data-loss guard); "
            f"got {plan[0].verb}"
        )

    def test_planner_v2_started_tmp_absent_dst_present_unlinks_src(self) -> None:
        """The post-replace branch only fires when dst is actually
        present — that's the proof ``os.replace`` consumed tmp. With
        tmp absent + dst present, ``unlink_src_then_drop`` is safe."""
        from file_organizer.undo.durable_move import _JournalEntry, plan_recovery_actions

        entry = _JournalEntry(
            op="move",
            src="/a",
            dst="/b",
            state="started",
            schema=2,
            op_id="op-x",
            tmp_path="/path/to/.b.42.tmp",
        )

        # fs_observer: tmp absent, dst present.
        def fs(p: str) -> bool:
            return p == "/b"

        plan = plan_recovery_actions([entry], fs_observer=fs)
        assert len(plan) == 1
        assert plan[0].verb == "unlink_src_then_drop"

    def test_planner_v1_started_remains_retain(self) -> None:
        """v1 records (no ``schema``, no ``tmp_path``) preserve PR #197
        retain-as-ambiguous behavior. The disambiguation is a v2-only
        capability; v1 records lack the metadata to safely choose a
        verb."""
        from file_organizer.undo.durable_move import _JournalEntry, plan_recovery_actions

        entry = _JournalEntry(op="move", src="/a", dst="/b", state="started")
        plan = plan_recovery_actions([entry], fs_observer=lambda _p: True)
        assert len(plan) == 1
        assert plan[0].verb == "retain"

    def test_executor_drop_tmp_then_drop_unlinks_tmp(self, tmp_path: Path) -> None:
        """Executor's ``drop_tmp_then_drop`` verb: unlinks the tmp file,
        drops the entry, leaves src + dst untouched (src is canonical
        because the replace never ran)."""
        from file_organizer.undo.durable_move import (
            _apply_planned_actions,
            _JournalEntry,
            plan_recovery_actions,
        )

        src = tmp_path / "src.txt"
        dst = tmp_path / "dst.txt"
        tmp = tmp_path / ".dst.txt.42.tmp"
        src.write_text("canonical source")
        tmp.write_text("orphan tmp from pre-replace crash")
        # dst absent — pre-replace crash means dst was never written.
        entry = _JournalEntry(
            op="move",
            src=str(src),
            dst=str(dst),
            state="started",
            schema=2,
            op_id="op-1",
            tmp_path=str(tmp),
        )
        plan = plan_recovery_actions([entry])
        assert plan[0].verb == "drop_tmp_then_drop"

        retained = _apply_planned_actions(plan)
        assert retained == [], "drop_tmp_then_drop must drop the entry"
        assert not tmp.exists(), "tmp must be unlinked"
        assert src.read_text() == "canonical source", "src must be preserved"
        assert not dst.exists(), "dst must remain absent"

    def test_executor_drop_tmp_then_drop_handles_already_gone(self, tmp_path: Path) -> None:
        """If ``tmp_path`` is already absent (e.g. operator cleaned it
        before sweep ran), ``drop_tmp_then_drop`` swallows
        ``FileNotFoundError`` and still drops the entry — same pattern
        as ``unlink_src_then_drop``."""
        from file_organizer.undo.durable_move import (
            _apply_planned_actions,
            _JournalEntry,
        )

        # Build a plan manually so the planner's fs_observer doesn't
        # flip the verb to unlink_src_then_drop.
        entry = _JournalEntry(
            op="move",
            src=str(tmp_path / "src.txt"),
            dst=str(tmp_path / "dst.txt"),
            state="started",
            schema=2,
            op_id="op-1",
            tmp_path=str(tmp_path / "absent.tmp"),
        )
        from file_organizer.undo.durable_move import _PlannedAction

        plan = [
            _PlannedAction(
                identity=("v2", "move", "op-1"),
                entry=entry,
                verb="drop_tmp_then_drop",
                reason="test: tmp gone before sweep",
            )
        ]
        retained = _apply_planned_actions(plan)
        assert retained == [], "missing tmp must still drop entry (idempotent)"

    def test_executor_drop_tmp_then_drop_removes_directory_tmp(self, tmp_path: Path) -> None:
        """If an unexpected directory occupies ``tmp_path``, sweep removes
        it and drops the entry instead of retaining forever on
        ``IsADirectoryError``."""
        from file_organizer.undo.durable_move import (
            _apply_planned_actions,
            _JournalEntry,
            _PlannedAction,
        )

        tmp = tmp_path / ".dst.42.tmp"
        tmp.mkdir()
        (tmp / "leftover").write_text("unexpected stale tmp payload")
        entry = _JournalEntry(
            op="move",
            src=str(tmp_path / "src"),
            dst=str(tmp_path / "dst"),
            state="started",
            schema=2,
            op_id="op-1",
            tmp_path=str(tmp),
        )
        plan = [
            _PlannedAction(
                identity=("v2", "move", "op-1"),
                entry=entry,
                verb="drop_tmp_then_drop",
                reason="test: directory-shaped tmp orphan",
            )
        ]

        retained = _apply_planned_actions(plan)

        assert retained == [], "directory-shaped tmp must still drop entry"
        assert not tmp.exists(), "directory-shaped tmp must be removed recursively"

    def test_executor_drop_tmp_os_error_retains(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Transient ``OSError`` (other than ``FileNotFoundError``) on
        tmp unlink retains the entry so the next sweep retries. Mirrors
        the ``unlink_src_then_drop`` behavior (PR #197 round-5 / codex
        fwMK)."""
        from file_organizer.undo.durable_move import (
            _apply_planned_actions,
            _JournalEntry,
            _PlannedAction,
        )

        tmp = tmp_path / ".dst.42.tmp"
        tmp.write_text("orphan")
        entry = _JournalEntry(
            op="move",
            src="/src",
            dst="/dst",
            state="started",
            schema=2,
            op_id="op-1",
            tmp_path=str(tmp),
        )
        plan = [
            _PlannedAction(
                identity=("v2", "move", "op-1"),
                entry=entry,
                verb="drop_tmp_then_drop",
                reason="test",
            )
        ]

        real_unlink = Path.unlink

        def failing_unlink(self: Path, *a: object, **k: object) -> None:
            if str(self) == str(tmp):
                raise OSError(13, "simulated permission denied")
            return real_unlink(self, *a, **k)

        monkeypatch.setattr(Path, "unlink", failing_unlink)

        retained = _apply_planned_actions(plan)
        assert retained == [entry], (
            "transient OSError on tmp unlink must fall back to retain "
            "(matches unlink_src_then_drop semantics)"
        )
        assert tmp.exists(), "unlink raised → tmp survives for next sweep"


class TestWriterProtocolV2:
    """Step 6 / §7.2 + §7.3: writer-side changes to satisfy the §7.1
    tmp-exists invariant.

    Concretely:

    1. v2 envelope on every journal append: ``schema=2``, ``op_id``
       (uuid stable across started/copied/done), ``tmp_path`` on
       started.
    2. ``fsync_directory(<dst.parent>)`` runs between tmp creation and
       the started journal append (the round-2 blocking fix).
    3. ``except BaseException: tmp_path.unlink()`` is removed (§7.4):
       tmp persists if an exception fires after creation, so sweep
       can disambiguate.
    """

    def _force_exdev(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Make ``os.replace`` raise EXDEV once, then pass through."""
        real_replace = os.replace
        triggered = {"v": False}

        def exdev_once(src: object, dst: object) -> object:
            if not triggered["v"]:
                triggered["v"] = True
                raise OSError(errno.EXDEV, "Cross-device link", str(src))
            return real_replace(src, dst)

        monkeypatch.setattr("file_organizer.undo.durable_move.os.replace", exdev_once)

    def test_writer_started_record_carries_v2_envelope(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A successful EXDEV move emits a ``started`` entry with
        ``schema=2``, a populated ``op_id``, and ``tmp_path`` pointing
        at the actual tmp file path used during the copy."""
        from file_organizer.undo.durable_move import durable_move

        self._force_exdev(monkeypatch)
        src = tmp_path / "src.txt"
        dst = tmp_path / "dst.txt"
        src.write_text("payload")
        journal = tmp_path / "move.journal"

        durable_move(src, dst, journal=journal)

        entries = _read_journal(journal)
        started = [e for e in entries if e["state"] == "started"]
        assert len(started) == 1, f"expected one started entry; got {entries!r}"
        rec = started[0]
        assert rec["schema"] == 2, "writer must emit schema=2 envelope (§7.2)"
        assert isinstance(rec.get("op_id"), str) and rec["op_id"], (
            "v2 started must carry a non-empty op_id (§4.1 rule 8)"
        )
        assert isinstance(rec.get("tmp_path"), str) and rec["tmp_path"], (
            "v2 move started must carry tmp_path for §7.1 disambiguation"
        )
        # tmp_path lives in dst.parent so the os.replace is same-fs.
        assert Path(rec["tmp_path"]).parent == dst.parent

    def test_writer_op_id_stable_across_started_copied_done(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """All three state records for a single move share the SAME
        ``op_id``, so §3.1 rule 1 collapse-key collapses them into a
        single identity."""
        from file_organizer.undo.durable_move import durable_move

        self._force_exdev(monkeypatch)
        src = tmp_path / "s.txt"
        dst = tmp_path / "d.txt"
        src.write_text("x")
        journal = tmp_path / "move.journal"

        durable_move(src, dst, journal=journal)

        entries = _read_journal(journal)
        op_ids = {e.get("op_id") for e in entries if e["op"] == "move"}
        assert len(op_ids) == 1, (
            f"all states for a single move must share one op_id; got {op_ids!r}"
        )
        assert next(iter(op_ids)), "op_id must be non-empty"

    def test_writer_journals_started_before_creating_tmp(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """#1248 [P1] file-loss race fix: the writer MUST journal the
        ``started`` in-flight marker BEFORE the EXDEV tmp/copy file is
        created, so a concurrent ``TrashGC.safe_delete`` that wins the
        journal ``LOCK_EX`` always observes ``src`` as in-flight before
        it can unlink it.

        The §7.1 tmp-exists invariant is still upheld — the tmp's
        directory entry is fsynced inside the same locked window after
        the tmp is created — but the ``started`` JOURNAL append now
        precedes tmp materialization. We assert that ordering by
        capturing the journal-started append and the first creation of a
        path under ``dst.parent`` whose name starts with the tmp prefix.
        """
        from file_organizer.undo import durable_move as dm_mod

        self._force_exdev(monkeypatch)
        src = tmp_path / "s.txt"
        dst = tmp_path / "d.txt"
        src.write_text("payload")
        journal = tmp_path / "move.journal"

        events: list[tuple[str, str]] = []
        tmp_prefix = f".{dst.name}."

        real_open = dm_mod.os.open

        def tracking_open(path, flags, *a, **k):  # type: ignore[no-untyped-def]
            name = os.path.basename(str(path))
            if name.startswith(tmp_prefix) and name.endswith(".tmp"):
                events.append(("create_tmp", str(path)))
            return real_open(path, flags, *a, **k)

        real_locked_append = dm_mod._append_journal_line_locked

        def tracking_locked_append(j, payload):  # type: ignore[no-untyped-def]
            if payload.get("state") == "started":
                events.append(("journal_started", str(j)))
            return real_locked_append(j, payload)

        monkeypatch.setattr("file_organizer.undo.durable_move.os.open", tracking_open)
        monkeypatch.setattr(
            "file_organizer.undo.durable_move._append_journal_line_locked",
            tracking_locked_append,
        )

        dm_mod.durable_move(src, dst, journal=journal)

        started_idx = next((i for i, ev in enumerate(events) if ev[0] == "journal_started"), None)
        create_idx = next((i for i, ev in enumerate(events) if ev[0] == "create_tmp"), None)
        assert started_idx is not None, f"no started journal write recorded; events={events!r}"
        assert create_idx is not None, f"no tmp creation recorded; events={events!r}"
        assert started_idx < create_idx, (
            "#1248 [P1]: the started in-flight marker MUST be journaled "
            f"before the tmp file is created; events={events!r}"
        )

    def test_writer_fsyncs_dst_parent_within_started_window(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """§7.1 rule 2 (preserved under #1248 reordering): the tmp's
        directory entry is still made durable via
        ``fsync_directory(dst.parent)`` after the tmp is created, before
        the EXDEV copy proceeds. We assert at least one fsync of
        ``dst.parent`` occurs during the move."""
        from file_organizer.undo import durable_move as dm_mod

        self._force_exdev(monkeypatch)
        src = tmp_path / "s.txt"
        dst = tmp_path / "d.txt"
        src.write_text("payload")
        journal = tmp_path / "move.journal"

        fsynced_dirs: list[str] = []
        real_fsync = dm_mod.fsync_directory

        def tracking_fsync(p: Path) -> None:
            fsynced_dirs.append(str(p.parent if p.is_file() else p))
            real_fsync(p)

        monkeypatch.setattr("file_organizer.undo.durable_move.fsync_directory", tracking_fsync)

        dm_mod.durable_move(src, dst, journal=journal)

        assert str(dst.parent) in fsynced_dirs, (
            "§7.1 rule 2 requires fsync_directory(dst.parent) during the "
            f"EXDEV move; fsynced dirs={fsynced_dirs!r}"
        )

    def test_writer_no_exception_cleanup_of_tmp(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """§7.4: ``except BaseException: tmp_path.unlink()`` is removed.
        Exceptions after tmp creation MUST leave tmp on disk so sweep
        can observe ``lexists(tmp_path) == True`` and disambiguate as
        pre-replace.

        This test forces ``os.replace`` to raise inside the EXDEV body
        AFTER the tmp has been created, then asserts the tmp is still
        on disk.
        """
        from file_organizer.undo.durable_move import durable_move

        # Force EXDEV on the FIRST replace (regular code path), then
        # raise OSError on the second replace (tmp -> dst rename) so
        # the body propagates an exception while tmp exists.
        state = {"call": 0}

        def replace_fail_at_tmp_to_dst(src_arg, dst_arg):  # type: ignore[no-untyped-def]
            state["call"] += 1
            if state["call"] == 1:
                # Simulate cross-device on the same-device fast path so
                # we fall into the EXDEV branch.
                raise OSError(errno.EXDEV, "simulated cross-device")
            # Subsequent call IS the tmp → dst rename inside the EXDEV
            # branch — fail it.
            raise OSError(28, "simulated disk full at replace")

        monkeypatch.setattr(
            "file_organizer.undo.durable_move.os.replace", replace_fail_at_tmp_to_dst
        )

        src = tmp_path / "s.txt"
        dst = tmp_path / "d.txt"
        src.write_text("payload")
        journal = tmp_path / "move.journal"

        with pytest.raises(OSError, match="simulated"):
            durable_move(src, dst, journal=journal)

        # Inspect tmp_path from the started journal record.
        entries = _read_journal(journal)
        started = [e for e in entries if e["state"] == "started"]
        assert len(started) == 1
        tmp_path_str = started[0].get("tmp_path")
        assert tmp_path_str, "started entry must record tmp_path for sweep"
        assert Path(tmp_path_str).exists(), (
            "§7.4: tmp must persist after exception so sweep can "
            "observe lexists(tmp_path) == True and unlink it as orphan"
        )

    def test_writer_no_exception_cleanup_symlink(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Same as above but for the symlink branch — tmp symlink
        persists across exceptions."""
        if os.name == "nt":
            pytest.skip("POSIX symlinks")
        from file_organizer.undo.durable_move import durable_move

        # First replace = simulate cross-device on the same-device fast
        # path. Second replace (the EXDEV branch's tmp→dst symlink
        # rename) raises so the symlink tmp survives.
        state = {"call": 0}

        def replace_fail_at_tmp_to_dst(src_arg, dst_arg):  # type: ignore[no-untyped-def]
            state["call"] += 1
            if state["call"] == 1:
                raise OSError(errno.EXDEV, "simulated cross-device")
            raise OSError(28, "simulated disk full at symlink replace")

        monkeypatch.setattr(
            "file_organizer.undo.durable_move.os.replace", replace_fail_at_tmp_to_dst
        )

        target = tmp_path / "target.txt"
        target.write_text("data")
        src = tmp_path / "link"
        src.symlink_to(target)
        dst = tmp_path / "moved-link"
        journal = tmp_path / "move.journal"

        with pytest.raises(OSError, match="simulated"):
            durable_move(src, dst, journal=journal)

        entries = _read_journal(journal)
        started = [e for e in entries if e["state"] == "started"]
        assert started, "started journal entry must exist for symlink branch"
        tmp_path_str = started[0].get("tmp_path")
        assert tmp_path_str, "v2 started must carry tmp_path"
        # lexists handles the dangling-link case (target may have moved).
        assert os.path.lexists(tmp_path_str), (
            "§7.4: symlink tmp must persist on exception so sweep can see and unlink it"
        )


class TestSweepEndToEndV2Started:
    """Step 6 integration: a real EXDEV move that crashes inside the
    body, followed by a real ``sweep`` call. Validates the round-trip
    through the v2 envelope, the §7.1 invariant, and the planner's
    disambiguation rows."""

    def test_sweep_recovers_pre_replace_crash_unlinks_tmp(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """End-to-end pre-replace crash:

        1. EXDEV branch creates tmp, fsyncs, writes started journal.
        2. ``os.replace`` raises (simulated crash before tmp consumed).
        3. ``sweep`` reads journal, observes ``lexists(tmp_path)==True``
           on the orphan tmp, executes ``drop_tmp_then_drop``: unlinks
           tmp, drops entry, leaves src as the canonical copy.
        """
        from file_organizer.undo.durable_move import durable_move, sweep

        state = {"call": 0}

        def fail_after_exdev(src_arg, dst_arg):  # type: ignore[no-untyped-def]
            state["call"] += 1
            if state["call"] == 1:
                raise OSError(errno.EXDEV, "simulated cross-device")
            raise OSError(28, "simulated crash mid-replace")

        monkeypatch.setattr("file_organizer.undo.durable_move.os.replace", fail_after_exdev)

        src = tmp_path / "src.txt"
        dst = tmp_path / "dst.txt"
        src.write_text("canonical")
        journal = tmp_path / "move.journal"

        with pytest.raises(OSError, match="simulated crash"):
            durable_move(src, dst, journal=journal)

        # Sanity: tmp orphan exists on disk; src + journal intact.
        entries = _read_journal(journal)
        tmp_path_str = entries[0]["tmp_path"]
        assert Path(tmp_path_str).exists()
        assert src.read_text() == "canonical"

        # Restore os.replace so sweep's compaction can rewrite the journal.
        monkeypatch.undo()

        sweep(journal)

        # Post-sweep: tmp gone, src preserved, journal compacted to empty.
        assert not Path(tmp_path_str).exists(), (
            "sweep must unlink the orphan tmp (drop_tmp_then_drop)"
        )
        assert src.read_text() == "canonical", (
            "sweep MUST NOT touch src when tmp is present (pre-replace)"
        )
        assert not dst.exists(), "dst should still be absent"
        # Journal compacted: started entry resolved, no surviving lines.
        assert _read_journal(journal) == []

    def test_cross_device_move_removes_stale_directory_tmp(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A stale directory at the reserved tmp name is removed before
        creating the EXDEV tmp file, avoiding an already-journaled
        ``started`` entry that sweep cannot clear."""
        from file_organizer.undo.durable_move import durable_move

        src = tmp_path / "src.txt"
        dst = tmp_path / "dst.txt"
        src.write_text("canonical")
        journal = tmp_path / "move.journal"
        stale_tmp = tmp_path / f".{dst.name}.{os.getpid()}.tmp"
        stale_tmp.mkdir()
        (stale_tmp / "old").write_text("unexpected stale directory")

        real_replace = os.replace
        calls = {"count": 0}

        def exdev_once(src_arg, dst_arg):  # type: ignore[no-untyped-def]
            calls["count"] += 1
            if calls["count"] == 1:
                raise OSError(errno.EXDEV, "simulated cross-device")
            return real_replace(src_arg, dst_arg)

        monkeypatch.setattr("file_organizer.undo.durable_move.os.replace", exdev_once)

        durable_move(src, dst, journal=journal)

        assert not src.exists()
        assert dst.read_text() == "canonical"
        assert not stale_tmp.exists(), "stale directory tmp must not survive the move"
        assert _read_journal(journal)[-1]["state"] == "done"


# ---------------------------------------------------------------------------
# PR5b — inode capture from durable_move (issue #269)
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.skipif(sys.platform == "win32", reason="lstat inode semantics are POSIX-only")
@pytest.mark.skip(
    reason="OperationTransaction.log_move(dest_dev=...) lands in WP-2.2 (undo call-site hardening)"
)
class TestDurableMoveInodeCapture:
    """durable_move returns (dev, ino, size) for callers that record history."""

    def test_same_device_returns_dst_inode(self, tmp_path: Path) -> None:
        """durable_move returns non-None (dev, ino, size) after same-device move."""
        from file_organizer.undo.durable_move import durable_move

        src = tmp_path / "src.txt"
        dst = tmp_path / "dst.txt"
        src.write_bytes(b"hello inode")
        journal = tmp_path / "move.journal"

        pin = durable_move(src, dst, journal=journal)

        assert pin is not None, "POSIX same-device move must return inode triple"
        dev, ino, size = pin
        st = dst.stat()
        assert dev == st.st_dev
        assert ino == st.st_ino
        assert size == st.st_size

    def test_inode_triple_matches_lstat(self, tmp_path: Path) -> None:
        """The captured (dev, ino, size) matches os.lstat on the destination."""
        from file_organizer.undo.durable_move import durable_move

        src = tmp_path / "file.txt"
        dst = tmp_path / "sub" / "file.txt"
        src.write_bytes(b"x" * 512)
        journal = tmp_path / "j.journal"

        pin = durable_move(src, dst, journal=journal)

        assert pin is not None
        st = os.lstat(dst)
        assert pin == (st.st_dev, st.st_ino, st.st_size)

    def test_inode_stored_in_history_via_log_operation(self, tmp_path: Path) -> None:
        """Caller passes (dev, ino) to log_operation; round-trip confirms non-None values."""
        from file_organizer.history.models import OperationType
        from file_organizer.history.tracker import OperationHistory
        from file_organizer.undo.durable_move import durable_move

        src = tmp_path / "a.txt"
        dst = tmp_path / "b.txt"
        src.write_bytes(b"history inode test")
        journal = tmp_path / "h.journal"
        db = tmp_path / "history.db"

        pin = durable_move(src, dst, journal=journal)
        assert pin is not None
        dev, ino, size = pin

        with OperationHistory(db_path=db) as history:
            history.log_operation(
                OperationType.MOVE,
                source_path=src,
                destination_path=dst,
                dest_dev=dev,
                dest_ino=ino,
            )
            ops = history.get_operations()

        assert len(ops) == 1
        op = ops[0]
        assert op.dest_dev == dev
        assert op.dest_ino == ino

    def test_legacy_row_has_none_inode(self, tmp_path: Path) -> None:
        """Operations logged without inode args (pre-PR5 rows) return None."""
        from file_organizer.history.models import OperationType
        from file_organizer.history.tracker import OperationHistory

        src = tmp_path / "old.txt"
        src.write_bytes(b"legacy")
        db = tmp_path / "history.db"

        with OperationHistory(db_path=db) as history:
            history.log_operation(OperationType.MOVE, source_path=src, destination_path=src)
            ops = history.get_operations()

        assert ops[0].dest_dev is None
        assert ops[0].dest_ino is None

    def test_transaction_log_move_passes_inode(self, tmp_path: Path) -> None:
        """OperationTransaction.log_move propagates dest_dev/dest_ino to the DB."""
        from file_organizer.history.tracker import OperationHistory
        from file_organizer.history.transaction import OperationTransaction
        from file_organizer.undo.durable_move import durable_move

        src = tmp_path / "txn_src.txt"
        dst = tmp_path / "txn_dst.txt"
        src.write_bytes(b"transaction inode")
        journal = tmp_path / "txn.journal"
        db = tmp_path / "txn.db"

        pin = durable_move(src, dst, journal=journal)
        assert pin is not None
        dev, ino, _ = pin

        with OperationHistory(db_path=db) as history:
            with OperationTransaction(history) as txn:
                txn.log_move(src, dst, dest_dev=dev, dest_ino=ino)
            ops = history.get_operations()

        assert ops[0].dest_dev == dev
        assert ops[0].dest_ino == ino

    def test_capture_dst_inode_returns_none_on_lstat_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_capture_dst_inode returns None and logs debug when os.lstat raises OSError."""
        from file_organizer.undo.durable_move import _capture_dst_inode

        def _raise_oserror(_path: object) -> None:
            raise OSError("permission denied")

        monkeypatch.setattr("file_organizer.undo.durable_move.os.lstat", _raise_oserror)

        result = _capture_dst_inode(tmp_path / "anything.txt")

        assert result is None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_journal(journal: Path) -> list[dict]:
    """Read a JSONL journal file — list of entries, one per line."""
    if not journal.exists():
        return []
    entries = []
    for line in journal.read_text().splitlines():
        line = line.strip()
        if line:
            entries.append(json.loads(line))
    return entries


def _write_journal(journal: Path, entries: list[dict]) -> None:
    """Write JSONL journal entries (test helper)."""
    journal.write_text("\n".join(json.dumps(e) for e in entries) + "\n")
