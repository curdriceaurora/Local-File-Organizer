# Issue #813 PR-5 + #822 Closeout Reconciliation

Date: `2026-03-15`  
Issues: `#813`, `#822`

## Purpose

This closeout records the final coverage mapping for the post-`#814` review-finding baseline and
binds each covered pattern to an enforced CI test.

## Catch-Rate Result

- Baseline findings: **19**
- Covered by current guardrails: **13**
- Uncovered: **6**
- Catch rate: **68.4%** (`13 / 19`)
- #813 target: **>= 12 / 19 (>= 63%)**
- Result: **target met**

## Discovery Artifact

- `#822` discovery artifact: `docs/plans/review-regressions/2026-03-15-issue-822-discovery-artifact.json`

## Closeout Metadata

<!-- REVIEW_REGRESSION_813_822_CLOSEOUT_METADATA_START -->
```json
{
  "baseline_source": "docs/plans/review-regressions/2026-03-15-post-814-review-comment-analysis.md",
  "baseline_total_findings": 19,
  "coverage_target_minimum": 12,
  "covered_finding_ids": [1, 2, 3, 4, 5, 6, 7, 8, 10, 11, 13, 15, 16],
  "uncovered_finding_ids": [9, 12, 14, 17, 18, 19],
  "coverage_recomputed": {
    "covered": 13,
    "uncovered": 6,
    "coverage_percent": 68.4
  },
  "finding_map": [
    {
      "id": 1,
      "covered": true,
      "pattern": "Audio suite fallback must be explicit and user-visible",
      "enforcing_tests": [
        "tests/ci/test_benchmark_contracts.py::test_audio_suite_fallback_is_explicit_in_json_output",
        "tests/cli/test_benchmark_suite_runners.py::test_audio_suite_warns_when_falling_back_to_io"
      ]
    },
    {
      "id": 2,
      "covered": true,
      "pattern": "Suite runner aliases must remain pairwise distinct",
      "enforcing_tests": [
        "tests/ci/test_benchmark_contracts.py::test_benchmark_suite_runners_are_distinct"
      ]
    },
    {
      "id": 3,
      "covered": true,
      "pattern": "Benchmark model stub must expose cleanup interface parity",
      "enforcing_tests": [
        "tests/cli/test_benchmark_suite_runners.py::test_benchmark_model_stub_exposes_safe_cleanup",
        "tests/ci/test_benchmark_testproof_guardrails.py::test_benchmark_stub_cleanup_parity_test_enforces_pre_and_post_state"
      ]
    },
    {
      "id": 4,
      "covered": true,
      "pattern": "Text/vision no-candidate paths must skip explicitly, not fallback silently",
      "enforcing_tests": [
        "tests/ci/test_benchmark_contracts.py::test_text_suite_skip_is_explicit_in_json_output",
        "tests/ci/test_benchmark_contracts.py::test_vision_suite_skip_is_explicit_in_json_output"
      ]
    },
    {
      "id": 5,
      "covered": true,
      "pattern": "Benchmark non-fatal file-stat failures must keep traceback diagnostics",
      "enforcing_tests": [
        "tests/cli/test_benchmark_suite_runners.py::test_io_suite_logs_oserror_traceback_for_failed_stat"
      ]
    },
    {
      "id": 6,
      "covered": true,
      "pattern": "Broad fallback catches must not be silent",
      "enforcing_tests": [
        "tests/ci/test_silent_broad_except_guard.py::test_guard_detects_silent_broad_exception_handlers"
      ]
    },
    {
      "id": 7,
      "covered": true,
      "pattern": "Vision benchmark tests must prove backend model pull is not used",
      "enforcing_tests": [
        "tests/cli/test_benchmark_suite_runners.py::test_vision_suite_does_not_require_backend_model_pull"
      ]
    },
    {
      "id": 8,
      "covered": true,
      "pattern": "Benchmark schema contract requires runtime payload fields",
      "enforcing_tests": [
        "tests/ci/test_benchmark_contracts.py::test_live_benchmark_payload_contains_required_runtime_fields"
      ]
    },
    {
      "id": 9,
      "covered": false,
      "pattern": "Docstring freshness and wording quality",
      "enforcing_tests": []
    },
    {
      "id": 10,
      "covered": true,
      "pattern": "files_count and throughput must follow processed-cardinality truth",
      "enforcing_tests": [
        "tests/ci/test_benchmark_contracts.py::test_scoped_suite_files_count_uses_filtered_candidates",
        "tests/ci/test_benchmark_contracts.py::test_cli_fails_when_processed_counts_drift_across_measured_iterations"
      ]
    },
    {
      "id": 11,
      "covered": true,
      "pattern": "Deterministic benchmark smoke test marker hygiene",
      "enforcing_tests": [
        "tests/ci/test_benchmark_testproof_guardrails.py::test_smoke_schema_test_has_required_pytest_markers"
      ]
    },
    {
      "id": 12,
      "covered": false,
      "pattern": "Overly broad typing (Any) hygiene",
      "enforcing_tests": []
    },
    {
      "id": 13,
      "covered": true,
      "pattern": "Audio fallback tests must prove delegated call path and result contract",
      "enforcing_tests": [
        "tests/ci/test_benchmark_testproof_guardrails.py::test_audio_fallback_test_proves_delegation_call_and_result_contract"
      ]
    },
    {
      "id": 14,
      "covered": false,
      "pattern": "Redundant import/style cleanups",
      "enforcing_tests": []
    },
    {
      "id": 15,
      "covered": true,
      "pattern": "UI status-path broad catches must remain observable",
      "enforcing_tests": [
        "tests/ci/test_silent_broad_except_guard.py::test_repository_has_no_silent_broad_exception_handlers"
      ]
    },
    {
      "id": 16,
      "covered": true,
      "pattern": "Import-time cpu_count fallback semantics must remain deterministic",
      "enforcing_tests": [
        "tests/tui/test_settings_view.py::test_load_parallel_runtime_settings_uses_cpu_count_fallback_when_unavailable",
        "tests/ci/test_import_time_fallback_contracts.py::test_import_time_probe_has_runtime_and_test_contract"
      ]
    },
    {
      "id": 17,
      "covered": false,
      "pattern": "Workflow least-privilege token permissions",
      "enforcing_tests": []
    },
    {
      "id": 18,
      "covered": false,
      "pattern": "Third-party GitHub Action immutable SHA pinning",
      "enforcing_tests": []
    },
    {
      "id": 19,
      "covered": false,
      "pattern": "Workflow mention guard / CI efficiency policy",
      "enforcing_tests": []
    }
  ]
}
```
<!-- REVIEW_REGRESSION_813_822_CLOSEOUT_METADATA_END -->

## Notes

- Findings `17-19` remain intentionally out of scope for `#813/#822` and belong to CI workflow policy stream.
- Findings `9/12/14` are documentation/style/type hygiene classes not currently in this guardrail family.
