"""Tests for splash screen implementation (Issue #540)."""

import unittest
from pathlib import Path


class TestSplashScreen(unittest.TestCase):
    """Verify the splash screen files exist and contain required elements."""

    def setUp(self) -> None:
        self.splash_html = Path("desktop/src-tauri/src/splash.html")
        self.splash_rs = Path("desktop/src-tauri/src/splash.rs")
        self.lib_rs = Path("desktop/src-tauri/src/lib.rs")
        self.tauri_conf = Path("desktop/src-tauri/tauri.conf.json")

    # --- File existence ---

    def test_splash_html_exists(self) -> None:
        self.assertTrue(self.splash_html.exists(), "splash.html must exist")

    def test_splash_rs_exists(self) -> None:
        self.assertTrue(self.splash_rs.exists(), "splash.rs must exist")

    # --- splash.html content ---

    def test_splash_has_spinner(self) -> None:
        content = self.splash_html.read_text(encoding="utf-8")
        self.assertIn("spinner", content)

    def test_splash_has_error_panel(self) -> None:
        content = self.splash_html.read_text(encoding="utf-8")
        self.assertIn("errorPanel", content)

    def test_splash_has_retry_button(self) -> None:
        content = self.splash_html.read_text(encoding="utf-8")
        self.assertIn("retry", content.lower())

    def test_splash_listens_for_sidecar_event(self) -> None:
        content = self.splash_html.read_text(encoding="utf-8")
        self.assertIn("sidecar-state", content)

    def test_splash_navigates_on_ready(self) -> None:
        content = self.splash_html.read_text(encoding="utf-8")
        self.assertIn("ready", content)
        self.assertIn("location.href", content)

    def test_splash_is_self_contained(self) -> None:
        """No external stylesheet or script src links."""
        content = self.splash_html.read_text(encoding="utf-8")
        self.assertNotIn('<link rel="stylesheet"', content)
        self.assertNotIn('src="http', content)

    def test_splash_has_app_name(self) -> None:
        content = self.splash_html.read_text(encoding="utf-8")
        self.assertIn("File Organizer", content)

    def test_splash_has_subtitle(self) -> None:
        content = self.splash_html.read_text(encoding="utf-8")
        self.assertIn("subtitle", content)

    def test_splash_handles_crashed_state(self) -> None:
        content = self.splash_html.read_text(encoding="utf-8")
        self.assertIn("crashed", content)

    def test_splash_handles_stopped_state(self) -> None:
        content = self.splash_html.read_text(encoding="utf-8")
        self.assertIn("stopped", content)

    def test_splash_invokes_get_sidecar_state(self) -> None:
        content = self.splash_html.read_text(encoding="utf-8")
        self.assertIn("get_sidecar_state", content)

    # --- lib.rs integration ---

    def test_lib_rs_declares_splash_mod(self) -> None:
        content = self.lib_rs.read_text(encoding="utf-8")
        self.assertIn("mod splash", content)

    def test_lib_rs_registers_get_sidecar_state(self) -> None:
        content = self.lib_rs.read_text(encoding="utf-8")
        self.assertIn("get_sidecar_state", content)

    # --- splash.rs content ---

    def test_splash_rs_defines_get_sidecar_state(self) -> None:
        content = self.splash_rs.read_text(encoding="utf-8")
        self.assertIn("get_sidecar_state", content)

    def test_splash_rs_returns_starting_state(self) -> None:
        content = self.splash_rs.read_text(encoding="utf-8")
        self.assertIn("starting", content)


if __name__ == "__main__":
    unittest.main()
