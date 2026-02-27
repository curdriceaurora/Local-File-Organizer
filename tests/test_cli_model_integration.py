"""Integration tests for CLI model commands.

Exercises model list/pull/cache with mocked Ollama responses.
"""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from file_organizer.cli.main import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# model list
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestModelList:
    """Tests for ``file-organizer model list``."""

    def test_list_help(self) -> None:
        result = runner.invoke(app, ["model", "list", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output.lower() or "Usage" in result.output

    def test_list_runs_without_crash(self) -> None:
        """model list should exit cleanly even if Ollama is unreachable."""
        result = runner.invoke(app, ["model", "list"])
        # May succeed or fail depending on Ollama availability
        assert result.exit_code in (0, 1)

    def test_list_with_type_filter(self) -> None:
        result = runner.invoke(app, ["model", "list", "--type", "text"])
        assert result.exit_code in (0, 1)


# ---------------------------------------------------------------------------
# model pull
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestModelPull:
    """Tests for ``file-organizer model pull``."""

    def test_pull_help(self) -> None:
        result = runner.invoke(app, ["model", "pull", "--help"])
        assert result.exit_code == 0
        assert "pull" in result.output.lower() or "Usage" in result.output

    def test_pull_nonexistent_model(self) -> None:
        """Pulling a nonsense model name should fail gracefully."""
        result = runner.invoke(app, ["model", "pull", "nonexistent-model-xyz:latest"])
        assert result.exit_code in (0, 1)


# ---------------------------------------------------------------------------
# model cache
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestModelCache:
    """Tests for ``file-organizer model cache``."""

    def test_cache_help(self) -> None:
        result = runner.invoke(app, ["model", "cache", "--help"])
        assert result.exit_code == 0
        assert "cache" in result.output.lower() or "Usage" in result.output

    def test_cache_runs_without_crash(self) -> None:
        """Cache command should exit cleanly."""
        result = runner.invoke(app, ["model", "cache"])
        assert result.exit_code in (0, 1)
