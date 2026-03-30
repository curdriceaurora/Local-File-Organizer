"""Tests for file_organizer.tui.app module."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from textual.app import App
from textual.binding import Binding
from textual.widgets import Static

from file_organizer.tui.analytics_view import AnalyticsView
from file_organizer.tui.app import (
    FileOrganizerApp,
    PlaceholderView,
    Sidebar,
    StatusBar,
    run_tui,
)
from file_organizer.tui.audio_view import AudioView
from file_organizer.tui.methodology_view import MethodologyView
from file_organizer.tui.organization_preview import OrganizationPreviewView
from file_organizer.tui.settings_view import SettingsView
from file_organizer.tui.undo_history_view import UndoHistoryView

pytestmark = [pytest.mark.unit]


@pytest.mark.unit
class TestStatusBar:
    """Tests for the StatusBar widget."""

    def test_inherits_from_static(self) -> None:
        assert issubclass(StatusBar, Static)

    def test_default_message_is_ready(self) -> None:
        bar = StatusBar()
        assert bar._message == "Ready"

    def test_custom_initial_message(self) -> None:
        bar = StatusBar("Loading...")
        assert bar._message == "Loading..."

    def test_set_status_updates_message_attribute(self) -> None:
        bar = StatusBar()
        bar._message = "Processing"
        assert bar._message == "Processing"

    def test_set_status_method(self) -> None:
        bar = StatusBar()
        bar.set_status("Processing")
        assert bar._message == "Processing"

    def test_default_css_defined(self) -> None:
        assert "StatusBar" in StatusBar.DEFAULT_CSS


@pytest.mark.unit
class TestSidebar:
    """Tests for the Sidebar widget."""

    def test_inherits_from_static(self) -> None:
        assert issubclass(Sidebar, Static)

    def test_has_compose_method(self) -> None:
        assert callable(getattr(Sidebar, "compose", None))

    def test_default_css_defined(self) -> None:
        assert "Sidebar" in Sidebar.DEFAULT_CSS


@pytest.mark.unit
class TestPlaceholderView:
    """Tests for the PlaceholderView widget."""

    def test_inherits_from_static(self) -> None:
        assert issubclass(PlaceholderView, Static)

    def test_default_css_defined(self) -> None:
        assert "PlaceholderView" in PlaceholderView.DEFAULT_CSS


@pytest.mark.unit
class TestFileOrganizerApp:
    """Tests for the FileOrganizerApp."""

    def test_inherits_from_app(self) -> None:
        assert issubclass(FileOrganizerApp, App)

    def test_title(self) -> None:
        assert FileOrganizerApp.TITLE == "File Organizer"

    def test_sub_title(self) -> None:
        assert FileOrganizerApp.SUB_TITLE == "AI-powered local file management"

    def test_has_bindings(self) -> None:
        assert isinstance(FileOrganizerApp.BINDINGS, list)
        assert len(FileOrganizerApp.BINDINGS) >= 8

    def test_quit_binding_present(self) -> None:
        keys = [b.key for b in FileOrganizerApp.BINDINGS if isinstance(b, Binding)]
        assert "q" in keys

    def test_view_switch_bindings_present(self) -> None:
        keys = [b.key for b in FileOrganizerApp.BINDINGS if isinstance(b, Binding)]
        for digit in ["1", "2", "3", "4", "5", "6", "7", "8"]:
            assert digit in keys, f"Missing binding for key '{digit}'"

    def test_tab_binding_present(self) -> None:
        keys = [b.key for b in FileOrganizerApp.BINDINGS if isinstance(b, Binding)]
        assert "tab" in keys

    def test_initial_view_is_files(self) -> None:
        app = FileOrganizerApp()
        assert app._current_view == "files"

    def test_create_view_settings_returns_settings_view(self) -> None:
        widget = FileOrganizerApp._create_view("settings")
        assert isinstance(widget, SettingsView)

    def test_create_view_settings_has_view_id(self) -> None:
        widget = FileOrganizerApp._create_view("settings")
        assert widget.id == "view"

    def test_create_view_unknown_returns_placeholder(self) -> None:
        widget = FileOrganizerApp._create_view("nonexistent_view_xyz")
        assert isinstance(widget, PlaceholderView)
        assert widget.id == "view"


@pytest.mark.unit
class TestRunTui:
    """Tests for the run_tui function."""

    def test_run_tui_is_callable(self) -> None:
        assert callable(run_tui)

    def test_run_tui_entry_point(self) -> None:
        """run_tui should create and run the application."""
        with patch.object(FileOrganizerApp, "run") as mock_run:
            run_tui()
            mock_run.assert_called_once()


# ---------------------------------------------------------------------------
# Async integration tests (require Textual app context)
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_app_starts_and_quits() -> None:
    """App should start, render, and exit cleanly."""
    app = FileOrganizerApp()
    async with app.run_test() as pilot:
        assert app.query_one(StatusBar) is not None
        assert app.query_one("#view") is not None
        await pilot.press("q")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_initial_view_is_files() -> None:
    """Initial main content should show the Files view."""
    app = FileOrganizerApp()
    async with app.run_test():
        assert app._current_view == "files"


@pytest.mark.integration
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


@pytest.mark.integration
@pytest.mark.asyncio
async def test_switch_to_settings_view() -> None:
    """Switching to settings view should mount SettingsView."""
    app = FileOrganizerApp()
    async with app.run_test() as pilot:
        await app.action_switch_view("settings")
        await pilot.pause()
        assert app._current_view == "settings"
        assert app.query_one("#view", SettingsView) is not None


@pytest.mark.integration
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


@pytest.mark.integration
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


@pytest.mark.integration
@pytest.mark.asyncio
async def test_help_action_updates_status() -> None:
    """Help action should update the status bar with help info."""
    app = FileOrganizerApp()
    async with app.run_test() as pilot:
        app.action_toggle_help()
        await pilot.pause()
        status = app.query_one(StatusBar)
        assert "quit" in status._message.lower()


@pytest.mark.integration
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


@pytest.mark.integration
@pytest.mark.asyncio
async def test_switch_to_methodology_view() -> None:
    """Switching to methodology view should mount MethodologyView."""
    with patch.object(MethodologyView, "_update_preview"):
        app = FileOrganizerApp()
        async with app.run_test() as pilot:
            await app.action_switch_view("methodology")
            await pilot.pause()
            assert app._current_view == "methodology"
            assert app.query_one("#view", MethodologyView) is not None


@pytest.mark.integration
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


@pytest.mark.integration
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


@pytest.mark.integration
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


@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_notification() -> None:
    """When update is available, notification should be shown."""
    app = FileOrganizerApp()
    async with app.run_test() as pilot:
        app._notify_update("2.0.1")
        await pilot.pause()

        status_bar = app.query_one(StatusBar)
        assert "2.0.1" in status_bar._message
