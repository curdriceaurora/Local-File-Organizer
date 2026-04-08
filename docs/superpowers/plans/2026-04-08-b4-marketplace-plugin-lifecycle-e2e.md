# B4: Marketplace Plugin Lifecycle E2E Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `tests/playwright/test_marketplace_lifecycle.py` with two browser E2E tests covering the `/ui/marketplace` plugin install → uninstall round-trip.

**Architecture:** A function-scoped `_marketplace_service` fixture seeds a real local stub plugin repo in `tmp_path`, instantiates a real `MarketplaceService` against it, and patches the `_service()` factory in `file_organizer.web.marketplace_routes` so the in-process live server uses the seeded data for the duration of each test. Two tests verify: (1) the listing page shows the stub plugin with an Install button, and (2) clicking Install then Uninstall completes the round-trip and leaves the UI in the original state.

**Tech Stack:** pytest-playwright (Page, expect), unittest.mock.patch, zipfile, file_organizer.plugins.marketplace (MarketplaceService, compute_sha256)

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| **Create** | `tests/playwright/test_marketplace_lifecycle.py` | Fixture + two B4 tests |

No production code changes. No conftest.py changes (all needed fixtures already exist).

---

### Task 1: Write the module skeleton, imports, and `_marketplace_service` fixture

**Files:**
- Create: `tests/playwright/test_marketplace_lifecycle.py`

- [ ] **Step 1: Create the file**

```python
"""Browser E2E tests for plugin marketplace lifecycle (B4).

Verifies the /ui/marketplace UI: listing plugins, installing one (the
"enable" step), and uninstalling it (the "disable" step).

Stub plugin
-----------
All tests use ``fo-test-echo`` — a minimal no-op plugin whose archive is
created on disk inside ``tmp_path`` by the ``_marketplace_service`` fixture.
This guarantees a stable, predictable target with no dependency on a live
marketplace server.

The ``_marketplace_service`` fixture patches
``file_organizer.web.marketplace_routes._service`` so the in-process live
server (started by the session-scoped ``live_server_url`` fixture in
conftest.py) resolves to a ``MarketplaceService`` backed by a real but
isolated local repo directory.  State written during a test (installed.json)
lives inside ``tmp_path`` and is discarded when the fixture tears down.

Auth
----
``authed_page`` (from conftest.py) is used because the live server runs with
``auth_enabled=True``.  The marketplace web routes carry no explicit auth
guard today, but using an authenticated page is forward-safe and matches the
issue requirement.

Running
-------
    pytest tests/playwright/test_marketplace_lifecycle.py \\
        --browser chromium --override-ini='addopts='
"""

from __future__ import annotations

import json
import zipfile
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest

from file_organizer.plugins.marketplace import MarketplaceService, compute_sha256

try:
    from playwright.sync_api import Page, expect
except ImportError as exc:
    raise ImportError(
        "Playwright is required: pip install playwright && playwright install chromium"
    ) from exc

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.playwright,
    pytest.mark.timeout(60),
]

_LOCATOR_TIMEOUT_MS = 10_000
_STUB_PLUGIN_NAME = "fo-test-echo"
_STUB_PLUGIN_VERSION = "1.0.0"

_PLUGIN_PY = "\n".join(
    [
        "from file_organizer.plugins import Plugin, PluginMetadata",
        "",
        "class EchoPlugin(Plugin):",
        "    def get_metadata(self):",
        f"        return PluginMetadata(name='{_STUB_PLUGIN_NAME}', version='{_STUB_PLUGIN_VERSION}', author='tests', description='plugin')",
        "    def on_load(self): pass",
        "    def on_enable(self): pass",
        "    def on_disable(self): pass",
        "    def on_unload(self): pass",
    ]
)


@pytest.fixture
def _marketplace_service(tmp_path: Path) -> Iterator[str]:
    """Seed a real local stub plugin repo and patch the marketplace _service() factory.

    Creates a self-contained marketplace home directory inside ``tmp_path``:
    - ``home/repository/`` contains ``fo-test-echo-1.0.0.zip`` and ``index.json``
    - ``home/`` is the MarketplaceService home (installed.json lands here)

    Patches ``file_organizer.web.marketplace_routes._service`` so that every
    request handled by the in-process live server during the test receives a
    real ``MarketplaceService`` backed by the seeded repo.

    Yields:
        The stub plugin name (``"fo-test-echo"``).
    """
    home = tmp_path / "home"
    home.mkdir()
    repo_dir = home / "repository"
    repo_dir.mkdir()

    archive_name = f"{_STUB_PLUGIN_NAME}-{_STUB_PLUGIN_VERSION}.zip"
    archive_path = repo_dir / archive_name
    with zipfile.ZipFile(archive_path, "w") as zf:
        zf.writestr("plugin.py", _PLUGIN_PY)

    metadata = {
        "name": _STUB_PLUGIN_NAME,
        "version": _STUB_PLUGIN_VERSION,
        "author": "tests",
        "description": f"{_STUB_PLUGIN_NAME} plugin",
        "homepage": "https://example.invalid",
        "download_url": archive_name,
        "checksum_sha256": compute_sha256(archive_path),
        "size_bytes": archive_path.stat().st_size,
        "dependencies": [],
        "tags": ["utility"],
        "category": "utility",
        "license": "MIT",
        "min_organizer_version": "2.0.0",
        "max_organizer_version": None,
        "downloads": 0,
        "rating": 0.0,
        "reviews_count": 0,
    }
    (repo_dir / "index.json").write_text(
        json.dumps({"plugins": [metadata]}, indent=2), encoding="utf-8"
    )

    service = MarketplaceService(home_dir=home, repo_url=str(repo_dir))

    with patch(
        "file_organizer.web.marketplace_routes._service",
        return_value=service,
    ):
        yield _STUB_PLUGIN_NAME
```

