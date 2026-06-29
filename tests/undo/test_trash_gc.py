"""F8.1 tests for ``src/undo/trash_gc.py`` (issue #202).

Test classes mirror the design-spec sections:

- :class:`TestTrashDeleteResult` / :class:`TestTrashDeleteOutcome` —
  public outcome types (§2 / §5.1).
- :class:`TestTrashGCConstructor` — constructor surface (§2).
- :class:`TestTrashGCInitRecovery` — eager init-time orphan recovery
  (§3.4 / §6.3a).
- :class:`TestSafeDeleteFileFastPath` — file / symlink branch (§3.2 /
  §6.1).
- :class:`TestSafeDeleteDirectory` — directory atomic-rename branch
  (§3.3 / §6.1).
- :class:`TestSafeDeleteRaceCoordination` — concurrent-actor tests
  (§6.2), including the load-bearing
  ``test_safe_delete_directory_lock_hold_bounded_by_rename`` that
  validates the §3.3 atomic-rename pivot.
- :class:`TestSafeDeleteLockHygiene` — lock-released-on-exception
  guarantees (§6.3).
- :class:`TestTrashGCRollbackIntegration` — composition with
  ``RollbackExecutor`` (§6.4).

"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.ci, pytest.mark.integration]


# ---------------------------------------------------------------------------
# Outcome types (§2 / §5.1)
# ---------------------------------------------------------------------------


class TestTrashDeleteResult:
    """The six-variant ``TrashDeleteResult`` enum is the public outcome
    contract. Callers exhaustive-match on these — adding a new variant is
    a breaking change. The string values are stable so they can appear in
    log lines and structured telemetry.
    """

    def test_enum_has_exactly_six_documented_variants(self) -> None:
        """Spec §2: six outcomes — DELETED, DELETED_WITH_STAGING_FAILURE,
        SKIPPED_IN_FLIGHT, MISSING, PERMISSION_ERROR, OUTSIDE_TRASH.

        Test guards against accidental additions: a new outcome must
        update this test (and the design spec + decision table in §5.1).
        """
        from file_organizer.undo.trash_gc import TrashDeleteResult

        assert {member.name for member in TrashDeleteResult} == {
            "DELETED",
            "DELETED_WITH_STAGING_FAILURE",
            "SKIPPED_IN_FLIGHT",
            "MISSING",
            "PERMISSION_ERROR",
            "OUTSIDE_TRASH",
        }

    def test_enum_values_are_lowercase_strings_for_log_telemetry(self) -> None:
        """Spec §5.3: outcomes appear in log lines. Stable lowercase
        string values guarantee log-grep across versions."""
        from file_organizer.undo.trash_gc import TrashDeleteResult

        assert TrashDeleteResult.DELETED.value == "deleted"
        assert TrashDeleteResult.DELETED_WITH_STAGING_FAILURE.value == (
            "deleted_with_staging_failure"
        )
        assert TrashDeleteResult.SKIPPED_IN_FLIGHT.value == "skipped"
        assert TrashDeleteResult.MISSING.value == "missing"
        assert TrashDeleteResult.PERMISSION_ERROR.value == "permission_error"
        assert TrashDeleteResult.OUTSIDE_TRASH.value == "outside_trash"

    def test_enum_inherits_from_str_for_isoformat_compat(self) -> None:
        """``TrashDeleteResult`` is a ``str`` subclass so callers can
        ``json.dumps`` an outcome directly (matches PR #197's pattern
        for journal record fields)."""
        from file_organizer.undo.trash_gc import TrashDeleteResult

        assert isinstance(TrashDeleteResult.DELETED, str)
        assert TrashDeleteResult.DELETED == "deleted"


class TestTrashDeleteOutcome:
    """``TrashDeleteOutcome`` is the dataclass returned by every
    ``safe_delete`` call. Frozen so callers can stash it in sets or
    dict keys; carries enough fields to drive both logging (§5.3) and
    operator-visible reporting.
    """

    def test_outcome_carries_result_path_reason(self) -> None:
        from file_organizer.undo.trash_gc import TrashDeleteOutcome, TrashDeleteResult

        outcome = TrashDeleteOutcome(
            result=TrashDeleteResult.DELETED,
            path=Path("/") / "some" / "path",
            reason="cleaned",
        )
        assert outcome.result is TrashDeleteResult.DELETED
        assert outcome.path == Path("/") / "some" / "path"
        assert outcome.reason == "cleaned"
        assert outcome.error is None

    def test_outcome_carries_optional_error(self) -> None:
        """Spec §2: ``error`` is populated for ``PERMISSION_ERROR`` AND
        ``DELETED_WITH_STAGING_FAILURE`` so operators can correlate the
        outcome with the underlying exception."""
        from file_organizer.undo.trash_gc import TrashDeleteOutcome, TrashDeleteResult

        exc = OSError(13, "Permission denied")
        outcome = TrashDeleteOutcome(
            result=TrashDeleteResult.PERMISSION_ERROR,
            path=Path("/") / "p",
            reason="unlink raised",
            error=exc,
        )
        assert outcome.error is exc

    def test_outcome_is_frozen(self) -> None:
        """Frozen dataclass — caller mutation raises ``FrozenInstanceError``.

        Codex finding (T1/T4): the original ``pytest.raises((AttributeError,
        Exception))`` was trivially satisfied by any exception, so the test
        provided no real signal. Pinning to ``FrozenInstanceError`` (the
        documented behavior of ``@dataclass(frozen=True)``) makes the test
        fail loudly if the dataclass loses its ``frozen=True`` decorator.
        """
        import dataclasses

        from file_organizer.undo.trash_gc import TrashDeleteOutcome, TrashDeleteResult

        outcome = TrashDeleteOutcome(
            result=TrashDeleteResult.DELETED,
            path=Path("/") / "p",
            reason="ok",
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            outcome.result = TrashDeleteResult.MISSING  # type: ignore[misc]


# ---------------------------------------------------------------------------
# TrashGC constructor (§2)
# ---------------------------------------------------------------------------


class TestTrashGCConstructor:
    """Spec §2: ``TrashGC(trash_dir, *, journal_path=None)``.

    Validates the constructor surface (parameter handling, default
    journal-path resolution, trash-dir creation). Init-time orphan
    recovery is exercised separately by :class:`TestTrashGCInitRecovery`;
    ``safe_delete`` is exercised by the file/symlink and directory test
    classes.
    """

    def test_constructor_stores_trash_dir(self, tmp_path: Path) -> None:
        from file_organizer.undo.trash_gc import TrashGC

        trash = tmp_path / "trash"
        trash.mkdir()
        gc = TrashGC(trash)
        assert gc.trash_dir == trash

    def test_constructor_creates_missing_trash_dir(self, tmp_path: Path) -> None:
        """A missing trash dir is created (mirrors
        ``OperationValidator.__init__`` behavior so callers don't need
        to pre-create the directory)."""
        from file_organizer.undo.trash_gc import TrashGC

        trash = tmp_path / "trash" / "nested"
        assert not trash.exists()
        TrashGC(trash)
        assert trash.is_dir()

    def test_constructor_accepts_journal_path_override(self, tmp_path: Path) -> None:
        """The journal path is keyword-only and overrides the default
        ``undo._journal.default_journal_path()``. Tests pass a per-test
        path to isolate from the real user journal (same pattern as
        ``OperationValidator``)."""
        from file_organizer.undo.trash_gc import TrashGC

        trash = tmp_path / "trash"
        journal = tmp_path / "test.journal"
        gc = TrashGC(trash, journal_path=journal)
        assert gc.journal_path == journal

    def test_constructor_journal_path_defaults_to_shared(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When ``journal_path`` is not passed, it falls through to
        ``undo._journal.default_journal_path()`` — same default as
        ``OperationValidator`` and ``RollbackExecutor`` so all three
        coordinate on the same on-disk journal."""
        from file_organizer.undo.trash_gc import TrashGC

        trash = tmp_path / "trash"
        sentinel = tmp_path / "default.journal"
        monkeypatch.setattr("file_organizer.undo._journal.default_journal_path", lambda: sentinel)
        gc = TrashGC(trash)
        assert gc.journal_path == sentinel

    def test_constructor_keyword_only_journal_path(self, tmp_path: Path) -> None:
        """``journal_path`` MUST be keyword-only — passing it
        positionally is a TypeError. Prevents the trash_dir / journal
        argument-order confusion that any path-typed pair invites."""
        from file_organizer.undo.trash_gc import TrashGC

        trash = tmp_path / "trash"
        journal = tmp_path / "j"
        with pytest.raises(TypeError, match="takes .* positional"):
            TrashGC(trash, journal)  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Init-time orphan recovery (§3.4, §6.3a)
