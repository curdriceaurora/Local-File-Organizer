---

issue: 576
title: Updater & Watcher Tests
analyzed: 2026-03-06T17:45:30Z
estimated_hours: 28
parallelization_factor: 2.0
status: closed
updated: 2026-03-09T06:06:50Z
---

# Parallel Work Analysis: Issue #576

## Overview

Write 11 test modules for updater (6 modules at 0%) and watcher (5 modules at 0%). Target both to 90%.

## Parallel Streams

### Stream A: Updater Tests

**Scope**: Test version checking, installation, management, rollback, and version comparison
**Files**:

- `tests/updater/test_checker.py` - Version fetch, comparison, caching behavior

- `tests/updater/test_installer.py` - Download, checksum verify, extract, apply update

- `tests/updater/test_manager.py` - Lifecycle: check → download → install → restart

- `tests/updater/test_rollback.py` - Backup before update, restore on failure, cleanup

- `tests/updater/test_version.py` - Semver parsing, ordering, constraint comparison

- `tests/updater/test_config.py` - Update settings: auto-check interval, channel selection
**Agent Type**: backend-specialist
**Can Start**: immediately
**Estimated Hours**: 14
**Dependencies**: none

### Stream B: Watcher Tests

**Scope**: Test filesystem monitoring, event handling, queuing, and debouncing
**Files**:

- `tests/watcher/test_monitor.py` - Detect create, modify, delete, rename events

- `tests/watcher/test_handler.py` - Route events to handlers, filter events

- `tests/watcher/test_queue.py` - Enqueue, dequeue, priority, overflow handling

- `tests/watcher/test_debounce.py` - Coalesce rapid changes, timeout behavior

- `tests/watcher/test_filter.py` - Path/extension filtering: include/exclude patterns
**Agent Type**: backend-specialist
**Can Start**: immediately
**Estimated Hours**: 12
**Dependencies**: none

### Stream C: Cross-Cutting Tests

**Scope**: Test error recovery, concurrent operations, and configuration integration
**Files**:

- Distributed across both updater and watcher test files

- Error handling assertions in each module's tests
**Agent Type**: backend-specialist
**Can Start**: after both Streams A & B
**Estimated Hours**: 2
**Dependencies**: Streams A & B

## Coordination Points

### Shared Files

- `tests/updater/conftest.py` - Mock HTTP, version fixtures

- `tests/watcher/conftest.py` - Temp filesystem fixtures, event helpers

- Both streams are completely independent—no file conflicts

### Sequential Requirements

None—streams are completely independent

## Conflict Risk Assessment

- **Low Risk**: Two completely separate modules (updater vs watcher)

- **No conflicts**: Each stream modifies only its own test directory

- **Parallel-friendly**: Can run simultaneously with zero coordination

## Parallelization Strategy

**Recommended Approach**: Full parallel execution with sequential finalization

1. **Streams A & B parallel** (12-14 hours): Run simultaneously
2. **Stream C sequential** (2 hours): Add cross-cutting tests after both complete

## Expected Timeline

With parallel execution:

- Wall time: 14-16 hours (parallel A&B + sequential C)

- Total work: 28 hours

- Efficiency gain: 45%

Without parallel execution:

- Wall time: 28 hours

## Notes

- **Updater tests**: Mock HTTP calls using `pytest-httpx` or `responses`—no real network

- **Updater tests**: Test version comparison with realistic semver strings (1.2.3, 2.0.0-beta, etc.)

- **Updater tests**: Rollback tests need real temp directories to simulate file operations

- **Watcher tests**: Use real temp directories with actual filesystem operations

- **Watcher tests**: Use async fixtures with `pytest-asyncio` for event loop testing

- **Watcher tests**: Mock OS-level file system watchers if using watchdog library

- **Cross-cutting**: Test network failures (retry logic), filesystem errors (graceful handling)

- **Concurrent**: Test multiple watcher instances on same directory, simultaneous updates

- Each test file must have module-level docstring

- Tag async tests with `@pytest.mark.asyncio`

- Tag updater tests with `@pytest.mark.unit`

- Performance: no single test > 5s (use smaller temp structures, faster mocks)
