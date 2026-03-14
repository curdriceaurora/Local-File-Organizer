"""Contract checks for benchmark suite behavior and governance artifacts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from file_organizer.cli import benchmark as benchmark_cli

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE_PATH = REPO_ROOT / "tests" / "fixtures" / "benchmark_baseline.json"
CLI_DOC_PATH = REPO_ROOT / "docs" / "cli-reference.md"
PERF_DOC_PATH = REPO_ROOT / "docs" / "admin" / "performance-tuning.md"


def _assert_suite_non_alias_contract(runners: dict[str, dict[str, object]]) -> None:
    """Assert every suite uses a distinct runner implementation."""
    suites = ("io", "text", "vision", "audio", "pipeline", "e2e")
    for idx, left_suite in enumerate(suites):
        for right_suite in suites[idx + 1 :]:
            assert runners[left_suite]["run"] is not runners[right_suite]["run"]


def _assert_baseline_schema_contract(payload: dict[str, object]) -> None:
    """Assert required benchmark baseline schema and types."""
    assert payload["suite"] == "io"
    assert payload["runner_profile_version"] == benchmark_cli._RUNNER_PROFILE_VERSION
    assert isinstance(payload["files_count"], int)
    assert isinstance(payload["hardware_profile"], dict)

    results = payload["results"]
    assert isinstance(results, dict)
    for key in ("median_ms", "p95_ms", "p99_ms", "stddev_ms", "throughput_fps"):
        value = results[key]
        assert isinstance(value, (int, float)), f"Result metric must be numeric: {key}"
        assert value >= 0

    iterations = results["iterations"]
    assert isinstance(iterations, int)
    assert iterations > 0


def test_benchmark_suite_runners_are_distinct() -> None:
    """Non-IO suites must not alias back to the IO runner."""
    _assert_suite_non_alias_contract(benchmark_cli._SUITE_RUNNERS)


def test_benchmark_baseline_fixture_exists_and_has_schema() -> None:
    """Benchmark baseline fixture should exist with the expected JSON schema."""
    assert BASELINE_PATH.is_file(), f"Missing benchmark baseline fixture: {BASELINE_PATH}"
    payload = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    _assert_baseline_schema_contract(payload)


def test_suite_alias_contract_validator_rejects_aliasing() -> None:
    """Contract helper should fail if a suite aliases back to io runner."""
    fake = {
        "io": {"run": object(), "description": "io"},
        "text": {"run": object(), "description": "text"},
        "vision": {"run": object(), "description": "vision"},
        "audio": {"run": object(), "description": "audio"},
        "pipeline": {"run": object(), "description": "pipeline"},
        "e2e": {"run": object(), "description": "e2e"},
    }
    fake["text"]["run"] = fake["io"]["run"]

    with pytest.raises(AssertionError):
        _assert_suite_non_alias_contract(fake)


def test_baseline_schema_validator_rejects_missing_metric() -> None:
    """Contract helper should fail when required metrics are missing."""
    bad_payload = {
        "suite": "io",
        "runner_profile_version": benchmark_cli._RUNNER_PROFILE_VERSION,
        "files_count": 1,
        "hardware_profile": {},
        "results": {
            "median_ms": 1.0,
            # Missing p95_ms
            "p99_ms": 1.0,
            "stddev_ms": 0.0,
            "throughput_fps": 100.0,
            "iterations": 1,
        },
    }

    with pytest.raises(KeyError):
        _assert_baseline_schema_contract(bad_payload)


def test_benchmark_docs_describe_suite_specific_behavior() -> None:
    """User/admin docs should describe suite-specific benchmark behavior."""
    cli_doc = CLI_DOC_PATH.read_text(encoding="utf-8")
    perf_doc = PERF_DOC_PATH.read_text(encoding="utf-8")

    assert "`--suite TEXT, -s TEXT`" in cli_doc
    assert "TextProcessor.process_file()" in cli_doc
    assert "VisionProcessor.process_file()" in cli_doc
    assert "PipelineOrchestrator.process_batch()" in cli_doc
    assert "full `FileOrganizer.organize()` pass" in cli_doc
    assert "runner_profile_version" in cli_doc
    assert "synthetic metadata only when optional extractor dependencies are unavailable" in cli_doc

    assert "file-organizer benchmark run ~/test-files --suite pipeline --json" in perf_doc
    assert "file-organizer benchmark run ~/test-files --suite e2e --json" in perf_doc
