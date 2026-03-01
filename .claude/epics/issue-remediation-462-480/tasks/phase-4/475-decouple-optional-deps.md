---
name: 475-decouple-optional-deps
title: "Decouple optional feature dependencies"
status: closed
priority: P2
effort_estimate: "8-12 hours"
phase: 4
created: 2026-02-27T16:27:55Z
updated: 2026-03-01T03:55:42Z
github_issue: 475
epic: issue-remediation-462-480
---

# Task 475: Decouple optional feature dependencies

## Description
Move optional dependencies (audio, video, CAD) to service-level imports instead of eager loading in core. Currently optional features still import eagerly, bloating core dependencies.

## Priority
Medium-High - Import cleanup and stability

## Acceptance Criteria
- [ ] Audio feature imports moved to service level
- [ ] Video feature imports moved to service level
- [ ] CAD feature imports moved to service level
- [ ] Core imports no longer load optional dependencies
- [ ] Features work when dependencies installed
- [ ] Graceful fallback when dependencies missing

## Files to Modify
- `src/file_organizer/services/*/__init__.py` - Selective imports
- Core module imports - remove optional features

## Related Issues
- Import isolation (#466)
- Startup latency (#472)

## Blocking Issues
- None

## Blocked By
- Task #472 (Reduce startup latency) - should follow

## Dependencies
- Builds on Task #472: Reduce startup latency
- Supports Task #480: Tighten lint/type strictness

## Notes
- Medium effort (8-12 hours)
- Enables true optional feature handling
- Should follow lazy loading work (#472)
- Part of Phase 4: Code Quality & Maintainability
