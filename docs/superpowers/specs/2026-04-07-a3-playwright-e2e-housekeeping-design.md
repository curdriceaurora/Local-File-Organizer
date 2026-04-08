# A3 — Browser E2E: Housekeeping & Dev Docs

**Issue:** [#1153](https://github.com/curdriceaurora/Local-File-Organizer/issues/1153)
**Parent epic:** #1149
**Date:** 2026-04-07

## Problem

1. `origin/feat/playwright-e2e` is stale. All of its content is already on `main` (merged via PR #1113 and follow-ups), and `main` is strictly ahead — `git diff origin/feat/playwright-e2e origin/main` shows ~594 insertions in `main` with no unique content on the branch. It is dead weight that confuses `git branch -r` output and invites accidental diverging work.
2. The browser E2E suite under `tests/playwright/` has no developer-facing documentation. The only guidance today is the module docstring in `tests/playwright/conftest.py`. A new contributor cannot run one Playwright test locally without reading source, and cannot find where the CI job is defined or how to pull debug artifacts from a failing run.

## Goals

- Retire the stale branch.
- Publish a single dev doc that lets a new contributor run one Playwright test locally without asking questions, and that explains how to debug a CI failure.
- Document the fixture contracts (`live_server_url`, `pywebview_mock`) so test authors do not have to reverse-engineer `conftest.py`.

## Non-goals

- Writing new Playwright tests (that is epic B — issues #1154 and siblings).
- Modifying CI workflow YAML (owned by A1/A2, already done in commit `6711bec0`).
- Changing fixture implementation (already exists and is working in CI).
- Documenting the `auth_enabled=True` variant — that fixture does not exist yet; B2 will add it. This doc only forward-references it.

## Deliverables

### 1. Delete remote branch

```bash
git push origin --delete feat/playwright-e2e
```

Safety check performed: diff against `origin/main` confirms zero unique content on the branch (see Problem §1). No dependent work — #1154 (B1) writes a new file and consumes fixtures already on `main`, never touching the stale branch.

### 2. New file: `docs/developer/playwright-e2e.md`

Path follows repo convention (`docs/developer/`, not `docs/dev/` as the issue literally said — convention trumps issue spec unless it is a rewrite).

Section outline:

1. **Overview** — one paragraph: what the suite is, where it lives (`tests/playwright/`), why it is isolated from the default `pytest` run (browser processes + `--cov` conflict), what is already covered (smoke, setup wizard, file browser, desktop API contract).
2. **Running locally**
   - Prerequisites: `pip install -e ".[dev]"` (provides `pytest-playwright`), `playwright install chromium` (or `firefox` / `webkit`).
   - The canonical command:
     `pytest tests/playwright/ --browser chromium --override-ini='addopts='`
   - Why `--override-ini='addopts='` is mandatory (strips project-wide `--cov` / `--cov-fail-under` that break browser-process isolation — extracted from the `conftest.py` module docstring, verified against `pyproject.toml:addopts`).
   - Interactive debug: `--headed`, `--slowmo=500`, `PWDEBUG=1` for the Playwright Inspector.
   - Trace viewer workflow: run with `--tracing on`, then `playwright show-trace <path>` (link to upstream Playwright docs for deeper usage).
   - Firefox and WebKit variants (same command, different `--browser` flag).
3. **Running in CI**
   - Where the job is defined: `.github/workflows/ci.yml`, job name `playwright`, one line pointing at the job header (verified via `grep -n playwright .github/workflows/ci.yml` on `origin/main`).
   - Matrix: chromium / firefox / webkit in parallel, `fail-fast: false`, runs on `pull_request` and `push`.
   - Failure-debug workflow: GitHub Actions UI → failed workflow run → **Artifacts** → `playwright-artifacts-<browser>` (7-day retention). Artifact contains trace files, screenshots, and videos retained on failure only. Explain how to open a trace locally with `playwright show-trace`.
   - Flake tolerance: `--reruns 2 --reruns-delay 2` via `pytest-rerunfailures` (installed inline in the job, not in `[dev]`).
4. **Fixture contract: `live_server_url`**
   - Scope: session.
   - What it does: starts the FastAPI app in-process on a random free port in a daemon thread; isolates `XDG_CONFIG_HOME` + `DEFAULT_CONFIG_DIR` to a per-session `tmp_path`; constructs `ApiSettings(auth_enabled=False, allowed_paths=[tmp])`; waits up to 20s for the port to accept connections; tears down via `server.should_exit` on fixture exit.
   - How to override settings: point at the `live_server_url` body in `tests/playwright/conftest.py` as the reference; explain that it is session-scoped so tests cannot override per-test (that is a deliberate constraint — per-test API would force a server restart per test and tank wall-clock). Note the forward pointer: **B2 will add an `auth_enabled=True` variant** as a separate session fixture; this doc will be updated when that lands.
   - The companion `base_url` fixture: overrides `pytest-playwright`'s built-in so `page.goto("/ui/files")` resolves to the live server.
5. **Fixture contract: `pywebview_mock`**
   - Scope: function (per-test).
   - What it does: injects a stub `window.pywebview.api` via `page.add_init_script()` before any navigation; setting `window.pywebview` triggers `desktop_api.js` to flip `document.body.dataset.desktopApp = "1"`, which enables `[data-desktop-only]` elements.
   - Returned handle (`PywebviewMockHandle`): lists the mutator methods (`set_browse_directory_result`, `set_browse_file_result`, `set_save_file_result`, `set_open_path_result`) and the observer (`get_open_path_calls`) with one-line descriptions copied from the docstrings.
   - Caveat: mock state lives in `window.__mockPyw` and resets on every navigation because `add_init_script` re-runs for each page load.
6. **Adding a new test**
   - File naming: `tests/playwright/test_<feature>.py`.
   - Marker: `@pytest.mark.playwright` (registered in `pyproject.toml:markers`).
   - Import pattern: use the `page` fixture from `pytest-playwright` and any of the session fixtures above.
   - Minimal skeleton, copied verbatim from `tests/playwright/test_smoke.py` so it stays in sync with whatever `test_smoke.py` shows:

     ```python
     import pytest
     from playwright.sync_api import Page


     @pytest.mark.playwright
     def test_my_new_page(page: Page, live_server_url: str) -> None:
         page.goto("/ui/files")
         assert page.locator("h1").is_visible()
     ```

   - Pointer to `test_smoke.py` as the canonical template.
7. **Gotchas**
   - `tests/conftest.py` adds `playwright/**` to `collect_ignore_glob` only when the `playwright` import fails — this is why the default `pytest tests/` run silently skips the directory but the dedicated CI job (which installs `playwright`) collects it. If you install `playwright` locally, the directory will be collected on every run, which can be surprising.
   - State leakage between tests: `test_home_redirect` deletes `config.yaml` before navigation because a sibling test flips `setup_completed=True` and the home route honours it. Any new test that mutates persistent state must reset it the same way or use a fresh `live_server_url` (which would force a per-test server and is not supported).
   - TOCTOU window on the random-port allocator (documented in `_find_free_port`): negligible on developer machines, occasionally flaky under parallel CI shards — `--reruns 2` covers this.

### 3. Link the doc from the developer index

Edit `docs/developer/index.md`:

- Under the **Testing** section (around line 149), add a bullet pointing at the new doc: `Browser E2E (Playwright): see playwright-e2e.md`.

Also add a short pointer from `docs/developer/testing.md` under the **Test Markers** section (line 38) — near the `@pytest.mark.e2e` bullet (line 46) add a sibling line noting that browser-based Playwright E2E tests live in `tests/playwright/` and link to the new `playwright-e2e.md`.

## Out of scope

- Screenshots or GIFs of the Playwright Inspector / trace viewer.
- Troubleshooting matrix for every possible failure mode — the doc points at the trace viewer and CI artifacts and trusts that to be sufficient.
- Updating `CONTRIBUTING.md` (single entry point is `docs/developer/` per convention).

## Verification / definition of done

- [ ] `origin/feat/playwright-e2e` no longer listed in `git branch -r`.
- [ ] `docs/developer/playwright-e2e.md` exists and every section above is populated from actual source (not from memory) — per `.claude/rules/documentation-generation-checklist.md`, every code block must be copied from the real file with the source path noted.
- [ ] `docs/developer/index.md` links to the new doc under Testing.
- [ ] `docs/developer/testing.md` has a one-line pointer to the new doc.
- [ ] `pymarkdown scan docs/developer/playwright-e2e.md docs/developer/index.md docs/developer/testing.md` passes with zero violations (catches D5, the #1 finding in the dataset).
- [ ] Pre-commit validation passes (`bash .claude/scripts/pre-commit-validation.sh`).
- [ ] Dry-run walkthrough: I (the author) follow the doc from scratch on a clean checkout and run one Playwright test locally end-to-end. Any step that requires guessing or reading source is a doc bug.

## Risks

- **Documentation drift.** The fixture contracts are described in prose, not generated — if `conftest.py` changes, the doc can silently go stale. Mitigation: link to the file + line ranges from each fixture section so a reader can always cross-check; note in the doc header that `tests/playwright/conftest.py` is the source of truth.
- **Branch deletion is irreversible.** Already mitigated: diff-verified the branch is strictly behind `main` and has no unique content. If somehow needed later, the commits remain reachable via reflog on the GitHub side for 90 days and can be recreated from the merge commits on `main`.
- **`docs/dev/` vs `docs/developer/` discrepancy.** The issue literally says `docs/dev/`. We are deliberately overriding the issue spec with repo convention. Noted in the PR description so reviewers do not flag it as a deviation.

## Source verification notes (per documentation-generation-checklist.md)

Every claim above has a source:

- Branch state: `git diff origin/feat/playwright-e2e origin/main -- tests/playwright/` (run 2026-04-07)
- CI job location: `grep -n playwright .github/workflows/ci.yml` on `origin/main` (lines 243–321)
- CI job authorship: commit `6711bec0` "ci: add Playwright E2E job to PR/push CI"
- Fixture contract prose: `tests/playwright/conftest.py` (on `origin/main`)
- `addopts` / `markers` / `pytest-playwright` dep: `pyproject.toml` (lines 134–136, 348–350)
- `collect_ignore_glob` gating: `tests/conftest.py` (see commit `6711bec0` for the rationale)
- Issue #1154 independence: issue body scope section + diff showing it writes new files only
