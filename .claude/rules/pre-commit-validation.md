# Pre-Commit Validation Rule

**MANDATORY**: Before EVERY commit, complete these validation steps in order.

## Why This Rule Exists

Previous sessions showed self-introduced errors that required iterative cleanup:
- Duplicate imports (`import os` appearing twice)
- Misplaced pytestmark lines in wrong locations
- E402/I001 ruff violations that slipped through
- Code formatting inconsistencies

A git pre-commit hook and this checklist prevent these errors from being committed.

---

## Pre-Commit Checklist (5 Steps)

### Step 1: Code Quality Validation
```bash
ruff check .
```
If violations found: `ruff check . --fix`

### Step 2: Code Formatting
```bash
ruff format . --check
```
If formatting issues: `ruff format .`

### Step 3: Run Test Suite
```bash
pytest tests/ -x -q
```

### Step 4: Review Your Diff
```bash
git diff --cached
```
Verify: No duplicate imports, no misplaced lines, changes match intent

### Step 5: Commit Only If All Pass
```bash
git commit -m "message"
```

**NEVER commit if ruff or tests fail.**

---

## Git Pre-Commit Hook

Configured at `.git/hooks/pre-commit` - auto-runs ruff checks before commits.

If hook fails, fix violations and try commit again.

---

Last Updated: 2026-03-04
