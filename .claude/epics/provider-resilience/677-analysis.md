---
issue: 677
title: "feat: verifiable graceful degradation when Ollama is unavailable"
analyzed: 2026-03-09T06:30:00Z
estimated_hours: 10
parallelization_factor: 1.0
---

# Parallel Work Analysis: Issue #677

## Overview

Single coherent pipeline change — wrap Ollama model initialization in try/except,
add extension-based fallback routing for text/image, extend health response,
and write a `no_ollama` test suite to prove it all works.

## Work Streams

### Stream A: Pipeline Fallback (Core Change)
**Scope**: Catch `ConnectionError` at model init; route text/image to extension-based fallback
**Files**:
- `src/file_organizer/core/organizer.py` — wrap TextProcessor/VisionProcessor init in try/except
- `src/file_organizer/pipeline/router.py` — ensure extension fallback paths cover all text/image types
**Agent Type**: general-purpose
**Can Start**: immediately
**Estimated Hours**: 4
**Dependencies**: none

### Stream B: Health Response Extension
**Scope**: Extend degraded status to enumerate which file types are affected
**Files**:
- `src/file_organizer/api/service_facade.py` — add `degraded_types` list to health response
**Agent Type**: general-purpose
**Can Start**: immediately (independent of Stream A)
**Estimated Hours**: 2
**Dependencies**: none

### Stream C: Test Suite (`no_ollama` marker)
**Scope**: Integration tests proving fallback behavior end-to-end
**Files**:
- `tests/integration/test_fallback_no_ollama.py` — new file, `@pytest.mark.no_ollama`
- `pyproject.toml` — register `no_ollama` marker
**Agent Type**: general-purpose
**Can Start**: after Stream A (tests exercise the fallback path)
**Estimated Hours**: 4
**Dependencies**: Stream A

## Coordination Points

### Shared Files
- None — streams touch distinct files

### Sequential Requirements
1. Stream A (pipeline change) must complete before Stream C (tests validate the change)
2. Stream B is fully independent — can merge separately

## Conflict Risk Assessment
- **Low Risk** — clean file separation, Stream B is self-contained

## Parallelization Strategy

**Recommended**: Start A & B in parallel. Start C when A is done.
- A + B simultaneously: ~4h wall time
- Then C: ~4h wall time
- **Total wall time**: ~8h vs 10h sequential

## Notes

- Do NOT change behavior when Ollama IS available — pure additive fallback
- Extension fallback for text should sort to: Documents/, Spreadsheets/, Presentations/, PDFs/, etc.
- Extension fallback for images should sort to: Images/{Year}/ using file mtime if no EXIF
- The `no_ollama` pytest marker should be added to `pyproject.toml` markers list
- Smoke test: `pytest -m no_ollama -x -q` must run in < 30s (no actual Ollama calls)
