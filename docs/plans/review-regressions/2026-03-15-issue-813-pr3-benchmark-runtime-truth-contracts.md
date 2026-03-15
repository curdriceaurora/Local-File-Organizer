# Issue #813 PR-3: Benchmark Runtime Truth Contracts

## Why This PR Exists

Workstream **F** in #813 owns runtime benchmark truth semantics.  
PR-2 established degraded/fallback metadata, but this PR tightens runtime invariants so benchmark output cannot silently drift from what was actually processed.

## Runtime Invariants Enforced

1. Processed-count truth:
- Measured iterations must agree on processed cardinality.
- If measured processed counts drift, benchmark run fails fast with a clear error.

2. Scoped suite filtering truth:
- `text` and `vision` suites must use scoped extension filtering.
- They must not silently fall back to processing all discovered files.

3. Throughput/files_count truth:
- `files_count` remains tied to actual processed cardinality, not discovered input count.
- Skip paths report `files_count == 0`.

4. User-visible degraded behavior:
- Degraded suite mode and reason stay visible in non-JSON output.

## Contract Evidence (Tests)

- `tests/cli/test_benchmark_suite_runners.py`
  - `test_resolve_processed_count_uses_measured_window`
  - `test_resolve_processed_count_fails_when_measured_counts_drift`
- `tests/ci/test_benchmark_contracts.py`
  - `test_cli_fails_when_processed_counts_drift_across_measured_iterations`
  - `test_text_suite_skip_is_explicit_in_json_output`
  - `test_vision_suite_skip_is_explicit_in_json_output`
  - `test_scoped_suite_files_count_uses_filtered_candidates`
  - `test_degraded_plain_output_surfaces_reason_to_user`

## Local Verification

```bash
pytest tests/cli/test_benchmark_suite_runners.py tests/ci/test_benchmark_contracts.py tests/cli/test_benchmark.py tests/cli/test_cli_benchmark_coverage.py -q --no-cov --override-ini="addopts="
bash .claude/scripts/pre-commit-validation.sh
```
