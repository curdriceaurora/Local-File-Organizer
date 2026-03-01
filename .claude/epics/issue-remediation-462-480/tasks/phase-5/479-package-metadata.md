---
name: 479-package-metadata
title: "Fix package metadata and add validation"
status: closed
priority: P3
effort_estimate: "4-8 hours"
phase: 5
created: 2026-02-27T16:27:55Z
updated: 2026-03-01T03:55:42Z
github_issue: 479
epic: issue-remediation-462-480
---

# Task 479: Fix package metadata and add validation

## Description
Fix package URLs in pyproject.toml and add release metadata CI check to ensure correct package information.

## Priority
Low - Release cleanliness

## Acceptance Criteria
- [ ] Package URLs in pyproject.toml verified and fixed
- [ ] Release metadata CI check implemented
- [ ] CI validates package metadata on releases
- [ ] Package information correct and consistent
- [ ] Release process improved

## Files to Modify
- `pyproject.toml` - Fix package URLs
- `.github/workflows/release.yml` - Add validation check

## Related Issues
- Release quality

## Blocking Issues
- None

## Blocked By
- None

## Dependencies
- None (standalone)

## Notes
- Low effort (4-8 hours)
- Quick win for release quality
- Can run in parallel with Phase 4
- Part of Phase 5: Documentation & Warnings
