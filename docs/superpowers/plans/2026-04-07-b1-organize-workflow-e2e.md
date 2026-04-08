# B1: Organize Workflow E2E Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two browser E2E tests for the organize workflow — a happy path that observes `running → completed` with filesystem verification, and a failure path that surfaces "Input directory not found."

**Architecture:** The tests live in a new `tests/playwright/test_organize_workflow.py` module and rely on four new fixtures in `tests/playwright/conftest.py`. The conftest refactor extracts `playwright_allowed_root` (session-scoped) from inside `live_server_url` so the file-tree fixtures can share the server's allowed-paths root. AI processors are patched with slow mocks (80 ms/file) to keep the job in `running` state long enough for Playwright's `wait_for_function` to observe a non-terminal frame atomically.

**Tech Stack:** pytest-playwright, Playwright Python sync API (`Page`, `expect`, `wait_for_function`), `unittest.mock.patch`, `file_organizer.services.ProcessedFile`

---

## File structure

```
tests/playwright/
  conftest.py          ← MODIFY: add playwright_allowed_root, organize_file_tree,
                                  organize_output_dir, slow_ai_processors;
                                  refactor live_server_url to consume playwright_allowed_root
  test_organize_workflow.py  ← CREATE: happy-path + failure-path tests
```

This change modifies Playwright tests/fixtures and also includes template fixes in `src/file_organizer/web/templates/base.html` and `src/file_organizer/web/templates/marketplace/index.html`.

---

### Task 1: Create the test module (skeleton — drives TDD)

**Files:**
- Create: `tests/playwright/test_organize_workflow.py`

Write the complete test file first. It will fail at collection with `fixture 'organize_file_tree' not found` — that is the expected red state. Do not implement any fixtures yet.

- [ ] **Step 1: Write the test file**

```python
"""Browser E2E tests for the organize workflow.

Covers:
- Happy path: scan → preview → execute → running → completed + filesystem output
- Failure path: scan nonexistent dir → error banner, page does not 500
"""

from __future__ import annotations

from pathlib import Path

import pytest

try:
    from playwright.sync_api import Page, expect
except ImportError as _exc:
    raise ImportError(
        "playwright not installed — run: pip install -e '.[dev]' && playwright install chromium"
    ) from _exc

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.playwright,
    pytest.mark.timeout(60),  # browser ops + ~1.6 s job slowdown
]


def test_organize_happy_path_runs_to_completion(
    page: Page,
    organize_file_tree: Path,
    organize_output_dir: Path,
    slow_ai_processors: None,
) -> None:
    """Scan → preview → execute; observe running frame then completion; verify output files."""
    page.goto("/ui/organize")

    # 1) Fill the scan form with the fixture-provided paths
    page.locator("#organize-input-dir").fill(str(organize_file_tree))
    page.locator("#organize-output-dir").fill(str(organize_output_dir))
    page.get_by_role("button", name="Generate plan").click()

    # 2) Wait for the plan partial to render with at least one movement
    expect(page.locator("[data-plan-id]")).to_be_visible(timeout=10000)
    expect(page.locator(".plan-movements")).to_be_visible()

    # 3) Approve and execute
    page.get_by_role("button", name="Approve and execute").click()

    # 4) Atomically assert status=="running" AND 0 < progress < 100 in one
    #    browser-side JS evaluation to avoid the TOCTOU race where the panel
    #    advances to "completed" between two separate DOM reads.
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

    # 5) Wait for completion: status=="completed", progress bar at 100%
    job_panel = page.locator("[data-organize-job]")
    progress_bar = page.locator("[data-organize-job] [role='progressbar']")
    expect(job_panel).to_have_attribute("data-job-status", "completed", timeout=10000)
    expect(progress_bar).to_have_attribute("aria-valuenow", "100")

    # 6) Verify execute actually wrote files — catches a no-op execute that
    #    only updates job status without performing file operations.
    output_files = list(organize_output_dir.rglob("*"))
    assert output_files, (
        f"Happy path must write at least one file to {organize_output_dir}; "
        "output dir is empty"
    )


def test_organize_scan_with_nonexistent_path_surfaces_error(
    page: Page,
    playwright_allowed_root: Path,
    organize_output_dir: Path,
) -> None:
    """Scan a nonexistent-but-allowed path → error banner; page does not 500."""
    page.goto("/ui/organize")

    # The bogus path MUST be under playwright_allowed_root so resolve_path()
    # succeeds (it raises ValueError for paths outside allowed_paths, which the
    # scan handler catches as the generic "Failed to generate plan." rather than
    # the specific "Input directory not found." we need).
    bogus = playwright_allowed_root / "does-not-exist-xyz123"
    page.locator("#organize-input-dir").fill(str(bogus))
    page.locator("#organize-output-dir").fill(str(organize_output_dir))
    page.get_by_role("button", name="Generate plan").click()

    error_banner = page.locator("#organize-plan .banner-error")
    expect(error_banner).to_be_visible()
    expect(error_banner).to_contain_text("Input directory not found.")

    # Sanity: the page itself did not 500 — the header still renders
    expect(page.locator("h1.page-title")).to_contain_text("Organization dashboard")
```

