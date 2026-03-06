---

issue: 573
title: TUI View Tests
analyzed: 2026-03-06T17:45:30Z
estimated_hours: 18
parallelization_factor: 2.0
---

# Parallel Work Analysis: Issue #573

## Overview

Write ~5 missing test modules for TUI views in `src/file_organizer/tui/`. Target module coverage from ~44% to 90%.

## Parallel Streams

### Stream A: Core App & Screen Tests

**Scope**: Test app initialization, lifecycle, and screen rendering
**Files**:

- `tests/tui/test_app.py` - App initialization, startup/shutdown, screen rendering

- `tests/tui/test_screens.py` - Screen navigation, transitions, state management
**Agent Type**: frontend-specialist
**Can Start**: immediately
**Estimated Hours**: 10
**Dependencies**: none

### Stream B: Widget & Interaction Tests

**Scope**: Test custom widgets, key bindings, and user interactions
**Files**:

- `tests/tui/test_widgets.py` - Widget rendering, state updates, composition

- `tests/tui/test_key_bindings.py` - Global and screen-specific key bindings

- `tests/tui/test_interactions.py` - User input flows, error states, accessibility
**Agent Type**: frontend-specialist
**Can Start**: immediately
**Estimated Hours**: 8
**Dependencies**: none

## Coordination Points

### Shared Files

- `tests/tui/conftest.py` - Textual pilot fixtures for async testing
  - Both streams need to import `app.run_test()` and pilot helpers

  - One stream should establish this, other imports

### Sequential Requirements

1. App tests (Stream A) should verify lifecycle before widget tests assume app is running
2. Widget tests (Stream B) may depend on app structure defined in Stream A

## Conflict Risk Assessment

- **Low Risk**: Different test modules for different concerns

- **Low Risk**: Both use Textual's `pilot` async context manager (standard pattern)

- **Mitigation**: Coordinate on `conftest.py` pilot fixture setup

## Parallelization Strategy

**Recommended Approach**: Parallel with light coordination

1. **Create `tests/tui/conftest.py`** (1 hour): Define Textual pilot fixtures and helpers
2. **Stream A & B parallel** (15-16 hours): Run simultaneously, both import from shared `conftest.py`

## Expected Timeline

With parallel execution:

- Wall time: 11-12 hours (setup + parallel streams)

- Total work: 18 hours

- Efficiency gain: 35-40%

Without parallel execution:

- Wall time: 18 hours

## Notes

- Use Textual `pilot` via `app.run_test()` async context manager (not manual rendering)

- Test key press handling with `pilot.press(key)`

- Verify screen transitions with `pilot.app.screen_stack`

- Test data display by checking widget content after state updates

- Verify CSS class application and widget visibility

- All tests must be async (`async def test_*`) with `@pytest.mark.asyncio`

- Each test file must have module-level docstring

- Performance: no single test > 5s

- Focus on user-facing behavior, not internal implementation details
