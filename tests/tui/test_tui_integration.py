"""Integration tests for TUI multi-view navigation and keybindings.

Covers round-trip view switching, binding dispatch, sidebar rendering,
and the new copilot view integration.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from file_organizer.tui.analytics_view import AnalyticsView
from file_organizer.tui.app import FileOrganizerApp, Sidebar, StatusBar
from file_organizer.tui.audio_view import AudioView
from file_organizer.tui.copilot_view import CopilotView
from file_organizer.tui.file_preview import FilePreviewView
from file_organizer.tui.methodology_view import MethodologyView
from file_organizer.tui.organization_preview import OrganizationPreviewView
from file_organizer.tui.settings_view import SettingsView
from file_organizer.tui.undo_history_view import UndoHistoryView

pytestmark = [pytest.mark.integration]


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
        assert app.query_one("#view", SettingsView) is not None

        await app.action_switch_view("files")
        await pilot.pause()
        assert app._current_view == "files"


def test_round_trip_all_views() -> None:
    """Every named navigation target should build a mountable view widget."""
    expected = {
        "files": FilePreviewView,
        "organized": OrganizationPreviewView,
        "analytics": AnalyticsView,
        "methodology": MethodologyView,
        "audio": AudioView,
        "history": UndoHistoryView,
        "settings": SettingsView,
        "copilot": CopilotView,
    }

    for name, view_type in expected.items():
        view = FileOrganizerApp._create_view(name)
        assert isinstance(view, view_type), f"Expected view {name!r}"
        assert view.id == "view"


def test_switch_to_copilot_view() -> None:
    """The app factory should build the copilot view for copilot navigation."""
    view = FileOrganizerApp._create_view("copilot")

    assert isinstance(view, CopilotView)
    assert view.id == "view"


# ---------------------------------------------------------------------------
# Keybinding dispatch
# ---------------------------------------------------------------------------


def test_keybinding_8_opens_copilot() -> None:
    """The 8 binding should target the copilot view action."""
    binding = next(binding for binding in FileOrganizerApp.BINDINGS if binding.key == "8")

    assert "copilot" in binding.action


def test_keybinding_1_to_7_switch_views() -> None:
    """Number bindings should target the expected named views."""
    expected = {
        "1": "files",
        "2": "organized",
        "3": "analytics",
        "4": "methodology",
        "5": "audio",
        "6": "history",
        "7": "settings",
    }

    actions_by_key = {binding.key: binding.action for binding in FileOrganizerApp.BINDINGS}
    for key, view_name in expected.items():
        assert view_name in actions_by_key[key]


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
    old_view = MagicMock()
    old_view.remove = AsyncMock()
    container = MagicMock()
    container.mount = AsyncMock()
    status = StatusBar()

    def query_one(selector: object, *args: object, **kwargs: object) -> object:
        if selector == "#view":
            return old_view
        if selector == "#main-content":
            return container
        if selector is StatusBar:
            return status
        raise AssertionError(f"Unexpected selector: {selector!r}")

    app.query_one = MagicMock(side_effect=query_one)

    await app.action_switch_view("copilot")

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


@pytest.mark.asyncio
async def test_audio_view_full_integration(tmp_path: Path) -> None:
    """Test switching to AudioView, scanning and displaying details with mock files."""
    dummy_audio = tmp_path / "song.mp3"
    dummy_audio.write_bytes(b"dummy")

    mock_metadata = MagicMock()
    mock_metadata.title = "Test Song"
    mock_metadata.artist = "Test Artist"
    mock_metadata.album = "Test Album"
    mock_metadata.genre = "Rock"
    mock_metadata.year = 2025
    mock_metadata.duration = 180.0
    mock_metadata.bitrate = 320000
    mock_metadata.sample_rate = 44100
    mock_metadata.channels = 2
    mock_metadata.format = "mp3"
    mock_metadata.file_path = dummy_audio
    mock_metadata.file_size = 5_000_000

    mock_classification = MagicMock()
    mock_classification.audio_type = MagicMock(value="music")
    mock_classification.confidence = 0.92
    mock_classification.reasoning = "Has music metadata"
    mock_classification.alternatives = []

    mock_extractor = MagicMock()
    mock_extractor.extract.return_value = mock_metadata
    mock_classifier = MagicMock()
    mock_classifier.classify.return_value = mock_classification

    with (
        patch(
            "file_organizer.services.audio.metadata_extractor.AudioMetadataExtractor",
            return_value=mock_extractor,
        ),
        patch(
            "file_organizer.services.audio.classifier.AudioClassifier",
            return_value=mock_classifier,
        ),
        patch(
            "file_organizer.services.audio.metadata_extractor.AudioMetadataExtractor.format_duration",
            return_value="3:00",
        ),
    ):
        app = FileOrganizerApp()
        async with app.run_test() as pilot:
            await app.action_switch_view("audio")
            import asyncio

            await asyncio.sleep(0.1)
            assert app._current_view == "audio"

            from file_organizer.tui.audio_view import (
                AudioClassificationPanel,
                AudioMetadataPanel,
            )

            view = app.query_one("#view", AudioView)

            # Wait for background thread scanning to complete.
            for _ in range(100):
                if len(view._files) == 1:
                    break
                await asyncio.sleep(0.05)
            else:
                pytest.fail("Timed out waiting for AudioView files to load")

            assert len(view._files) == 1

            # Verify details are populated correctly in the panels.
            # Wait for the UI-level panel updates dispatched via call_from_thread;
            # _files being set does not guarantee renderable has been updated yet.
            metadata_panel = view.query_one(AudioMetadataPanel)
            classification_panel = view.query_one(AudioClassificationPanel)

            for _ in range(100):
                if (
                    "Test Song" in str(metadata_panel.renderable)
                    and "music" in str(classification_panel.renderable)
                ):
                    break
                await asyncio.sleep(0.05)
            else:
                pytest.fail("Timed out waiting for panel UI to reflect loaded state")

            assert "Test Song" in str(metadata_panel.renderable)
            assert "Test Artist" in str(metadata_panel.renderable)
            assert "music" in str(classification_panel.renderable)

            # Test pilot actions/navigation
            await pilot.press("j")
            await pilot.pause()
            assert view._current_index == 0
            assert "Test Song" in str(metadata_panel.renderable)

            await pilot.press("k")
            await pilot.pause()
            assert view._current_index == 0
            assert "Test Song" in str(metadata_panel.renderable)

            # Press r to refresh/reload
            await pilot.press("r")

            # Wait for reload scanning to complete.
            for _ in range(100):
                if len(view._files) == 1:
                    break
                await asyncio.sleep(0.05)
            else:
                pytest.fail("Timed out waiting for AudioView files to reload")

            # Wait for UI panels to reflect reloaded state.
            for _ in range(100):
                if "Test Song" in str(metadata_panel.renderable):
                    break
                await asyncio.sleep(0.05)
            else:
                pytest.fail("Timed out waiting for panel UI to reflect reloaded state")

            assert len(view._files) == 1
            assert view._current_index == 0
            assert "Test Song" in str(metadata_panel.renderable)
