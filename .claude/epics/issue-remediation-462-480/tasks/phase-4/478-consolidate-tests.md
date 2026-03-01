---
name: 478-consolidate-tests
title: "Consolidate test suites and enforce conventions"
status: closed
priority: P2
effort_estimate: "20-32 hours"
phase: 4
created: 2026-02-27T16:27:55Z
updated: 2026-03-01T03:55:42Z
github_issue: 478
epic: issue-remediation-462-480
---

# Task 478: Consolidate test suites and enforce conventions

## Description
Unify test fixture patterns, consolidate overlapping test files, and enforce naming conventions across test suite. Improves test maintainability and consistency.

## Priority
Medium - Test maintainability

## Acceptance Criteria
- [ ] Test fixture patterns unified
- [ ] Overlapping test files consolidated
- [ ] Naming conventions enforced consistently
- [ ] Test organization improved
- [ ] Pytest configuration updated
- [ ] All tests pass with new structure

## Files to Modify
- `tests/` - Systematic reorganization
- `pytest.ini` - Updated configuration
- Multiple test files consolidated

## Related Issues
- NLTK hermeticity (#470)
- Import isolation (#466)

## Blocking Issues
- None

## Blocked By
- Task #470 (NLTK hermeticity) - should follow
- Task #466 (Import isolation) - should follow

## Dependencies
- Builds on Task #470: Fix NLTK test hermeticity
- Builds on Task #466: Isolate API imports

## Notes
- High effort (20-32 hours)
- Systematic refactoring of test infrastructure
- Should follow import and hermeticity fixes
- Part of Phase 4: Code Quality & Maintainability
