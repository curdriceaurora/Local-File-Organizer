# Issue #813 — PR-2 Scaffold (B + C)

This PR covers **Workstream B (backend fatal/degraded runtime contracts)** and
**Workstream C (fallback label integrity)** from
[#813](https://github.com/curdriceaurora/Local-File-Organizer/issues/813).

## Scope

- Add explicit runtime degradation metadata to benchmark JSON output.
- Preserve fail-fast behavior for fatal suite errors.
- Ensure fallback and skip paths do not silently present misleading suite labels.
- Add CI and CLI tests that fail on regression of these contracts.

## Implementation Checklist

- [x] Add suite-iteration classification primitives (`effective_suite`, degraded state, reason codes).
- [x] Attach explicit degraded metadata to benchmark JSON output:
  - [x] `effective_suite`
  - [x] `degraded`
  - [x] `degradation_reasons`
- [x] Keep fatal iteration failures non-silent (`typer.Exit(code=1)` path unchanged).
- [x] Add CI tests for fallback/skip label integrity in JSON mode.
- [x] Update benchmark schema checks and fixture baseline to include new fields.
- [x] Update benchmark CLI docs for the new JSON contract fields.

## Acceptance Mapping (PR-2 subset)

- [x] Audio fallback (`audio` → `io`) is explicit in JSON output.
- [x] Text/vision skip paths are explicit degraded runs with stable reason codes.
- [x] Non-degraded suite runs keep `degraded=false` and empty reason list.
- [x] `files_count` remains actual processed cardinality (existing contract preserved).
- [x] `pytest tests/ci/test_benchmark_contracts.py -q --no-cov --override-ini="addopts="` passes.
- [x] `pytest tests/cli/test_benchmark_suite_runners.py tests/cli/test_benchmark.py tests/cli/test_cli_benchmark_coverage.py -q --no-cov --override-ini="addopts="` passes.

## Notes

- This PR intentionally does not implement #822 cross-cutting silent-swallow/import-time ratchets.
- This PR intentionally does not add workflow-security policy checks (tracked outside #813).
