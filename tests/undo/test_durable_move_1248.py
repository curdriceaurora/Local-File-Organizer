"""#1248 (WP-1.2b) regression tests for durable_move crash-safety fixes.

Covers the four fixes that are exercisable without WP-2.2 integration:

- #1 cross-device pre-journal file-loss race: the ``started`` in-flight
  marker is journaled BEFORE the EXDEV tmp is created.
- #2 partial ``os.write`` on journal compaction: a short write must not
  publish a truncated journal / drop retained entries.
- #3 read-only source ``EACCES``: a 0444 source must move cleanly without
  the data-fsync reopen hitting EACCES, and dst mode must match source.
- #5 journal UTF-8 encoding: non-ASCII journal paths round-trip via the
  reader regardless of platform default codec.
"""

from __future__ import annotations

import errno
import os
import sys

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.ci]


def _force_exdev(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the first ``os.replace`` raise EXDEV so durable_move takes
    the cross-device branch; subsequent replaces (tmp -> dst) proceed."""
    real_replace = os.replace
    state = {"n": 0}

    def fake_replace(a, b):  # type: ignore[no-untyped-def]
        state["n"] += 1
        if state["n"] == 1:
            raise OSError(errno.EXDEV, "simulated cross-device")
        return real_replace(a, b)

    monkeypatch.setattr("file_organizer.undo.durable_move.os.replace", fake_replace)


# ---------------------------------------------------------------------------
# Fix #1 — started marker journaled before tmp creation
# ---------------------------------------------------------------------------


class TestStartedBeforeTmpOrdering:
    """#1248 #1: in-flight marker must precede the GC-visible tmp window."""

    def test_started_journaled_before_tmp_created(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from file_organizer.undo import durable_move as dm
        from file_organizer.undo.durable_move import durable_move

        _force_exdev(monkeypatch)
        src = tmp_path / "s.txt"
        dst = tmp_path / "d.txt"
        src.write_text("payload")
        journal = tmp_path / "move.journal"

        order: list[str] = []
        real_locked = dm._append_journal_line_locked
        real_open = dm.os.open
        prefix = f".{dst.name}."

        def tracking_locked(j, payload):  # type: ignore[no-untyped-def]
            if payload.get("state") == "started":
                order.append("started")
            return real_locked(j, payload)

        def tracking_open(path, flags, *a, **k):  # type: ignore[no-untyped-def]
            name = os.path.basename(str(path))
            if name.startswith(prefix) and name.endswith(".tmp"):
                order.append("create_tmp")
            return real_open(path, flags, *a, **k)

        monkeypatch.setattr(dm, "_append_journal_line_locked", tracking_locked)
        monkeypatch.setattr(dm.os, "open", tracking_open)

        durable_move(src, dst, journal=journal)

        assert "started" in order and "create_tmp" in order
        assert order.index("started") < order.index("create_tmp"), (
            f"started marker must precede tmp creation; order={order!r}"
        )

    def test_started_entry_carries_tmp_path(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The started row must still carry tmp_path for sweep
        disambiguation (the §7.1 invariant survives the reorder)."""
        from file_organizer.undo.durable_move import _read_journal, durable_move

        _force_exdev(monkeypatch)
        src = tmp_path / "s.txt"
        dst = tmp_path / "d.txt"
        src.write_text("payload")
        journal = tmp_path / "move.journal"

        durable_move(src, dst, journal=journal)

        started = [e for e in _read_journal(journal) if e.state == "started"]
        assert started and started[0].tmp_path, "started entry must record tmp_path for sweep"


# ---------------------------------------------------------------------------
# Fix #2 — partial os.write on compaction
# ---------------------------------------------------------------------------


class TestCompactionShortWrite:
    """#1248 #2: a short os.write must not drop retained entries."""

    def test_short_write_does_not_lose_data(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from file_organizer.undo import durable_move as dm

        tmp = tmp_path / "j.compact.tmp"
        payload = "".join(f'{{"line": {i}}}\n' for i in range(50))

        real_write = os.write

        def short_write(fd, data):  # type: ignore[no-untyped-def]
            # Write at most 8 bytes per call to force the loop to iterate.
            return real_write(fd, data[:8])

        monkeypatch.setattr(dm.os, "write", short_write)

        dm._write_compact_tmp(tmp, payload)

        assert tmp.read_text(encoding="utf-8") == payload, (
            "short writes must be looped until all bytes land — no data loss"
        )

    def test_no_progress_write_raises(self, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
        """A write that returns 0 (no progress) must raise rather than
        spin or publish a truncated file."""
        from file_organizer.undo import durable_move as dm

        tmp = tmp_path / "j.compact.tmp"
        payload = "data\n" * 10

        monkeypatch.setattr(dm.os, "write", lambda fd, data: 0)

        with pytest.raises(OSError, match="no progress"):
            dm._write_compact_tmp(tmp, payload)


# ---------------------------------------------------------------------------
# Fix #3 — read-only source must not EACCES; dst mode matches source
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX mode bits / EACCES semantics")
class TestReadOnlySourceCrossDevice:
    """#1248 #3: a 0444 source moves cleanly cross-device."""

    def test_readonly_source_moves_without_eacces(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from file_organizer.undo.durable_move import durable_move

        _force_exdev(monkeypatch)
        src = tmp_path / "ro.txt"
        dst = tmp_path / "moved.txt"
        src.write_text("read only payload")
        os.chmod(src, 0o444)

        # Must not raise EACCES on the data-fsync reopen.
        durable_move(src, dst, journal=tmp_path / "j.journal")

        assert dst.read_text() == "read only payload"
        # copystat parity: final dst mode equals source mode (0444).
        assert (dst.stat().st_mode & 0o777) == 0o444, (
            "dst mode must match the 0444 source (copystat parity)"
        )
        assert not src.exists()


# ---------------------------------------------------------------------------
# Fix #5 — journal UTF-8 round-trip
# ---------------------------------------------------------------------------


class TestJournalUtf8RoundTrip:
    """#1248 #5: non-ASCII journal paths read back correctly."""

    def test_read_journal_decodes_utf8(self, tmp_path) -> None:
        """Write a journal line as raw UTF-8 bytes (non-ASCII, NOT
        ``\\uXXXX``-escaped) and confirm the reader decodes it as UTF-8.

        This is the load-bearing case for fix #5: with platform-default
        decoding, a locale whose default codec isn't UTF-8 would mojibake
        or raise on these bytes; explicit ``encoding="utf-8"`` round-trips
        them losslessly.
        """
        import json

        from file_organizer.undo.durable_move import _read_journal

        journal = tmp_path / "u.journal"
        unicode_src = "/trash/файл-café-日本語.txt"
        unicode_dst = "/home/файл-café-日本語.txt"
        line = json.dumps(
            {
                "schema": 2,
                "op": "move",
                "op_id": "abc",
                "src": unicode_src,
                "dst": unicode_dst,
                "state": "started",
                "tmp_path": "/trash/.café.tmp",
            },
            ensure_ascii=False,  # force real multi-byte UTF-8 on disk
        )
        journal.write_bytes((line + "\n").encode("utf-8"))

        # Raw bytes on disk are genuine multi-byte UTF-8, not \\u escapes.
        assert "café".encode() in journal.read_bytes()

        entries = _read_journal(journal)
        assert len(entries) == 1
        assert entries[0].src == unicode_src
        assert entries[0].dst == unicode_dst

    def test_in_flight_predicate_matches_unicode_path(self, tmp_path) -> None:
        """The in-flight check works end-to-end on a unicode path even
        when read back from disk."""
        from file_organizer.undo.durable_move import _append_journal, is_path_in_flight

        journal = tmp_path / "u.journal"
        unicode_path = str(tmp_path / "café-日本語.txt")
        _append_journal(
            journal,
            {
                "schema": 2,
                "op": "move",
                "op_id": "abc",
                "src": unicode_path,
                "dst": str(tmp_path / "dest.txt"),
                "state": "started",
                "tmp_path": str(tmp_path / ".dest.tmp"),
            },
        )

        from pathlib import Path

        assert is_path_in_flight(Path(unicode_path), journal=journal) is True
