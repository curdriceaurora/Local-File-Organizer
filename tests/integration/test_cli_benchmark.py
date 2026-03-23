"""Integration tests for cli/benchmark.py.

Covers:
- compute_stats: empty, single item, multiple items, throughput
- _percentile: empty, single, multiple values
- _require_non_negative_numeric_field: valid, bool rejected, negative, non-numeric
- _require_payload_fields: valid, missing fields
- _validate_payload_identity_fields: valid, wrong type, empty string
- _validate_payload_degradation_reasons: valid, degraded mismatch, empty reasons
- _validate_payload_results: valid, missing fields, wrong types
- validate_benchmark_payload: valid full payload, various invalid payloads
- compare_results: no regression, regression, zero baseline, nested results key
- BenchmarkStats: field access
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.integration


def _make_valid_payload(
    *,
    suite: str = "io",
    degraded: bool = False,
    degradation_reasons: list[str] | None = None,
    files_count: int = 10,
) -> dict:
    return {
        "suite": suite,
        "effective_suite": suite,
        "degraded": degraded,
        "degradation_reasons": degradation_reasons or [],
        "runner_profile_version": "1.0",
        "files_count": files_count,
        "hardware_profile": {"cpu": "arm64"},
        "results": {
            "median_ms": 10.0,
            "p95_ms": 20.0,
            "p99_ms": 25.0,
            "stddev_ms": 2.0,
            "throughput_fps": 100.0,
            "iterations": 100,
        },
    }


# ---------------------------------------------------------------------------
# _percentile
# ---------------------------------------------------------------------------


class TestPercentile:
    def test_empty_returns_zero(self) -> None:
        from file_organizer.cli.benchmark import _percentile

        assert _percentile([], 95) == 0.0

    def test_single_element(self) -> None:
        from file_organizer.cli.benchmark import _percentile

        assert _percentile([42.0], 95) == 42.0

    def test_p50_median(self) -> None:
        from file_organizer.cli.benchmark import _percentile

        data = [1.0, 2.0, 3.0, 4.0, 5.0]
        result = _percentile(data, 50)
        assert result == 3.0

    def test_p95_high_end(self) -> None:
        from file_organizer.cli.benchmark import _percentile

        data = list(range(1, 101, 1))
        data = [float(x) for x in data]
        result = _percentile(data, 95)
        assert result == 95.0

    def test_p100_last_element(self) -> None:
        from file_organizer.cli.benchmark import _percentile

        data = [1.0, 5.0, 10.0]
        assert _percentile(data, 100) == 10.0


# ---------------------------------------------------------------------------
# compute_stats
# ---------------------------------------------------------------------------


class TestComputeStats:
    def test_empty_returns_zeros(self) -> None:
        from file_organizer.cli.benchmark import compute_stats

        stats = compute_stats([], 0)
        assert stats["median_ms"] == 0.0
        assert stats["p95_ms"] == 0.0
        assert stats["p99_ms"] == 0.0
        assert stats["stddev_ms"] == 0.0
        assert stats["throughput_fps"] == 0.0
        assert stats["iterations"] == 0

    def test_single_item(self) -> None:
        from file_organizer.cli.benchmark import compute_stats

        stats = compute_stats([100.0], 5)
        assert stats["iterations"] == 1
        assert stats["median_ms"] == 100.0
        assert stats["stddev_ms"] == 0.0

    def test_multiple_items(self) -> None:
        from file_organizer.cli.benchmark import compute_stats

        stats = compute_stats([10.0, 20.0, 30.0, 40.0, 50.0], 1)
        assert stats["iterations"] == 5
        assert stats["median_ms"] == 30.0
        assert stats["stddev_ms"] > 0.0

    def test_throughput_calculation(self) -> None:
        from file_organizer.cli.benchmark import compute_stats

        # median=1000ms = 1s, 5 files → 5 fps
        stats = compute_stats([1000.0], 5)
        assert stats["throughput_fps"] == pytest.approx(5.0)

    def test_p95_and_p99(self) -> None:
        from file_organizer.cli.benchmark import compute_stats

        times = [float(i) for i in range(1, 101)]
        stats = compute_stats(times, 1)
        assert stats["p95_ms"] <= stats["p99_ms"]
        assert stats["p95_ms"] >= 1.0

    def test_zero_median_throughput_is_zero(self) -> None:
        from file_organizer.cli.benchmark import compute_stats

        # All zeros → median=0 → throughput=0
        stats = compute_stats([0.0, 0.0], 5)
        assert stats["throughput_fps"] == 0.0


# ---------------------------------------------------------------------------
# _require_non_negative_numeric_field
# ---------------------------------------------------------------------------


class TestRequireNonNegativeNumericField:
    def test_valid_int(self) -> None:
        from file_organizer.cli.benchmark import _require_non_negative_numeric_field

        _require_non_negative_numeric_field(10, field="test")  # no exception

    def test_valid_float(self) -> None:
        from file_organizer.cli.benchmark import _require_non_negative_numeric_field

        _require_non_negative_numeric_field(3.14, field="test")

    def test_zero_is_valid(self) -> None:
        from file_organizer.cli.benchmark import _require_non_negative_numeric_field

        _require_non_negative_numeric_field(0, field="test")

    def test_bool_raises_type_error(self) -> None:
        from file_organizer.cli.benchmark import _require_non_negative_numeric_field

        with pytest.raises(TypeError, match="must be numeric"):
            _require_non_negative_numeric_field(True, field="test")

    def test_string_raises_type_error(self) -> None:
        from file_organizer.cli.benchmark import _require_non_negative_numeric_field

        with pytest.raises(TypeError, match="must be numeric"):
            _require_non_negative_numeric_field("10", field="test")

    def test_negative_raises_value_error(self) -> None:
        from file_organizer.cli.benchmark import _require_non_negative_numeric_field

        with pytest.raises(ValueError, match="must be non-negative"):
            _require_non_negative_numeric_field(-1.0, field="test")


# ---------------------------------------------------------------------------
# _require_payload_fields
# ---------------------------------------------------------------------------


class TestRequirePayloadFields:
    def test_valid_payload_passes(self) -> None:
        from file_organizer.cli.benchmark import _require_payload_fields

        _require_payload_fields(_make_valid_payload())  # no exception

    def test_missing_field_raises_key_error(self) -> None:
        from file_organizer.cli.benchmark import _require_payload_fields

        payload = _make_valid_payload()
        del payload["suite"]
        with pytest.raises(KeyError, match="suite"):
            _require_payload_fields(payload)

    def test_missing_multiple_fields_lists_them(self) -> None:
        from file_organizer.cli.benchmark import _require_payload_fields

        with pytest.raises(KeyError) as exc_info:
            _require_payload_fields({})
        msg = str(exc_info.value)
        assert "suite" in msg
        assert "results" in msg


# ---------------------------------------------------------------------------
# _validate_payload_identity_fields
# ---------------------------------------------------------------------------


class TestValidatePayloadIdentityFields:
    def test_valid_payload(self) -> None:
        from file_organizer.cli.benchmark import _validate_payload_identity_fields

        _validate_payload_identity_fields(_make_valid_payload())

    def test_non_string_suite_raises_type_error(self) -> None:
        from file_organizer.cli.benchmark import _validate_payload_identity_fields

        payload = _make_valid_payload()
        payload["suite"] = 42
        with pytest.raises(TypeError, match="must be a string"):
            _validate_payload_identity_fields(payload)

    def test_empty_string_suite_raises_value_error(self) -> None:
        from file_organizer.cli.benchmark import _validate_payload_identity_fields

        payload = _make_valid_payload()
        payload["suite"] = ""
        with pytest.raises(ValueError, match="must be non-empty"):
            _validate_payload_identity_fields(payload)


# ---------------------------------------------------------------------------
# _validate_payload_degradation_reasons
# ---------------------------------------------------------------------------


class TestValidatePayloadDegradationReasons:
    def test_valid_non_degraded(self) -> None:
        from file_organizer.cli.benchmark import _validate_payload_degradation_reasons

        _validate_payload_degradation_reasons(_make_valid_payload())

    def test_valid_degraded_with_reasons(self) -> None:
        from file_organizer.cli.benchmark import _validate_payload_degradation_reasons

        payload = _make_valid_payload(degraded=True, degradation_reasons=["cpu throttle"])
        _validate_payload_degradation_reasons(payload)

    def test_degraded_not_bool_raises_type_error(self) -> None:
        from file_organizer.cli.benchmark import _validate_payload_degradation_reasons

        payload = _make_valid_payload()
        payload["degraded"] = "yes"
        with pytest.raises(TypeError):
            _validate_payload_degradation_reasons(payload)

    def test_degraded_true_no_reasons_raises_value_error(self) -> None:
        from file_organizer.cli.benchmark import _validate_payload_degradation_reasons

        payload = _make_valid_payload(degraded=True, degradation_reasons=[])
        with pytest.raises(ValueError, match="non-empty"):
            _validate_payload_degradation_reasons(payload)

    def test_not_degraded_with_reasons_raises_value_error(self) -> None:
        from file_organizer.cli.benchmark import _validate_payload_degradation_reasons

        payload = _make_valid_payload(degraded=False, degradation_reasons=["spurious"])
        with pytest.raises(ValueError, match="must be empty"):
            _validate_payload_degradation_reasons(payload)

    def test_empty_reason_string_raises_value_error(self) -> None:
        from file_organizer.cli.benchmark import _validate_payload_degradation_reasons

        payload = _make_valid_payload(degraded=True, degradation_reasons=[""])
        with pytest.raises(ValueError):
            _validate_payload_degradation_reasons(payload)

    def test_reasons_not_list_raises_type_error(self) -> None:
        from file_organizer.cli.benchmark import _validate_payload_degradation_reasons

        payload = _make_valid_payload()
        payload["degradation_reasons"] = "not a list"
        with pytest.raises(TypeError):
            _validate_payload_degradation_reasons(payload)


# ---------------------------------------------------------------------------
# _validate_payload_results
# ---------------------------------------------------------------------------


class TestValidatePayloadResults:
    def _valid_results(self) -> dict:
        return _make_valid_payload()["results"]

    def test_valid_results_passes(self) -> None:
        from file_organizer.cli.benchmark import _validate_payload_results

        _validate_payload_results(self._valid_results())

    def test_missing_field_raises_key_error(self) -> None:
        from file_organizer.cli.benchmark import _validate_payload_results

        results = self._valid_results()
        del results["median_ms"]
        with pytest.raises(KeyError):
            _validate_payload_results(results)

    def test_bool_iterations_raises_type_error(self) -> None:
        from file_organizer.cli.benchmark import _validate_payload_results

        results = self._valid_results()
        results["iterations"] = True
        with pytest.raises(TypeError):
            _validate_payload_results(results)

    def test_negative_p95_raises_value_error(self) -> None:
        from file_organizer.cli.benchmark import _validate_payload_results

        results = self._valid_results()
        results["p95_ms"] = -1.0
        with pytest.raises(ValueError, match="non-negative"):
            _validate_payload_results(results)

    def test_float_iterations_raises_type_error(self) -> None:
        from file_organizer.cli.benchmark import _validate_payload_results

        # float passes _require_non_negative_numeric_field but fails the int check
        results = self._valid_results()
        results["iterations"] = 1.5
        with pytest.raises(TypeError):
            _validate_payload_results(results)


# ---------------------------------------------------------------------------
# validate_benchmark_payload
# ---------------------------------------------------------------------------


class TestValidateBenchmarkPayload:
    def test_valid_payload_passes(self) -> None:
        from file_organizer.cli.benchmark import validate_benchmark_payload

        validate_benchmark_payload(_make_valid_payload())

    def test_missing_top_level_field_raises(self) -> None:
        from file_organizer.cli.benchmark import validate_benchmark_payload

        payload = _make_valid_payload()
        del payload["hardware_profile"]
        with pytest.raises(KeyError):
            validate_benchmark_payload(payload)

    def test_files_count_bool_raises_type_error(self) -> None:
        from file_organizer.cli.benchmark import validate_benchmark_payload

        payload = _make_valid_payload()
        payload["files_count"] = True
        with pytest.raises(TypeError, match="must be an int"):
            validate_benchmark_payload(payload)

    def test_files_count_negative_raises_value_error(self) -> None:
        from file_organizer.cli.benchmark import validate_benchmark_payload

        payload = _make_valid_payload()
        payload["files_count"] = -1
        with pytest.raises(ValueError, match="non-negative"):
            validate_benchmark_payload(payload)

    def test_hardware_profile_not_dict_raises_type_error(self) -> None:
        from file_organizer.cli.benchmark import validate_benchmark_payload

        payload = _make_valid_payload()
        payload["hardware_profile"] = "not-a-dict"
        with pytest.raises(TypeError, match="must be a dict"):
            validate_benchmark_payload(payload)

    def test_results_not_dict_raises_type_error(self) -> None:
        from file_organizer.cli.benchmark import validate_benchmark_payload

        payload = _make_valid_payload()
        payload["results"] = "not-a-dict"
        with pytest.raises(TypeError, match="must be a dict"):
            validate_benchmark_payload(payload)

    def test_valid_degraded_payload(self) -> None:
        from file_organizer.cli.benchmark import validate_benchmark_payload

        payload = _make_valid_payload(degraded=True, degradation_reasons=["thermal"])
        validate_benchmark_payload(payload)


# ---------------------------------------------------------------------------
# compare_results
# ---------------------------------------------------------------------------


class TestCompareResults:
    def _results(self, p95: float = 10.0) -> dict:
        return {
            "median_ms": p95 * 0.5,
            "p95_ms": p95,
            "p99_ms": p95 * 1.1,
            "stddev_ms": 1.0,
            "throughput_fps": 100.0,
        }

    def test_no_regression(self) -> None:
        from file_organizer.cli.benchmark import compare_results

        result = compare_results(self._results(10.0), self._results(10.0))
        assert result["regression"] is False

    def test_regression_when_p95_exceeds_threshold(self) -> None:
        from file_organizer.cli.benchmark import compare_results

        # current p95=25, baseline p95=10, threshold=1.2 → 25 > 12 → regression
        result = compare_results(self._results(25.0), self._results(10.0), threshold=1.2)
        assert result["regression"] is True

    def test_deltas_pct_keys_present(self) -> None:
        from file_organizer.cli.benchmark import compare_results

        result = compare_results(self._results(10.0), self._results(5.0))
        for key in ("median_ms", "p95_ms", "p99_ms", "stddev_ms", "throughput_fps"):
            assert key in result["deltas_pct"]

    def test_zero_baseline_gives_zero_delta(self) -> None:
        from file_organizer.cli.benchmark import compare_results

        baseline = dict.fromkeys(
            ("median_ms", "p95_ms", "p99_ms", "stddev_ms", "throughput_fps"), 0.0
        )
        current = self._results(5.0)
        result = compare_results(current, baseline)
        assert result["deltas_pct"]["p95_ms"] == 0.0

    def test_nested_results_key(self) -> None:
        from file_organizer.cli.benchmark import compare_results

        current = {"results": self._results(10.0)}
        baseline = {"results": self._results(10.0)}
        result = compare_results(current, baseline)
        assert result["regression"] is False

    def test_custom_threshold(self) -> None:
        from file_organizer.cli.benchmark import compare_results

        # With threshold=2.0, p95=15 vs baseline 10 → 15 < 20 → no regression
        result = compare_results(self._results(15.0), self._results(10.0), threshold=2.0)
        assert result["regression"] is False
        assert result["threshold"] == 2.0

    def test_improvement_gives_negative_delta(self) -> None:
        from file_organizer.cli.benchmark import compare_results

        # current faster than baseline → negative delta for ms metrics
        result = compare_results(self._results(5.0), self._results(10.0))
        assert result["deltas_pct"]["p95_ms"] < 0.0


# ---------------------------------------------------------------------------
# _SuiteIterationOutcome / _SuiteExecutionClassification dataclasses
# ---------------------------------------------------------------------------


class TestSuiteDataclasses:
    def test_iteration_outcome_defaults(self) -> None:
        from file_organizer.cli.benchmark import _SuiteIterationOutcome

        outcome = _SuiteIterationOutcome(processed_count=5)
        assert outcome.processed_count == 5
        assert outcome.used_synthetic_audio_metadata is False

    def test_iteration_outcome_with_synthetic_flag(self) -> None:
        from file_organizer.cli.benchmark import _SuiteIterationOutcome

        outcome = _SuiteIterationOutcome(processed_count=3, used_synthetic_audio_metadata=True)
        assert outcome.used_synthetic_audio_metadata is True

    def test_execution_classification_fields(self) -> None:
        from file_organizer.cli.benchmark import _SuiteExecutionClassification

        cls = _SuiteExecutionClassification(effective_suite="io", degraded=False)
        assert cls.effective_suite == "io"
        assert cls.degraded is False
        assert cls.degradation_reasons == ()

    def test_execution_classification_with_reasons(self) -> None:
        from file_organizer.cli.benchmark import _SuiteExecutionClassification

        cls = _SuiteExecutionClassification(
            effective_suite="audio",
            degraded=True,
            degradation_reasons=("audio-no-candidates-fallback-to-io",),
        )
        assert cls.degraded is True
        assert "audio-no-candidates-fallback-to-io" in cls.degradation_reasons


# ---------------------------------------------------------------------------
# _suite_candidates
# ---------------------------------------------------------------------------


class TestSuiteCandidates:
    def test_returns_matching_extensions(self, tmp_path: Path) -> None:

        from file_organizer.cli.benchmark import _suite_candidates

        (tmp_path / "a.txt").touch()
        (tmp_path / "b.jpg").touch()
        (tmp_path / "c.pdf").touch()
        files = [tmp_path / "a.txt", tmp_path / "b.jpg", tmp_path / "c.pdf"]
        result = _suite_candidates(files, {".txt", ".pdf"})
        assert len(result) == 2

    def test_no_match_returns_empty_without_fallback(self, tmp_path: Path) -> None:

        from file_organizer.cli.benchmark import _suite_candidates

        files = [tmp_path / "a.mp3", tmp_path / "b.wav"]
        result = _suite_candidates(files, {".txt"}, fallback_to_all=False)
        assert result == []

    def test_fallback_to_all_when_no_match(self, tmp_path: Path) -> None:

        from file_organizer.cli.benchmark import _suite_candidates

        files = [tmp_path / "a.mp3", tmp_path / "b.wav"]
        result = _suite_candidates(files, {".txt"}, fallback_to_all=True)
        assert len(result) == 2

    def test_cap_limits_output(self, tmp_path: Path) -> None:

        from file_organizer.cli.benchmark import _suite_candidates

        files = [tmp_path / f"f{i}.txt" for i in range(100)]
        result = _suite_candidates(files, {".txt"}, cap=5)
        assert len(result) == 5

    def test_empty_files_returns_empty(self) -> None:
        from file_organizer.cli.benchmark import _suite_candidates

        result = _suite_candidates([], {".txt"})
        assert result == []


# ---------------------------------------------------------------------------
# _classify_* functions
# ---------------------------------------------------------------------------


class TestClassifyFunctions:
    def test_classify_io_suite_never_degraded(self) -> None:
        from file_organizer.cli.benchmark import _classify_io_suite, _SuiteIterationOutcome

        outcome = _SuiteIterationOutcome(processed_count=5)
        cls = _classify_io_suite([], outcome)
        assert cls.effective_suite == "io"
        assert cls.degraded is False

    def test_classify_text_suite_no_candidates_degraded(self) -> None:
        from file_organizer.cli.benchmark import _classify_text_suite, _SuiteIterationOutcome

        outcome = _SuiteIterationOutcome(processed_count=0)
        # No text files → degraded
        cls = _classify_text_suite([], outcome)
        assert cls.degraded is True
        assert "text-no-candidates-skip" in cls.degradation_reasons

    def test_classify_text_suite_with_text_files(self, tmp_path: Path) -> None:
        from file_organizer.cli.benchmark import _classify_text_suite, _SuiteIterationOutcome

        files = [tmp_path / "a.txt", tmp_path / "b.md"]
        outcome = _SuiteIterationOutcome(processed_count=2)
        cls = _classify_text_suite(files, outcome)
        assert cls.degraded is False
        assert cls.effective_suite == "text"

    def test_classify_vision_suite_no_candidates_degraded(self) -> None:
        from file_organizer.cli.benchmark import _classify_vision_suite, _SuiteIterationOutcome

        outcome = _SuiteIterationOutcome(processed_count=0)
        cls = _classify_vision_suite([], outcome)
        assert cls.degraded is True
        assert "vision-no-candidates-skip" in cls.degradation_reasons

    def test_classify_vision_suite_with_images(self, tmp_path: Path) -> None:
        from file_organizer.cli.benchmark import _classify_vision_suite, _SuiteIterationOutcome

        files = [tmp_path / "img.jpg"]
        outcome = _SuiteIterationOutcome(processed_count=1)
        cls = _classify_vision_suite(files, outcome)
        assert cls.degraded is False
        assert cls.effective_suite == "vision"

    def test_classify_audio_suite_no_candidates_fallback(self) -> None:
        from file_organizer.cli.benchmark import _classify_audio_suite, _SuiteIterationOutcome

        outcome = _SuiteIterationOutcome(processed_count=0)
        cls = _classify_audio_suite([], outcome)
        assert cls.degraded is True
        assert "audio-no-candidates-fallback-to-io" in cls.degradation_reasons
        assert cls.effective_suite == "io"

    def test_classify_audio_suite_synthetic_metadata(self, tmp_path: Path) -> None:
        from file_organizer.cli.benchmark import _classify_audio_suite, _SuiteIterationOutcome

        files = [tmp_path / "song.mp3"]
        outcome = _SuiteIterationOutcome(processed_count=1, used_synthetic_audio_metadata=True)
        cls = _classify_audio_suite(files, outcome)
        assert cls.degraded is True
        assert "audio-synthesized-metadata-fallback" in cls.degradation_reasons

    def test_classify_audio_suite_clean(self, tmp_path: Path) -> None:
        from file_organizer.cli.benchmark import _classify_audio_suite, _SuiteIterationOutcome

        files = [tmp_path / "song.mp3"]
        outcome = _SuiteIterationOutcome(processed_count=1, used_synthetic_audio_metadata=False)
        cls = _classify_audio_suite(files, outcome)
        assert cls.degraded is False
        assert cls.effective_suite == "audio"

    def test_classify_pipeline_suite_never_degraded(self) -> None:
        from file_organizer.cli.benchmark import (
            _classify_pipeline_suite,
            _SuiteIterationOutcome,
        )

        outcome = _SuiteIterationOutcome(processed_count=5)
        cls = _classify_pipeline_suite([], outcome)
        assert cls.effective_suite == "pipeline"
        assert cls.degraded is False

    def test_classify_e2e_suite_no_processed_files(self, tmp_path: Path) -> None:
        from file_organizer.cli.benchmark import _classify_e2e_suite, _SuiteIterationOutcome

        files = [tmp_path / "f.txt"]
        outcome = _SuiteIterationOutcome(processed_count=0)
        cls = _classify_e2e_suite(files, outcome)
        assert cls.degraded is True
        assert "e2e-no-candidates-processed" in cls.degradation_reasons

    def test_classify_e2e_suite_success(self, tmp_path: Path) -> None:
        from file_organizer.cli.benchmark import _classify_e2e_suite, _SuiteIterationOutcome

        files = [tmp_path / "f.txt"]
        outcome = _SuiteIterationOutcome(processed_count=1)
        cls = _classify_e2e_suite(files, outcome)
        assert cls.degraded is False
        assert cls.effective_suite == "e2e"

    def test_classify_e2e_suite_empty_files(self) -> None:
        from file_organizer.cli.benchmark import _classify_e2e_suite, _SuiteIterationOutcome

        outcome = _SuiteIterationOutcome(processed_count=0)
        cls = _classify_e2e_suite([], outcome)
        assert cls.degraded is False


# ---------------------------------------------------------------------------
# _BenchmarkModelStub
# ---------------------------------------------------------------------------


class TestBenchmarkModelStub:
    def _stub(self) -> Any:
        from file_organizer.cli.benchmark import _BenchmarkModelStub
        from file_organizer.models.base import ModelType

        return _BenchmarkModelStub(
            model_type=ModelType.TEXT,
            prompt_responses={"hello": "world"},
            default_response="default",
        )

    def test_is_initialized_true(self) -> None:
        stub = self._stub()
        assert stub.is_initialized is True

    def test_generate_known_prompt(self) -> None:
        stub = self._stub()
        result = stub.generate("say hello please")
        assert result == "world"

    def test_generate_unknown_prompt_returns_default(self) -> None:
        stub = self._stub()
        result = stub.generate("something completely different")
        assert result == "default"

    def test_initialize_sets_flag(self) -> None:
        stub = self._stub()
        stub.cleanup()
        assert stub.is_initialized is False
        stub.initialize()
        assert stub.is_initialized is True

    def test_cleanup_clears_flag(self) -> None:
        stub = self._stub()
        stub.cleanup()
        assert stub.is_initialized is False

    def test_config_name(self) -> None:
        stub = self._stub()
        assert stub.config.name == "benchmark-stub"


# ---------------------------------------------------------------------------
# _resolve_processed_count
# ---------------------------------------------------------------------------


class TestResolveProcessedCount:
    def test_consistent_counts_returns_last(self) -> None:

        from file_organizer.cli.benchmark import _resolve_processed_count

        console = MagicMock()
        result = _resolve_processed_count([5, 5, 5], warmup=1, suite="io", console=console)
        assert result == 5

    def test_empty_measured_falls_back_to_last(self) -> None:

        from file_organizer.cli.benchmark import _resolve_processed_count

        console = MagicMock()
        result = _resolve_processed_count([3], warmup=1, suite="io", console=console)
        assert result == 3

    def test_completely_empty_returns_zero(self) -> None:

        from file_organizer.cli.benchmark import _resolve_processed_count

        console = MagicMock()
        result = _resolve_processed_count([], warmup=0, suite="io", console=console)
        assert result == 0

    def test_inconsistent_counts_raises_exit(self) -> None:

        import typer

        from file_organizer.cli.benchmark import _resolve_processed_count

        console = MagicMock()
        with pytest.raises(SystemExit) as excinfo:
            try:
                _resolve_processed_count([1, 2, 3], warmup=0, suite="io", console=console)
            except typer.Exit as e:
                raise SystemExit(e.exit_code) from e
        assert excinfo.value.code == 1
        console.print.assert_called_once()


# ---------------------------------------------------------------------------
# _detect_hardware_profile
# ---------------------------------------------------------------------------


class TestDetectHardwareProfile:
    def test_returns_dict_with_keys(self) -> None:
        from file_organizer.cli.benchmark import _detect_hardware_profile

        result = _detect_hardware_profile()
        assert isinstance(result, dict)
        assert len(result) > 0

    def test_fallback_contains_error_key(self) -> None:
        from unittest.mock import patch

        from file_organizer.cli.benchmark import _detect_hardware_profile

        with patch(
            "file_organizer.core.hardware_profile.detect_hardware",
            side_effect=RuntimeError("simulated hardware detection failure"),
        ):
            result = _detect_hardware_profile()
        assert "error" in result


# ---------------------------------------------------------------------------
# _check_baseline_profile_compatibility
# ---------------------------------------------------------------------------


class TestCheckBaselineProfileCompatibility:
    def test_none_profile_returns_none(self) -> None:

        from file_organizer.cli.benchmark import _check_baseline_profile_compatibility

        console = MagicMock()
        result = _check_baseline_profile_compatibility(
            {}, suite="io", console=console, json_output=False
        )
        assert result is None

    def test_matching_profile_returns_none(self) -> None:

        from file_organizer.cli.benchmark import (
            _RUNNER_PROFILE_VERSION,
            _check_baseline_profile_compatibility,
        )

        console = MagicMock()
        result = _check_baseline_profile_compatibility(
            {"runner_profile_version": _RUNNER_PROFILE_VERSION},
            suite="io",
            console=console,
            json_output=False,
        )
        assert result is None

    def test_mismatched_profile_returns_warning(self) -> None:

        from file_organizer.cli.benchmark import _check_baseline_profile_compatibility

        console = MagicMock()
        result = _check_baseline_profile_compatibility(
            {"runner_profile_version": "old-profile-v0"},
            suite="io",
            console=console,
            json_output=False,
        )
        assert result is not None
        assert "mismatch" in result.lower()

    def test_json_output_skips_console_print(self) -> None:

        from file_organizer.cli.benchmark import _check_baseline_profile_compatibility

        console = MagicMock()
        _check_baseline_profile_compatibility(
            {"runner_profile_version": "old-profile-v0"},
            suite="io",
            console=console,
            json_output=True,
        )
        console.print.assert_not_called()


# ---------------------------------------------------------------------------
# _run_io_suite
# ---------------------------------------------------------------------------


class TestRunIoSuite:
    def test_returns_outcome_with_count(self, tmp_path: Path) -> None:
        from file_organizer.cli.benchmark import _run_io_suite

        (tmp_path / "a.txt").write_text("hello")
        (tmp_path / "b.txt").write_text("world")
        files = [tmp_path / "a.txt", tmp_path / "b.txt"]
        outcome = _run_io_suite(files)
        assert outcome.processed_count == 2

    def test_empty_files_returns_zero(self) -> None:
        from file_organizer.cli.benchmark import _run_io_suite

        outcome = _run_io_suite([])
        assert outcome.processed_count == 0

    def test_handles_oserror_gracefully(self, tmp_path: Path) -> None:
        from file_organizer.cli.benchmark import _run_io_suite

        # Exercises the OSError branch in _run_io_suite: passing a nonexistent file causes
        # an OSError during the read attempt. Graceful handling means the function increments
        # outcome.processed_count (the file was attempted) and returns without raising.
        outcome = _run_io_suite([tmp_path / "nonexistent.txt"])
        assert outcome.processed_count == 1


# ---------------------------------------------------------------------------
# _BenchmarkModelStub.safe_cleanup
# ---------------------------------------------------------------------------


class TestBenchmarkModelStubSafeCleanup:
    def test_safe_cleanup_calls_cleanup(self) -> None:
        from file_organizer.cli.benchmark import _BenchmarkModelStub
        from file_organizer.models.base import ModelType

        stub = _BenchmarkModelStub(
            model_type=ModelType.TEXT,
            prompt_responses={},
            default_response="default",
        )
        assert stub.is_initialized is True
        stub.safe_cleanup()
        assert stub.is_initialized is False


# ---------------------------------------------------------------------------
# _summarize_suite_classifications
# ---------------------------------------------------------------------------


class TestSummarizeSuiteClassifications:
    def test_all_clean_returns_not_degraded(self) -> None:
        from file_organizer.cli.benchmark import (
            _SuiteExecutionClassification,
            _summarize_suite_classifications,
        )

        classifications = [
            _SuiteExecutionClassification(effective_suite="io", degraded=False),
            _SuiteExecutionClassification(effective_suite="io", degraded=False),
        ]
        suite, degraded, reasons = _summarize_suite_classifications(
            classifications, warmup=0, requested_suite="io"
        )
        assert suite == "io"
        assert degraded is False
        assert reasons == []

    def test_degraded_classification_propagates(self) -> None:
        from file_organizer.cli.benchmark import (
            _SuiteExecutionClassification,
            _summarize_suite_classifications,
        )

        classifications = [
            _SuiteExecutionClassification(
                effective_suite="io",
                degraded=True,
                degradation_reasons=("audio-no-candidates-fallback-to-io",),
            ),
        ]
        _suite, degraded, reasons = _summarize_suite_classifications(
            classifications, warmup=0, requested_suite="audio"
        )
        assert degraded is True
        assert "audio-no-candidates-fallback-to-io" in reasons

    def test_warmup_excluded_from_analysis(self) -> None:
        from file_organizer.cli.benchmark import (
            _SuiteExecutionClassification,
            _summarize_suite_classifications,
        )

        # warmup=1 means first entry is excluded
        classifications = [
            _SuiteExecutionClassification(
                effective_suite="io",
                degraded=True,
                degradation_reasons=("warmup-degraded",),
            ),
            _SuiteExecutionClassification(effective_suite="io", degraded=False),
        ]
        _suite, degraded, reasons = _summarize_suite_classifications(
            classifications, warmup=1, requested_suite="io"
        )
        assert degraded is False
        assert reasons == []

    def test_mixed_suite_names_returns_mixed(self) -> None:
        from file_organizer.cli.benchmark import (
            _SuiteExecutionClassification,
            _summarize_suite_classifications,
        )

        classifications = [
            _SuiteExecutionClassification(effective_suite="io", degraded=False),
            _SuiteExecutionClassification(effective_suite="text", degraded=False),
        ]
        suite, _degraded, _reasons = _summarize_suite_classifications(
            classifications, warmup=0, requested_suite="io"
        )
        assert suite == "mixed"

    def test_empty_after_warmup_returns_requested_suite(self) -> None:
        from file_organizer.cli.benchmark import _summarize_suite_classifications

        suite, degraded, reasons = _summarize_suite_classifications(
            [], warmup=0, requested_suite="text"
        )
        assert suite == "text"
        assert degraded is False
        assert reasons == []
