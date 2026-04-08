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
   `--override-ini='addopts='`, which strips the entire project-wide
   `addopts` list (not only the `--cov*` flags). See "Running locally"
   below for the full implications and the flags you must re-add.
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
    --override-ini='addopts=' \
    --strict-markers \
    --timeout=60
```

- `--browser chromium` — pick the browser. `firefox` and `webkit` are
  the other valid values. CI runs all three in parallel (see below);
  locally you usually only need one.
- `--override-ini='addopts='` — **required**. `pyproject.toml`'s
  project-wide `addopts` includes `--cov` / `--cov-fail-under` (which
  break browser-process isolation), `--strict-markers`, and
  `--timeout=30`. Stripping `addopts` clears **all** of those flags for
  this run.
- `--strict-markers` — re-adds strict-marker enforcement so pytest still
  fails if any test uses an unregistered marker (stripped from `addopts`
  above).
- `--timeout=60` — re-adds a per-test timeout appropriate for browser
  tests. The project-wide 30 s is too tight for browser startup; 60 s
  matches what CI uses (stripped from `addopts` above).

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
    --strict-markers \
    --timeout=60 \
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
5. `pytest tests/playwright/ --browser ${{ matrix.browser }} --tracing retain-on-failure --screenshot only-on-failure --video retain-on-failure --output=playwright-artifacts --reruns 2 --reruns-delay 2 --timeout=60 --strict-markers --override-ini="addopts="`

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

## Fixture contracts

All fixtures live in `tests/playwright/conftest.py`. Scopes and line
numbers below are current as of the most recent edit to this doc — if
you are about to write a test and any of this looks stale, re-read
the conftest.

### `playwright_config_dir` (session-scoped)

Defined at `tests/playwright/conftest.py:117`.

Returns a per-session `tmp_path` that is used as the FastAPI server's
`XDG_CONFIG_HOME`. This isolates the server's `ConfigManager` from your
real `~/.config/file-organizer` so tests cannot pollute your dev
environment (and vice versa).

**When test authors care about it:** any test that needs to *reset* or
*mutate* persistent config mid-session must write to or delete files
under `playwright_config_dir / "file-organizer"`, **not** the real home
directory. The canonical reset pattern is in
`tests/playwright/test_smoke.py` — it deletes
`<playwright_config_dir>/file-organizer/config.yaml` immediately before
navigation so `ConfigManager.load()` returns `AppConfig` defaults
(`setup_completed=False`), making the test order-independent.

If you do not touch persistent state, you can ignore this fixture — it
is wired into `live_server_url` already and does its job transparently.

### `live_server_url` (session-scoped)

Defined at `tests/playwright/conftest.py:127`.

Starts the FastAPI app in-process on a random free port in a daemon
thread and yields a base URL like `http://127.0.0.1:54321`.

What it does under the hood:

1. Pulls `playwright_config_dir` to get an isolated config home.
2. Sets `XDG_CONFIG_HOME` and monkeypatches
   `file_organizer.config.manager.DEFAULT_CONFIG_DIR` **before**
   importing the API modules, so the module-level constant captures
   the tmp dir instead of the user's real config.
3. Constructs `ApiSettings(auth_enabled=False, allowed_paths=[tmp], auth_db_path=<tmp>/auth.db)`.
4. Builds the app via `create_app(settings)` and runs it in a daemon
   `uvicorn.Server` thread.
5. Waits up to 20 seconds for the port to accept TCP connections
   (`_wait_for_port`). If the server never comes up, raises a
   `RuntimeError` that includes any exception raised from the server
   thread — so you get a real stack trace instead of a silent timeout.
6. On teardown, sets `server.should_exit = True`, joins the thread,
   and restores environment variables — wrapped in `try/finally` so
   cleanup runs even if startup fails before `yield`.

**How to override settings:** `live_server_url` is session-scoped, so
you cannot override its `ApiSettings` per-test. That is deliberate —
per-test overrides would force a server restart per test and tank
wall-clock. If you need an authenticated variant for a test,
**epic B2** will add a separate session fixture that builds the app
with `auth_enabled=True`; this doc will be updated when that lands.

### `base_url` (session-scoped, overrides `pytest-playwright`)

Defined at `tests/playwright/conftest.py:243`.

Returns `live_server_url` as the default URL Playwright resolves
relative paths against. With this fixture in place you can write:

```python
page.goto("/ui/files")
```

…and Playwright rewrites it to `http://127.0.0.1:<port>/ui/files`.
Without the override, `pytest-playwright`'s built-in `base_url`
reads from the `--base-url` CLI flag, which this project does not
pass.

### `pywebview_mock` (function-scoped)

Defined at `tests/playwright/conftest.py:338`.

Injects a stub `window.pywebview.api` into the page via
`page.add_init_script()`. Because `add_init_script` runs before **any**
navigation in the page's lifecycle, the mock is always present when
`desktop_api.js` runs its `if (window.pywebview)` feature detection —
which sets `document.body.dataset.desktopApp = "1"`, enabling any
elements decorated with `[data-desktop-only]`.

