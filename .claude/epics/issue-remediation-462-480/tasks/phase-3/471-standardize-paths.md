---
name: 471-standardize-paths
title: "Standardize storage/config/state paths"
status: open
priority: P1
effort_estimate: "24-32 hours"
phase: 3
created: 2026-02-27T16:27:55Z
updated: 2026-02-27T16:27:55Z
github_issue: 471
epic: issue-remediation-462-480
---

# Task 471: Standardize storage/config/state paths

## Description
Implement consistent path handling across all modules using XDG/platform-aware path resolution. Currently inconsistent path patterns cause migration complexity and user data location uncertainty.

## Priority
Critical - Foundation for migrations and cross-platform support

## Acceptance Criteria
- [ ] XDG path resolution standard implemented
- [ ] Platform-aware path utilities created
- [ ] All module path handling refactored
- [ ] Migration framework implemented
- [ ] User data paths documented
- [ ] Cross-platform compatibility verified

## Files to Modify
- `src/file_organizer/config/paths.py` (new) - Path resolution utilities
- 10+ modules requiring path standardization
- Migration framework implementation

## Related Issues
- Migration recovery (#476)
- Future cross-platform support

## Blocking Issues
- None

## Blocked By
- None

## Dependencies
- Task #476 (Migration recovery) depends on this
- Foundation for cross-platform work

## Notes
- Very high effort (24-32 hours)
- Architectural change affecting multiple modules
- Critical for production data safety
- Must complete before #476
- Part of Phase 3: Architectural Foundation
