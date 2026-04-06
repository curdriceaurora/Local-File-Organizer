# Integration Coverage Ratchet — Design Spec

**Date**: 2026-04-06
**Issue**: curdriceaurora/Local-File-Organizer#856
**Status**: Approved

---

## Goal

Raise the integration test coverage gate from 71.9% to 90% combined line+branch, using a
ratchet-based approach across multiple focused PRs ordered by coverage yield.

---

## Current State

| Metric | Value |
|--------|-------|
| Integration test count | 86 tests across 15 files |
| Current CI gate | 71.9% combined line+branch |
| Target | 90% combined line+branch |
| Gap | ~18 percentage points |
| CI job | `test-integration` in `.github/workflows/ci.yml` (main push only) |
| Measurement script | `.claude/scripts/measure-integration-coverage.sh` |

---

## Approach: Measure → Coherent-domain PRs

PRs are grouped by related domain (not fixed % increments) and ordered by coverage yield
(modules with the most uncovered lines go first). The actual order is determined by the
measurement snapshot — the table below is the expected ordering based on the issue's known
gap areas.

---

## Phase 1: Measurement Snapshot

Before any test writing, run a clean local measurement:

```bash
bash .claude/scripts/measure-integration-coverage.sh --cov-report=term-missing
```

Collect every module, its current combined %, and its uncovered line count. Rank by
**uncovered lines** (not %) to identify highest absolute yield. Document the result in
issue #856 as the "measurement snapshot" — this drives PR ordering.

---

## Phase 2: Domain PRs (ordered by yield)

| PR | Domain | Expected modules | Ratchet target |
|----|--------|-----------------|----------------|
| PR1 | Auth & rate-limiting | `api/auth.py`, `api/auth_rate_limit.py` | measured after merge |
| PR2 | Service facade & file ops | `api/service_facade.py`, file op rollback paths | measured after merge |
| PR3 | WebSocket & event streams | WebSocket session lifecycle, event replay | measured after merge |
| PR4 | Remaining gaps | Any modules still below threshold | 90% |

If measurement results show a different yield ordering (e.g., `service_facade.py` has more
uncovered lines than `auth.py`), swap PR1 and PR2 accordingly. The table above is a likely
ordering, not a fixed one.

---

## Per-PR Workflow

Each PR follows this repeatable pattern:

### 1. Branch
```bash
git checkout -b feat/integration-cov-<domain>
```

### 2. Write tests
- Location: appropriate `tests/` subdirectory, consistent with existing structure
- Marker: `@pytest.mark.integration`
- Constraint: real DB/filesystem — no mocks at the integration layer
- Priority: happy path gaps first (biggest line yield), then error paths and edge cases

### 3. Measure locally
```bash
bash .claude/scripts/measure-integration-coverage.sh
```
Note the new `TOTAL` combined %. This becomes the new ratchet floor.

### 4. Bump the gate
In `.github/workflows/ci.yml`, `test-integration` job:
```yaml
--cov-fail-under=<new_floor>
```
Add ratchet comment:
```yaml
# YYYY-MM-DD: <new>% combined (ratchet after <domain> tests; actual <measured>%)
```

### 5. Quality gates
Run pre-commit validation and code reviewer before pushing.

### 6. PR title convention
```
test(integration): <domain> coverage expansion (ratchet → <new>%)
```

---

## Completion Criteria

- [ ] Measurement snapshot documented in issue #856
- [ ] Each domain PR merges cleanly with CI gate bumped
- [ ] `pytest -m "integration" --cov-fail-under=90` passes on main
- [ ] `CLAUDE.md` updated with 90% integration gate alongside existing 95% unit gate
- [ ] All acceptance criteria in issue #856 checked off

---

## Constraints

- Integration tests must use real DB/filesystem — no mocks at the integration layer
- Each new API endpoint must ship with at least one integration test in its introducing PR
  (ongoing requirement, not specific to this ratchet)
- CI gate (`test-integration` job) runs on `push` to `main` only — not on PRs
- Error-path guidance: see `.claude/rules/feature-generation-patterns.md` F1

---

## References

- Issue: curdriceaurora/Local-File-Organizer#856
- CI job: `.github/workflows/ci.yml` → `test-integration`
- Measurement script: `.claude/scripts/measure-integration-coverage.sh`
- Anti-pattern rules: `.claude/rules/feature-generation-patterns.md`
- Test generation patterns: `.claude/rules/test-generation-patterns.md`
