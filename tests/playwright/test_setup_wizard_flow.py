"""Setup wizard 4-step flow tests via Playwright.

Covers: step rendering, mode selection navigation, Browse button integration
with the pywebview mock, and fallback behaviour without the mock.

Running
-------
pytest tests/playwright/test_setup_wizard_flow.py \\
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

_WIZARD_URL = "/ui/setup"


def _force_show_step(page: Page, step: int) -> None:
    """Jump directly to wizard step *step* by manipulating the DOM.

    This bypasses the normal flow (mode selection → capability detection →
    step 3) so tests can reach later steps without spawning real API calls.
    """
    page.evaluate(
        f"""() => {{
            document.querySelectorAll('.wizard-step').forEach(el => {{
                el.classList.remove('wizard-step-active');
                if (parseInt(el.dataset.step) === {step}) {{
                    el.classList.add('wizard-step-active');
                }}
            }});
        }}"""
    )


class TestWizardStep1:
    """Step 1: mode selection UI."""

    def test_wizard_step1_renders_mode_selection(self, page: Page) -> None:
        """Step 1 must show 'Quick Start' and 'Power User' mode cards."""
        page.goto(_WIZARD_URL)
        expect(page.get_by_role("heading", name="Quick Start")).to_be_visible()
        expect(page.get_by_role("heading", name="Power User")).to_be_visible()

    def test_quick_start_advances_to_step2(self, page: Page) -> None:
        """Clicking 'Use Quick Start' must show step 2 (capability detection)."""
        page.goto(_WIZARD_URL)
        page.get_by_role("button", name="Use Quick Start").click()
        expect(page.locator("[data-step='2'].wizard-step-active")).to_be_visible()


class TestWizardStep2:
    """Step 2: capability detection panel."""

    def test_step2_renders_detection_panel(self, page: Page) -> None:
        """Step 2 must include capability detection status elements."""
        page.goto(_WIZARD_URL)
        _force_show_step(page, 2)
        expect(page.locator("#ollama-status")).to_be_attached()
        expect(page.locator("#models-status")).to_be_attached()

    def test_continue_button_advances_to_step3(self, page: Page) -> None:
        """Force-clicking 'Continue' from step 2 must show step 3."""
        page.goto(_WIZARD_URL)
        _force_show_step(page, 2)
        # Dispatch click via JS to bypass disabled attribute and z-index issues.
        page.evaluate(
            "() => document.getElementById('btn-next-step2').dispatchEvent(new MouseEvent('click', {bubbles: true}))"
        )
        expect(page.locator("[data-step='3'].wizard-step-active")).to_be_visible()


class TestWizardStep3:
    """Step 3: directory configuration and Browse integration."""

    def test_step3_browse_buttons_present(self, page: Page) -> None:
        """Step 3 must contain Browse buttons for input and output directories."""
        page.goto(_WIZARD_URL)
        _force_show_step(page, 3)
        # Both Browse… buttons should be visible in the DOM
        buttons = page.get_by_role("button", name="Browse\u2026")
        assert buttons.count() >= 2

    def test_step3_browse_directory_populates_input_via_pywebview(
        self, page: Page, pywebview_mock: PywebviewMockHandle
    ) -> None:
        """With pywebview mock: clicking Browse must populate the input-dir field."""
        page.goto(_WIZARD_URL)
        _force_show_step(page, 3)

        # Call browseDirectory directly (same as onclick="window.browseDirectory('input-dir')")
        page.evaluate("async () => { await window.browseDirectory('input-dir'); }")

        expect(page.locator("#input-dir")).to_have_value("/mock/dir")

    def test_step3_browse_directory_no_js_error_without_pywebview(self, page: Page) -> None:
        """Without pywebview mock: browseDirectory must be defined with no JS errors."""
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))

        # Stub the browse-folder endpoint so the async fallback resolves quickly
        # without opening a native OS dialog (which would block headless Playwright).
        page.route(
            "**/api/v1/setup/browse-folder",
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body='{"available": false, "cancelled": false, "path": ""}',
            ),
        )

        page.goto(_WIZARD_URL)
        _force_show_step(page, 3)

        # Verify the function is defined; no synchronous JS errors on load.
        is_fn: bool = page.evaluate("() => typeof window.browseDirectory === 'function'")
        assert is_fn, "window.browseDirectory should be defined on the wizard page"
        assert not errors, f"JS errors during page load: {errors}"

    def test_complete_setup_navigates_to_step4(self, page: Page) -> None:
        """Clicking 'Complete Setup' (with mocked API success) must show step 4."""
        # Stub setup/complete so the wizard can advance without a real Ollama server.
        page.route(
            "**/api/v1/setup/complete",
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body='{"success": true, "errors": []}',
            ),
        )
        page.goto(_WIZARD_URL)
        _force_show_step(page, 3)
        # Populate the required text-model select (normally filled by capability detection).
        page.evaluate(
            """() => {
                const sel = document.getElementById('text-model');
                const opt = document.createElement('option');
                opt.value = 'llama3:8b';
                opt.textContent = 'llama3:8b';
                sel.appendChild(opt);
                sel.value = 'llama3:8b';
            }"""
        )
        # Dispatch click via JS to bypass disabled state and reach the body event listener.
        page.evaluate(
            "() => document.getElementById('btn-complete').dispatchEvent("
            "new MouseEvent('click', {bubbles: true}))"
        )
        expect(page.locator("[data-step='4'].wizard-step-active")).to_be_visible()
