---
name: 470-nltk-test-hermeticity
title: "Fix NLTK test hermeticity"
status: in-progress
priority: P1
effort_estimate: "8-12 hours"
phase: 2
created: 2026-02-27T16:27:55Z
updated: 2026-02-27T17:20:00Z
started: 2026-02-27T17:20:00Z
github_issue: 470
epic: issue-remediation-462-480
---

# Task 470: Fix NLTK test hermeticity

## Description
Remove dependency on host NLTK corpus state by mocking NLTK loaders and embedding test fixtures. Tests currently fail in clean containers without pre-installed corpora, causing CI/local environment mismatches.

## Priority
High - Test reliability and CI determinism

## Acceptance Criteria
- [ ] NLTK loaders mocked in tests
- [ ] Test fixtures embedded (no external corpus dependencies)
- [ ] Tests pass in clean container environments
- [ ] No environment-specific failures
- [ ] Local and CI test results consistent

## Files to Modify
- `tests/utils/test_text_processing.py` - Mock NLTK loaders
- `src/file_organizer/utils/text_processing.py` - Ensure mockability
- Test fixtures embedded

## Related Issues
- Test reliability
- CI determinism

## Blocking Issues
- None (but supports #478)

## Blocked By
- None

## Dependencies
- Supports Task #478: Consolidate test suites

## Notes
- Medium-high effort (8-12 hours)
- Critical for test reliability
- Eliminates flaky test failures
- Part of Phase 2: Test Reliability
