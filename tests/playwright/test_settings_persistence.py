"""Browser E2E tests for settings persistence (B3).

Verifies that settings saved via the /ui/settings UI survive a full page
reload.  Two representative settings are tested:

* Language (General section) — ``en`` → ``es``
* Theme (Appearance section)  — ``light`` → ``dark``

The plain ``page`` fixture (unauthenticated) is used because settings routes
carry no auth dependency.

State isolation
---------------
A function-scoped ``_reset_settings`` autouse fixture POSTs to
``/ui/settings/reset`` both before and after each test body (yield fixture),
so settings are always restored to defaults even when a test fails or is
interrupted mid-way.  The reset is done via httpx (not the browser) so it is
cheap and does not interfere with Playwright's browser context.
"""

from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest

try:
    from playwright.sync_api import Page
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
# Fixtures
# ---------------------------------------------------------------------------


def _do_reset(client: httpx.Client, live_server_url: str) -> None:
    """POST /ui/settings/reset and assert the request succeeded.

    Reuses the caller's ``httpx.Client`` so the CSRF cookie obtained during
    the GET is automatically forwarded on the POST.  The ``section`` parameter
    controls only which response partial is rendered — the reset always writes
    a fresh ``WebSettings()`` to disk regardless of section.
    """
    client.get(f"{live_server_url}/ui/settings").raise_for_status()
    csrf_token = client.cookies.get("_csrf_token")
    if csrf_token is None:
        raise RuntimeError(
            f"CSRF token cookie '_csrf_token' missing from GET {live_server_url}/ui/settings"
        )
    client.post(
        f"{live_server_url}/ui/settings/reset",
        data={"section": "general", "csrf_token": csrf_token},
    ).raise_for_status()


@pytest.fixture(autouse=True)
def _reset_settings(live_server_url: str) -> Iterator[None]:
    """Reset web settings to defaults before and after each test.

    Yield-based so teardown runs even when the test body raises an exception.
    A single ``httpx.Client`` is reused for both the before- and after-reset
    calls so the cookie jar is shared and no extra GET is needed.
    """
    with httpx.Client(follow_redirects=True) as client:
        _do_reset(client, live_server_url)
        yield
        _do_reset(client, live_server_url)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _open_general_section(page: Page) -> None:
    """Navigate to /ui/settings and wait for the General section to load.

    The panel carries ``hx-trigger="load"`` so HTMX auto-loads the General
    section without clicking a tab.
    """
    page.goto("/ui/settings")
    page.locator("#settings-language").wait_for(state="visible", timeout=_LOCATOR_TIMEOUT_MS)


def _open_appearance_section(page: Page) -> None:
    """Navigate to /ui/settings and click the Appearance tab.

    HTMX swaps the panel content; we wait for ``#settings-theme`` to appear.
    """
    page.goto("/ui/settings")
    # Wait for HTMX-loaded General panel to settle so the tab click does not
    # race with the initial load swap.
    page.locator("#settings-language").wait_for(state="visible", timeout=_LOCATOR_TIMEOUT_MS)
    page.get_by_role("tab", name="Appearance").click()
    page.locator("#settings-theme").wait_for(state="visible", timeout=_LOCATOR_TIMEOUT_MS)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_language_persists_after_reload(page: Page) -> None:
    """Changing language to 'es' and saving should survive a page reload."""
    # -- Arrange: open General section, confirm default is 'en' --
    _open_general_section(page)
    assert page.locator("#settings-language").input_value() == "en"

    # -- Act: change language to Spanish and save --
    page.locator("#settings-language").select_option("es")
    page.get_by_role("button", name="Save general settings").click()
    # Wait for the success banner to confirm the server accepted the change.
    page.locator(".banner-info").wait_for(
        state="visible", timeout=_LOCATOR_TIMEOUT_MS
    )  # success banner injected by HTMX on 200 response

    # -- Assert: reload page; General section should show 'es' --
    _open_general_section(page)
    assert page.locator("#settings-language").input_value() == "es", (
        "Language setting did not persist after reload"
    )


def test_theme_persists_after_reload(page: Page) -> None:
    """Changing theme to 'dark' and saving should survive a page reload."""
    # -- Arrange: open Appearance section, confirm default is 'light' --
    _open_appearance_section(page)
    assert page.locator("#settings-theme").input_value() == "light"

    # -- Act: change theme to 'dark' and save --
    page.locator("#settings-theme").select_option("dark")
    page.get_by_role("button", name="Save appearance settings").click()
    page.locator(".banner-info").wait_for(
        state="visible", timeout=_LOCATOR_TIMEOUT_MS
    )  # success banner injected by HTMX on 200 response

    # -- Assert: reload page; Appearance section should show 'dark' --
    _open_appearance_section(page)
    assert page.locator("#settings-theme").input_value() == "dark", (
        "Theme setting did not persist after reload"
    )
