"""Shared fixtures for TUI tests."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def tui_completed_setup(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep TUI app tests out of first-run setup unless a test opts into it."""
    if request.node.name == "test_complete_wizard_persists_setup_completed":
        return

    mock_config = MagicMock()
    mock_config.setup_completed = True
    mock_config_manager = MagicMock()
    mock_config_manager.load.return_value = mock_config

    monkeypatch.setattr(
        "file_organizer.tui.app.ConfigManager",
        MagicMock(return_value=mock_config_manager),
    )
    monkeypatch.setattr(
        "file_organizer.tui.app.FileOrganizerApp._check_for_updates", lambda _: None
    )
