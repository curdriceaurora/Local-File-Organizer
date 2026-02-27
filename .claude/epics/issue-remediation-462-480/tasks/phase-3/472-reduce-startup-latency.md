---
name: 472-reduce-startup-latency
title: "Reduce CLI/API startup latency"
status: open
priority: P1
effort_estimate: "20-28 hours"
phase: 3
created: 2026-02-27T16:27:55Z
updated: 2026-02-27T16:27:55Z
github_issue: 472
epic: issue-remediation-462-480
---

# Task 472: Reduce CLI/API startup latency

## Description
Optimize import chain and implement lazy loading for commands and services. Currently eager imports load 50+ modules on startup, causing 2-3 second startup latency that reduces usability.

## Priority
Critical - User-facing performance

## Acceptance Criteria
- [ ] Import time profiling completed
- [ ] Startup latency ≥50% improvement achieved
- [ ] Lazy loading implemented for commands
- [ ] Lazy loading implemented for services
- [ ] Memory footprint reduced
- [ ] Performance metrics documented

## Files to Modify
- `src/file_organizer/cli/__init__.py` - Lazy command loading
- `src/file_organizer/api/__init__.py` - Lazy service loading
- Multiple service modules requiring lazy loading

## Related Issues
- Import isolation (#466)
- Optional dependencies (#475)

## Blocking Issues
- None

## Blocked By
- Task #466 (Import isolation) - should follow

## Dependencies
- Builds on Task #466: Isolate API imports
- Supports Task #475: Decouple optional dependencies

## Notes
- High effort (20-28 hours)
- User-facing performance improvement
- Should follow #466 (import isolation work)
- Target: 2-3s → ~1s startup time
- Part of Phase 3: Architectural Foundation
