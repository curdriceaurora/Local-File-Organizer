"""Tests for the main Typer CLI application."""

from __future__ import annotations

import re

import pytest
from typer.testing import CliRunner

from file_organizer.cli.main import app

runner = CliRunner()

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from *text* for portable string assertions."""
    return _ANSI_RE.sub("", text)


@pytest.mark.unit
class TestVersionCommand:
    """Tests for the version command."""

    def test_version_output(self) -> None:
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert "fo" in result.output
        assert "2.0.0" in result.output


@pytest.mark.unit
class TestConfigCommands:
    """Tests for the config sub-app."""

    def test_config_show_defaults(self, tmp_path: pytest.TempPathFactory) -> None:
        """Config show with no profile file should display defaults."""
        result = runner.invoke(app, ["config", "show"])
        assert result.exit_code == 0
        assert "default" in result.output

    def test_config_list_empty(self) -> None:
        """Config list should work even with no profiles."""
        result = runner.invoke(app, ["config", "list"])
        assert result.exit_code == 0

    def test_config_edit_runs_successfully(self) -> None:
        """Config edit should save without error."""
        result = runner.invoke(
            app,
            ["config", "edit", "--text-model", "test-model:latest"],
        )
        assert result.exit_code == 0
        assert "Saved" in result.output


@pytest.mark.unit
class TestHelpOutputs:
    """All sub-commands should produce help text."""

    @pytest.mark.parametrize(
        "cmd",
        [
            ["--help"],
            ["start", "--help"],
            ["quickstart", "--help"],
            ["version", "--help"],
            ["organize", "--help"],
            ["preview", "--help"],
            ["tui", "--help"],
            ["config", "--help"],
            ["config", "show", "--help"],
            ["config", "list", "--help"],
            ["config", "edit", "--help"],
            ["model", "--help"],
            ["model", "list", "--help"],
            ["dedupe", "--help"],
            ["marketplace", "--help"],
            ["marketplace", "list", "--help"],
            ["marketplace", "search", "--help"],
            ["marketplace", "install", "--help"],
            ["marketplace", "uninstall", "--help"],
            ["marketplace", "update", "--help"],
            ["marketplace", "installed", "--help"],
            ["marketplace", "updates", "--help"],
            ["marketplace", "review", "--help"],
            ["undo", "--help"],
            ["redo", "--help"],
            ["history", "--help"],
            ["analytics", "--help"],
            ["copilot", "--help"],
            ["copilot", "chat", "--help"],
            ["copilot", "status", "--help"],
            ["rules", "--help"],
            ["rules", "list", "--help"],
            ["rules", "sets", "--help"],
            ["rules", "add", "--help"],
            ["rules", "remove", "--help"],
            ["rules", "toggle", "--help"],
            ["rules", "preview", "--help"],
            ["rules", "export", "--help"],
            ["rules", "import", "--help"],
            ["update", "--help"],
            ["update", "check", "--help"],
            ["update", "install", "--help"],
            ["update", "rollback", "--help"],
        ],
    )
    def test_help(self, cmd: list[str]) -> None:
        result = runner.invoke(app, cmd)
        assert result.exit_code == 0
        assert "Usage" in result.output or "usage" in result.output.lower()

    def test_top_level_help_is_grouped_and_unique(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        # Typer forces terminal colors when GITHUB_ACTIONS is set — strip
        # styling so the panel-row matching below works in CI too.
        plain = _strip_ansi(result.output)
        assert "Core Commands" in plain
        assert "Interfaces Commands" in plain
        assert "Automation Commands" in plain
        assert "Advanced Commands" in plain

        # Each command should appear once in grouped help rows.
        for command in ("start", "quickstart", "organize", "serve", "dedupe", "update"):
            assert plain.count(f"│ {command}") == 1


@pytest.mark.unit
class TestModelListPlaceholder:
    """Model list placeholder should work."""

    def test_model_list(self) -> None:
        result = runner.invoke(app, ["model", "list"])
        assert result.exit_code == 0


@pytest.mark.unit
class TestGlobalOptions:
    """Global --verbose, --dry-run, --json flags should be accepted."""

    def test_verbose_version(self) -> None:
        result = runner.invoke(app, ["--verbose", "version"])
        assert result.exit_code == 0

    def test_dry_run_version(self) -> None:
        result = runner.invoke(app, ["--dry-run", "version"])
        assert result.exit_code == 0

    def test_json_version(self) -> None:
        result = runner.invoke(app, ["--json", "version"])
        assert result.exit_code == 0


def _make_manager(config_dir):
    """Helper to create a ConfigManager pointing at a temp dir."""
    from file_organizer.config import ConfigManager

    return ConfigManager(config_dir)
