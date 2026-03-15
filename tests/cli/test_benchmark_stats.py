"""Tests for benchmark statistical output and comparison.

Validates statistical calculations (median, p95, p99, stddev,
throughput) against synthetic data, warmup exclusion, and
regression detection.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from file_organizer.cli.benchmark import (
    _percentile,
    compare_results,
    compute_stats,
    validate_benchmark_payload,
)

# ---------------------------------------------------------------------------
# Statistical calculation tests
# ---------------------------------------------------------------------------


@pytest.mark.ci
@pytest.mark.unit
class TestComputeStats:
    """Verify statistical calculations against known synthetic data."""

    def test_empty_input(self) -> None:
        stats = compute_stats([], 10)
        assert stats["median_ms"] == 0.0
        assert stats["p95_ms"] == 0.0
        assert stats["p99_ms"] == 0.0
        assert stats["stddev_ms"] == 0.0
        assert stats["throughput_fps"] == 0.0
        assert stats["iterations"] == 0

    def test_single_value(self) -> None:
        stats = compute_stats([100.0], 10)
        assert stats["median_ms"] == 100.0
        assert stats["p95_ms"] == 100.0
        assert stats["p99_ms"] == 100.0
        assert stats["stddev_ms"] == 0.0
        assert stats["iterations"] == 1

    def test_known_distribution(self) -> None:
        """10 values from 100 to 1000 ms."""
        times = [100.0, 200.0, 300.0, 400.0, 500.0, 600.0, 700.0, 800.0, 900.0, 1000.0]
        stats = compute_stats(times, 5)

        assert stats["median_ms"] == 550.0
        assert stats["iterations"] == 10
        assert stats["p95_ms"] == 1000.0
        assert stats["p99_ms"] == 1000.0
        assert stats["stddev_ms"] > 0
        assert stats["throughput_fps"] > 0

    def test_throughput_calculation(self) -> None:
        """100ms per iteration, 10 files -> 100 files/s."""
        stats = compute_stats([100.0, 100.0, 100.0], 10)
        assert stats["throughput_fps"] == 100.0

    def test_two_values_stddev(self) -> None:
        stats = compute_stats([100.0, 200.0], 1)
        # stddev of [100, 200] = ~70.71
        assert stats["stddev_ms"] > 70
        assert stats["stddev_ms"] < 71


@pytest.mark.ci
@pytest.mark.unit
class TestPercentile:
    """Verify percentile calculation."""

    def test_p95_of_100_values(self) -> None:
        data = sorted(range(1, 101))  # 1..100
        assert _percentile(data, 95) == 95

    def test_p99_of_100_values(self) -> None:
        data = sorted(range(1, 101))
        assert _percentile(data, 99) == 99

    def test_p50_is_median(self) -> None:
        data = sorted([10.0, 20.0, 30.0])
        assert _percentile(data, 50) == 20.0

    def test_empty_data(self) -> None:
        assert _percentile([], 95) == 0.0


# ---------------------------------------------------------------------------
# Comparison and regression tests
# ---------------------------------------------------------------------------


@pytest.mark.ci
@pytest.mark.unit
class TestCompareResults:
    """Verify baseline comparison and regression detection."""

    def test_no_regression(self) -> None:
        current = {
            "results": {
                "median_ms": 100,
                "p95_ms": 110,
                "p99_ms": 120,
                "stddev_ms": 5,
                "throughput_fps": 50,
            }
        }
        baseline = {
            "results": {
                "median_ms": 100,
                "p95_ms": 110,
                "p99_ms": 120,
                "stddev_ms": 5,
                "throughput_fps": 50,
            }
        }

        comp = compare_results(current, baseline)
        assert comp["regression"] is False
        assert comp["deltas_pct"]["median_ms"] == 0.0

    def test_regression_detected(self) -> None:
        """p95 > 120% of baseline triggers regression."""
        current = {
            "results": {
                "median_ms": 100,
                "p95_ms": 250,
                "p99_ms": 300,
                "stddev_ms": 10,
                "throughput_fps": 40,
            }
        }
        baseline = {
            "results": {
                "median_ms": 100,
                "p95_ms": 100,
                "p99_ms": 120,
                "stddev_ms": 5,
                "throughput_fps": 50,
            }
        }

        comp = compare_results(current, baseline)
        assert comp["regression"] is True

    def test_delta_percentage(self) -> None:
        current = {
            "results": {
                "median_ms": 150,
                "p95_ms": 110,
                "p99_ms": 120,
                "stddev_ms": 5,
                "throughput_fps": 50,
            }
        }
        baseline = {
            "results": {
                "median_ms": 100,
                "p95_ms": 110,
                "p99_ms": 120,
                "stddev_ms": 5,
                "throughput_fps": 50,
            }
        }

        comp = compare_results(current, baseline)
        assert comp["deltas_pct"]["median_ms"] == 50.0

    def test_flat_results_format(self) -> None:
        """Works with flat dict (no 'results' key)."""
        current = {
            "median_ms": 100,
            "p95_ms": 100,
            "p99_ms": 100,
            "stddev_ms": 5,
            "throughput_fps": 50,
        }
        baseline = {
            "median_ms": 100,
            "p95_ms": 100,
            "p99_ms": 100,
            "stddev_ms": 5,
            "throughput_fps": 50,
        }

        comp = compare_results(current, baseline)
        assert comp["regression"] is False


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


@pytest.mark.ci
@pytest.mark.unit
class TestBenchmarkCLI:
    """Test CLI command integration."""

    def test_benchmark_json_output_schema(self, tmp_path: Path) -> None:
        """JSON output matches benchmark payload schema and metric contracts."""
        from typer.testing import CliRunner

        from file_organizer.cli.main import app

        # Create some test files
        for i in range(3):
            (tmp_path / f"file{i}.txt").write_text(f"content {i}")

        runner = CliRunner()
        result = runner.invoke(
            app,
            ["benchmark", "run", str(tmp_path), "--json", "--iterations", "2", "--warmup", "1"],
        )

        assert result.exit_code == 0, f"CLI failed: {result.output}"
        output = json.loads(result.stdout)
        validate_benchmark_payload(output)
        assert isinstance(output["hardware_profile"], dict)

        results = output["results"]
        for key in ("median_ms", "p95_ms", "p99_ms", "stddev_ms", "throughput_fps"):
            assert isinstance(results[key], (int, float)) and not isinstance(results[key], bool)
            assert results[key] >= 0
        assert isinstance(results["iterations"], int) and not isinstance(
            results["iterations"], bool
        )
        assert results["iterations"] >= 0

    def test_benchmark_warmup_exclusion(self, tmp_path: Path) -> None:
        """Warmup iterations are excluded from results."""
        from typer.testing import CliRunner

        from file_organizer.cli.main import app

        (tmp_path / "file.txt").write_text("test")

        runner = CliRunner()
        result = runner.invoke(
            app,
            ["benchmark", "run", str(tmp_path), "--json", "--iterations", "5", "--warmup", "3"],
        )

        assert result.exit_code == 0, f"CLI failed: {result.output}"
        output = json.loads(result.stdout)
        assert output["results"]["iterations"] == 5

    def test_benchmark_suite_selection(self, tmp_path: Path) -> None:
        """Suite parameter is passed through to output."""
        from typer.testing import CliRunner

        from file_organizer.cli.main import app

        (tmp_path / "file.txt").write_text("test")

        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "benchmark",
                "run",
                str(tmp_path),
                "--json",
                "--suite",
                "text",
                "--iterations",
                "1",
                "--warmup",
                "0",
            ],
        )

        assert result.exit_code == 0, f"CLI failed: {result.output}"
        output = json.loads(result.stdout)
        assert output["suite"] == "text"

    def test_benchmark_compare(self, tmp_path: Path) -> None:
        """Comparison with baseline file works."""
        from typer.testing import CliRunner

        from file_organizer.cli.main import app

        (tmp_path / "file.txt").write_text("test")

        baseline = {
            "suite": "io",
            "results": {
                "median_ms": 0.5,
                "p95_ms": 1.0,
                "p99_ms": 1.5,
                "stddev_ms": 0.2,
                "throughput_fps": 2000,
                "iterations": 5,
            },
        }
        baseline_path = tmp_path / "baseline.json"
        baseline_path.write_text(json.dumps(baseline))

        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "benchmark",
                "run",
                str(tmp_path),
                "--json",
                "--iterations",
                "2",
                "--warmup",
                "0",
                "--compare",
                str(baseline_path),
            ],
        )

        assert result.exit_code == 0, f"CLI failed: {result.output}"

    def test_benchmark_empty_directory(self, tmp_path: Path) -> None:
        """Empty directory produces valid JSON output."""
        from typer.testing import CliRunner

        from file_organizer.cli.main import app

        empty = tmp_path / "empty"
        empty.mkdir()

        runner = CliRunner()
        result = runner.invoke(
            app,
            ["benchmark", "run", str(empty), "--json"],
        )

        assert result.exit_code == 0, f"CLI failed: {result.output}"
        output = json.loads(result.stdout)
        assert output["results"]["iterations"] == 0
