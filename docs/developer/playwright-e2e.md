# Browser E2E Tests (Playwright)

This guide explains how to run the browser-based end-to-end test suite
at `tests/playwright/` — locally during development and in CI — and how
to write new tests against the shared fixture surface.

`tests/playwright/conftest.py` is the source of truth for fixture
behaviour. This doc paraphrases it for discoverability; if the two ever
disagree, the conftest wins.

## Overview

The suite uses [`pytest-playwright`](https://playwright.dev/python/docs/intro)
to drive a real Chromium / Firefox / WebKit browser against an
in-process FastAPI server. It is intentionally isolated from the default
`pytest` run for two reasons:

1. **Browser processes** do not play nicely with `pytest --cov`'s
   subprocess instrumentation — coverage measurement interferes with
   browser-process isolation, so the suite must be invoked with
   `--override-ini='addopts='` to strip the project-wide coverage flags.
2. **No Playwright dependency on the default path.** `tests/conftest.py`
   gates collection on a `try: import playwright` — if Playwright is not
   installed (the default for most contributors), the directory is
   silently added to `collect_ignore_glob` and skipped. The dedicated CI
   job (which *does* install Playwright) collects the directory and
   runs the suite.

Current coverage (see `tests/playwright/`):

- `test_smoke.py` — page-load smoke across every UI route
- `test_setup_wizard_flow.py` — first-run setup wizard happy path
- `test_file_browser_desktop.py` — desktop-mode file browser
- `test_desktop_api_contract.py` — `window.pywebview.api` contract via the mock fixture

## Running locally

### Prerequisites

```bash
pip install -e ".[dev]"          # provides pytest-playwright
playwright install chromium      # or: firefox, webkit
```

`pytest-playwright` is part of the `[dev]` extra (see `pyproject.toml`);
the `playwright install` command downloads the actual browser binaries
under `~/.cache/ms-playwright/`. You only need to run it once per
machine per browser.

### The canonical command

```bash
pytest tests/playwright/ \
    --browser chromium \
    --override-ini='addopts='
```

- `--browser chromium` — pick the browser. `firefox` and `webkit` are
  the other valid values. CI runs all three in parallel (see below);
  locally you usually only need one.
- `--override-ini='addopts='` — **required**. `pyproject.toml`'s
  project-wide `addopts` includes `--cov` / `--cov-fail-under`, which
  break browser-process isolation. Stripping `addopts` for this run
  disables coverage measurement just for the Playwright suite.

### Interactive debugging

```bash
# Run headed so you can watch the browser
pytest tests/playwright/ --browser chromium --headed --override-ini='addopts='

# Slow every action so you can see what is happening
pytest tests/playwright/ --browser chromium --headed --slowmo=500 --override-ini='addopts='

# Drop into the Playwright Inspector on the first action
PWDEBUG=1 pytest tests/playwright/ --browser chromium --override-ini='addopts='
```

### Trace viewer

When a test fails (or when you want to inspect a passing run), record a
trace and open it in Playwright's trace viewer:

```bash
pytest tests/playwright/test_smoke.py \
    --browser chromium \
    --override-ini='addopts=' \
    --tracing=retain-on-failure \
    --output=playwright-artifacts

# After a failure:
playwright show-trace playwright-artifacts/<test-name>/trace.zip
```

The trace viewer shows every browser action with a before/after DOM
snapshot, network activity, and console output. It is by far the
fastest way to diagnose a broken UI test — use it before resorting to
`print()` or `page.pause()`.

Upstream Playwright docs cover the trace viewer in detail:
<https://playwright.dev/python/docs/trace-viewer>.
