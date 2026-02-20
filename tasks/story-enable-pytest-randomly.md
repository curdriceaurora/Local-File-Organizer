# [Testing] Enable pytest-randomly for Test Order Independence

## Goal

Re-enable `pytest-randomly` to detect hidden test ordering dependencies across the 3934-test suite.

## Background

`pytest-randomly` was added in PR #396 but removed in a follow-up commit because it exposed 3 pre-existing test failures in CI run #268 (seed: 1648692849). The plugin auto-enables on install (no opt-in flag), which randomized the entire test suite and revealed ordering dependencies.

## Pros

- **Detects hidden ordering dependencies** — tests that only pass in a specific sequence
- **Catches shared state leaks** — singletons, module-level variables, and class-level caches that persist between tests
- **Improves CI reliability** — randomized tests are more robust and less likely to have false passes
- **Seed-based reproducibility** — failures are easy to replay with `--randomly-seed=N`
- **Zero config** — auto-enables on install, no extra CLI flags needed

## Cons / Lessons Learned from PR #396

- **Auto-enables on install** — simply adding to `[dev]` deps changes all test execution behavior. No opt-in flag.
- **Exposed 3 pre-existing failures** — tests like `TestAnalyzeEndpoint.test_analyze_handles_images` failed under randomized order
- **Compounds with xdist** — randomization + parallelization together creates harder-to-debug failure modes
- **3934 tests need audit** — the existing test suite has ordering dependencies that must be fixed first
- **CI seed varies per run** — failures may be non-deterministic and hard to reproduce without the specific seed

## Prerequisites

1. Audit all test modules for shared state (module-level variables, singletons, class-level caches)
2. Ensure all tests use proper `setup`/`teardown` or `autouse` fixtures for state reset
3. Fix all ordering dependencies identified by running with multiple random seeds locally
4. Verify `conftest.py` autouse fixtures (`ensure_default_event_loop`, `reset_realtime_state`) properly isolate state

## Acceptance Criteria

- [ ] `pytest-randomly` added back to `[dev]` dependencies
- [ ] Full test suite passes with 10+ different random seeds
- [ ] No flaky tests in 5 consecutive CI runs
- [ ] Document any tests that require specific ordering (mark with `@pytest.mark.order`)

## Effort Estimate

4-6 hours (audit + fix ordering dependencies across ~3934 tests)

## Labels

`testing`, `enhancement`, `tech-debt`
