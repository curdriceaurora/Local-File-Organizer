"""#1248 (WP-1.2b) — tests for the ``fo recover`` CLI command.

The ``recover`` command replays/sweeps the durable_move journal so any
unfinished cross-device move left by a crash is completed or rolled back.
With ``--dry-run`` it reports the planned actions without mutating disk.

Mirrors ``tests/cli/test_cli_config.py`` (Typer ``CliRunner``).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from file_organizer.cli.main import app

pytestmark = [pytest.mark.unit, pytest.mark.ci]

runner = CliRunner()


class TestRecoverCommand:
    """``fo recover`` journal replay / sweep."""

    def test_recover_no_journal_reports_nothing(self, tmp_path: Path) -> None:
        """A missing journal is a clean no-op (exit 0)."""
        journal = tmp_path / "missing.journal"
        result = runner.invoke(app, ["recover", "--journal", str(journal)])
        assert result.exit_code == 0
        assert "nothing" in result.output.lower() or "no " in result.output.lower()

    def test_recover_invokes_sweep(self, tmp_path: Path) -> None:
        """Without --dry-run, recover calls durable_move.sweep on the
        journal path."""
        journal = tmp_path / "move.journal"
        journal.write_text("", encoding="utf-8")
        with patch("file_organizer.cli.undo_recover.sweep") as mock_sweep:
            result = runner.invoke(app, ["recover", "--journal", str(journal)])
        assert result.exit_code == 0
        mock_sweep.assert_called_once()
        called_path = mock_sweep.call_args[0][0]
        assert Path(called_path) == journal

    def test_recover_dry_run_does_not_sweep(self, tmp_path: Path) -> None:
        """--dry-run reports planned actions but never mutates the journal."""
        journal = tmp_path / "move.journal"
        journal.write_text("", encoding="utf-8")
        with (
            patch("file_organizer.cli.undo_recover.sweep") as mock_sweep,
            patch(
                "file_organizer.cli.undo_recover.read_journal_under_shared_lock",
                return_value=[],
            ),
            patch(
                "file_organizer.cli.undo_recover.plan_recovery_actions",
                return_value=[],
            ),
        ):
            result = runner.invoke(app, ["recover", "--journal", str(journal), "--dry-run"])
        assert result.exit_code == 0
        mock_sweep.assert_not_called()

    def test_recover_dry_run_lists_planned_actions(self, tmp_path: Path) -> None:
        """--dry-run renders the planner's reasons for each entry."""
        from file_organizer.undo.durable_move import (
            OP_MOVE,
            STATE_COPIED,
            _JournalEntry,
            _PlannedAction,
        )

        journal = tmp_path / "move.journal"
        journal.write_text("x", encoding="utf-8")
        entry = _JournalEntry(OP_MOVE, "/t/a", "/h/a", STATE_COPIED, 2, "op1")
        action = _PlannedAction(
            identity=("v2", OP_MOVE, "op1"),
            entry=entry,
            verb="unlink_src_then_drop",
            reason="copied entry /t/a -> /h/a; finishing by unlinking src",
        )
        with (
            patch(
                "file_organizer.cli.undo_recover.read_journal_under_shared_lock",
                return_value=[entry],
            ),
            patch(
                "file_organizer.cli.undo_recover.plan_recovery_actions",
                return_value=[action],
            ),
        ):
            result = runner.invoke(app, ["recover", "--journal", str(journal), "--dry-run"])
        assert result.exit_code == 0
        assert "unlink_src_then_drop" in result.output
        assert "/t/a" in result.output

    def test_recover_uses_default_journal_when_omitted(self, tmp_path: Path) -> None:
        """With no --journal, recover resolves the shared default path."""
        default = tmp_path / "undo" / "durable_move.journal"
        default.parent.mkdir(parents=True, exist_ok=True)
        default.write_text("", encoding="utf-8")
        with (
            patch(
                "file_organizer.cli.undo_recover.default_journal_path",
                return_value=default,
            ),
            patch("file_organizer.cli.undo_recover.sweep") as mock_sweep,
        ):
            result = runner.invoke(app, ["recover"])
        assert result.exit_code == 0
        mock_sweep.assert_called_once()
        assert Path(mock_sweep.call_args[0][0]) == default

    def test_recover_reports_sweep_failure(self, tmp_path: Path) -> None:
        """An OSError from sweep surfaces as a non-zero exit, not a stack
        trace."""
        journal = tmp_path / "move.journal"
        journal.write_text("", encoding="utf-8")
        with patch(
            "file_organizer.cli.undo_recover.sweep",
            side_effect=OSError("disk gone"),
        ):
            result = runner.invoke(app, ["recover", "--journal", str(journal)])
        assert result.exit_code == 1
        assert "disk gone" in result.output or "failed" in result.output.lower()

    def test_recover_reports_dry_run_failure(self, tmp_path: Path) -> None:
        """An OSError from dry-run journal reads surfaces as a clean
        non-zero CLI error, matching the sweep path."""
        journal = tmp_path / "move.journal"
        journal.write_text("", encoding="utf-8")
        with patch(
            "file_organizer.cli.undo_recover.read_journal_under_shared_lock",
            side_effect=OSError("permission denied"),
        ):
            result = runner.invoke(app, ["recover", "--journal", str(journal), "--dry-run"])
        assert result.exit_code == 1
        assert "permission denied" in result.output
        assert "dry run failed" in result.output.lower()
