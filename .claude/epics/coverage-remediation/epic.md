---
name: coverage-remediation
status: backlog
created: 2026-03-02T14:30:36Z
updated: 2026-03-02T14:30:36Z
progress: 0%
prd: .claude/prds/coverage-remediation.md
github: Will be updated when synced to GitHub
---

# Epic: Coverage Remediation — 12% to 90%

## Overview

Systematically increase Python test coverage from 12.24% to 90% and docstring coverage to 90%. The CI gate at 74% (`--cov-fail-under`) is currently failing. This epic is split into Phase A (reach 74% to unblock CI) and Phase B (reach 90% project target). Modules are prioritized by LOC and current coverage gap.

## Architecture Decisions

- **No mocking where avoidable** — use real services with test fixtures for accurate coverage
- **`pytest-cov`** for measurement, `interrogate` for docstrings — both already configured in `pyproject.toml`
- **Module-by-module approach** — focus on one module at a time, merge incrementally
- **Test pattern consistency** — follow existing test patterns (`httpx.AsyncClient` for API, `CliRunner` for CLI, Textual `pilot` for TUI)
- **Coverage gate in pre-commit** — add `--cov-fail-under` to `pre-commit-validation.sh` to prevent regressions

## Technical Approach

### Phase A: Reach 74% CI Threshold

Focus on highest-LOC, lowest-coverage modules for maximum impact:

1. **API routers & middleware** (41 source, 19 test files, ~46% coverage)
   - ~22 missing test modules for route handlers
   - FastAPI `TestClient` / `httpx.AsyncClient` patterns
   - Middleware, error responses, authentication

2. **Plugin system** (23 source, 7 test files, ~30% coverage)
   - ~16 missing test modules
   - Plugin lifecycle, marketplace, registry, sandbox

3. **CLI commands** (23 source, 14 test files, ~61% coverage)
   - ~9 missing test modules
   - `typer.testing.CliRunner` patterns

4. **Services/intelligence** (23 source, 0 test files, 0% coverage)
   - Preference learning, pattern extraction, scoring
   - Complex test fixtures needed

5. **Web routes** (7 source, 4 test files, ~57% coverage)
   - ~3 missing test modules
   - Jinja2 rendering, HTMX endpoints

### Phase B: Reach 90% Project Target

6. **TUI views** (9 source, 4 test files, ~44% coverage)
   - Textual `pilot` framework for widget testing

7. **Models** (9 source, 5 test files, ~56% coverage)
   - Model manager, registry, lifecycle

8. **Client + Config** (8 source, 3 test files, ~38% coverage)
   - Client library, configuration management

9. **Updater + Watcher** (11 source, 0 test files, 0% coverage)
   - Self-update system, file system watching

10. **Docstring coverage** via `interrogate` to 90%
    - Add missing docstrings across all public APIs

## Task Breakdown Preview

- [ ] Task 1: API routers and middleware tests (~22 test modules)
- [ ] Task 2: Plugin system tests (~16 test modules)
- [ ] Task 3: CLI command tests (~9 test modules)
- [ ] Task 4: Services/intelligence tests (23 modules from 0%)
- [ ] Task 5: Web route handler tests (~3 test modules)
- [ ] Task 6: TUI, models, client, config tests (~16 test modules)
- [ ] Task 7: Updater and watcher tests (11 modules from 0%)
- [ ] Task 8: Docstring coverage to 90% via interrogate
- [ ] Task 9: Pre-commit coverage gate enforcement
- [ ] Task 10: Final coverage verification and CI green

## Dependencies

- No external dependencies — all tools already installed
- Existing 70 passing tests must not regress
- Existing 47 Rust tests are out of scope (already well-covered)

## Success Criteria (Technical)

- `pytest --cov-fail-under=74` passes (Phase A milestone)
- `pytest --cov-fail-under=90` passes (Phase B milestone)
- `interrogate --fail-under 90 src/file_organizer/` passes
- All 70+ existing Python tests continue to pass
- Coverage gate enforced in `pre-commit-validation.sh` and CI
- Per-module coverage report generated (`--cov-report=html`)

## Estimated Effort

| Phase | Target | Modules | Est. Effort |
|-------|--------|---------|-------------|
| Phase A | 74% | api, plugins, cli, intelligence, web | 8-12 weeks |
| Phase B | 90% | tui, models, client, updater, watcher, docstrings | 6-8 weeks |
| **Total** | **90%** | **All** | **14-20 weeks** |

## Notes

- Phase A is the critical path — unblocks CI
- Tasks 1-5 (Phase A) can be parallelized across developers
- The coverage roadmap document at `.claude/epics/cross-platform-desktop-ui/coverage-roadmap.md` has additional detail