- [ ] **Step 2: Verify collection fails with missing fixture**

```bash
pytest tests/playwright/test_organize_workflow.py \
    --collect-only \
    --override-ini='addopts=' \
    2>&1 | grep -E "ERROR|fixture|not found"
```

Expected output contains: `fixture 'organize_file_tree' not found`

---

### Task 2: Refactor `live_server_url` to consume `playwright_allowed_root`

**Files:**
- Modify: `tests/playwright/conftest.py:126-234`

Extract the session-scoped tmp dir (currently minted inline at line 176 as
`tmp = tmp_path_factory.mktemp("playwright_server")`) into a standalone
`playwright_allowed_root` fixture. Add four new imports at the top of the file.
`live_server_url` drops `tmp_path_factory` as a parameter and consumes
`playwright_allowed_root` instead. No behavioural change — same dir, same
lifetime, same `allowed_paths` value.

- [ ] **Step 1: Add new imports to the top of `tests/playwright/conftest.py`**

Find the existing import block (lines 44–62). Add after `from pathlib import Path`:

```python
import time
import uuid
from typing import Any
from unittest.mock import patch
```

And add after the `pytest` import:

```python
from file_organizer.services import ProcessedFile
```

The full updated import block (lines 44–62 in the current file) becomes:

```python
from __future__ import annotations

import os
import socket
import threading
import time
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from file_organizer.services import ProcessedFile

try:
    from playwright.sync_api import Page
except ImportError as exc:
    raise ImportError(
        "Playwright is required to run the desktop E2E tests. "
        "Install it with: pip install playwright && "
        "playwright install chromium  # or firefox, or webkit"
    ) from exc
```

- [ ] **Step 2: Add `playwright_allowed_root` fixture immediately before `live_server_url`**

Insert after line 123 (after `playwright_config_dir` fixture ends, before the blank line
and `live_server_url`):

```python
@pytest.fixture(scope="session")
def playwright_allowed_root(
    tmp_path_factory: pytest.TempPathFactory,
) -> Path:
    """Session-scoped root the live server allows. Shared with file-tree fixtures.

    Extracted from the inline ``tmp = tmp_path_factory.mktemp("playwright_server")``
    that was previously inside ``live_server_url``.  Exposing it as a named fixture
    lets B-series test fixtures build file trees inside the server's allowed-paths
    root without reopening or inspecting ``live_server_url``'s internals.
    """
    return tmp_path_factory.mktemp("playwright_server")
```

- [ ] **Step 3: Update `live_server_url` signature and body**

Replace the current `live_server_url` signature (line 126–130):

```python
@pytest.fixture(scope="session")
def live_server_url(
    tmp_path_factory: pytest.TempPathFactory,
    playwright_config_dir: Path,
) -> Iterator[str]:
```

With:

```python
@pytest.fixture(scope="session")
def live_server_url(
    playwright_config_dir: Path,
    playwright_allowed_root: Path,
) -> Iterator[str]:
```

Then inside the body, replace lines 176–181 (the block that mints `tmp`):

```python
        tmp = tmp_path_factory.mktemp("playwright_server")
        settings = ApiSettings(
            allowed_paths=[str(tmp)],
            auth_enabled=False,
            auth_db_path=str(tmp / "auth.db"),
        )
```

With:

```python
        settings = ApiSettings(
            allowed_paths=[str(playwright_allowed_root)],
            auth_enabled=False,
            auth_db_path=str(playwright_allowed_root / "auth.db"),
        )
```

