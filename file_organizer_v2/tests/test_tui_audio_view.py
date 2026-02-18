"""Tests for TUI audio view."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.tui.audio_view import (
    AudioClassificationPanel,
    AudioFileListPanel,
    AudioMetadataPanel,
    AudioView,
    _truncate,
)


def _get_content(panel: object) -> str:
    """Get the text content of a Static widget."""
    return str(getattr(panel, "_Static__content", ""))


# ---------------------------------------------------------------------------
# Helper: create mock AudioMetadata and ClassificationResult
# ---------------------------------------------------------------------------


def _make_metadata(
    title: str | None = "Test Song",
    artist: str | None = "Test Artist",
    album: str | None = "Test Album",
    genre: str | None = "Rock",
    year: int | None = 2025,
    duration: float = 180.0,
    bitrate: int = 320000,
    sample_rate: int = 44100,
    channels: int = 2,
    fmt: str = "mp3",
) -> MagicMock:
    """Create a mock AudioMetadata."""
    m = MagicMock()
    m.title = title
    m.artist = artist
    m.album = album
    m.genre = genre
    m.year = year
    m.duration = duration
    m.bitrate = bitrate
    m.sample_rate = sample_rate
    m.channels = channels
    m.format = fmt
    m.file_path = Path("/audio/test.mp3")
    m.file_size = 5_000_000
    return m


def _make_classification(
    audio_type: str = "music",
    confidence: float = 0.92,
    reasoning: str = "Has music metadata",
) -> MagicMock:
    """Create a mock ClassificationResult."""
    c = MagicMock()
    c.audio_type = MagicMock(value=audio_type)
    c.confidence = confidence
    c.reasoning = reasoning
    c.alternatives = []
    return c


# ---------------------------------------------------------------------------
# Unit: AudioFileListPanel
# ---------------------------------------------------------------------------


class TestAudioFileListPanel:
    """Unit tests for AudioFileListPanel."""

    def test_set_files_empty(self) -> None:
        panel = AudioFileListPanel()
        panel.set_files([])
        assert "No audio files" in _get_content(panel)

    def test_set_files_with_data(self) -> None:
        files = [
            ("song.mp3", "mp3", "3:00"),
            ("podcast.wav", "wav", "45:12"),
        ]
        panel = AudioFileListPanel()
        panel.set_files(files)
        text = _get_content(panel)
        assert "Audio Files" in text
        assert "song.mp3" in text
        assert "podcast.wav" in text
        assert "2 found" in text


# ---------------------------------------------------------------------------
# Unit: AudioMetadataPanel
# ---------------------------------------------------------------------------


class TestAudioMetadataPanel:
    """Unit tests for AudioMetadataPanel."""

    def test_set_metadata_none(self) -> None:
        panel = AudioMetadataPanel()
        panel.set_metadata(None)
        assert "Select a file" in _get_content(panel)

    def test_set_metadata_with_data(self) -> None:
        panel = AudioMetadataPanel()
        panel.set_metadata(_make_metadata())
        text = _get_content(panel)
        assert "Metadata" in text
        assert "Test Song" in text
        assert "Test Artist" in text

    def test_set_metadata_missing_fields(self) -> None:
        panel = AudioMetadataPanel()
        meta = _make_metadata(title=None, artist=None, album=None, genre=None, year=None)
        panel.set_metadata(meta)
        assert "unknown" in _get_content(panel)


# ---------------------------------------------------------------------------
# Unit: AudioClassificationPanel
# ---------------------------------------------------------------------------


class TestAudioClassificationPanel:
    """Unit tests for AudioClassificationPanel."""

    def test_set_classification_none(self) -> None:
        panel = AudioClassificationPanel()
        panel.set_classification(None)
        assert "No classification" in _get_content(panel)

    def test_set_classification_with_data(self) -> None:
        panel = AudioClassificationPanel()
        panel.set_classification(_make_classification())
        text = _get_content(panel)
        assert "music" in text
        assert "92%" in text
        assert "Has music metadata" in text

    def test_set_classification_with_alternatives(self) -> None:
        result = _make_classification()
        alt = MagicMock()
        alt.audio_type = MagicMock(value="podcast")
        alt.confidence = 0.05
        alt.reasoning = "Low confidence"
        result.alternatives = [alt]
        panel = AudioClassificationPanel()
        panel.set_classification(result)
        text = _get_content(panel)
        assert "Alternatives" in text
        assert "podcast" in text


# ---------------------------------------------------------------------------
# Unit: helpers
# ---------------------------------------------------------------------------


class TestHelpers:
    """Unit tests for module-level helpers."""

    def test_truncate_short(self) -> None:
        assert _truncate("hello", 10) == "hello"

    def test_truncate_long(self) -> None:
        result = _truncate("a very long string", 10)
        assert len(result) == 10
        assert result.endswith("\u2026")


# ---------------------------------------------------------------------------
# Integration: AudioView in app context
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audio_view_mounts() -> None:
    """AudioView should mount and render panels."""
    from file_organizer.tui.app import FileOrganizerApp

    with patch.object(AudioView, "_scan_audio_files"):
        app = FileOrganizerApp()
        async with app.run_test() as pilot:
            await app.action_switch_view("audio")
            await pilot.pause()
            view = app.query_one("#view", AudioView)
            assert view is not None
            assert app.query_one(AudioFileListPanel) is not None
            assert app.query_one(AudioMetadataPanel) is not None
            assert app.query_one(AudioClassificationPanel) is not None


@pytest.mark.asyncio
async def test_audio_view_bindings_exist() -> None:
    """AudioView should have r, j, k bindings."""
    binding_keys = {b.key for b in AudioView.BINDINGS}
    assert "r" in binding_keys
    assert "j" in binding_keys
    assert "k" in binding_keys


def test_audio_view_navigation() -> None:
    """j/k navigation should change current index."""
    with patch.object(AudioView, "_scan_audio_files"):
        view = AudioView(scan_dir=".")
        # Simulate having files loaded (no panels to query, just test index logic)
        view._files = [
            (Path("/a.mp3"), _make_metadata(), _make_classification()),
            (Path("/b.mp3"), _make_metadata(), _make_classification()),
            (Path("/c.mp3"), _make_metadata(), _make_classification()),
        ]
        # Patch _show_file_details to avoid query_one calls outside app context
        with patch.object(view, "_show_file_details"):
            view._current_index = 0
            view.action_next_file()
            assert view._current_index == 1
            view.action_next_file()
            assert view._current_index == 2
            view.action_next_file()
            assert view._current_index == 2  # Capped at end
            view.action_prev_file()
            assert view._current_index == 1
            view.action_prev_file()
            assert view._current_index == 0
            view.action_prev_file()
            assert view._current_index == 0  # Capped at start
