# B1: Browser E2E — Organize Workflow Coverage (Design)

> Issue: curdriceaurora/Local-File-Organizer#1154
> Parent epic: curdriceaurora/Local-File-Organizer#1150
> Date: 2026-04-07

## Goal

Add browser-driven E2E coverage of the core organize workflow against the
existing Playwright live server. Two tests:

1. **Happy path** — `/ui/organize` scan → preview → execute, observing
   both a non-terminal `running` frame (0 < progress < 100) **and** the
   `completed` terminal frame (progress == 100), then asserting at least
   one file was written to the output directory.
2. **Failure path** — scan against a nonexistent input dir, assert the
   error banner surfaces "Input directory not found." and the page does
   not 500.

## Scope and non-goals

**In scope (this design):**

- New module `tests/playwright/test_organize_workflow.py` with the two
  tests above.
- Conftest additions in `tests/playwright/conftest.py`:
  - Refactor: extract `playwright_allowed_root` (session-scoped) from
    the inline `tmp_path_factory.mktemp("playwright_server")` at line
    176 of `live_server_url`.
  - New `organize_file_tree` (function-scoped): builds a small ~20-file
    tree under the allowed root per test.
  - New `organize_output_dir` (function-scoped): per-test output dir.
  - New `slow_ai_processors` (function-scoped): patches `TextProcessor`
    and `VisionProcessor` with mocks that sleep ~80 ms per file.

**Out of scope (deferred to other B-series children or future work):**

- Auth-protected variants of the organize flow (B2 introduces the
  `auth_enabled=True` fixture).
