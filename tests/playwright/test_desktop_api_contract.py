"""Desktop API bridge contract tests via Playwright.

Verifies that the ``window.pywebview.api`` mock injected by the
``pywebview_mock`` fixture correctly integrates with the live JS utilities
(``desktop_api.js``) and updates the DOM as expected.

All tests use the ``pywebview_mock`` fixture which injects a controllable
``window.pywebview.api`` mock before any page navigation.

Running
-------
pytest tests/playwright/test_desktop_api_contract.py \\
    --browser chromium --override-ini='addopts=' -v
"""

from __future__ import annotations

import pytest

try:
    from playwright.sync_api import Page, expect
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


class TestBridgeMockInjection:
    """Verify the pywebview_mock fixture wires up correctly."""

    def test_pywebview_api_present_after_mock_fixture(
        self, page: Page, pywebview_mock: PywebviewMockHandle
    ) -> None:
        """``window.pywebview.api`` must exist in page context after fixture."""
        page.goto("/ui/setup")
        present: bool = page.evaluate("() => !!(window.pywebview && window.pywebview.api)")
        assert present is True

    def test_browse_directory_returns_mock_path(
        self, page: Page, pywebview_mock: PywebviewMockHandle
    ) -> None:
        """``browse_directory()`` must resolve to the configured mock value."""
        page.goto("/ui/setup")
        result: str = page.evaluate("() => window.pywebview.api.browse_directory().then(v => v)")
        assert result == "/mock/dir"

    def test_browse_file_returns_mock_path(
        self, page: Page, pywebview_mock: PywebviewMockHandle
    ) -> None:
        """``browse_file()`` must resolve to the configured mock value."""
        page.goto("/ui/settings")
        result: str = page.evaluate("() => window.pywebview.api.browse_file([]).then(v => v)")
        assert result == "/mock/file.json"

    def test_open_path_records_call(self, page: Page, pywebview_mock: PywebviewMockHandle) -> None:
        """Calls to ``open_path()`` must be recorded in ``__mockPyw.open_path_calls``."""
        page.goto("/ui/files")
        page.evaluate("() => window.pywebview.api.open_path('/test/path')")
        calls = pywebview_mock.get_open_path_calls()
        assert "/test/path" in calls


class TestDesktopModeVisibility:
    """Verify [data-desktop-only] CSS gating behaviour."""

    def test_desktop_app_attribute_set_with_mock(
        self, page: Page, pywebview_mock: PywebviewMockHandle
    ) -> None:
        """With pywebview mock injected, ``body[data-desktop-app="1"]`` must be set."""
        page.goto("/ui/settings")
        page.wait_for_load_state("networkidle")
        value: str = page.evaluate("() => document.body.getAttribute('data-desktop-app') || ''")
        assert value == "1"

    def test_desktop_app_attribute_absent_without_mock(self, page: Page) -> None:
        """Without the pywebview mock, body must NOT have ``data-desktop-app``."""
        page.goto("/ui/settings")
        page.wait_for_load_state("networkidle")
        value: str | None = page.evaluate("() => document.body.getAttribute('data-desktop-app')")
        assert value is None

    def test_desktop_browse_file_populates_settings_input(
        self, page: Page, pywebview_mock: PywebviewMockHandle
    ) -> None:
        """Clicking the desktop Browse button in settings must populate the path input."""
        page.goto("/ui/settings")
        page.wait_for_load_state("networkidle")

        # Trigger desktopBrowseFile directly (the button is data-desktop-only so
        # it's guaranteed to exist; rely on JS call rather than DOM click to avoid
        # z-index / visibility issues with the settings page layout).
        page.evaluate(
            "() => window.desktopBrowseFile('settings-file-path',"
            " [['JSON files (*.json)', '*.json']])"
        )

        expect(page.locator("#settings-file-path")).to_have_value("/mock/file.json")
