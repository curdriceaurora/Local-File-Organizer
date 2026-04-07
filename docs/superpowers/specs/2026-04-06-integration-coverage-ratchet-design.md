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
| Integration test files | 142 (verify at measurement time — count grows each PR) |
| `@pytest.mark.integration` occurrences | 86 (verify at measurement time) |
| Current CI gate | 71.9% combined line+branch (`--cov-fail-under=71.9 --cov-branch`) |
| Target | 90% combined line+branch |
| Gap | ~18 percentage points |
| CI job | `test-integration` in `.github/workflows/ci.yml` (main push only) |
| Measurement script | `.claude/scripts/measure-integration-coverage.sh` |
| CLAUDE.md gate reference | `docs/internal/CLAUDE.md` → "Integration Coverage Gate" section |

---

## Approach: Measure → Coherent-domain PRs

PRs are grouped by related domain (not fixed % increments) and ordered by coverage yield
(modules with the most uncovered lines go first). The actual order is determined by the
measurement snapshot — the domain table below is a likely ordering based on the issue's
known gap areas, not a fixed sequence.

---

## Phase 1: Measurement Snapshot

Before any test writing, produce a clean per-module coverage breakdown:

```bash
# Step 1: erase stale data and run integration suite with branch + JSON coverage
coverage erase
pytest tests/ -m "integration" \
    --strict-markers \
    --cov=file_organizer \
    --cov-branch \
    --cov-report=term-missing \
    --cov-report=json:coverage-integration.json \
    --override-ini="addopts="

# Step 2: extract per-module combined (line+branch) % and uncovered line count
python3 - << 'EOF'
import json

with open("coverage-integration.json") as f:
    data = json.load(f)

rows = []
for filename, info in data["files"].items():
    s = info["summary"]
    covered_lines = s["covered_lines"]
    missing_lines = s["missing_lines"]
    total_lines = s["num_statements"]
    covered_branches = s.get("covered_branches", 0)
    missing_branches = s.get("missing_branches", 0)
    total_branches = s.get("num_branches", 0)

    total = total_lines + total_branches
    covered = covered_lines + covered_branches
    pct = round(covered / total * 100, 1) if total > 0 else 100.0
    uncovered = missing_lines + missing_branches

    rows.append((uncovered, pct, filename))

rows.sort(reverse=True)  # highest uncovered first
print(f"{'Uncovered':>10}  {'%':>6}  Module")
print("-" * 60)
for uncovered, pct, filename in rows:
    print(f"{uncovered:>10}  {pct:>6.1f}  {filename}")
EOF
```

The script above produces a ranked table of modules by uncovered lines (line + branch
combined). This table drives PR ordering and is documented in issue #856 as the
"measurement snapshot."

> The existing `measure-integration-coverage.sh` helper does the `coverage erase` + `pytest`
> run for you; add `--cov-report=json:coverage-integration.json` as an extra arg and run
> the Python snippet above on the resulting file.

---

## Phase 2: Domain PRs (ordered by yield)

Assign domain labels to the highest-yield modules from the snapshot, then group into PRs:

| PR | Domain | Expected modules | Ratchet target |
|----|--------|-----------------|----------------|
| PR1 | Auth & rate-limiting | `api/auth.py`, `api/auth_rate_limit.py` | measured after merge |
| PR2 | Service facade & file ops | `api/service_facade.py`, file op rollback paths | measured after merge |
| PR3 | WebSocket & event streams | WebSocket session lifecycle, event replay | measured after merge |
| PR4 | Remaining gaps | Any modules still below threshold | 90% |

If the snapshot shows a different yield ordering, reorder PRs accordingly.

---

## Per-PR Workflow

Each PR follows this repeatable pattern:

### 1. Branch

```bash
git checkout -b feat/integration-cov-<domain>
```

### 2. Write tests

