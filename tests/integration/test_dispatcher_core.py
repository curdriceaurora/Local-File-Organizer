"""Integration tests for the dispatcher module.

Covers: process_text_files(), process_image_files(), process_audio_files(),
process_video_files() — success path, result-with-error path, failure path,
and fallback folder assignments.

All external processor calls are mocked — no AI models or real files needed.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.ci]

# ---------------------------------------------------------------------------
# Patch targets
# ---------------------------------------------------------------------------

_PROGRESS_TARGET = "file_organizer.core.dispatcher.create_progress"

# Audio/video: the functions use local imports, so patch in the source modules.
_AUDIO_CLASSIFIER_TARGET = "file_organizer.services.audio.classifier.AudioClassifier"
_AUDIO_ORGANIZER_TARGET = "file_organizer.services.audio.organizer.AudioOrganizer"
_VIDEO_ORGANIZER_TARGET = "file_organizer.services.video.organizer.VideoOrganizer"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_progress_ctx() -> MagicMock:
    """Return a MagicMock that acts as a context-manager progress bar."""
    progress = MagicMock()
    progress.add_task.return_value = "task-1"

    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=progress)
    ctx.__exit__ = MagicMock(return_value=False)
    return ctx


def _make_file_result(
    *,
    success: bool,
    path: Path,
    result: object | None = None,
    error: str | None = None,
) -> MagicMock:
    """Return a MagicMock parallel processor file result."""
    fr = MagicMock()
    fr.success = success
    fr.path = path
    fr.result = result
    fr.error = error
    return fr


# ---------------------------------------------------------------------------
# process_text_files()
# ---------------------------------------------------------------------------


class TestProcessTextFiles:
    """Tests for process_text_files()."""

    def test_success_result_appended(self) -> None:
        from file_organizer.core.dispatcher import process_text_files
        from file_organizer.services import ProcessedFile

        file_path = Path("/mock/docs/report.txt")
        processed = ProcessedFile(
            file_path=file_path,
            description="A quarterly report",
            folder_name="Reports",
            filename="report",
            error=None,
        )
        file_result = _make_file_result(success=True, path=file_path, result=processed)

        mock_pp = MagicMock()
        mock_pp.process_batch_iter.return_value = iter([file_result])
        progress_ctx = _make_progress_ctx()

        with patch(_PROGRESS_TARGET, return_value=progress_ctx):
            results = process_text_files(
                [file_path],
                text_processor=MagicMock(),
                parallel_processor=mock_pp,
                console=MagicMock(),
            )

        assert len(results) == 1
        assert results[0].folder_name == "Reports"
        assert results[0].filename == "report"
        assert results[0].description == "A quarterly report"

    def test_success_result_with_error_field_appended(self) -> None:
        """A 'success' batch result whose ProcessedFile has a non-None error is still appended."""
        from file_organizer.core.dispatcher import process_text_files
        from file_organizer.services import ProcessedFile

        file_path = Path("/mock/docs/broken.txt")
        processed = ProcessedFile(
            file_path=file_path,
            description="",
            folder_name="errors",
            filename="broken",
            error="Could not parse file",
        )
        file_result = _make_file_result(success=True, path=file_path, result=processed)

        mock_pp = MagicMock()
        mock_pp.process_batch_iter.return_value = iter([file_result])
        progress_ctx = _make_progress_ctx()

        with patch(_PROGRESS_TARGET, return_value=progress_ctx):
            results = process_text_files(
                [file_path],
                text_processor=MagicMock(),
                parallel_processor=mock_pp,
                console=MagicMock(),
            )

        assert len(results) == 1
        assert results[0].error == "Could not parse file"

    def test_failure_result_creates_error_fallback(self) -> None:
        from file_organizer.core.dispatcher import process_text_files
        from file_organizer.core.types import ERROR_FALLBACK_FOLDER

        file_path = Path("/mock/docs/missing.txt")
        file_result = _make_file_result(success=False, path=file_path, error="process failed")

        mock_pp = MagicMock()
        mock_pp.process_batch_iter.return_value = iter([file_result])
        progress_ctx = _make_progress_ctx()

        with patch(_PROGRESS_TARGET, return_value=progress_ctx):
            results = process_text_files(
                [file_path],
                text_processor=MagicMock(),
                parallel_processor=mock_pp,
                console=MagicMock(),
            )

        assert len(results) == 1
        assert results[0].folder_name == ERROR_FALLBACK_FOLDER
        assert results[0].error == "process failed"
        assert results[0].file_path == file_path

    def test_failure_result_unknown_error_message(self) -> None:
        """When error is None on a failed result, fallback should use 'Unknown error'."""
        from file_organizer.core.dispatcher import process_text_files

        file_path = Path("/mock/docs/mystery.txt")
        file_result = _make_file_result(success=False, path=file_path, error=None)

        mock_pp = MagicMock()
        mock_pp.process_batch_iter.return_value = iter([file_result])
        progress_ctx = _make_progress_ctx()

        with patch(_PROGRESS_TARGET, return_value=progress_ctx):
            results = process_text_files(
                [file_path],
                text_processor=MagicMock(),
                parallel_processor=mock_pp,
                console=MagicMock(),
            )

        assert len(results) == 1
        assert results[0].error == "Unknown error"

    def test_empty_files_returns_empty_list(self) -> None:
        from file_organizer.core.dispatcher import process_text_files

        mock_pp = MagicMock()
        mock_pp.process_batch_iter.return_value = iter([])
        progress_ctx = _make_progress_ctx()

        with patch(_PROGRESS_TARGET, return_value=progress_ctx):
            results = process_text_files(
                [],
                text_processor=MagicMock(),
                parallel_processor=mock_pp,
                console=MagicMock(),
            )

        assert results == []

    def test_mixed_results_all_appended(self) -> None:
        from file_organizer.core.dispatcher import process_text_files
        from file_organizer.core.types import ERROR_FALLBACK_FOLDER
        from file_organizer.services import ProcessedFile

        path_ok = Path("/mock/docs/good.txt")
        path_fail = Path("/mock/docs/bad.txt")

        processed_ok = ProcessedFile(
            file_path=path_ok,
            description="Good file",
            folder_name="Docs",
            filename="good",
            error=None,
        )
        fr_ok = _make_file_result(success=True, path=path_ok, result=processed_ok)
        fr_fail = _make_file_result(success=False, path=path_fail, error="disk error")

        mock_pp = MagicMock()
        mock_pp.process_batch_iter.return_value = iter([fr_ok, fr_fail])
        progress_ctx = _make_progress_ctx()

        with patch(_PROGRESS_TARGET, return_value=progress_ctx):
            results = process_text_files(
                [path_ok, path_fail],
                text_processor=MagicMock(),
                parallel_processor=mock_pp,
                console=MagicMock(),
            )

        assert len(results) == 2
        assert results[0].folder_name == "Docs"
        assert results[1].folder_name == ERROR_FALLBACK_FOLDER


# ---------------------------------------------------------------------------
# process_image_files()
# ---------------------------------------------------------------------------


class TestProcessImageFiles:
    """Tests for process_image_files()."""

    def test_success_result_appended(self) -> None:
        from file_organizer.core.dispatcher import process_image_files
        from file_organizer.services import ProcessedImage

        file_path = Path("/mock/photos/sunset.jpg")
        processed = ProcessedImage(
            file_path=file_path,
            description="A sunset over the ocean",
            folder_name="Nature",
            filename="sunset",
            error=None,
        )
        file_result = _make_file_result(success=True, path=file_path, result=processed)

        mock_pp = MagicMock()
        mock_pp.process_batch_iter.return_value = iter([file_result])
        progress_ctx = _make_progress_ctx()

        with patch(_PROGRESS_TARGET, return_value=progress_ctx):
            results = process_image_files(
                [file_path],
                vision_processor=MagicMock(),
                parallel_processor=mock_pp,
                console=MagicMock(),
            )

        assert len(results) == 1
        assert results[0].folder_name == "Nature"
        assert results[0].filename == "sunset"
        assert results[0].description == "A sunset over the ocean"

    def test_success_result_with_error_field(self) -> None:
        from file_organizer.core.dispatcher import process_image_files
        from file_organizer.services import ProcessedImage

        file_path = Path("/mock/photos/corrupt.jpg")
        processed = ProcessedImage(
            file_path=file_path,
            description="",
            folder_name="errors",
            filename="corrupt",
            error="EXIF parse failed",
        )
        file_result = _make_file_result(success=True, path=file_path, result=processed)

        mock_pp = MagicMock()
        mock_pp.process_batch_iter.return_value = iter([file_result])
        progress_ctx = _make_progress_ctx()

        with patch(_PROGRESS_TARGET, return_value=progress_ctx):
            results = process_image_files(
                [file_path],
                vision_processor=MagicMock(),
                parallel_processor=mock_pp,
                console=MagicMock(),
            )

        assert len(results) == 1
        assert results[0].error == "EXIF parse failed"

    def test_failure_result_creates_error_fallback(self) -> None:
        from file_organizer.core.dispatcher import process_image_files
        from file_organizer.core.types import ERROR_FALLBACK_FOLDER

        file_path = Path("/mock/photos/missing.png")
        file_result = _make_file_result(success=False, path=file_path, error="vision timeout")

        mock_pp = MagicMock()
        mock_pp.process_batch_iter.return_value = iter([file_result])
        progress_ctx = _make_progress_ctx()

        with patch(_PROGRESS_TARGET, return_value=progress_ctx):
            results = process_image_files(
                [file_path],
                vision_processor=MagicMock(),
                parallel_processor=mock_pp,
                console=MagicMock(),
            )

        assert len(results) == 1
        assert results[0].folder_name == ERROR_FALLBACK_FOLDER
        assert results[0].error == "vision timeout"
        assert results[0].file_path == file_path
        assert results[0].filename == "missing"

    def test_failure_result_unknown_error(self) -> None:
        from file_organizer.core.dispatcher import process_image_files

        file_path = Path("/mock/photos/unknown.jpg")
        file_result = _make_file_result(success=False, path=file_path, error=None)

        mock_pp = MagicMock()
        mock_pp.process_batch_iter.return_value = iter([file_result])
        progress_ctx = _make_progress_ctx()

        with patch(_PROGRESS_TARGET, return_value=progress_ctx):
            results = process_image_files(
                [file_path],
                vision_processor=MagicMock(),
                parallel_processor=mock_pp,
                console=MagicMock(),
            )

        assert len(results) == 1
        assert results[0].error == "Unknown error"

    def test_empty_input_returns_empty_list(self) -> None:
        from file_organizer.core.dispatcher import process_image_files

        mock_pp = MagicMock()
        mock_pp.process_batch_iter.return_value = iter([])
        progress_ctx = _make_progress_ctx()

        with patch(_PROGRESS_TARGET, return_value=progress_ctx):
            results = process_image_files(
                [],
                vision_processor=MagicMock(),
                parallel_processor=mock_pp,
                console=MagicMock(),
            )

        assert results == []


# ---------------------------------------------------------------------------
# process_audio_files()
# ---------------------------------------------------------------------------


class TestProcessAudioFiles:
    """Tests for process_audio_files().

    Note: AudioClassifier and AudioOrganizer are imported locally inside the
    function body, so they must be patched at their source module locations.
    """

    def _make_audio_metadata(
        self,
        *,
        artist: str | None = None,
        title: str | None = None,
    ) -> MagicMock:
        meta = MagicMock()
        meta.artist = artist
        meta.title = title
        return meta

    def _make_audio_classification(self, audio_type_value: str = "music") -> MagicMock:
        audio_type = MagicMock()
        audio_type.value = audio_type_value

        classification = MagicMock()
        classification.audio_type = audio_type
        return classification

    def _make_dest_path(self, folder: str, stem: str) -> MagicMock:
        dest = MagicMock(spec=Path)
        dest.parent = MagicMock()
        dest.parent.as_posix.return_value = folder
        dest.stem = stem
        return dest

    def test_success_path_appended(self) -> None:
        from file_organizer.core.dispatcher import process_audio_files

        audio_path = Path("/mock/music/song.mp3")
        meta = self._make_audio_metadata(artist="The Band", title="My Song")
        classification = self._make_audio_classification()
        dest = self._make_dest_path("Music/The Band", "My_Song")

        mock_extractor_instance = MagicMock()
        mock_extractor_instance.extract.return_value = meta
        mock_extractor_cls = MagicMock(return_value=mock_extractor_instance)

        mock_classifier_instance = MagicMock()
        mock_classifier_instance.classify.return_value = classification
        mock_organizer_instance = MagicMock()
        mock_organizer_instance.generate_path.return_value = dest

        with (
            patch(_AUDIO_CLASSIFIER_TARGET, return_value=mock_classifier_instance),
            patch(_AUDIO_ORGANIZER_TARGET, return_value=mock_organizer_instance),
        ):
            results = process_audio_files([audio_path], extractor_cls=mock_extractor_cls)

        assert len(results) == 1
        assert results[0].folder_name == "Music/The Band"
        assert results[0].filename == "My_Song"
        assert results[0].error is None
        assert results[0].file_path == audio_path

    def test_success_description_contains_type_and_artist(self) -> None:
        from file_organizer.core.dispatcher import process_audio_files

        audio_path = Path("/mock/music/track.mp3")
        meta = self._make_audio_metadata(artist="DJ Echo", title="Night Drive")
        classification = self._make_audio_classification("music")
        dest = self._make_dest_path("Music/DJ Echo", "Night_Drive")

        mock_extractor_instance = MagicMock()
        mock_extractor_instance.extract.return_value = meta
        mock_extractor_cls = MagicMock(return_value=mock_extractor_instance)
        mock_classifier_instance = MagicMock()
        mock_classifier_instance.classify.return_value = classification
        mock_organizer_instance = MagicMock()
        mock_organizer_instance.generate_path.return_value = dest

        with (
            patch(_AUDIO_CLASSIFIER_TARGET, return_value=mock_classifier_instance),
            patch(_AUDIO_ORGANIZER_TARGET, return_value=mock_organizer_instance),
        ):
            results = process_audio_files([audio_path], extractor_cls=mock_extractor_cls)

        # Description should contain audio type, artist, and title — all three
        desc = results[0].description
        assert "Music" in desc and "DJ Echo" in desc and "Night Drive" in desc

    def test_extraction_os_error_uses_audio_fallback_folder(self) -> None:
        """OSError during extract() → fallback folder, error message preserved."""
        from file_organizer.core.dispatcher import process_audio_files
        from file_organizer.core.types import AUDIO_FALLBACK_FOLDER

        audio_path = Path("/mock/music/corrupt.mp3")

        mock_extractor_instance = MagicMock()
        mock_extractor_instance.extract.side_effect = OSError("cannot read file")
        mock_extractor_cls = MagicMock(return_value=mock_extractor_instance)

        # No need to patch classifier/organizer — exception fires before they're called.
        with (
            patch(_AUDIO_CLASSIFIER_TARGET),
            patch(_AUDIO_ORGANIZER_TARGET),
        ):
            results = process_audio_files([audio_path], extractor_cls=mock_extractor_cls)

        assert len(results) == 1
        assert results[0].folder_name == AUDIO_FALLBACK_FOLDER
        assert results[0].error == "cannot read file"
        assert results[0].file_path == audio_path
        assert results[0].filename == "corrupt"

    def test_extraction_value_error_uses_audio_fallback_folder(self) -> None:
        from file_organizer.core.dispatcher import process_audio_files
        from file_organizer.core.types import AUDIO_FALLBACK_FOLDER

        audio_path = Path("/mock/music/bad.flac")
        mock_extractor_instance = MagicMock()
        mock_extractor_instance.extract.side_effect = ValueError("bad tag data")
        mock_extractor_cls = MagicMock(return_value=mock_extractor_instance)

        with (
            patch(_AUDIO_CLASSIFIER_TARGET),
            patch(_AUDIO_ORGANIZER_TARGET),
        ):
            results = process_audio_files([audio_path], extractor_cls=mock_extractor_cls)

        assert len(results) == 1
        assert results[0].folder_name == AUDIO_FALLBACK_FOLDER
        assert results[0].error == "bad tag data"

    def test_empty_input_returns_empty_list(self) -> None:
        from file_organizer.core.dispatcher import process_audio_files

        results = process_audio_files([])

        assert results == []

    def test_multiple_files_all_processed(self) -> None:
        from file_organizer.core.dispatcher import process_audio_files

        paths = [Path(f"/mock/music/track{i}.mp3") for i in range(3)]

        call_count = {"n": 0}

        def extract_side_effect(path: Path) -> MagicMock:
            meta = self._make_audio_metadata(
                artist=f"Artist{call_count['n']}",
                title=f"Title{call_count['n']}",
            )
            call_count["n"] += 1
            return meta

        mock_extractor_instance = MagicMock()
        mock_extractor_instance.extract.side_effect = extract_side_effect
        mock_extractor_cls = MagicMock(return_value=mock_extractor_instance)

        classification = self._make_audio_classification()
        dest = self._make_dest_path("Music/Various", "track")

        mock_classifier_instance = MagicMock()
        mock_classifier_instance.classify.return_value = classification
        mock_organizer_instance = MagicMock()
        mock_organizer_instance.generate_path.return_value = dest

        with (
            patch(_AUDIO_CLASSIFIER_TARGET, return_value=mock_classifier_instance),
            patch(_AUDIO_ORGANIZER_TARGET, return_value=mock_organizer_instance),
        ):
            results = process_audio_files(paths, extractor_cls=mock_extractor_cls)

        assert len(results) == 3


# ---------------------------------------------------------------------------
# process_video_files()
# ---------------------------------------------------------------------------


class TestProcessVideoFiles:
    """Tests for process_video_files().

    Note: VideoOrganizer is imported locally inside the function body, so it
    must be patched at its source module location.
    """

    def test_success_path_appended(self) -> None:
        from file_organizer.core.dispatcher import process_video_files

        video_path = Path("/mock/videos/movie.mp4")
        meta = MagicMock()

        mock_extractor_instance = MagicMock()
        mock_extractor_instance.extract.return_value = meta
        mock_extractor_cls = MagicMock(return_value=mock_extractor_instance)

        mock_organizer_instance = MagicMock()
        mock_organizer_instance.generate_path.return_value = ("Movies/Action", "movie_2025")
        mock_organizer_instance.generate_description.return_value = "An action movie"

        with patch(_VIDEO_ORGANIZER_TARGET, return_value=mock_organizer_instance):
            results = process_video_files([video_path], extractor_cls=mock_extractor_cls)

        assert len(results) == 1
        assert results[0].folder_name == "Movies/Action"
        assert results[0].filename == "movie_2025"
        assert results[0].description == "An action movie"
        assert results[0].error is None
        assert results[0].file_path == video_path

    def test_file_not_found_uses_video_fallback_folder(self) -> None:
        from file_organizer.core.dispatcher import process_video_files
        from file_organizer.core.types import VIDEO_FALLBACK_FOLDER

        video_path = Path("/mock/videos/missing.avi")

        mock_extractor_instance = MagicMock()
        mock_extractor_instance.extract.side_effect = FileNotFoundError("file gone")
        mock_extractor_cls = MagicMock(return_value=mock_extractor_instance)

        with patch(_VIDEO_ORGANIZER_TARGET):
            results = process_video_files([video_path], extractor_cls=mock_extractor_cls)

        assert len(results) == 1
        assert results[0].folder_name == VIDEO_FALLBACK_FOLDER
        assert results[0].error == "file gone"
        assert results[0].file_path == video_path
        assert results[0].filename == "missing"

    def test_os_error_uses_video_fallback_folder(self) -> None:
        from file_organizer.core.dispatcher import process_video_files
        from file_organizer.core.types import VIDEO_FALLBACK_FOLDER

        video_path = Path("/mock/videos/locked.mkv")
        mock_extractor_instance = MagicMock()
        mock_extractor_instance.extract.side_effect = OSError("permission denied")
        mock_extractor_cls = MagicMock(return_value=mock_extractor_instance)

        with patch(_VIDEO_ORGANIZER_TARGET):
            results = process_video_files([video_path], extractor_cls=mock_extractor_cls)

        assert len(results) == 1
        assert results[0].folder_name == VIDEO_FALLBACK_FOLDER
        assert results[0].error == "permission denied"

    def test_runtime_error_uses_video_fallback_folder(self) -> None:
        from file_organizer.core.dispatcher import process_video_files
        from file_organizer.core.types import VIDEO_FALLBACK_FOLDER

        video_path = Path("/mock/videos/crash.mp4")
        mock_extractor_instance = MagicMock()
        mock_extractor_instance.extract.side_effect = RuntimeError("ffprobe crashed")
        mock_extractor_cls = MagicMock(return_value=mock_extractor_instance)

        with patch(_VIDEO_ORGANIZER_TARGET):
            results = process_video_files([video_path], extractor_cls=mock_extractor_cls)

        assert len(results) == 1
        assert results[0].folder_name == VIDEO_FALLBACK_FOLDER
        assert results[0].error == "ffprobe crashed"

    def test_empty_input_returns_empty_list(self) -> None:
        from file_organizer.core.dispatcher import process_video_files

        results = process_video_files([])

        assert results == []

    def test_multiple_files_all_processed(self) -> None:
        from file_organizer.core.dispatcher import process_video_files

        paths = [Path(f"/mock/videos/clip{i}.mp4") for i in range(4)]

        mock_extractor_instance = MagicMock()
        mock_extractor_instance.extract.return_value = MagicMock()
        mock_extractor_cls = MagicMock(return_value=mock_extractor_instance)

        mock_organizer_instance = MagicMock()
        mock_organizer_instance.generate_path.return_value = ("Videos/Clips", "clip")
        mock_organizer_instance.generate_description.return_value = "A video clip"

        with patch(_VIDEO_ORGANIZER_TARGET, return_value=mock_organizer_instance):
            results = process_video_files(paths, extractor_cls=mock_extractor_cls)

        assert len(results) == 4

    def test_description_stored_from_organizer(self) -> None:
        from file_organizer.core.dispatcher import process_video_files

        video_path = Path("/mock/videos/documentary.mp4")
        meta = MagicMock()

        mock_extractor_instance = MagicMock()
        mock_extractor_instance.extract.return_value = meta
        mock_extractor_cls = MagicMock(return_value=mock_extractor_instance)

        mock_organizer_instance = MagicMock()
        mock_organizer_instance.generate_path.return_value = ("Documentaries", "documentary_title")
        mock_organizer_instance.generate_description.return_value = (
            "Nature documentary about whales"
        )

        with patch(_VIDEO_ORGANIZER_TARGET, return_value=mock_organizer_instance):
            results = process_video_files([video_path], extractor_cls=mock_extractor_cls)

        assert results[0].description == "Nature documentary about whales"
