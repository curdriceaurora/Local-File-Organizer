"""Tests for the ``fo recover`` CLI command (F7.1 step 8 / §8.2).

The command reads the durable_move journal under ``LOCK_SH`` (per §6.5),
calls the pure ``plan_recovery_actions`` planner, and renders the plan
as a table for operator visibility — no disk mutation.

Exit-code contract:

- ``0`` if the plan is empty (no actionable retained entries).
- ``1`` if any action would be taken (so scripts can detect "needs cleanup").

Per §9.6 test plan items:

- empty / missing journal → exit 0, "no retained entries" rendered.
- retained entries → exit 1, formatted table with op/state/src/dst/verb/reason.
- v2 ``move started`` rows include the §5.1 disambiguation tier in the reason.
- planner is pure: invoking the CLI MUST NOT mutate any file on disk.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

pytestmark = [pytest.mark.unit, pytest.mark.ci, pytest.mark.integration]


# ---------------------------------------------------------------------------
# Fixtures + helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def runner() -> CliRunner:
    """Per-test Typer runner for explicitness."""
    return CliRunner()


def _write_journal_lines(journal: Path, entries: list[dict]) -> None:
    """Write JSONL entries directly (bypassing the writer's lock — fine
    in tests since we control the only writer)."""
    journal.parent.mkdir(parents=True, exist_ok=True)
    journal.write_text("\n".join(json.dumps(e) for e in entries) + "\n")


# ---------------------------------------------------------------------------
# Public reader contract
# ---------------------------------------------------------------------------


class TestReadJournalUnderSharedLock:
    """``read_journal_under_shared_lock`` is the public reader the CLI
    uses — acquires ``LOCK_SH`` on ``<journal>.lock`` (per §6.1) and
    returns parsed entries. Missing journal → empty list (no-op)."""

    def test_missing_journal_returns_empty(self, tmp_path: Path) -> None:
        from file_organizer.undo.durable_move import read_journal_under_shared_lock

        journal = tmp_path / "absent.journal"
        assert read_journal_under_shared_lock(journal) == []

    def test_empty_journal_returns_empty(self, tmp_path: Path) -> None:
        from file_organizer.undo.durable_move import read_journal_under_shared_lock

        journal = tmp_path / "empty.journal"
        journal.write_text("")
        assert read_journal_under_shared_lock(journal) == []

    def test_returns_parsed_entries(self, tmp_path: Path) -> None:
        from file_organizer.undo.durable_move import read_journal_under_shared_lock

        journal = tmp_path / "move.journal"
        _write_journal_lines(
            journal,
            [
                {"op": "move", "src": "/a", "dst": "/b", "state": "started"},
                {"op": "move", "src": "/a", "dst": "/b", "state": "copied"},
            ],
        )
        entries = read_journal_under_shared_lock(journal)
        assert len(entries) == 2
        assert entries[0].state == "started"
        assert entries[1].state == "copied"


# ---------------------------------------------------------------------------
# CLI command
# ---------------------------------------------------------------------------


class TestRecoverCommand:
    """``fo recover`` end-to-end: invoke through the Typer app, assert
    on exit code + rendered output."""

    def test_recover_missing_journal_exits_zero(
        self, tmp_path: Path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No journal on disk → no retained entries → exit 0."""
        from file_organizer.cli.main import app

        monkeypatch.setattr(
            "file_organizer.undo._journal.default_journal_path", lambda: tmp_path / "absent.journal"
        )

        result = runner.invoke(app, ["recover"])
        assert result.exit_code == 0, result.output
        assert "no retained entries" in result.output.lower(), result.output

    def test_recover_empty_journal_exits_zero(
        self, tmp_path: Path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Journal exists but is empty → no retained entries → exit 0."""
        from file_organizer.cli.main import app

        journal = tmp_path / "empty.journal"
        journal.write_text("")
        monkeypatch.setattr("file_organizer.undo._journal.default_journal_path", lambda: journal)

        result = runner.invoke(app, ["recover"])
        assert result.exit_code == 0, result.output

    def test_recover_done_only_exits_zero(
        self, tmp_path: Path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Journal with only ``done`` entries → planner emits ``drop``
        verbs; no retained actions → exit 0."""
        from file_organizer.cli.main import app

        journal = tmp_path / "move.journal"
        _write_journal_lines(journal, [{"op": "move", "src": "/x", "dst": "/y", "state": "done"}])
        monkeypatch.setattr("file_organizer.undo._journal.default_journal_path", lambda: journal)

        result = runner.invoke(app, ["recover"])
        assert result.exit_code == 0, result.output

    def test_recover_copied_with_dst_present_exits_one(
        self, tmp_path: Path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``copied`` with dst present → planner emits
        ``unlink_src_then_drop`` → actionable → exit 1.

        Critical: invoking ``recover`` MUST NOT execute the unlink
        (planner is pure). src remains on disk after the command."""
        from file_organizer.cli.main import app

        src = tmp_path / "src.txt"
        dst = tmp_path / "dst.txt"
        src.write_text("must survive recover")
        dst.write_text("complete dst")
        journal = tmp_path / "move.journal"
        _write_journal_lines(
            journal,
            [{"op": "move", "src": str(src), "dst": str(dst), "state": "copied"}],
        )
        monkeypatch.setattr("file_organizer.undo._journal.default_journal_path", lambda: journal)

        result = runner.invoke(app, ["recover"])
        assert result.exit_code == 1, result.output
        # Output names the verb the executor would run.
        assert "unlink_src_then_drop" in result.output, result.output
        # CLI is read-only.
        assert src.read_text() == "must survive recover"
        assert dst.read_text() == "complete dst"

    def test_recover_copied_with_dst_missing_exits_one(
        self, tmp_path: Path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``copied`` with dst absent → planner emits ``retain``
        (codex hGWW guard: dst missing means tmp/dst was cleaned out
        of band; unlinking src would destroy the last copy) → exit 1."""
        from file_organizer.cli.main import app

        src = tmp_path / "src.txt"
        dst = tmp_path / "missing.txt"
        src.write_text("only copy")
        journal = tmp_path / "move.journal"
        _write_journal_lines(
            journal,
            [{"op": "move", "src": str(src), "dst": str(dst), "state": "copied"}],
        )
        monkeypatch.setattr("file_organizer.undo._journal.default_journal_path", lambda: journal)

        result = runner.invoke(app, ["recover"])
        assert result.exit_code == 1, result.output
        assert "retain" in result.output, result.output
        # src still present.
        assert src.read_text() == "only copy"

    def test_recover_v2_started_tmp_present_renders_pre_replace_tier(
        self, tmp_path: Path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """v2 ``move started`` with ``tmp_path`` present → planner
        emits ``drop_tmp_then_drop``, and the rendered reason indicates
        the §5.1 pre-replace disambiguation tier so operators
        understand WHY sweep would unlink tmp instead of src."""
        from file_organizer.cli.main import app

        src = tmp_path / "src.txt"
        dst = tmp_path / "dst.txt"
        tmp = tmp_path / ".dst.txt.42.tmp"
        src.write_text("canonical")
        tmp.write_text("orphan tmp from pre-replace crash")
        journal = tmp_path / "move.journal"
        _write_journal_lines(
            journal,
            [
                {
                    "schema": 2,
                    "op": "move",
                    "op_id": "op-pre",
                    "src": str(src),
                    "dst": str(dst),
                    "tmp_path": str(tmp),
                    "state": "started",
                }
            ],
        )
        monkeypatch.setattr("file_organizer.undo._journal.default_journal_path", lambda: journal)

        result = runner.invoke(app, ["recover"])
        assert result.exit_code == 1, result.output
        assert "drop_tmp_then_drop" in result.output, result.output
        # Reason includes the §5.1 disambiguation tier hint.
        assert "pre-replace" in result.output.lower(), result.output
        # Read-only: tmp still on disk after the CLI runs.
        assert tmp.exists()
        assert src.read_text() == "canonical"

    def test_recover_v2_started_tmp_absent_renders_post_replace_tier(
        self, tmp_path: Path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """v2 ``move started`` with ``tmp_path`` absent + dst PRESENT
        → planner emits ``unlink_src_then_drop`` (post-replace
        confirmed by dst's presence), reason indicates post-replace
        tier so operators understand the rationale.

        Codex lCbU dst-presence guard: tmp absent alone is not proof
        of post-replace. dst present is what makes the
        unlink_src_then_drop verb safe.
        """
        from file_organizer.cli.main import app

        src = tmp_path / "src.txt"
        dst = tmp_path / "dst.txt"
        src.write_text("post-replace src")
        # dst present — proof that os.replace consumed tmp into dst.
        dst.write_text("post-replace dst (replace consumed tmp)")
        journal = tmp_path / "move.journal"
        _write_journal_lines(
            journal,
            [
                {
                    "schema": 2,
                    "op": "move",
                    "op_id": "op-post",
                    "src": str(src),
                    "dst": str(dst),
                    "tmp_path": str(tmp_path / ".dst.txt.42.tmp"),
                    "state": "started",
                }
            ],
        )
        monkeypatch.setattr("file_organizer.undo._journal.default_journal_path", lambda: journal)

        result = runner.invoke(app, ["recover"])
        assert result.exit_code == 1, result.output
        assert "unlink_src_then_drop" in result.output, result.output
        assert "post-replace" in result.output.lower(), result.output

    def test_recover_skips_startup_sweep(
        self, tmp_path: Path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Codex P1 lCbV / coderabbit lDDy: ``main_callback`` runs
        startup sweep before any command. ``fo recover`` is the
        read-only preview of what sweep would do — running sweep
        FIRST would mutate state (unlink, compact) and then the
        preview would report "no retained entries". The startup sweep
        MUST be skipped for the recover subcommand.
        """
        from file_organizer.cli.main import app

        # Pre-populate a journal that sweep would compact (a done entry).
        journal = tmp_path / "move.journal"
        _write_journal_lines(journal, [{"op": "move", "src": "/x", "dst": "/y", "state": "done"}])
        monkeypatch.setattr("file_organizer.undo._journal.default_journal_path", lambda: journal)

        # Instrument sweep so we can prove it's NOT called by the
        # recover invocation. The startup sweep targets the default
        # journal path — also patched above — so we'd see the call here
        # if it fired.
        sweep_calls: list[Path] = []
        from file_organizer.undo import durable_move as dm_mod

        real_sweep = dm_mod.sweep

        def tracking_sweep(j: Path) -> None:
            sweep_calls.append(j)
            real_sweep(j)

        monkeypatch.setattr("file_organizer.cli.main._durable_move_sweep", tracking_sweep)

        result = runner.invoke(app, ["recover"])
        assert result.exit_code == 0, result.output
        assert sweep_calls == [], (
            f"recover MUST skip startup sweep (read-only contract); "
            f"observed sweep calls: {sweep_calls}"
        )

    def test_recover_rejects_non_file_journal_override(
        self, tmp_path: Path, runner: CliRunner
    ) -> None:
        """--journal must point to an existing regular file, not a directory."""
        from file_organizer.cli.main import app

        journal_dir = tmp_path / "journal-dir"
        journal_dir.mkdir()

        result = runner.invoke(app, ["recover", "--journal", str(journal_dir)])
        assert result.exit_code == 2, result.output
        assert "Journal path is not a regular file" in result.output

    def test_recover_surfaces_warning_drops(
        self, tmp_path: Path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """CodeRabbit lDD3: ``dir_move started`` entries are dropped
        (sweep can't safely retry shutil.move) but flagged WARNING
        because operators need to inspect on-disk state. The recover
        preview MUST show these rows even though their verb is
        ``drop`` — otherwise the command this PR adds for operator
        visibility doesn't surface the case it most needs to.

        Exit code stays 0 because there's no recovery action sweep
        will take — these are operator-visibility rows, not
        "needs cleanup" rows.
        """
        from file_organizer.cli.main import app

        journal = tmp_path / "move.journal"
        _write_journal_lines(
            journal,
            [
                {
                    "op": "dir_move",
                    "src": str(tmp_path / "src_dir"),
                    "dst": str(tmp_path / "dst_dir"),
                    "state": "started",
                }
            ],
        )
        monkeypatch.setattr("file_organizer.undo._journal.default_journal_path", lambda: journal)

        result = runner.invoke(app, ["recover"])
        # Stranded dir_move is operator-visible but not actionable —
        # exit 0 (no sweep verb would actually run).
        assert result.exit_code == 0, result.output
        # The row must still appear in the rendered preview.
        assert "dir_move" in result.output, result.output
        assert "drop" in result.output, result.output

    def test_recover_does_not_mutate_disk(
        self,
        tmp_path: Path,
        runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The CLI MUST be read-only — it calls only the planner, never
        the executor. Instrumented unlink + fsync_directory: zero calls
        from file_organizer.undo.durable_move during the recover command."""
        from file_organizer.cli.main import app
        from file_organizer.undo import durable_move as dm_mod

        src = tmp_path / "src.txt"
        dst = tmp_path / "dst.txt"
        src.write_text("x")
        dst.write_text("y")
        journal = tmp_path / "move.journal"
        _write_journal_lines(
            journal,
            [{"op": "move", "src": str(src), "dst": str(dst), "state": "copied"}],
        )
        monkeypatch.setattr("file_organizer.undo._journal.default_journal_path", lambda: journal)

        mutations: list[str] = []

        real_unlink = Path.unlink

        def tracking_unlink(self: Path, *a: object, **k: object) -> None:
            mutations.append(f"unlink:{self}")
            return real_unlink(self, *a, **k)

        def tracking_fsync(p: Path) -> None:
            mutations.append(f"fsync:{p}")

        monkeypatch.setattr(Path, "unlink", tracking_unlink)
        monkeypatch.setattr(dm_mod, "fsync_directory", tracking_fsync)

        result = runner.invoke(app, ["recover"])
        assert result.exit_code == 1, result.output
        assert mutations == [], f"CLI must be read-only; observed mutations: {mutations}"