- **Location**: appropriate `tests/` subdirectory, consistent with existing structure
- **Markers**: both `@pytest.mark.integration` **and** `@pytest.mark.ci`
  - `integration` → picked up by the `test-integration` CI gate on main push
  - `ci` → picked up by the standard PR job (`-m "ci and not benchmark"`), so the
    tests also provide changed-line diff-cover signal on PRs
- **Mocking boundary**: use real app wiring, real DB, real filesystem, and real
  router/service integration. External HTTP calls and AI/model inference boundaries
  may be mocked — the invariant is cross-layer integration, not zero-mock.
- **Priority**: happy-path gaps first (biggest line yield), then error paths and edge cases

### 3. Measure locally

```bash
bash .claude/scripts/measure-integration-coverage.sh \
    --cov-report=json:coverage-integration.json
# Then run the Python snippet from Phase 1 to get the new TOTAL combined %
```

Read the `TOTAL` combined line+branch % from the output. Round **down** to one decimal
place — this is the new ratchet floor. Example: if coverage is 74.87%, the floor is 74.8%.

**Safeguard**: never set `--cov-fail-under` above the value measured in a clean local run
(`coverage erase` first). If the measurement was not clean, re-run before bumping.

### 4. Bump the gate — four locations

All four must be updated in the same commit:

**a) CI job step name** in `.github/workflows/ci.yml`:

```yaml
- name: "Integration coverage gate (floor: <new>% combined line+branch)"
```

**b) CI `--cov-fail-under` value** in the same step's `run:` command:

```bash
pytest tests/ -m "integration" ... --cov-fail-under=<new_floor> ...
```

**c) Ratchet comment** directly above the `run:` line:

```yaml
# YYYY-MM-DD: <new_floor>% combined (ratchet after <domain> tests; actual <measured>%)
```

**d) CLAUDE.md** — `docs/internal/CLAUDE.md`, "Integration Coverage Gate" section:

```markdown
- **Current floor**: <new_floor>% (ratchet — bumped with each coverage PR, target 90% per issue #856)
```

### 5. Quality gates

Run pre-commit validation and `/code-reviewer` before pushing.

### 6. PR title convention

```
test(integration): <domain> coverage expansion (ratchet → <new_floor>%)
```

---

## Completion Criteria

- [ ] Measurement snapshot documented in issue #856
- [ ] Each domain PR merges cleanly with CI gate bumped in all four locations
- [ ] `pytest -m "integration" --cov-branch --cov-fail-under=90` passes on main
- [ ] `docs/internal/CLAUDE.md` "Integration Coverage Gate" section updated to 90%
- [ ] All acceptance criteria in issue #856 checked off

---

## Constraints

- **Mocking boundary**: real app wiring, DB, filesystem, router/service integration required.
  External HTTP and AI/model inference boundaries may be mocked. No mocking of internal
  service, repository, or router layers.
- **Both markers required**: every new integration test carries `@pytest.mark.integration`
  AND `@pytest.mark.ci` so it participates in both the main-push gate and PR diff-cover.
- **Ratchet floor is rounded down** to one decimal place and must not exceed the clean
  local measurement.
- **CI gate runs on main push only** (`test-integration` job condition:
  `github.event_name == 'push' && github.ref == 'refs/heads/main'`).
- Each new API endpoint must ship with at least one integration test in its introducing PR
  (ongoing requirement, not specific to this ratchet).
- Error-path guidance: see `.claude/patterns/feature-generation-patterns.md` F1.

---

## References

- Issue: curdriceaurora/Local-File-Organizer#856
- CI job: `.github/workflows/ci.yml` → `test-integration`
- Measurement script: `.claude/scripts/measure-integration-coverage.sh`
- CLAUDE.md gate docs: `docs/internal/CLAUDE.md` → "Integration Coverage Gate"
- Anti-pattern rules: `.claude/patterns/feature-generation-patterns.md`
- Test generation patterns: `.claude/patterns/test-generation-patterns.md`