- [ ] **Step 4: Verify existing Playwright suite still collects cleanly**

```bash
pytest tests/playwright/ \
    --collect-only \
    --override-ini='addopts=' \
    2>&1 | tail -5
```

Expected: all existing tests listed, no errors.

- [ ] **Step 5: Commit the refactor**

```bash
git add tests/playwright/conftest.py
git commit -m "refactor(playwright): extract playwright_allowed_root from live_server_url

Exposes the server's allowed-paths root as a named session fixture so
B-series file-tree fixtures can build inside it without touching
live_server_url internals. No behaviour change.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 3: Add `organize_file_tree` and `organize_output_dir` fixtures

**Files:**
- Modify: `tests/playwright/conftest.py` (append after the `base_url` fixture, before the pywebview section)

Add a new section for organize-specific fixtures. The section starts with a module-level
constant for the minimal-valid PNG stub and the two new fixtures.

- [ ] **Step 1: Add the minimal-PNG constant and two fixtures**

In `tests/playwright/conftest.py`, locate the line that starts:

```python
# ---------------------------------------------------------------------------
# pywebview mock fixture
# ---------------------------------------------------------------------------
```

Insert the following block immediately before that section (after `base_url`):

```python
# ---------------------------------------------------------------------------
# Organize workflow fixtures
# ---------------------------------------------------------------------------

# Minimal valid 1×1 pixel PNG (all-white).  Enough for VisionProcessor to
# receive a real file path; the slow mock never reads the bytes.
_MINIMAL_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f"
    b"\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)

# Per-file sleep duration for the slow AI mock.  ~20 files × 0.08 s ≈ 1.6 s
# of "running" wall-clock — wide enough for Playwright's wait_for_function
# (~100 ms polling) to catch a non-terminal frame.
SLOW_AI_DELAY_S = 0.08

_TEXT_FOLDER_MAP: dict[str, str] = {
    ".txt": "documents",
    ".md": "documents",
    ".pdf": "documents",
    ".docx": "documents",
    ".csv": "spreadsheets",
    ".xlsx": "spreadsheets",
}

_IMAGE_FOLDER_MAP: dict[str, str] = {
    ".jpg": "images",
    ".jpeg": "images",
    ".png": "images",
    ".gif": "images",
    ".bmp": "images",
}


@pytest.fixture
def organize_file_tree(playwright_allowed_root: Path) -> Path:
    """Build a fresh ~20-file flat tree per test inside the server's allowed root.

    Function-scoped so each test invocation gets a clean source tree regardless
    of whether the organizer uses hardlinks, copies, or moves.  20 tiny files
    take < 1 ms to create.

    File mix: 10 .txt, 5 .md, 5 .png.  All content is deterministic.

    Returns:
        Path to the created input directory.
    """
    root = playwright_allowed_root / f"organize_input_{uuid.uuid4().hex[:8]}"
    root.mkdir(parents=True, exist_ok=True)
    for i in range(10):
        (root / f"note_{i:02d}.txt").write_text(
            f"Sample document text number {i}.\n", encoding="utf-8"
        )
    for i in range(5):
        (root / f"readme_{i:02d}.md").write_text(
            f"# Document {i}\n\nSample markdown body for file {i}.\n", encoding="utf-8"
        )
    for i in range(5):
        (root / f"photo_{i:02d}.png").write_bytes(_MINIMAL_PNG)
    return root


@pytest.fixture
def organize_output_dir(playwright_allowed_root: Path) -> Path:
    """Per-test output directory under the server's allowed root.

    Function-scoped with a uuid suffix so repeated test runs (e.g. --reruns 1)
    do not share state.

    Returns:
        Path to the created (empty) output directory.
    """
    out = playwright_allowed_root / f"organize_output_{uuid.uuid4().hex[:8]}"
    out.mkdir(parents=True, exist_ok=True)
    return out
```

- [ ] **Step 2: Verify collection — `organize_file_tree` and `organize_output_dir` resolve**

```bash
pytest tests/playwright/test_organize_workflow.py \
    --collect-only \
    --override-ini='addopts=' \
    2>&1 | grep -E "ERROR|fixture|not found"
