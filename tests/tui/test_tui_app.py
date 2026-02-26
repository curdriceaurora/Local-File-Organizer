"""Tests for file_organizer.tui.app module."""

from __future__ import annotations

import pytest
from textual.app import App
from textual.binding import Binding
from textual.widgets import Static

from file_organizer.tui.app import (
    FileOrganizerApp,
    PlaceholderView,
    Sidebar,
    StatusBar,
    run_tui,
)

pytestmark = [pytest.mark.unit]


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

    def test_default_css_defined(self) -> None:
        assert "StatusBar" in StatusBar.DEFAULT_CSS


class TestSidebar:
    """Tests for the Sidebar widget."""

    def test_inherits_from_static(self) -> None:
        assert issubclass(Sidebar, Static)

    def test_has_compose_method(self) -> None:
        assert callable(getattr(Sidebar, "compose", None))

    def test_default_css_defined(self) -> None:
        assert "Sidebar" in Sidebar.DEFAULT_CSS


class TestPlaceholderView:
    """Tests for the PlaceholderView widget."""

    def test_inherits_from_static(self) -> None:
        assert issubclass(PlaceholderView, Static)

    def test_default_css_defined(self) -> None:
        assert "PlaceholderView" in PlaceholderView.DEFAULT_CSS


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

    def test_create_view_settings_returns_placeholder(self) -> None:
        widget = FileOrganizerApp._create_view("settings")
        assert isinstance(widget, PlaceholderView)

    def test_create_view_settings_has_view_id(self) -> None:
        widget = FileOrganizerApp._create_view("settings")
        assert widget.id == "view"

    def test_create_view_unknown_returns_placeholder(self) -> None:
        widget = FileOrganizerApp._create_view("nonexistent_view_xyz")
        assert isinstance(widget, PlaceholderView)
        assert widget.id == "view"


class TestRunTui:
    """Tests for the run_tui function."""

    def test_run_tui_is_callable(self) -> None:
        assert callable(run_tui)
