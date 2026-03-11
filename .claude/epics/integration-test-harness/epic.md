# Epic #728: Integration Test Harness

## Overview

Our 95% unit coverage hides integration blindness — every component works in isolation, but bugs live in the wiring between them. Issues #724 (config overrides ignored) and #726 (vision model race condition) were both missed because unit tests mock away the exact boundaries where these bugs occur.

This epic establishes a systematic integration test harness covering 7 gap patterns identified across 1,737 unit tests and 132 integration tests.

## Architecture Decisions

- **Mock only external HTTP**: Ollama/OpenAI clients are mocked; all internal services (TextProcessor, VisionProcessor, ConfigManager, ParallelProcessor, FileOrganizer) use real instances
- **Mock at model.generate() level**: Not at service level — this exercises the real service→model wiring
- **Real filesystem**: Tests use `tmp_path` for source/output/config dirs
- **Real SQLite**: OperationHistory uses temp db files, not mocks
- **pytest.mark.integration**: All new tests marked; CI runs them on main pushes only (not every PR)

## Streams

```
Stream A (Foundation):  conftest + Gap P1 (Config-to-Runtime)    — do first
Stream B (Services):    Gap P2 (Cross-Service) + P3 (Errors)     — after A
Stream C (Concurrency): Gap P4 (Concurrency) + P5 (Cleanup)      — after A, parallel with B
Stream D (E2E):         Gap P6 (CLI) + P7 (State Recovery)        — after B+C
```

### Dependency Graph

```
Stream A (conftest + P1) ──→ Stream B (P2 + P3) ──→ Stream D (P6 + P7)
Stream A (conftest + P1) ──→ Stream C (P4 + P5) ──→ Stream D (P6 + P7)
```

## Stream Details

### Stream A: Foundation + Config-to-Runtime (#732)

**Files**: `tests/integration/conftest.py`, `tests/integration/test_config_to_runtime.py`

**Shared fixtures (conftest.py)**:
- `stub_text_model_generate` — patches `TextModel.generate()` with deterministic responses
- `stub_vision_model_generate` — patches `VisionModel.generate()` with deterministic responses
- `stub_model_init` — patches model `initialize()` to skip Ollama/OpenAI client setup
- `integration_source_dir` — temp dir with real `.txt`, `.csv`, `.md` files
- `integration_output_dir` — clean temp output dir
- `isolated_config_dir` — temp dir for ConfigManager YAML (no user config interference)

**Tests (>=6)**:
1. Config model selection flows to organizer
2. Config parallel workers flows to organizer
3. Config dry_run prevents file creation
4. Env provider openai flows to model config
5. Config profile switch changes model
6. Config temperature propagates to model options

**Acceptance**: All 6 tests pass, fixtures reusable by other streams.

### Stream B: Cross-Service + Error Propagation (#733)

**Files**: `tests/integration/test_cross_service.py`, `tests/integration/test_error_propagation.py`

**Cross-Service tests (>=5)**:
1. TextProcessor reads real .txt file end-to-end
2. TextProcessor reads real .csv file end-to-end
3. Organizer chains TextProcessor to file output on disk
4. VisionProcessor returns metadata for image file
5. Fallback chain when model init fails

**Error Propagation tests (>=5)**:
1. File read error surfaces in ProcessedFile result
2. Model timeout surfaces as failed file in batch
3. Permission denied on output dir reported gracefully
4. Missing input dir raises ValueError with clear message
5. Deep exception in parallel worker doesn't crash batch

**Acceptance**: 10 tests pass, real service instances used throughout.

### Stream C: Concurrency + Cleanup (#734)

**Files**: `tests/integration/test_concurrent_lifecycle.py`

**Tests (>=6)**:
1. Concurrent text processing with real ParallelProcessor
2. Timeout cancellation does not deadlock
3. ParallelProcessor shutdown cleans up threads
4. Mid-operation failure cleanup (partial output handling)
5. Processors cleaned up after organize()
6. Pool exhaustion under many files (50 files, 2 workers)

**Acceptance**: 6 tests pass, no flaky timing (use threading.Event where possible per #731).

### Stream D: CLI E2E + State Recovery (#735)

**Files**: `tests/integration/test_cli_end_to_end.py`, `tests/integration/test_state_recovery.py`

**CLI tests (>=3)**:
1. CLI organize --dry-run on temp dir
2. CLI organize creates output files
3. CLI verbose flag increases output

**State Recovery tests (>=3)**:
1. Undo reverses organized files
2. Corrupt history db graceful fallback
3. Interrupted transaction not committed
4. Config file corruption loads defaults

**Acceptance**: 6+ tests pass, CLI tests use typer.testing.CliRunner.

## Phase Exit Gates

### Stream A Exit — Foundation Ready
- [x] conftest.py provides all shared fixtures
- [x] 8 config-to-runtime tests pass
- [x] Fixtures importable by other stream test files

### Stream B+C Exit — Core Integration Verified
- [x] 14 cross-service + error propagation tests pass
- [x] 7 concurrency + cleanup tests pass
- [x] No test flakiness over 3 consecutive runs

### Stream D Exit — Epic Complete
- [x] 9 CLI + state recovery tests pass
- [x] All 132 integration tests run on main CI
- [x] `pytest -m integration` selects exactly the new tests
- [x] Zero production code changes required

## CI Integration

No workflow changes needed — existing CI pattern handles this:
- PRs: `pytest tests/ -m "ci"` — skips `@pytest.mark.integration`
- Main: `pytest tests/` — runs everything including `@pytest.mark.integration`

## Related Issues

- #724 (Config overrides ignored — Gap P1 symptom)
- #726 (Vision model race condition — Gap P4+P5 symptom)
- #725 (VRAM exhaustion — Gap P1+P2 symptom)
- #727 (Parallelism controls — Gap P6 symptom)
- #731 (Deterministic thread-safety tests — deferred from #730)
