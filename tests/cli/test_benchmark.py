"""Tests for benchmark CLI command."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from file_organizer.cli.main import app

runner = CliRunner()


@pytest.mark.ci
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


@pytest.mark.ci
@pytest.mark.unit
def test_benchmark_runs_with_fixtures(tmp_path: Path) -> None:
    """Test benchmark command runs with fixture directory."""
    fixtures_dir = tmp_path / "fixtures"
    fixtures_dir.mkdir()
    (fixtures_dir / "test1.txt").write_text("test content 1")
    (fixtures_dir / "test2.txt").write_text("test content 2")

    result = runner.invoke(
        app,
        ["benchmark", "run", str(fixtures_dir), "--iterations", "1", "--warmup", "0"],
    )

    assert result.exit_code == 0
    assert "Benchmark completed" in result.stdout or "benchmark" in result.stdout.lower()


@pytest.mark.ci
@pytest.mark.unit
def test_benchmark_json_output(tmp_path: Path) -> None:
    """Test benchmark command JSON output has required schema."""
    fixtures_dir = tmp_path / "fixtures"
    fixtures_dir.mkdir()
    (fixtures_dir / "test1.txt").write_text("test content")

    result = runner.invoke(
        app,
        ["benchmark", "run", str(fixtures_dir), "--json", "--iterations", "2", "--warmup", "0"],
    )

    assert result.exit_code == 0

    try:
        output_json = json.loads(result.stdout)
        assert "suite" in output_json
        assert "results" in output_json
        assert "files_count" in output_json
        assert "hardware_profile" in output_json
        assert isinstance(output_json["files_count"], int)
        assert output_json["files_count"] >= 1
    except json.JSONDecodeError:
        pytest.fail(f"JSON output is not valid JSON: {result.stdout}")


@pytest.mark.ci
@pytest.mark.unit
def test_benchmark_results_have_statistics(tmp_path: Path) -> None:
    """Test that JSON results include statistical metrics."""
    fixtures_dir = tmp_path / "fixtures"
    fixtures_dir.mkdir()
    (fixtures_dir / "test1.txt").write_text("test content")

    result = runner.invoke(
        app,
        ["benchmark", "run", str(fixtures_dir), "--json", "--iterations", "3", "--warmup", "0"],
    )

    assert result.exit_code == 0
    output_json = json.loads(result.stdout)
    results = output_json["results"]

    assert "median_ms" in results
    assert "p95_ms" in results
    assert "p99_ms" in results
    assert "stddev_ms" in results
    assert "throughput_fps" in results
    assert "iterations" in results
    assert isinstance(results["median_ms"], (int, float))
    assert isinstance(results["throughput_fps"], (int, float))


@pytest.mark.ci
@pytest.mark.unit
def test_benchmark_hardware_profile_included(tmp_path: Path) -> None:
    """Test that hardware profile is present in JSON output."""
    fixtures_dir = tmp_path / "fixtures"
    fixtures_dir.mkdir()
    (fixtures_dir / "test1.txt").write_text("test content")

    result = runner.invoke(
        app,
        ["benchmark", "run", str(fixtures_dir), "--json", "--iterations", "1", "--warmup", "0"],
    )

    assert result.exit_code == 0
    output_json = json.loads(result.stdout)
    assert "hardware_profile" in output_json
    assert isinstance(output_json["hardware_profile"], dict)


@pytest.mark.ci
@pytest.mark.unit
def test_benchmark_llm_call_count(tmp_path: Path) -> None:
    """Test that benchmark produces valid iteration count."""
    fixtures_dir = tmp_path / "fixtures"
    fixtures_dir.mkdir()
    (fixtures_dir / "test1.txt").write_text("test content")

    result = runner.invoke(
        app,
        ["benchmark", "run", str(fixtures_dir), "--json", "--iterations", "5", "--warmup", "0"],
    )

    assert result.exit_code == 0
    output_json = json.loads(result.stdout)
    assert output_json["results"]["iterations"] == 5


@pytest.mark.ci
@pytest.mark.unit
@pytest.mark.parametrize("suite", ["text", "vision", "audio", "pipeline", "e2e"])
def test_benchmark_non_io_suite_json_includes_suite_note(tmp_path: Path, suite: str) -> None:
    """Non-io suites include a suite_note in JSON output documenting the fallback."""
    (tmp_path / "sample.txt").write_text("content")

    result = runner.invoke(
        app,
        [
            "benchmark",
            "run",
            str(tmp_path),
            "--json",
            "--suite",
            suite,
            "--iterations",
            "1",
            "--warmup",
            "0",
        ],
    )

    assert result.exit_code == 0, f"CLI failed for suite={suite}: {result.output}"
    output_json = json.loads(result.stdout)
    assert output_json["suite"] == suite
    assert "suite_note" in output_json, f"Expected suite_note for suite={suite}"
    assert "I/O" in output_json["suite_note"] or "io" in output_json["suite_note"].lower()


@pytest.mark.ci
@pytest.mark.unit
def test_benchmark_io_suite_json_has_no_suite_note(tmp_path: Path) -> None:
    """The 'io' suite does NOT include a suite_note in JSON output."""
    (tmp_path / "sample.txt").write_text("content")

    result = runner.invoke(
        app,
        [
            "benchmark",
            "run",
            str(tmp_path),
            "--json",
            "--suite",
            "io",
            "--iterations",
            "1",
            "--warmup",
            "0",
        ],
    )

    assert result.exit_code == 0
    output_json = json.loads(result.stdout)
    assert "suite_note" not in output_json


@pytest.mark.ci
@pytest.mark.unit
def test_benchmark_non_io_suite_table_mode_prints_warning(tmp_path: Path) -> None:
    """Non-io suite in table mode prints a yellow note about the fallback."""
    (tmp_path / "sample.txt").write_text("content")

    result = runner.invoke(
        app,
        [
            "benchmark",
            "run",
            str(tmp_path),
            "--suite",
            "text",
            "--iterations",
            "1",
            "--warmup",
            "0",
        ],
    )

    assert result.exit_code == 0
    # The note should mention the suite name and the I/O fallback
    assert "text" in result.stdout
    assert "not yet implemented" in result.stdout or "Falling back" in result.stdout


@pytest.mark.ci
@pytest.mark.unit
def test_benchmark_help_documents_suite_limitation() -> None:
    """benchmark run --help mentions that only 'io' has a dedicated runner."""
    result = runner.invoke(app, ["benchmark", "run", "--help"])
    assert result.exit_code == 0
    help_text = result.stdout.lower()
    # The updated help text should mention the fallback and Phase C
    assert "fall" in help_text, "Help should mention 'fall back' behaviour"
    assert "io" in help_text, "Help should reference the 'io' suite"
    assert "phase" in help_text or "processor" in help_text, (
        "Help should reference processor integrations or Phase C"
    )
