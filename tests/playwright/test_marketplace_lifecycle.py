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
        # Bare filename (no scheme): PluginRepository resolves it relative to
        # _base_file_root, which is derived from repo_url=str(repo_dir).
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
        new=lambda: service,
    ):
        yield _STUB_PLUGIN_NAME


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
    authed_page.locator("#plugins-tbody").wait_for(state="visible", timeout=_LOCATOR_TIMEOUT_MS)

    row = authed_page.locator("#plugins-tbody tr", has_text=plugin_name)
    expect(row).to_be_visible(timeout=_LOCATOR_TIMEOUT_MS)
    expect(row.get_by_role("button", name="Install")).to_be_visible(timeout=_LOCATOR_TIMEOUT_MS)


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
    row.get_by_role("button", name="Install", exact=True).click()
    # Flash message confirms the server handled the POST and re-rendered #main.
    authed_page.locator("p.organize-hint").wait_for(state="visible", timeout=_LOCATOR_TIMEOUT_MS)
    # Re-acquire row locator: HTMX replaced #main, old DOM nodes are gone.
    row = authed_page.locator("#plugins-tbody tr", has_text=plugin_name)
    expect(row.get_by_role("button", name="Uninstall", exact=True)).to_be_visible(
        timeout=_LOCATOR_TIMEOUT_MS
    )
    expect(row.get_by_role("button", name="Install", exact=True)).not_to_be_visible(
        timeout=_LOCATOR_TIMEOUT_MS
    )

    # --- Uninstall phase ---
    row.get_by_role("button", name="Uninstall", exact=True).click()
    expect(authed_page.locator("p.organize-hint")).to_have_text(
        f"Uninstalled {plugin_name}.",
        timeout=_LOCATOR_TIMEOUT_MS,
    )
    row = authed_page.locator("#plugins-tbody tr", has_text=plugin_name)
    expect(row.get_by_role("button", name="Install", exact=True)).to_be_visible(
        timeout=_LOCATOR_TIMEOUT_MS
    )
    expect(row.get_by_role("button", name="Uninstall", exact=True)).not_to_be_visible(
        timeout=_LOCATOR_TIMEOUT_MS
    )
