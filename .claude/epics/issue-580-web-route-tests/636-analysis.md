---

issue: 636
title: Web Route Tests - Error Paths & Edge Cases for 100% Coverage
analyzed: 2026-03-06T22:19:42Z
estimated_hours: 12.0
parallelization_factor: 3.5
---

# Parallel Work Analysis: Issue #636

## Overview

Phase 2 of web route testing: add 29 comprehensive tests covering error paths, edge cases, and async behavior to increase coverage from 80% to 100%. Tests will follow patterns established in Phase 1 (PR #635) and leverage lessons from Copilot code review.

## Parallel Streams

### Stream A: Error Handling Tests

**Scope**: Invalid inputs, file errors, security, concurrency
**Tests**: 10 tests for error paths and edge case handling
**Files**:

- `tests/test_web_files_routes.py` - File operation errors

- `tests/test_web_organize_routes.py` - Scan operation errors

- `tests/test_web_marketplace_routes.py` - Search/filter errors

**Key Test Categories**:

- Invalid/malformed query parameters (format validation)

- File not found / permission denied errors

- Directory traversal security checks (path validation)

- Out-of-disk space scenarios

- Concurrent file access conflicts

**Agent Type**: backend-specialist
**Can Start**: immediately
**Estimated Hours**: 3.5
**Dependencies**: none

### Stream B: Async & Streaming Tests

**Scope**: SSE events, progress streaming, response handling
**Tests**: 8 tests for async and streaming behavior
**Files**:

- `tests/test_web_organize_routes.py` - Progress streaming for scans

- `tests/test_web_files_routes.py` - Optional SSE event handling

- `tests/test_web_router.py` - Response headers and HTMX integration

**Key Test Categories**:

- SSE event stream completion and formatting

- Progress update streaming during long operations

- Response cancellation and timeout handling

- HTMX swap target behavior (HX-Swap header)

- Custom header handling (HX-Trigger, HX-Redirect)

**Agent Type**: backend-specialist (async knowledge)
**Can Start**: immediately
**Estimated Hours**: 3.0
**Dependencies**: none

### Stream C: Input Validation Tests

**Scope**: Parameter validation, edge cases, special characters
**Tests**: 6 tests for input validation boundaries
**Files**:

- `tests/test_web_files_routes.py` - Path and parameter validation

- `tests/test_web_organize_routes.py` - Methodology and mode validation

- `tests/test_web_marketplace_routes.py` - Pagination and search validation

**Key Test Categories**:

- Empty/whitespace-only inputs

- Path normalization and canonicalization

- Sort/filter combination validity

- Pagination boundaries (0, negative values, too large)

- Unicode and special characters in filenames/queries

**Agent Type**: fullstack-specialist
**Can Start**: immediately
**Estimated Hours**: 2.0
**Dependencies**: none

### Stream D: State & Integration Tests

**Scope**: Template rendering, filtering, caching behavior
**Tests**: 5 tests for integration and state management
**Files**:

- `tests/test_web_files_routes.py` - Sorting and filtering results

- `tests/test_web_organize_routes.py` - Template context rendering

- `tests/test_web_router.py` - Browser cache headers and validation

**Key Test Categories**:

- Template rendering with complex contexts

- Sorting with tied values and multiple fields

- Filter result count validation

- Browser cache headers (ETag, Cache-Control)

- Rate limit enforcement and headers

**Agent Type**: fullstack-specialist
**Can Start**: immediately
**Estimated Hours**: 3.5
**Dependencies**: none

## Coordination Points

### Shared Test Files

The 4 streams will modify the same test files but different test functions:

- `tests/test_web_files_routes.py` - Streams A, C, D

- `tests/test_web_organize_routes.py` - Streams A, B, D

- `tests/test_web_marketplace_routes.py` - Streams A, C

- `tests/test_web_router.py` - Streams B, D

**Coordination Strategy**:

- Each stream works on its own test functions (no overlap in function names)

- Use clear naming: `test_{module}_{category}_{scenario}`
  - Example: `test_files_error_invalid_path_encoding`

  - Example: `test_organize_async_progress_streaming`

  - Example: `test_files_validation_unicode_names`

### Shared Dependencies

- Phase 1 route implementations and test fixtures must be stable

- Test infrastructure from PR #635 (patterns, fixtures, client setup)

- Lessons from Copilot review (parameter validation, assertion patterns)

### Sequential Requirements

None - all streams can execute in parallel as they target different test scenarios.

## Conflict Risk Assessment

**Low Risk Overall**: Each stream targets distinct test scenarios in same files

- **File overlap**: Yes (same test modules), but different test functions

- **Route overlap**: No - each stream tests different endpoint behaviors

- **Fixture overlap**: Minimal - reuse existing fixtures from Phase 1

- **Conflict probability**: ~10% (only if agents accidentally name same function)

**Mitigation**:

- Use stream-specific naming convention for test functions

- Pre-coordinate naming with agent assignments

- Frequent git commits prevent long-lived merge conflicts

## Parallelization Strategy

**Recommended Approach**: Full Parallel Execution

Launch all 4 streams simultaneously:
1. Stream A, B, C, D start immediately (no dependencies)
2. Agents work on different test scenarios in same files
3. Commit frequently with clear test function names
4. Pull and merge from teammates every 30 minutes
5. Consolidate results when all streams complete

**No sequential wait points** - true parallel execution possible.

## Expected Timeline

**With parallel execution (4 agents, 1 stream each):**

- Wall time: 3.5 hours (longest stream: Streams A & D)

- Total work: 12 hours

- Efficiency gain: 71% (vs 12h sequential = 3.4x speedup)

**Without parallel execution (1 agent sequentially):**

- Wall time: 12 hours

## Testing Integration Notes

**From Phase 1 Lessons** (to apply in Phase 2):

1. **Route Parameter Validation**

   - Always verify actual route signatures before testing

   - Reference validated routes from copilot-review-findings.md

   - Use params dict for automatic URL encoding

2. **Test Assertions**

   - Assert meaningful behavior, not just status codes

   - Check response content when testing filtering/ordering

   - Separate assertions for different concerns (status AND content)

3. **Test Patterns**

   - Match pytest patterns from PR #635

   - Use TestClient fixtures from test setup

   - Follow naming: `test_module_category_scenario`

4. **Error Testing**

   - Verify exact error messages for user-facing errors

   - Test both client-side validation and server-side safety

   - Cover security edge cases (path traversal, injection)

## Module Coverage Mapping

| Module | Phase 1 Tests | Phase 2 Tests | Target |
|--------|---------------|---------------|--------|
| files_routes | 12 | 9 (3A, 2C, 2D, 2B) | 21 → 100% |
| organize_routes | 18 | 10 (4A, 3B, 2C, 1D) | 28 → 100% |
| marketplace_routes | 8 | 6 (2A, 1C, 3D) | 14 → 100% |
| router | 12 | 4 (2D, 2B) | 16 → 100% |
| **Total** | **50** | **29** | **80% → 100%** |

## Deliverables

**Per Stream**:

- Set of test functions in respective modules

- All tests passing locally

- All assertions meaningful (not placeholder)

- Clear test documentation

**Overall**:

- 29 new tests added

- Web module coverage: 80% → 100%

- All tests passing in CI

- No behavior changes (tests only)

- Follows Phase 1 patterns from PR #635

## Known Unknowns & Risks

**Potential Issues**:

- Async test timing: SSE tests may need tuning for timing stability

- Fixture availability: Some error scenarios may need new test fixtures

- Rate limit testing: May require test-specific rate limit configuration

**Mitigation**:

- Use pytest markers for timing-sensitive tests (may need --timeout adjustment)

- Create error scenario fixtures in stream A, share with other streams

- Coordinate with infra on test environment rate limit settings

## Notes

- Phase 2 builds directly on Phase 1 test infrastructure

- Copilot review findings should guide test patterns and parameter validation

- No architectural changes needed - tests only

- This is final coverage push for web module (from Phase 2 roadmap)
