"""Integration tests for CLI benchmark utility functions.

Covers pure-function helpers and validators in cli/benchmark.py:
  - _percentile, compute_stats
  - validate_benchmark_payload and sub-validators
  - compare_results
  - _resolve_processed_count
  - _suite_candidates
  - _classify_*_suite functions
  - _check_baseline_profile_compatibility
  - _summarize_suite_classifications
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

pytestmark = [pytest.mark.integration]


# ---------------------------------------------------------------------------
# Helpers — build valid payloads for validate_benchmark_payload
# ---------------------------------------------------------------------------


def _valid_payload(**overrides: object) -> dict:
    base = {
        "suite": "io",
        "effective_suite": "io",
        "degraded": False,
        "degradation_reasons": [],
        "runner_profile_version": "2026-03-14-v1",
        "files_count": 5,
        "hardware_profile": {"cpu": "x86_64", "ram_gb": 16},
        "results": {
            "median_ms": 10.0,
            "p95_ms": 20.0,
            "p99_ms": 25.0,
            "stddev_ms": 2.0,
            "throughput_fps": 100.0,
            "iterations": 10,
        },
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# _percentile
# ---------------------------------------------------------------------------


class TestPercentile:
    def test_empty_list_returns_zero(self) -> None:
        from file_organizer.cli.benchmark import _percentile

        assert _percentile([], 50) == 0.0

    def test_single_element_returns_it(self) -> None:
        from file_organizer.cli.benchmark import _percentile

        assert _percentile([42.0], 50) == 42.0

    def test_p50_on_sorted_list(self) -> None:
        from file_organizer.cli.benchmark import _percentile

        data = [1.0, 2.0, 3.0, 4.0, 5.0]
        result = _percentile(data, 50)
        assert result == pytest.approx(3.0)

    def test_p95_on_ten_elements(self) -> None:
        from file_organizer.cli.benchmark import _percentile

        data = [float(i) for i in range(1, 11)]
        result = _percentile(data, 95)
        assert result == 10.0

    def test_p99_on_ten_elements(self) -> None:
        from file_organizer.cli.benchmark import _percentile

        data = [float(i) for i in range(1, 11)]
        result = _percentile(data, 99)
        assert result == 10.0

    def test_p0_returns_first_element(self) -> None:
        from file_organizer.cli.benchmark import _percentile

        data = [1.0, 2.0, 3.0]
        # ceil(0) = 0, max(0, -1) = 0 → data[0]
        result = _percentile(data, 0)
        assert result == 1.0


# ---------------------------------------------------------------------------
# compute_stats
# ---------------------------------------------------------------------------


class TestComputeStats:
    def test_empty_times_returns_zeros(self) -> None:
        from file_organizer.cli.benchmark import compute_stats

        stats = compute_stats([], 0)
        assert stats["median_ms"] == 0.0
        assert stats["p95_ms"] == 0.0
        assert stats["iterations"] == 0

    def test_single_element(self) -> None:
        from file_organizer.cli.benchmark import compute_stats

        stats = compute_stats([100.0], 1)
        assert stats["median_ms"] == 100.0
        assert stats["stddev_ms"] == 0.0
        assert stats["iterations"] == 1

    def test_throughput_calculated(self) -> None:
        from file_organizer.cli.benchmark import compute_stats

        stats = compute_stats([1000.0], 5)
        assert stats["throughput_fps"] == pytest.approx(5.0)

    def test_stddev_multiple_elements(self) -> None:
        from file_organizer.cli.benchmark import compute_stats

        stats = compute_stats([10.0, 20.0, 30.0], 1)
        assert stats["stddev_ms"] > 0

    def test_p95_p99_on_large_list(self) -> None:
        from file_organizer.cli.benchmark import compute_stats

        times = [float(i) for i in range(1, 101)]
        stats = compute_stats(times, 1)
        assert stats["p95_ms"] == 95.0
        assert stats["p99_ms"] == 99.0
        assert stats["iterations"] == 100

    def test_zero_median_throughput_zero(self) -> None:
        from file_organizer.cli.benchmark import compute_stats

        stats = compute_stats([0.0, 0.0], 5)
        assert stats["throughput_fps"] == 0.0


# ---------------------------------------------------------------------------
# _require_non_negative_numeric_field
# ---------------------------------------------------------------------------


class TestRequireNonNegativeNumericField:
    def test_valid_int(self) -> None:
        from file_organizer.cli.benchmark import _require_non_negative_numeric_field

        _require_non_negative_numeric_field(5, field="count")

    def test_valid_float(self) -> None:
        from file_organizer.cli.benchmark import _require_non_negative_numeric_field

        _require_non_negative_numeric_field(3.14, field="ms")

    def test_bool_raises_type_error(self) -> None:
        from file_organizer.cli.benchmark import _require_non_negative_numeric_field

        with pytest.raises(TypeError):
            _require_non_negative_numeric_field(True, field="count")

    def test_string_raises_type_error(self) -> None:
        from file_organizer.cli.benchmark import _require_non_negative_numeric_field

        with pytest.raises(TypeError):
            _require_non_negative_numeric_field("5", field="count")

    def test_negative_raises_value_error(self) -> None:
        from file_organizer.cli.benchmark import _require_non_negative_numeric_field

        with pytest.raises(ValueError):
            _require_non_negative_numeric_field(-1.0, field="ms")

    def test_zero_is_valid(self) -> None:
        from file_organizer.cli.benchmark import _require_non_negative_numeric_field

        _require_non_negative_numeric_field(0, field="ms")


# ---------------------------------------------------------------------------
# validate_benchmark_payload
# ---------------------------------------------------------------------------


class TestValidateBenchmarkPayload:
    def test_valid_payload_passes(self) -> None:
        from file_organizer.cli.benchmark import validate_benchmark_payload

        validate_benchmark_payload(_valid_payload())

    def test_missing_suite_raises_key_error(self) -> None:
        from file_organizer.cli.benchmark import validate_benchmark_payload

        payload = _valid_payload()
        del payload["suite"]
        with pytest.raises(KeyError):
            validate_benchmark_payload(payload)

    def test_missing_multiple_fields_raises_key_error(self) -> None:
        from file_organizer.cli.benchmark import validate_benchmark_payload

        with pytest.raises(KeyError):
            validate_benchmark_payload({})

    def test_suite_not_string_raises_type_error(self) -> None:
        from file_organizer.cli.benchmark import validate_benchmark_payload

        with pytest.raises(TypeError):
            validate_benchmark_payload(_valid_payload(suite=123))

    def test_empty_suite_raises_value_error(self) -> None:
        from file_organizer.cli.benchmark import validate_benchmark_payload

        with pytest.raises(ValueError):
            validate_benchmark_payload(_valid_payload(suite=""))

    def test_degraded_true_empty_reasons_raises(self) -> None:
        from file_organizer.cli.benchmark import validate_benchmark_payload

        with pytest.raises(ValueError):
            validate_benchmark_payload(_valid_payload(degraded=True, degradation_reasons=[]))

    def test_degraded_false_nonempty_reasons_raises(self) -> None:
        from file_organizer.cli.benchmark import validate_benchmark_payload

        with pytest.raises(ValueError):
            validate_benchmark_payload(
                _valid_payload(degraded=False, degradation_reasons=["reason"])
            )

    def test_degraded_true_with_reasons_passes(self) -> None:
        from file_organizer.cli.benchmark import validate_benchmark_payload

        validate_benchmark_payload(_valid_payload(degraded=True, degradation_reasons=["slow-disk"]))

    def test_files_count_bool_raises_type_error(self) -> None:
        from file_organizer.cli.benchmark import validate_benchmark_payload

        with pytest.raises(TypeError):
            validate_benchmark_payload(_valid_payload(files_count=True))

    def test_files_count_negative_raises_value_error(self) -> None:
        from file_organizer.cli.benchmark import validate_benchmark_payload

        with pytest.raises(ValueError):
            validate_benchmark_payload(_valid_payload(files_count=-1))

    def test_hardware_profile_not_dict_raises_type_error(self) -> None:
        from file_organizer.cli.benchmark import validate_benchmark_payload

        with pytest.raises(TypeError):
            validate_benchmark_payload(_valid_payload(hardware_profile="not-dict"))

    def test_results_not_dict_raises_type_error(self) -> None:
        from file_organizer.cli.benchmark import validate_benchmark_payload

        with pytest.raises(TypeError):
            validate_benchmark_payload(_valid_payload(results="not-dict"))

    def test_degraded_not_bool_raises_type_error(self) -> None:
        from file_organizer.cli.benchmark import validate_benchmark_payload

        with pytest.raises(TypeError):
            validate_benchmark_payload(_valid_payload(degraded="yes"))

    def test_degradation_reasons_not_list_raises_type_error(self) -> None:
        from file_organizer.cli.benchmark import validate_benchmark_payload

        with pytest.raises(TypeError):
            validate_benchmark_payload(_valid_payload(degradation_reasons="reason"))

    def test_degradation_reason_empty_string_raises_value_error(self) -> None:
        from file_organizer.cli.benchmark import validate_benchmark_payload

        with pytest.raises(ValueError):
            validate_benchmark_payload(_valid_payload(degraded=True, degradation_reasons=[""]))


# ---------------------------------------------------------------------------
# _validate_payload_results
# ---------------------------------------------------------------------------


class TestValidatePayloadResults:
    def test_missing_result_field_raises_key_error(self) -> None:
        from file_organizer.cli.benchmark import _validate_payload_results

        results = {
            "median_ms": 10.0,
            "p95_ms": 20.0,
            "p99_ms": 25.0,
            "stddev_ms": 2.0,
            "throughput_fps": 100.0,
            # iterations missing
        }
        with pytest.raises(KeyError):
            _validate_payload_results(results)

    def test_iterations_bool_raises_type_error(self) -> None:
        from file_organizer.cli.benchmark import _validate_payload_results

        results = {
            "median_ms": 10.0,
            "p95_ms": 20.0,
            "p99_ms": 25.0,
            "stddev_ms": 2.0,
            "throughput_fps": 100.0,
            "iterations": True,
        }
        with pytest.raises(TypeError):
            _validate_payload_results(results)

    def test_valid_results_passes(self) -> None:
        from file_organizer.cli.benchmark import _validate_payload_results

        _validate_payload_results(_valid_payload()["results"])


# ---------------------------------------------------------------------------
# compare_results
# ---------------------------------------------------------------------------


class TestCompareResults:
    def _baseline(self) -> dict:
        return {
            "results": {
                "median_ms": 10.0,
                "p95_ms": 20.0,
                "p99_ms": 25.0,
                "stddev_ms": 2.0,
                "throughput_fps": 100.0,
            }
        }

    def test_no_regression_when_same(self) -> None:
        from file_organizer.cli.benchmark import compare_results

        result = compare_results(self._baseline(), self._baseline())
        assert result["regression"] is False

    def test_regression_when_p95_exceeds_threshold(self) -> None:
        from file_organizer.cli.benchmark import compare_results

        current = {
            "results": {
                "median_ms": 10.0,
                "p95_ms": 50.0,
                "p99_ms": 55.0,
                "stddev_ms": 2.0,
                "throughput_fps": 100.0,
            }
        }
        result = compare_results(current, self._baseline(), threshold=1.2)
        assert result["regression"] is True

    def test_deltas_computed(self) -> None:
        from file_organizer.cli.benchmark import compare_results

        current = {
            "results": {
                "median_ms": 20.0,
                "p95_ms": 20.0,
                "p99_ms": 25.0,
                "stddev_ms": 2.0,
                "throughput_fps": 100.0,
            }
        }
        result = compare_results(current, self._baseline())
        assert result["deltas_pct"]["median_ms"] == pytest.approx(100.0)

    def test_zero_baseline_produces_zero_delta(self) -> None:
        from file_organizer.cli.benchmark import compare_results

        baseline = {
            "results": {
                "median_ms": 0.0,
                "p95_ms": 0.0,
                "p99_ms": 0.0,
                "stddev_ms": 0.0,
                "throughput_fps": 0.0,
            }
        }
        current = {
            "results": {
                "median_ms": 5.0,
                "p95_ms": 5.0,
                "p99_ms": 5.0,
                "stddev_ms": 1.0,
                "throughput_fps": 50.0,
            }
        }
        result = compare_results(current, baseline)
        assert result["deltas_pct"]["median_ms"] == 0.0

    def test_accepts_flat_dict_without_results_key(self) -> None:
        from file_organizer.cli.benchmark import compare_results

        flat = {
            "median_ms": 10.0,
            "p95_ms": 20.0,
            "p99_ms": 25.0,
            "stddev_ms": 2.0,
            "throughput_fps": 100.0,
        }
        result = compare_results(flat, flat)
        assert result["regression"] is False


# ---------------------------------------------------------------------------
# _suite_candidates
# ---------------------------------------------------------------------------


class TestSuiteCandidates:
    def test_returns_matching_extensions(self, tmp_path: Path) -> None:
        from file_organizer.cli.benchmark import _suite_candidates

        (tmp_path / "a.txt").write_text("x")
        (tmp_path / "b.jpg").write_bytes(b"x")
        (tmp_path / "c.csv").write_text("x")
        files = list(tmp_path.iterdir())
        result = _suite_candidates(files, {".txt", ".csv"})
        names = {f.name for f in result}
        assert "a.txt" in names
        assert "c.csv" in names
        assert "b.jpg" not in names

    def test_fallback_to_all_when_no_match(self, tmp_path: Path) -> None:
        from file_organizer.cli.benchmark import _suite_candidates

        d = tmp_path / "files"
        d.mkdir()
        (d / "a.jpg").write_bytes(b"x")
        (d / "b.png").write_bytes(b"x")
        files = [f for f in d.iterdir() if f.is_file()]
        result = _suite_candidates(files, {".txt"}, fallback_to_all=True)
        assert len(result) == 2

    def test_no_fallback_returns_empty_when_no_match(self, tmp_path: Path) -> None:
        from file_organizer.cli.benchmark import _suite_candidates

        (tmp_path / "a.jpg").write_bytes(b"x")
        files = list(tmp_path.iterdir())
        result = _suite_candidates(files, {".txt"}, fallback_to_all=False)
        assert result == []

    def test_empty_file_list_returns_empty(self) -> None:
        from file_organizer.cli.benchmark import _suite_candidates

        result = _suite_candidates([], {".txt"})
        assert result == []


# ---------------------------------------------------------------------------
# _classify_*_suite functions
# ---------------------------------------------------------------------------


class TestClassifySuites:
    def _outcome(self, processed: int = 1, synth: bool = False) -> object:
        from file_organizer.cli.benchmark import _SuiteIterationOutcome

        return _SuiteIterationOutcome(
            processed_count=processed, used_synthetic_audio_metadata=synth
        )

    def test_classify_io_suite_never_degraded(self, tmp_path: Path) -> None:
        from file_organizer.cli.benchmark import _classify_io_suite

        result = _classify_io_suite([], self._outcome())
        assert result.degraded is False
        assert result.effective_suite == "io"

    def test_classify_text_suite_no_candidates_degraded(self) -> None:
        from file_organizer.cli.benchmark import _classify_text_suite

        result = _classify_text_suite([], self._outcome())
        assert result.degraded is True
        assert "text-no-candidates-skip" in result.degradation_reasons

    def test_classify_text_suite_with_text_files_not_degraded(self, tmp_path: Path) -> None:
        from file_organizer.cli.benchmark import _classify_text_suite

        f = tmp_path / "doc.txt"
        f.write_text("x")
        result = _classify_text_suite([f], self._outcome())
        assert result.degraded is False

    def test_classify_vision_suite_no_candidates_degraded(self) -> None:
        from file_organizer.cli.benchmark import _classify_vision_suite

        result = _classify_vision_suite([], self._outcome())
        assert result.degraded is True

    def test_classify_vision_suite_with_image_not_degraded(self, tmp_path: Path) -> None:
        from file_organizer.cli.benchmark import _classify_vision_suite

        f = tmp_path / "img.jpg"
        f.write_bytes(b"x")
        result = _classify_vision_suite([f], self._outcome())
        assert result.degraded is False

    def test_classify_audio_suite_no_candidates_falls_back_to_io(self) -> None:
        from file_organizer.cli.benchmark import _classify_audio_suite

        result = _classify_audio_suite([], self._outcome())
        assert result.degraded is True
        assert result.effective_suite == "io"

    def test_classify_audio_suite_synthetic_metadata_degraded(self, tmp_path: Path) -> None:
        from file_organizer.cli.benchmark import _classify_audio_suite

        f = tmp_path / "song.mp3"
        f.write_bytes(b"x")
        result = _classify_audio_suite([f], self._outcome(synth=True))
        assert result.degraded is True
        assert "audio-synthesized-metadata-fallback" in result.degradation_reasons

    def test_classify_audio_suite_real_audio_not_degraded(self, tmp_path: Path) -> None:
        from file_organizer.cli.benchmark import _classify_audio_suite

        f = tmp_path / "song.mp3"
        f.write_bytes(b"x")
        result = _classify_audio_suite([f], self._outcome(synth=False))
        assert result.degraded is False

    def test_classify_pipeline_suite_never_degraded(self) -> None:
        from file_organizer.cli.benchmark import _classify_pipeline_suite

        result = _classify_pipeline_suite([], self._outcome())
        assert result.degraded is False

    def test_classify_e2e_suite_no_processed_degraded(self, tmp_path: Path) -> None:
        from file_organizer.cli.benchmark import _classify_e2e_suite

        f = tmp_path / "f.txt"
        f.write_text("x")
        result = _classify_e2e_suite([f], self._outcome(processed=0))
        assert result.degraded is True

    def test_classify_e2e_suite_processed_not_degraded(self, tmp_path: Path) -> None:
        from file_organizer.cli.benchmark import _classify_e2e_suite

        f = tmp_path / "f.txt"
        f.write_text("x")
        result = _classify_e2e_suite([f], self._outcome(processed=1))
        assert result.degraded is False

    def test_classify_e2e_suite_empty_files_not_degraded(self) -> None:
        from file_organizer.cli.benchmark import _classify_e2e_suite

        result = _classify_e2e_suite([], self._outcome(processed=0))
        assert result.degraded is False


# ---------------------------------------------------------------------------
# _resolve_processed_count
# ---------------------------------------------------------------------------


class TestResolveProcessedCount:
    def test_consistent_counts_returns_last(self) -> None:
        from file_organizer.cli.benchmark import _resolve_processed_count

        console = MagicMock()
        result = _resolve_processed_count([3, 3, 3], warmup=0, suite="io", console=console)
        assert result == 3

    def test_warmup_excluded(self) -> None:
        from file_organizer.cli.benchmark import _resolve_processed_count

        console = MagicMock()
        result = _resolve_processed_count([1, 3, 3, 3], warmup=1, suite="io", console=console)
        assert result == 3

    def test_empty_list_returns_zero(self) -> None:
        from file_organizer.cli.benchmark import _resolve_processed_count

        console = MagicMock()
        result = _resolve_processed_count([], warmup=0, suite="io", console=console)
        assert result == 0

    def test_only_warmup_returns_last_warmup(self) -> None:
        from file_organizer.cli.benchmark import _resolve_processed_count

        console = MagicMock()
        result = _resolve_processed_count([5], warmup=1, suite="io", console=console)
        assert result == 5


# ---------------------------------------------------------------------------
# _check_baseline_profile_compatibility
# ---------------------------------------------------------------------------


class TestCheckBaselineProfileCompatibility:
    def test_same_version_returns_none(self) -> None:
        from file_organizer.cli.benchmark import (
            _RUNNER_PROFILE_VERSION,
            _check_baseline_profile_compatibility,
        )

        console = MagicMock()
        baseline = {"runner_profile_version": _RUNNER_PROFILE_VERSION}
        result = _check_baseline_profile_compatibility(
            baseline, suite="io", console=console, json_output=False
        )
        assert result is None
        console.print.assert_not_called()

    def test_different_version_prints_warning(self) -> None:
        from file_organizer.cli.benchmark import _check_baseline_profile_compatibility

        console = MagicMock()
        baseline = {"runner_profile_version": "old-version-1"}
        result = _check_baseline_profile_compatibility(
            baseline, suite="io", console=console, json_output=False
        )
        assert result is not None
        console.print.assert_called_once()

    def test_different_version_json_output_no_print(self) -> None:
        from file_organizer.cli.benchmark import _check_baseline_profile_compatibility

        console = MagicMock()
        baseline = {"runner_profile_version": "old-version-1"}
        result = _check_baseline_profile_compatibility(
            baseline, suite="io", console=console, json_output=True
        )
        assert result is not None
        console.print.assert_not_called()

    def test_missing_version_key_returns_none(self) -> None:
        from file_organizer.cli.benchmark import _check_baseline_profile_compatibility

        console = MagicMock()
        result = _check_baseline_profile_compatibility(
            {}, suite="io", console=console, json_output=False
        )
        assert result is None


# ---------------------------------------------------------------------------
# _summarize_suite_classifications
# ---------------------------------------------------------------------------


class TestSummarizeSuiteClassifications:
    def test_all_non_degraded_returns_false(self) -> None:
        from file_organizer.cli.benchmark import (
            _SuiteExecutionClassification,
            _summarize_suite_classifications,
        )

        classifications = [
            _SuiteExecutionClassification(effective_suite="io", degraded=False),
            _SuiteExecutionClassification(effective_suite="io", degraded=False),
        ]
        _, degraded, reasons = _summarize_suite_classifications(
            classifications, warmup=0, requested_suite="io"
        )
        assert degraded is False
        assert reasons == []

    def test_any_degraded_returns_true(self) -> None:
        from file_organizer.cli.benchmark import (
            _SuiteExecutionClassification,
            _summarize_suite_classifications,
        )

        classifications = [
            _SuiteExecutionClassification(effective_suite="io", degraded=False),
            _SuiteExecutionClassification(
                effective_suite="text",
                degraded=True,
                degradation_reasons=("text-no-candidates-skip",),
            ),
        ]
        _, degraded, reasons = _summarize_suite_classifications(
            classifications, warmup=0, requested_suite="text"
        )
        assert degraded is True
        assert "text-no-candidates-skip" in reasons

    def test_empty_classifications_returns_requested_suite(self) -> None:
        from file_organizer.cli.benchmark import _summarize_suite_classifications

        effective, degraded, reasons = _summarize_suite_classifications(
            [], warmup=0, requested_suite="io"
        )
        assert effective == "io"
        assert degraded is False
        assert reasons == []

    def test_warmup_excluded_from_summary(self) -> None:
        from file_organizer.cli.benchmark import (
            _SuiteExecutionClassification,
            _summarize_suite_classifications,
        )

        classifications = [
            _SuiteExecutionClassification(
                effective_suite="io",
                degraded=True,
                degradation_reasons=("warmup-issue",),
            ),
            _SuiteExecutionClassification(effective_suite="io", degraded=False),
            _SuiteExecutionClassification(effective_suite="io", degraded=False),
        ]
        _, degraded, reasons = _summarize_suite_classifications(
            classifications, warmup=1, requested_suite="io"
        )
        assert degraded is False
        assert "warmup-issue" not in reasons

    def test_mixed_effective_suites_returns_mixed(self) -> None:
        from file_organizer.cli.benchmark import (
            _SuiteExecutionClassification,
            _summarize_suite_classifications,
        )

        classifications = [
            _SuiteExecutionClassification(effective_suite="io", degraded=False),
            _SuiteExecutionClassification(effective_suite="text", degraded=False),
        ]
        effective, _, _ = _summarize_suite_classifications(
            classifications, warmup=0, requested_suite="io"
        )
        assert effective == "mixed"