```

Expected output contains: `fixture 'slow_ai_processors' not found` (the two new
fixtures are resolved; only `slow_ai_processors` remains missing).

---

### Task 4: Add `slow_ai_processors` fixture

**Files:**
- Modify: `tests/playwright/conftest.py` (append to the organize workflow section added in Task 3)

- [ ] **Step 1: Add `slow_ai_processors` fixture after `organize_output_dir`**

```python
@pytest.fixture
def slow_ai_processors() -> Iterator[None]:
    """Patch TextProcessor and VisionProcessor with slow deterministic mocks.

    Each ``process_file`` call sleeps ``SLOW_AI_DELAY_S`` before returning a
    ``ProcessedFile`` with a folder name derived from the file extension.  With
    ~20 files this creates a ~1.6 s "running" window that Playwright's
    ``wait_for_function`` can observe.

    Patches ``file_organizer.core.organizer.{TextProcessor,VisionProcessor}`` —
    the same import sites that ``tests/e2e/conftest.py`` patches — so the
    in-process live server's background task picks them up when it instantiates
    ``FileOrganizer`` inside ``_run_organize_job``.

    Yields:
        None.  Used as a side-effect fixture.
    """

    def _make_slow_process_file(folder_map: dict[str, str]) -> Any:
        def _process_file(file_path: Path, **kwargs: Any) -> ProcessedFile:
            threading.Event().wait(SLOW_AI_DELAY_S)
            ext = file_path.suffix.lower()
            folder = folder_map.get(ext, "general")
            return ProcessedFile(
                file_path=file_path,
                description=f"Mock description for {file_path.name}",
                folder_name=folder,
                filename=file_path.stem,
            )

        return _process_file

    with (
        patch("file_organizer.core.organizer.TextProcessor") as mock_text,
        patch("file_organizer.core.organizer.VisionProcessor") as mock_vision,
    ):
        mock_text.return_value.process_file.side_effect = _make_slow_process_file(
            _TEXT_FOLDER_MAP
        )
        mock_vision.return_value.process_file.side_effect = _make_slow_process_file(
            _IMAGE_FOLDER_MAP
        )
        yield
```

- [ ] **Step 2: Verify all fixtures resolve — no collection errors**

```bash
pytest tests/playwright/test_organize_workflow.py \
    --collect-only \
    --override-ini='addopts=' \
    2>&1 | tail -10
```

Expected: both tests listed, no `fixture not found` errors.

```
<Module test_organize_workflow.py>
  <Function test_organize_happy_path_runs_to_completion>
  <Function test_organize_scan_with_nonexistent_path_surfaces_error>
```

- [ ] **Step 3: Commit conftest additions**

```bash
git add tests/playwright/conftest.py
git commit -m "feat(playwright): add organize workflow fixtures to conftest

Adds organize_file_tree (function-scoped, ~20 files), organize_output_dir
(function-scoped, uuid-suffixed), and slow_ai_processors (patches
TextProcessor/VisionProcessor at 80 ms/file to create an observable
running window). All fixtures root under playwright_allowed_root.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 5: Run the new tests and fix any failures

**Files:**
- Modify: `tests/playwright/test_organize_workflow.py` (only if bugs surface)
- Modify: `tests/playwright/conftest.py` (only if bugs surface)

Playwright must be installed for this task. If it is not:

```bash
pip install -e ".[dev]"
playwright install chromium
```

- [ ] **Step 1: Run the failure-path test alone (no slow mocks, fast)**

```bash
pytest tests/playwright/test_organize_workflow.py \
    -k test_organize_scan_with_nonexistent_path_surfaces_error \
    --browser chromium \
    --override-ini='addopts=' \
    --strict-markers \
    --timeout=60 \
    -v
```

Expected: `PASSED`. If it fails:

- If `AssertionError: 'Input directory not found.' not in banner text` — check that `bogus` is under `playwright_allowed_root`, not `/tmp`. The scan handler calls `resolve_path()` before the existence check; a path outside `allowed_paths` surfaces "Failed to generate plan." instead.
- If the error banner is not visible — check selector `#organize-plan .banner-error` against the template at `src/file_organizer/web/templates/organize/_plan.html:5`.

- [ ] **Step 2: Run the happy-path test alone**

```bash
pytest tests/playwright/test_organize_workflow.py \
    -k test_organize_happy_path_runs_to_completion \
    --browser chromium \
    --override-ini='addopts=' \
    --strict-markers \
    --timeout=60 \
    -v
```

Expected: `PASSED`. Common failure modes:

