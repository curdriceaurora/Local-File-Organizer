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

## Running in CI

The Playwright job is defined in `.github/workflows/ci.yml` under the
`playwright:` job (currently around line 243, added in commit
`6711bec0` — "ci: add Playwright E2E job to PR/push CI"). It runs on
every `pull_request` and `push`.

### Matrix

| Browser  | Runner         | fail-fast |
|----------|----------------|-----------|
| chromium | ubuntu-latest  | no        |
| firefox  | ubuntu-latest  | no        |
| webkit   | ubuntu-latest  | no        |

All three run in parallel. `fail-fast: false` is deliberate: a Firefox
regression should not cancel the in-progress WebKit leg, because the
review value of seeing all three results outweighs the runner-minute
cost.

### What the job does (condensed)

1. `pip install -e ".[dev,search]"` — installs `pytest-playwright` and
   the standard test deps.
2. `pip install "pytest-rerunfailures>=14.0"` — installed inline
   (not in `[dev]`) because only this job uses it for flake tolerance.
3. Cache `~/.cache/ms-playwright` keyed on `pyproject.toml` hash +
   browser name.
4. `python -m playwright install --with-deps ${browser}` — downloads
   the browser binary and pulls the system libs a fresh Ubuntu runner
   needs.
5. `pytest tests/playwright/ --browser ${browser} --tracing=retain-on-failure --screenshot=only-on-failure --video=retain-on-failure --output=playwright-artifacts --reruns 2 --reruns-delay 2 --timeout=60 --strict-markers --override-ini='addopts='`

### Debugging a CI failure

When a Playwright leg fails on a PR:

1. Open the failing GitHub Actions run.
2. Go to the **Artifacts** panel (bottom of the run summary page).
3. Download `playwright-artifacts-<browser>` — the browser-specific
   name prevents matrix legs from clobbering each other.
4. Unzip locally. You will find trace files, screenshots, and videos
   for every failed test (none for passing tests — retention is
   `retain-on-failure` / `only-on-failure` to keep artifact size sane).
5. Open the trace:

   ```bash
   playwright show-trace <unzipped>/<test-name>/trace.zip
   ```

Retention is 7 days. If you need the artifact longer, download and
stash it locally.

### Flake tolerance

`--reruns 2 --reruns-delay 2` retries each failing test up to twice
with a 2-second delay, via `pytest-rerunfailures`. This absorbs
transient CI-side flakes (browser launch races, network hiccups on the
GitHub-hosted runner) without hiding real regressions — a genuinely
broken test still fails on the third attempt. If a test starts needing
more than 2 reruns, treat it as broken and fix the root cause rather
than bumping the retry count.
