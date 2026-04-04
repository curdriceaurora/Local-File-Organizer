"""Playwright E2E smoke tests for the File Organizer web UI.

Each test verifies that a core page:
  1. Returns a non-error HTTP status (< 400 after redirects).
  2. Renders valid HTML (``<html>`` element present).
  3. Does not display a server-error indicator.
  4. Shows at least one expected structural element.

These tests are intentionally coarse — they are *smoke* tests, not
functional tests.  They catch regressions where a template fails to
render, a route 500s, or a critical import breaks at startup.

Running
-------
Playwright browser binaries must be installed once::

    playwright install chromium

Then run (stripping the default ``--cov`` addopts that break browser tests)::

    pytest tests/playwright/ --browser chromium --override-ini='addopts='

To watch the tests execute in a visible window add ``--headed``::

    pytest tests/playwright/ --browser chromium --headed --override-ini='addopts='
"""

from __future__ import annotations

import pytest

try:
    from playwright.sync_api import Page, Response, expect
except ImportError as _exc:
    raise ImportError(
        "playwright not installed — run: pip install -e '.[dev]' && playwright install chromium"
    ) from _exc

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.playwright,
    pytest.mark.timeout(60),  # browser ops need more headroom than unit tests
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _assert_no_server_error(page: Page) -> None:
    """Assert the rendered page does not contain a server-error indicator."""
    body_text = page.locator("body").inner_text()
    assert "Internal Server Error" not in body_text, (
        "Page rendered a server error:\n" + body_text[:500]
    )
    assert "500" not in page.title(), f"Page title suggests 5xx: {page.title()!r}"


def _goto_ok(page: Page, path: str) -> Response:
    """Navigate to *path* (relative to base_url) and assert the response is OK.

    Playwright follows redirects automatically; the returned Response reflects
    the *final* destination after any 3xx chain.

    Args:
        page: Playwright Page object.
        path: Relative path, e.g. ``"/ui/files"``.

    Returns:
        The final HTTP response.
    """
    response = page.goto(path)
    assert response is not None, f"page.goto({path!r}) returned None"
    assert response.ok, f"Expected 2xx for {path!r}, got {response.status} ({page.url})"
    return response


# ---------------------------------------------------------------------------
# Core page smoke tests
# ---------------------------------------------------------------------------


class TestPageLoads:
    """Verify that each primary web UI page renders without a server error."""

    def test_setup_wizard_page(self, page: Page) -> None:
        """Setup wizard renders on a fresh (unconfigured) server.

        Navigate directly so this test does not depend on the home-redirect logic.
        """
        _goto_ok(page, "/ui/setup")
        _assert_no_server_error(page)
        headings = page.locator("h1, h2, h3")
        assert headings.count() > 0, "Setup page has no heading elements"
        assert page.title() != "", "Setup page rendered with empty <title>"

    def test_home_redirect(self, page: Page) -> None:
        """Root path redirects to ``/ui/setup`` on a fresh server.

        On a fresh server ``setup_completed`` defaults to ``False``, so the
        home route always redirects to ``/ui/setup``.  Playwright follows the
        redirect and lands on a 2xx page.
        """
        response = page.goto("/")
        assert response is not None
        # After following redirects Playwright lands on a 2xx page.
        assert response.ok, f"Expected 2xx after redirect, got {response.status}"
        assert "/ui/setup" in page.url, f"Expected redirect to /ui/setup, got {page.url}"
        _assert_no_server_error(page)

    def test_files_browser_page(self, page: Page) -> None:
        """File browser renders the main listing view."""
        _goto_ok(page, "/ui/files")
        _assert_no_server_error(page)
        headings = page.locator("h1, h2, h3")
        assert headings.count() > 0, "Files page has no heading elements"
        assert page.title() != "", "Files page rendered with empty <title>"

    def test_organize_dashboard_page(self, page: Page) -> None:
        """Organize dashboard renders the scan/execute workflow page."""
        _goto_ok(page, "/ui/organize")
        _assert_no_server_error(page)
        headings = page.locator("h1, h2, h3")
        assert headings.count() > 0, "Organize page has no heading elements"
        assert page.title() != "", "Organize page rendered with empty <title>"

    def test_settings_page(self, page: Page) -> None:
        """Settings index page renders without errors."""
        _goto_ok(page, "/ui/settings")
        _assert_no_server_error(page)
        expect(page.locator("body")).to_be_visible()
        assert page.title() != "", "Settings page rendered with empty <title>"

    def test_marketplace_page(self, page: Page) -> None:
        """Marketplace plugin browser renders without errors."""
        _goto_ok(page, "/ui/marketplace")
        _assert_no_server_error(page)
        expect(page.locator("body")).to_be_visible()
        assert page.title() != "", "Marketplace page rendered with empty <title>"

    def test_profile_login_page(self, page: Page) -> None:
        """Login page renders (available regardless of auth_enabled setting)."""
        _goto_ok(page, "/ui/profile/login")
        _assert_no_server_error(page)
        expect(page.locator("form")).to_be_visible()

    def test_profile_register_page(self, page: Page) -> None:
        """Registration page renders without errors."""
        _goto_ok(page, "/ui/profile/register")
        _assert_no_server_error(page)
        expect(page.locator("form")).to_be_visible()


