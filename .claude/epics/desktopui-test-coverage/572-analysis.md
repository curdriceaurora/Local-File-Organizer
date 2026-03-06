---

issue: 572
title: API Router & Middleware Tests
analyzed: 2026-03-06T17:45:30Z
estimated_hours: 50
parallelization_factor: 3.0
---

# Parallel Work Analysis: Issue #572

## Overview

Write ~22 missing test modules for FastAPI routers and middleware in `src/file_organizer/api/`. Target module coverage from ~46% to 80%.

## Parallel Streams

### Stream A: Router Tests

**Scope**: Create test files for all FastAPI routers (organize, files, search, health, etc.)
**Files**:

- `tests/api/test_organize_routes.py`

- `tests/api/test_files_routes.py`

- `tests/api/test_search_routes.py`

- `tests/api/test_health_routes.py`

- `tests/api/test_models_routes.py`

- `tests/api/test_*_routes.py` (all router test files)
**Agent Type**: backend-specialist
**Can Start**: immediately
**Estimated Hours**: 30
**Dependencies**: none

### Stream B: Middleware & App Tests

**Scope**: Create test files for middleware (auth, CORS, error handling, logging) and app factory
**Files**:

- `tests/api/test_middleware_auth.py`

- `tests/api/test_middleware_cors.py`

- `tests/api/test_middleware_error_handling.py`

- `tests/api/test_middleware_logging.py`

- `tests/api/test_app_factory.py`
**Agent Type**: backend-specialist
**Can Start**: immediately
**Estimated Hours**: 15
**Dependencies**: none

### Stream C: Response Schema Validation

**Scope**: Verify all routers return correct JSON schemas and status codes
**Files**:

- Part of `tests/api/test_*_routes.py` (schema assertions in router tests)

- May need to create `tests/api/conftest.py` for shared response validators
**Agent Type**: backend-specialist
**Can Start**: after Stream A completes
**Estimated Hours**: 5
**Dependencies**: Stream A (needs router tests to exist)

## Coordination Points

### Shared Files

- `tests/api/conftest.py` - Shared fixtures (AsyncClient, test app instance)
  - Stream A & B need to coordinate on fixture definitions

  - One agent should create base fixtures, other extends if needed

### Sequential Requirements

1. App factory tests (Stream B) should verify middleware chain before router tests use it
2. Router tests (Stream A) depend on working app factory
3. Response validation (Stream C) depends on router tests being complete

## Conflict Risk Assessment

- **Low Risk**: Streams work on different router and middleware modules

- **Medium Risk**: Both streams need `tests/api/conftest.py` for fixtures

- **Mitigation**: Create `conftest.py` in Stream B first, then import in Stream A

## Parallelization Strategy

**Recommended Approach**: Parallel with coordination

1. **Stream B first** (5-10 hours): Create app factory tests and middleware tests, establish shared fixtures in `conftest.py`
2. **Stream A parallel** (20-30 hours): Create router tests using fixtures from Stream B's `conftest.py`
3. **Stream C after A** (5 hours): Add response schema validation assertions

## Expected Timeline

With parallel execution:

- Wall time: 35-40 hours (B sequential, then A & B overlap, then C)

- Total work: 50 hours

- Efficiency gain: 20-30%

Without parallel execution:

- Wall time: 50 hours

## Notes

- Use `httpx.AsyncClient` with `pytest-asyncio` for testing async endpoints

- Mount full app via `create_app()` for integration-style tests

- Cover both success (2xx) and error (4xx/5xx) paths

- Test all HTTP methods (GET, POST, PUT, DELETE) per router

- Ensure no mocking of internal modules—only mock HTTP boundaries

- Tag tests with `@pytest.mark.unit` or `@pytest.mark.asyncio`

- Each test file must have module-level docstring

- Performance: no single test > 5s
