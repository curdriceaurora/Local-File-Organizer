"""Coverage tests for file_organizer.cli.benchmark — uncovered lines 59-60, 66-86, 117-118, 131, 138."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

pytestmark = pytest.mark.unit

runner = CliRunner()


def _get_app():
    from file_organizer.cli import app

    return app


class TestBenchmarkErrors:
    """Covers error branches."""

    def test_path_not_exists(self, tmp_path: Path) -> None:
        app = _get_app()
        nonexist = tmp_path / "nonexistent_benchmark_sub"
        result = runner.invoke(app, ["benchmark", "run", str(nonexist)])
        # Typer validates the path and returns exit code 1 or 2
        assert result.exit_code in (1, 2)

    def test_read_error(self, tmp_path: Path) -> None:
        app = _get_app()
        # Patching Path.rglob globally can interfere with Typer's internal
        # path validation, so we accept either exit code 1 (our error handler)
        # or 2 (Typer's argument validation).
        with patch.object(Path, "rglob", side_effect=PermissionError("denied")):
            result = runner.invoke(app, ["benchmark", "run", str(tmp_path)])

        assert result.exit_code in (1, 2)

    def test_no_files_json(self, tmp_path: Path) -> None:
        """No files found with JSON output."""
        app = _get_app()
        result = runner.invoke(app, ["benchmark", "run", str(tmp_path), "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["effective_suite"] == "io"
        assert payload["degraded"] is False
        assert payload["degradation_reasons"] == []
        assert payload["files_count"] == 0

    def test_no_files_plain(self, tmp_path: Path) -> None:
        """No files found with plain output."""
        app = _get_app()
        result = runner.invoke(app, ["benchmark", "run", str(tmp_path)])
        assert result.exit_code == 0
        assert "No files found" in result.output


class TestBenchmarkEvenIterations:
    """Covers median calculation for even number of iterations (line 138)."""

    def test_even_iterations(self, tmp_path: Path) -> None:
        app = _get_app()
        (tmp_path / "a.txt").write_text("hello")

        # Mock profiler and monitor
        mock_profiler = MagicMock()
        mock_timeline = MagicMock()
        mock_timeline.snapshots = []
        mock_profiler.stop_tracking.return_value = mock_timeline

        mock_monitor = MagicMock()
        mock_mem = MagicMock()
        mock_mem.rss = 100 * 1024 * 1024
        mock_monitor.get_memory_usage.return_value = mock_mem

        with (
            patch(
                "file_organizer.optimization.memory_profiler.MemoryProfiler",
                return_value=mock_profiler,
            ),
            patch(
                "file_organizer.optimization.resource_monitor.ResourceMonitor",
                return_value=mock_monitor,
            ),
        ):
            result = runner.invoke(
                app,
                ["benchmark", "run", str(tmp_path), "--iterations", "2", "--json"],
            )

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["effective_suite"] == "io"
        assert payload["degraded"] is False
        assert payload["degradation_reasons"] == []
        assert payload["files_count"] == 1
