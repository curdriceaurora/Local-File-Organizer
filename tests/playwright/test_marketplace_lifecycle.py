"""Browser E2E tests for plugin marketplace lifecycle (B4).

Verifies the /ui/marketplace UI: listing plugins, installing one (the
"enable" step), and uninstalling it (the "disable" step).

Stub plugin
-----------
All tests use ``fo-test-echo`` — a minimal no-op plugin whose archive is
created on disk inside ``tmp_path`` by the ``_marketplace_service`` fixture.
This guarantees a stable, predictable target with no dependency on a live
marketplace server.

The ``_marketplace_service`` fixture (defined in ``conftest.py``) patches
``file_organizer.web.marketplace_routes._service`` so the in-process live
server resolves to a ``MarketplaceService`` backed by a real but isolated
local repo directory.  State written during a test (installed.json) lives
inside ``tmp_path`` and is discarded when the fixture tears down.

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

import pytest

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
