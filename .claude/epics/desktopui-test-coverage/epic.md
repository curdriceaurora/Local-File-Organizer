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

Raise project test coverage from 12.24% to 90% in two phases. Phase A (P0) unblocks CI by hitting the 74% `--cov-fail-under` gate. Phase B (P1) reaches the 90% project target. The work is purely additive test files -- no production code changes (except docstrings in Task #579).

## Architecture Decisions

- **No mocking of internals**: Mock only external boundaries (HTTP calls, filesystem, subprocess). Internal code exercises real paths.
- **Framework-native test clients**: `httpx.AsyncClient` for FastAPI, `typer.testing.CliRunner` for CLI, Textual `pilot` for TUI. Keeps tests close to how the code actually runs.
- **Parallel-safe**: Each test module uses isolated temp dirs and ports. Full suite must run in < 5 minutes on CI.
- **Stubs for hardware-dependent code**: Ollama, GPU, and whisper calls use lightweight stubs since CI has no GPU.

## MECE Coverage Map

Every source module maps to exactly one task. No overlaps, no gaps.

| Source Module | Src Files | Existing Tests | Dedicated Task | Target Coverage |
|---------------|-----------|----------------|----------------|-----------------|
| `api/` | 44 | 20 | **#572** | 80% |
| `plugins/` | 27 | 11 | **#575** | 75% |
| `cli/` | 24 | 15 | **#577** | 80% |
| `web/` | 8 | 5 | **#580** | 80% |
| `services/` (all) | 71 | 86 | **#581** | 70-80% |
| `tui/` | 10 | 5 | **#573** | 90% |
| `models/` | 10 | 5 | **#574** | 90% |
| `client/` | 5 | 2 | **#574** | 90% |
| `config/` | 5 | 3 | **#574** | 90% |
| `updater/` | 7 | 5 | **#576** | 90% |
| `watcher/` | 5 | 4 | **#576** | 90% |
| `core/` | 2 | 3 | **#578** (audit) | 80% |
| `daemon/` | 5 | 5 | **#578** (audit) | 80% |
| `events/` | 15 | 13 | **#578** (audit) | 80% |
| `history/` | 7 | 7 | **#578** (audit) | 80% |
| `undo/` | 6 | 8 | **#578** (audit) | 80% |
| `utils/` | 12 | 12 | **#578** (audit) | 80% |
| `parallel/` | 13 | 14 | **#578** (audit) | 80% |
| `pipeline/` | 5 | 4 | **#578** (audit) | 80% |
| `methodologies/` | 27 | 23 | **#578** (audit) | 80% |
| `optimization/` | 12 | 13 | **#578** (audit) | 80% |
| `deploy/` | 6 | 7 | **#578** (audit) | 80% |
| `integrations/` | 7 | 4 | **#578** (audit) | 80% |
| `interfaces/` | 1 | 0 | **#578** (audit) | 80% |
| All `.py` docstrings | 314+ | N/A | **#579** | 90% interrogate |

**Legend**:
- Tasks #572-#577, #580-#581: Write new tests for under-covered modules
- Task #578: Audit + gap-fill modules with existing tests near 1:1 ratio
- Task #579: Docstring coverage across all modules (orthogonal to test coverage)

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
# Per-module coverage
pytest --cov=file_organizer.{module} --cov-report=term-missing

# Full project coverage (CI gate)
pytest --cov=file_organizer --cov-report=term-missing --cov-report=html --cov-fail-under=74

# Docstring coverage
interrogate -v src/file_organizer --fail-under 90
```

### Standard Verification Checklist (All Tasks)

Every task includes this verification checklist:

1. **Tests pass**: `pytest tests/{module}/ -v` — all green
2. **Coverage met**: `pytest --cov=file_organizer.{module} --cov-report=term-missing` — meets target
3. **Lint clean**: `ruff check tests/{module}/` — no errors
4. **No internal mocks**: Only external boundaries mocked (HTTP, GPU, filesystem)
5. **Docstrings**: Each test file has module-level docstring
6. **Isolation**: Tests use temp dirs/ports (no shared state)
7. **Performance**: No single test > 5s
8. **Regression**: `pytest --tb=short -q` — no new failures across full suite

## Tasks Created

**Phase A -- Reach 74% (P0)**
- [ ] #572 - API Router & Middleware Tests (parallel: true, XL, 40-60h)
- [ ] #575 - Plugin System & Marketplace Tests (parallel: true, L, 30-40h)
- [ ] #577 - CLI Command Tests (parallel: true, M, 20-30h)
- [ ] #580 - Web Route & HTMX Endpoint Tests (parallel: true, S, 8-12h)
- [ ] #581 - Services Layer Tests (parallel: true, XL, 50-70h)

**Phase B -- Reach 90% (P1)**
- [ ] #573 - TUI View Tests (parallel: true, M, 15-20h)
- [ ] #574 - Models, Client & Config Tests (parallel: true, M, 20-25h)
- [ ] #576 - Updater & Watcher Tests (parallel: true, M, 20-25h)
- [ ] #578 - Integration & E2E + Residual Module Audit (parallel: false, depends on Phase A, XL, 35-50h)
- [ ] #579 - Docstring Coverage via Interrogate (parallel: true, L, 20-30h)

Total tasks: 10
Parallel tasks: 9
Sequential tasks: 1 (#578 depends on Phase A)
Estimated total effort: 258-362 hours

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
| Docstrings | interrogate >= 90% | `interrogate -v src/file_organizer --fail-under 90` |
| All modules >= 80% | Per-module check | See MECE Coverage Map |

## Estimated Effort

- **Phase A**: 8-12 weeks (~73 new test modules + services audit)
- **Phase B**: 6-8 weeks (~28 new test modules + integration tests + residual audit)
- **Total**: 14-20 weeks
- **Critical path**: Tasks #572 and #581 (API + services) contribute the most coverage delta and should start first
- **Parallelizable**: All tasks within a phase are independent and can run in parallel
