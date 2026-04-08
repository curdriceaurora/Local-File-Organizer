# A3 — Browser E2E Housekeeping & Dev Docs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Retire the stale `feat/playwright-e2e` remote branch and publish `docs/developer/playwright-e2e.md` — a dev doc that lets a new contributor run one Playwright test locally without reading `conftest.py`, and lets them debug a CI failure without spelunking `ci.yml`.

**Architecture:** Pure documentation work plus one remote branch deletion. The new doc lives at `docs/developer/playwright-e2e.md` (repo convention overrides the issue's `docs/dev/` path), is linked from `docs/developer/index.md` and `docs/developer/testing.md`, and is authored section-by-section with every code block copied verbatim from source (no paraphrasing — per `.claude/rules/documentation-generation-checklist.md`). Branch deletion runs only after the doc PR is approved, guarded by the four-step verification protocol from the spec's Deliverable 1.

**Tech Stack:** Markdown, `pymarkdown` (linter, `.pymarkdown.json` config), `git` + `gh` for branch operations, `bash .claude/scripts/pre-commit-validation.sh` for commit-gate. The doc itself references `pytest-playwright`, `uvicorn`, and the existing `tests/playwright/conftest.py` fixture surface.

**Spec:** `docs/superpowers/specs/2026-04-07-a3-playwright-e2e-housekeeping-design.md`

**Working branch:** `feature/1153-a3-playwright-e2e-docs` (already created, spec already committed on it as `f172e88e` + `c195c143`).

---

## File Structure

**Files to create:**

- `docs/developer/playwright-e2e.md` — the new dev doc (single markdown file, 8 sections, ~300–400 lines)

**Files to modify:**

- `docs/developer/index.md` — add a bullet under the "Testing" section (currently around line 149) linking to the new doc
- `docs/developer/testing.md` — add a one-line pointer under the "Test Markers" section (around line 38) noting browser E2E lives in `tests/playwright/` and linking to the new doc

**Files that are read-only reference (verify against, do not modify):**

- `tests/playwright/conftest.py` — source of truth for every fixture contract claim
- `tests/playwright/test_smoke.py` — source of truth for the test-skeleton code block and marker convention
- `tests/playwright/test_setup_wizard_flow.py` — source of the `config.yaml` reset pattern referenced in the `playwright_config_dir` section
- `.github/workflows/ci.yml` — source of the CI job details (lines 243–321 on `origin/main`)
- `pyproject.toml` — source of `pytest-playwright` dep line, marker registration, `addopts`
- `tests/conftest.py` — source of the `collect_ignore_glob` gating claim

---

## Task 1: Capture source-of-truth snapshots

Before touching the doc file, extract the exact strings the doc will quote. This prevents doc drift from the "write from memory, verify later" pattern that D1 of the documentation-generation-checklist exists to kill. Output of this task is a scratchpad file (not committed) that later tasks copy-paste from.

**Files:**

- Create (scratch, git-ignored): `/tmp/a3-sources.txt`
- Read: `tests/playwright/conftest.py`, `tests/playwright/test_smoke.py`, `tests/playwright/test_setup_wizard_flow.py`, `.github/workflows/ci.yml`, `pyproject.toml`, `tests/conftest.py`

- [ ] **Step 1.1: Read the full Playwright conftest.**

Run:

```bash
cat tests/playwright/conftest.py > /tmp/a3-sources.txt
echo "=== ^conftest.py | vtest_smoke.py ===" >> /tmp/a3-sources.txt
cat tests/playwright/test_smoke.py >> /tmp/a3-sources.txt
```

Expected: file exists, contains `def live_server_url`, `def playwright_config_dir`, `def base_url`, `def pywebview_mock`, `class PywebviewMockHandle`, and `pytestmark = [pytest.mark.e2e, pytest.mark.playwright]`. If any of these are missing, **stop** — the doc plan is out of date with `main` and must be re-verified.

- [ ] **Step 1.2: Extract the Playwright CI job block.**

Run:

```bash
sed -n '243,321p' .github/workflows/ci.yml
```

Expected output: starts with `  playwright:` and ends with the `if-no-files-found: ignore` artifact upload line. Confirms the job exists at the line range the doc will reference. If the line range has shifted (someone edited `ci.yml` since the spec was written), find the new range with `grep -n '^  playwright:' .github/workflows/ci.yml` and update every line-number reference in Tasks 4 and 6 below.

- [ ] **Step 1.3: Extract the relevant `pyproject.toml` lines.**

Run:

```bash
grep -n 'pytest-playwright\|"playwright:' pyproject.toml
```

Expected output: one line near `pytest-playwright>=0.5.0` (dep, around line 136) and one line near `"playwright: browser-based E2E tests` (marker registration, around line 350). Confirms the dep is in `[dev]` and the marker is registered. If either is missing, the doc's install instructions will mislead contributors — **stop** and escalate.

- [ ] **Step 1.4: Extract the `collect_ignore_glob` gate.**

Run:

```bash
grep -n -B1 -A5 'collect_ignore_glob\|playwright' tests/conftest.py
```

Expected output: a `try: import playwright; except ImportError: collect_ignore_glob.append("playwright/**")` (or equivalent) block. Confirms the Gotchas section's claim about the default-skip behaviour.

- [ ] **Step 1.5: Confirm the `config.yaml` reset pattern in the setup wizard test.**

Run:

```bash
grep -n 'config.yaml\|playwright_config_dir' tests/playwright/test_setup_wizard_flow.py
```

Expected output: at least one line showing a deletion or truncation of `config.yaml` under `playwright_config_dir`. Captures the exact pattern the doc will cite as "the canonical way to reset state mid-session".

- [ ] **Step 1.6: No commit.**

This task produces no tracked changes — `/tmp/a3-sources.txt` is scratch paper for the author.

---

## Task 2: Create `docs/developer/playwright-e2e.md` — Overview and Running Locally

**Files:**

- Create: `docs/developer/playwright-e2e.md`

- [ ] **Step 2.1: Create the file with the Overview and "Running locally" sections.**

Write the following content to `docs/developer/playwright-e2e.md`:

````markdown
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
````

- [ ] **Step 2.2: Lint the new file.**

Run:

```bash
pymarkdown --config .pymarkdown.json scan docs/developer/playwright-e2e.md
```

Expected: zero output (success). If MD031 (blank lines around fenced code blocks) fires, add the missing blank lines. If any other rule fires, fix the specific violation — **do not disable rules**.

- [ ] **Step 2.3: Commit.**

```bash
git add docs/developer/playwright-e2e.md
git commit -m "docs(developer): start Playwright E2E guide (overview + local run)

First sections of docs/developer/playwright-e2e.md for #1153:
- Overview of the suite and why it is isolated from the default run
- Prerequisites, canonical pytest command, --override-ini rationale
- Headed / slowmo / PWDEBUG interactive debugging
- Trace viewer workflow"
```

---

## Task 3: Add "Running in CI" section

**Files:**

- Modify: `docs/developer/playwright-e2e.md` (append)

- [ ] **Step 3.1: Append the CI section.**

Append the following to `docs/developer/playwright-e2e.md`:

````markdown
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
````

- [ ] **Step 3.2: Verify the line number is still accurate.**

Run:

```bash
grep -n '^  playwright:' .github/workflows/ci.yml
```

Expected: exactly one line matching `^243:  playwright:` (or whatever the current line is). If the line number has drifted from 243, update the reference in the section text you just appended and re-lint.

- [ ] **Step 3.3: Lint.**

```bash
pymarkdown --config .pymarkdown.json scan docs/developer/playwright-e2e.md
```

Expected: zero output.

- [ ] **Step 3.4: Commit.**

```bash
git add docs/developer/playwright-e2e.md
git commit -m "docs(developer): add Playwright CI job section

For #1153. Describes the .github/workflows/ci.yml playwright job:
chromium/firefox/webkit matrix, fail-fast rationale, job steps,
artifact download workflow for debugging CI failures, and the
pytest-rerunfailures flake-tolerance policy."
```

---

## Task 4: Add fixture-contract sections (`playwright_config_dir`, `live_server_url`, `pywebview_mock`)

**Files:**

- Modify: `docs/developer/playwright-e2e.md` (append)
- Read: `tests/playwright/conftest.py` (all fixture docstrings — do not paraphrase, condense directly from source)

- [ ] **Step 4.1: Re-read the conftest fixtures to capture current line numbers.**

Run:

```bash
grep -n '^def \|^class \|^@pytest.fixture' tests/playwright/conftest.py
```

Expected output (on `origin/main` at spec-write time):

```text
56:def _find_free_port() -> int:
70:def _wait_for_port(port: int, timeout: float = 20.0) -> bool:
103:@pytest.fixture(scope="session")
104:def live_server_url(...
117:def playwright_config_dir(...      # may be a different line on main
182:@pytest.fixture(scope="session")
183:def base_url(...
218:class PywebviewMockHandle:
277:@pytest.fixture
278:def pywebview_mock(...
```

Use the actual line numbers from your run in the section text below — do not hard-code the spec-time numbers.

- [ ] **Step 4.2: Append the fixture sections.**

Append to `docs/developer/playwright-e2e.md`:

````markdown
## Fixture contracts

All fixtures live in `tests/playwright/conftest.py`. Scopes and line
numbers below are current as of the most recent edit to this doc — if
you are about to write a test and any of this looks stale, re-read
the conftest.

### `playwright_config_dir` (session-scoped)

Returns a per-session `tmp_path` that is used as the FastAPI server's
`XDG_CONFIG_HOME`. This isolates the server's `ConfigManager` from your
real `~/.config/file-organizer` so tests cannot pollute your dev
environment (and vice versa).

**When test authors care about it:** any test that needs to *reset* or
*mutate* persistent config mid-session must write to or delete files
under `playwright_config_dir / "file-organizer"`, **not** the real home
directory. The canonical reset pattern is in
`tests/playwright/test_setup_wizard_flow.py`: it deletes
`<playwright_config_dir>/file-organizer/config.yaml` immediately before
navigation so `ConfigManager.load()` returns `AppConfig` defaults
(`setup_completed=False`), making the test order-independent.

If you do not touch persistent state, you can ignore this fixture — it
is wired into `live_server_url` already and does its job transparently.

### `live_server_url` (session-scoped)

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

Injects a stub `window.pywebview.api` into the page via
`page.add_init_script()`. Because `add_init_script` runs before **any**
navigation in the page's lifecycle, the mock is always present when
`desktop_api.js` runs its `if (window.pywebview)` feature detection —
which sets `document.body.dataset.desktopApp = "1"`, enabling any
elements decorated with `[data-desktop-only]`.

The fixture returns a `PywebviewMockHandle` with the following methods
(see `tests/playwright/conftest.py` for full docstrings):

| Method                            | Purpose                                                            |
|-----------------------------------|--------------------------------------------------------------------|
| `set_browse_directory_result(p)`  | Override what `window.pywebview.api.browse_directory()` resolves to. |
| `set_browse_file_result(p)`       | Override the `browse_file()` return value.                         |
| `set_save_file_result(p)`         | Override the `save_file()` return value.                           |
| `set_open_path_result(bool)`      | Override the `open_path()` return value (success / failure).       |
| `get_open_path_calls()`           | Return the ordered list of paths `open_path()` was called with.    |

**Caveat:** mock state lives in `window.__mockPyw`. Because
`add_init_script` re-runs on every page load, the state resets on
every navigation — if you need to assert "the page called
`open_path('/foo')`" you must read `get_open_path_calls()` **before**
the next navigation.
````

- [ ] **Step 4.3: Lint.**

```bash
pymarkdown --config .pymarkdown.json scan docs/developer/playwright-e2e.md
```

Expected: zero output.

- [ ] **Step 4.4: Commit.**

```bash
git add docs/developer/playwright-e2e.md
git commit -m "docs(developer): document Playwright fixture contracts

For #1153. Documents playwright_config_dir, live_server_url, base_url,
and pywebview_mock from tests/playwright/conftest.py — scopes,
behaviour, override rules, and the PywebviewMockHandle method table.
Forward-points at epic B2 for the auth_enabled=True variant."
```

---

## Task 5: Add "Adding a new test" and "Gotchas" sections

**Files:**

- Modify: `docs/developer/playwright-e2e.md` (append)
- Read: `tests/playwright/test_smoke.py` (copy the marker block verbatim)

- [ ] **Step 5.1: Re-read the test-smoke module-level marker block.**

Run:

```bash
sed -n '38,48p' tests/playwright/test_smoke.py
```

Expected: a block containing `pytestmark = [` then `pytest.mark.e2e,` then `pytest.mark.playwright,` then `]`. Copy this exactly into the skeleton in step 5.2 — do not retype it.

- [ ] **Step 5.2: Append the "Adding a new test" and "Gotchas" sections.**

Append to `docs/developer/playwright-e2e.md`:

````markdown
## Adding a new test

1. **File placement.** New files go under `tests/playwright/` and must
   be named `test_<feature>.py`.
2. **Markers.** Apply **both** `e2e` and `playwright` at module level
   via `pytestmark`. Not per-function decorators — the existing suite
   uses the list form consistently.

   - The `e2e` marker keeps the suite visible to developers running
     `pytest -m "integration or e2e"` and keeps
     `docs/developer/testing.md`'s marker taxonomy consistent.
   - The `playwright` marker is what the CI job's selector expects and
     what `tests/conftest.py`'s `collect_ignore_glob` gate keys off
     when the `playwright` dep is not installed.

   Omitting either marker silently breaks one of those two flows.

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
       --override-ini='addopts='
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

The canonical reset pattern, from `test_setup_wizard_flow.py`: delete
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

If local runs start failing with `OSError: [Errno 48] Address already
in use` during fixture setup, simply re-run — do **not** bump
`_wait_for_port`'s timeout.
````

- [ ] **Step 5.3: Lint.**

```bash
pymarkdown --config .pymarkdown.json scan docs/developer/playwright-e2e.md
```

Expected: zero output.

- [ ] **Step 5.4: Commit.**

```bash
git add docs/developer/playwright-e2e.md
git commit -m "docs(developer): add test-authoring skeleton and gotchas

For #1153. 'Adding a new test' section requires BOTH pytest.mark.e2e
and pytest.mark.playwright applied at module level via pytestmark
(matches the existing convention across all four test files) and
gives a copy-pasteable skeleton. 'Gotchas' covers the
collect_ignore_glob import gate, the state-leakage reset pattern,
and the random-port TOCTOU window."
```

---

## Task 6: Link the new doc from `docs/developer/index.md`

**Files:**

- Modify: `docs/developer/index.md` (around line 149, "Testing" section)

- [ ] **Step 6.1: Re-read the testing section of the dev index.**

Run:

```bash
sed -n '149,175p' docs/developer/index.md
```

Expected: a `## Testing` heading followed by "Run Tests" and "Write Tests" sub-sections with fenced code blocks.

- [ ] **Step 6.2: Add a sub-section linking to the new doc.**

Edit `docs/developer/index.md`. Immediately after the `## Testing` heading (before the "Run Tests" sub-section), insert a new sub-section:

```markdown
### Browser E2E (Playwright)

Browser-based end-to-end tests live under `tests/playwright/` and run
against all three major browsers in CI. They are isolated from the
default `pytest` run and require `playwright install <browser>` as a
one-time prerequisite.

See [Browser E2E Tests (Playwright)](playwright-e2e.md) for the full
guide: local invocation, CI job layout, fixture contracts, and a
new-test skeleton.
```

- [ ] **Step 6.3: Lint.**

```bash
pymarkdown --config .pymarkdown.json scan docs/developer/index.md
```

Expected: zero output. The edit only adds a new `###` sub-section under an existing `##` — heading levels should not skip and no other rules should fire.

- [ ] **Step 6.4: Commit.**

```bash
git add docs/developer/index.md
git commit -m "docs(developer): link Playwright E2E guide from dev index

For #1153. Adds a 'Browser E2E (Playwright)' sub-section under the
Testing section of docs/developer/index.md pointing at the new
playwright-e2e.md guide."
```

---

## Task 7: Link the new doc from `docs/developer/testing.md`

**Files:**

- Modify: `docs/developer/testing.md` (around line 38, "Test Markers" section)

- [ ] **Step 7.1: Re-read the Test Markers section.**

Run:

```bash
sed -n '38,60p' docs/developer/testing.md
```

Expected: a `## Test Markers` heading, a fenced code block listing the registered markers including `@pytest.mark.e2e`, and a "Running Tests by Marker" sub-section.

- [ ] **Step 7.2: Add a one-line pointer after the marker code block.**

Edit `docs/developer/testing.md`. Immediately after the fenced code block that lists `@pytest.mark.e2e` (before the "Running Tests by Marker" sub-section), insert:

```markdown
> **Browser E2E:** Playwright-driven browser tests live under
> `tests/playwright/` and carry **both** `e2e` and `playwright`
> markers at module level. They are excluded from the default run
> and have their own dedicated CI job. See
> [Browser E2E Tests (Playwright)](playwright-e2e.md) for how to run
> them and how to add new ones.
```

- [ ] **Step 7.3: Lint.**

```bash
pymarkdown --config .pymarkdown.json scan docs/developer/testing.md
```

Expected: zero output.

- [ ] **Step 7.4: Commit.**

```bash
git add docs/developer/testing.md
git commit -m "docs(developer): cross-link Playwright guide from testing.md

For #1153. Adds a blockquote pointer after the Test Markers code block
noting that browser-based Playwright tests live under tests/playwright/
and carry both e2e and playwright markers. Links to playwright-e2e.md
for the full guide."
```

---

## Task 8: Dry-run walkthrough

This is the final doc-quality gate before opening the PR: you (or a fresh reader) follow the doc top-to-bottom on a clean checkout and run **one** Playwright test end-to-end. Any step that requires guessing, reading source, or asking questions is a doc bug — fix it before merging.

**Files:**

- Modify: `docs/developer/playwright-e2e.md` (only if bugs are found)

- [ ] **Step 8.1: Run the canonical local command exactly as documented.**

From a clean shell (no editor state, no `PYTHONPATH` tricks):

```bash
playwright install chromium     # safe no-op if already installed
pytest tests/playwright/test_smoke.py \
    --browser chromium \
    --override-ini='addopts='
```

Expected: suite collects and runs against the real browser. Some tests may be slow; that is fine. If collection fails with an import error, the prerequisites section is incomplete. If the run errors on coverage, the `--override-ini` rationale is wrong. If the run hangs, the server-startup gotcha needs more detail.

- [ ] **Step 8.2: Follow the "Adding a new test" skeleton.**

Copy the skeleton from the doc into a scratch file at `tests/playwright/test_scratch.py`, run it:

```bash
pytest tests/playwright/test_scratch.py \
    --browser chromium \
    --override-ini='addopts='
```

Expected: one test passes (it just asserts `<h1>` is visible on `/ui/files`). If the skeleton is missing an import, the markers, or the fixture, fix the doc.

- [ ] **Step 8.3: Delete the scratch file.**

```bash
rm tests/playwright/test_scratch.py
```

- [ ] **Step 8.4: Re-run full lint.**

```bash
pymarkdown --config .pymarkdown.json scan docs/developer/playwright-e2e.md docs/developer/index.md docs/developer/testing.md
```

Expected: zero output across all three files.

- [ ] **Step 8.5: Run pre-commit validation.**

```bash
bash .claude/scripts/pre-commit-validation.sh
```

Expected: green. If any check fails, fix and re-run — do **not** `--no-verify`.

- [ ] **Step 8.6: If any doc bugs were fixed, commit them.**

If Step 8.1 or 8.2 surfaced a bug that you patched in the doc:

```bash
git add docs/developer/playwright-e2e.md
git commit -m "docs(developer): fix Playwright guide issues found during dry-run

For #1153. Dry-run walkthrough from a clean shell surfaced:
- <one-line description of each issue>"
```

Otherwise skip this step.

---

## Task 9: Open the PR

**Files:** (none — `gh` operation)

- [ ] **Step 9.1: Push the branch.**

```bash
git push -u origin feature/1153-a3-playwright-e2e-docs
```

- [ ] **Step 9.2: Open the PR with a body that includes the four pre-deletion checks from the spec.**

Run:

```bash
gh pr create \
    --title "docs(developer): add Playwright E2E guide (#1153)" \
    --body "$(cat <<'EOF'
## Summary

Closes #1153 (A3). Introduces `docs/developer/playwright-e2e.md` —
the first dev-facing guide for the browser E2E suite under
`tests/playwright/` — and cross-links it from `docs/developer/index.md`
and `docs/developer/testing.md`.

The doc covers:

- Local invocation (prerequisites, canonical command, headed/slowmo/PWDEBUG, trace viewer)
- CI job layout (`.github/workflows/ci.yml` → `playwright:` job, matrix, artifact download flow, flake tolerance)
- Fixture contracts (`playwright_config_dir`, `live_server_url`, `base_url`, `pywebview_mock`)
- Test-authoring skeleton (**both** `e2e` and `playwright` markers at module level via `pytestmark`)
- Gotchas (`collect_ignore_glob` import gate, state-leakage reset pattern, random-port TOCTOU)

**Path decision:** issue says `docs/dev/playwright-e2e.md`, repo convention is `docs/developer/`. Followed convention.

**Branch deletion is NOT in this PR.** Per the spec's Deliverable 1, deleting `origin/feat/playwright-e2e` requires four pre-deletion checks that must be re-run at the moment of deletion. I will run them in a comment on this PR after approval and paste the output; the delete itself happens after this PR merges.

## Test plan

- [ ] `pymarkdown --config .pymarkdown.json scan docs/developer/playwright-e2e.md docs/developer/index.md docs/developer/testing.md` is clean
- [ ] `bash .claude/scripts/pre-commit-validation.sh` passes
- [ ] Dry-run: follow the "Running locally" section on a clean shell and run `pytest tests/playwright/test_smoke.py --browser chromium --override-ini='addopts='` → suite collects and runs
- [ ] Dry-run: copy the "Adding a new test" skeleton into `tests/playwright/test_scratch.py`, run it, delete it → one test passes
- [ ] Reviewer sanity-check: every fixture line number and CI line number in the doc matches current `main`

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: PR URL printed. Record it for Task 10.

---

## Task 10: Post-merge — delete the stale branch

This task runs **after** the PR from Task 9 is reviewed, approved, and merged to `main`. It is gated by the four pre-deletion checks from the spec's Deliverable 1. **Do not skip any check** — this is an irreversible remote operation.

**Files:** (none — `git`/`gh` operations on the remote)

- [ ] **Step 10.1: Fetch the latest `origin/main` and the target branch.**

```bash
git fetch origin main feat/playwright-e2e
```

Expected: both refs update without error. If `feat/playwright-e2e` is gone already, someone else deleted it — skip to Step 10.7 to record the result.

- [ ] **Step 10.2: Check 1 — commit range is unchanged.**

```bash
git log --oneline origin/main..origin/feat/playwright-e2e
```

Expected: exactly the six commits from Appendix A.1 of the spec:

```text
b40b0fef fix: route-specific assertions in TestPageLoads + opt-in playwright collection
b5ed040c refactor(e2e): parametrize test_pages_share_consistent_html_structure
31c47af1 fix: address unresolved CodeRabbit threads on playwright smoke suite
ac37f074 fix: address ruff lint/format failures and review comments (round 2)
28d9c24f fix: address CI failures and PR review findings for playwright E2E branch
2fd089f2 feat(e2e): add Playwright browser smoke test suite
```

If the list is different (new commits added, fewer commits, different SHAs), **STOP**. Someone pushed to the branch after the spec was written — re-investigate before proceeding.

- [ ] **Step 10.3: Check 2 — `tests/playwright/` on `main` is still a superset.**

```bash
git diff --stat origin/feat/playwright-e2e origin/main -- tests/playwright/
```

Expected: all rows show insertions-only in `main` (the branch has no unique `tests/playwright/` content). If any row shows `main` *losing* content relative to the branch, **STOP** — the branch may carry work the spec missed.

- [ ] **Step 10.4: Check 3 — file-level accounting of branch-only paths.**

```bash
comm -23 \
    <(git ls-tree -r --name-only origin/feat/playwright-e2e | sort) \
    <(git ls-tree -r --name-only origin/main | sort) > /tmp/a3-branch-only-files.txt
wc -l /tmp/a3-branch-only-files.txt
cat /tmp/a3-branch-only-files.txt
```

Expected: every line matches one of the categories from the spec's Appendix A.3 — pre-refactor `.claude/*` files (removed in `181eb6d2`), Tauri v2 `desktop/*` files (removed in `183813d5`), or equivalent known refactors. Any line you cannot tie to a known refactor is a **STOP** condition: escalate to the issue author before deleting.

- [ ] **Step 10.5: Check 4 — dependent-work check.**

Re-read issue #1154 (B1) and confirm it still uses `live_server_url` / `base_url` / `pywebview_mock` / `playwright_config_dir` from `main` and does **not** branch from `feat/playwright-e2e`:

```bash
gh issue view 1154 | grep -iE 'playwright|branch|base'
```

Expected: the scope section still describes writing a new file under `tests/playwright/` and consuming the existing fixtures. If the issue has been re-scoped to depend on the stale branch, **STOP** and escalate.

- [ ] **Step 10.6: Delete the branch.**

All four checks pass. Delete the remote ref:

```bash
git push origin --delete feat/playwright-e2e
```

Expected: `- [deleted]         feat/playwright-e2e` confirmation from the server.

- [ ] **Step 10.7: Record the result as a comment on #1153.**

```bash
gh issue comment 1153 --body "$(cat <<'EOF'
Branch deletion complete.

Pre-deletion verification (from the spec's Deliverable 1):

1. ✅ Commit range matches Appendix A.1 (6 commits, SHAs unchanged)
2. ✅ `tests/playwright/` on `main` is still a strict content superset
3. ✅ All branch-only files traced to known main-side refactors
4. ✅ #1154 still uses fixtures from `main`, no dependency on the stale branch

`git push origin --delete feat/playwright-e2e` ran cleanly.

Closing.
EOF
)"
gh issue close 1153
```

Expected: comment posted, issue closed.

---

## Self-review

**Spec coverage check:**

- Deliverable 1 (delete remote branch + 4 pre-deletion checks + Appendix A evidence) → Task 10 (all four checks mapped to Steps 10.2–10.5, evidence captured in spec Appendix A and re-verified at push time)
- Deliverable 2 (new `docs/developer/playwright-e2e.md` with 8 sections) → Tasks 2 (Overview + Running locally), 3 (Running in CI), 4 (fixture contracts 4–6), 5 (Adding a new test + Gotchas)
- Deliverable 3 (link from `docs/developer/index.md` and `docs/developer/testing.md`) → Tasks 6 and 7
- Verification / definition of done →
  - Branch gone: Task 10
  - Doc exists + sections populated: Tasks 2–5
  - Index link: Task 6
  - Testing.md pointer: Task 7
  - `pymarkdown scan` clean: every task has a lint step, plus Task 8.4 final sweep
  - Pre-commit validation: Task 8.5
  - Dry-run walkthrough: Task 8.1–8.3
- Risks → branch-deletion risk is fully mitigated by Task 10's gated checks; documentation-drift risk is acknowledged in the doc header (Task 2.1 content) pointing at `tests/playwright/conftest.py` as source of truth; `docs/dev` vs `docs/developer` discrepancy is called out in the PR body (Task 9.2)

**Placeholder scan:** No `TBD` / `TODO` / `implement later` anywhere in the plan. Every code block and command is fully specified. The only conditional step (Task 8.6) is explicitly gated on "if bugs were fixed".

**Consistency check:** Fixture names, file paths, marker names (`e2e` + `playwright`), and line-range references (`.github/workflows/ci.yml:243`) are consistent across all tasks. Commit range in Task 10 matches Appendix A.1 of the spec.

No gaps found.
