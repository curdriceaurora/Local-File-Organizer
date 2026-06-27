# tests/extras

Optional-dependency matrix tests — behavior across the extras declared in
`pyproject.toml` (`audio`, `video`, `dedup`, `archive`, `scientific`, `cad`, …).

These tests cover both paths of an optional dependency: the feature working when
the extra is installed, and the graceful-degradation / clear-error path when it
is not. They pair with the reader-cap and optional-dep-UX work packages
(WP-3.1, WP-5.3).

## Convention

- Mark tests with `@pytest.mark.extras`.
- Guard imports of optional packages and `pytest.skip(...)` (or
  `importorskip`) when the extra under test is absent, so the suite stays green
  in minimal environments.

This directory is a WP-0.1 skeleton (#1222); it intentionally contains no tests
yet.
