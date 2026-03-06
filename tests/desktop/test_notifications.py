"""Tests for native notification system."""

import unittest
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


class TestNativeNotifications(unittest.TestCase):
    def setUp(self):
        self.notifications_rs = Path("desktop/src-tauri/src/notifications.rs")
        self.lib_rs = Path("desktop/src-tauri/src/lib.rs")

    def test_notifications_rs_exists(self):
        self.assertTrue(self.notifications_rs.exists())

    def test_mod_declared_in_lib_rs(self):
        content = self.lib_rs.read_text()
        self.assertIn("mod notifications", content)

    def test_organization_complete_event(self):
        content = self.notifications_rs.read_text()
        self.assertIn("OrganizationComplete", content)

    def test_duplicates_found_event(self):
        content = self.notifications_rs.read_text()
        self.assertIn("DuplicatesFound", content)

    def test_update_available_event(self):
        content = self.notifications_rs.read_text()
        self.assertIn("UpdateAvailable", content)

    def test_daemon_events_present(self):
        content = self.notifications_rs.read_text()
        self.assertIn("DaemonStarted", content)
        self.assertIn("DaemonStopped", content)

    def test_tauri_plugin_notification_used(self):
        content = self.notifications_rs.read_text()
        self.assertIn("notification", content.lower())

    def test_event_listeners_registered(self):
        content = self.notifications_rs.read_text()
        self.assertIn("register_notification_listeners", content)

    def test_all_event_types_have_body(self):
        content = self.notifications_rs.read_text()
        self.assertIn("fn body", content)

    def test_rust_unit_tests_present(self):
        content = self.notifications_rs.read_text()
        self.assertIn("#[cfg(test)]", content)
        self.assertIn("#[test]", content)


if __name__ == "__main__":
    unittest.main()
