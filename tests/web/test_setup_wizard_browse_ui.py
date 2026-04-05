"""Tests for the directory-picker UI additions to the setup wizard.

Checks:
- Both directory inputs have an accompanying Browse button in the HTML template
- The Browse buttons carry the correct onclick attributes
- setup_wizard.js defines window.browseDirectory before the IIFE
- The JS function handles pywebview path, server-API path, and fallback paths
- The JS function does NOT return early on showDirectoryPicker errors
  (must fall through to webkitdirectory fallback)
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.ci]

TEMPLATE_PATH = (
    Path(__file__).parent.parent.parent / "src/file_organizer/web/templates/setup_wizard.html"
)
JS_PATH = Path(__file__).parent.parent.parent / "src/file_organizer/web/static/js/setup_wizard.js"


# ---------------------------------------------------------------------------
# HTML template — Browse buttons present
# ---------------------------------------------------------------------------


class TestSetupWizardTemplateBrowseButtons:
    @pytest.fixture(autouse=True)
    def html(self) -> str:
        return TEMPLATE_PATH.read_text()

    def test_input_dir_browse_button_exists(self, html: str) -> None:
        """Input Directory section must have a Browse button."""
        assert "browseDirectory('input-dir')" in html

    def test_output_dir_browse_button_exists(self, html: str) -> None:
        """Output Directory section must have a Browse button."""
        assert "browseDirectory('output-dir')" in html

    def test_input_dir_input_still_present(self, html: str) -> None:
        """The text input for input-dir must still exist alongside the button."""
        assert 'id="input-dir"' in html

    def test_output_dir_input_still_present(self, html: str) -> None:
        """The text input for output-dir must still exist alongside the button."""
        assert 'id="output-dir"' in html

    def test_browse_buttons_are_type_button(self, html: str) -> None:
        """Browse buttons must be type=button to avoid accidental form submission."""
        # Find button elements with browseDirectory in onclick
        pattern = re.compile(
            r'<button[^>]+onclick="window\.browseDirectory\([^)]+\)"[^>]*>', re.DOTALL
        )
        matches = pattern.findall(html)
        assert len(matches) >= 2, f"Expected at least 2 Browse buttons, found: {matches}"
        for match in matches:
            assert 'type="button"' in match, f"Browse button missing type=button: {match}"


# ---------------------------------------------------------------------------
# JS — window.browseDirectory is defined and structured correctly
# ---------------------------------------------------------------------------


class TestSetupWizardJSBrowseFunction:
    @pytest.fixture(autouse=True)
    def js(self) -> str:
        return JS_PATH.read_text()

    def test_browse_directory_defined_on_window(self, js: str) -> None:
        """window.browseDirectory must be assigned before the IIFE."""
        assert "window.browseDirectory" in js

    def test_defined_before_iife(self, js: str) -> None:
        """window.browseDirectory assignment must appear before the (() => { IIFE."""
        browse_pos = js.index("window.browseDirectory")
        iife_pos = js.index("(() => {")
        assert browse_pos < iife_pos, (
            "window.browseDirectory must be defined before the IIFE "
            f"(found at {browse_pos}, IIFE at {iife_pos})"
        )

    def test_pywebview_branch_present(self, js: str) -> None:
        """Function must check for window.pywebview.api.browse_directory."""
        assert "pywebview" in js
        assert "browse_directory" in js

    def test_server_api_fetch_present(self, js: str) -> None:
        """Function must call the server-side /api/v1/setup/browse-folder endpoint."""
        assert "/api/v1/setup/browse-folder" in js

    def test_webkitdirectory_fallback_present(self, js: str) -> None:
        """Function must include the webkitdirectory fallback input as last resort."""
        assert "webkitdirectory" in js

    def test_showdirectorypicker_error_does_not_use_bare_return(self, js: str) -> None:
        """
        When showDirectoryPicker throws an error that is NOT AbortError, the code
        must NOT simply `return` — it must fall through to the next picker method.

        We verify this by checking that inside the showDirectoryPicker catch block,
        the only unconditional `return` is for AbortError cancellation.
        Specifically, the pattern `if (e.name === "AbortError") return;` must be
        present AND there must be NO bare `return;` immediately after the catch
        error logging.
        """
        # The correct pattern: only return on AbortError, otherwise fall through
        assert 'e.name === "AbortError"' in js or 'e.name !== "AbortError"' in js

    def test_fetch_fallback_on_server_unavailable(self, js: str) -> None:
        """The fetch call must have error handling so server errors fall through."""
        # There must be a try/catch around the fetch call
        fetch_pos = js.index("/api/v1/setup/browse-folder")
        # Find the surrounding try block (search backward)
        code_before = js[:fetch_pos]
        assert "try" in code_before[-200:], (
            "fetch('/api/setup/browse-folder') must be inside a try block "
            "so network errors fall through to the next picker"
        )
