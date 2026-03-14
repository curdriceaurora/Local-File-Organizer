"""Integration tests for audio and video metadata pipelines in FileOrganizer."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.core.organizer import FileOrganizer
from file_organizer.services import ProcessedFile

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_audio_file(tmp_path: Path, name: str = "song.mp3") -> Path:
    p = tmp_path / name
    p.write_bytes(b"\x00" * 512)
    return p


def _make_video_file(tmp_path: Path, name: str = "clip.mp4") -> Path:
    p = tmp_path / name
    p.write_bytes(b"\x00" * 1024)
    return p


# ---------------------------------------------------------------------------
# _process_audio_files tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestProcessAudioFiles:
    def test_returns_processed_file_list(self, tmp_path: Path) -> None:
        """Audio pipeline returns ProcessedFile instances."""
        audio = _make_audio_file(tmp_path)
        organizer = FileOrganizer()
        results = organizer._process_audio_files([audio])

        assert len(results) == 1
        assert isinstance(results[0], ProcessedFile)
        assert results[0].file_path == audio

    def test_multiple_files_returned(self, tmp_path: Path) -> None:
        files = [_make_audio_file(tmp_path, f"track_{i}.mp3") for i in range(3)]
        organizer = FileOrganizer()
        results = organizer._process_audio_files(files)
        assert len(results) == 3

    def test_folder_name_is_set(self, tmp_path: Path) -> None:
        """folder_name must not be empty."""
        audio = _make_audio_file(tmp_path)
        organizer = FileOrganizer()
        results = organizer._process_audio_files([audio])
        assert results[0].folder_name  # non-empty

    def test_filename_stem_no_extension(self, tmp_path: Path) -> None:
        """filename must not contain the extension."""
        audio = _make_audio_file(tmp_path, "mysong.mp3")
        organizer = FileOrganizer()
        results = organizer._process_audio_files([audio])
        assert not results[0].filename.endswith(".mp3")

    def test_description_is_set(self, tmp_path: Path) -> None:
        """Description is non-empty when extraction succeeds (needs audio deps),
        or error is set when deps are missing — either is a valid outcome."""
        audio = _make_audio_file(tmp_path)
        organizer = FileOrganizer()
        results = organizer._process_audio_files([audio])
        # Either we got a description (deps present) or we got an error (deps absent)
        assert results[0].description or results[0].error is not None

    def test_error_on_extraction_failure(self, tmp_path: Path) -> None:
        """When extraction raises, result should have error set rather than crashing."""
        audio = _make_audio_file(tmp_path)
        organizer = FileOrganizer()

        with patch(
            "file_organizer.core.organizer.AudioMetadataExtractor.extract",
            side_effect=RuntimeError("bad file"),
        ):
            results = organizer._process_audio_files([audio])

        assert len(results) == 1
        assert results[0].error is not None
        assert results[0].folder_name == "Audio/Unsorted"

    def test_error_result_filename_is_original_stem(self, tmp_path: Path) -> None:
        audio = _make_audio_file(tmp_path, "mysong.mp3")
        organizer = FileOrganizer()

        with patch(
            "file_organizer.core.organizer.AudioMetadataExtractor.extract",
            side_effect=RuntimeError("bad"),
        ):
            results = organizer._process_audio_files([audio])

        assert results[0].filename == "mysong"


# ---------------------------------------------------------------------------
# _process_video_files tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestProcessVideoFiles:
    def test_returns_processed_file_list(self, tmp_path: Path) -> None:
        """Video pipeline returns ProcessedFile instances."""
        video = _make_video_file(tmp_path)
        organizer = FileOrganizer()
        results = organizer._process_video_files([video])

        assert len(results) == 1
        assert isinstance(results[0], ProcessedFile)
        assert results[0].file_path == video

    def test_multiple_files_returned(self, tmp_path: Path) -> None:
        files = [_make_video_file(tmp_path, f"video_{i}.mp4") for i in range(3)]
        organizer = FileOrganizer()
        results = organizer._process_video_files(files)
        assert len(results) == 3

    def test_folder_name_is_set(self, tmp_path: Path) -> None:
        video = _make_video_file(tmp_path)
        organizer = FileOrganizer()
        results = organizer._process_video_files([video])
        assert results[0].folder_name  # non-empty

    def test_filename_stem_no_extension(self, tmp_path: Path) -> None:
        video = _make_video_file(tmp_path, "myvideo.mp4")
        organizer = FileOrganizer()
        results = organizer._process_video_files([video])
        assert not results[0].filename.endswith(".mp4")

    def test_description_contains_video(self, tmp_path: Path) -> None:
        video = _make_video_file(tmp_path)
        organizer = FileOrganizer()
        results = organizer._process_video_files([video])
        assert "Video" in results[0].description

    def test_screen_recording_goes_to_correct_folder(self, tmp_path: Path) -> None:
        video = _make_video_file(tmp_path, "Screen Recording 2025-01-15 at 3.45.22 PM.mov")
        organizer = FileOrganizer()
        results = organizer._process_video_files([video])
        assert results[0].folder_name.startswith("Screen_Recordings")

    def test_error_on_extraction_failure(self, tmp_path: Path) -> None:
        video = _make_video_file(tmp_path)
        organizer = FileOrganizer()

        with patch(
            "file_organizer.core.organizer.VideoMetadataExtractor.extract",
            side_effect=RuntimeError("corrupt"),
        ):
            results = organizer._process_video_files([video])

        assert results[0].error is not None
        assert results[0].folder_name == "Videos/Unsorted"

    def test_missing_video_file_returns_fallback_result(self, tmp_path: Path) -> None:
        """Missing files should produce an error result, not raise."""
        organizer = FileOrganizer()
        missing = tmp_path / "nonexistent.mp4"

        results = organizer._process_video_files([missing])

        assert len(results) == 1
        assert results[0].file_path == missing
        assert results[0].error is not None
        assert "not found" in results[0].error.lower()
        assert results[0].folder_name == "Videos/Unsorted"
        assert results[0].filename == "nonexistent"


# ---------------------------------------------------------------------------
# organize() integration: audio + video routing
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestOrganizeRouting:
    """Verify audio and video files are routed through metadata pipelines, not skipped."""

    def _mock_models(self) -> tuple[MagicMock, MagicMock]:
        """Return (text_processor_mock, vision_processor_mock)."""
        tp = MagicMock()
        tp.process_file.return_value = MagicMock(error=None, folder_name="Docs", filename="doc")
        vp = MagicMock()
        vp.process_file.return_value = MagicMock(error=None, folder_name="Images", filename="img")
        return tp, vp

    def test_audio_not_skipped(self, tmp_path: Path) -> None:
        """Audio files reach _process_audio_files, not the skipped list."""
        src = tmp_path / "input"
        src.mkdir()
        audio = src / "song.mp3"
        audio.write_bytes(b"\x00" * 512)

        out = tmp_path / "output"
        organizer = FileOrganizer(dry_run=True)

        with patch.object(
            organizer, "_process_audio_files", wraps=organizer._process_audio_files
        ) as mock_audio:
            result = organizer.organize(str(src), str(out))

        mock_audio.assert_called_once()
        # skipped_files should be 0 (audio is no longer skipped)
        assert result.skipped_files == 0

    def test_video_uses_metadata_pipeline(self, tmp_path: Path) -> None:
        """Video files reach _process_video_files, not _process_image_files."""
        src = tmp_path / "input"
        src.mkdir()
        video = src / "clip.mp4"
        video.write_bytes(b"\x00" * 1024)

        out = tmp_path / "output"
        organizer = FileOrganizer(dry_run=True)

        with (
            patch.object(
                organizer, "_process_video_files", wraps=organizer._process_video_files
            ) as mock_video,
            patch.object(organizer, "_process_image_files") as mock_image,
        ):
            organizer.organize(str(src), str(out))

        mock_video.assert_called_once()
        # _process_image_files should NOT be called for video files
        mock_image.assert_not_called()

    def test_vision_model_not_initialized_for_video_only(self, tmp_path: Path) -> None:
        """VisionProcessor is NOT loaded when there are only video files (no images)."""
        src = tmp_path / "input"
        src.mkdir()
        (src / "clip.mp4").write_bytes(b"\x00" * 1024)

        out = tmp_path / "output"
        organizer = FileOrganizer(dry_run=True)
        organizer.organize(str(src), str(out))

        # vision_processor should never have been initialized
        assert organizer.vision_processor is None

    def test_mixed_directory_all_types_processed(self, tmp_path: Path) -> None:
        """Mixed directory: text, image, audio, video all handled correctly."""
        src = tmp_path / "input"
        src.mkdir()
        (src / "doc.txt").write_text("hello world")
        (src / "photo.jpg").write_bytes(b"\xff\xd8\xff" + b"\x00" * 100)
        (src / "song.mp3").write_bytes(b"\x00" * 512)
        (src / "clip.mp4").write_bytes(b"\x00" * 1024)

        out = tmp_path / "output"
        organizer = FileOrganizer(dry_run=True)

        with (
            patch.object(organizer, "_process_text_files") as mock_text,
            patch.object(organizer, "_process_image_files") as mock_img,
            patch.object(
                organizer, "_process_audio_files", wraps=organizer._process_audio_files
            ) as mock_audio,
            patch.object(
                organizer, "_process_video_files", wraps=organizer._process_video_files
            ) as mock_video,
            # Prevent real Ollama/model connections during test
            patch("file_organizer.core.organizer.TextProcessor") as mock_tp_cls,
            patch("file_organizer.core.organizer.VisionProcessor") as mock_vp_cls,
        ):
            mock_text.return_value = []
            mock_img.return_value = []
            mock_tp_cls.return_value = MagicMock()
            mock_vp_cls.return_value = MagicMock()
            organizer.organize(str(src), str(out))

        mock_text.assert_called_once()
        mock_img.assert_called_once()
        mock_audio.assert_called_once()
        mock_video.assert_called_once()

    def test_audio_in_dry_run_counted(self, tmp_path: Path) -> None:
        """In dry_run mode, audio files appear in organized_structure."""
        src = tmp_path / "input"
        src.mkdir()
        (src / "song.mp3").write_bytes(b"\x00" * 512)

        out = tmp_path / "output"
        organizer = FileOrganizer(dry_run=True)
        result = organizer.organize(str(src), str(out))

        assert result.processed_files > 0 or result.failed_files > 0
        assert result.skipped_files == 0