| Symptom | Cause | Fix |
|---|---|---|
| `wait_for_function` times out at 5 s | Job completed before the JS predicate ran | Bump `SLOW_AI_DELAY_S` to 0.15 in conftest |
| `[data-plan-id]` never visible | Input/output dirs not under `allowed_paths` | Verify `playwright_allowed_root` is used |
| `output_files` is empty | AI mock not patched correctly | Check patch targets match `file_organizer.core.organizer.*` |
| `fixture 'slow_ai_processors' is None` type error | Return type annotation on fixture — fine, `None` is valid | No action needed |

- [ ] **Step 3: Run the full Playwright suite to check for regressions**

```bash
pytest tests/playwright/ \
    --browser chromium \
    --override-ini='addopts=' \
    --strict-markers \
    --timeout=60 \
    -v
```

Expected: all six tests pass (four existing + two new). Pay attention to the
existing tests — the `live_server_url` refactor must not change their behaviour.

- [ ] **Step 4: Commit the test file**

Only commit at this step if both tests pass:

```bash
git add tests/playwright/test_organize_workflow.py
git commit -m "feat(tests): add B1 organize workflow E2E tests

Happy path: scan → preview → execute → observe running (atomic
wait_for_function) → completed → filesystem output check.
Failure path: nonexistent-but-allowed path → error banner, no 500.

Closes #1154

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 6: Pre-commit and open PR

**Files:**
- No code changes in this task.

- [ ] **Step 1: Run pre-commit on all touched files**

```bash
pre-commit run --files \
    tests/playwright/conftest.py \
    tests/playwright/test_organize_workflow.py
```

Expected: all hooks pass. Common failures:

- `ruff`: unused imports, missing type annotations on inner functions — fix inline.
- `codespell`: any spell errors — fix inline.
- `pymarkdown`: not applicable (Python files).

If ruff reports `ANN` (missing annotations) on inner `_process_file`, add the return type:

```python
def _process_file(file_path: Path, **kwargs: Any) -> ProcessedFile:
```

This is already in the plan above so it should pass.

- [ ] **Step 2: Push branch and open PR**

```bash
git push -u origin feature/1154-b1-organize-workflow-e2e
```

```bash
gh pr create \
  --title "feat(tests): B1 browser E2E for the organize workflow" \
  --body "$(cat <<'EOF'
## Summary

Closes #1154 (B1 in epic #1150).

- Adds `tests/playwright/test_organize_workflow.py` with two browser E2E tests:
  - **Happy path**: scan → preview → execute; atomically observes a
    `running` frame (0 < progress < 100 via `wait_for_function`) then
    `completed` (progress == 100); asserts output files were written.
  - **Failure path**: nonexistent-but-allowed input dir → error banner
    "Input directory not found.", page does not 500.
- Refactors `tests/playwright/conftest.py` to extract `playwright_allowed_root`
  (session-scoped) from inside `live_server_url`, enabling file-tree fixtures
  to write under the server's `allowed_paths` root.
- Adds four new conftest fixtures: `playwright_allowed_root`,
  `organize_file_tree`, `organize_output_dir`, `slow_ai_processors`.

## Test plan

- [ ] CI green on all three browser legs (chromium / firefox / webkit)
- [ ] Happy-path test observes a non-terminal running frame (not just start → end)
- [ ] Output directory non-empty after completion
- [ ] Failure-path test asserts the specific "Input directory not found." message
- [ ] All four existing Playwright tests still pass (no regression from conftest refactor)
- [ ] (Post-merge) Check `#1150` child checklist; close if all children done

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Spec reference

`docs/superpowers/specs/2026-04-07-b1-organize-workflow-e2e-design.md`

Key implementation constraints documented there:

- **Atomic running assertion**: use `page.wait_for_function()` with a JS predicate, not `expect(...).to_have_attribute(...)` followed by `get_attribute()` — the latter has a TOCTOU race.
- **Failure-path bogus path**: must be under `playwright_allowed_root`, not an absolute system path, so `resolve_path()` passes and the existence check fires the specific 404 message.
- **`organize_file_tree` function-scoped**: session-scoped would rely on the `use_hardlinks` form default for source-tree safety — fragile; function-scoped is correct by construction.
- **Patch targets**: `file_organizer.core.organizer.TextProcessor` and `file_organizer.core.organizer.VisionProcessor` — same as `tests/e2e/conftest.py:330,345`.
