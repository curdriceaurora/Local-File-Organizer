---
name: timestamp-remediation
description: Eliminate naive datetime usage and add defensive timestamp gates
status: in-progress
created: 2026-03-01T17:44:38Z
updated: 2026-03-01T17:44:38Z
---

# Timestamp Remediation

## Problem Statement

The File Organizer codebase has accumulated 38 naive datetime instances (27 `datetime.now()` without timezone + 11 `fromtimestamp()` without `tz=`) across 20 files. Five distinct timestamp incidents have already been discovered and fixed, but the root causes — missing lint rules, no pre-commit validation, and no timestamp-aware tests — remain unaddressed. For a file management application where timestamps drive archive decisions, backup naming, and operation history, these are load-bearing bugs.

## Goals

1. Fix all 38 remaining naive datetime violations
2. Enable DTZ ruff lint rules to catch future violations at lint time
3. Add timestamp validation to the pre-commit script
4. Add timestamp-aware test fixtures to prevent regressions
5. Make it impossible to introduce a new naive datetime without CI catching it

## Success Criteria

- `ruff check src/file_organizer/ --select DTZ` returns zero violations
- `rg "datetime\.now\(\)" src/file_organizer/ --type py | grep -v "now(UTC\|now(timezone"` returns zero results
- `rg "datetime\.utcnow\(\)" src/file_organizer/ --type py` returns zero results
- `rg "fromtimestamp\(" src/file_organizer/ --type py | grep -v "tz="` returns zero results
- Pre-commit script catches naive datetime patterns on staged files
- All tests pass with timestamp-aware fixtures

## Scope

### In Scope
- Fix 27 naive `datetime.now()` calls across 12 files
- Fix 11 naive `fromtimestamp()` calls across 8 files
- Enable DTZ001-DTZ012 ruff rules
- Add 4 timestamp validation checks to pre-commit script
- Add timestamp-aware test fixtures and safety tests

### Out of Scope
- Refactoring the entire datetime strategy (e.g., switching to pendulum)
- Fixing timestamp issues in test files (only production code)
- Cross-platform st_ctime handling (already fixed in commit 3078196)

## Technical Approach

1. Enable DTZ ruff rules in `pyproject.toml` to surface all violations
2. Fix violations using `from datetime import UTC` (already available via `_compat.py`)
3. Add pre-commit gates to catch new violations before they reach main
4. Add test fixtures using `time-machine` for frozen-time testing

## References

- Blog post: `docs/blog/timestamp-deep-dive.md`
- GitHub Issue #524: Code review findings
- Commits: 1732687, 8e6f6eb, 3078196, e8e3b07 (historical timestamp fixes)
