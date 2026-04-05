---
name: desktop-e2e-testing
description: End-to-end UI testing for the pywebview desktop application via Playwright
status: in-progress
created: 2026-03-02T14:25:52Z
updated: 2026-04-05T00:00:00Z
---

# PRD: Desktop E2E UI Testing (pywebview + Playwright)

## Problem Statement

The desktop app consolidated on pywebview in Alpha 3. The Python side of the
`DesktopAPI` bridge has full unit-test coverage, but the JavaScript contract —
that `window.pywebview.api.<method>()` calls actually update the DOM — has no
automated test coverage. The Playwright smoke suite has 14 basic page-load
tests with zero desktop-specific coverage.

## Goals

1. E2E tests covering the `window.pywebview.api` bridge contract (JS → mock → DOM)
2. E2E tests covering the 4-step setup wizard user flow
3. E2E tests verifying desktop-mode visibility gating (`[data-desktop-only]`)
4. Infrastructure: reusable `pywebview_mock` Playwright fixture

## Non-Goals

- Testing the actual pywebview native window (no headless pywebview mode exists)
- Cross-platform CI matrix for native GUI (handled by unit tests)
- Performance benchmarking

## Success Criteria

- [x] 18+ E2E scenarios across 3 test files
- [x] All 4 bridge methods covered in contract tests
- [x] 4-step wizard flow covered (step rendering, navigation, browse integration)
- [x] Desktop-mode visibility gating verified (with/without mock)
- [x] Zero Tauri/sidecar/system-tray references
- [x] Suite runtime < 5 min
- [x] `pywebview_mock` fixture reusable across all three test files

## Technical Approach

### Strategy

pywebview has no headless mode. Instead of launching a real native window,
we use Playwright's `page.add_init_script()` to inject a controllable
`window.pywebview.api` mock into the real FastAPI server's web UI. This lets
us test the full JS → mock → DOM update chain against a live server without
any native window.

### Fixture: `pywebview_mock` (function-scoped)

Calls `page.add_init_script()` before any navigation. The script sets:

```javascript
window.__mockPyw = {
  browse_directory_result: "/mock/dir",
  browse_file_result:      "/mock/file.json",
  save_file_result:        "/mock/save/dest.json",
  open_path_result:        true,
  open_path_calls:         [],
};
window.pywebview = {
  api: {
    browse_directory: () => Promise.resolve(window.__mockPyw.browse_directory_result ?? ""),
    browse_file:      (ft) => Promise.resolve(window.__mockPyw.browse_file_result ?? ""),
    save_file:        (n, ft) => Promise.resolve(window.__mockPyw.save_file_result ?? ""),
    open_path:        (p) => {
      window.__mockPyw.open_path_calls.push(p);
      return Promise.resolve(window.__mockPyw.open_path_result ?? true);
    },
  }
};
```

Returns a `PywebviewMockHandle` with helpers to mutate mock state and read
recorded calls from the page.

### Phase 1: Fixture infrastructure
File: `tests/playwright/conftest.py` (additions)

### Phase 2: Bridge contract tests
File: `tests/playwright/test_desktop_api_contract.py` (7 tests)

### Phase 3: Wizard flow tests
File: `tests/playwright/test_setup_wizard_flow.py` (7 tests)

### Phase 4: File browser desktop-mode tests
File: `tests/playwright/test_file_browser_desktop.py` (4 tests)

## Running

```bash
playwright install chromium   # once per machine

# All desktop E2E tests
pytest tests/playwright/test_desktop_api_contract.py \
       tests/playwright/test_setup_wizard_flow.py \
       tests/playwright/test_file_browser_desktop.py \
       --browser chromium --override-ini='addopts=' -v

# Full Playwright suite
pytest tests/playwright/ --browser chromium --override-ini='addopts='
```

## Marker Strategy

Tests use `@pytest.mark.e2e` and `@pytest.mark.playwright` (existing markers).
Collection is excluded by default via `collect_ignore_glob = ["playwright/**"]`
in `conftest.py`; no CI gate impact.

## Coverage Impact

`tests/playwright/` is excluded from default coverage collection.
Zero gate impact on the 95% code-coverage threshold.
