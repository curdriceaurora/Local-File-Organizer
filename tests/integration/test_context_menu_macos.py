"""Tests for macOS Finder context menu Quick Action."""

import stat
import unittest
from pathlib import Path


class TestMacOSQuickAction(unittest.TestCase):
    def setUp(self):
        self.macos_dir = Path("desktop/context-menus/macos")
        self.quick_action_sh = self.macos_dir / "organize-quick-action.sh"
        self.workflow_dir = self.macos_dir / "OrganizeWithFileOrganizer.workflow"
        self.info_plist = self.workflow_dir / "Contents" / "Info.plist"
        self.document_wflow = self.workflow_dir / "Contents" / "document.wflow"

    def test_macos_dir_exists(self):
        self.assertTrue(self.macos_dir.exists())

    def test_quick_action_script_exists(self):
        self.assertTrue(self.quick_action_sh.exists())

    def test_script_has_shebang(self):
        content = self.quick_action_sh.read_text()
        self.assertTrue(content.startswith("#!/bin/bash"))

    def test_script_calls_api_endpoint(self):
        content = self.quick_action_sh.read_text()
        self.assertIn("/api/v1/organize", content)

    def test_script_has_cli_fallback(self):
        content = self.quick_action_sh.read_text()
        self.assertIn("file-organizer", content)

    def test_script_is_executable(self):
        mode = self.quick_action_sh.stat().st_mode
        self.assertTrue(bool(mode & stat.S_IXUSR))

    def test_workflow_directory_exists(self):
        self.assertTrue(self.workflow_dir.exists())

    def test_info_plist_exists(self):
        self.assertTrue(self.info_plist.exists())

    def test_info_plist_has_service_definition(self):
        content = self.info_plist.read_text()
        self.assertIn("NSServices", content)
        self.assertIn("Organize with File Organizer", content)

    def test_document_wflow_exists(self):
        self.assertTrue(self.document_wflow.exists())

    def test_workflow_is_service_type(self):
        content = self.document_wflow.read_text()
        self.assertIn("servicesMenu", content)

    def test_install_script_exists(self):
        install_sh = Path("desktop/context-menus/install-macos.sh")
        self.assertTrue(install_sh.exists())


if __name__ == "__main__":
    unittest.main()
