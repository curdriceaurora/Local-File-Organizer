"""Tests for benchmark CLI command."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from file_organizer.cli.main import app

runner = CliRunner()


@pytest.mark.unit
def test_benchmark_command_exists() -> None:
    """Test that benchmark command exists in CLI."""
    result = runner.invoke(app, ["benchmark", "run", "--help"])
    assert result.exit_code == 0
    assert "benchmark" in result.stdout.lower() or "run" in result.stdout.lower()

    # Test that the options are documented in help (case-insensitive to handle formatting variations)
    help_text = result.stdout.lower()
    assert "iterations" in help_text, "Help should document --iterations parameter"
    assert "json" in help_text, "Help should document --json parameter"


@pytest.mark.integration
def test_benchmark_runs_with_fixtures(tmp_path: Path) -> None:
    """Test benchmark command runs with fixture directory."""
    # Create test fixtures
    fixtures_dir = tmp_path / "fixtures"
    fixtures_dir.mkdir()

    # Create some test files
    (fixtures_dir / "test1.txt").write_text("test content 1")
    (fixtures_dir / "test2.txt").write_text("test content 2")

    with (
        patch("file_organizer.optimization.resource_monitor.ResourceMonitor") as mock_monitor_cls,
        patch("file_organizer.optimization.memory_profiler.MemoryProfiler") as mock_profiler_cls,
    ):
        # Mock the monitor
        mock_monitor = MagicMock()
        mock_monitor.get_memory_usage.return_value.rss = 1000000
        mock_monitor.get_memory_usage.return_value.vms = 2000000
        mock_monitor.get_memory_usage.return_value.percent = 10.0
        mock_monitor_cls.return_value = mock_monitor

        # Mock the profiler with timeline snapshots
        mock_profiler = MagicMock()
        mock_timeline = MagicMock()
        # Create mock snapshots with rss values
        mock_snapshot = MagicMock()
        mock_snapshot.rss = 1500000
        mock_timeline.snapshots = [mock_snapshot]
        mock_profiler.stop_tracking.return_value = mock_timeline
        mock_profiler_cls.return_value = mock_profiler

        result = runner.invoke(
            app,
            ["benchmark", "run", str(fixtures_dir), "--iterations", "1"],
        )

        assert result.exit_code == 0
        assert "Benchmark completed" in result.stdout or "files processed" in result.stdout.lower()


@pytest.mark.unit
def test_benchmark_json_output(tmp_path: Path) -> None:
    """Test benchmark command JSON output."""
    # Create test fixtures
    fixtures_dir = tmp_path / "fixtures"
    fixtures_dir.mkdir()

    (fixtures_dir / "test1.txt").write_text("test content")

    with (
        patch("file_organizer.optimization.resource_monitor.ResourceMonitor") as mock_monitor_cls,
        patch("file_organizer.optimization.memory_profiler.MemoryProfiler") as mock_profiler_cls,
    ):
        # Mock the monitor
        mock_monitor = MagicMock()
        mock_monitor.get_memory_usage.return_value.rss = 1000000
        mock_monitor.get_memory_usage.return_value.vms = 2000000
        mock_monitor.get_memory_usage.return_value.percent = 10.0
        mock_monitor_cls.return_value = mock_monitor

        # Mock the profiler with timeline snapshots
        mock_profiler = MagicMock()
        mock_timeline = MagicMock()
        mock_snapshot = MagicMock()
        mock_snapshot.rss = 1500000
        mock_timeline.snapshots = [mock_snapshot]
        mock_profiler.stop_tracking.return_value = mock_timeline
        mock_profiler_cls.return_value = mock_profiler

        result = runner.invoke(
            app,
            ["benchmark", "run", str(fixtures_dir), "--json"],
        )

        assert result.exit_code == 0

        # Parse and verify JSON output
        try:
            output_json = json.loads(result.stdout)
            assert "files_processed" in output_json
            assert "total_time_seconds" in output_json
            assert isinstance(output_json["files_processed"], int)
            assert isinstance(output_json["total_time_seconds"], (int, float))
        except json.JSONDecodeError:
            pytest.fail(f"JSON output is not valid JSON: {result.stdout}")


@pytest.mark.unit
def test_benchmark_tracks_cache_hits(tmp_path: Path) -> None:
    """Test that benchmark tracks cache hits metric."""
    fixtures_dir = tmp_path / "fixtures"
    fixtures_dir.mkdir()
    (fixtures_dir / "test1.txt").write_text("test content")

    with (
        patch("file_organizer.optimization.resource_monitor.ResourceMonitor") as mock_monitor_cls,
        patch("file_organizer.optimization.memory_profiler.MemoryProfiler") as mock_profiler_cls,
    ):
        # Mock the monitor
        mock_monitor = MagicMock()
        mock_monitor.get_memory_usage.return_value.rss = 1000000
        mock_monitor_cls.return_value = mock_monitor

        # Mock the profiler with timeline snapshots
        mock_profiler = MagicMock()
        mock_timeline = MagicMock()
        mock_timeline.snapshots = []  # Empty snapshots list for this test
        mock_profiler.stop_tracking.return_value = mock_timeline
        mock_profiler_cls.return_value = mock_profiler

        result = runner.invoke(
            app,
            ["benchmark", "run", str(fixtures_dir), "--json"],
        )

        assert result.exit_code == 0
        output_json = json.loads(result.stdout)
        assert "cache_hits" in output_json
        assert isinstance(output_json["cache_hits"], int)
        assert output_json["cache_hits"] >= 0


@pytest.mark.unit
def test_benchmark_json_includes_cache_metrics(tmp_path: Path) -> None:
    """Test that JSON output includes cache and LLM metrics."""
    fixtures_dir = tmp_path / "fixtures"
    fixtures_dir.mkdir()
    (fixtures_dir / "test1.txt").write_text("test content")

    with (
        patch("file_organizer.optimization.resource_monitor.ResourceMonitor") as mock_monitor_cls,
        patch("file_organizer.optimization.memory_profiler.MemoryProfiler") as mock_profiler_cls,
    ):
        # Mock the monitor
        mock_monitor = MagicMock()
        mock_monitor.get_memory_usage.return_value.rss = 1000000
        mock_monitor_cls.return_value = mock_monitor

        # Mock the profiler with timeline snapshots
        mock_profiler = MagicMock()
        mock_timeline = MagicMock()
        mock_timeline.snapshots = []  # Empty snapshots list for this test
        mock_profiler.stop_tracking.return_value = mock_timeline
        mock_profiler_cls.return_value = mock_profiler

        result = runner.invoke(
            app,
            ["benchmark", "run", str(fixtures_dir), "--json"],
        )

        assert result.exit_code == 0
        output_json = json.loads(result.stdout)
        assert "cache_hits" in output_json
        assert "cache_misses" in output_json
        assert "llm_calls" in output_json
        assert isinstance(output_json["cache_hits"], int)
        assert isinstance(output_json["cache_misses"], int)
        assert isinstance(output_json["llm_calls"], int)


@pytest.mark.unit
def test_benchmark_llm_call_count(tmp_path: Path) -> None:
    """Test that benchmark tracks LLM call count metric."""
    fixtures_dir = tmp_path / "fixtures"
    fixtures_dir.mkdir()
    (fixtures_dir / "test1.txt").write_text("test content")

    with (
        patch("file_organizer.optimization.resource_monitor.ResourceMonitor") as mock_monitor_cls,
        patch("file_organizer.optimization.memory_profiler.MemoryProfiler") as mock_profiler_cls,
    ):
        # Mock the monitor
        mock_monitor = MagicMock()
        mock_monitor.get_memory_usage.return_value.rss = 1000000
        mock_monitor_cls.return_value = mock_monitor

        # Mock the profiler with timeline snapshots
        mock_profiler = MagicMock()
        mock_timeline = MagicMock()
        mock_timeline.snapshots = []  # Empty snapshots list for this test
        mock_profiler.stop_tracking.return_value = mock_timeline
        mock_profiler_cls.return_value = mock_profiler

        result = runner.invoke(
            app,
            ["benchmark", "run", str(fixtures_dir), "--json"],
        )

        assert result.exit_code == 0
        output_json = json.loads(result.stdout)
        assert "llm_calls" in output_json
        assert isinstance(output_json["llm_calls"], int)
        assert output_json["llm_calls"] >= 0
