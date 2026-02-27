---
name: 473-refactor-modules
title: "Refactor oversized low-cohesion modules"
status: open
priority: P2
effort_estimate: "40-60 hours"
phase: 4
created: 2026-02-27T16:27:55Z
updated: 2026-02-27T16:27:55Z
github_issue: 473
epic: issue-remediation-462-480
---

# Task 473: Refactor oversized low-cohesion modules

## Description
Break up 15+ oversized service modules (>1000 LOC) with mixed concerns into focused, single-responsibility components. Reduces maintenance burden and improves code clarity.

## Priority
High - Long-term maintainability

## Acceptance Criteria
- [ ] All oversized modules identified and analyzed
- [ ] Refactoring patterns established
- [ ] Initial modules refactored (2-3 services)
- [ ] Remaining modules refactored with pattern
- [ ] Code coverage maintained ≥90%
- [ ] Tests pass for all refactored modules

## Files to Modify
- `src/file_organizer/services/` - Comprehensive refactor
- 15+ service modules requiring decomposition

## Related Issues
- Code maintainability
- Testing (#478)

## Blocking Issues
- None

## Blocked By
- None

## Dependencies
- Can be parallelized after pattern established
- Supports Task #478: Consolidate test suites
- Supports Task #480: Tighten lint/type strictness

## Notes
- Very high effort (40-60 hours)
- Largest scope task
- Can parallelize after pattern established
- Major risk of regressions - requires comprehensive testing
- Part of Phase 4: Code Quality & Maintainability
