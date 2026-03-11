# /pr-prep - PR Hardening & Preparation Skill

Verifies a branch is complete as a deliverable before creating a PR. Goes beyond "tests pass" to ensure docs, cross-references, and integration are all coherent.

## Usage

```
/pr-prep
```

Run after all implementation work is done, before `/pr` or `gh pr create`.

## Workflow (All Steps Mandatory)

### Phase 1: Scope Discovery

1. **Identify all changes on this branch**
   - Run `git diff main --stat` to get the full change set
   - Run `git log --oneline main..HEAD` to understand commit history
   - Categorize changes: code, tests, docs, config

2. **Build a claims list**
   - What does this branch claim to deliver? (from commit messages, epic docs, issue descriptions)
   - List every testable claim (e.g., "39 integration tests", "7 gap patterns covered", "shared fixtures")

### Phase 2: Cross-Stream Integration

3. **Verify all tests pass together**
   - Run the full relevant test suite (not just individual files)
   - Confirm no cross-stream conflicts or import errors
   - If tests were written in streams/phases, verify they compose correctly

4. **Run `/simplify` on all changed code**
   - Launch code reuse, quality, and efficiency review agents
   - Apply valid findings, skip false positives
   - Re-run tests after fixes

### Phase 3: Documentation Completeness

5. **Check user-facing docs for gaps**
   - Search `docs/`, `CONTRIBUTING.md`, `README.md` for references to the area you changed
   - Are new features/patterns documented for contributors?
   - Are existing docs stale? (old counts, removed features, renamed classes)
   - Use the Agent tool to search broadly — don't guess

6. **Check internal docs for staleness**
   - Epic planning docs: do estimates match actuals? (test counts, file counts, exit gates)
   - `.claude/rules/` files: any references to old patterns?
   - `memory/MEMORY.md`: any stale entries?

7. **Verify cross-references**
   - Do docs reference files that exist?
   - Do test counts in docs match actual `pytest --collect-only` counts?
   - Do feature claims in docs match actual implementation?

### Phase 4: Final Verification

8. **Run pre-commit validation**
   ```bash
   bash .claude/scripts/pre-commit-validation.sh
   ```
   - Must pass before proceeding

9. **Produce readiness summary**
   - List what was verified and what was fixed
   - Confirm branch is ready for PR creation

## What This Catches (That Tests Alone Miss)

| Gap | Example |
|-----|---------|
| Stale doc counts | Epic says "~28 tests" but actual is 39 |
| Missing contributor guidance | New test harness exists but CONTRIBUTING.md doesn't explain how to use it |
| Orphaned cross-references | Docs reference a class that was renamed |
| Incomplete exit gates | Planning doc checkboxes still unchecked after work is done |
| Undocumented fixtures/helpers | Shared test fixtures exist but no reference table for contributors |
| Test isolation failures | Tests pass individually but fail when run together |

## Critical Rules

- ❌ NEVER skip the documentation completeness check (Phase 3)
- ❌ NEVER assume docs are fine because tests pass
- ❌ NEVER skip `/simplify` — it catches real issues every time
- ❌ NEVER create a PR with stale counts or claims in docs
- ✅ DO search broadly for doc references (use Agent tool, not just grep)
- ✅ DO update epic/planning docs with actual outcomes
- ✅ DO add contributor guidance for any new patterns or fixtures
- ✅ DO fix stale docs in the same PR, not as follow-up

## Example Output

```
/pr-prep

Phase 1: Scope Discovery
  Branch: feat/integration-test-harness (2 commits ahead of main)
  Changes: 7 new test files, 1 epic doc, 1600 lines added
  Claims: "39 integration tests across 7 gaps"

Phase 2: Cross-Stream Integration
  ✅ All 132 integration tests pass together (23s)
  ✅ /simplify applied — 5 fixes (removed duplicate test, unused imports, resource leaks)

Phase 3: Documentation Completeness
  ⚠️  epic.md says "~28 tests" — actual is 39 → FIXED
  ⚠️  epic.md exit gates still unchecked → FIXED (marked [x] with actual counts)
  ⚠️  docs/developer/testing.md has no integration test section → ADDED
  ⚠️  CONTRIBUTING.md missing integration test guidance → ADDED
  ✅ README.md — no stale references
  ✅ .claude/rules/ — no stale references

Phase 4: Final Verification
  ✅ pre-commit-validation.sh passed
  ✅ All fixes committed and pushed

Ready for /pr
```
