---
name: 474-ci-workflow-dedup
title: "Remove CI workflow duplication"
status: open
priority: P2
effort_estimate: "4-6 hours"
phase: 4
created: 2026-02-27T16:27:55Z
updated: 2026-02-27T16:27:55Z
github_issue: 474
epic: issue-remediation-462-480
---

# Task 474: Remove CI workflow duplication

## Description
Consolidate 3+ duplicate workflow definitions into single parameterized workflow. Reduces maintenance burden and ensures consistency across CI jobs.

## Priority
Medium - Development experience improvement

## Acceptance Criteria
- [ ] All workflow definitions analyzed
- [ ] Parameterized workflow template created
- [ ] All jobs converted to use template
- [ ] CI runs successfully with consolidated workflows
- [ ] Maintenance complexity reduced

## Files to Modify
- `.github/workflows/*.yml` - Consolidate into reusable patterns

## Related Issues
- CI/CD maintainability

## Blocking Issues
- None

## Blocked By
- None

## Dependencies
- None (standalone)

## Notes
- Low-medium effort (4-6 hours)
- Quick win for developer experience
- Part of Phase 4: Code Quality & Maintainability
