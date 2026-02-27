---
name: 467-watcher-fsevents-fallback
title: "Add Watcher FSEvents fallback"
status: open
priority: P1
effort_estimate: "4-6 hours"
phase: 1
created: 2026-02-27T16:27:55Z
updated: 2026-02-27T16:27:55Z
github_issue: 467
epic: issue-remediation-462-480
---

# Task 467: Add Watcher FSEvents fallback

## Description
Implement graceful fallback from FSEvents to polling-based file watching when FSEvents is unavailable. This ensures daemon stability on non-macOS systems without support for FSEvents.

## Priority
High - Stability improvement for cross-platform compatibility

## Acceptance Criteria
- [ ] FSEvents initialization wrapped in try/except
- [ ] Graceful fallback to polling watcher implemented
- [ ] Both code paths tested
- [ ] Daemon runs successfully on systems without FSEvents
- [ ] Performance metrics captured for both modes

## Files to Modify
- `src/file_organizer/watcher/*` - Implement fallback mechanism
- Tests for both watcher paths

## Related Issues
- Daemon stability
- Cross-platform support

## Blocking Issues
- None

## Blocked By
- None

## Notes
- Medium effort (4-6 hours)
- Critical for daemon reliability
- Part of Phase 1: Quick Wins & Stability