- [ ] **Step 2: Verify the module imports cleanly (no Playwright browser needed)**

```bash
python -c "import tests.playwright.test_marketplace_lifecycle"
```

Expected: no output, exit code 0. If `ModuleNotFoundError` for playwright, install it:
`pip install playwright && playwright install chromium`.

- [ ] **Step 3: Commit the skeleton**

```bash
git add tests/playwright/test_marketplace_lifecycle.py
git commit -m "test(playwright): B4 — marketplace lifecycle fixture skeleton"
```

---

### Task 2: Add `test_marketplace_page_lists_stub_plugin`

**Files:**
- Modify: `tests/playwright/test_marketplace_lifecycle.py` (append test)

- [ ] **Step 1: Append the test to the file**

Add this after the fixture:

```python


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_marketplace_page_lists_stub_plugin(
    authed_page: Page,
    _marketplace_service: str,
) -> None:
    """Marketplace page should list the seeded stub plugin with an Install button.

    Verifies that:
    - /ui/marketplace returns a page with a plugin table
    - ``fo-test-echo`` appears in the table
    - The row shows an Install button (plugin not yet installed)
    """
    plugin_name = _marketplace_service

    authed_page.goto("/ui/marketplace")
    authed_page.locator("#plugins-tbody").wait_for(
        state="visible", timeout=_LOCATOR_TIMEOUT_MS
    )

    row = authed_page.locator("#plugins-tbody tr", has_text=plugin_name)
    expect(row).to_be_visible()
    expect(row.get_by_role("button", name="Install")).to_be_visible()
```

- [ ] **Step 2: Run the test**

```bash
pytest tests/playwright/test_marketplace_lifecycle.py::test_marketplace_page_lists_stub_plugin \
    --browser chromium --override-ini='addopts=' -v
```

Expected output (abbreviated):

```
PASSED tests/playwright/test_marketplace_lifecycle.py::test_marketplace_page_lists_stub_plugin
```

If `FAILED` with "no element found matching #plugins-tbody": the page rendered without
the stub plugin — check that `_service` is being patched before the page request arrives.
Add `page.pause()` temporarily and inspect the rendered HTML.

- [ ] **Step 3: Commit**

```bash
git add tests/playwright/test_marketplace_lifecycle.py
git commit -m "test(playwright): B4 — assert stub plugin listed on marketplace page"
```

---

### Task 3: Add `test_install_uninstall_round_trip`

**Files:**
- Modify: `tests/playwright/test_marketplace_lifecycle.py` (append test)

- [ ] **Step 1: Append the round-trip test**

Add this after `test_marketplace_page_lists_stub_plugin`:

