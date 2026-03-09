---

issue: 581
title: Services Layer Tests
analyzed: 2026-03-06T17:45:30Z
estimated_hours: 60
parallelization_factor: 3.0
status: closed
updated: 2026-03-09T06:06:50Z
---

# Parallel Work Analysis: Issue #581

## Overview

Write test modules covering the entire `src/file_organizer/services/` layer. Focus on intelligence module (23 files, 0% coverage) with target of 70%, and other services to 80%.

## Parallel Streams

### Stream A: Intelligence Module Tests (Primary)

**Scope**: Test all 23 modules in intelligence submodule—learning, patterns, scoring
**Files**:

- `tests/services/intelligence/test_preference_learner.py` - User feedback, model updates, predictions

- `tests/services/intelligence/test_pattern_extractor.py` - File naming, directory, temporal patterns

- `tests/services/intelligence/test_scoring.py` - Relevance scoring, confidence calculation, ranking

- `tests/services/intelligence/test_*.py` (all 23 modules under services/intelligence/)
**Agent Type**: backend-specialist
**Can Start**: immediately
**Estimated Hours**: 28
**Dependencies**: none

### Stream B: Existing Service Gaps (Analytics, Auto-Tagging, Copilot)

**Scope**: Audit and fill coverage gaps in analytics, auto-tagging, and copilot services
**Files**:

- `tests/services/analytics/test_*.py` - Extend with missing test coverage

- `tests/services/auto_tagging/test_*.py` - Extend with tag recommendation, learning

- `tests/services/copilot/test_*.py` - Extend with suggestion generation, context building
**Agent Type**: backend-specialist
**Can Start**: immediately
**Estimated Hours**: 12
**Dependencies**: none

### Stream C: Audio, Dedup, Video Services

**Scope**: Audit and fill coverage gaps in audio, deduplication, and video services
**Files**:

- `tests/services/audio/test_*.py` - Extend with transcription, language detection, format conversion

- `tests/services/deduplication/test_*.py` - Extend with image dedup, document dedup, quality assessment

- `tests/services/video/test_*.py` - Extend with scene detection, format handling
**Agent Type**: backend-specialist
**Can Start**: immediately
**Estimated Hours**: 10
**Dependencies**: none

### Stream D: Root-Level Service Files

**Scope**: Test core service processing and suggestion logic
**Files**:

- `tests/services/test_text_processor.py` - Text extraction, format handling

- `tests/services/test_vision_processor.py` - Image/video pipeline, model dispatching

- `tests/services/test_pattern_analyzer.py` - Naming pattern detection, matching

- `tests/services/test_smart_suggestions.py` - Placement suggestion logic, scoring

- `tests/services/test_misplacement_detector.py` - Context analysis, anomaly detection

- `tests/services/test_suggestion_feedback.py` - Feedback recording, aggregation
**Agent Type**: backend-specialist
**Can Start**: immediately
**Estimated Hours**: 10
**Dependencies**: none

## Coordination Points

### Shared Files

- `tests/services/conftest.py` - Shared fixtures for all service tests
  - Mock Ollama/Whisper/vision backends

  - Temp database fixtures for stateful tests

  - Mock filesystem operations

  - All streams import from this

### Sequential Requirements

None—all streams are completely independent

## Conflict Risk Assessment

- **Low Risk**: Different service submodules with clear boundaries

- **Low Risk**: All use same fixture patterns and mock strategies

- **Mitigation**: Create comprehensive `conftest.py` early with standard mocks for external services

## Parallelization Strategy

**Recommended Approach**: Full parallel execution with shared fixtures

1. **Setup** (2-3 hours): Create `tests/services/conftest.py` with:

   - Mock Ollama/Whisper/vision backends

   - Temp database/filesystem fixtures

   - Common service configuration helpers

2. **Streams A, B, C, D parallel** (57-58 hours):

   - Stream A: 28 hours (intelligence—largest effort)

   - Streams B, C, D: 10-12 hours each

   - All run simultaneously after setup

## Expected Timeline

With parallel execution:

- Wall time: 30-32 hours (setup + longest stream A)

- Total work: 60 hours

- Efficiency gain: 48%

Without parallel execution:

- Wall time: 60 hours

## Notes

- **Intelligence focus**: This is the largest gap (23 files, 0% coverage)—allocate most effort here

- **External service mocks**: Mock only HTTP/GPU boundaries (Ollama, Whisper, vision APIs)—don't mock internal service code

- **Stateful testing**: Use temp databases for preference learning and pattern storage tests

- **Database fixtures**: Create clean test databases for each test via fixtures

- **Filesystem testing**: Use temp directories (`tempfile.TemporaryDirectory`) for file operations

- **Stream A strategy** (intelligence):
  - Create base test classes for common intelligence testing patterns

  - Test preference learning with simple feedback sequences

  - Test pattern extraction with curated file/directory structures

  - Test scoring with known input → expected output mappings

  - Use parameterized tests for multiple pattern types

- **Existing gaps audit**:
  - Run `pytest --cov` on existing service tests to identify coverage gaps

  - Add specific tests for uncovered branches/functions

  - Focus on error paths and edge cases

- Each test file must have module-level docstring

- Tag all tests with `@pytest.mark.unit`

- Performance: no single test > 5s (use minimal mocks, fast stubs)

- Consider using fixtures for common patterns: mock model outputs, temp databases, file structures
