---
name: desktopui-test-coverage
status: backlog
created: 2026-03-02T20:49:25Z
updated: 2026-03-02T21:08:31Z
progress: 0%
prd: .claude/prds/desktopui-test-coverage.md
github: https://github.com/curdriceaurora/Local-File-Organizer/issues/571
---

# Epic: Desktop UI Test Coverage (12% to 90%)

## Overview

Raise project test coverage from 12.24% to 90% in two phases. Phase A (P0) unblocks CI by hitting the 74% `--cov-fail-under` gate. Phase B (P1) reaches the 90% project target. The work is purely additive test files -- no production code changes.

## Architecture Decisions

- **No mocking of internals**: Mock only external boundaries (HTTP calls, filesystem, subprocess). Internal code exercises real paths.
- **Framework-native test clients**: `httpx.AsyncClient` for FastAPI, `typer.testing.CliRunner` for CLI, Textual `pilot` for TUI. Keeps tests close to how the code actually runs.
- **Parallel-safe**: Each test module uses isolated temp dirs and ports. Full suite must run in < 5 minutes on CI.
- **Stubs for hardware-dependent code**: Ollama, GPU, and whisper calls use lightweight stubs since CI has no GPU.

## Technical Approach

The work is organized by module area. Each task adds test files for one module group, following existing patterns in `tests/`.

### Test Pattern Summary

| Module Type | Client/Harness | Pattern |
|-------------|----------------|---------|
| API routers | `httpx.AsyncClient` + `pytest-asyncio` | Mount app, assert status + JSON |
| CLI commands | `typer.testing.CliRunner` | Invoke command, assert exit code + output |
| Web routes | `httpx.AsyncClient` | Test Jinja2 rendering + HTMX endpoints |
| TUI views | Textual `pilot` | `run_test()` context, press keys, assert DOM |
| Services | Direct instantiation | Call methods, assert return values |
| Plugins | Registry + lifecycle | Load/unload/execute plugin, assert state |

### Coverage Measurement

```bash
pytest --cov=file_organizer --cov-report=term-missing --cov-report=html --cov-fail-under=74
```

## Task Breakdown Preview

**Phase A -- Reach 74% (P0, ~8-12 weeks)**

- [ ] Task 1: API router & middleware tests (~22 test modules, ~46% -> 80%)
- [ ] Task 2: Plugin system & marketplace tests (~16 test modules, ~30% -> 75%)
- [ ] Task 3: CLI command tests (~9 test modules, ~61% -> 80%)
- [ ] Task 4: Web route & HTMX endpoint tests (~3 test modules, ~57% -> 80%)
- [ ] Task 5: Services/intelligence tests (23 test modules, 0% -> 70%)

**Phase B -- Reach 90% (P1, ~6-8 weeks)**

- [ ] Task 6: TUI view tests (~5 test modules, ~44% -> 90%)
- [ ] Task 7: Models, client, config tests (~9 test modules, 25-56% -> 90%)
- [ ] Task 8: Updater & watcher tests (11 test modules, 0% -> 90%)
- [ ] Task 9: Integration & end-to-end workflow tests
- [ ] Task 10: Docstring coverage via interrogate (target 90%)

## Dependencies

- **Merged**: Desktop UI code on main (PR #562, #564)
- **Dev deps**: `pytest`, `pytest-cov`, `pytest-asyncio`, `httpx` (already in pyproject.toml)
- **Dev deps**: `interrogate` for docstring coverage (configured at 90% in pyproject.toml)
- **Blocker**: None -- all tasks can start immediately

## Success Criteria (Technical)

| Gate | Metric | Command |
|------|--------|---------|
| CI unblocked | Coverage >= 74% | `pytest --cov-fail-under=74` |
| Project target | Coverage >= 90% | `pytest --cov-fail-under=90` |
| No slowdown | Suite < 5 min | `time pytest` |
| Docstrings | interrogate >= 90% | `interrogate -v src/file_organizer` |

## Estimated Effort

- **Phase A**: 8-12 weeks (~73 new test modules)
- **Phase B**: 6-8 weeks (~28 new test modules + integration tests)
- **Total**: 14-20 weeks
- **Critical path**: Tasks 1 and 2 (API + plugins) contribute the most coverage delta and should start first
- **Parallelizable**: All tasks within a phase are independent and can run in parallel

## Tasks Created

**Phase A -- Reach 74% (P0)**
- [ ] #572 - API Router & Middleware Tests (parallel: true, XL, 40-60h)
- [ ] #575 - Plugin System & Marketplace Tests (parallel: true, L, 30-40h)
- [ ] #577 - CLI Command Tests (parallel: true, M, 20-30h)
- [ ] #580 - Web Route & HTMX Endpoint Tests (parallel: true, S, 8-12h)
- [ ] #581 - Services Intelligence Tests (parallel: true, XL, 40-50h)

**Phase B -- Reach 90% (P1)**
- [ ] #573 - TUI View Tests (parallel: true, M, 15-20h)
- [ ] #574 - Models, Client & Config Tests (parallel: true, M, 20-25h)
- [ ] #576 - Updater & Watcher Tests (parallel: true, M, 20-25h)
- [ ] #578 - Integration & E2E Workflow Tests (parallel: false, depends on Phase A, L, 25-35h)
- [ ] #579 - Docstring Coverage via Interrogate (parallel: true, L, 20-30h)

Total tasks: 10
Parallel tasks: 9
Sequential tasks: 1 (#578 depends on Phase A)
Estimated total effort: 238-327 hours
