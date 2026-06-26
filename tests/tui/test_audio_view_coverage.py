# ruff: noqa: E402
"""Unit and integration coverage tests for file_organizer.tui.audio_view.

Targets 100% statement and branch coverage for AudioView and its panels.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, PropertyMock, patch

import pytest


# 1. Mock textual.work decorator BEFORE importing AudioView
def mock_work_decorator(*args, **kwargs):
    if len(args) == 1 and callable(args[0]):
        return args[0]
    return lambda f: f


import textual

textual.work = mock_work_decorator

from textual.widgets import Static

from file_organizer.tui.audio_view import (
    AudioClassificationPanel,
    AudioFileListPanel,
    AudioMetadataPanel,
    AudioView,
    _truncate,
)

pytestmark = pytest.mark.unit


def _create_view_with_mocks() -> tuple[AudioView, dict[type[Static], MagicMock], MagicMock]:
    """Helper to create an AudioView with panels and app mocked."""
    view = AudioView(scan_dir="/mock/dir")

    # Mock panels
    mock_list_panel = MagicMock(spec=AudioFileListPanel)
    mock_meta_panel = MagicMock(spec=AudioMetadataPanel)
    mock_class_panel = MagicMock(spec=AudioClassificationPanel)

    panels = {
        AudioFileListPanel: mock_list_panel,
        AudioMetadataPanel: mock_meta_panel,
        AudioClassificationPanel: mock_class_panel,
    }

    def mock_query_one(panel_type):
        return panels.get(panel_type, MagicMock())

    view.query_one = MagicMock(side_effect=mock_query_one)

    # Mock app property
    mock_app = MagicMock()
    app_prop = PropertyMock(return_value=mock_app)
    type(view).app = app_prop

    # Force call_from_thread to execute synchronously in tests
    mock_app.call_from_thread = lambda func, *args, **kwargs: func(*args, **kwargs)

    return view, panels, mock_app


# --- Panel Tests ---


def test_audio_file_list_panel_empty() -> None:
    """Verify AudioFileListPanel behavior with no files."""
    panel = AudioFileListPanel()
    with patch.object(panel, "update") as mock_update:
        panel.set_files([])
        mock_update.assert_called_once_with(
            "[b]Audio Files[/b]\n\n  [dim]No audio files found.[/dim]"
        )


def test_audio_file_list_panel_with_files() -> None:
    """Verify AudioFileListPanel with files, including a long filename for truncation."""
    panel = AudioFileListPanel()
    files = [
        ("short.mp3", "MP3", "02:30"),
        ("this_is_a_very_long_filename_that_needs_to_be_truncated.wav", "WAV", "10:15"),
    ]
    with patch.object(panel, "update") as mock_update:
        panel.set_files(files)
        mock_update.assert_called_once()
        markup = mock_update.call_args[0][0]
        assert "Audio Files" in markup
        assert "short.mp3" in markup
        assert "this_is_a_very_long_filename" in markup
        # Check ellipsis character \u2026 is present
        assert "\u2026" in markup


def test_audio_metadata_panel_none() -> None:
    """Verify AudioMetadataPanel behavior with None metadata."""
    panel = AudioMetadataPanel()
    with patch.object(panel, "update") as mock_update:
        panel.set_metadata(None)
        mock_update.assert_called_once_with(
            "[b]Metadata[/b]\n\n  [dim]Select a file to view metadata.[/dim]"
        )


def test_audio_metadata_panel_valid() -> None:
    """Verify AudioMetadataPanel with valid metadata and formatters."""
    panel = AudioMetadataPanel()
    mock_metadata = MagicMock()
    mock_metadata.title = "Song Title"
    mock_metadata.artist = "Artist Name"
    mock_metadata.album = "Album Name"
    mock_metadata.genre = "Rock"
    mock_metadata.year = "2024"
    mock_metadata.duration = 185.5
    mock_metadata.bitrate = 320000
    mock_metadata.sample_rate = 44100
    mock_metadata.channels = 2

    with patch.object(panel, "update") as mock_update:
        panel.set_metadata(mock_metadata)
        mock_update.assert_called_once()
        markup = mock_update.call_args[0][0]
        assert "Title:        Song Title" in markup
        assert "Artist:       Artist Name" in markup
        assert "Album:        Album Name" in markup
        assert "Genre:        Rock" in markup
        assert "Year:         2024" in markup
        assert "Tag complete:" in markup


def test_audio_metadata_panel_format_exception() -> None:
    """Verify AudioMetadataPanel fallback formatting on extractor exception."""
    panel = AudioMetadataPanel()
    mock_metadata = MagicMock()
    mock_metadata.title = None
    mock_metadata.artist = None
    mock_metadata.album = None
    mock_metadata.genre = None
    mock_metadata.year = None
    mock_metadata.duration = 185.5
    mock_metadata.bitrate = 320000
    mock_metadata.sample_rate = 44100
    mock_metadata.channels = 2

    # Mock the extractor formatting to raise Exception
    with (
        patch(
            "file_organizer.services.audio.metadata_extractor.AudioMetadataExtractor"
        ) as mock_ext_class,
        patch.object(panel, "update") as mock_update,
    ):
        mock_ext_class.format_duration.side_effect = Exception("Format error")
        panel.set_metadata(mock_metadata)
        mock_update.assert_called_once()
        markup = mock_update.call_args[0][0]
        assert "185.5s" in markup
        assert "320000 bps" in markup
        assert "unknown" in markup


def test_audio_classification_panel_none() -> None:
    """Verify AudioClassificationPanel behavior with None result."""
    panel = AudioClassificationPanel()
    with patch.object(panel, "update") as mock_update:
        panel.set_classification(None)
        mock_update.assert_called_once_with(
            "[b]Classification[/b]\n\n  [dim]No classification available.[/dim]"
        )


def test_audio_classification_panel_valid() -> None:
    """Verify AudioClassificationPanel with different confidence thresholds and alternatives."""
    panel = AudioClassificationPanel()

    # 1. High confidence, alternatives with value attributes
    mock_result = MagicMock()
    mock_result.audio_type = MagicMock()
    mock_result.audio_type.value = "music"
    mock_result.confidence = 0.95
    mock_result.reasoning = "Clear melodic patterns."

    mock_alt = MagicMock()
    mock_alt.audio_type = MagicMock()
    mock_alt.audio_type.value = "speech"
    mock_alt.confidence = 0.05
    mock_alt.reasoning = "Background whisper."
    mock_result.alternatives = [mock_alt]

    with patch.object(panel, "update") as mock_update:
        panel.set_classification(mock_result)
        markup = mock_update.call_args[0][0]
        assert "Type:       [bold]music[/bold]" in markup
        assert "Reasoning:  Clear melodic patterns." in markup
        assert "Alternatives:" in markup
        assert "speech" in markup

    # 2. Medium confidence, no value attribute on audio_type, no alternatives
    mock_result_2 = MagicMock()
    mock_result_2.audio_type = "speech"
    mock_result_2.confidence = 0.55
    mock_result_2.reasoning = "Spoken words."
    mock_result_2.alternatives = []

    with patch.object(panel, "update") as mock_update:
        panel.set_classification(mock_result_2)
        markup = mock_update.call_args[0][0]
        assert "Type:       [bold]speech[/bold]" in markup
        assert "Alternatives:" not in markup

    # 3. Low confidence to trigger red color branch
    mock_result_3 = MagicMock()
    mock_result_3.audio_type = "noise"
    mock_result_3.confidence = 0.2
    mock_result_3.reasoning = "Unstructured hiss."
    mock_result_3.alternatives = []

    with patch.object(panel, "update") as mock_update:
        panel.set_classification(mock_result_3)
        markup = mock_update.call_args[0][0]
        assert "[red]" in markup


# --- AudioView Tests ---


def test_audio_view_initialization() -> None:
    """Verify AudioView fields on creation."""
    view = AudioView(scan_dir="/some/path")
    assert view._scan_dir == Path("/some/path")
    assert view._files == []
    assert view._current_index == 0


def test_audio_view_compose() -> None:
    """Verify compose yields the correct sub-widgets."""
    view = AudioView()
    widgets = list(view.compose())
    assert len(widgets) == 4
    assert widgets[0].id == "audio-header"
    assert isinstance(widgets[1], AudioFileListPanel)
    assert isinstance(widgets[2], AudioMetadataPanel)
    assert isinstance(widgets[3], AudioClassificationPanel)


def test_audio_view_on_mount() -> None:
    """Verify on_mount triggers scan."""
    view, _, _ = _create_view_with_mocks()
    with patch.object(view, "_scan_audio_files") as mock_scan:
        view.on_mount()
        mock_scan.assert_called_once()


def test_audio_view_action_refresh_audio() -> None:
    """Verify refresh action resets state and triggers scan."""
    view, panels, _ = _create_view_with_mocks()
    view._files = [("somefile", None, None)]
    view._current_index = 5

    with patch.object(view, "_scan_audio_files") as mock_scan:
        view.action_refresh_audio()
        assert view._files == []
        assert view._current_index == 0

        panels[AudioFileListPanel].update.assert_called_once_with("[dim]Scanning...[/dim]")
        panels[AudioMetadataPanel].update.assert_called_once_with("[dim]Loading...[/dim]")
        panels[AudioClassificationPanel].update.assert_called_once_with("[dim]Loading...[/dim]")
        mock_scan.assert_called_once()


def test_audio_view_action_next_prev_navigation() -> None:
    """Verify next/prev navigation handles boundary cases and updates panels."""
    view, panels, _ = _create_view_with_mocks()

    # 1. Navigation with empty files list
    view._files = []
    view.action_next_file()
    assert view._current_index == 0
    view.action_prev_file()
    assert view._current_index == 0

    # 2. Setup mock files
    file1 = (Path("1.mp3"), MagicMock(), MagicMock())
    file2 = (Path("2.mp3"), MagicMock(), MagicMock())
    file3 = (Path("3.mp3"), MagicMock(), MagicMock())
    view._files = [file1, file2, file3]
    view._current_index = 0

    # Go next -> index 1
    view.action_next_file()
    assert view._current_index == 1
    panels[AudioMetadataPanel].set_metadata.assert_called_with(file2[1])
    panels[AudioClassificationPanel].set_classification.assert_called_with(file2[2])

    # Go next -> index 2 (boundary)
    view.action_next_file()
    assert view._current_index == 2

    # Go next again -> stays at index 2 (boundary)
    view.action_next_file()
    assert view._current_index == 2

    # Go prev -> index 1
    view.action_prev_file()
    assert view._current_index == 1

    # Go prev -> index 0 (boundary)
    view.action_prev_file()
    assert view._current_index == 0

    # Go prev again -> stays at index 0 (boundary)
    view.action_prev_file()
    assert view._current_index == 0


def test_audio_view_scan_no_audio_files() -> None:
    """Verify scanning directory with no audio files updates panels correctly."""
    view, panels, _ = _create_view_with_mocks()

    # Mock Path methods
    mock_dir = MagicMock()
    mock_dir.is_dir.return_value = True
    mock_dir.rglob.return_value = [Path("file.txt"), Path("image.png")]
    view._scan_dir = mock_dir

    with (
        patch("file_organizer.services.audio.metadata_extractor.AudioMetadataExtractor"),
        patch("file_organizer.services.audio.classifier.AudioClassifier"),
        patch.object(view, "_set_status") as mock_status,
    ):
        view._scan_audio_files()

        panels[AudioFileListPanel].set_files.assert_called_once_with([])
        panels[AudioMetadataPanel].set_metadata.assert_called_once_with(None)
        panels[AudioClassificationPanel].set_classification.assert_called_once_with(None)
        mock_status.assert_called_once_with("No audio files found")


def test_audio_view_scan_success() -> None:
    """Verify scanning directory with audio files extracts, classifies, and updates panels."""
    view, panels, _ = _create_view_with_mocks()

    p1 = Path("track1.mp3")
    p2 = Path("track2.wav")

    mock_dir = MagicMock()
    mock_dir.is_dir.return_value = True
    mock_dir.rglob.return_value = [p1, p2]
    view._scan_dir = mock_dir

    # Mock extractors/classifiers
    mock_extractor = MagicMock()
    mock_meta1 = MagicMock(duration=120.0, format="MP3")
    mock_meta2 = MagicMock(duration=90.0, format="WAV")
    mock_extractor.extract.side_effect = [mock_meta1, mock_meta2]

    mock_classifier = MagicMock()
    mock_class1 = MagicMock()
    mock_class2 = MagicMock()
    mock_classifier.classify.side_effect = [mock_class1, mock_class2]

    with (
        patch.object(Path, "is_file", return_value=True),
        patch(
            "file_organizer.services.audio.metadata_extractor.AudioMetadataExtractor"
        ) as mock_extractor_class,
        patch(
            "file_organizer.services.audio.classifier.AudioClassifier", return_value=mock_classifier
        ),
        patch.object(view, "_set_status") as mock_status,
    ):
        mock_extractor_class.return_value = mock_extractor
        mock_extractor_class.format_duration.side_effect = lambda d: (
            "02:00" if d == 120.0 else "01:30"
        )
        view._scan_audio_files()

        # Verify extractor/classifier calls
        assert mock_extractor.extract.call_count == 2
        assert mock_classifier.classify.call_count == 2

        # Verify files stored
        assert len(view._files) == 2
        assert view._files[0] == (p1, mock_meta1, mock_class1)

        # Verify panel updates
        panels[AudioFileListPanel].set_files.assert_called_once_with(
            [
                ("track1.mp3", "MP3", "02:00"),
                ("track2.wav", "WAV", "01:30"),
            ]
        )
        panels[AudioMetadataPanel].set_metadata.assert_called_once_with(mock_meta1)
        panels[AudioClassificationPanel].set_classification.assert_called_once_with(mock_class1)
        mock_status.assert_called_once_with("Audio: 2 files loaded")


def test_audio_view_scan_extraction_exception() -> None:
    """Verify scan handles exceptions during single file metadata extraction gracefully."""
    view, panels, _ = _create_view_with_mocks()

    p1 = Path("track1.mp3")
    mock_dir = MagicMock()
    mock_dir.is_dir.return_value = True
    mock_dir.rglob.return_value = [p1]
    view._scan_dir = mock_dir

    mock_extractor = MagicMock()
    mock_extractor.extract.side_effect = Exception("Read error")

    with (
        patch.object(Path, "is_file", return_value=True),
        patch(
            "file_organizer.services.audio.metadata_extractor.AudioMetadataExtractor",
            return_value=mock_extractor,
        ),
        patch("file_organizer.services.audio.classifier.AudioClassifier"),
        patch.object(view, "_set_status"),
    ):
        view._scan_audio_files()

        # Verify it falls back and marks metadata/classification as None
        assert len(view._files) == 1
        assert view._files[0] == (p1, None, None)

        panels[AudioFileListPanel].set_files.assert_called_once_with(
            [
                ("track1.mp3", "mp3", "?"),
            ]
        )


def test_audio_view_scan_import_error() -> None:
    """Verify scan catches ImportError and shows warning on all panels."""
    view, panels, _ = _create_view_with_mocks()

    with patch(
        "file_organizer.services.audio.metadata_extractor.AudioMetadataExtractor",
        side_effect=ImportError("mutagen missing"),
    ):
        view._scan_audio_files()

        for panel in panels.values():
            panel.update.assert_called_once()
            assert "mutagen" in panel.update.call_args[0][0]


def test_audio_view_scan_general_exception() -> None:
    """Verify scan catches general exceptions and shows warning on all panels."""
    view, panels, _ = _create_view_with_mocks()

    with patch(
        "file_organizer.services.audio.metadata_extractor.AudioMetadataExtractor",
        side_effect=ValueError("Global crash"),
    ):
        view._scan_audio_files()

        for panel in panels.values():
            panel.update.assert_called_once()
            assert "Global crash" in panel.update.call_args[0][0]


def test_audio_view_status_bar_updates() -> None:
    """Verify _set_status updates application StatusBar or logs on failure."""
    view, _, mock_app = _create_view_with_mocks()

    # 1. Success path
    mock_status_bar = MagicMock()
    mock_app.query_one.return_value = mock_status_bar
    view._set_status("Playing track")
    mock_status_bar.set_status.assert_called_once_with("Playing track")

    # 2. Exception path
    mock_app.query_one.side_effect = Exception("No status bar")
    with patch("file_organizer.tui.audio_view.logger") as mock_logger:
        view._set_status("Playing track")
        # Should not crash, but log debug message
        mock_logger.debug.assert_called_once()


def test_truncate_helper() -> None:
    """Verify _truncate helper logic."""
    assert _truncate("hello", 10) == "hello"
    assert _truncate("hello world", 5) == "hell\u2026"
