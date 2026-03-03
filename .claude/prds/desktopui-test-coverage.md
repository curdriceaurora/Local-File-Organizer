---
name: desktopui-test-coverage
description: Raise project test coverage from 12% to 90% with focus on Desktop UI integration and all under-tested modules
status: in-progress
created: 2026-03-02T20:48:20Z
---

# PRD: desktopui-test-coverage

## Executive Summary

The Desktop UI epic (PR #562, #564) added ~17,000 lines across 330 files, bringing project test coverage down to 12.24%. The CI gate requires 74% and the project target is 90%. This PRD defines a phased approach to close the gap: Phase A reaches the CI threshold (74%), Phase B reaches the project target (90%).

## Problem Statement

The CI pipeline is currently failing on the `--cov-fail-under=74` gate. The Desktop UI implementation added significant code across service facades, daemon managers, API hardening, and Tauri sidecar integration. While the new code has 70 Python tests and 47 Rust tests, the overall project coverage dropped because many pre-existing modules remain under-tested.

This blocks all future PRs from merging until coverage is restored.

## User Stories

### US-1: Developer merging PRs
**As a** developer submitting a PR, **I want** CI coverage checks to pass, **so that** my PR can be merged without manual overrides.
- **Acceptance**: `pytest --cov=file_organizer --cov-fail-under=74` exits 0

### US-2: Maintainer ensuring quality
**As a** project maintainer, **I want** 90% test coverage across all modules, **so that** regressions are caught before release.
- **Acceptance**: Coverage report shows >= 90% across all top-level packages

### US-3: Contributor understanding test patterns
**As a** new contributor, **I want** consistent test patterns per module type, **so that** I can write tests that match project conventions.
- **Acceptance**: Each module type (API, CLI, TUI, services) has a documented test pattern with examples

## Requirements

### Functional Requirements

#### Phase A: Reach CI Threshold (74%)

| ID | Module | Current | Target | Gap | Priority |
|----|--------|---------|--------|-----|----------|
| FA-1 | api (routers, middleware) | ~46% | 80% | ~22 test modules | P0 |
| FA-2 | plugins (system, marketplace) | ~30% | 75% | ~16 test modules | P0 |
| FA-3 | cli (commands) | ~61% | 80% | ~9 test modules | P1 |
| FA-4 | web (routes, helpers) | ~57% | 80% | ~3 test modules | P1 |
| FA-5 | services/intelligence | 0% | 70% | 23 test modules | P1 |

#### Phase B: Reach Project Target (90%)

| ID | Module | Current | Target | Gap | Priority |
|----|--------|---------|--------|-----|----------|
| FB-1 | tui (views) | ~44% | 90% | ~5 test modules | P2 |
| FB-2 | models | ~56% | 90% | ~4 test modules | P2 |
| FB-3 | client | ~25% | 90% | ~3 test modules | P2 |
| FB-4 | config | ~50% | 90% | ~2 test modules | P2 |
| FB-5 | updater | 0% | 90% | 6 test modules | P2 |
| FB-6 | watcher | 0% | 90% | 5 test modules | P2 |
| FB-7 | Integration tests | N/A | N/A | End-to-end workflows | P2 |

### Non-Functional Requirements

- **NF-1**: All tests must run without external services (Ollama, GPU) unless marked `@pytest.mark.integration`
- **NF-2**: Full test suite must complete in under 5 minutes on CI
- **NF-3**: No mocking of internal code; mock only external boundaries (HTTP, filesystem, subprocess)
- **NF-4**: Test patterns must use project conventions: `pytest`, `pytest-asyncio`, `httpx.AsyncClient`, `typer.testing.CliRunner`, Textual `pilot`
- **NF-5**: Coverage reports generated in both terminal and HTML formats

## Success Criteria

| Metric | Current | Phase A Target | Phase B Target |
|--------|---------|----------------|----------------|
| Overall coverage | 12.24% | >= 74% | >= 90% |
| CI gate | Failing | Passing | Passing |
| Test count | 237 files | +73 files | +28 files |
| Test runtime | N/A | < 5 min | < 5 min |
| Docstring coverage (interrogate) | Unknown | >= 70% | >= 90% |

## Constraints & Assumptions

- **Constraint**: No changes to production code solely to improve coverage; tests must exercise existing behavior
- **Constraint**: Tests for models (Ollama, whisper) must use stubs since CI has no GPU
- **Assumption**: The 237 existing test files are valid and passing on main
- **Assumption**: Coverage measurement uses `pytest-cov` with the `file_organizer` package
- **Timeline**: Phase A: 8-12 weeks, Phase B: 6-8 weeks

## Out of Scope

- Rust/Tauri test coverage (handled separately by desktop-e2e-testing epic)
- Performance benchmarking and load testing
- Mutation testing
- Code refactoring to improve testability (separate epic if needed)
- Desktop E2E testing with `tauri-driver` (separate epic)

## Dependencies

- **Internal**: All Desktop UI code merged to main (PR #562, #564) -- DONE
- **Internal**: `pytest`, `pytest-cov`, `pytest-asyncio` in dev dependencies
- **Internal**: `httpx` for async API testing
- **Internal**: Textual test harness for TUI tests
- **Tool**: `interrogate` for docstring coverage (configured in pyproject.toml at 90%)

## Test Pattern Reference

### API Tests
```python
from httpx import AsyncClient
from file_organizer.api.app import create_app

async def test_endpoint():
    app = create_app()
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/api/v1/health")
        assert response.status_code == 200
```

### CLI Tests
```python
from typer.testing import CliRunner
from file_organizer.cli.main import app

def test_command():
    runner = CliRunner()
    result = runner.invoke(app, ["organize", "--dry-run"])
    assert result.exit_code == 0
```

### TUI Tests
```python
from file_organizer.tui.app import FileOrganizerApp

async def test_tui_view():
    async with FileOrganizerApp().run_test() as pilot:
        await pilot.press("q")
```
