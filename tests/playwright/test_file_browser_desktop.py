"""File browser desktop-mode tests via Playwright.

Verifies desktop-mode CSS gating on the files browser page and the
``desktopOpenPath`` integration with the pywebview mock.

Running
-------
pytest tests/playwright/test_file_browser_desktop.py \\
    --browser chromium --override-ini='addopts=' -v
"""

from __future__ import annotations

import pytest

try:
    from playwright.sync_api import Page
except ImportError as _exc:
    raise ImportError(
        "playwright not installed — run: pip install -e '.[dev]' && playwright install chromium"
    ) from _exc

from tests.playwright.conftest import PywebviewMockHandle

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.playwright,
    pytest.mark.timeout(60),
]

_FILES_URL = "/ui/files"


class TestFileBrowserBaseline:
    """Baseline smoke tests for the file browser page."""

    def test_file_browser_renders_without_error(self, page: Page) -> None:
        """File browser page must return HTTP 200 and not show a server error."""
        response = page.goto(_FILES_URL)
        assert response is not None
        assert response.status < 400
        # No server-error banner (checks common error text patterns)
        body_text = page.inner_text("body")
        assert "Internal Server Error" not in body_text
        assert "500" not in page.title()


class TestDesktopModeGating:
    """Verify [data-desktop-only] visibility gating on the file browser."""

    def test_body_not_desktop_app_without_mock(self, page: Page) -> None:
        """Without pywebview mock, body must NOT have data-desktop-app attribute."""
        page.goto(_FILES_URL)
        page.wait_for_load_state("networkidle")
        value: str | None = page.evaluate("() => document.body.getAttribute('data-desktop-app')")
        assert value != "1"

    def test_body_is_desktop_app_with_mock(
        self, page: Page, pywebview_mock: PywebviewMockHandle
    ) -> None:
        """With pywebview mock injected, body must have data-desktop-app='1'."""
        page.goto(_FILES_URL)
        page.wait_for_load_state("networkidle")
        value: str = page.evaluate("() => document.body.getAttribute('data-desktop-app') || ''")
        assert value == "1"

    def test_desktop_open_path_records_path_when_called_directly(
        self, page: Page, pywebview_mock: PywebviewMockHandle
    ) -> None:
        """Calling ``window.desktopOpenPath()`` must record the path in the mock."""
        page.goto(_FILES_URL)
        page.wait_for_load_state("networkidle")

        page.evaluate("() => window.desktopOpenPath('/some/output/folder')")

        calls = pywebview_mock.get_open_path_calls()
        assert "/some/output/folder" in calls
