---

issue: 578
title: Integration & End-to-End Workflow Tests
analyzed: 2026-03-06T17:45:30Z
estimated_hours: 45
parallelization_factor: 1.5
status: closed
updated: 2026-03-09T06:06:50Z
---

# Parallel Work Analysis: Issue #578

## Overview

Write integration tests covering cross-module workflows and audit residual coverage gaps in modules with existing tests. Depends on tasks #572, #575, #577, #580, #581 being complete.

## Parallel Streams

### Stream A: Core Pipeline Integration Tests

**Scope**: Test end-to-end file organization, undo/redo, and event bus workflows
**Files**:

- `tests/integration/test_organization_pipeline.py` - Full pipeline: scan → detect → analyze → suggest → move → record

- `tests/integration/test_undo_redo_workflow.py` - Organize → undo → verify → redo → verify

- `tests/integration/test_event_bus_integration.py` - Publish → subscribe → handle → store

- `tests/integration/test_daemon_workflow.py` - Start → watch → detect → process → stop
**Agent Type**: fullstack-specialist
**Can Start**: after all dependency tasks (#572, #575, #577, #580, #581) complete
**Estimated Hours**: 18
**Dependencies**: All unit test tasks (#572-577, #580-581)

### Stream B: Plugin & Config Integration Tests

**Scope**: Test plugin activation/execution and configuration-driven behavior
**Files**:

- `tests/integration/test_plugin_integration.py` - Load → activate → execute → deactivate

- `tests/integration/test_config_behavior_integration.py` - Change config → restart → verify behavior

- `tests/integration/test_cli_service_integration.py` - CLI → service → result → formatted output
**Agent Type**: fullstack-specialist
**Can Start**: after all dependency tasks complete
**Estimated Hours**: 10
**Dependencies**: All unit test tasks

### Stream C: Methodology & Multi-Format Tests

**Scope**: Test complex workflows: methodologies (PARA, Johnny Decimal) and multi-format processing
**Files**:

- `tests/integration/test_methodology_pipeline.py` - Select methodology → organize → verify structure

- `tests/integration/test_dedup_pipeline.py` - Scan → hash → find → present → resolve

- `tests/integration/test_multiformat_pipeline.py` - Process text + image + audio together
**Agent Type**: fullstack-specialist
**Can Start**: after all dependency tasks complete
**Estimated Hours**: 8
**Dependencies**: All unit test tasks

### Stream D: Residual Coverage Audit

**Scope**: Audit existing modules and fill coverage gaps to reach 80%+
**Files**:

- Distributed: enhancement of existing test files in `tests/core/`, `tests/daemon/`, `tests/events/`, etc.

- Focus areas: `core/`, `daemon/`, `events/`, `history/`, `undo/`, `utils/`, `parallel/`, `pipeline/`, `methodologies/`, `optimization/`, `deploy/`, `integrations/`, `interfaces/`
**Agent Type**: backend-specialist
**Can Start**: during parallel test work (if coverage data available) or after unit tests
**Estimated Hours**: 9
**Dependencies**: All unit test tasks (to establish baselines)

## Coordination Points

### Shared Files

- `tests/integration/conftest.py` - Shared fixtures for all integration tests
  - FileOrganizer instance configuration

  - Temp file structures for workflows

  - Mock external services (Ollama, Whisper, marketplace API)

  - Event bus mocks and helpers

  - All streams import from this

### Sequential Requirements

1. **All unit tests must complete first** (#572-577, #580-581) before integration tests

   - Integration tests exercise code that unit tests validate

   - Can't test integration if units aren't working
2. **Coverage audit can start during integration work** once coverage baseline is established

## Conflict Risk Assessment

- **High dependencies**: This task depends on 5 other tasks being complete

- **Medium coordination**: All streams share `conftest.py` fixtures

- **Low file conflicts**: Each integration test focuses on different workflows

- **Mitigation**:
  - Block this task until dependencies (#572-577, #580-581) are done

  - Create shared fixtures early

  - Coordinate on mock implementations (especially Ollama, Whisper)

## Parallelization Strategy

**Recommended Approach**: Sequential by dependency phase, then parallel by workflow

**Phase 1: Wait for Dependencies** (blocking)

- All 5 dependency tasks (#572, #575, #577, #580, #581) must complete

- This is a critical path blocker

**Phase 2: Setup** (1-2 hours)

- Create `tests/integration/conftest.py` with shared fixtures

- Mock external services (Ollama, Whisper, marketplace API)

- Create temp file structure helpers

**Phase 3: Parallel Streams** (18-24 hours)

- Streams A, B, C run simultaneously

- Each focuses on different workflow areas

- Minimal coordination needed (all use shared conftest)

**Phase 4: Coverage Audit** (9 hours)

- Can run during Phase 3 or after (parallel or sequential)

- Analyze coverage reports from Phase 3

- Add missing tests to existing test files

## Expected Timeline

With parallel execution (after dependencies complete):

- Wall time: 28-32 hours (setup + parallel 3 streams + audit)

- Total work: 45 hours

- Efficiency gain: 30%

Without parallel execution:

- Wall time: 45 hours

## Notes

- **Critical dependency**: This task cannot start until #572, #575, #577, #580, #581 are merged to main

- **Integration scope**: These tests exercise real file operations on real disk—use temp directories

- **No AI calls**: Mock Ollama and Whisper completely—integration tests verify orchestration, not model quality

- **Event bus testing**: Create test event bus implementation that captures events instead of using real handlers

- **Daemon testing**: Mock subprocess—don't actually start daemon in tests

- **Coverage audit**: Use `pytest --cov` to generate coverage reports, identify gaps, add specific tests

- Each integration test should cover one complete workflow end-to-end

- Use `@pytest.mark.integration` to tag all integration tests

- Each test file must have module-level docstring

- Performance: integration tests can be slower (10-30s) since they test full stack

- Consider creating shared fixtures for common setup: temp file trees, config managers, event buses
