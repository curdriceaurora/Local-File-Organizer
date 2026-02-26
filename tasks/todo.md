# Issue #462: Coverage Improvement Plan (Target: 90%)

## Current State Assessment

| Metric | Issue Claims | Verified |
|--------|-------------|----------|
| Test coverage | 71% | ~71% (28% at import-time; full run needed to confirm) |
| Coverage threshold | 45% | **45%** (`--cov-fail-under=45` in pyproject.toml + CI) |
| Docstring coverage | 83.7% | Unverified (interrogate not configured at all) |
| Failing tests | 57 | **1** (plugin timeout in `test_plugin_examples.py`) |
| Total tests | — | **4,197 collected** |
| Skipped tests | — | ~30+ (16 Phase 3 / optional deps) |

**Key Discrepancy**: The issue claims 57 failing tests, but a full test run shows only
1 failure (a 30s timeout in `test_example_plugins_load_and_lifecycle`). The 57 failures
may have been from a prior state or different environment.

---

## Execution Plan

### Phase 1: Fix Existing Failing Tests
**Effort: Small | Risk: Low**

- [x] ~~Verify TUI async test issues~~ → No async failures found in current run
- [x] ~~Verify test_analyze_api.py errors~~ → Tests use flexible assertions, no failures
- [x] ~~Verify test_middleware.py errors~~ → Tests pass (errors caught by design)
- [ ] **1.1** Fix `test_example_plugins_load_and_lifecycle` timeout
  - File: `tests/plugins/test_plugin_examples.py:39`
  - Root cause: `executor.call("on_load")` hangs on `self._proc.stdout.readline()`
  - Fix: Add timeout to subprocess read in `src/file_organizer/plugins/executor.py:353`
    or mark test with `@pytest.mark.timeout(60)` / restructure to avoid blocking read
- [ ] **1.2** Run full test suite, confirm ≤0 failures after fix

### Phase 2: Enforce 90% Coverage Thresholds
**Effort: Small | Risk: Low**

- [ ] **2.1** Update `pyproject.toml` pytest coverage threshold
  - Change `--cov-fail-under=45` → `--cov-fail-under=90` in `[tool.pytest.ini_options]` addopts
- [ ] **2.2** Add interrogate configuration to `pyproject.toml`
  - Add `[tool.interrogate]` section with `fail-under = 90`
  - Configure: `ignore-init-method = true`, `ignore-init-module = true`
  - Exclude: `tests/`, `setup.py`, `docs/`
  - Install interrogate as dev dependency
- [ ] **2.3** Update `.github/workflows/ci.yml`
  - Change `--cov-fail-under=45` → `--cov-fail-under=90`
  - Add interrogate check step: `pipx run interrogate -v src/ --fail-under 90`
- [ ] **2.4** Update `.github/workflows/ci-full.yml`
  - Add coverage collection and enforcement to full matrix
  - Add interrogate check step
- [ ] **2.5** Verify both CI workflows pass locally with new thresholds
  - **NOTE**: This step will FAIL until Phases 3+4 are complete; commit config
    changes but expect CI to gate on actual coverage improvements

### Phase 3: Increase Test Coverage (71% → 90%)
**Effort: Large | Risk: Medium**

Priority ordered by coverage gap × file size (biggest impact first):

#### 3A. Intelligence Services
- [ ] **3A.1** Create `tests/services/intelligence/test_profile_migrator.py`
  - Source: `profile_migrator.py` (393 LOC, 13% coverage)
  - Test: version detection, migration paths, backup/rollback, edge cases
  - Target: ≥90% coverage for this module
- [ ] **3A.2** Create `tests/services/intelligence/test_preference_tracker.py`
  - Source: `preference_tracker.py` (610 LOC, 31% coverage)
  - Test: correction tracking, preference learning, decay logic, persistence
  - Target: ≥90% coverage for this module

#### 3B. Utilities
- [ ] **3B.1** Expand `tests/utils/test_text_processing.py`
  - Source: `text_processing.py` (366 LOC, 16% coverage)
  - Test: NLTK paths, tokenization, cleaning, keyword extraction, fallbacks
  - Target: ≥90% coverage for this module
- [ ] **3B.2** Expand `tests/utils/test_file_readers.py`
  - Source: `file_readers.py` (1,163 LOC, 46% coverage)
  - Test: Each reader function, format detection, error handling, edge cases
  - Focus on untested readers (mock optional deps as needed)
  - Target: ≥90% coverage for this module

#### 3C. TUI Components
- [ ] **3C.1** Expand `tests/test_tui_app.py`
  - Source: `app.py` (259 LOC, 40% coverage)
  - Test: sidebar actions, status bar updates, compose/mount lifecycle
  - Target: ≥90% coverage for this module
- [ ] **3C.2** Create `tests/test_tui_copilot_view.py`
  - Source: `copilot_view.py` (189 LOC, 37% coverage)
  - Test: chat panel rendering, message log, input handling
  - Target: ≥90% coverage for this module

