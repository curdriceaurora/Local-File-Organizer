# [Testing] Enable pytest-xdist for Parallel CI Test Execution

## Goal

Re-enable `pytest-xdist` with `-n auto` for faster CI runs (currently ~5 min, potential ~2 min with parallelization).

## Background

`pytest-xdist` was added in PR #396 but removed in a follow-up commit because it ran with 4 workers in CI (auto-detected from runner CPU cores) and exposed shared state issues in pre-existing API tests. The plugin was activated even without an explicit `-n auto` flag.

## Pros

- **~2-3x faster CI runs** — parallelizes across CPU cores (4 workers on GitHub Actions runners)
- **Forces proper test isolation** — no shared filesystem state, database connections, or singletons
- **Catches thread-safety issues** — reveals race conditions and shared resource contention
- **Scales with CI resources** — auto-detects available cores
- **Industry standard** — widely used in large Python test suites

## Cons / Lessons Learned from PR #396

- **Ran with 4 workers without explicit `-n auto`** — auto-detection behavior triggered even though we didn't configure it in pyproject.toml `addopts`
- **Exposed shared state in API tests** — `TestAnalyzeEndpoint.test_analyze_handles_images` and 2 other tests failed under parallel execution
- **Debugging is harder** — parallel failures are non-deterministic, depend on worker scheduling
- **Some tests may need sequential execution** — database operations, file system state, port bindings
- **Autouse fixtures need verification** — `ensure_default_event_loop` and `reset_realtime_state` from conftest.py need to be confirmed xdist-safe (each worker runs in its own process, so they should be fine, but needs verification)
- **Compounds with pytest-randomly** — parallel + randomized creates a matrix of possible failure modes

## Prerequisites

1. Fix all shared state issues identified in CI run #268
2. Ensure each test is fully independent — no reliance on test ordering or shared resources
3. Verify `conftest.py` autouse fixtures work correctly with xdist worker processes
4. Identify tests that require sequential execution and mark with `@pytest.mark.no_xdist` or similar
5. Add explicit `-n auto` to CI command (don't rely on auto-detection)

## Acceptance Criteria

- [ ] `pytest-xdist` added back to `[dev]` dependencies
- [ ] `-n auto` added to CI pytest command explicitly
- [ ] Full test suite passes with 4 workers consistently
- [ ] No flaky tests in 5 consecutive parallel CI runs
- [ ] CI run time reduced to ~2-3 minutes (from ~5 minutes)
- [ ] Tests requiring sequential execution properly marked and excluded from parallel runs

## Effort Estimate

6-8 hours (audit shared state + fix isolation issues + verify fixtures + CI testing)

## Labels

`testing`, `enhancement`, `performance`, `tech-debt`

## Dependencies

Should be done AFTER the pytest-randomly story — fix ordering deps first, then parallelize.
