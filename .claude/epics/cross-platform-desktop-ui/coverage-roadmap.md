---
name: coverage-roadmap
title: "Coverage Roadmap: 12% → 74% → 90%"
created: 2026-03-02T14:12:19Z
updated: 2026-03-02T14:12:19Z
epic: cross-platform-desktop-ui
status: open
---

# Coverage Roadmap: 12% → 74% → 90%

## Current State

- **Test coverage**: 12.24% (measured via `pytest --cov`)
- **Test files**: 237 across `tests/`
- **Python tests passing**: 70 (service facade, health, daemon)
- **Rust tests passing**: 47/47
- **CI threshold**: 74% (currently failing)
- **Project target**: 90%

## Critical Coverage Gaps

| Module | Source Files | Test Files | Approx Coverage | Priority |
|--------|-------------|------------|-----------------|----------|
| **api** (routers, middleware) | 41 | 19 | ~46% | P0 |
| **plugins** (system, marketplace) | 23 | 7 | ~30% | P0 |
| **cli** (commands) | 23 | 14 | ~61% | P1 |
| **web** (routes, helpers) | 7 | 4 | ~57% | P1 |
| **tui** (views) | 9 | 4 | ~44% | P1 |
| **services/intelligence** | 23 | 0 | 0% | P1 |
| **models** | 9 | 5 | ~56% | P2 |
| **client** | 4 | 1 | ~25% | P2 |
| **config** | 4 | 2 | ~50% | P2 |
| **updater** | 6 | 0 | 0% | P2 |
| **watcher** | 5 | 0 | 0% | P2 |

## Phase A: Reach CI Threshold (74%)

**Goal**: Unblock CI by hitting the 74% `--cov-fail-under` gate.

**Focus areas** (high-LOC modules with lowest coverage):

1. **API routers** — ~22 missing test modules
   - Route handlers, middleware, error responses
   - Mock FastAPI TestClient patterns
2. **Plugin system** — ~16 missing test modules
   - Plugin lifecycle, marketplace API, registry
3. **CLI commands** — ~9 missing test modules
   - Typer command testing with CliRunner
4. **Web route handlers** — ~3 missing test modules
   - Jinja2 template rendering, HTMX endpoints
5. **Services/intelligence** — 23 modules at 0%
   - Preference learning, pattern extraction, scoring

**Estimated effort**: ~8-12 weeks

## Phase B: Reach Project Target (90%)

**Goal**: Hit the 90% coverage threshold across all modules.

**Remaining after Phase A**:

1. **TUI views** — ~5 missing test modules (Textual widget testing)
2. **Models** — ~4 missing test modules (model manager, registry)
3. **Client library** — ~3 missing test modules
4. **Updater** — 6 modules at 0% (checker, installer, manager)
5. **Watcher** — 5 modules at 0% (monitor, handler, queue)
6. **Integration tests** — End-to-end workflows
7. **Docstring coverage** via `interrogate` (configured at 90% in pyproject.toml)

**Estimated effort**: ~6-8 weeks

## Implementation Strategy

### Test Patterns to Follow

- Use `pytest` with `pytest-asyncio` for async endpoints
- Use `httpx.AsyncClient` for FastAPI testing
- Use `typer.testing.CliRunner` for CLI tests
- Use Textual's `pilot` for TUI tests
- Avoid mocking where possible; use real services

### Pre-Commit Coverage Gate

The `pre-commit-validation.sh` script should enforce:
```bash
pytest --cov=file_organizer --cov-fail-under=74 --tb=short
```

### Coverage Tracking

Track coverage per-module over time:
```bash
pytest --cov=file_organizer --cov-report=term-missing --cov-report=html
```

## Timeline

| Phase | Target | Status | Estimated |
|-------|--------|--------|-----------|
| Current | 12.24% | Measured | — |
| Phase A | 74% | Not started | 8-12 weeks |
| Phase B | 90% | Not started | 6-8 weeks |
| **Total** | **90%** | — | **14-20 weeks** |

## Notes

- The 70 passing Python tests cover the most critical Desktop UI integration points (service facade, health endpoint, daemon managers)
- 47 Rust unit tests all pass covering sidecar, tray, updater, daemon managers, notifications
- Coverage remediation should be tracked as a separate epic with its own tasks