#### 3D. Web Routes (biggest LOC gap)
- [ ] **3D.1** Create `tests/web/test_files_routes.py`
  - Source: `files_routes.py` (638 LOC, ~11% coverage)
  - Test: browse, preview, upload, thumbnails, HTMX partials
  - Target: ≥90% coverage
- [ ] **3D.2** Create `tests/web/test_organize_routes.py`
  - Source: `organize_routes.py` (866 LOC, ~20% coverage)
  - Test: dashboard, background jobs, reports, streaming
  - Target: ≥90% coverage
- [ ] **3D.3** Create `tests/web/test_settings_routes.py` (expand existing)
  - Source: `settings_routes.py` (630 LOC)
  - Existing: `tests/test_web_settings.py` (435 LOC)
  - Gap analysis: identify uncovered paths, add tests
  - Target: ≥90% coverage
- [ ] **3D.4** Create `tests/web/test_profile_routes.py`
  - Source: `profile_routes.py` (1,211 LOC, ~20% coverage)
  - Test: auth, profiles, API keys, collaboration, HTMX
  - **Largest single file** — may need 500+ LOC of tests
  - Target: ≥90% coverage
- [ ] **3D.5** Expand `tests/web/test_marketplace_routes.py`
  - Source: `marketplace_routes.py` (193 LOC)
  - Test: plugin browsing, search, install triggers
  - Target: ≥90% coverage

#### 3E. Additional Modules (if needed to reach 90% overall)
- [ ] **3E.1** Run `pytest --cov=file_organizer --cov-report=term-missing` after 3A-3D
- [ ] **3E.2** Identify remaining modules below 90% and add targeted tests
- [ ] **3E.3** Focus on modules with highest LOC × coverage-gap product

### Phase 4: Increase Docstring Coverage (83.7% → 90%)
**Effort: Medium | Risk: Low**

- [ ] **4.1** Install interrogate and run baseline: `pipx run interrogate -v src/`
- [ ] **4.2** Add docstrings to Web Routes (lowest coverage):
  - `web/organize_routes.py` (3% docstring coverage)
  - `web/profile_routes.py` (6%)
  - `web/settings_routes.py` (7%)
  - `web/files_routes.py` (8%)
  - `web/marketplace_routes.py` (12%)
- [ ] **4.3** Re-run interrogate to identify remaining under-documented modules
- [ ] **4.4** Add docstrings to any remaining modules below 90%
- [ ] **4.5** Verify `interrogate -v src/ --fail-under 90` passes

### Phase 5: Final Verification
**Effort: Small | Risk: Low**

- [ ] **5.1** Run full test suite: `pytest --cov=file_organizer --cov-report=term-missing`
- [ ] **5.2** Verify coverage ≥ 90%
- [ ] **5.3** Run `interrogate -v src/ --fail-under 90` and verify pass
- [ ] **5.4** Run CI workflows locally (or push to branch and verify)
- [ ] **5.5** Create summary comment on issue #462 with final metrics

---

## Parallelization Strategy

These work streams can run in parallel:

| Stream | Tasks | Dependencies |
|--------|-------|-------------|
| **A: Config** | 2.1–2.5 | None |
| **B: Intelligence tests** | 3A.1–3A.2 | None |
| **C: Utility tests** | 3B.1–3B.2 | None |
| **D: TUI tests** | 3C.1–3C.2 | None |
| **E: Web route tests** | 3D.1–3D.5 | None |
| **F: Docstrings** | 4.1–4.5 | None |
| **G: Verification** | 5.1–5.5 | All above |

Streams B–F are independent file-level work and can all proceed simultaneously.

---

## Estimated Effort

| Phase | Tasks | Est. New LOC | Complexity |
|-------|-------|-------------|------------|
| Phase 1 | 2 | ~20 | Low |
| Phase 2 | 5 | ~50 | Low |
| Phase 3 | 14 | ~3,000–5,000 | High |
| Phase 4 | 5 | ~500–800 | Medium |
| Phase 5 | 5 | 0 | Low |
| **Total** | **31** | **~3,600–5,900** | **High** |

Phase 3 dominates the effort. The web routes alone (3D) represent ~3,500 LOC
of source code needing ~2,000+ LOC of new tests.

---

## Risk Mitigation

1. **Coverage measurement discrepancy**: Run a full `pytest` (not `--co`) to get
   accurate baseline before starting work
2. **Interrogate not installed**: Install and baseline before setting threshold
3. **Optional dependency mocking**: Many file readers depend on optional libs;
   mock unavailable ones to avoid false failures
4. **Async test fragility**: Use `pytest-asyncio` auto mode and ensure proper
   event loop fixtures for TUI tests
5. **CI enforcement timing**: Commit threshold changes AFTER coverage improvements
   land, or gate behind a feature flag / separate PR
