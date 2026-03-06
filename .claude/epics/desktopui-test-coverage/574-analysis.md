---

issue: 574
title: Models, Client & Config Tests
analyzed: 2026-03-06T17:45:30Z
estimated_hours: 25
parallelization_factor: 2.5
---

# Parallel Work Analysis: Issue #574

## Overview

Write ~9 missing test modules for models (25-56% coverage), client library (~25%), and config (~50%). Target all three to 90%.

## Parallel Streams

### Stream A: Model Tests

**Scope**: Test model manager, registry, analytics, and base model classes
**Files**:

- `tests/models/test_model_manager.py` - Init, load, unload, switch models

- `tests/models/test_registry.py` - CRUD operations (register, get, list, remove)

- `tests/models/test_analytics.py` - Usage tracking, metrics, stats export

- `tests/models/test_base.py` - Abstract interface compliance, config parsing

- `tests/models/test_text_model.py` - Ollama stub, text generation, error handling

- `tests/models/test_vision_model.py` - Vision model, image processing

- `tests/models/test_audio_model.py` - Whisper stub, transcription, language detection
**Agent Type**: backend-specialist
**Can Start**: immediately
**Estimated Hours**: 12
**Dependencies**: none

### Stream B: Client Library Tests

**Scope**: Test HTTP client, request building, response parsing, and public API methods
**Files**:

- `tests/client/test_client.py` - Initialization, configuration, base URL/timeout/retry setup

- `tests/client/test_request_building.py` - Correct URLs, headers, auth token handling

- `tests/client/test_response_parsing.py` - JSON deserialization, error handling, retries

- `tests/client/test_api_methods.py` - Public methods: organize, dedupe, status, health
**Agent Type**: backend-specialist
**Can Start**: immediately
**Estimated Hours**: 8
**Dependencies**: none

### Stream C: Config Tests

**Scope**: Test config loading, validation, merging, and defaults
**Files**:

- `tests/config/test_config_loading.py` - Load from TOML, YAML, environment variables

- `tests/config/test_config_validation.py` - Required fields, type checking, range validation

- `tests/config/test_config_merging.py` - Priority order: file + env + defaults

- `tests/config/test_config_defaults.py` - Every setting has sensible default
**Agent Type**: backend-specialist
**Can Start**: immediately
**Estimated Hours**: 5
**Dependencies**: none

## Coordination Points

### Shared Files

None expected—streams work on completely separate modules

- Models: `src/file_organizer/models/`

- Client: `src/file_organizer/client/`

- Config: `src/file_organizer/config/`

### Sequential Requirements

None—all streams are completely independent

## Conflict Risk Assessment

- **Low Risk**: Three completely different modules with no overlap

- **No conflicts**: Each stream touches different files exclusively

- **Parallel-friendly**: Can run all three simultaneously with zero coordination

## Parallelization Strategy

**Recommended Approach**: Full parallel execution

Launch all three streams simultaneously:
1. Stream A: 12 hours (models)
2. Stream B: 8 hours (client)
3. Stream C: 5 hours (config)

## Expected Timeline

With parallel execution:

- Wall time: 12 hours (longest stream)

- Total work: 25 hours

- Efficiency gain: 52%

Without parallel execution:

- Wall time: 25 hours

## Notes

- Stream A: Mock Ollama/Whisper/vision backends—test stub implementations

- Stream B: Mock HTTP responses using `pytest-httpx` or `responses` library

- Stream C: Use temp files for TOML/YAML config loading tests

- All streams: Each test file must have module-level docstring

- Use fixtures for common setup (mock models, mock HTTP clients, temp config files)

- Tag all tests with appropriate markers: `@pytest.mark.unit`

- Performance: no single test > 5s

- Consider using `pytest-mock` for clean mocking patterns
