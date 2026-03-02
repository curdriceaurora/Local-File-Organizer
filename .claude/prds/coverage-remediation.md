---
name: coverage-remediation
description: Increase test and documentation coverage from 12% to 90% across all Python modules
status: backlog
created: 2026-03-02T14:25:52Z
updated: 2026-03-02T14:25:52Z
---

# PRD: Coverage Remediation — 12% to 90%

## Problem Statement

The project has 12.24% test coverage measured via `pytest --cov`. The CI threshold is set at 74% (`--cov-fail-under=74`), which is currently failing. The project target is 90%. Additionally, docstring coverage via `interrogate` is configured at 90% in `pyproject.toml` and is enforced in CI (Python 3.12 job) via `interrogate -v src/ --fail-under 90`.

With 314 Python modules and 237 test files, coverage is spread unevenly — some modules have 0% coverage while others are well-tested. A systematic approach is needed to reach 90%.

## Goals

1. Reach 74% test coverage to unblock CI (`--cov-fail-under` gate)
2. Reach 90% test coverage as the project target
3. Reach 90% docstring coverage via `interrogate`
4. No regressions — all existing 70 passing Python tests continue to pass
5. Coverage gates enforced in pre-commit validation

## Non-Goals

- Rust test coverage (already at 47/47 with good coverage)
- Desktop E2E testing (separate epic)
- Production builds (separate epic)
- New feature development

## Current State

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

## Technical Approach

### Phase A: Reach CI Threshold — 74% (8-12 weeks)

Focus on high-LOC modules with lowest coverage for maximum impact.

#### Sprint A1: API Routers (3-4 weeks)

- ~22 missing test modules for API route handlers
- Use `httpx.AsyncClient` with FastAPI `TestClient`
- Test all route handlers, middleware, error responses
- Cover authentication, CORS, rate limiting middleware

#### Sprint A2: Plugin System (2-3 weeks)

- ~16 missing test modules
- Plugin lifecycle (install, enable, disable, uninstall)
- Marketplace API integration tests
- Plugin registry and discovery
- Plugin sandbox and security boundaries

#### Sprint A3: CLI Commands (1-2 weeks)

- ~9 missing test modules
- Use `typer.testing.CliRunner` for command testing
- Cover all subcommands: organize, dedupe, daemon, marketplace, copilot
- Test CLI output formatting and error messages

#### Sprint A4: Web & Services (1-2 weeks)

- ~3 missing web test modules (Jinja2 rendering, HTMX endpoints)
- 23 intelligence service modules at 0% coverage
- Preference learning, pattern extraction, scoring algorithms

### Phase B: Reach Project Target — 90% (6-8 weeks)

#### Sprint B1: TUI Views (1-2 weeks)

- ~5 missing test modules
- Use Textual's `pilot` testing framework
- Test all views: dashboard, file browser, settings, logs

#### Sprint B2: Models & Client (1-2 weeks)

- ~4 missing model test modules (model manager, registry)
- ~3 missing client test modules
- Model lifecycle, configuration, error handling

#### Sprint B3: Updater & Watcher (1-2 weeks)

- 6 updater modules at 0% (checker, installer, manager)
- 5 watcher modules at 0% (monitor, handler, queue)
- File system watching, auto-update flow

#### Sprint B4: Integration & Docstrings (2 weeks)

- End-to-end workflow tests
- Cross-module integration scenarios
- Docstring coverage via `interrogate` to 90%
- Coverage report generation and tracking

## Test Patterns

- Use `pytest` with `pytest-asyncio` for async endpoints
- Use `httpx.AsyncClient` for FastAPI testing
- Use `typer.testing.CliRunner` for CLI tests
- Use Textual's `pilot` for TUI tests
- Prefer real services over mocks where feasible
- Use `pytest-cov` for coverage measurement

## Pre-Commit Enforcement

Add to `pre-commit-validation.sh`:

```bash
pytest --cov=file_organizer --cov-fail-under=74 --tb=short -q
```

After Phase B:

```bash
pytest --cov=file_organizer --cov-fail-under=90 --tb=short -q
interrogate -v src/file_organizer/ --fail-under 90
```

## Success Criteria

- [ ] `pytest --cov-fail-under=74` passes (Phase A complete)
- [ ] `pytest --cov-fail-under=90` passes (Phase B complete)
- [ ] `interrogate --fail-under 90` passes (docstring coverage)
- [ ] All 70+ existing tests continue to pass
- [ ] Coverage gates enforced in pre-commit and CI
- [ ] Per-module coverage tracked and reported

## Estimated Effort

| Phase | Target | Estimated |
|-------|--------|-----------|
| Phase A | 74% | 8-12 weeks |
| Phase B | 90% | 6-8 weeks |
| **Total** | **90%** | **14-20 weeks** |

## Dependencies

- No external dependencies
- Can start immediately
- Phases can run in parallel with other epics

## Risks

- Some modules may be difficult to test without significant refactoring
- Intelligence services (23 modules at 0%) may require complex test fixtures
- Coverage measurement accuracy depends on test isolation
