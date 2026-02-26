"""Tests for TUI application."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from file_organizer.tui.analytics_view import AnalyticsView
from file_organizer.tui.app import FileOrganizerApp, PlaceholderView, StatusBar, run_tui
from file_organizer.tui.audio_view import AudioView
from file_organizer.tui.methodology_view import MethodologyView
from file_organizer.tui.organization_preview import OrganizationPreviewView
from file_organizer.tui.undo_history_view import UndoHistoryView


@pytest.mark.asyncio
async def test_app_starts_and_quits() -> None:
    """App should start, render, and exit cleanly."""
    app = FileOrganizerApp()
    async with app.run_test() as pilot:
        assert app.query_one(StatusBar) is not None
        # Files view now mounts FilePreviewView instead of PlaceholderView
        assert app.query_one("#view") is not None
        await pilot.press("q")


@pytest.mark.asyncio
async def test_initial_view_is_files() -> None:
    """Initial main content should show the Files view."""
    app = FileOrganizerApp()
    async with app.run_test():
        assert app._current_view == "files"


@pytest.mark.asyncio
async def test_switch_to_organized_view() -> None:
    """Switching to organized view should mount OrganizationPreviewView."""
    with patch.object(OrganizationPreviewView, "_load_preview"):
        app = FileOrganizerApp()
        async with app.run_test() as pilot:
            await app.action_switch_view("organized")
            await pilot.pause()
            assert app._current_view == "organized"
            assert app.query_one("#view", OrganizationPreviewView) is not None


@pytest.mark.asyncio
async def test_switch_to_settings_view() -> None:
    """Switching to settings view should mount a PlaceholderView."""
    app = FileOrganizerApp()
    async with app.run_test() as pilot:
        await app.action_switch_view("settings")
        await pilot.pause()
        assert app._current_view == "settings"
        assert app.query_one("#view", PlaceholderView) is not None


@pytest.mark.asyncio
async def test_switch_back_to_files_view() -> None:
    """Switching back to files should restore the FilePreviewView."""
    app = FileOrganizerApp()
    async with app.run_test() as pilot:
        await app.action_switch_view("settings")
        await pilot.pause()
        await app.action_switch_view("files")
        await pilot.pause()
        assert app._current_view == "files"


@pytest.mark.asyncio
async def test_status_bar_updates_on_view_switch() -> None:
    """StatusBar should update its internal message when switching views."""
    with patch.object(OrganizationPreviewView, "_load_preview"):
        app = FileOrganizerApp()
        async with app.run_test() as pilot:
            await app.action_switch_view("organized")
            await pilot.pause()
            status = app.query_one(StatusBar)
            assert "Organized" in status._message


@pytest.mark.asyncio
async def test_help_action_updates_status() -> None:
    """Help action should update the status bar with help info."""
    app = FileOrganizerApp()
    async with app.run_test() as pilot:
        app.action_toggle_help()
        await pilot.pause()
        status = app.query_one(StatusBar)
        assert "quit" in status._message.lower()


class TestStatusBarUnit:
    """Unit tests for StatusBar widget (no app context needed)."""

    def test_default_message(self) -> None:
        bar = StatusBar()
        assert bar._message == "Ready"

    def test_custom_initial_message(self) -> None:
        bar = StatusBar("Loading...")
        assert bar._message == "Loading..."

    def test_set_status_updates_message(self) -> None:
        bar = StatusBar()
        bar.set_status("Processing")
        assert bar._message == "Processing"


@pytest.mark.asyncio
async def test_switch_to_analytics_view() -> None:
    """Switching to analytics view should mount AnalyticsView."""
    with patch.object(AnalyticsView, "_load_analytics"):
        app = FileOrganizerApp()
        async with app.run_test() as pilot:
            await app.action_switch_view("analytics")
            await pilot.pause()
            assert app._current_view == "analytics"
            assert app.query_one("#view", AnalyticsView) is not None


@pytest.mark.asyncio
async def test_switch_to_methodology_view() -> None:
    """Switching to methodology view should mount MethodologyView."""
    app = FileOrganizerApp()
    async with app.run_test() as pilot:
        await app.action_switch_view("methodology")
        await pilot.pause()
        assert app._current_view == "methodology"
        assert app.query_one("#view", MethodologyView) is not None


@pytest.mark.asyncio
async def test_status_bar_updates_on_analytics_switch() -> None:
    """StatusBar should show 'Analytics' when switching to analytics view."""
    with patch.object(AnalyticsView, "_load_analytics"):
        app = FileOrganizerApp()
        async with app.run_test() as pilot:
            await app.action_switch_view("analytics")
            await pilot.pause()
            status = app.query_one(StatusBar)
            assert "Analytics" in status._message


@pytest.mark.asyncio
async def test_switch_to_audio_view() -> None:
    """Switching to audio view should mount AudioView."""
    with patch.object(AudioView, "_scan_audio_files"):
        app = FileOrganizerApp()
        async with app.run_test() as pilot:
            await app.action_switch_view("audio")
            await pilot.pause()
            assert app._current_view == "audio"
            assert app.query_one("#view", AudioView) is not None


@pytest.mark.asyncio
async def test_switch_to_history_view() -> None:
    """Switching to history view should mount UndoHistoryView."""
    with patch.object(UndoHistoryView, "_load_history"):
        app = FileOrganizerApp()
        async with app.run_test() as pilot:
            await app.action_switch_view("history")
            await pilot.pause()
            assert app._current_view == "history"
            assert app.query_one("#view", UndoHistoryView) is not None


@pytest.mark.asyncio
async def test_update_notification() -> None:
    """When update is available, notification should be shown."""
    app = FileOrganizerApp()
    async with app.run_test() as pilot:
        app._notify_update("2.0.1")
        await pilot.pause()

        status_bar = app.query_one(StatusBar)
        assert "2.0.1" in status_bar._message


def test_run_tui_entry_point() -> None:
    """run_tui should create and run the application."""
    with patch.object(FileOrganizerApp, "run") as mock_run:
        run_tui()
        mock_run.assert_called_once()