The fixture returns a `PywebviewMockHandle` (defined at
`tests/playwright/conftest.py:278`) with the following methods
(see the conftest for full docstrings):

| Method                            | Purpose                                                              |
|-----------------------------------|----------------------------------------------------------------------|
| `set_browse_directory_result(p)`  | Override what `window.pywebview.api.browse_directory()` resolves to. |
| `set_browse_file_result(p)`       | Override the `browse_file()` return value.                           |
| `set_save_file_result(p)`         | Override the `save_file()` return value.                             |
| `set_open_path_result(bool)`      | Override the `open_path()` return value (success / failure).         |
| `get_open_path_calls()`           | Return the ordered list of paths `open_path()` was called with.      |

**Caveat:** mock state lives in `window.__mockPyw`. Because
`add_init_script` re-runs on every page load, the state resets on
every navigation — if you need to assert "the page called
`open_path('/foo')`" you must read `get_open_path_calls()` **before**
the next navigation.

## Adding a new test

1. **File placement.** New files go under `tests/playwright/` and must
   be named `test_<feature>.py`.
2. **Markers.** Apply **both** `e2e` and `playwright` at module level
   via `pytestmark`. Not per-function decorators — the existing suite
   uses the list form consistently.

   - The `e2e` marker keeps the suite visible to developers running
     `pytest -m "integration or e2e"` and keeps
     `docs/developer/testing.md`'s marker taxonomy consistent. Omitting
     it excludes the test from those selectors.
   - The `playwright` marker enables `pytest -m playwright` as a
     convenience selector and satisfies the project-wide
     `--strict-markers` flag (which makes pytest fail collection if
     any test uses an unregistered marker). Omitting it means
     `pytest -m playwright` skips the test.

   Note: `tests/conftest.py`'s `collect_ignore_glob` gate is
   import-based (it skips the directory when `import playwright` raises
   `ImportError`), not marker-based. CI selects the suite by directory
   (`pytest tests/playwright/`), not by marker selector. Neither
   mechanism is affected by which markers your test carries.

3. **Fixtures.** Take `page` (from `pytest-playwright`) and
   `live_server_url` (or any of the other session fixtures above).
   Because the `base_url` fixture is wired in, you can use relative
   paths in `page.goto()`.

4. **Skeleton.** Copy the module-level marker block from
   `tests/playwright/test_smoke.py` and add one test:

   ```python
   import pytest
   from playwright.sync_api import Page

   pytestmark = [
       pytest.mark.e2e,
       pytest.mark.playwright,
       pytest.mark.timeout(60),  # browser ops need more headroom than unit tests
   ]


   def test_my_new_page(page: Page, live_server_url: str) -> None:
       page.goto("/ui/files")
       assert page.locator("h1").is_visible()
   ```

5. **Run it locally** using the canonical command from "Running
   locally" above, targeting just your new file:

   ```bash
   pytest tests/playwright/test_my_feature.py \
       --browser chromium \
       --override-ini='addopts=' \
       --strict-markers \
       --timeout=60
   ```

`tests/playwright/test_smoke.py` is the canonical template — if you
are unsure about style or structure, mirror it.

## Gotchas

### `collect_ignore_glob` is gated on the Playwright import

`tests/conftest.py` adds `playwright/**` to `collect_ignore_glob`
**only** when `import playwright` raises `ImportError`. This means:

- Default developer environment (Playwright not installed):
  `pytest tests/` silently skips the directory. Surprising the first
  time you hit it, but intentional — the suite cannot run without a
  browser anyway.
- Dedicated CI job (Playwright installed): the directory is collected,
  and your new tests run on every PR.
- **Developer machine with Playwright installed:** the directory is
  collected on every `pytest tests/` run. If you were not expecting
  that and your suite is slow, run with
  `--ignore=tests/playwright` explicitly.

### State leakage between tests

The `live_server_url` fixture is session-scoped, so every Playwright
test in a run shares the same FastAPI process and the same
`playwright_config_dir`. A test that flips `setup_completed=True` (for
example by completing the setup wizard) will break sibling tests
under random ordering unless it resets the state.

The canonical reset pattern, from `test_smoke.py`: delete
`<playwright_config_dir>/file-organizer/config.yaml` **before** the
navigation under test, so `ConfigManager.load()` returns
`AppConfig()` defaults. Do this in a fixture or at the top of the
test — never in `teardown`, because another test may run first in
random order.

### Random-port TOCTOU window

`_find_free_port` binds port 0, reads the assigned port, and releases
the socket — then `uvicorn` re-binds the same port. There is a small
window where another process could steal the port. This is negligible
on developer machines but occasionally trips on heavily-loaded CI
runners. The CI job's `--reruns 2` covers it.

If local runs start failing with `OSError: ... Address already in use`
during fixture setup, simply re-run — do **not** bump
`_wait_for_port`'s timeout.
