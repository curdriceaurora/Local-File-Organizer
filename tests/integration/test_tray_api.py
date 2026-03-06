"""Integration tests for system tray -> Python backend REST API endpoint mapping.

These tests verify that desktop/src-tauri/src/tray.rs contains the correct API
endpoint URLs and menu items required by issue #552.
"""

import unittest
from pathlib import Path

TRAY_RS = Path("desktop/src-tauri/src/tray.rs")


class TestTrayApiMapping(unittest.TestCase):
    """Verify tray.rs contains all required menu items and API endpoints."""

    def setUp(self) -> None:
        self.assertTrue(
            TRAY_RS.exists(),
            f"tray.rs not found at {TRAY_RS.resolve()}",
        )
        self.content = TRAY_RS.read_text(encoding="utf-8")

    # ── File presence ─────────────────────────────────────────────────────────

    def test_tray_rs_exists(self) -> None:
        """tray.rs must exist in the expected location."""
        self.assertTrue(TRAY_RS.exists())

    # ── API endpoints ─────────────────────────────────────────────────────────

    def test_organize_triggers_api(self) -> None:
        """Organize Now must call /api/v1/organize."""
        self.assertIn("/api/v1/organize", self.content)

    def test_daemon_toggle_api_present(self) -> None:
        """Pause/Resume must call /api/v1/daemon/toggle."""
        self.assertIn("/api/v1/daemon/toggle", self.content)

    # ── Menu items ────────────────────────────────────────────────────────────

    def test_settings_menu_item_present(self) -> None:
        """Settings menu item must be present."""
        self.assertIn("settings", self.content.lower())

    def test_about_menu_item_present(self) -> None:
        """About menu item must be present."""
        self.assertIn("about", self.content.lower())

    def test_quit_menu_item_present(self) -> None:
        """Quit menu item must be present."""
        self.assertIn("quit", self.content.lower())

    def test_recent_activity_submenu(self) -> None:
        """Recent Activity submenu must be present."""
        self.assertIn("Recent Activity", self.content)

    def test_pause_resume_item(self) -> None:
        """Pause Daemon / Resume Daemon toggle must be present."""
        self.assertTrue(
            "pause" in self.content.lower(),
            "Expected 'pause' (case-insensitive) in tray.rs",
        )

    def test_show_window_item(self) -> None:
        """Show Window menu item must be present."""
        self.assertIn("Show Window", self.content)

    # ── UX / metadata ─────────────────────────────────────────────────────────

    def test_tooltip_present(self) -> None:
        """Tray icon must have a tooltip for accessibility."""
        self.assertIn("tooltip", self.content.lower())

    def test_left_click_toggle(self) -> None:
        """Left-click on tray icon must toggle window visibility."""
        self.assertIn("MouseButton::Left", self.content)

    def test_tray_state_struct_present(self) -> None:
        """TrayState struct must be defined for shared state management."""
        self.assertIn("TrayState", self.content)

    def test_api_post_function_present(self) -> None:
        """api_post helper must exist to call backend endpoints."""
        self.assertIn("api_post", self.content)

    def test_backend_port_configurable(self) -> None:
        """Backend port must be stored in TrayState for configurability."""
        self.assertIn("backend_port", self.content)

    def test_daemon_paused_state_tracked(self) -> None:
        """Daemon pause state must be tracked in TrayState."""
        self.assertIn("daemon_paused", self.content)

    def test_organize_item_id(self) -> None:
        """Organize Now menu item must have id 'organize'."""
        self.assertIn('"organize"', self.content)

    def test_quit_item_id(self) -> None:
        """Quit menu item must have id 'quit'."""
        self.assertIn('"quit"', self.content)

    def test_settings_item_id(self) -> None:
        """Settings menu item must have id 'settings'."""
        self.assertIn('"settings"', self.content)

    def test_about_item_id(self) -> None:
        """About menu item must have id 'about'."""
        self.assertIn('"about"', self.content)

    def test_settings_navigates_to_route(self) -> None:
        """Settings handler must navigate the webview to /settings."""
        self.assertIn("/settings", self.content)

    def test_separator_used_between_sections(self) -> None:
        """Menu must use separators to divide logical groups."""
        self.assertIn("separator()", self.content)


if __name__ == "__main__":
    unittest.main()
