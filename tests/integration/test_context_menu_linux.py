"""Tests for Linux context menu integration scripts."""

import stat
import unittest
from pathlib import Path


class TestNautilusScript(unittest.TestCase):
    def setUp(self):
        self.script = Path("desktop/context-menus/nautilus/Organize with File Organizer")

    def test_nautilus_script_exists(self):
        self.assertTrue(self.script.exists())

    def test_nautilus_script_has_shebang(self):
        content = self.script.read_text()
        self.assertTrue(content.startswith("#!/bin/bash"))

    def test_nautilus_script_uses_env_variable(self):
        content = self.script.read_text()
        self.assertIn("NAUTILUS_SCRIPT_SELECTED_FILE_PATHS", content)

    def test_nautilus_script_invokes_cli_fallback(self):
        content = self.script.read_text()
        self.assertIn("file-organizer", content)

    def test_nautilus_script_uses_api_endpoint(self):
        content = self.script.read_text()
        self.assertIn("/api/v1/organize", content)

    def test_nautilus_script_is_executable(self):
        mode = self.script.stat().st_mode
        self.assertTrue(bool(mode & stat.S_IXUSR), "Script should be executable")


class TestDolphinServiceFile(unittest.TestCase):
    def setUp(self):
        self.desktop_file = Path("desktop/context-menus/dolphin/file-organizer.desktop")

    def test_desktop_file_exists(self):
        self.assertTrue(self.desktop_file.exists())

    def test_desktop_file_type_is_service(self):
        content = self.desktop_file.read_text()
        self.assertIn("Type=Service", content)

    def test_desktop_file_has_exec(self):
        content = self.desktop_file.read_text()
        self.assertIn("Exec=", content)

    def test_desktop_file_has_action_name(self):
        content = self.desktop_file.read_text()
        self.assertIn("Organize with File Organizer", content)

    def test_desktop_file_has_mime_types(self):
        content = self.desktop_file.read_text()
        self.assertIn("MimeType=", content)


class TestInstallScript(unittest.TestCase):
    def setUp(self):
        self.install_script = Path("desktop/context-menus/install-linux.sh")

    def test_install_script_exists(self):
        self.assertTrue(self.install_script.exists())

    def test_install_script_has_shebang(self):
        content = self.install_script.read_text()
        self.assertTrue(content.startswith("#!/bin/bash"))

    def test_install_script_handles_nautilus(self):
        content = self.install_script.read_text()
        self.assertIn("nautilus", content.lower())

    def test_install_script_handles_dolphin(self):
        content = self.install_script.read_text()
        self.assertIn("dolphin", content.lower())


if __name__ == "__main__":
    unittest.main()