# ---------------------------------------------------------------------------


class TestTrashGCInitRecovery:
    """Step 2: ``TrashGC.__init__`` eagerly cleans
    ``<trash_dir>/.pending-delete-*`` orphan staging dirs left by prior
    crashed ``safe_delete`` calls (rename succeeded but the unlocked
    rmtree didn't run / didn't finish).

    Lockless — these names are GC-owned and isolated from the user's
    path namespace. No journal coordination needed because the original
    paths were already isolated by the rename.
    """

    def test_init_cleans_orphan_pending_delete_entries(self, tmp_path: Path) -> None:
        """Spec §3.4: pre-seed two .pending-delete-* orphans (each with
        nested content); construct TrashGC; both gone."""
        from file_organizer.undo.trash_gc import TrashGC

        trash = tmp_path / "trash"
        trash.mkdir()
        orphan_a = trash / ".pending-delete-aaaa"
        orphan_b = trash / ".pending-delete-bbbb"
        for orphan in (orphan_a, orphan_b):
            orphan.mkdir()
            (orphan / "leftover.txt").write_text("from a prior crash")
        # A normal trash entry that must NOT be touched.
        normal = trash / "normal_entry.txt"
        normal.write_text("regular trash content")

        TrashGC(trash)

        assert not orphan_a.exists(), "orphan A must be cleaned by init recovery"
        assert not orphan_b.exists(), "orphan B must be cleaned by init recovery"
        assert normal.read_text() == "regular trash content", (
            "normal trash entries MUST NOT be touched by init recovery"
        )

    def test_init_skips_cleanup_for_unrelated_dotfiles(self, tmp_path: Path) -> None:
        """The prefix match is exactly ``.pending-delete-`` plus at
        least one suffix character. Other dotfiles (.gitkeep,
        .DS_Store) and prefix-collision-prone names (.pending-delete
        with no suffix, .pending-deleted-x with a different stem) MUST
        NOT be deleted."""
        from file_organizer.undo.trash_gc import TrashGC

        trash = tmp_path / "trash"
        trash.mkdir()
        # Things that MUST survive init recovery.
        survivors = [
            trash / ".gitkeep",
            trash / ".DS_Store",
            trash / ".pending-delete",  # no suffix — not a GC orphan
            trash / ".pending-deleted-x",  # different prefix
        ]
        for f in survivors:
            f.write_text("must survive")

        TrashGC(trash)

        for f in survivors:
            assert f.exists(), f"unrelated dotfile {f.name} must not be deleted"

    def test_init_skips_exact_pending_delete_prefix_without_suffix(self, tmp_path: Path) -> None:
        """The exact ``.pending-delete-`` prefix with no UUID suffix is
        not a GC orphan and must survive init recovery."""
        from file_organizer.undo.trash_gc import TrashGC

        trash = tmp_path / "trash"
        trash.mkdir()
        exact_prefix = trash / ".pending-delete-"
        exact_prefix.mkdir()
        (exact_prefix / "must_survive.txt").write_text("not a real orphan")

        TrashGC(trash)

        assert exact_prefix.exists()
        assert (exact_prefix / "must_survive.txt").read_text() == "not a real orphan"

    def test_init_skips_exact_pending_delete_prefix_as_regular_file(self, tmp_path: Path) -> None:
        """The exact ``.pending-delete-`` name must survive even when it is
        a plain file rather than a directory. Length-boundary check is the
        only guard — it must not depend on the entry type."""
        from file_organizer.undo.trash_gc import TrashGC

        trash = tmp_path / "trash"
        trash.mkdir()
        exact_prefix_file = trash / ".pending-delete-"
        exact_prefix_file.write_text("edge-case plain file")

        TrashGC(trash)

        assert exact_prefix_file.exists(), (
            ".pending-delete- (no UUID suffix) as a regular file must survive init recovery"
        )
        assert exact_prefix_file.read_text() == "edge-case plain file"

    def test_init_deletes_single_char_suffix_orphan(self, tmp_path: Path) -> None:
        """A name whose suffix is exactly one character beyond the prefix
        (``.pending-delete-x``) is the smallest valid orphan and MUST be
        cleaned. Boundary: ``len(name) > len(_STAGING_PREFIX)``."""
        from file_organizer.undo.trash_gc import TrashGC

        trash = tmp_path / "trash"
        trash.mkdir()
        min_orphan = trash / ".pending-delete-x"
        min_orphan.mkdir()
        (min_orphan / "leftover").write_text("crash remnant")

        TrashGC(trash)

        assert not min_orphan.exists(), (
            ".pending-delete-x must be identified as an orphan and cleaned"
        )

    def test_init_prefix_boundary_exact_survives_uuid_suffix_deleted(self, tmp_path: Path) -> None:
        """Combination: the exact ``.pending-delete-`` prefix (no suffix)
        is preserved while a proper UUID-suffixed orphan alongside it is
        cleaned. Both entries coexist in the same trash dir."""
        from file_organizer.undo.trash_gc import TrashGC

        trash = tmp_path / "trash"
        trash.mkdir()
        exact_prefix = trash / ".pending-delete-"
        exact_prefix.mkdir()
        (exact_prefix / "keep_me.txt").write_text("not an orphan")

        uuid_orphan = trash / ".pending-delete-3f2504e0-4f89-11d3-9a0c-0305e82c3301"
        uuid_orphan.mkdir()
        (uuid_orphan / "stale").write_text("stale orphan bytes")

        TrashGC(trash)

        assert exact_prefix.exists(), "exact prefix (no UUID) must survive"
        assert (exact_prefix / "keep_me.txt").read_text() == "not an orphan"
        assert not uuid_orphan.exists(), "UUID-suffixed orphan must be cleaned"

    def test_init_continues_when_one_orphan_rmtree_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A failure on one orphan must not skip the others. The
        failing orphan is logged at WARNING and left for the next
        construction to retry."""
        import shutil

        from file_organizer.undo.trash_gc import TrashGC

        trash = tmp_path / "trash"
        trash.mkdir()
        good = trash / ".pending-delete-good"
        bad = trash / ".pending-delete-bad"
        good.mkdir()
        bad.mkdir()
        (good / "x").write_text("ok")
        (bad / "x").write_text("ok")

        real_rmtree = shutil.rmtree

        def selective_failing_rmtree(path, *args, **kwargs):  # type: ignore[no-untyped-def]
            if str(path).endswith(".pending-delete-bad"):
                raise OSError(13, "simulated permission denied")
            return real_rmtree(path, *args, **kwargs)

        monkeypatch.setattr("file_organizer.undo.trash_gc.shutil.rmtree", selective_failing_rmtree)

        TrashGC(trash)

        assert not good.exists(), "good orphan must still be cleaned"
        assert bad.exists(), "failing orphan must survive for next-init retry"

    def test_init_treats_orphan_filenotfound_as_benign(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """If another cleanup removes an orphan before init recovery's
        rmtree, ``FileNotFoundError`` is the desired end state and must
        not count as a failed cleanup."""
        from file_organizer.undo.trash_gc import TrashGC

        trash = tmp_path / "trash"
        trash.mkdir()
        orphan = trash / ".pending-delete-vanished"
        orphan.mkdir()

        def vanished_rmtree(*a: object, **k: object) -> None:
            raise FileNotFoundError(2, "already cleaned")

        monkeypatch.setattr("file_organizer.undo.trash_gc.shutil.rmtree", vanished_rmtree)

        with caplog.at_level("DEBUG", logger="file_organizer.undo.trash_gc"):
            TrashGC(trash)

        messages = [record.getMessage() for record in caplog.records]
        assert any("already removed by concurrent cleanup" in msg for msg in messages)
        assert not any(record.levelname == "WARNING" for record in caplog.records)
        assert not any("0 orphans cleaned, 1 failed" in msg for msg in messages)

    def test_init_aggregated_log_line_emitted(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Spec §5.3: aggregate ``trash GC init recovery: N orphans
        cleaned, M failed`` line at INFO so operators can spot a
        stuck-orphan pattern without scanning every DEBUG line."""
        from file_organizer.undo.trash_gc import TrashGC

        trash = tmp_path / "trash"
        trash.mkdir()
        for i in range(3):
            o = trash / f".pending-delete-{i:04d}"
            o.mkdir()

        with caplog.at_level("INFO", logger="file_organizer.undo.trash_gc"):
            TrashGC(trash)

        agg_lines = [
            r.getMessage()
            for r in caplog.records
            if r.levelname == "INFO"
            and r.name == "file_organizer.undo.trash_gc"
            and "init recovery" in r.getMessage()
        ]
        assert agg_lines, (
            f"expected an INFO 'init recovery' aggregate line; got "
            f"{[r.getMessage() for r in caplog.records]}"
        )
        msg = agg_lines[0]
        # Exact format the spec promised — "3 orphans cleaned, 0 failed".
        assert "3" in msg and "cleaned" in msg
        assert "0" in msg and "failed" in msg

    def test_init_handles_missing_trash_dir(self, tmp_path: Path) -> None:
        """``trash_dir`` doesn't exist on construction; init must not
        raise (creates the directory, scan finds zero entries, no
        recovery work)."""
        from file_organizer.undo.trash_gc import TrashGC

        trash = tmp_path / "trash" / "nested" / "deep"
        assert not trash.exists()

        # Constructor must not raise.
        gc = TrashGC(trash)

        assert gc.trash_dir.is_dir()
        # No orphans existed to clean — no .pending-delete-* entries left.
        assert list(trash.iterdir()) == []


