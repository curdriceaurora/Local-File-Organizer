"""Contract checks for benchmark suite behavior and governance artifacts."""

from __future__ import annotations

import json
from pathlib import Path

from file_organizer.cli import benchmark as benchmark_cli

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE_PATH = REPO_ROOT / "tests" / "fixtures" / "benchmark_baseline.json"
CLI_DOC_PATH = REPO_ROOT / "docs" / "cli-reference.md"
PERF_DOC_PATH = REPO_ROOT / "docs" / "admin" / "performance-tuning.md"


def test_benchmark_suite_runners_are_distinct() -> None:
    """Non-IO suites must not alias back to the IO runner."""
    runners = benchmark_cli._SUITE_RUNNERS
    io_runner = runners["io"]["run"]
    assert runners["text"]["run"] is not io_runner
    assert runners["vision"]["run"] is not io_runner
    assert runners["audio"]["run"] is not io_runner
    assert runners["pipeline"]["run"] is not io_runner
    assert runners["e2e"]["run"] is not io_runner


def test_benchmark_baseline_fixture_exists_and_has_schema() -> None:
    """Benchmark baseline fixture should exist with the expected JSON schema."""
    assert BASELINE_PATH.is_file(), f"Missing benchmark baseline fixture: {BASELINE_PATH}"
    payload = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))

    assert payload["suite"] == "io"
    assert isinstance(payload["files_count"], int)
    assert isinstance(payload["hardware_profile"], dict)

    results = payload["results"]
    for key in ("median_ms", "p95_ms", "p99_ms", "stddev_ms", "throughput_fps"):
        assert isinstance(results[key], (int, float)), f"Result metric must be numeric: {key}"
        assert results[key] >= 0

    assert isinstance(results["iterations"], int)
    assert results["iterations"] > 0


def test_benchmark_docs_describe_suite_specific_behavior() -> None:
    """User/admin docs should describe suite-specific benchmark behavior."""
    cli_doc = CLI_DOC_PATH.read_text(encoding="utf-8")
    perf_doc = PERF_DOC_PATH.read_text(encoding="utf-8")

    assert "`--suite TEXT, -s TEXT`" in cli_doc
    assert "TextProcessor.process_file()" in cli_doc
    assert "VisionProcessor.process_file()" in cli_doc
    assert "PipelineOrchestrator.process_batch()" in cli_doc
    assert "full `FileOrganizer.organize()` pass" in cli_doc

    assert "file-organizer benchmark run ~/test-files --suite pipeline --json" in perf_doc
    assert "file-organizer benchmark run ~/test-files --suite e2e --json" in perf_doc
