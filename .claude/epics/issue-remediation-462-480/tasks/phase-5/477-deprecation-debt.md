---
name: 477-deprecation-debt
title: "Burn down deprecation/warning debt"
status: closed
priority: P3
effort_estimate: "8-16 hours"
phase: 5
created: 2026-02-27T16:27:55Z
updated: 2026-03-01T03:55:42Z
github_issue: 477
epic: issue-remediation-462-480
---

# Task 477: Burn down deprecation/warning debt

## Description
Address deprecation warnings and suppress/fix pytest warnings. Cleans up technical debt and reduces build noise.

## Priority
Low-Medium - Code cleanliness

## Acceptance Criteria
- [ ] All deprecation warnings identified
- [ ] Deprecated APIs replaced or suppressed
- [ ] Pytest warnings addressed
- [ ] Build output clean
- [ ] Warning-free test runs
- [ ] Documentation updated for changes

## Files to Modify
- Multiple modules using deprecated APIs
- Test configuration (pytest.ini)
- Setup/configuration files

## Related Issues
- Code cleanliness

## Blocking Issues
- None

## Blocked By
- None

## Dependencies
- None (can run in parallel with Phase 4)

## Notes
- Medium effort (8-16 hours)
- Low priority but good for code health
- Can run in parallel with Phase 4 work
- Part of Phase 5: Documentation & Warnings
