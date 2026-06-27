# tests/smoke

Fast, broad smoke tests for pre-commit validation (target: <30s total).

Smoke tests assert that core entry points import and run — not deep behavior —
so a regression is caught at commit time before the full suite runs.

## Convention

- Mark tests with `@pytest.mark.smoke` (already registered in `pyproject.toml`).
- Keep each test fast and dependency-light (no network, no Ollama, no heavy
  optional extras).

This directory is a WP-0.1 skeleton (#1222); it intentionally contains no tests
yet.
