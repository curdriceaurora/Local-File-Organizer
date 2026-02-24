"""Main Textual application for File Organizer TUI.

Provides the root App with a sidebar/main-content layout, status bar,
and placeholder views that will be replaced by downstream Phase 2 tasks.
"""

from __future__ import annotations

import threading

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import Footer, Header, Static


class StatusBar(Static):
    """Bottom status bar widget.

    Displays a short message that can be updated at runtime.
    """

    DEFAULT_CSS = """
    StatusBar {
        dock: bottom;
        height: 1;
        background: $accent;
        color: $text;
        padding: 0 1;
    }
    """

    def __init__(self, message: str = "Ready") -> None:
        """Initialize the status bar with an initial message."""
        super().__init__(message)
        self._message = message

    def set_status(self, message: str) -> None:
        """Update the displayed status message.

        Args:
            message: New status text.
        """
        self._message = message
        self.update(message)


class Sidebar(Static):
    """Left sidebar navigation panel."""

    DEFAULT_CSS = """
    Sidebar {
        width: 30;
        background: $surface;
        padding: 1;
        border-right: solid $primary;
    }
    """

    def compose(self) -> ComposeResult:
        """Compose the sidebar navigation content."""
        yield Static(
            "[b]Navigation[/b]\n\n"
            "[1] Files\n"
            "[2] Organized\n"
            "[3] Analytics\n"
            "[4] Methodology\n"
            "[5] Audio\n"
            "[6] History\n"
            "[7] Settings\n"
            "[8] Copilot"
        )


class PlaceholderView(Static):
    """Placeholder content view replaced by later Phase 2 tasks."""

    DEFAULT_CSS = """
    PlaceholderView {
        padding: 1 2;
    }
    """


class FileOrganizerApp(App[None]):
    """File Organizer terminal user interface.

    Layout::

        Header
        ┌──────────┬──────────────────────────┐
        │ Sidebar  │  MainContent             │
        │          │                           │
        └──────────┴──────────────────────────┘
        StatusBar
        Footer (keybindings)

    Bindings:
        q - Quit the application
        ? - Toggle help
        1 - Switch to Files view
        2 - Switch to Organized view
        3 - Switch to Analytics view
        4 - Switch to Methodology view
        5 - Switch to Audio view
        6 - Switch to History view
        7 - Switch to Settings view
        Tab - Cycle focus between panels
    """

    CSS = """
    #main-content {
        width: 1fr;
        padding: 1 2;
    }
    """

    TITLE = "File Organizer"
    SUB_TITLE = "AI-powered local file management"

    BINDINGS = [
        Binding("q", "quit", "Quit", priority=True),
        Binding("question_mark", "toggle_help", "Help"),
        Binding("1", "switch_view('files')", "Files"),
        Binding("2", "switch_view('organized')", "Organized"),
        Binding("3", "switch_view('analytics')", "Analytics"),
        Binding("4", "switch_view('methodology')", "Methodology"),
        Binding("5", "switch_view('audio')", "Audio"),
        Binding("6", "switch_view('history')", "History"),
        Binding("7", "switch_view('settings')", "Settings"),
        Binding("8", "switch_view('copilot')", "Copilot"),
        Binding("tab", "focus_next", "Next Panel"),
    ]

    def __init__(self) -> None:
        """Initialize the file organizer application."""
        super().__init__()
        self._current_view = "files"

    def on_mount(self) -> None:
        """Kick off background update checks after mount."""
        thread = threading.Thread(target=self._check_for_updates, daemon=True)
        thread.start()

    def compose(self) -> ComposeResult:
        """Compose the main application layout."""
        yield Header()
        with Horizontal():
            yield Sidebar()
            with Vertical(id="main-content"):
                yield self._create_view("files")
        yield StatusBar()
        yield Footer()

    # ------------------------------------------------------------------
    # View switching
    # ------------------------------------------------------------------

    async def action_switch_view(self, name: str) -> None:
        """Switch the main content area to the named view.

        Removes the current ``#view`` widget and mounts a new one
        created by ``_create_view()``.

        Args:
            name: View identifier (files, organized, settings).
        """
        self._current_view = name
        old = self.query_one("#view")
        await old.remove()
        new_view = self._create_view(name)
        container = self.query_one("#main-content")
        await container.mount(new_view)
        status = self.query_one(StatusBar)
        status.set_status(f"View: {name.capitalize()}")

    def _check_for_updates(self) -> None:
        from file_organizer.updater.background import maybe_check_for_updates

        status = maybe_check_for_updates()
        if status is None or not status.available:
            return
        self.call_from_thread(self._notify_update, status.latest_version)

    def _notify_update(self, latest_version: str) -> None:
        status_bar = self.query_one(StatusBar)
        status_bar.set_status(
            f"Update available: {latest_version} (run file-organizer update install)"
        )

    def action_toggle_help(self) -> None:
        """Toggle the help overlay."""
        self.query_one(StatusBar).set_status(
            "Press q to quit, 1-7 to switch views, Tab to navigate"
        )

    @staticmethod
    def _create_view(name: str) -> Widget:
        """Create and return the widget for a named view.

        Args:
            name: View identifier (files, organized, analytics,
                methodology, settings).

        Returns:
            Widget to mount as ``#view`` in the main content area.
        """
        if name == "files":
            from file_organizer.tui.file_preview import FilePreviewView

            return FilePreviewView(id="view")

        if name == "organized":
            from file_organizer.tui.organization_preview import (
                OrganizationPreviewView,
            )

            return OrganizationPreviewView(id="view")

        if name == "analytics":
            from file_organizer.tui.analytics_view import AnalyticsView

            return AnalyticsView(id="view")

        if name == "methodology":
            from file_organizer.tui.methodology_view import MethodologyView

            return MethodologyView(id="view")

        if name == "audio":
            from file_organizer.tui.audio_view import AudioView

            return AudioView(id="view")

        if name == "history":
            from file_organizer.tui.undo_history_view import UndoHistoryView

            return UndoHistoryView(id="view")

        if name == "copilot":
            from file_organizer.tui.copilot_view import CopilotView

            return CopilotView(id="view")

        # Settings remains a placeholder for now
        titles = {
            "settings": "[b]Settings[/b]\n\nConfigure models, paths, and preferences.",
        }
        return PlaceholderView(titles.get(name, f"[b]{name.capitalize()}[/b]"), id="view")


def run_tui() -> None:
    """Launch the File Organizer TUI.

    Convenience entry point called from the CLI ``tui`` command.
    """
    app = FileOrganizerApp()
    app.run()
