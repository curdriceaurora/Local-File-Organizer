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

**Pre-deletion verification (all four checks required before running the push).** A path-limited diff is insufficient — the branch must be proven to carry no forward progress anywhere in the tree, not just under `tests/playwright/`.

1. **Commit range is small and fully enumerated.**
   `git log --oneline origin/main..origin/feat/playwright-e2e` must list exactly the 6 commits documented in Appendix A below and nothing else. If the count differs, stop and re-investigate — someone pushed to the branch after this spec was written.
2. **Playwright content on main is a content superset of the branch.**
   `git diff --stat origin/feat/playwright-e2e origin/main -- tests/playwright/` must show only additions in main (no "branch-has-more" rows). The new `conftest.py`, `test_smoke.py`, and the three new test files that exist on main confirm this.
3. **Every file that appears on the branch but not on main must be accounted for as a stale pre-refactor artifact, not forward progress.**
   Run `comm -23 <(git ls-tree -r --name-only origin/feat/playwright-e2e | sort) <(git ls-tree -r --name-only origin/main | sort)` and for each result confirm it falls into one of: (a) `.claude/rules/*-generation-patterns.md` — moved to `.claude/patterns/` in commit `181eb6d2` "chore(rules): streamline .claude rules and move patterns to lookup-only"; (b) other `.claude/` files removed or relocated by that same refactor; (c) any other file — must be individually justified. If anything in this list cannot be tied to a known main-side refactor, **abort deletion** and escalate.
4. **Dependent-work check.** #1154 (B1) writes a new file (`tests/playwright/test_organize_workflow.py`) and consumes fixtures already on `main` (`live_server_url`, `base_url`, `pywebview_mock`, `playwright_config_dir`). It has no dependency on the stale branch — verified by reading the issue body.

Document all four checks in the PR description so reviewers can re-run them, and include the actual command output (not paraphrased) for the commit range and the file-set diff. Deletion runs only after reviewer approval, not as part of the docs commit.

See Appendix A for the full evidence captured at spec-write time.

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
4. **Fixture contract: `playwright_config_dir`**
   - Scope: session.
   - What it does: returns a per-session `tmp_path` used as `XDG_CONFIG_HOME` by `live_server_url`, isolating the server's `ConfigManager` from the developer's real `~/.config/file-organizer`. Defined at `tests/playwright/conftest.py:117`.
   - Why it matters for test authors: tests that need to *reset* or *mutate* persistent config between actions (e.g. wiping `config.yaml` to force a fresh setup-wizard flow, as `test_setup_wizard_flow.py:100` does) must write to or delete files under `playwright_config_dir / "file-organizer"`, not the real home dir.
   - Reference code: the `config.yaml` deletion pattern used in `test_setup_wizard_flow.py` is the canonical way to reset state mid-session.

5. **Fixture contract: `live_server_url`**
   - Scope: session.
   - What it does: starts the FastAPI app in-process on a random free port in a daemon thread; depends on `playwright_config_dir` to get its isolated config home; monkeypatches `file_organizer.config.manager.DEFAULT_CONFIG_DIR` before importing API modules so the module-level constant captures the tmp dir; constructs `ApiSettings(auth_enabled=False, allowed_paths=[tmp])`; waits up to 20s for the port to accept connections; tears down via `server.should_exit` on fixture exit (with `try/finally` to restore environment variables even on startup failure).
   - How to override settings: point at the `live_server_url` body in `tests/playwright/conftest.py` as the reference; explain that it is session-scoped so tests cannot override per-test (that is a deliberate constraint — per-test API would force a server restart per test and tank wall-clock). Note the forward pointer: **B2 will add an `auth_enabled=True` variant** as a separate session fixture; this doc will be updated when that lands.
   - The companion `base_url` fixture: overrides `pytest-playwright`'s built-in so `page.goto("/ui/files")` resolves to the live server.
6. **Fixture contract: `pywebview_mock`**
   - Scope: function (per-test).
   - What it does: injects a stub `window.pywebview.api` via `page.add_init_script()` before any navigation; setting `window.pywebview` triggers `desktop_api.js` to flip `document.body.dataset.desktopApp = "1"`, which enables `[data-desktop-only]` elements.
   - Returned handle (`PywebviewMockHandle`): lists the mutator methods (`set_browse_directory_result`, `set_browse_file_result`, `set_save_file_result`, `set_open_path_result`) and the observer (`get_open_path_calls`) with one-line descriptions copied from the docstrings.
   - Caveat: mock state lives in `window.__mockPyw` and resets on every navigation because `add_init_script` re-runs for each page load.
7. **Adding a new test**
   - File naming: `tests/playwright/test_<feature>.py`.
   - **Markers: apply BOTH `e2e` and `playwright` at module level via `pytestmark`.** This is the existing convention (verified across all four current test modules: `test_smoke.py:41-44`, `test_setup_wizard_flow.py:25-28`, `test_file_browser_desktop.py:25-28`, `test_desktop_api_contract.py:29-32`). The `e2e` marker keeps the suite visible to `-m "integration or e2e"` workflows and keeps `docs/developer/testing.md`'s taxonomy consistent; the `playwright` marker is what the CI job selects and what `tests/conftest.py`'s `collect_ignore_glob` gate keys off. Omitting either marker silently breaks one of those two workflows.
   - Import pattern: use the `page` fixture from `pytest-playwright` and any of the session fixtures above.
   - Minimal skeleton (copy verbatim from `tests/playwright/test_smoke.py` during implementation to guarantee it tracks the real template — do not hand-transcribe):

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

   - Pointer to `test_smoke.py` as the canonical template.
