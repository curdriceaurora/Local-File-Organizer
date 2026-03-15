"""Tests for benchmark CLI command."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from file_organizer.cli import benchmark as benchmark_cli
from file_organizer.cli.main import app

runner = CliRunner()
_FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"
_CORPUS_DIR = _FIXTURES_DIR / "benchmark_suite_corpus"


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
        benchmark_cli.validate_benchmark_payload(output_json)
        assert isinstance(output_json["hardware_profile"], dict)
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
    benchmark_cli.validate_benchmark_payload(output_json)
    results = output_json["results"]

    for key in ("median_ms", "p95_ms", "p99_ms", "stddev_ms", "throughput_fps"):
        assert isinstance(results[key], (int, float)) and not isinstance(results[key], bool)
        assert results[key] >= 0
    assert isinstance(results["iterations"], int) and not isinstance(results["iterations"], bool)
    assert results["iterations"] >= 0


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
    benchmark_cli.validate_benchmark_payload(output_json)
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
def test_benchmark_reports_processed_subset_count_for_filtered_suite(tmp_path: Path) -> None:
    """Files count should reflect the suite-processed subset, not all discovered files."""
    fixtures_dir = tmp_path / "fixtures"
    fixtures_dir.mkdir()
    (fixtures_dir / "notes1.txt").write_text("test content 1")
    (fixtures_dir / "notes2.txt").write_text("test content 2")

    sample_image = _CORPUS_DIR / "sample_photo.jpg"
    assert sample_image.is_file(), f"Missing fixture image: {sample_image}"
    shutil.copy2(sample_image, fixtures_dir / "sample_photo.jpg")

    result = runner.invoke(
        app,
        [
            "benchmark",
            "run",
            str(fixtures_dir),
            "--suite",
            "vision",
            "--json",
            "--iterations",
            "1",
            "--warmup",
            "0",
        ],
    )

    assert result.exit_code == 0, result.output
    output_json = json.loads(result.stdout)
    assert output_json["effective_suite"] == "vision"
    assert output_json["degraded"] is False
    assert output_json["degradation_reasons"] == []
    assert output_json["files_count"] == 1