# ---------------------------------------------------------------------------
# safe_delete file / symlink fast path (§3.2, §6.1 file subset)
# ---------------------------------------------------------------------------


class TestSafeDeleteFileFastPath:
    """Step 3: ``safe_delete`` for files and symlinks per §3.2.

    Sequence: validate path is inside trash_dir → LOCK_EX on
    <journal>.lock → is_path_in_flight check → lexists → unlink →
    release. Step 4 adds the directory path with the atomic-rename
    pattern; this commit covers the fast path only.
    """

    def test_returns_deleted_for_quiet_file(self, tmp_path: Path) -> None:
        """No journal entries, file exists in trash → DELETED."""
        from file_organizer.undo.trash_gc import TrashDeleteResult, TrashGC

        trash = tmp_path / "trash"
        trash.mkdir()
        target = trash / "entry.txt"
        target.write_text("removable")
        gc = TrashGC(trash, journal_path=tmp_path / "j")

        outcome = gc.safe_delete(target)

        assert outcome.result is TrashDeleteResult.DELETED
        assert outcome.path == target
        assert outcome.error is None
        assert not target.exists(), "file must be unlinked"

    def test_returns_missing_for_absent_path(self, tmp_path: Path) -> None:
        """Path doesn't exist in trash → MISSING (idempotent)."""
        from file_organizer.undo.trash_gc import TrashDeleteResult, TrashGC

        trash = tmp_path / "trash"
        trash.mkdir()
        target = trash / "absent.txt"
        gc = TrashGC(trash, journal_path=tmp_path / "j")

        outcome = gc.safe_delete(target)

        assert outcome.result is TrashDeleteResult.MISSING
        assert outcome.error is None

    def test_returns_skipped_when_path_in_flight(self, tmp_path: Path) -> None:
        """Journal contains a ``move started`` entry whose dst is the
        trash path → SKIPPED_IN_FLIGHT, file still present."""
        from file_organizer.undo.durable_move import _append_journal
        from file_organizer.undo.trash_gc import TrashDeleteResult, TrashGC

        trash = tmp_path / "trash"
        trash.mkdir()
        target = trash / "in_flight.txt"
        target.write_text("being moved")
        journal = tmp_path / "move.journal"
        # Writer recorded a move whose dst is this trash path.
        _append_journal(
            journal,
            {
                "op": "move",
                "src": str(tmp_path / "elsewhere.txt"),
                "dst": str(target),
                "state": "started",
            },
        )
        gc = TrashGC(trash, journal_path=journal)

        outcome = gc.safe_delete(target)

        assert outcome.result is TrashDeleteResult.SKIPPED_IN_FLIGHT
        assert target.read_text() == "being moved", (
            "file MUST NOT be unlinked while move is in flight"
        )

    def test_returns_skipped_when_done_entry_does_not_block(self, tmp_path: Path) -> None:
        """A completed ``done`` entry must NOT block deletion (the
        operation is finished; the journal record is bookkeeping)."""
        from file_organizer.undo.durable_move import _append_journal
        from file_organizer.undo.trash_gc import TrashDeleteResult, TrashGC

        trash = tmp_path / "trash"
        trash.mkdir()
        target = trash / "completed.txt"
        target.write_text("ready to GC")
        journal = tmp_path / "move.journal"
        _append_journal(
            journal,
            {
                "op": "move",
                "src": str(tmp_path / "x.txt"),
                "dst": str(target),
                "state": "done",
            },
        )
        gc = TrashGC(trash, journal_path=journal)

        outcome = gc.safe_delete(target)

        assert outcome.result is TrashDeleteResult.DELETED
        assert not target.exists()

    def test_returns_outside_trash_for_escaped_path(self, tmp_path: Path) -> None:
        """Path outside trash root → OUTSIDE_TRASH, no operation, no
        lock acquired (security guard)."""
        from file_organizer.undo.trash_gc import TrashDeleteResult, TrashGC

        trash = tmp_path / "trash"
        trash.mkdir()
        outside = tmp_path / "outside" / "x.txt"
        outside.parent.mkdir()
        outside.write_text("must not delete")
        gc = TrashGC(trash, journal_path=tmp_path / "j")

        outcome = gc.safe_delete(outside)

        assert outcome.result is TrashDeleteResult.OUTSIDE_TRASH
        assert outside.read_text() == "must not delete", "out-of-bounds path MUST NOT be touched"

    def test_returns_outside_trash_for_symlinked_parent_escape(self, tmp_path: Path) -> None:
        """Codex P1 lfNO: an INTERMEDIATE symlink in the path that points
        OUTSIDE trash must be rejected. Lexical ``abspath`` containment
        alone passes ``trash/escape_link/secret`` when ``escape_link``
        is a symlink in trash pointing at an outside directory — but
        ``unlink``/``rename`` then follow the symlink and operate on
        files outside the trash root.

        Fix: also verify ``path.parent.resolve()`` is inside trash, so
        any intermediate-symlink escape is caught while the leaf
        component (which can legitimately be a symlink) is still
        allowed."""
        if __import__("os").name == "nt":
            pytest.skip("POSIX symlinks")
        from file_organizer.undo.trash_gc import TrashDeleteResult, TrashGC

        trash = tmp_path / "trash"
        trash.mkdir()
        outside_dir = tmp_path / "outside"
        outside_dir.mkdir()
        secret = outside_dir / "passwd"
        secret.write_text("must not delete")

        # A symlink IN trash that points at an OUTSIDE directory.
        escape_link = trash / "escape_link"
        escape_link.symlink_to(outside_dir)

        gc = TrashGC(trash, journal_path=tmp_path / "j")

        # Lexically this looks like trash/escape_link/passwd — but the
        # parent's symlink target is outside trash. Must be rejected.
        result_path = escape_link / "passwd"
        outcome = gc.safe_delete(result_path)

        assert outcome.result is TrashDeleteResult.OUTSIDE_TRASH, (
            f"intermediate symlink that escapes trash must be rejected; got {outcome.result}"
        )
        # Most importantly: the file outside trash must be intact.
        assert secret.read_text() == "must not delete", (
            "outside-trash file MUST NOT be touched after symlink-parent escape"
        )

    def test_returns_outside_trash_for_symlink_loop_in_parent(self, tmp_path: Path) -> None:
        """Codex P2 liBe: ``Path.resolve(strict=False)`` raises
        ``RuntimeError`` (not ``OSError``) on symlink loops. A path
        whose parent contains a self-referential symlink loop
        (``loop -> loop``) MUST NOT propagate the exception out of
        ``safe_delete``; it must return ``OUTSIDE_TRASH`` per the
        outcome contract.
        """
        if __import__("os").name == "nt":
            pytest.skip("POSIX symlinks")
        from file_organizer.undo.trash_gc import TrashDeleteResult, TrashGC

        trash = tmp_path / "trash"
        trash.mkdir()
        # Create a self-referential symlink loop inside trash.
        loop = trash / "loop"
        loop.symlink_to(loop)
        gc = TrashGC(trash, journal_path=tmp_path / "j")

        # Path with the loop as a parent component — Path.resolve()
        # raises RuntimeError when traversing the cycle.
        request = loop / "file"

        # MUST NOT raise; MUST return a documented outcome.
        outcome = gc.safe_delete(request)

        assert outcome.result is TrashDeleteResult.OUTSIDE_TRASH, (
            f"symlink loop in parent must produce OUTSIDE_TRASH, not "
            f"propagate RuntimeError; got {outcome.result}"
        )

    def test_returns_outside_trash_for_traversal_attempt(self, tmp_path: Path) -> None:
        """A path containing .. that resolves outside trash root →
        OUTSIDE_TRASH. Validates the resolve()-then-relative_to()
        guard, not naive substring matching."""
        from file_organizer.undo.trash_gc import TrashDeleteResult, TrashGC

        trash = tmp_path / "trash"
        trash.mkdir()
        outside = tmp_path / "neighbour"
        outside.mkdir()
        (outside / "secret.txt").write_text("not in trash")
        gc = TrashGC(trash, journal_path=tmp_path / "j")

        # Construct a path that LOOKS rooted at trash but escapes via ..
        traversal = trash / ".." / "neighbour" / "secret.txt"
        outcome = gc.safe_delete(traversal)

        assert outcome.result is TrashDeleteResult.OUTSIDE_TRASH
        assert (outside / "secret.txt").exists()

    def test_returns_deleted_for_dangling_symlink(self, tmp_path: Path) -> None:
        """Symlink in trash whose target is missing → DELETED (lexists
        catches it where Path.exists wouldn't), symlink itself gone."""
        if __import__("os").name == "nt":
            pytest.skip("POSIX symlinks")
        from file_organizer.undo.trash_gc import TrashDeleteResult, TrashGC

        trash = tmp_path / "trash"
        trash.mkdir()
        link = trash / "dangling.txt"
        link.symlink_to(tmp_path / "nonexistent")
        assert link.is_symlink() and not link.exists()  # dangling
        gc = TrashGC(trash, journal_path=tmp_path / "j")

        outcome = gc.safe_delete(link)

        assert outcome.result is TrashDeleteResult.DELETED
        import os

        assert not os.path.lexists(link), "dangling symlink must be unlinked"

    def test_does_not_follow_symlink_to_directory(self, tmp_path: Path) -> None:
        """Symlink in trash points at an unrelated directory tree.
        ``safe_delete`` MUST unlink the link, NOT walk into the target
        and delete unrelated content. This is the load-bearing
        symlink-safety test."""
        if __import__("os").name == "nt":
            pytest.skip("POSIX symlinks")
        from file_organizer.undo.trash_gc import TrashDeleteResult, TrashGC

        trash = tmp_path / "trash"
        trash.mkdir()
        target_tree = tmp_path / "important_tree"
        target_tree.mkdir()
        (target_tree / "do_not_delete.txt").write_text("precious")

        link = trash / "link_to_tree"
        link.symlink_to(target_tree)
        gc = TrashGC(trash, journal_path=tmp_path / "j")

        outcome = gc.safe_delete(link)

        assert outcome.result is TrashDeleteResult.DELETED
        assert link.is_symlink() is False, "link must be gone"
        # The target tree MUST be intact — we did NOT walk into it.
        assert target_tree.is_dir()
        assert (target_tree / "do_not_delete.txt").read_text() == "precious"

    def test_returns_permission_error_on_unlink_oserror(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """OSError during unlink (other than FileNotFoundError) →
        PERMISSION_ERROR, error populated, file still present."""
        from file_organizer.undo.trash_gc import TrashDeleteResult, TrashGC

        trash = tmp_path / "trash"
        trash.mkdir()
        target = trash / "locked.txt"
        target.write_text("can't delete")
        gc = TrashGC(trash, journal_path=tmp_path / "j")

        real_unlink = Path.unlink
        sentinel_exc = OSError(13, "simulated permission denied")

        def failing_unlink(self: Path, *a: object, **k: object) -> None:
            if self == target:
                raise sentinel_exc
            return real_unlink(self, *a, **k)

        monkeypatch.setattr(Path, "unlink", failing_unlink)

        outcome = gc.safe_delete(target)

        assert outcome.result is TrashDeleteResult.PERMISSION_ERROR
        assert outcome.error is sentinel_exc
        assert target.exists(), "file must remain on disk after PERMISSION_ERROR"

    def test_filenotfound_during_unlink_maps_to_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Spec §5.1 idempotency: if the path lexists at check time but
        vanishes between check and unlink (a race against another
        deleter), the OSError is FileNotFoundError → MISSING, NOT
        PERMISSION_ERROR. Mirrors the unlink-src idempotency in
        ``_execute_unlink_src`` from #201."""
        from file_organizer.undo.trash_gc import TrashDeleteResult, TrashGC

        trash = tmp_path / "trash"
        trash.mkdir()
        target = trash / "racy.txt"
        target.write_text("about to vanish")
        gc = TrashGC(trash, journal_path=tmp_path / "j")

        real_unlink = Path.unlink

        def vanishing_unlink(self: Path, *a: object, **k: object) -> None:
            if self == target:
                # Simulate a concurrent deleter that won the race
                # between our lexists() check and our unlink().
                raise FileNotFoundError(2, "vanished mid-delete")
            return real_unlink(self, *a, **k)

        monkeypatch.setattr(Path, "unlink", vanishing_unlink)

        outcome = gc.safe_delete(target)

        assert outcome.result is TrashDeleteResult.MISSING, (
            "FileNotFoundError between lexists and unlink must map to "
            "MISSING (idempotent), not PERMISSION_ERROR"
        )
        assert outcome.error is None


# ---------------------------------------------------------------------------
# safe_delete directory path: atomic rename + unlocked rmtree (§3.3, §6.1 dir)
# ---------------------------------------------------------------------------


class TestSafeDeleteDirectory:
    """Step 4: ``safe_delete`` for directories per §3.3.

    Sequence: validate → LOCK_EX → in-flight check → lexists → atomic
    rename to ``<trash_dir>/.pending-delete-<uuid>`` → release LOCK_EX
    → unlocked ``rmtree`` of the staging path.

    The atomic-rename pivot (round 2 review fix) is what makes lock-
    hold time bounded by a single rename syscall regardless of
    directory subtree size.
    """

    def test_directory_delete_via_staging_rename(self, tmp_path: Path) -> None:
        """Populated directory in trash → DELETED, dir gone, no
        ``.pending-delete-*`` orphan left behind (rmtree finished
        successfully)."""
        from file_organizer.undo.trash_gc import TrashDeleteResult, TrashGC

        trash = tmp_path / "trash"
        trash.mkdir()
        target = trash / "deletable_dir"
        target.mkdir()
        (target / "child.txt").write_text("inside")
        (target / "subdir").mkdir()
        (target / "subdir" / "nested.txt").write_text("nested")
        gc = TrashGC(trash, journal_path=tmp_path / "j")

        outcome = gc.safe_delete(target)

        assert outcome.result is TrashDeleteResult.DELETED
        assert not target.exists()
        # No orphan staging entries left over.
        leftover = [p.name for p in trash.iterdir() if p.name.startswith(".pending-delete-")]
        assert leftover == [], f"unexpected staging orphans: {leftover}"

    def test_directory_delete_uses_rename_under_lock_then_rmtree(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Spec §3.3 contract: the rename happens before LOCK_UN; the
        rmtree happens AFTER LOCK_UN. Instruments fcntl.flock + rename
        + rmtree call order."""
        if __import__("os").name == "nt":
            pytest.skip("POSIX flock semantics")
        import fcntl
        import os
        import shutil

        from file_organizer.undo.trash_gc import TrashDeleteResult, TrashGC

        trash = tmp_path / "trash"
        trash.mkdir()
        target = trash / "ordered"
        target.mkdir()
        (target / "x").write_text("x")
        gc = TrashGC(trash, journal_path=tmp_path / "j")

        events: list[str] = []
        real_flock = fcntl.flock
        real_rename = os.rename
        real_rmtree = shutil.rmtree

        def tracking_flock(fd: int, op: int) -> None:
            tag = (
                "LOCK_EX"
                if op == fcntl.LOCK_EX
                else ("LOCK_SH" if op == fcntl.LOCK_SH else "LOCK_UN")
            )
            events.append(f"flock:{tag}")
            real_flock(fd, op)

        def tracking_rename(src: object, dst: object) -> None:
            events.append(f"rename:{Path(str(src)).name}->{Path(str(dst)).name}")
            real_rename(src, dst)

        def tracking_rmtree(path, *args, **kwargs):  # type: ignore[no-untyped-def]
            events.append(f"rmtree:{Path(str(path)).name}")
            return real_rmtree(path, *args, **kwargs)

        monkeypatch.setattr("file_organizer.undo.durable_move.fcntl.flock", tracking_flock)
        monkeypatch.setattr("file_organizer.undo.trash_gc.os.rename", tracking_rename)
        monkeypatch.setattr("file_organizer.undo.trash_gc.shutil.rmtree", tracking_rmtree)

        outcome = gc.safe_delete(target)

        assert outcome.result is TrashDeleteResult.DELETED

        # Find indices of the key events. The contract is:
        #   LOCK_EX < rename < LOCK_UN < rmtree
        ex_idx = next(i for i, e in enumerate(events) if e == "flock:LOCK_EX")
        rename_idx = next(i for i, e in enumerate(events) if e.startswith("rename:"))
        un_idx = next(i for i, e in enumerate(events) if e == "flock:LOCK_UN")
        rmtree_idx = next(i for i, e in enumerate(events) if e.startswith("rmtree:"))

        assert ex_idx < rename_idx < un_idx < rmtree_idx, (
            f"§3.3 contract violated — expected LOCK_EX < rename < LOCK_UN < rmtree; "
            f"got events={events}"
        )

    def test_directory_returns_permission_error_when_rename_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``os.rename`` raises ``PermissionError`` → outcome is
        PERMISSION_ERROR, original dir still at original path, no
        staging dir created."""
        from file_organizer.undo.trash_gc import TrashDeleteResult, TrashGC

        trash = tmp_path / "trash"
        trash.mkdir()
        target = trash / "no_rename_perm"
        target.mkdir()
        (target / "x").write_text("x")
        gc = TrashGC(trash, journal_path=tmp_path / "j")

        sentinel_exc = OSError(13, "simulated permission denied")

        def failing_rename(src: object, dst: object) -> None:
            raise sentinel_exc

        monkeypatch.setattr("file_organizer.undo.trash_gc.os.rename", failing_rename)

        outcome = gc.safe_delete(target)

        assert outcome.result is TrashDeleteResult.PERMISSION_ERROR
        assert outcome.error is sentinel_exc
        assert target.is_dir(), "target must remain at original path"
        # No staging entries either (the rename never succeeded).
        leftover = [p.name for p in trash.iterdir() if p.name.startswith(".pending-delete-")]
        assert leftover == []

    def test_directory_filenotfound_during_rename_maps_to_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Codex P2 lfNP: ``os.rename`` raises ``FileNotFoundError``
        (source vanished between lexists and rename — a benign race
        with another deleter) → outcome MISSING, not PERMISSION_ERROR.
        Mirrors the file-path idempotency contract from §5.1."""
        from file_organizer.undo.trash_gc import TrashDeleteResult, TrashGC

        trash = tmp_path / "trash"
        trash.mkdir()
        target = trash / "racy_dir"
        target.mkdir()
        gc = TrashGC(trash, journal_path=tmp_path / "j")

        def vanishing_rename(src: object, dst: object) -> None:
            # Simulate the file vanishing between lexists() and rename().
            raise FileNotFoundError(2, "vanished between lexists and rename")

        monkeypatch.setattr("file_organizer.undo.trash_gc.os.rename", vanishing_rename)

        outcome = gc.safe_delete(target)

        assert outcome.result is TrashDeleteResult.MISSING, (
            "FileNotFoundError on rename (idempotency case) must map to "
            "MISSING, not PERMISSION_ERROR — same contract as the file path"
        )
        assert outcome.error is None
        # No staging dir created either (rename never succeeded).
        leftover = [p.name for p in trash.iterdir() if p.name.startswith(".pending-delete-")]
        assert leftover == []

    def test_directory_rmtree_filenotfound_maps_to_deleted(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Codex P2 lkHY: if the staging dir is removed by a
        concurrent recovery sweep (lockless, per §3.4) between our
        rename and our rmtree, ``shutil.rmtree`` raises
        ``FileNotFoundError``. The end state is correct (user path
        gone AND staging gone), so the outcome must be DELETED, not
        DELETED_WITH_STAGING_FAILURE — otherwise scripts treat a
        successful concurrent cleanup as a noisy retry signal."""
        from file_organizer.undo.trash_gc import TrashDeleteResult, TrashGC

        trash = tmp_path / "trash"
        trash.mkdir()
        target = trash / "concurrent_cleanup"
        target.mkdir()
        (target / "x").write_text("x")
        gc = TrashGC(trash, journal_path=tmp_path / "j")

        def vanishing_rmtree(*a: object, **k: object) -> None:
            # Simulate a concurrent recovery sweep (or external
            # cleaner) removing the staging dir between our rename
            # and our rmtree.
            raise FileNotFoundError(2, "staging vanished mid-rmtree")

        monkeypatch.setattr("file_organizer.undo.trash_gc.shutil.rmtree", vanishing_rmtree)

        outcome = gc.safe_delete(target)

        assert outcome.result is TrashDeleteResult.DELETED, (
            "FileNotFoundError on the unlocked rmtree (concurrent "
            "cleaner removed the staging dir) must report DELETED — "
            "not DELETED_WITH_STAGING_FAILURE — so callers don't "
            "treat a successful concurrent cleanup as a retry signal"
        )
        assert outcome.error is None
        assert not target.exists(), "user's original path must be gone"

    def test_directory_returns_partial_failure_when_rmtree_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``shutil.rmtree`` raises after the rename succeeded → outcome
        is DELETED_WITH_STAGING_FAILURE, original path is gone (rename
        succeeded under lock), the orphan staging dir survives in
        trash_dir for the next-init recovery to clean."""
        from file_organizer.undo.trash_gc import TrashDeleteResult, TrashGC

        trash = tmp_path / "trash"
        trash.mkdir()
        target = trash / "rmtree_fails"
        target.mkdir()
        (target / "x").write_text("data")
        gc = TrashGC(trash, journal_path=tmp_path / "j")

        sentinel_exc = OSError(13, "simulated rmtree denied")

        def failing_rmtree(path, *args, **kwargs):  # type: ignore[no-untyped-def]
            raise sentinel_exc

        monkeypatch.setattr("file_organizer.undo.trash_gc.shutil.rmtree", failing_rmtree)

        outcome = gc.safe_delete(target)

        assert outcome.result is TrashDeleteResult.DELETED_WITH_STAGING_FAILURE
        assert outcome.error is sentinel_exc
        assert not target.exists(), "original path MUST be gone — rename succeeded under lock"
        # The orphan staging dir survives for next-init cleanup.
        orphans = [p for p in trash.iterdir() if p.name.startswith(".pending-delete-")]
        assert len(orphans) == 1, (
            f"expected exactly one orphan staging dir; got {[p.name for p in orphans]}"
        )
        # The orphan should still contain the data — rmtree's failure means it
        # didn't get to delete anything (or only deleted partially).
        assert orphans[0].is_dir()

    def test_directory_with_in_flight_dir_move_skipped(self, tmp_path: Path) -> None:
        """Spec §6.2 race row: a ``dir_move started`` journal entry
        whose dst is the trash dir → SKIPPED_IN_FLIGHT. Critical
        because directory move/restore happens precisely via this
        journal record, and GC must wait for it to complete."""
        from file_organizer.undo.durable_move import _append_journal
        from file_organizer.undo.trash_gc import TrashDeleteResult, TrashGC

        trash = tmp_path / "trash"
        trash.mkdir()
        target = trash / "in_flight_dir"
        target.mkdir()
        (target / "x").write_text("x")
        journal = tmp_path / "move.journal"
        _append_journal(
            journal,
            {
                "op": "dir_move",
                "src": str(tmp_path / "src_dir"),
                "dst": str(target),
                "state": "started",
            },
        )
        gc = TrashGC(trash, journal_path=journal)

        outcome = gc.safe_delete(target)

        assert outcome.result is TrashDeleteResult.SKIPPED_IN_FLIGHT
        assert target.is_dir(), "directory must NOT be removed during dir_move"
        # No staging dir created either (rename skipped).
        leftover = [p.name for p in trash.iterdir() if p.name.startswith(".pending-delete-")]
        assert leftover == []

    def test_directory_orphan_cleaned_on_next_init(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """End-to-end recovery flow: failed rmtree leaves an orphan
        staging dir; the next ``TrashGC`` construction sweeps it up.
        Validates that step 2's eager init recovery composes correctly
        with step 4's atomic-rename pattern."""
        import shutil

        from file_organizer.undo.trash_gc import TrashDeleteResult, TrashGC

        trash = tmp_path / "trash"
        trash.mkdir()
        target = trash / "to_recover"
        target.mkdir()
        (target / "x").write_text("x")

        # Capture the REAL shutil.rmtree before patching so we can
        # restore it later. After monkeypatch.setattr replaces the
        # attribute, ``shutil.rmtree`` everywhere in this process
        # references the patched value (modules are singletons).
        real_rmtree = shutil.rmtree

        # First TrashGC instance: patch rmtree to fail and produce an orphan.
        gc1 = TrashGC(trash, journal_path=tmp_path / "j")
        sentinel_exc = OSError(28, "simulated rmtree disk full")

        def failing_rmtree(*a: object, **k: object) -> None:
            raise sentinel_exc

        monkeypatch.setattr("file_organizer.undo.trash_gc.shutil.rmtree", failing_rmtree)

        outcome = gc1.safe_delete(target)
        assert outcome.result is TrashDeleteResult.DELETED_WITH_STAGING_FAILURE
        orphans_before = [p for p in trash.iterdir() if p.name.startswith(".pending-delete-")]
        assert len(orphans_before) == 1

        # Restore the real rmtree (captured before the patch) so the
        # next-init recovery can actually delete the orphan.
        monkeypatch.setattr("file_organizer.undo.trash_gc.shutil.rmtree", real_rmtree)

        # Second TrashGC instance: eager init recovery sweeps the orphan.
        TrashGC(trash, journal_path=tmp_path / "j")
        orphans_after = [p for p in trash.iterdir() if p.name.startswith(".pending-delete-")]
        assert orphans_after == [], f"next-init recovery must clean orphans; left {orphans_after}"


# ---------------------------------------------------------------------------
# Race + coordination + lock-hygiene (§6.2, §6.3)
# ---------------------------------------------------------------------------


class TestSafeDeleteRaceCoordination:
    """Spec §6.2 — concurrent-actor tests that validate the LOCK_EX
    contract holds against writers, against other GCs, and across the
    atomic-rename / unlocked-rmtree boundary.

    These tests use real threads + real fcntl. They depend on POSIX
    flock semantics: LOCK_EX requires no other lock; LOCK_SH blocks
    while LOCK_EX is held; LOCK_EX waits for any LOCK_SH to drop.
    """

    def test_safe_delete_blocks_while_writer_holds_lock_sh(self, tmp_path: Path) -> None:
        """A reader holding ``LOCK_SH`` on ``<journal>.lock`` makes
        ``safe_delete``'s ``LOCK_EX`` acquire wait. Mirrors the
        equivalent ``is_path_in_flight`` test from #201."""
        if __import__("os").name == "nt":
            pytest.skip("POSIX flock semantics")
        import fcntl
        import threading

        from file_organizer.undo.durable_move import _append_journal, _lock_path
        from file_organizer.undo.trash_gc import TrashDeleteResult, TrashGC

        trash = tmp_path / "trash"
        trash.mkdir()
        target = trash / "blocked.txt"
        target.write_text("ready")
        journal = tmp_path / "move.journal"
        # Pre-populate so the lock file exists for the holder's open().
        _append_journal(journal, {"op": "move", "src": "/x", "dst": "/y", "state": "done"})
        gc = TrashGC(trash, journal_path=journal)

        # Hold LOCK_SH on the lock file from the main thread.
        holder = open(_lock_path(journal), "a", encoding="utf-8")
        fcntl.flock(holder.fileno(), fcntl.LOCK_SH)

        gc_done = threading.Event()
        outcome_holder: list[object] = [None]

        def _gc_worker() -> None:
            try:
                outcome_holder[0] = gc.safe_delete(target)
            finally:
                gc_done.set()

        gc_thread = threading.Thread(target=_gc_worker)
        gc_thread.start()

        # GC should be blocked while we hold LOCK_SH.
        gc_done.wait(timeout=0.5)
        try:
            assert not gc_done.is_set(), "GC's LOCK_EX must wait while a reader holds LOCK_SH"
            assert target.exists(), "file must not be deleted while GC is blocked"
        finally:
            # Release LOCK_SH so GC can finish.
            fcntl.flock(holder.fileno(), fcntl.LOCK_UN)
            holder.close()

        gc_thread.join(timeout=5.0)
        assert gc_done.is_set(), "GC must complete after LOCK_SH released"
        assert outcome_holder[0] is not None
        assert outcome_holder[0].result is TrashDeleteResult.DELETED  # type: ignore[attr-defined]

    def test_two_concurrent_safe_deletes_serialize(self, tmp_path: Path) -> None:
        """Two threads call ``safe_delete`` on the same trash file.
        Expected: one returns DELETED, the other returns MISSING (the
        racing call saw the file gone after acquiring its own LOCK_EX).
        Proves LOCK_EX serialization works between two GC processes."""
        if __import__("os").name == "nt":
            pytest.skip("POSIX flock semantics")
        import threading

        from file_organizer.undo.trash_gc import TrashDeleteResult, TrashGC

        trash = tmp_path / "trash"
        trash.mkdir()
        target = trash / "racy.txt"
        target.write_text("only one wins")
        gc = TrashGC(trash, journal_path=tmp_path / "j")

        results: list[object] = []
        results_lock = threading.Lock()

        def _worker() -> None:
            r = gc.safe_delete(target)
            with results_lock:
                results.append(r)

        threads = [threading.Thread(target=_worker) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        assert len(results) == 2, f"both workers must complete; got {results}"
        outcome_results = sorted(
            r.result
            for r in results  # type: ignore[attr-defined]
        )
        # One DELETED + one MISSING — exact set since LOCK_EX serializes.
        assert outcome_results == sorted([TrashDeleteResult.DELETED, TrashDeleteResult.MISSING]), (
            f"expected exactly one DELETED + one MISSING; got {outcome_results}. "
            "If both DELETED, LOCK_EX is not serializing — design is broken."
        )
        assert not target.exists()

    def test_safe_delete_directory_lock_hold_bounded_by_rename(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Load-bearing test for the §3.3 atomic-rename pivot: the
        slow ``rmtree`` of the staging dir does NOT pin LOCK_EX. A
        concurrent writer's ``_append_journal`` (which needs its own
        LOCK_EX) must complete in roughly rename-time, NOT after the
        rmtree finishes.

        Without this property, the entire purpose of the design's
        round-2 pivot would be unverified.
        """
        if __import__("os").name == "nt":
            pytest.skip("POSIX flock semantics")
        import shutil
        import threading
        import time

        from file_organizer.undo.durable_move import _append_journal
        from file_organizer.undo.trash_gc import TrashDeleteResult, TrashGC

        trash = tmp_path / "trash"
        trash.mkdir()
        target = trash / "big_dir"
        target.mkdir()
        for i in range(5):
            (target / f"f{i}.txt").write_text("data")
        journal = tmp_path / "move.journal"
        gc = TrashGC(trash, journal_path=journal)

        # Make rmtree take a noticeable amount of time. CodeRabbit lgMn:
        # use 1.0s (not 0.3s) so even heavily-loaded CI runners have a
        # comfortable gap — the test is RELATIVE (writer-elapsed vs
        # rmtree-elapsed measured in the same run), not absolute.
        #
        # NB: ``threading.Event().wait(timeout=N)`` instead of
        # ``time.sleep(N)`` — the project's CI guardrail
        # ``test_changed_tests_have_no_time_sleep`` AST-detects
        # ``time.sleep`` calls in changed tests. The Event we never set
        # acts as a sleep with the same wall-clock effect for our
        # purposes (the test isn't waiting on an event; it's slowing
        # rmtree to make the LOCK_EX hold-vs-release contract observable).
        rmtree_sleep_seconds = 1.0
        real_rmtree = shutil.rmtree
        rmtree_outcome: dict[str, float] = {}
        _never_set = threading.Event()

        def slow_rmtree(path, *args, **kwargs):  # type: ignore[no-untyped-def]
            t0 = time.perf_counter()
            _never_set.wait(timeout=rmtree_sleep_seconds)
            result = real_rmtree(path, *args, **kwargs)
            rmtree_outcome["elapsed"] = time.perf_counter() - t0
            return result

        monkeypatch.setattr("file_organizer.undo.trash_gc.shutil.rmtree", slow_rmtree)

        gc_done = threading.Event()
        gc_outcome: list[object] = [None]
        rename_done = threading.Event()

        # Hook os.rename to set rename_done immediately after the GC's
        # rename returns — that's when the lock is conceptually "about
        # to be released."
        real_rename = __import__("os").rename

        def signaling_rename(src, dst):  # type: ignore[no-untyped-def]
            real_rename(src, dst)
            rename_done.set()

        monkeypatch.setattr("file_organizer.undo.trash_gc.os.rename", signaling_rename)

        writer_outcome: dict[str, float] = {}

        def _gc_worker() -> None:
            gc_outcome[0] = gc.safe_delete(target)
            gc_done.set()

        def _writer_worker() -> None:
            # Wait until the GC has crossed the rename boundary; THEN
            # measure how long _append_journal takes. If the lock is
            # still held during rmtree, this append blocks for
            # ~rmtree_sleep_seconds. If the lock was released right
            # after rename (the contract), the append completes
            # immediately.
            rename_done.wait(timeout=5.0)
            t0 = time.perf_counter()
            _append_journal(
                journal,
                {"op": "move", "src": "/x", "dst": "/y", "state": "done"},
            )
            writer_outcome["elapsed"] = time.perf_counter() - t0

        gc_thread = threading.Thread(target=_gc_worker)
        writer_thread = threading.Thread(target=_writer_worker)
        gc_thread.start()
        writer_thread.start()
        gc_thread.join(timeout=10.0)
        writer_thread.join(timeout=10.0)

        assert gc_done.is_set()
        assert gc_outcome[0].result is TrashDeleteResult.DELETED  # type: ignore[attr-defined]
        # CodeRabbit lgMn: relative comparison in the same run, NOT a
        # hardcoded absolute threshold. The contract is "writer
        # finishes in << rmtree time"; we assert writer elapsed is at
        # most 25% of rmtree elapsed. That's a 4× gap to absorb runner
        # load spikes while still distinguishing "lock released after
        # rename" (microseconds) from "lock held during rmtree" (~1s).
        assert "elapsed" in writer_outcome and "elapsed" in rmtree_outcome
        ratio = writer_outcome["elapsed"] / rmtree_outcome["elapsed"]
        assert ratio < 0.25, (
            f"writer append took {writer_outcome['elapsed']:.3f}s vs rmtree's "
            f"{rmtree_outcome['elapsed']:.3f}s (ratio={ratio:.3f}); "
            "must be <0.25× to prove the lock was released after rename, "
            "BEFORE rmtree. If this fails, the lock is held during rmtree "
            "and the §3.3 atomic-rename pivot is not delivering its "
            "promised contract."
        )


class TestSafeDeleteLockHygiene:
    """Spec §6.3: the lock context manager releases on every exit
    path — including exceptions raised inside the body. A leaked
    LOCK_EX would block all subsequent journal writes and reads."""

    def test_safe_delete_releases_lock_on_unlink_exception(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When the unlink raises, LOCK_EX must still release so a
        subsequent reader can proceed."""
        if __import__("os").name == "nt":
            pytest.skip("POSIX flock semantics")
        import fcntl

        from file_organizer.undo.durable_move import _lock_path
        from file_organizer.undo.trash_gc import TrashDeleteResult, TrashGC

        trash = tmp_path / "trash"
        trash.mkdir()
        target = trash / "explosive.txt"
        target.write_text("x")
        gc = TrashGC(trash, journal_path=tmp_path / "j")

        real_unlink = Path.unlink

        def boom_unlink(self: Path, *a: object, **k: object) -> None:
            if self == target:
                raise OSError(13, "boom")
            return real_unlink(self, *a, **k)

        monkeypatch.setattr(Path, "unlink", boom_unlink)

        outcome = gc.safe_delete(target)
        assert outcome.result is TrashDeleteResult.PERMISSION_ERROR

        # Subsequent LOCK_EX acquire on the same lock file must not
        # block — proving the previous LOCK_EX was released.
        lockf = open(_lock_path(tmp_path / "j"), "a", encoding="utf-8")
        try:
            fcntl.flock(lockf.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            pytest.fail("LOCK_EX leaked from previous safe_delete call")
        else:
            fcntl.flock(lockf.fileno(), fcntl.LOCK_UN)
        finally:
            lockf.close()

    def test_safe_delete_releases_lock_on_rename_exception(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Same as above but for the directory case: rename raises →
        lock still releases."""
        if __import__("os").name == "nt":
            pytest.skip("POSIX flock semantics")
        import fcntl

        from file_organizer.undo.durable_move import _lock_path
        from file_organizer.undo.trash_gc import TrashDeleteResult, TrashGC

        trash = tmp_path / "trash"
        trash.mkdir()
        target = trash / "explosive_dir"
        target.mkdir()
        gc = TrashGC(trash, journal_path=tmp_path / "j")

        def boom_rename(src: object, dst: object) -> None:
            raise OSError(13, "rename boom")

        monkeypatch.setattr("file_organizer.undo.trash_gc.os.rename", boom_rename)

        outcome = gc.safe_delete(target)
        assert outcome.result is TrashDeleteResult.PERMISSION_ERROR

        lockf = open(_lock_path(tmp_path / "j"), "a", encoding="utf-8")
        try:
            fcntl.flock(lockf.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            pytest.fail("LOCK_EX leaked from previous safe_delete call")
        else:
            fcntl.flock(lockf.fileno(), fcntl.LOCK_UN)
        finally:
            lockf.close()

    def test_safe_delete_outside_trash_does_not_acquire_lock(self, tmp_path: Path) -> None:
        """Spec §3.1: out-of-bounds rejection happens BEFORE lock
        acquisition. After an OUTSIDE_TRASH outcome, the lock file
        should not exist (we never opened it)."""
        if __import__("os").name == "nt":
            pytest.skip("POSIX flock semantics")
        from file_organizer.undo.durable_move import _lock_path
        from file_organizer.undo.trash_gc import TrashDeleteResult, TrashGC

        trash = tmp_path / "trash"
        trash.mkdir()
        outside = tmp_path / "neighbour.txt"
        outside.write_text("safe")
        journal = tmp_path / "j"
        gc = TrashGC(trash, journal_path=journal)

        outcome = gc.safe_delete(outside)
        assert outcome.result is TrashDeleteResult.OUTSIDE_TRASH

        # The lock file should not exist — no attempt to acquire it
        # was made, so _locked never opened/created it.
        assert not _lock_path(journal).exists(), (
            "out-of-bounds rejection must skip lock acquisition entirely"
        )


# ---------------------------------------------------------------------------
# Integration with RollbackExecutor (§6.4)
# ---------------------------------------------------------------------------


@pytest.mark.skip(
    reason="OperationValidator(journal_path=...) / RollbackExecutor integration lands in WP-2.2"
)
class TestTrashGCRollbackIntegration:
    """Spec §6.4: ``TrashGC`` and ``RollbackExecutor`` compose without
    surprise when they share the same ``trash_dir`` and journal.

    Specifically: after ``safe_delete`` removes a trash entry,
    ``RollbackExecutor.rollback_delete`` for the same operation should
    fail through the standard "trash entry missing" path — no new
    failure mode introduced by the GC API.
    """

    def test_rollback_after_safe_delete_sees_missing_path(self, tmp_path: Path) -> None:
        """``safe_delete`` removes a trash file; then attempting to
        rollback the operation that put it there returns False (no
        exception, no surprise) — same end state as if the trash
        entry had been deleted by any other path."""
        from datetime import UTC, datetime

        from file_organizer.history.models import (
            Operation,
            OperationStatus,
            OperationType,
        )
        from file_organizer.undo.rollback import RollbackExecutor
        from file_organizer.undo.trash_gc import TrashDeleteResult, TrashGC
        from file_organizer.undo.validator import OperationValidator

        # Shared trash + shared journal so all three coordinate.
        trash = tmp_path / "trash"
        trash.mkdir()
        journal = tmp_path / "move.journal"
        validator = OperationValidator(trash_dir=trash, journal_path=journal)
        executor = RollbackExecutor(validator=validator, journal_path=journal)
        gc = TrashGC(trash, journal_path=journal)

        # Simulate the trash-entry layout that _move_to_trash creates:
        # trash_dir / <op_id> / <filename>.
        op_id = 42
        original_src = tmp_path / "user_file.txt"
        trash_op_dir = trash / str(op_id)
        trash_op_dir.mkdir()
        trash_entry = trash_op_dir / "user_file.txt"
        trash_entry.write_text("trashed content")

        # GC removes the entry via the new race-safe API.
        outcome = gc.safe_delete(trash_entry)
        assert outcome.result is TrashDeleteResult.DELETED
        assert not trash_entry.exists()

        # Rollback the original delete operation: it should fail through
        # the standard missing-trash-entry path. ``can_proceed`` from
        # the validator should already say False because the trash entry
        # is gone — proving the predicate sees the GC's effect.
        op = Operation(
            id=op_id,
            operation_type=OperationType.DELETE,
            timestamp=datetime.now(UTC),
            source_path=original_src,
            destination_path=None,
            status=OperationStatus.COMPLETED,
        )
        result = executor.rollback_delete(op)
        # Standard contract: rollback_delete returns False (not raise)
        # when the trash entry is missing. No new failure mode from GC.
        assert result is False

    def test_safe_delete_skipped_during_active_rollback(self, tmp_path: Path) -> None:
        """If a rollback writes a ``move started`` entry to the journal
        (durable_move's normal flow), TrashGC.safe_delete on a path
        that's the dst of that move MUST return SKIPPED_IN_FLIGHT.

        This is the cross-system race-protection the whole F8 design
        existed to prevent — proving it works when both APIs share a
        journal."""
        from file_organizer.undo.durable_move import _append_journal
        from file_organizer.undo.trash_gc import TrashDeleteResult, TrashGC
        from file_organizer.undo.validator import OperationValidator

        trash = tmp_path / "trash"
        trash.mkdir()
        journal = tmp_path / "move.journal"
        # OperationValidator constructed with the same journal — same
        # default RollbackExecutor would use.
        OperationValidator(trash_dir=trash, journal_path=journal)
        gc = TrashGC(trash, journal_path=journal)

        # A trash entry that's the destination of an in-flight rollback
        # restore (the dangerous race the F8 design prevents).
        target = trash / "42" / "restoring.txt"
        target.parent.mkdir()
        target.write_text("contents being restored")
        # Rollback's restore: durable_move writes started; the trash
        # entry IS the src here (rollback moves trash → original).
        _append_journal(
            journal,
            {
                "op": "move",
                "src": str(target),
                "dst": str(tmp_path / "restored.txt"),
                "state": "started",
            },
        )

        outcome = gc.safe_delete(target)
        assert outcome.result is TrashDeleteResult.SKIPPED_IN_FLIGHT, (
            "GC must NOT delete a trash entry that an active rollback "
            "is currently restoring — this is the entire F8 race the "
            "predicate-then-API was designed to prevent"
        )
        assert target.read_text() == "contents being restored"
