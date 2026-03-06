"""Unit tests for the TUI audio view module.

Tests panel rendering, AudioView init/navigation, and the _truncate helper.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.tui.audio_view import (
    AudioClassificationPanel,
    AudioFileListPanel,
    AudioMetadataPanel,
    AudioView,
    _truncate,
)

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Fake data objects
# ---------------------------------------------------------------------------


@dataclass
class FakeMetadata:
    """Minimal audio metadata stand-in."""

    title: str | None = "Test Song"
    artist: str | None = "Artist"
    album: str | None = "Album"
    genre: str | None = "Rock"
    year: int | None = 2024
    duration: float = 180.0
    bitrate: int = 320000
    sample_rate: int = 44100
    channels: int = 2
    format: str = "mp3"


@dataclass
class FakeClassification:
    """Minimal classification result stand-in."""

    audio_type: SimpleNamespace = field(default_factory=lambda: SimpleNamespace(value="music"))
    confidence: float = 0.85
    reasoning: str = "Detected melody"
    alternatives: list = field(default_factory=list)


@dataclass
class FakeAltClassification:
    """Alternative classification entry."""

    audio_type: SimpleNamespace = field(default_factory=lambda: SimpleNamespace(value="speech"))
    confidence: float = 0.1
    reasoning: str = "Low match"


# ---------------------------------------------------------------------------
# _truncate helper
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestTruncate:
    """Test the _truncate utility function."""

    def test_short_text_unchanged(self):
        assert _truncate("hello", 10) == "hello"

    def test_exact_length(self):
        assert _truncate("hello", 5) == "hello"

    def test_long_text_truncated(self):
        result = _truncate("hello world", 6)
        assert len(result) == 6
        assert result.endswith("\u2026")

    def test_empty_string(self):
        assert _truncate("", 5) == ""

    def test_one_char_max(self):
        result = _truncate("abc", 1)
        assert result == "\u2026"


# ---------------------------------------------------------------------------
# AudioFileListPanel
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAudioFileListPanel:
    """Test AudioFileListPanel rendering."""

    def test_set_files_empty(self):
        panel = AudioFileListPanel()
        panel.update = MagicMock()
        panel.set_files([])
        panel.update.assert_called_once()
        rendered = panel.update.call_args[0][0]
        assert "No audio files" in rendered

    def test_set_files_with_data(self):
        panel = AudioFileListPanel()
        panel.update = MagicMock()
        files = [
            ("song.mp3", "mp3", "3:00"),
            ("podcast.wav", "wav", "45:00"),
        ]
        panel.set_files(files)
        rendered = panel.update.call_args[0][0]
        assert "2 found" in rendered
        assert "song.mp3" in rendered
        assert "podcast.wav" in rendered

    def test_set_files_truncates_long_names(self):
        panel = AudioFileListPanel()
        panel.update = MagicMock()
        long_name = "a" * 50 + ".mp3"
        panel.set_files([(long_name, "mp3", "1:00")])
        rendered = panel.update.call_args[0][0]
        assert "1 found" in rendered


# ---------------------------------------------------------------------------
# AudioMetadataPanel
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAudioMetadataPanel:
    """Test AudioMetadataPanel rendering."""

    def test_set_metadata_none(self):
        panel = AudioMetadataPanel()
        panel.update = MagicMock()
        panel.set_metadata(None)
        rendered = panel.update.call_args[0][0]
        assert "Select a file" in rendered

    def test_set_metadata_with_data(self):
        panel = AudioMetadataPanel()
        panel.update = MagicMock()
        meta = FakeMetadata()
        # Patch the import to avoid needing the real extractor
        with patch(
            "file_organizer.services.audio.metadata_extractor.AudioMetadataExtractor"
        ) as mock_cls:
            mock_cls.format_duration.return_value = "3:00"
            mock_cls.format_bitrate.return_value = "320 kbps"
            panel.set_metadata(meta)

        rendered = panel.update.call_args[0][0]
        assert "Test Song" in rendered
        assert "Artist" in rendered
        assert "Rock" in rendered
        assert "44100" in rendered

    def test_set_metadata_import_failure(self):
        panel = AudioMetadataPanel()
        panel.update = MagicMock()
        meta = FakeMetadata()
        # Block the import so the except branch triggers
        mod_key = "file_organizer.services.audio.metadata_extractor"
        saved = sys.modules.get(mod_key)
        sys.modules[mod_key] = None  # causes ImportError on `from ... import`
        try:
            panel.set_metadata(meta)
        finally:
            if saved is None:
                sys.modules.pop(mod_key, None)
            else:
                sys.modules[mod_key] = saved
        rendered = panel.update.call_args[0][0]
        assert "180.0s" in rendered or "180" in rendered

    def test_tag_completeness_partial(self):
        panel = AudioMetadataPanel()
        panel.update = MagicMock()
        meta = FakeMetadata(title=None, artist=None, album=None)
        with patch(
            "file_organizer.services.audio.metadata_extractor.AudioMetadataExtractor",
            side_effect=Exception("fail"),
        ):
            panel.set_metadata(meta)
        rendered = panel.update.call_args[0][0]
        # 2 of 5 fields filled (genre, year) → 40%
        assert "40%" in rendered


# ---------------------------------------------------------------------------
# AudioClassificationPanel
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAudioClassificationPanel:
    """Test AudioClassificationPanel rendering."""

    def test_set_classification_none(self):
        panel = AudioClassificationPanel()
        panel.update = MagicMock()
        panel.set_classification(None)
        rendered = panel.update.call_args[0][0]
        assert "No classification" in rendered

    def test_set_classification_high_confidence(self):
        panel = AudioClassificationPanel()
        panel.update = MagicMock()
        cls = FakeClassification()
        panel.set_classification(cls)
        rendered = panel.update.call_args[0][0]
        assert "music" in rendered
        assert "85%" in rendered
        assert "green" in rendered

    def test_set_classification_medium_confidence(self):
        panel = AudioClassificationPanel()
        panel.update = MagicMock()
        cls = FakeClassification(confidence=0.5)
        panel.set_classification(cls)
        rendered = panel.update.call_args[0][0]
        assert "yellow" in rendered

    def test_set_classification_low_confidence(self):
        panel = AudioClassificationPanel()
        panel.update = MagicMock()
        cls = FakeClassification(confidence=0.2)
        panel.set_classification(cls)
        rendered = panel.update.call_args[0][0]
        assert "red" in rendered

    def test_set_classification_with_alternatives(self):
        panel = AudioClassificationPanel()
        panel.update = MagicMock()
        cls = FakeClassification(alternatives=[FakeAltClassification(), FakeAltClassification()])
        panel.set_classification(cls)
        rendered = panel.update.call_args[0][0]
        assert "speech" in rendered
        assert "Alternatives" in rendered

    def test_audio_type_without_value_attr(self):
        panel = AudioClassificationPanel()
        panel.update = MagicMock()
        cls = FakeClassification()
        cls.audio_type = "plain_string"
        panel.set_classification(cls)
        rendered = panel.update.call_args[0][0]
        assert "plain_string" in rendered


# ---------------------------------------------------------------------------
# AudioView init and navigation
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAudioViewInit:
    """Test AudioView initialization."""

    def test_default_scan_dir(self):
        view = AudioView()
        assert view._scan_dir == Path(".")
        assert view._files == []
        assert view._current_index == 0

    def test_custom_scan_dir(self, tmp_path):
        view = AudioView(scan_dir=tmp_path)
        assert view._scan_dir == tmp_path

    def test_string_scan_dir(self):
        view = AudioView(scan_dir="/tmp")
        assert view._scan_dir == Path("/tmp")


@pytest.mark.unit
class TestAudioViewNavigation:
    """Test AudioView navigation actions."""

    def test_next_file_empty(self):
        view = AudioView()
        view._files = []
        # Should not crash
        view.action_next_file()
        assert view._current_index == 0

    def test_prev_file_empty(self):
        view = AudioView()
        view._files = []
        view.action_prev_file()
        assert view._current_index == 0

    def test_next_file_advances(self):
        view = AudioView()
        view._files = [("a", None, None), ("b", None, None), ("c", None, None)]
        view._current_index = 0
        view._show_file_details = MagicMock()
        view.action_next_file()
        assert view._current_index == 1

    def test_next_file_clamps(self):
        view = AudioView()
        view._files = [("a", None, None), ("b", None, None)]
        view._current_index = 1
        view._show_file_details = MagicMock()
        view.action_next_file()
        assert view._current_index == 1

    def test_prev_file_decrements(self):
        view = AudioView()
        view._files = [("a", None, None), ("b", None, None)]
        view._current_index = 1
        view._show_file_details = MagicMock()
        view.action_prev_file()
        assert view._current_index == 0

    def test_prev_file_clamps_at_zero(self):
        view = AudioView()
        view._files = [("a", None, None)]
        view._current_index = 0
        view._show_file_details = MagicMock()
        view.action_prev_file()
        assert view._current_index == 0


@pytest.mark.unit
class TestAudioViewShowFileDetails:
    """Test _show_file_details bounds checking."""

    def test_negative_index(self):
        view = AudioView()
        view._files = [("a", "meta", "cls")]
        # Should not crash for out-of-bounds
        view.query_one = MagicMock()
        view._show_file_details(-1)
        view.query_one.assert_not_called()

    def test_index_too_large(self):
        view = AudioView()
        view._files = [("a", "meta", "cls")]
        view.query_one = MagicMock()
        view._show_file_details(5)
        view.query_one.assert_not_called()

    def test_valid_index(self):
        view = AudioView()
        meta_mock = MagicMock()
        cls_mock = MagicMock()
        view._files = [(Path("a.mp3"), meta_mock, cls_mock)]
        mock_meta_panel = MagicMock()
        mock_cls_panel = MagicMock()

        def query_side_effect(panel_cls):
            if panel_cls is AudioMetadataPanel:
                return mock_meta_panel
            return mock_cls_panel

        view.query_one = query_side_effect
        view._show_file_details(0)
        mock_meta_panel.set_metadata.assert_called_once_with(meta_mock)
        mock_cls_panel.set_classification.assert_called_once_with(cls_mock)


@pytest.mark.unit
class TestAudioViewSetStatus:
    """Test _set_status helper."""

    def test_set_status_no_app(self):
        view = AudioView()
        # Should not crash when app is not available
        view._set_status("test")

    def test_set_status_with_app(self):
        view = AudioView()
        mock_status = MagicMock()
        mock_app = MagicMock()
        mock_app.query_one.return_value = mock_status
        view._app = mock_app
        # _set_status catches exceptions
        view._set_status("loaded")


@pytest.mark.unit
class TestAudioViewRefresh:
    """Test action_refresh_audio method (lines 217-224)."""

    def test_refresh_resets_state(self):
        view = AudioView()
        view._files = [("a", "meta", "cls"), ("b", "meta2", "cls2")]
        view._current_index = 1

        mock_file_panel = MagicMock()
        mock_meta_panel = MagicMock()
        mock_cls_panel = MagicMock()

        def query_side(panel_cls):
            if panel_cls is AudioFileListPanel:
                return mock_file_panel
            if panel_cls is AudioMetadataPanel:
                return mock_meta_panel
            return mock_cls_panel

        view.query_one = query_side
        view._scan_audio_files = MagicMock()

        view.action_refresh_audio()

        assert view._files == []
        assert view._current_index == 0
        mock_file_panel.update.assert_called_once()
        mock_meta_panel.update.assert_called_once()
        mock_cls_panel.update.assert_called_once()
        view._scan_audio_files.assert_called_once()


# ---------------------------------------------------------------------------
# _scan_audio_files worker (lines 240-325)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestScanAudioFiles:
    """Test _scan_audio_files worker method."""

    # Store reference to the unwrapped function before any patching.
    # Use staticmethod so Python doesn't bind 'self' when accessed via instance.
    _scan_unwrapped = staticmethod(AudioView._scan_audio_files.__wrapped__)

    def test_scan_no_audio_files(self, tmp_path):
        """When dir has no audio files, panels are cleared."""
        view = AudioView(scan_dir=tmp_path)

        mock_file_panel = MagicMock()
        mock_meta_panel = MagicMock()
        mock_cls_panel = MagicMock()

        def query_side(panel_cls):
            if panel_cls is AudioFileListPanel:
                return mock_file_panel
            if panel_cls is AudioMetadataPanel:
                return mock_meta_panel
            return mock_cls_panel

        view.query_one = query_side
        view.call_from_thread = lambda fn, *a, **kw: fn(*a, **kw)
        view._set_status = MagicMock()

        mock_extractor_cls = MagicMock()
        mock_classifier_cls = MagicMock()

        with (
            patch(
                "file_organizer.services.audio.metadata_extractor.AudioMetadataExtractor",
                mock_extractor_cls,
            ),
            patch(
                "file_organizer.services.audio.classifier.AudioClassifier",
                mock_classifier_cls,
            ),
        ):
            self._scan_unwrapped(view)

        mock_file_panel.set_files.assert_called_once_with([])
        mock_meta_panel.set_metadata.assert_called_once_with(None)

    def test_scan_with_audio_files(self, tmp_path):
        """When dir has audio files, panels are populated."""
        # Create a fake mp3 file
        mp3_file = tmp_path / "song.mp3"
        mp3_file.write_bytes(b"fake_mp3")

        view = AudioView(scan_dir=tmp_path)
        mock_file_panel = MagicMock()
        mock_meta_panel = MagicMock()
        mock_cls_panel = MagicMock()

        def query_side(panel_cls):
            if panel_cls is AudioFileListPanel:
                return mock_file_panel
            if panel_cls is AudioMetadataPanel:
                return mock_meta_panel
            return mock_cls_panel

        view.query_one = query_side
        view.call_from_thread = lambda fn, *a, **kw: fn(*a, **kw)
        view._set_status = MagicMock()

        mock_metadata = FakeMetadata()
        mock_classification = FakeClassification()

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
            self._scan_unwrapped(view)

        assert len(view._files) == 1
        mock_file_panel.set_files.assert_called_once()
        mock_meta_panel.set_metadata.assert_called_once_with(mock_metadata)
        mock_cls_panel.set_classification.assert_called_once_with(mock_classification)

    def test_scan_import_error(self, tmp_path):
        """When audio imports fail, error message shown on panels."""
        mp3_file = tmp_path / "song.mp3"
        mp3_file.write_bytes(b"fake")

        view = AudioView(scan_dir=tmp_path)
        mock_panel = MagicMock()
        view.query_one = MagicMock(return_value=mock_panel)
        view.call_from_thread = lambda fn, *a, **kw: fn(*a, **kw)

        with patch.dict(
            "sys.modules",
            {
                "file_organizer.services.audio.classifier": None,
                "file_organizer.services.audio.metadata_extractor": None,
            },
        ):
            self._scan_unwrapped(view)

        # All three panels updated with error message
        assert mock_panel.update.call_count >= 1

    def test_scan_extraction_exception(self, tmp_path):
        """When extraction fails for a file, it still appears with fallback data."""
        mp3_file = tmp_path / "bad.mp3"
        mp3_file.write_bytes(b"corrupted")

        view = AudioView(scan_dir=tmp_path)
        mock_file_panel = MagicMock()
        mock_meta_panel = MagicMock()
        mock_cls_panel = MagicMock()

        def query_side(panel_cls):
            if panel_cls is AudioFileListPanel:
                return mock_file_panel
            if panel_cls is AudioMetadataPanel:
                return mock_meta_panel
            return mock_cls_panel

        view.query_one = query_side
        view.call_from_thread = lambda fn, *a, **kw: fn(*a, **kw)
        view._set_status = MagicMock()

        mock_extractor = MagicMock()
        mock_extractor.extract.side_effect = Exception("corrupt file")

        with (
            patch(
                "file_organizer.services.audio.metadata_extractor.AudioMetadataExtractor",
                return_value=mock_extractor,
            ),
            patch(
                "file_organizer.services.audio.classifier.AudioClassifier",
                return_value=MagicMock(),
            ),
        ):
            self._scan_unwrapped(view)

        assert len(view._files) == 1
        # First file has None metadata due to extraction error
        assert view._files[0][1] is None
        assert view._files[0][2] is None

    def test_scan_general_exception(self, tmp_path):
        """When scan encounters unexpected exception, error shown on panels."""
        mp3_file = tmp_path / "song.mp3"
        mp3_file.write_bytes(b"fake")

        view = AudioView(scan_dir=tmp_path)
        mock_panel = MagicMock()
        view.query_one = MagicMock(return_value=mock_panel)
        view.call_from_thread = lambda fn, *a, **kw: fn(*a, **kw)
        view._set_status = MagicMock()

        mock_extractor_cls = MagicMock(side_effect=RuntimeError("kaboom"))

        with (
            patch(
                "file_organizer.services.audio.metadata_extractor.AudioMetadataExtractor",
                mock_extractor_cls,
            ),
            patch(
                "file_organizer.services.audio.classifier.AudioClassifier",
                MagicMock(),
            ),
        ):
            self._scan_unwrapped(view)

        assert mock_panel.update.call_count >= 1


@pytest.mark.unit
class TestAudioViewBindings:
    """Test that AudioView has correct bindings."""

    def test_bindings_defined(self):
        assert len(AudioView.BINDINGS) == 3
        keys = [b.key for b in AudioView.BINDINGS]
        assert "r" in keys
        assert "j" in keys
        assert "k" in keys
