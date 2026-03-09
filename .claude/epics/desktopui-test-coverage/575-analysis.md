---

issue: 575
title: Plugin System & Marketplace Tests
analyzed: 2026-03-06T17:45:30Z
estimated_hours: 32
parallelization_factor: 2.5
status: closed
updated: 2026-03-09T06:06:50Z
---

# Parallel Work Analysis: Issue #575

## Overview

Write ~16 missing test modules for the plugin system in `src/file_organizer/plugins/`. Target module coverage from ~30% to 75%.

## Parallel Streams

### Stream A: Plugin Lifecycle & Registry Tests

**Scope**: Test plugin registration, activation, deactivation, execution, and registry CRUD
**Files**:

- `tests/plugins/test_plugin_base.py` - Abstract plugin interface compliance

- `tests/plugins/test_plugin_registry.py` - CRUD operations (add, get, list, remove)

- `tests/plugins/test_plugin_lifecycle.py` - Register, activate, deactivate, execute

- `tests/plugins/test_plugin_discovery.py` - Scan directories, validate structure, dependency resolution

- `tests/plugins/test_plugin_execution.py` - Execute with valid/invalid input, timeout handling, crash recovery
**Agent Type**: backend-specialist
**Can Start**: immediately
**Estimated Hours**: 15
**Dependencies**: none

### Stream B: Marketplace Tests

**Scope**: Test marketplace search, install, update, and uninstall operations
**Files**:

- `tests/plugins/test_marketplace_client.py` - HTTP client initialization, configuration

- `tests/plugins/test_marketplace_search.py` - Query, filter, pagination

- `tests/plugins/test_marketplace_install.py` - Download, validate, extract, register

- `tests/plugins/test_marketplace_update.py` - Version check, download, apply update

- `tests/plugins/test_marketplace_uninstall.py` - Deactivate, remove files, clean registry
**Agent Type**: backend-specialist
**Can Start**: immediately
**Estimated Hours**: 12
**Dependencies**: none

### Stream C: Error Handling & Sandboxing Tests

**Scope**: Test error recovery, graceful degradation, and plugin isolation
**Files**:

- `tests/plugins/test_plugin_error_handling.py` - Crash recovery, graceful degradation

- `tests/plugins/test_plugin_sandbox.py` - Plugin isolation, resource limits (if applicable)

- Part of registry tests: persistence and state management
**Agent Type**: backend-specialist
**Can Start**: after Stream A (needs plugin base implementation)
**Estimated Hours**: 5
**Dependencies**: Stream A

## Coordination Points

### Shared Files

- `tests/plugins/conftest.py` - Shared fixtures for plugin testing
  - Temp directories for plugin installation

  - Mock marketplace API responses

  - Plugin creation helpers

  - Both streams need to coordinate fixture definitions

### Sequential Requirements

1. Stream A must complete plugin base and registry before Stream C's isolation tests
2. Stream B can run independently but needs marketplace API mocks defined in `conftest.py`

## Conflict Risk Assessment

- **Low Risk**: Mostly different test modules

- **Medium Risk**: Both streams use plugin registry for operations

- **Medium Risk**: `conftest.py` shared by all streams

- **Mitigation**: Create `conftest.py` early with plugin creation helpers; coordinate on temp directory isolation

## Parallelization Strategy

**Recommended Approach**: Hybrid execution

1. **Setup** (1-2 hours): Create `conftest.py` with plugin fixtures and marketplace mocks
2. **Streams A & B parallel** (12-15 hours): Both run simultaneously after setup
3. **Stream C sequential** (5 hours): After Stream A completes, add error handling and sandbox tests

## Expected Timeline

With parallel execution:

- Wall time: 18-20 hours (setup + parallel A&B + sequential C)

- Total work: 32 hours

- Efficiency gain: 40%

Without parallel execution:

- Wall time: 32 hours

## Notes

- Use temp directories (`tempfile.TemporaryDirectory`) for plugin installation tests—no shared state

- Mock only external HTTP calls to marketplace API using `pytest-httpx` or `responses`

- Don't mock internal plugin code—test real plugin behavior

- Plugin creation helpers: Write utility to create minimal valid plugins for testing

- Test both success and error paths for all marketplace operations

- Registry persistence: Test save/load across test restarts using temp files

- Performance: no single test > 5s

- Each test file must have module-level docstring

- Tag tests with `@pytest.mark.unit`

- Consider plugin isolation testing carefully—test that plugins can't break each other