# ---------------------------------------------------------------------------
# REST API smoke tests (no browser rendering, just HTTP)
# ---------------------------------------------------------------------------


class TestAPIEndpoints:
    """Verify core REST API endpoints are reachable and return expected shapes."""

    def test_health_endpoint(self, page: Page) -> None:
        """Health endpoint returns a valid health status JSON body.

        Accepts 200 (ok) or 207 (degraded — Ollama unreachable).  503 is the
        ``"error"`` / ``"unhealthy"`` path and is not an acceptable smoke-test
        outcome.  Plain ``response.ok`` would reject 207, causing false
        failures when Ollama is not running.
        """
        response = page.request.get("/api/v1/health")
        assert response.status in (200, 207), (
            f"Unexpected health status {response.status}; expected 200 or 207"
        )
        body = response.json()
        assert body.get("status") in {"ok", "degraded", "unknown"}, (
            f"Unexpected health payload: {body}"
        )

    def test_static_assets_reachable(self, page: Page) -> None:
        """At least one static asset (CSS or JS) is served correctly."""
        # Navigate to a known page first so the static route is mounted.
        _goto_ok(page, "/ui/settings")
        # Collect all stylesheet hrefs from the DOM.
        hrefs: list[str] = page.eval_on_selector_all(
            "link[rel='stylesheet']",
            "els => els.map(el => el.href)",
        )
        assert hrefs, (
            "Expected at least one <link rel='stylesheet'> on /ui/settings — "
            "static assets may not be mounted or base template failed to render"
        )

        # Request the first stylesheet and verify it's served.
        resp = page.request.get(hrefs[0])
        assert resp.ok, f"Static asset {hrefs[0]!r} returned {resp.status}"


# ---------------------------------------------------------------------------
# Navigation / page-structure tests
# ---------------------------------------------------------------------------


class TestPageStructure:
    """Verify structural elements that must exist on rendered pages."""

    def test_settings_page_has_heading(self, page: Page) -> None:
        """Settings page contains at least one heading element."""
        _goto_ok(page, "/ui/settings")
        _assert_no_server_error(page)
        headings = page.locator("h1, h2, h3")
        assert headings.count() > 0, "Settings page has no heading elements"

    def test_marketplace_page_has_heading(self, page: Page) -> None:
        """Marketplace page contains at least one heading element."""
        _goto_ok(page, "/ui/marketplace")
        _assert_no_server_error(page)
        headings = page.locator("h1, h2, h3")
        assert headings.count() > 0, "Marketplace page has no heading elements"

    @pytest.mark.parametrize(
        "path",
        ["/ui/setup", "/ui/files", "/ui/settings", "/ui/marketplace"],
    )
    def test_pages_share_consistent_html_structure(self, page: Page, path: str) -> None:
        """Each UI page returns a complete HTML document in the raw server response.

        Validates DOCTYPE + html + head + body in ``response.text()`` rather
        than the browser DOM — browsers synthesize ``<html>`` and ``<body>``
        around bare fragment responses, so DOM-based locator checks pass even
        when the server returns an incomplete document.  Each path is a separate
        parametrized case so a failure for one path does not prevent the others
        from running.
        """
        response = page.goto(path)
        assert response is not None and response.ok, (
            f"{path!r} returned {response.status if response else 'None'}"
        )
        raw = response.text().lower()
        assert "<!doctype" in raw, f"{path!r}: missing DOCTYPE in raw response"
        assert "<html" in raw, f"{path!r}: missing <html> in raw response"
        assert "<head" in raw, f"{path!r}: missing <head> in raw response"
        assert "<body" in raw, f"{path!r}: missing <body> in raw response"
        content_type = response.headers.get("content-type", "")
        assert "text/html" in content_type, f"{path!r}: unexpected Content-Type {content_type!r}"
        _assert_no_server_error(page)

    def test_unknown_route_returns_404(self, page: Page) -> None:
        """A nonexistent UI route returns 404, not 500.

        Verifies that the exception handler correctly converts unknown-route
        errors into client errors rather than server errors.
        """
        response = page.goto("/ui/this-route-does-not-exist-smoke-check")
        assert response is not None, "page.goto() returned None for 404 path"
        assert response.status == 404, f"Expected 404 for unknown route, got {response.status}"
