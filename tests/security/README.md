# tests/security

Security hardening and regression tests for the fo-core pull-back
(`docs/internal/fo-core-pullback-implementation-plan.md`).

Tests landing here travel with the work package that hardens the code they
cover — for example the path-safety suite (WP-1.1) and the write/undo durability
suite (WP-2.2). The original's `review_regressions/` security tests are
**preserved** here while test trees are reconciled (never dropped).

## Convention

- Mark tests with `@pytest.mark.security`.
- Keep tests deterministic and offline (no network, no Ollama).

This directory is a WP-0.1 skeleton (#1222); it intentionally contains no tests
yet.
