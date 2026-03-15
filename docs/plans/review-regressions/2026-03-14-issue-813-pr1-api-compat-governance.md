# Issue #813 — PR-1 Scaffold (A + D)

This scaffold covers **Workstream A (Public API Compatibility Guards)** and
**Workstream D (Governance + Determinism)** from [#813](https://github.com/curdriceaurora/Local-File-Organizer/issues/813).

## Scope

- Add static/AST enforcement for allowlisted public API evolution rules.
- Add governance checks that enforce one canonical policy home per blocking rule.
- Do **not** implement runtime behavior contracts in this PR (those belong to PR-2).

## Implementation Checklist

- [x] Add a new review-regression detector module for public API compatibility.
- [x] Implement allowlist-driven detection for:
  - [x] insertion of new params before legacy params on public callables
  - [x] newly added optional params that are not keyword-only
- [x] Add detector fixtures (positive + safe) under `tests/fixtures/review_regressions/`.
- [x] Add detector unit tests under `tests/unit/review_regressions/`.
- [x] Add/extend CI semantic tests in `tests/ci/` to enforce deterministic policy mapping.
- [x] Update governance checks so each new blocking rule has one canonical layer.
- [x] Update developer guardrail docs with the canonical home for these rules.

## Acceptance Mapping (PR-1 subset)

- [x] Reintroducing constructor parameter insertion before legacy args fails CI.
- [x] Reintroducing non-keyword-only optional public constructor params on allowlist fails CI.
- [x] Canonical policy mapping is enforced (no duplicate stricter rule in shell wrapper).
- [x] `pytest tests/ci -q --no-cov --override-ini="addopts="` passes.
- [x] `bash .claude/scripts/pre-commit-validation.sh` passes.

## Guardrail Ownership

- `.pre-commit-config.yaml`: staged mechanical checks only (if any are added).
- `tests/ci` + `tests/unit/review_regressions`: semantic/API policy enforcement.
- `.claude/scripts/pre-commit-validation.sh`: orchestration only.

## Commands (must be run before PR open)

```bash
bash .claude/scripts/pre-commit-validation.sh
python3 -m pytest tests/unit/review_regressions -q --no-cov --override-ini="addopts="
python3 -m pytest tests/ci -q --no-cov --override-ini="addopts="
```