8. **Gotchas**
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
- **Branch deletion is irreversible.** A naive path-limited diff is not sufficient evidence; Deliverable 1 now requires four explicit checks (commit range enumeration, `tests/playwright/` superset check, file-level accounting of every branch-only path against known main-side refactors, dependent-work check) all captured in the PR description. The 6 branch commits cannot be patch-matched against `main` via `git cherry` because PR #1113 landed as a squash — so `git cherry -v origin/main origin/feat/playwright-e2e` will report all 6 as `+` (unmerged) even though their content is absorbed in the squashed commit. That is expected and does not invalidate the other checks. If deletion turns out to be wrong after the fact, the commits remain reachable via GitHub's reflog for ~90 days.
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
- Fixture surface (`playwright_config_dir`, `live_server_url`, `base_url`, `pywebview_mock`): `tests/playwright/conftest.py` on `origin/main` (lines 103–291)
- Marker convention: `pytestmark = [pytest.mark.e2e, pytest.mark.playwright]` at module level in all four current test files — verified by grep on `origin/main`
- Branch staleness evidence: captured in Appendix A

---

## Appendix A — Branch-deletion evidence (captured 2026-04-07)

### A.1 Commit range (branch ahead of main by 6 commits, none patch-equivalent via `git cherry`)

```text
$ git log --oneline origin/main..origin/feat/playwright-e2e
b40b0fef fix: route-specific assertions in TestPageLoads + opt-in playwright collection
b5ed040c refactor(e2e): parametrize test_pages_share_consistent_html_structure
31c47af1 fix: address unresolved CodeRabbit threads on playwright smoke suite
ac37f074 fix: address ruff lint/format failures and review comments (round 2)
28d9c24f fix: address CI failures and PR review findings for playwright E2E branch
2fd089f2 feat(e2e): add Playwright browser smoke test suite
```

### A.2 `tests/playwright/` — main is a strict content superset

```text
$ git diff --stat origin/feat/playwright-e2e origin/main -- tests/playwright/
 tests/playwright/conftest.py                  | 286 ++++++++++++++++++++------
 tests/playwright/test_desktop_api_contract.py | 105 ++++++++++
 tests/playwright/test_file_browser_desktop.py |  77 +++++++
 tests/playwright/test_setup_wizard_flow.py    | 165 +++++++++++++++
 tests/playwright/test_smoke.py                |  25 ++-
 5 files changed, 594 insertions(+), 64 deletions(-)
```

Three of the five files (`test_desktop_api_contract.py`, `test_file_browser_desktop.py`, `test_setup_wizard_flow.py`) exist only on main. `conftest.py` on main adds the `playwright_config_dir` fixture, environment isolation, cross-browser docstring, and try/finally cleanup — none of which exist on the branch. `test_smoke.py` gains the module-level `pytestmark` list on main.

### A.3 Files that exist on the branch but not on main — all stale pre-refactor artifacts

`comm -23 <(git ls-tree -r --name-only origin/feat/playwright-e2e | sort) <(git ls-tree -r --name-only origin/main | sort)` returned 43 files, grouped:

- `.claude/rules/{ci,docs,feature,search,test}-generation-patterns.md` — moved to `.claude/patterns/` by commit `181eb6d2` "chore(rules): streamline .claude rules and move patterns to lookup-only".
- `.claude/rules/documentation-quality-workflow.md`, `.claude/rules/documentation-verification.md`, `.claude/rules/pr-workflow-conformance.md`, `.claude/rules/pr-workflow-state-machine.md` — superseded by consolidated rules under `.claude/rules/` on main in the same streamline commit.
- `.claude/PROCESS-SETUP.md`, `.claude/TOMORROW-QUICK-START.md`, `.claude/bin/docker-compose-*.sh`, `.claude/context/*`, `.claude/launch.json`, `.claude/prds/*`, `.claude/patterns/*` (duplicate old paths) — removed during the streamline refactor.
- `desktop/package.json` and related `desktop/` files — main removed the Tauri v2 shell in commit `183813d5` "chore(desktop): remove Tauri v2 shell and sidecar architecture (#1118)".
- Remaining entries (scripts, docs, old test helpers): all match the "main intentionally removed/relocated" pattern from the same two refactor commits above.

No file in this list represents forward progress unique to the branch. Implementation will re-run the `comm` command immediately before pushing the delete and paste its output into the PR description so a reviewer can verify nothing new has appeared.

### A.4 `git cherry` sanity check (expected all-`+` because of squash merge)

```text
$ git cherry -v origin/main origin/feat/playwright-e2e
+ 2fd089f2 feat(e2e): add Playwright browser smoke test suite
+ 28d9c24f fix: address CI failures and PR review findings for playwright E2E branch
+ ac37f074 fix: address ruff lint/format failures and review comments (round 2)
+ 31c47af1 fix: address unresolved CodeRabbit threads on playwright smoke suite
+ b5ed040c refactor(e2e): parametrize test_pages_share_consistent_html_structure
+ b40b0fef fix: route-specific assertions in TestPageLoads + opt-in playwright collection
```

All six marked `+` (no patch-id equivalent on main). This is the expected result for a squash merge — PR #1113 landed as one squashed commit on main whose content combines all six branch commits, so individual patch-ids do not match. A.2 and A.3 together are the substantive proof; A.4 is recorded only to preempt a reviewer running `git cherry` and being misled.
