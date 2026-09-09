# CI Check Matrix

> Issue #1786 — reduced PR fanout from ~70 to ≤35 non-skipped jobs.

## Pull request checks

| Job | Workflow | Condition |
|-----|----------|-----------|
| changes | ci.yml | always |
| lint | ci.yml | always |
| unused-deps | ci.yml | always |
| type-check | ci.yml | always |
| link-integrity | ci.yml | always |
| Test PR suite (py3.11) | ci.yml | always — records combined coverage context |
| Test PR suite (py3.14) | ci.yml | always — latest-version compatibility |
| Playwright E2E (chromium) | ci.yml | always |
| Playwright E2E (firefox, webkit) | ci.yml | only when web-facing files change¹ |
| Integration coverage gate | ci.yml | always |
| Benchmark suite | ci.yml | only when benchmark files change² |
| **PR required** | ci.yml | always — aggregation gate for branch protection |
| Extra … (py3.14) × 11 Linux | ci-extras.yml | path-filtered: pyproject.toml, src/, workflow, install script |
| Extra … macOS (py3.14) × 5 | ci-extras.yml | same path filter |
| **Extras required** | ci-extras.yml | always (when workflow triggers) |
| Conformance suite | conformance.yml | always |
| Check Markdown Links | docs-link-check.yml | always |
| Lint Markdown | docs-lint.yml | always |
| Pyre | pyre.yml | always |
| audit-dependencies | security.yml | always |
| bandit-scan | security.yml | always |
| codeql-analysis | security.yml | always |
| checkov-scan | security.yml | always |

**Typical source PR total: ≤35 non-skipped jobs.**

¹ Web paths: `src/file_organizer/{web,api,tui,desktop}/**`, `tests/playwright/**`
² Benchmark paths: `src/file_organizer/cli/benchmark.py`, `tests/ci/test_benchmark_contracts.py`, `tests/cli/test_benchmark*.py`, `tests/e2e/**`, `tests/fixtures/benchmark*/**`, `docs/admin/performance-tuning.md`, `docs/cli-reference.md`

## Push-to-main checks

All PR checks plus:

| Job | Workflow | Notes |
|-----|----------|-------|
| Test full (py3.11–3.14 × 6 shards) | ci.yml | replaces the 2-version PR matrix |
| Coverage gate (py3.11) | ci.yml | 93% floor, docstring coverage, Codecov upload |
| Unit coverage floor gate | ci.yml | dedicated unit-only `pytest -m unit` run |
| Benchmark suite | ci.yml | always — uploads baseline artifact |
| Playwright E2E (all 3 browsers) | ci.yml | always on push |

## Scheduled / full-matrix checks

| Job | Workflow | Schedule |
|-----|----------|----------|
| Extras Matrix (3.12–3.14 × all extras) | ci-extras.yml | Monday 07:00 UTC |
| Security scans | security.yml | Monday 06:00 UTC |
| CI Full Matrix (Linux shards + macOS + Windows) | ci-full.yml | daily 06:00 UTC |
| Deep Python Probe | python-probe.yml | weekly |
| Mutation Pilot | mutation.yml | daily 04:00 UTC |

## Branch protection

The `PR required` job in `ci.yml` depends on all required PR checks (lint,
unused-deps, type-check, link-integrity, test, playwright, test-integration).
Branch protection should require this single stable job name instead of
individual matrix-generated names. Adding or removing a Python version or
optional extra no longer requires a branch-protection settings update.

The `Extras required` job in `ci-extras.yml` serves the same role for the
extras workflow.

## How to add a Python version or extra

1. Add the version/extra to the matrix in the workflow file.
2. Update the guardrail tests in `tests/ci/test_workflows.py`.
3. No branch-protection update needed — the aggregation jobs absorb the change.

## How to trigger the full matrix manually

```bash
gh workflow run ci-full.yml
gh workflow run python-probe.yml
```
