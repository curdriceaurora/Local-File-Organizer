# TDD Workflow Rule

**Purpose**: Move anti-pattern prevention upstream of code generation. Enforce test-first for new `src/` modules so that error handling (F1), types (F2), security boundaries (F4), and assertion quality are designed before implementation — not patched after review.

**Background**: Issue #850 — PR #846 generated 19 review findings across 3 rounds despite anti-pattern rules being in context. Root cause: reasoning about error paths and types happens during review, not design. Test-first forces that reasoning upstream.

---

## The Rule

**Write the test file before the implementation file.**

```
tests/subdir/test_<module>.py   ← write this first
src/file_organizer/subdir/<module>.py  ← then this
```

---

## Hook Enforcement

Implemented in `.claude/hooks/tdd-gate.sh`, registered in `.claude/settings.json`:

| Scenario | Hook Behaviour |
|----------|----------------|
| `Write` to new `src/file_organizer/**/*.py` with no test file | **DENY** — must write test first |
| `Edit` to existing `src/file_organizer/**/*.py` with no test file | **ADVISORY** — warning on stderr, not blocked |
| `__init__.py` | Exempt |
| Docs, config, CI, tests themselves | Exempt |

---

## Why Tests Are the Right Upstream Contract

Alternative from issue #850 Option A (JSON contract) duplicates information already in rule files. Tests are:

1. **Already required** — no extra artifact overhead
2. **Inspectable** — user reviews assertions before implementation begins
3. **Stateless to check** — hook just checks if `test_<stem>.py` exists anywhere under `tests/`
4. **Naturally force the right reasoning**:
   - F1 (error handling): test must declare what exceptions to expect → `pytest.raises`
   - F2 (types): test assertions reveal expected return shapes
   - F4 (security): test for boundary inputs before writing the path handler
   - Test quality (assertion churn): bad assertions are visible before any implementation exists

---

## Test-First Workflow

```
1. Read base class / interface BEFORE writing anything (F6 prevention)
2. Write test file: tests/<subdir>/test_<module>.py
   - List all public methods
   - Add assertions for error paths (F1)
   - Add type assertions where relevant (F2)
   - Add security boundary tests if touching paths/auth (F4)
3. Verify hook passes: attempt Write to src/ — gate should allow through
4. Write implementation
5. Run: pytest tests/<subdir>/test_<module>.py -v
6. Run quality gates: pre-commit validation → /code-reviewer
```

---

## What This Doesn't Cover

- **Refactors of existing modules**: `Edit` on an existing file is advisory only (hook doesn't block). Responsibility is on the author to check test coverage.
- **Option B (adversarial pipeline)**: Already exists as `/audit` + `/code-reviewer`. Execution discipline — not a missing tool — is the gap.
- **Option D (structured output schema)**: Not feasible within Claude Code — `response_format` applies to direct API calls, not internal tool dispatch.

---

## References

- `.claude/hooks/tdd-gate.sh` — hook implementation
- `.claude/settings.json` — hook registration
- `docs/internal/CLAUDE.md` — TDD Workflow Rule section
- Issue #850 — upstream generation constraints
- `.claude/rules/feature-generation-patterns.md` — F1–F10 anti-patterns

---

**Last Updated**: 2026-03-18
**Status**: Active enforcement via PreToolUse hook
**Scope**: New `src/file_organizer/**/*.py` files only
