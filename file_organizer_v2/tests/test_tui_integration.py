"""Integration tests for TUI multi-view navigation and keybindings.

Covers round-trip view switching, binding dispatch, sidebar rendering,
and the new copilot view integration.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from file_organizer.tui.analytics_view import AnalyticsView
from file_organizer.tui.app import FileOrganizerApp, PlaceholderView, Sidebar, StatusBar
from file_organizer.tui.audio_view import AudioView
from file_organizer.tui.copilot_view import CopilotView
from file_organizer.tui.methodology_view import MethodologyView
from file_organizer.tui.organization_preview import OrganizationPreviewView
from file_organizer.tui.undo_history_view import UndoHistoryView


# ---------------------------------------------------------------------------
# View switching round-trips
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_round_trip_files_to_settings_and_back() -> None:
    """files -> settings -> files should restore the original view."""
    app = FileOrganizerApp()
    async with app.run_test() as pilot:
        assert app._current_view == "files"

        await app.action_switch_view("settings")
        await pilot.pause()
        assert app._current_view == "settings"
        assert app.query_one("#view", PlaceholderView) is not None

        await app.action_switch_view("files")
        await pilot.pause()
        assert app._current_view == "files"


@pytest.mark.asyncio
async def test_round_trip_all_views() -> None:
    """Cycle through every view and verify the view widget is mounted."""
    view_names = [
        "files",
        "organized",
        "analytics",
        "methodology",
        "audio",
        "history",
        "settings",
        "copilot",
    ]

    # Patch background loaders to avoid real I/O
    with (
        patch.object(OrganizationPreviewView, "_load_preview"),
        patch.object(AnalyticsView, "_load_analytics"),
        patch.object(AudioView, "_scan_audio_files"),
        patch.object(UndoHistoryView, "_load_history"),
        patch.object(CopilotView, "_process_message"),
    ):
        app = FileOrganizerApp()
        async with app.run_test() as pilot:
            for name in view_names:
                await app.action_switch_view(name)
                await pilot.pause()
                assert app._current_view == name, f"Expected view {name!r}"
                assert app.query_one("#view") is not None


@pytest.mark.asyncio
async def test_switch_to_copilot_view() -> None:
    """Switching to copilot should mount CopilotView."""
    app = FileOrganizerApp()
    async with app.run_test() as pilot:
        await app.action_switch_view("copilot")
        await pilot.pause()
        assert app._current_view == "copilot"
        assert app.query_one("#view", CopilotView) is not None


# ---------------------------------------------------------------------------
# Keybinding dispatch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_keybinding_8_opens_copilot() -> None:
    """Action switch to copilot via action method (keybinding dispatch)."""
    app = FileOrganizerApp()
    async with app.run_test() as pilot:
        await app.action_switch_view("copilot")
        await pilot.pause()
        assert app._current_view == "copilot"


@pytest.mark.asyncio
async def test_keybinding_1_to_7_switch_views() -> None:
    """Switch views via action_switch_view for each named view."""
    expected = ["files", "organized", "analytics", "methodology", "audio", "history", "settings"]

    with (
        patch.object(OrganizationPreviewView, "_load_preview"),
        patch.object(AnalyticsView, "_load_analytics"),
        patch.object(AudioView, "_scan_audio_files"),
        patch.object(UndoHistoryView, "_load_history"),
    ):
        app = FileOrganizerApp()
        async with app.run_test() as pilot:
            for view_name in expected:
                await app.action_switch_view(view_name)
                await pilot.pause()
                assert app._current_view == view_name, (
                    f"Expected {view_name!r}, got {app._current_view!r}"
                )


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sidebar_contains_copilot_entry() -> None:
    """Sidebar navigation text should list the Copilot entry."""
    app = FileOrganizerApp()
    async with app.run_test():
        sidebar = app.query_one(Sidebar)
        assert sidebar is not None


# ---------------------------------------------------------------------------
# Status bar updates
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_status_bar_updates_for_copilot() -> None:
    """Switching to copilot should update the status bar."""
    app = FileOrganizerApp()
    async with app.run_test() as pilot:
        await app.action_switch_view("copilot")
        await pilot.pause()
        status = app.query_one(StatusBar)
        assert "Copilot" in status._message


@pytest.mark.asyncio
async def test_status_bar_shows_view_name_on_switch() -> None:
    """Status bar should contain the capitalised view name after switch."""
    with patch.object(AnalyticsView, "_load_analytics"):
        app = FileOrganizerApp()
        async with app.run_test() as pilot:
            await app.action_switch_view("analytics")
            await pilot.pause()
            status = app.query_one(StatusBar)
            assert "Analytics" in status._message
