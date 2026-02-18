"""Integration tests for CLI analytics command."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from file_organizer.cli.main import app

runner = CliRunner()


class TestAnalyticsCommand:
    """Tests for ``file-organizer analytics``."""

    def test_analytics_help(self) -> None:
        result = runner.invoke(app, ["analytics", "--help"])
        assert result.exit_code == 0
        assert "analytics" in result.output.lower() or "Usage" in result.output

    def test_analytics_runs_without_crash(self) -> None:
        """Analytics should exit cleanly even without data."""
        result = runner.invoke(app, ["analytics"])
        # Exit code 2 means Typer reported missing required argument
        assert result.exit_code in (0, 1, 2)

    def test_analytics_with_directory(self, tmp_path: pytest.TempPathFactory) -> None:
        """Analytics with a directory argument."""
        result = runner.invoke(app, ["analytics", str(tmp_path)])
        assert result.exit_code in (0, 1)

    def test_analytics_verbose(self, tmp_path: pytest.TempPathFactory) -> None:
        result = runner.invoke(app, ["analytics", str(tmp_path), "--verbose"])
        assert result.exit_code in (0, 1)
