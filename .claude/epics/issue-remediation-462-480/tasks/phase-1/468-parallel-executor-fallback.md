---
name: 468-parallel-executor-fallback
title: "Add ParallelProcessor executor fallback"
status: open
priority: P1
effort_estimate: "4-6 hours"
phase: 1
created: 2026-02-27T16:27:55Z
updated: 2026-02-27T16:27:55Z
github_issue: 468
epic: issue-remediation-462-480
---

# Task 468: Add ParallelProcessor executor fallback

## Description
Implement fallback chain for parallel execution: ProcessPoolExecutor → ThreadPoolExecutor. Ensures parallel processing doesn't crash in restricted environments (Docker, CI) where semaphore restrictions prevent multiprocessing.

## Priority
High - Stability improvement for restricted environments

## Acceptance Criteria
- [ ] ProcessPoolExecutor wrapped with exception handling
- [ ] ThreadPoolExecutor fallback implemented
- [ ] Executor fallback chain working correctly
- [ ] Tests pass in both process and thread modes
- [ ] No crashes in restricted environments (Docker, CI)

## Files to Modify
- `src/file_organizer/parallel/executor.py` - Implement fallback chain

## Related Issues
- Parallel processing reliability
- Docker/CI compatibility

## Blocking Issues
- None

## Blocked By
- None

## Notes
- Medium effort (4-6 hours)
- Critical for parallel processing reliability
- Part of Phase 1: Quick Wins & Stability
