"""Testing utilities for plugin developers."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path


class PluginTestCase(unittest.TestCase):
    """Base unittest test case with isolated filesystem helpers."""

    def setUp(self) -> None:
        """Set up a temporary directory for the test."""
        super().setUp()
        self._tmp_dir = tempfile.TemporaryDirectory(prefix="fo-plugin-test-")
        self.test_dir = Path(self._tmp_dir.name)

    def tearDown(self) -> None:
        """Tear down and clean up the temporary directory."""
        self._tmp_dir.cleanup()
        super().tearDown()

    def create_test_file(self, relative_path: str, content: str = "") -> Path:
        """Create a UTF-8 text fixture file under the test directory."""
        destination = self.test_dir / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
        return destination

    def assert_file_exists(self, path: Path) -> None:
        """Assert that the given path exists on the filesystem."""
        self.assertTrue(path.exists(), f"Expected file to exist: {path}")

    def assert_file_not_exists(self, path: Path) -> None:
        """Assert that the given path does not exist on the filesystem."""
        self.assertFalse(path.exists(), f"Expected file to be absent: {path}")
