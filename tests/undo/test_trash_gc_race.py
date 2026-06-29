"""#1248 (WP-1.2b) — pure unit tests for the journal in-flight predicate.

These tests exercise :func:`durable_move._path_in_flight_from_entries`
directly with hand-built :class:`durable_move._JournalEntry` lists — no
filesystem, no locks, no threads. The predicate is the canonical
journal-coordination check that ``TrashGC.safe_delete`` consults under
``LOCK_EX`` to avoid deleting a path an in-flight rollback depends on.

Load-bearing case: ``TestIsPathInFlight.test_dir_move_protects_descendant``
proves the #1248 fix #4 — a ``dir_move`` entry must protect DESCENDANTS
of the moved directory, not just the exact directory path.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from file_organizer.undo.durable_move import (
    OP_DIR_MOVE,
    OP_MOVE,
    STATE_COPIED,
    STATE_DONE,
    STATE_STARTED,
    _JournalEntry,
    _normalized_path_str,
    _path_in_flight_from_entries,
)

pytestmark = [pytest.mark.unit, pytest.mark.ci]


def _norm(p: str) -> str:
    """Normalize a path string the way production writers do."""
    return _normalized_path_str(Path(p))


def _move_entry(src: str, dst: str, state: str) -> _JournalEntry:
    """Build a v2 single-file ``move`` journal entry (normalized paths)."""
    return _JournalEntry(
        op=OP_MOVE,
        src=_norm(src),
        dst=_norm(dst),
        state=state,
        schema=2,
        op_id="op-" + state,
    )


def _dir_move_entry(src: str, dst: str, state: str) -> _JournalEntry:
    """Build a ``dir_move`` journal entry (v1-shape, path-keyed identity)."""
    return _JournalEntry(op=OP_DIR_MOVE, src=_norm(src), dst=_norm(dst), state=state)


class TestIsPathInFlight:
    """Journal-coordination predicate unit tests (#1248)."""

    def test_empty_journal_not_in_flight(self) -> None:
        assert _path_in_flight_from_entries(Path("/trash/a.txt"), []) is False

    def test_exact_src_match_in_flight(self) -> None:
        """A path that is the exact src of an active move is in-flight."""
        entries = [_move_entry("/trash/a.txt", "/home/a.txt", STATE_STARTED)]  # noqa: test-hardcoded-paths
        assert _path_in_flight_from_entries(Path("/trash/a.txt"), entries) is True

    def test_exact_dst_match_in_flight(self) -> None:
        """A path that is the exact dst of an active move is in-flight."""
        entries = [_move_entry("/trash/a.txt", "/home/a.txt", STATE_COPIED)]  # noqa: test-hardcoded-paths
        assert _path_in_flight_from_entries(Path("/home/a.txt"), entries) is True  # noqa: test-hardcoded-paths

    def test_unrelated_path_not_in_flight(self) -> None:
        entries = [_move_entry("/trash/a.txt", "/home/a.txt", STATE_STARTED)]  # noqa: test-hardcoded-paths
        assert _path_in_flight_from_entries(Path("/trash/b.txt"), entries) is False

    def test_done_state_not_in_flight(self) -> None:
        """A completed move no longer protects its paths."""
        entries = [_move_entry("/trash/a.txt", "/home/a.txt", STATE_DONE)]  # noqa: test-hardcoded-paths
        assert _path_in_flight_from_entries(Path("/trash/a.txt"), entries) is False

    def test_latest_state_wins_done_collapses(self) -> None:
        """started → copied → done collapses to done (same op_id): not in flight."""
        entries = [
            _JournalEntry(OP_MOVE, _norm("/t/a"), _norm("/h/a"), STATE_STARTED, 2, "op1"),
            _JournalEntry(OP_MOVE, _norm("/t/a"), _norm("/h/a"), STATE_COPIED, 2, "op1"),
            _JournalEntry(OP_MOVE, _norm("/t/a"), _norm("/h/a"), STATE_DONE, 2, "op1"),
        ]
        assert _path_in_flight_from_entries(Path("/t/a"), entries) is False

    # ------------------------------------------------------------------
    # #1248 fix #4 — dir_move descendant protection (load-bearing)
    # ------------------------------------------------------------------

    def test_dir_move_protects_descendant(self) -> None:
        """#1248 #4: a child of an in-flight ``dir_move`` directory is
        in-flight. Without the fix, only the exact directory matched and
        a GC could delete ``trash/dir/child.txt`` mid-restore."""
        entries = [_dir_move_entry("/trash/dir", "/home/dir", STATE_STARTED)]  # noqa: test-hardcoded-paths
        child = Path("/trash/dir/child.txt")
        assert _path_in_flight_from_entries(child, entries) is True

    def test_dir_move_protects_nested_descendant(self) -> None:
        """Deeply nested descendants are protected too."""
        entries = [_dir_move_entry("/trash/dir", "/home/dir", STATE_STARTED)]  # noqa: test-hardcoded-paths
        nested = Path("/trash/dir/sub/deep/file.txt")
        assert _path_in_flight_from_entries(nested, entries) is True

    def test_dir_move_protects_dst_descendant(self) -> None:
        """Descendants of the dir_move DESTINATION are protected too."""
        entries = [_dir_move_entry("/trash/dir", "/home/dir", STATE_STARTED)]  # noqa: test-hardcoded-paths
        dst_child = Path("/home/dir/child.txt")  # noqa: test-hardcoded-paths
        assert _path_in_flight_from_entries(dst_child, entries) is True

    def test_dir_move_exact_directory_match(self) -> None:
        """The exact dir_move directory itself is in-flight (regression)."""
        entries = [_dir_move_entry("/trash/dir", "/home/dir", STATE_STARTED)]  # noqa: test-hardcoded-paths
        assert _path_in_flight_from_entries(Path("/trash/dir"), entries) is True

    def test_dir_move_sibling_prefix_not_in_flight(self) -> None:
        """A sibling sharing a name PREFIX is NOT a descendant: the
        separator-anchored check must reject ``/trash/dirXYZ`` against
        ancestor ``/trash/dir``."""
        entries = [_dir_move_entry("/trash/dir", "/home/dir", STATE_STARTED)]  # noqa: test-hardcoded-paths
        sibling = Path("/trash/dirXYZ/file.txt")
        assert _path_in_flight_from_entries(sibling, entries) is False

    def test_dir_move_done_does_not_protect_descendant(self) -> None:
        """A completed dir_move no longer protects descendants."""
        entries = [_dir_move_entry("/trash/dir", "/home/dir", STATE_DONE)]  # noqa: test-hardcoded-paths
        child = Path("/trash/dir/child.txt")
        assert _path_in_flight_from_entries(child, entries) is False

    def test_single_file_move_does_not_protect_descendant(self) -> None:
        """A single-file ``move`` (not dir_move) keeps exact-match only —
        a regular file has no descendants, so prefix matching must NOT
        leak in and over-protect unrelated paths."""
        entries = [_move_entry("/trash/file", "/home/file", STATE_STARTED)]  # noqa: test-hardcoded-paths
        # A path that would be a "descendant" of the file path string must
        # not match for a single-file move.
        assert _path_in_flight_from_entries(Path("/trash/file/child"), entries) is False

    def test_relative_query_path_normalizes(self) -> None:
        """The predicate normalizes the query path so a relative path
        equivalent to a stored absolute path still matches."""
        abs_src = os.path.abspath("rel_a.txt")
        entries = [_move_entry(abs_src, "/home/a.txt", STATE_STARTED)]  # noqa: test-hardcoded-paths
        assert _path_in_flight_from_entries(Path("rel_a.txt"), entries) is True
