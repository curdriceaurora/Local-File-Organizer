---
name: 480-tighten-type-strictness
title: "Tighten lint/type strictness"
status: open
priority: P2
effort_estimate: "24-40 hours"
phase: 4
created: 2026-02-27T16:27:55Z
updated: 2026-02-27T16:27:55Z
github_issue: 480
epic: issue-remediation-462-480
---

# Task 480: Tighten lint/type strictness

## Description
Enable mypy strict mode module-by-module with ratcheting approach. Fix type violations in critical modules to improve code quality and type safety.

## Priority
Medium - Type safety and code quality

## Acceptance Criteria
- [ ] Mypy strict mode enabled module-by-module
- [ ] Type violations fixed in critical modules
- [ ] Ratcheting approach implemented
- [ ] Type coverage improved across codebase
- [ ] CI validation of type strictness
- [ ] Zero type errors in enabled modules

## Files to Modify
- `pyproject.toml` - Mypy configuration
- Multiple core modules - Type annotation fixes
- Critical modules prioritized for strict mode

## Related Issues
- Code quality
- Type safety

## Blocking Issues
- None

## Blocked By
- Other Phase 4 refactoring tasks should precede

## Dependencies
- Should be last (after other Phase 4 refactoring)
- Builds on Task #473: Module refactoring

## Notes
- High effort (24-40 hours)
- Should be last Phase 4 task (requires refactoring to complete first)
- Module-by-module approach reduces risk
- Ratcheting prevents regression
- Part of Phase 4: Code Quality & Maintainability