- Settings persistence interactions (B3).
- Marketplace plugin interactions (B4).
- Accessibility scans of the organize page (B5).
- Performance/load assertions on organize.
- Cross-browser matrix execution (handled by the Playwright CI job
  added under epic #1149).
- Wire-protocol assertions on the SSE stream — assert at the UI level
  only.
- Real AI model invocation — always mocked for hermeticity.

## Architecture

### Test files touched

- **Create:** `tests/playwright/test_organize_workflow.py` (one module,
  two test functions, ~120 lines including docstrings).
- **Modify:** `tests/playwright/conftest.py` — add the four
  fixtures listed above and refactor `live_server_url` to consume the
  new `playwright_allowed_root` fixture instead of minting a tmp dir
  inline.

### Why these decisions

**Why patch processors at `file_organizer.core.organizer.{Text,Vision}Processor`:**
This mirrors the pattern in `tests/e2e/conftest.py:330,345`. The
in-process Playwright server imports `FileOrganizer` from
`file_organizer.core.organizer`, and `FileOrganizer.__init__`
instantiates `TextProcessor()` / `VisionProcessor()` from those module
names. Patching the same import sites guarantees the patches take
effect when the route handler's background task creates a new
`FileOrganizer` instance inside `_run_organize_job`
(`src/file_organizer/web/organize_routes.py:397`).

**Why slow the mocks instead of slowing the route helper:**
`_run_organize_job` is a private helper of `organize_routes.py`. Patching
it would couple the test to an internal name (refactor risk). Slowing
the mock processors keeps the test on the same patch surface as
existing e2e tests AND lets `processed_files / total_files` tick
realistically during the run, so the running-frame assertion exercises
the genuine progress calculation in `_build_job_view`
(`src/file_organizer/web/organize_routes.py:309-314`), not just a
status-derived constant.

**Why ~20 files at 80 ms each:**
~1.6 s of "running" wall-clock. Playwright's `expect()` polls every
~100 ms, so the running frame is observable in 16+ poll cycles. Smaller
trees (e.g., 5 files × 80 ms = 400 ms) risk the job completing
between polls; larger trees waste CI minutes. 20 is the smallest size
that gives a comfortable safety margin without bloating runtime.

**Why a separate `playwright_allowed_root` fixture:**
The current `live_server_url` mints `tmp = tmp_path_factory.mktemp("playwright_server")`
at line 176 and only exposes the resulting URL — not the path. The
file-tree fixture must write inside that allowed-paths root for the
scan to succeed. Extracting the root into its own fixture is the
minimal refactor that lets both `live_server_url` and the new
file-tree fixture share the path. The behaviour of `live_server_url`
is otherwise identical: same lifetime (session), same factory, same
directory.

**Why function-scoped `organize_file_tree`:**
A session-scoped tree would be safe only if the organize job uses
hardlinks (never mutates source files). That relies on the `use_hardlinks`
form checkbox remaining checked by default — an implicit, fragile
assumption. If the default changes or form hydration regresses, the
source tree gets mutated and later tests or reruns become
order-dependent. Function-scoped is the correct-by-construction
alternative: each test builds its own ~20 tiny-file tree (< 1 ms
overhead), the session-scope optimization is not needed for two tests,
and the correctness invariant holds regardless of form defaults.

**Why function-scoped `organize_output_dir`:**
The happy-path test writes outputs under it; running the test twice
in the same session (e.g., `pytest --reruns 1`) would otherwise see
files left over from the previous run and behave differently.
Function-scoped with a uuid suffix keeps tests order-independent and
rerun-safe.

**Why function-scoped `slow_ai_processors`:**
Session-scoped patching would slow down any other Playwright test that
incidentally invokes `FileOrganizer`. None do today, but locking the
scope to one test is the YAGNI-correct default. The failure-path test
deliberately omits this fixture because the failure happens before
any `FileOrganizer` instantiation, saving ~1.6 s.

## Fixture contracts

### `playwright_allowed_root` (session-scoped)

Returns a session-scoped tmp dir used as the live server's
`allowed_paths` root. Replaces the inline `tmp` variable currently
defined at `tests/playwright/conftest.py:176`.

```python
@pytest.fixture(scope="session")
def playwright_allowed_root(
    tmp_path_factory: pytest.TempPathFactory,
) -> Path:
    """Session-scoped root the live server allows. Shared with file-tree fixtures."""
    return tmp_path_factory.mktemp("playwright_server")
```

`live_server_url` is updated to take this as a parameter and use it
where it currently mints its own. No other behaviour changes.

### `organize_file_tree` (function-scoped)

Builds a ~20-file flat tree under a per-test subdirectory of
`playwright_allowed_root` and yields the path. File mix:

- 10 `.txt` files with deterministic faker-seeded text
- 5 `.md` files with short markdown content
- 5 `.png` files (minimal valid PNG byte stub)

Total payload < 50 KB per test. Function-scoped so the source tree is
never shared between tests — correctness holds regardless of whether
hardlinks, copies, or moves are used during execution.

```python
@pytest.fixture
def organize_file_tree(playwright_allowed_root: Path) -> Path:
    root = playwright_allowed_root / f"organize_input_{uuid.uuid4().hex[:8]}"
    root.mkdir(parents=True, exist_ok=True)
    # ... write 20 files deterministically
    return root
```

### `organize_output_dir` (function-scoped)

Returns a per-test output directory under `playwright_allowed_root`,
suffixed with a uuid hex to avoid collisions across tests.

```python
@pytest.fixture
def organize_output_dir(playwright_allowed_root: Path) -> Path:
    out = playwright_allowed_root / f"organize_output_{uuid.uuid4().hex[:8]}"
    out.mkdir(parents=True, exist_ok=True)
    return out
```

### `slow_ai_processors` (function-scoped)

Patches `file_organizer.core.organizer.TextProcessor` and
`VisionProcessor` with mock instances whose `process_file` sleeps
`SLOW_AI_DELAY_S` (constant, 0.08) before returning a deterministic
`ProcessedFile`. The deterministic mapping mirrors
`tests/e2e/conftest.py:_TEXT_FOLDER_MAP` / `_IMAGE_FOLDER_MAP`.

```python
SLOW_AI_DELAY_S = 0.08

@pytest.fixture
def slow_ai_processors() -> Iterator[None]:
    with patch("file_organizer.core.organizer.TextProcessor") as mock_text, \
         patch("file_organizer.core.organizer.VisionProcessor") as mock_vision:
        # configure mock_text.return_value.process_file.side_effect to sleep + return ProcessedFile
        # configure mock_vision similarly
        yield
```

The patches are active for the entire test body, including the
Playwright `expect()` waits for the `running` and `completed` frames.

## Test bodies

### Test 1: happy path

```python
def test_organize_happy_path_runs_to_completion(
    page: Page,
    live_server_url: str,
    organize_file_tree: Path,
    organize_output_dir: Path,
    slow_ai_processors: None,
) -> None:
    page.goto("/ui/organize")

    # Fill scan form and submit
    page.locator("#organize-input-dir").fill(str(organize_file_tree))
    page.locator("#organize-output-dir").fill(str(organize_output_dir))
    page.get_by_role("button", name="Generate plan").click()

    # Wait for plan partial
    expect(page.locator("[data-plan-id]")).to_be_visible()
    expect(page.locator(".plan-movements")).to_be_visible()

    # Approve and execute
    page.get_by_role("button", name="Approve and execute").click()

    # Running frame: atomically assert status=="running" AND 0 < progress < 100
    # in a single JS evaluation to avoid the TOCTOU race where the panel
    # advances to "completed" between a status read and a progress read.
    page.wait_for_function(
        """() => {
            const panel = document.querySelector('[data-organize-job]');
            if (!panel) return false;
            const status = panel.getAttribute('data-job-status');
            const bar = panel.querySelector('[role="progressbar"]');
            const pct = parseInt(bar?.getAttribute('aria-valuenow') || '0', 10);
            return status === 'running' && pct > 0 && pct < 100;
        }""",
        timeout=5000,
    )

    # Completion: status=="completed" and progress==100
    progress_bar = page.locator("[data-organize-job] [role='progressbar']")
    job_panel = page.locator("[data-organize-job]")
    expect(job_panel).to_have_attribute("data-job-status", "completed", timeout=10000)
    expect(progress_bar).to_have_attribute("aria-valuenow", "100")

    # Verify execution actually wrote files — guards against a no-op execute
    # that only updates job status without performing any file operations.
    output_files = list(organize_output_dir.rglob("*"))
    assert output_files, (
        f"Happy path must write at least one file to {organize_output_dir}; output dir is empty"
    )
```

### Test 2: failure path

```python
def test_organize_scan_with_nonexistent_path_surfaces_error(
    page: Page,
    live_server_url: str,
    playwright_allowed_root: Path,
    organize_output_dir: Path,
) -> None:
    page.goto("/ui/organize")

    # Must be under allowed_paths so resolve_path() succeeds; then the
    # existence check fires and yields the 404 "Input directory not found."
    # An absolute path outside allowed_paths would raise ValueError from
    # resolve_path, get caught by the broad `except Exception`, and surface
    # the generic "Failed to generate plan." instead.
    bogus = playwright_allowed_root / "does-not-exist-xyz123"
    page.locator("#organize-input-dir").fill(str(bogus))
    page.locator("#organize-output-dir").fill(str(organize_output_dir))
    page.get_by_role("button", name="Generate plan").click()

    error_banner = page.locator("#organize-plan .banner-error")
    expect(error_banner).to_be_visible()
    expect(error_banner).to_contain_text("Input directory not found.")

    # Sanity: page didn't 500
    expect(page.locator("h1.page-title")).to_contain_text("Organization dashboard")
```

Notes:

- `expect(...).to_have_attribute(...)` auto-retries until the per-call
  timeout, so it naturally polls the DOM as HTMX swaps in fresh
  `_job_status.html` partials and as the SSE handler updates
  attributes.
- The 5 s and 10 s timeouts are per-assertion. The module-level
  `pytest.mark.timeout(60)` is the safety net for the whole test.
- The failure test deliberately does not request `slow_ai_processors`
  because the failure path never instantiates `FileOrganizer`.

## Markers

Module-level (matching the canonical block in
`tests/playwright/test_smoke.py:41-45`):

```python
pytestmark = [
    pytest.mark.e2e,
    pytest.mark.playwright,
    pytest.mark.timeout(60),  # browser ops + ~1.6s job slowdown
]
```

## Gotchas

### Race condition between "running" and "completed"

With `SLOW_AI_DELAY_S = 0.08` and ~20 files, the running window is
~1.6 s. The two-step pattern of "wait for `data-job-status=running`
then read `aria-valuenow`" has a TOCTOU race: the DOM can advance to
`completed` between those two operations.

**Resolved by `page.wait_for_function()`:** The JS predicate reads
`data-job-status` and `aria-valuenow` in a single browser-side
evaluation. The browser event loop cannot swap the DOM between two
reads inside one JS function call, so the assertion is atomic.

If a CI runner is so overloaded that the entire ~1.6 s window
elapses between two `wait_for_function` polls (~100 ms apart), the
function would never return `true` and the test would time out at 5 s
rather than pass with a wrong result. That is a test failure, not a
false positive. If this timeout occurs in practice, bump
`SLOW_AI_DELAY_S` to 0.15.

### HTMX polling vs SSE

The job-status partial uses both HTMX `hx-trigger` polling and an
`EventSource` declared in `src/file_organizer/web/static/js/app.js`
around line 58. Either transport keeps `data-job-status` and
`aria-valuenow` fresh. The test asserts only on the resulting DOM
state, not on which transport delivered the update.

### Mock patch lifetime

The Playwright live server runs in the same Python process as the
test, so `with patch("file_organizer.core.organizer.TextProcessor")`
does affect the background task spawned by `/ui/organize/execute`. The
patch must be active **before** the click on "Approve and execute"
and remain active **until** the `completed` frame is observed. The
function-scoped `slow_ai_processors` fixture wraps the entire test
body, satisfying both requirements automatically.

### Source-tree and output-dir isolation

Both `organize_file_tree` and `organize_output_dir` are
function-scoped with unique suffixes. Each test invocation gets a
fresh input tree and a fresh output dir, so no assumptions about
`use_hardlinks` form defaults or execution mode affect correctness.
Inter-test interference is structurally impossible.

### Refactor blast radius on `live_server_url`

Extracting `playwright_allowed_root` is structural only — same
factory call, same lifetime, same directory. The four existing
Playwright test modules
(`test_smoke.py`, `test_setup_wizard_flow.py`,
`test_file_browser_desktop.py`, `test_desktop_api_contract.py`) all
consume only `live_server_url` / `base_url` / `page` and do not
reference the inline tmp path. We verify by running the existing
suite once after the refactor lands.

## Verification plan

1. Run the new module alone:

   ```bash
   pytest tests/playwright/test_organize_workflow.py \
       --browser chromium \
       --override-ini='addopts=' \
       --strict-markers \
       --timeout=60
   ```

2. Run the full Playwright suite to confirm the conftest refactor
   does not regress existing tests:

   ```bash
   pytest tests/playwright/ \
       --browser chromium \
       --override-ini='addopts=' \
       --strict-markers \
       --timeout=60
   ```

3. Lint touched files with pymarkdown:

   ```bash
   pymarkdown --config .pymarkdown.json scan \
       docs/superpowers/specs/2026-04-07-b1-organize-workflow-e2e-design.md
   ```

4. Pre-commit on touched files (note: project's
   `pre-commit-validation.sh` requires bash 4+, which is not present
   on macOS by default — fall back to `pre-commit run --files` directly):

   ```bash
   pre-commit run --files \
       tests/playwright/test_organize_workflow.py \
       tests/playwright/conftest.py
   ```

## Definition of done

- New module `tests/playwright/test_organize_workflow.py` exists with
  both test functions.
- Conftest additions land: `playwright_allowed_root`,
  `organize_file_tree` (function-scoped), `organize_output_dir`,
  `slow_ai_processors`.
- `live_server_url` is refactored to consume `playwright_allowed_root`
  with no behavioural change.
- Both new tests pass against chromium locally.
- The full Playwright suite still passes (no regression in the four
  existing modules).
- Pre-commit hooks pass on the touched files.
- The PR description references curdriceaurora/Local-File-Organizer#1154
  and the parent epic #1150.
