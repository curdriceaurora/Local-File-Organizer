"""End-to-end Pilot integration tests for the Textual TUI app.

These boot the real :class:`FileOrganizerApp` through Textual's headless
``run_test`` driver and drive it with simulated key presses, asserting the
main-content view actually transitions between the real view widgets and the
status bar updates — genuine UI-transition coverage rather than mocked units.

Only two external touchpoints are neutralized: the setup-wizard check (so the
main layout composes instead of the wizard) and the background update thread
(so no network call fires during the test).
"""

from __future__ import annotations

import pytest

from file_organizer.tui.analytics_view import AnalyticsView
from file_organizer.tui.app import FileOrganizerApp, StatusBar
from file_organizer.tui.file_preview import FilePreviewView
from file_organizer.tui.methodology_view import MethodologyView
from file_organizer.tui.settings_view import SettingsView
from file_organizer.tui.undo_history_view import UndoHistoryView

pytestmark = [pytest.mark.integration, pytest.mark.ci]


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch) -> FileOrganizerApp:
    """A FileOrganizerApp with the wizard skipped and update thread stubbed."""
    monkeypatch.setattr(FileOrganizerApp, "_check_setup_needed", lambda self: False)
    monkeypatch.setattr(FileOrganizerApp, "_check_for_updates", lambda self: None)
    return FileOrganizerApp()


async def test_app_boots_into_files_view(app: FileOrganizerApp) -> None:
    """The app mounts the main layout with the files view and a status bar."""
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app._current_view == "files"
        assert isinstance(app.query_one("#view"), FilePreviewView)
        # The status bar is present and the app is not in the wizard.
        assert app.query_one(StatusBar) is not None
        assert app._in_wizard is False


async def test_view_switching_transitions_between_views(app: FileOrganizerApp) -> None:
    """Number keys switch the main-content view to the corresponding widget.

    The ``organized`` view is intentionally excluded: mounting it kicks off a
    real organization preview (network-dependent) and overwrites the status
    bar, which would make this transition-focused test slow and flaky.
    """
    transitions = [
        ("3", "analytics", AnalyticsView),
        ("4", "methodology", MethodologyView),
        ("6", "history", UndoHistoryView),
        ("7", "settings", SettingsView),
        ("1", "files", FilePreviewView),
    ]
    async with app.run_test() as pilot:
        await pilot.pause()
        for key, expected_name, expected_type in transitions:
            await pilot.press(key)
            await pilot.pause()
            # The transition itself: the named view widget is now mounted.
            assert app._current_view == expected_name
            assert isinstance(app.query_one("#view"), expected_type)


async def test_toggle_help_updates_status_bar(app: FileOrganizerApp) -> None:
    """The help binding writes usage text to the status bar."""
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("question_mark")
        await pilot.pause()
        rendered = str(app.query_one(StatusBar).render())
        assert "quit" in rendered.lower()
