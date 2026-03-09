---
issue: 639
title: refactor: consolidate web route test helpers and fixtures
analyzed: 2026-03-07T14:02:53Z
estimated_hours: 3
parallelization_factor: 1.5
status: closed
updated: 2026-03-09T06:06:50Z
---

# Parallel Work Analysis: Issue #639

## Overview
Consolidate duplicated code in web route tests by extracting shared fixtures, mock helpers, and assertion functions. Based on /simplify findings from PR #635. Improves code maintainability, test reliability (structured HTML parsing), and efficiency.

## Parallel Streams

### Stream A: Fixture & Mock Extraction
**Scope**: Extract reusable pytest fixtures for common test setup patterns
**Files**:
- `tests/conftest.py` (add fixtures)
- `tests/test_web_files_routes.py` (update to use fixtures)
- `tests/test_web_marketplace_routes.py` (update to use fixtures)
- `tests/test_web_organize_routes.py` (update to use fixtures)

**Agent Type**: test-specialist
**Can Start**: immediately
**Estimated Hours**: 1
**Dependencies**: none

**Work**:
- Extract `_build_client()` helper (9 lines, duplicated 3x)
- Create `@pytest.fixture def mock_marketplace_service()` (21 lines, duplicated 3x)
- Update 3 test files to import and use new fixtures

### Stream B: Assertion Helper Functions
**Scope**: Create reusable helper functions for common test assertion patterns
**Files**:
- `tests/conftest.py` (add helper functions)
- `tests/test_web_files_routes.py` (update to use helpers)
- `tests/test_web_marketplace_routes.py` (update to use helpers)

**Agent Type**: test-specialist
**Can Start**: immediately (after conftest.py structure from Stream A)
**Estimated Hours**: 1
**Dependencies**: Stream A (conftest.py must exist for imports)

**Work**:
- Create `assert_file_order_in_html(response_text, file1, file2)` helper
- Create `assert_html_contains(*keywords)` helper
- Create `assert_marketplace_install_called_with(mock, plugin_name)` helper
- Create HTML parser-based assertion helper to replace brittle text searches

### Stream C: Test Refactoring & Optimization
**Scope**: Apply new fixtures and helpers, parametrize redundant tests, optimize string operations
**Files**:
- `tests/test_web_files_routes.py` (refactor sorting tests)
- `tests/test_web_organize_routes.py` (parametrize organize tests)
- `tests/test_web_marketplace_routes.py` (add mock argument verification)

**Agent Type**: test-specialist
**Can Start**: after Streams A & B complete
**Estimated Hours**: 1
**Dependencies**: Stream A (fixtures), Stream B (helpers)

**Work**:
- Replace 5 sorting test methods with parametrized test
- Replace 3 organize test methods with parametrized test
- Update marketplace tests to use `assert_called_with()` verification
- Cache `.lower()` calls (optimization)
- Replace `content.index()` comparisons with helper function calls

## Coordination Points

### Shared Files
**`tests/conftest.py`**:
- Stream A: Adds fixtures (_build_client, mock_marketplace_service)
- Stream B: Adds helper functions (assert_* functions)
- Both streams need to coordinate imports and organization

**Test files** (3 files modified by all streams):
- Stream A updates them to use fixtures
- Stream B updates them to use assertion helpers
- Stream C refactors test logic and parametrization
- **Coordination**: Sequential application - A → B → C

### Sequential Requirements
1. **Fixtures must exist first** (Stream A) before tests can use them
2. **Helpers must be available** (Stream B) before Stream C can refactor tests
3. **No parallelization possible** - streams have hard dependencies

## Conflict Risk Assessment
- **Risk Level**: LOW (natural sequential dependency)
- **All work in conftest.py**: Streams A & B are additive (no conflicts)
- **All test file changes**: Sequential by nature (A applies, then B, then C)
- **No branching/merging needed**: Single feature branch handles all streams

## Parallelization Strategy

**Recommended Approach**: Sequential (despite dependency, total time is short ~3 hours)

**Rationale**: While streams could theoretically parallelize (A & B could start together since conftest.py changes don't conflict), the sequential dependency (C needs both A & B done) means:
- Parallel overhead: setup agents, manage coordination
- Net benefit: minimal (saves 0-15 min on 3h task)
- **Recommendation**: Single agent executes A → B → C in sequence

## Expected Timeline

**Sequential execution** (single agent):
- Stream A: ~1h
- Stream B: ~1h
- Stream C: ~1h
- **Total: 3 hours**
- **Includes testing & verification**

With parallel agents (theoretical):
- Stream A & B start simultaneously: 1h wall time
- Stream C after both: +1h
- **Wall time: 2h** (but adds coordination overhead)
- **Practical gain: ~15 min** (not worth complexity)

## Implementation Order

1. **Stream A first**: Extract fixtures (safest, lowest risk)
2. **Stream B second**: Add helpers (builds on A's foundation)
3. **Stream C last**: Apply changes throughout (verification)

After each stream, run subset of tests to verify no regressions.

## Notes

- All 41 existing tests must pass after refactoring
- No functionality changes - only structure
- Sorting/filtering tests will become more robust (structured HTML parsing)
- Code reuse verified by checking line-count reduction in conftest.py
- One-shot task - no ongoing monitoring needed
- Quality gates: /simplify (check reuse), /code-reviewer (design), pre-commit (tests)

## Success Criteria

✅ Tests pass (41/41)
✅ No duplicate code in conftest.py or test files
✅ 5+ sorting tests become 1 parametrized test
✅ 3 organize tests become 1 parametrized test
✅ Mock assertions use `assert_called_with()`
✅ Brittle text searches replaced with HTML parser calls
✅ String operations optimized
