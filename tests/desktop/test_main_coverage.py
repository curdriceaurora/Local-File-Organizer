"""Unit and integration coverage tests for file_organizer.desktop.__main__.

Targets 100% statement coverage.
"""

from __future__ import annotations

import runpy
from unittest.mock import patch
import pytest

pytestmark = pytest.mark.unit


def test_desktop_main_execution() -> None:
    """Verify that launching the desktop main module calls the app launch function."""
    with patch("file_organizer.desktop.app.launch") as mock_launch:
        runpy.run_module("file_organizer.desktop.__main__", run_name="__main__")
        mock_launch.assert_called_once()
