---
name: 466-isolate-api-imports
title: "Isolate API import-time side effects"
status: open
priority: P1
effort_estimate: "12-16 hours"
phase: 2
created: 2026-02-27T16:27:55Z
updated: 2026-02-27T16:27:55Z
github_issue: 466
epic: issue-remediation-462-480
---

# Task 466: Isolate API import-time side effects

## Description
Move `.config` writes from import time to explicit initialization. Currently, importing `file_organizer.api.main` has side effects that break isolated test environments and CI workers with restricted filesystems.

## Priority
Critical - Blocks isolated test environments

## Acceptance Criteria
- [ ] `.config` directory writes removed from import time
- [ ] Initialization moved to explicit function calls
- [ ] Lazy loaders implemented for API components
- [ ] Tests pass in isolated/restricted filesystem environments
- [ ] No import-time side effects remain

## Files to Modify
- `src/file_organizer/api/main.py` - Remove side effects
- `src/file_organizer/api/__init__.py` - Implement lazy loading
- Tests updated to call initialization

## Related Issues
- Import coupling (#475)
- Startup latency (#472)
- Test isolation

## Blocking Issues
- None

## Blocked By
- None

## Dependencies
- Supports Task #472: Reduce startup latency
- Supports Task #475: Decouple optional dependencies
- Supports Task #478: Consolidate test suites

## Notes
- High effort (12-16 hours)
- Foundation for import refactoring
- Critical for test environment stability
- Part of Phase 2: Test Reliability
