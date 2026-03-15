"""Suite coverage tests for benchmark runner dispatch."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import typer
from typer.testing import CliRunner

from file_organizer.cli import benchmark as benchmark_cli
from file_organizer.cli.main import app
from file_organizer.models.base import ModelType

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
    assert benchmark_cli._SUITE_RUNNERS["io"]["classify"] is benchmark_cli._classify_io_suite
    assert benchmark_cli._SUITE_RUNNERS["text"]["run"] is benchmark_cli._run_text_suite
    assert benchmark_cli._SUITE_RUNNERS["text"]["classify"] is benchmark_cli._classify_text_suite
    assert benchmark_cli._SUITE_RUNNERS["vision"]["run"] is benchmark_cli._run_vision_suite
    assert (
        benchmark_cli._SUITE_RUNNERS["vision"]["classify"] is benchmark_cli._classify_vision_suite
    )
    assert benchmark_cli._SUITE_RUNNERS["audio"]["run"] is benchmark_cli._run_audio_suite
    assert benchmark_cli._SUITE_RUNNERS["audio"]["classify"] is benchmark_cli._classify_audio_suite
    assert benchmark_cli._SUITE_RUNNERS["pipeline"]["run"] is benchmark_cli._run_pipeline_suite
    assert (
        benchmark_cli._SUITE_RUNNERS["pipeline"]["classify"]
        is benchmark_cli._classify_pipeline_suite
    )
    assert benchmark_cli._SUITE_RUNNERS["e2e"]["run"] is benchmark_cli._run_e2e_suite
    assert benchmark_cli._SUITE_RUNNERS["e2e"]["classify"] is benchmark_cli._classify_e2e_suite

    io_runner = benchmark_cli._SUITE_RUNNERS["io"]["run"]
    for suite_name in ("text", "vision", "audio", "pipeline", "e2e"):
        assert benchmark_cli._SUITE_RUNNERS[suite_name]["run"] is not io_runner


@pytest.mark.ci
@pytest.mark.unit
def test_benchmark_model_stub_exposes_safe_cleanup() -> None:
    """Benchmark model stub should support cleanup interface used by processors."""
    model = benchmark_cli._BenchmarkModelStub(
        model_type=ModelType.TEXT,
        prompt_responses={},
        default_response="ok",
    )

    assert model.is_initialized is True
    model.safe_cleanup()
    assert model.is_initialized is False


@pytest.mark.ci
@pytest.mark.unit
@pytest.mark.smoke
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
    if suite_name == "audio" and payload["degraded"] is True:
        assert payload["effective_suite"] == "audio"
        assert payload["degradation_reasons"] == ["audio-synthesized-metadata-fallback"]
    else:
        assert payload["effective_suite"] == suite_name
        assert payload["degraded"] is False
        assert payload["degradation_reasons"] == []
    assert payload["runner_profile_version"] == benchmark_cli._RUNNER_PROFILE_VERSION
    assert payload["files_count"] >= expected["min_files"]
    assert isinstance(payload["hardware_profile"], dict)
    assert payload["hardware_profile"]
    assert payload["results"]["iterations"] == 1
    assert payload["results"]["median_ms"] >= 0.0
    assert payload["results"]["p95_ms"] >= 0.0
    assert payload["results"]["p99_ms"] >= 0.0
    assert payload["results"]["stddev_ms"] >= 0.0
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
    ) as mocked_get_vision_model:
        benchmark_cli._run_vision_suite([image_file])
        mocked_get_vision_model.assert_not_called()


@pytest.mark.ci
@pytest.mark.unit
def test_audio_suite_warns_when_falling_back_to_io() -> None:
    """Audio suite should emit a warning when no audio candidates are available."""
    expected_result = 7
    with patch("file_organizer.cli.benchmark._run_io_suite") as mocked_io_suite:
        mocked_io_suite.return_value = benchmark_cli._SuiteIterationOutcome(
            processed_count=expected_result
        )
        with patch("file_organizer.cli.benchmark.typer.echo") as mocked_echo:
            result = benchmark_cli._run_audio_suite([_CORPUS_DIR / "sample_notes.txt"])

    mocked_io_suite.assert_called_once_with([_CORPUS_DIR / "sample_notes.txt"])
    assert result.processed_count == expected_result
    mocked_echo.assert_called_once_with(
        "Warning: no audio files found; falling back to IO-only benchmark.",
        err=True,
    )


@pytest.mark.ci
@pytest.mark.unit
def test_text_suite_warns_and_skips_when_no_text_candidates() -> None:
    """Text suite should skip when no text candidates are available."""
    with patch("file_organizer.cli.benchmark.typer.echo") as mocked_echo:
        result = benchmark_cli._run_text_suite([_CORPUS_DIR / "sample_photo.jpg"])

    assert result.processed_count == 0
    mocked_echo.assert_called_once_with(
        "Warning: no text files found for text suite; skipping benchmark.",
        err=True,
    )


@pytest.mark.ci
@pytest.mark.unit
def test_vision_suite_warns_and_skips_when_no_vision_candidates() -> None:
    """Vision suite should skip when no vision candidates are available."""
    with patch("file_organizer.cli.benchmark.typer.echo") as mocked_echo:
        result = benchmark_cli._run_vision_suite([_CORPUS_DIR / "sample_notes.txt"])

    assert result.processed_count == 0
    mocked_echo.assert_called_once_with(
        "Warning: no vision files found for vision suite; skipping benchmark.",
        err=True,
    )


@pytest.mark.ci
@pytest.mark.unit
def test_classify_e2e_suite_marks_no_processed_candidates_as_degraded() -> None:
    """E2E classification should mark zero processed candidates as degraded."""
    files = [_CORPUS_DIR / "sample_notes.txt"]

    classification = benchmark_cli._classify_e2e_suite(
        files, benchmark_cli._SuiteIterationOutcome(processed_count=0)
    )

    assert classification.effective_suite == "e2e"
    assert classification.degraded is True
    assert classification.degradation_reasons == ("e2e-no-candidates-processed",)


@pytest.mark.ci
@pytest.mark.unit
def test_execute_suite_iteration_measures_runner_before_classification() -> None:
    """Iteration timing should stop after runner execution, before classifier bookkeeping."""
    observed_call_counts: list[int] = []
    console = MagicMock()

    def _runner(_: list[Path]) -> benchmark_cli._SuiteIterationOutcome:
        return benchmark_cli._SuiteIterationOutcome(processed_count=1)

    def _classifier(
        _: list[Path], _outcome: benchmark_cli._SuiteIterationOutcome
    ) -> benchmark_cli._SuiteExecutionClassification:
        observed_call_counts.append(mocked_monotonic.call_count)
        return benchmark_cli._SuiteExecutionClassification(effective_suite="io", degraded=False)

    with patch(
        "file_organizer.cli.benchmark.time.monotonic",
        side_effect=[10.0, 10.25],
    ) as mocked_monotonic:
        elapsed_ms, processed_count, classification = benchmark_cli._execute_suite_iteration(
            runner=_runner,
            classifier=_classifier,
            files=[_CORPUS_DIR / "sample_notes.txt"],
            suite="io",
            console=console,
        )

    assert observed_call_counts == [2]
    assert elapsed_ms == pytest.approx(250.0)
    assert processed_count == 1
    assert classification.effective_suite == "io"
    assert classification.degraded is False


@pytest.mark.ci
@pytest.mark.unit
def test_execute_suite_iteration_wraps_classifier_failure() -> None:
    """Classifier failures should use the same typed exit flow as runner failures."""
    console = MagicMock()

    def _runner(_: list[Path]) -> benchmark_cli._SuiteIterationOutcome:
        return benchmark_cli._SuiteIterationOutcome(processed_count=1)

    def _classifier(
        _: list[Path], _outcome: benchmark_cli._SuiteIterationOutcome
    ) -> benchmark_cli._SuiteExecutionClassification:
        raise RuntimeError("classification exploded")

    with pytest.raises(typer.Exit) as exc:
        benchmark_cli._execute_suite_iteration(
            runner=_runner,
            classifier=_classifier,
            files=[_CORPUS_DIR / "sample_notes.txt"],
            suite="io",
            console=console,
        )

    assert exc.value.exit_code == 1
    printed_message = console.print.call_args.args[0]
    assert "classification failed" in printed_message


@pytest.mark.ci
@pytest.mark.unit
def test_resolve_processed_count_uses_measured_window() -> None:
    """Processed count should be resolved from measured iterations, not warmup values."""
    console = MagicMock()

    count = benchmark_cli._resolve_processed_count(
        [0, 2, 2],
        warmup=1,
        suite="text",
        console=console,
    )

    assert count == 2
    console.print.assert_not_called()


@pytest.mark.ci
@pytest.mark.unit
def test_resolve_processed_count_fails_when_measured_counts_drift() -> None:
    """Benchmark should fail fast when measured processed counts are inconsistent."""
    console = MagicMock()

    with pytest.raises(typer.Exit) as exc:
        benchmark_cli._resolve_processed_count(
            [2, 1, 2],
            warmup=0,
            suite="io",
            console=console,
        )

    assert exc.value.exit_code == 1
    printed_message = console.print.call_args.args[0]
    assert "inconsistent processed counts" in printed_message


@pytest.mark.ci
@pytest.mark.unit
def test_resolve_processed_count_does_not_check_warmup_only_drift() -> None:
    """When measured window is empty, warmup-only counts should not trigger drift failure."""
    console = MagicMock()

    count = benchmark_cli._resolve_processed_count(
        [3, 1],
        warmup=2,
        suite="vision",
        console=console,
    )

    assert count == 1
    console.print.assert_not_called()
