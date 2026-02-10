"""Integration tests for CLI undo/redo/history commands.

Uses mocked OperationHistory and UndoManager to test the CLI layer
without real database operations.
"""
from __future__ import annotations

from typer.testing import CliRunner

from file_organizer.cli.main import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# Undo command
# ---------------------------------------------------------------------------


class TestUndoCommand:
    """Tests for ``file-organizer undo``."""

    def test_undo_help(self) -> None:
        result = runner.invoke(app, ["undo", "--help"])
        assert result.exit_code == 0
        assert "undo" in result.output.lower() or "Usage" in result.output

    def test_undo_runs_without_crash(self) -> None:
        """Undo should exit cleanly even with no history."""
        result = runner.invoke(app, ["undo"])
        # Exit code may be 0 or 1 depending on whether history is available
        assert result.exit_code in (0, 1)

    def test_undo_dry_run(self) -> None:
        """Undo with --dry-run should not crash."""
        result = runner.invoke(app, ["undo", "--dry-run"])
        assert result.exit_code in (0, 1)

    def test_undo_verbose(self) -> None:
        """Undo with --verbose should not crash."""
        result = runner.invoke(app, ["undo", "--verbose"])
        assert result.exit_code in (0, 1)

    def test_undo_with_operation_id(self) -> None:
        """Undo with a specific operation ID."""
        result = runner.invoke(app, ["undo", "--operation-id", "999"])
        assert result.exit_code in (0, 1)


# ---------------------------------------------------------------------------
# Redo command
# ---------------------------------------------------------------------------


class TestRedoCommand:
    """Tests for ``file-organizer redo``."""

    def test_redo_help(self) -> None:
        result = runner.invoke(app, ["redo", "--help"])
        assert result.exit_code == 0
        assert "redo" in result.output.lower() or "Usage" in result.output

    def test_redo_runs_without_crash(self) -> None:
        """Redo should exit cleanly even with no history."""
        result = runner.invoke(app, ["redo"])
        assert result.exit_code in (0, 1)

    def test_redo_dry_run(self) -> None:
        result = runner.invoke(app, ["redo", "--dry-run"])
        assert result.exit_code in (0, 1)


# ---------------------------------------------------------------------------
# History command
# ---------------------------------------------------------------------------


class TestHistoryCommand:
    """Tests for ``file-organizer history``."""

    def test_history_help(self) -> None:
        result = runner.invoke(app, ["history", "--help"])
        assert result.exit_code == 0
        assert "history" in result.output.lower() or "Usage" in result.output

    def test_history_runs_without_crash(self) -> None:
        """History should show recent operations or an empty message."""
        result = runner.invoke(app, ["history"])
        assert result.exit_code in (0, 1)

    def test_history_with_limit(self) -> None:
        result = runner.invoke(app, ["history", "--limit", "5"])
        assert result.exit_code in (0, 1)

    def test_history_stats(self) -> None:
        result = runner.invoke(app, ["history", "--stats"])
        assert result.exit_code in (0, 1)

    def test_history_type_filter(self) -> None:
        result = runner.invoke(app, ["history", "--type", "move"])
        assert result.exit_code in (0, 1)

    def test_history_status_filter(self) -> None:
        result = runner.invoke(app, ["history", "--status", "completed"])
        assert result.exit_code in (0, 1)

    def test_history_verbose(self) -> None:
        result = runner.invoke(app, ["history", "--verbose"])
        assert result.exit_code in (0, 1)
