---
name: timestamp-remediation
title: Eliminate Naive Datetime Usage and Add Defensive Timestamp Gates
status: in-progress
created: 2026-03-01T17:44:38Z
updated: 2026-03-01T18:02:15Z
progress: 0%
github: https://github.com/curdriceaurora/Local-File-Organizer/issues/526
---

# Eliminate Naive Datetime Usage and Add Defensive Timestamp Gates

## Overview

The File Organizer codebase contains 38 naive datetime instances that are potential sources of timezone bugs. Five incidents have already occurred (documented in `docs/blog/timestamp-deep-dive.md`). This epic eliminates all remaining violations and adds defensive gates to prevent recurrence.

## Background

For a file management application, timestamps are load-bearing infrastructure:

- **Archive decisions**: PARA methodology uses file age to decide what to archive
- **Backup naming**: Timestamp suffixes must be collision-free
- **Duplicate resolution**: "Newer" depends on correct timezone handling
- **Operation history**: Timestamps must be monotonically ordered for undo/redo

### Current State

- 27 instances of `datetime.now()` without timezone across 12 files
- 11 instances of `fromtimestamp()` without `tz=` across 8 files
- DTZ ruff rules available but not enabled
- Pre-commit script has 13 checks but zero datetime validation
- No timestamp-aware test fixtures

### Target State

- Zero naive datetime instances in production code
- DTZ ruff rules enforced at lint time
- Pre-commit script catches naive datetime patterns
- Timestamp-aware test fixtures prevent regressions

## Tasks

### Task 1: Enable DTZ Ruff Rules

- Add `"DTZ"` to ruff lint select in `pyproject.toml`
- Enables DTZ001-DTZ007, DTZ011-DTZ012 (10 datetime rules)
- Run initial scan to confirm violation count
- **Effort**: 30 minutes

### Task 2: Fix 27 Naive `datetime.now()` Calls

- Replace with `datetime.now(UTC)` using `from datetime import UTC`
- Files: pattern_analyzer.py, suggestion_feedback.py, smart_suggestions.py, audio/organizer.py, auto_tagging/tag_learning.py, deduplication/backup.py, deduplication/index.py, intelligence/pattern_extractor.py, johnny_decimal/migrator.py, para/detection/heuristics.py, para/rules/engine.py, config/path_migration.py
- **Effort**: 2-3 hours

### Task 3: Fix 11 Naive `fromtimestamp()` Calls

- Add `tz=UTC` parameter to all instances
- Files: analytics/storage_analyzer.py, deduplication/viewer.py, deduplication/backup.py, deduplication/index.py, copilot/rules/preview.py, history/tracker.py, tui/file_browser.py, cli/dedupe.py
- **Effort**: 1-2 hours

### Task 4: Add Timestamp Validation to Pre-Commit Script

- Add 4 new checks to `.claude/scripts/pre-commit-validation.sh`:
  1. Naive `datetime.now()` without UTC on staged files
  2. Deprecated `datetime.utcnow()` on staged files
  3. Bare `fromtimestamp()` without `tz=` parameter
  4. The `isoformat()+"Z"` trap pattern
- **Effort**: 1 hour

### Task 5: Remove Temporary Per-File DTZ Ignores

- After Tasks 2-3 fix all violations, remove any temporary ignores
- Verify `ruff check src/file_organizer/ --select DTZ` returns 0 violations
- **Effort**: 15 minutes

### Task 6: Add Timestamp-Aware Test Fixtures

- Add `time-machine` to test dependencies
- Create `tests/test_timestamp_safety.py` with tests verifying:
  - No naive datetimes leak from public APIs
  - `fromtimestamp()` calls produce timezone-aware datetimes
  - Backup naming includes microseconds
- **Effort**: 1 hour

## Execution Order

```bash
Task 1 (enable DTZ rules)
    |
    v
Task 2 + Task 3 (fix violations - can parallelize)
    |
    v
Task 5 (remove temporary ignores)
    |
    v
Task 4 + Task 6 (add gates - can parallelize)
```

## Verification

```bash
# Zero DTZ violations

ruff check src/file_organizer/ --select DTZ

# Zero naive datetime.now() in src/

rg "datetime\.now\(\)" src/file_organizer/ --type py | grep -v "now(UTC\|now(timezone"

# Zero deprecated utcnow

rg "datetime\.utcnow\(\)" src/file_organizer/ --type py

# Zero naive fromtimestamp

rg "fromtimestamp\(" src/file_organizer/ --type py | grep -v "tz="

# All tests pass

pytest tests/ -x -q --timeout=30
```

## Tasks Created

- [ ] #527 - Enable DTZ Ruff Rules (parallel: false)
- [ ] #528 - Fix 27 Naive datetime.now() Calls (parallel: true)
- [ ] #529 - Fix 11 Naive fromtimestamp() Calls (parallel: true)
- [ ] #530 - Add Timestamp Validation to Pre-Commit Script (parallel: true)
- [ ] #531 - Remove Temporary Per-File DTZ Ignores (parallel: false)
- [ ] #532 - Add Timestamp-Aware Test Fixtures (parallel: true)

Total tasks: 6
Parallel tasks: 4
Sequential tasks: 2
Estimated total effort: 6-8 hours

## References

- PRD: `.claude/prds/timestamp-remediation.md`
- Blog post: `docs/blog/timestamp-deep-dive.md`
- Historical fixes: commits 1732687, 8e6f6eb, 3078196, e8e3b07