```python


def test_install_uninstall_round_trip(
    authed_page: Page,
    _marketplace_service: str,
) -> None:
    """Install then uninstall the stub plugin — the B4 enable → disable round-trip.

    Install phase:
    - Clicks Install on the fo-test-echo row
    - Waits for the flash message (confirms server wrote installed.json)
    - Asserts the row now shows Uninstall (not Install)

    Uninstall phase:
    - Clicks Uninstall on the fo-test-echo row
    - Waits for the flash message again
    - Asserts the row shows Install again (plugin removed from installed.json)

    HTMX swap note: clicking Install/Uninstall triggers hx-post which replaces
    the entire #main element.  Playwright locators re-evaluate lazily so the
    ``row`` locator is re-acquired after each swap by calling
    ``authed_page.locator(...)`` again.
    """
    plugin_name = _marketplace_service

    authed_page.goto("/ui/marketplace")
    row = authed_page.locator("#plugins-tbody tr", has_text=plugin_name)
    row.wait_for(state="visible", timeout=_LOCATOR_TIMEOUT_MS)

    # --- Install phase ---
    row.get_by_role("button", name="Install").click()
    # Flash message confirms the server handled the POST and re-rendered #main.
    authed_page.locator("p.organize-hint").wait_for(
        state="visible", timeout=_LOCATOR_TIMEOUT_MS
    )
    # Re-acquire row locator: HTMX replaced #main, old DOM nodes are gone.
    row = authed_page.locator("#plugins-tbody tr", has_text=plugin_name)
    expect(row.get_by_role("button", name="Uninstall")).to_be_visible()
    expect(row.get_by_role("button", name="Install")).not_to_be_visible()

    # --- Uninstall phase ---
    row.get_by_role("button", name="Uninstall").click()
    authed_page.locator("p.organize-hint").wait_for(
        state="visible", timeout=_LOCATOR_TIMEOUT_MS
    )
    row = authed_page.locator("#plugins-tbody tr", has_text=plugin_name)
    expect(row.get_by_role("button", name="Install")).to_be_visible()
    expect(row.get_by_role("button", name="Uninstall")).not_to_be_visible()
```

- [ ] **Step 2: Run the new test**

```bash
pytest tests/playwright/test_marketplace_lifecycle.py::test_install_uninstall_round_trip \
    --browser chromium --override-ini='addopts=' -v
```

Expected:

```
PASSED tests/playwright/test_marketplace_lifecycle.py::test_install_uninstall_round_trip
```

Failure modes and debugging:
- `TimeoutError` on `p.organize-hint`: the Install POST failed or the flash message selector is wrong. Check the rendered HTML with `authed_page.content()` after the click.
- Uninstall button not visible after install: the HTMX swap may not have completed. Increase `_LOCATOR_TIMEOUT_MS` to `20_000` temporarily to rule out slow CI.
- `checksum mismatch` error from MarketplaceService: `compute_sha256` was called before the zip was fully written — ensure it's called after the `with zipfile.ZipFile(...)` block closes.

- [ ] **Step 3: Run both tests together to verify no interaction**

```bash
pytest tests/playwright/test_marketplace_lifecycle.py \
    --browser chromium --override-ini='addopts=' -v
```

Expected: 2 passed.

- [ ] **Step 4: Commit**

```bash
git add tests/playwright/test_marketplace_lifecycle.py
git commit -m "test(playwright): B4 — marketplace plugin install/uninstall round-trip"
```

---

### Task 4: Regression run, quality gates, and pr-prep

**Files:** none — verification only

- [ ] **Step 1: Run the full playwright suite (chromium) to check for regressions**

```bash
pytest tests/playwright/ --browser chromium --override-ini='addopts=' -v
```

Expected: all existing tests pass alongside the 2 new ones. If any pre-existing test
fails, it is a pre-existing issue — note it but do not fix it in this branch.

- [ ] **Step 2: Run pre-commit validation**

```bash
bash .claude/scripts/pre-commit-validation.sh
```

Expected: all checks pass. Fix any lint/format/type issues before continuing.

- [ ] **Step 3: Run pr-prep**

```bash
/pr-prep
```

Follow the pr-prep output. Address any blocking findings before creating the PR.

- [ ] **Step 4: Update the #1150 child checklist**

After the PR is approved and merged, mark B4 done in the epic:

```bash
gh issue view 1150 --repo curdriceaurora/Local-File-Organizer
# Edit the checklist to mark #1157 complete, then close #1157
gh issue close 1157 --repo curdriceaurora/Local-File-Organizer \
    --comment "Completed in PR #<PR_NUM>. Both tests pass on chromium, firefox, webkit via CI."
```
