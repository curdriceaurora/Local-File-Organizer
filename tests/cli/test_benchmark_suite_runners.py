"""Suite coverage tests for benchmark runner dispatch."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from file_organizer.cli import benchmark as benchmark_cli
from file_organizer.cli.main import app

runner = CliRunner()

_FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"
_CORPUS_DIR = _FIXTURES_DIR / "benchmark_suite_corpus"
_EXPECTATIONS_PATH = _FIXTURES_DIR / "benchmark_suite_expectations.json"
_EXPECTATIONS = json.loads(_EXPECTATIONS_PATH.read_text(encoding="utf-8"))


@pytest.mark.ci
@pytest.mark.unit
def test_suite_runner_map_uses_dedicated_functions() -> None:
    """Each suite must map to its dedicated runner function."""
    assert benchmark_cli._SUITE_RUNNERS["io"]["run"] is benchmark_cli._run_io_suite
    assert benchmark_cli._SUITE_RUNNERS["text"]["run"] is benchmark_cli._run_text_suite
    assert benchmark_cli._SUITE_RUNNERS["vision"]["run"] is benchmark_cli._run_vision_suite
    assert benchmark_cli._SUITE_RUNNERS["audio"]["run"] is benchmark_cli._run_audio_suite
    assert benchmark_cli._SUITE_RUNNERS["pipeline"]["run"] is benchmark_cli._run_pipeline_suite
    assert benchmark_cli._SUITE_RUNNERS["e2e"]["run"] is benchmark_cli._run_e2e_suite

    io_runner = benchmark_cli._SUITE_RUNNERS["io"]["run"]
    for suite_name in ("text", "vision", "audio", "pipeline", "e2e"):
        assert benchmark_cli._SUITE_RUNNERS[suite_name]["run"] is not io_runner


@pytest.mark.ci
@pytest.mark.unit
@pytest.mark.parametrize("suite_name", sorted(_EXPECTATIONS["suites"].keys()))
def test_benchmark_suite_smoke_outputs_expected_schema(suite_name: str) -> None:
    """Each suite should run against fixture corpus and emit stable JSON schema."""
    result = runner.invoke(
        app,
        [
            "benchmark",
            "run",
            str(_CORPUS_DIR),
            "--suite",
            suite_name,
            "--iterations",
            "1",
            "--warmup",
            "0",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output

    payload = json.loads(result.stdout)
    expected = _EXPECTATIONS["suites"][suite_name]

    assert payload["suite"] == suite_name
    assert payload["runner_profile_version"] == benchmark_cli._RUNNER_PROFILE_VERSION
    assert payload["files_count"] >= expected["min_files"]
    assert payload["results"]["iterations"] == 1
    assert payload["results"]["median_ms"] >= 0.0
    assert payload["results"]["p95_ms"] >= 0.0
    assert payload["results"]["p99_ms"] >= 0.0
    assert payload["results"]["throughput_fps"] >= 0.0


@pytest.mark.ci
@pytest.mark.unit
def test_vision_suite_does_not_require_backend_model_pull() -> None:
    """Vision suite should execute with deterministic stubs even without backend models."""
    image_file = _CORPUS_DIR / "sample_photo.jpg"
    assert image_file.is_file(), f"Missing fixture image: {image_file}"

    with patch(
        "file_organizer.services.vision_processor.get_vision_model",
        side_effect=RuntimeError("backend model pull should not be used in suite runner"),
    ):
        benchmark_cli._run_vision_suite([image_file])
