---
name: 469-fix-readme-links
title: "Fix README broken links"
status: open
priority: P1
effort_estimate: "2 hours"
phase: 1
created: 2026-02-27T16:27:55Z
updated: 2026-02-27T16:27:55Z
github_issue: 469
epic: issue-remediation-462-480
---

# Task 469: Fix README broken links

## Description
Fix 3-5 broken links in README.md and add CI link-integrity test to prevent future regressions.

## Priority
High - Quick win with immediate UX improvement

## Acceptance Criteria
- [ ] All broken links in README.md identified and fixed
- [ ] Links verified to point to existing files
- [ ] CI workflow updated with link-integrity test
- [ ] Test runs successfully in CI
- [ ] Documentation credibility restored

## Files to Modify
- `README.md` - Fix broken links
- `.github/workflows/ci.yml` - Add link-integrity check

## Related Issues
- None (independent task)

## Blocking Issues
- None

## Blocked By
- None

## Notes
- Quick win task - 2 hours effort
- Improves user experience and documentation credibility
- Part of Phase 1: Quick Wins & Stability
