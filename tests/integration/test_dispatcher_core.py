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
    non_retryable: bool = True,
    duration_ms: float = 0.0,
) -> MagicMock:
    """Return a MagicMock parallel processor file result.

    ``non_retryable=True`` is the historical default (existing tests assume
    aborted tasks aren't retried). The #432 retry path requires callers to pass
    ``non_retryable=False`` to opt into the dispatcher's sequential retry pass.
    """
    fr = MagicMock()
    fr.success = success
    fr.path = path
    fr.result = result
    fr.error = error
    fr.non_retryable = non_retryable
    fr.duration_ms = duration_ms
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

    def test_pool_saturation_retryable_aborts_run_sequentially(self) -> None:
        # #432: when the parallel processor returns saturation aborts
        # tagged ``non_retryable=False`` (never-started tasks), the
        # dispatcher reruns them sequentially via ``vision_processor``
        # rather than mass-failing them as collateral damage.
        from file_organizer.core.dispatcher import process_image_files
        from file_organizer.services import ProcessedImage

        hung_path = Path("/mock/photos/hung.jpg")
        retry1 = Path("/mock/photos/never_started_1.jpg")
        retry2 = Path("/mock/photos/never_started_2.jpg")

        # Parallel processor yields one truly-hung abort (non_retryable)
        # + two never-started aborts (retryable).
        hung_fr = _make_file_result(
            success=False,
            path=hung_path,
            error="Aborted: worker pool saturated by hung tasks",
            non_retryable=True,
        )
        retry1_fr = _make_file_result(
            success=False,
            path=retry1,
            error="Aborted: worker pool saturated by hung tasks",
            non_retryable=False,
        )
        retry2_fr = _make_file_result(
            success=False,
            path=retry2,
            error="Aborted: worker pool saturated by hung tasks",
            non_retryable=False,
        )
        # Retry pass also runs through the parallel processor (preserves
        # timeout / cancellation enforcement). Yield successful retries.
        retry1_success = _make_file_result(
            success=True,
            path=retry1,
            result=ProcessedImage(
                file_path=retry1,
                description="d1",
                folder_name="ok",
                filename="never_started_1",
            ),
        )
        retry2_success = _make_file_result(
            success=True,
            path=retry2,
            result=ProcessedImage(
                file_path=retry2,
                description="d2",
                folder_name="ok",
                filename="never_started_2",
            ),
        )
        # Initial processor (multi-worker) yields the saturation batch.
        mock_pp = MagicMock()
        mock_pp.config.timeout_per_file = 60.0  # real float for ParallelConfig() validation
        mock_pp.process_batch_iter.return_value = iter([hung_fr, retry1_fr, retry2_fr])

        # Retry processor is a fresh single-worker ParallelProcessor —
        # reusing the original multi-worker config can re-saturate. Patch
        # the class at the dispatcher's import site so we can assert it was
        # built with ``max_workers=1, prefetch_depth=0``.
        retry_pp = MagicMock()
        retry_pp.process_batch_iter.return_value = iter([retry1_success, retry2_success])

        vp = MagicMock()
        progress_ctx = _make_progress_ctx()
        with (
            patch(_PROGRESS_TARGET, return_value=progress_ctx),
            patch(
                "file_organizer.core.dispatcher.ParallelProcessor", return_value=retry_pp
            ) as mock_pp_cls,
        ):
            results = process_image_files(
                [hung_path, retry1, retry2],
                vision_processor=vp,
                parallel_processor=mock_pp,
                console=MagicMock(),
            )

        # 1 genuinely-hung failure + 2 sequential successes.
        by_path = {r.file_path: r for r in results}
        assert by_path[hung_path].error == "Aborted: worker pool saturated by hung tasks"
        assert by_path[retry1].error is None
        assert by_path[retry1].folder_name == "ok"
        assert by_path[retry2].error is None
        assert by_path[retry2].folder_name == "ok"
        # Initial multi-worker processor was used once; retry processor
        # was constructed with single-worker + no-prefetch.
        assert mock_pp.process_batch_iter.call_count == 1
        assert mock_pp_cls.call_count == 1
        retry_config = mock_pp_cls.call_args.kwargs["config"]
        assert retry_config.max_workers == 1
        assert retry_config.prefetch_depth == 0
        # Operator-tunable timeout is inherited from the caller's config.
        assert retry_config.timeout_per_file == 60.0
        # Retry processor.process_batch_iter was called with just the
        # never-started paths.
        assert retry_pp.process_batch_iter.call_count == 1
        retry_paths_arg = retry_pp.process_batch_iter.call_args.args[0]
        assert set(retry_paths_arg) == {retry1, retry2}

    def test_retry_timeout_routes_through_vision_fallback(self) -> None:
        # #432 follow-up: the sequential retry pass runs through
        # ``parallel_processor.process_batch_iter`` so the per-file timeout
        # is enforced. When a retry hits that timeout, the dispatcher must
        # route the file through the same #406 EXIF fallback path the initial
        # pass uses — preserving the operator-facing classification rather
        # than letting the timeout escape as a generic error.
        from file_organizer.core.dispatcher import process_image_files

        path = Path("/mock/photos/retry_timeout.jpg")
        initial_abort = _make_file_result(
            success=False,
            path=path,
            error="Aborted: worker pool saturated by hung tasks",
            non_retryable=False,
        )
        retry_timeout = _make_file_result(
            success=False,
            path=path,
            error="Timed out after 60s",
            duration_ms=60000.0,
        )
        mock_pp = MagicMock()
        mock_pp.config.timeout_per_file = 60.0
        mock_pp.process_batch_iter.return_value = iter([initial_abort])
        retry_pp = MagicMock()
        retry_pp.process_batch_iter.return_value = iter([retry_timeout])
        with patch("file_organizer.core.dispatcher.compute_fallback") as mock_fb:
            fb = MagicMock()
            fb.source = "fallback_exif"
            fb.folder = "Images/Photos/2024/01"
            fb.filename = "retry_timeout"
            mock_fb.return_value = fb
            progress_ctx = _make_progress_ctx()
            with (
                patch(_PROGRESS_TARGET, return_value=progress_ctx),
                patch("file_organizer.core.dispatcher.ParallelProcessor", return_value=retry_pp),
            ):
                results = process_image_files(
                    [path],
                    vision_processor=MagicMock(),
                    parallel_processor=mock_pp,
                    console=MagicMock(),
                )
        assert len(results) == 1
        assert results[0].source == "fallback_exif"
        assert results[0].folder_name == "Images/Photos/2024/01"
        # Carries timer duration through for #410 p95/p99 accounting.
        assert results[0].inference_ms == 60000.0

    def test_retry_generic_error_falls_to_error_folder(self) -> None:
        # #432 follow-up: non-timeout retry failures (e.g. corrupt image
        # data, vision-model error) record as genuine failures in the
        # ``errors`` folder — there's no second-level retry.
        from file_organizer.core.dispatcher import process_image_files
        from file_organizer.core.types import ERROR_FALLBACK_FOLDER

        path = Path("/mock/photos/retry_bad.jpg")
        initial_abort = _make_file_result(
            success=False,
            path=path,
            error="Aborted: worker pool saturated by hung tasks",
            non_retryable=False,
        )
        retry_err = _make_file_result(
            success=False,
            path=path,
            error="Corrupt JPEG data: 12 extraneous bytes",
        )
        mock_pp = MagicMock()
        mock_pp.config.timeout_per_file = 60.0
        mock_pp.process_batch_iter.return_value = iter([initial_abort])
        retry_pp = MagicMock()
        retry_pp.process_batch_iter.return_value = iter([retry_err])
        progress_ctx = _make_progress_ctx()
        with (
            patch(_PROGRESS_TARGET, return_value=progress_ctx),
            patch("file_organizer.core.dispatcher.ParallelProcessor", return_value=retry_pp),
        ):
            results = process_image_files(
                [path],
                vision_processor=MagicMock(),
                parallel_processor=mock_pp,
                console=MagicMock(),
            )
        assert len(results) == 1
        assert results[0].folder_name == ERROR_FALLBACK_FOLDER
        assert results[0].error == "Corrupt JPEG data: 12 extraneous bytes"
        assert results[0].confidence == 0.0

    def test_retry_saturation_abort_routes_through_vision_fallback(self) -> None:
        # #1287 review: the sequential retry reuses one single-worker
        # processor for all retry candidates. If an earlier retry hangs, its
        # thread occupies the lone worker and the remaining candidates get
        # never-started saturation aborts (``non_retryable=False``). Those must
        # degrade to the #406 metadata fallback rather than the error folder —
        # otherwise one hung retry cascades the untried candidates into
        # failures, reintroducing the cascade this path exists to prevent.
        from file_organizer.core.dispatcher import process_image_files

        path = Path("/mock/photos/retry_never_ran.jpg")
        initial_abort = _make_file_result(
            success=False,
            path=path,
            error="Aborted: worker pool saturated by hung tasks",
            non_retryable=False,
        )
        # Retry pass: this candidate never started (collateral of a hung peer).
        retry_saturated = _make_file_result(
            success=False,
            path=path,
            error="Aborted: worker pool saturated by hung tasks",
            non_retryable=False,
        )
        mock_pp = MagicMock()
        mock_pp.config.timeout_per_file = 60.0
        mock_pp.process_batch_iter.return_value = iter([initial_abort])
        retry_pp = MagicMock()
        retry_pp.process_batch_iter.return_value = iter([retry_saturated])
        with patch("file_organizer.core.dispatcher.compute_fallback") as mock_fb:
            fb = MagicMock()
            fb.source = "fallback_filename"
            fb.folder = "Images/Photos/untagged"
            fb.filename = "retry_never_ran"
            mock_fb.return_value = fb
            progress_ctx = _make_progress_ctx()
            with (
                patch(_PROGRESS_TARGET, return_value=progress_ctx),
                patch("file_organizer.core.dispatcher.ParallelProcessor", return_value=retry_pp),
            ):
                results = process_image_files(
                    [path],
                    vision_processor=MagicMock(),
                    parallel_processor=mock_pp,
                    console=MagicMock(),
                )
        # Degraded to metadata fallback, not the error folder — no cascade.
        assert len(results) == 1
        assert results[0].error is None
        assert results[0].source == "fallback_filename"
        assert results[0].folder_name == "Images/Photos/untagged"

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
# Audio best-effort transcription (WP-4.1 anti-cascade audio path)
# ---------------------------------------------------------------------------


class TestAudioTranscription:
    """Tests for _maybe_transcribe / _to_transcription_result + wiring."""

    def test_maybe_transcribe_none_transcriber_returns_none(self) -> None:
        from file_organizer.core.dispatcher import _maybe_transcribe

        result = _maybe_transcribe(
            Path("/mock/a.mp3"),
            metadata=MagicMock(duration=10.0),
            transcriber=None,
            max_transcribe_seconds=None,
        )
        assert result is None

    def test_maybe_transcribe_invalid_transcriber_degrades(self) -> None:
        """A transcriber exposing neither transcribe() nor generate() degrades."""
        from file_organizer.core.dispatcher import _maybe_transcribe

        bad = object()  # no .transcribe / .generate
        result = _maybe_transcribe(
            Path("/mock/a.mp3"),
            metadata=MagicMock(duration=10.0),
            transcriber=bad,
            max_transcribe_seconds=None,
        )
        assert result is None

    def test_maybe_transcribe_over_cap_skips(self) -> None:
        from file_organizer.core.dispatcher import _maybe_transcribe

        transcriber = MagicMock(spec=["transcribe"])
        result = _maybe_transcribe(
            Path("/mock/long.mp3"),
            metadata=MagicMock(duration=900.0),
            transcriber=transcriber,
            max_transcribe_seconds=600.0,
        )
        assert result is None
        transcriber.transcribe.assert_not_called()

    def test_maybe_transcribe_uses_transcribe_api(self) -> None:
        """The repo's AudioTranscriber (transcribe() -> TranscriptionResult) is used.

        Regression for #1287 review: the guard previously required generate(),
        rejecting the real Whisper transcriber and forcing metadata-only audio.
        """
        from types import SimpleNamespace

        from file_organizer.core.dispatcher import _maybe_transcribe

        transcriber = MagicMock(spec=["transcribe"])
        transcriber.transcribe.return_value = SimpleNamespace(text="hello from whisper")
        result = _maybe_transcribe(
            Path("/mock/a.mp3"),
            metadata=MagicMock(duration=10.0),
            transcriber=transcriber,
            max_transcribe_seconds=600.0,
        )
        assert result == "hello from whisper"
        transcriber.transcribe.assert_called_once_with("/mock/a.mp3")

    def test_maybe_transcribe_generate_duck_type_returns_text(self) -> None:
        """A generate(path) -> str duck-type is still accepted as a fallback."""
        from file_organizer.core.dispatcher import _maybe_transcribe

        transcriber = MagicMock(spec=["generate"])
        transcriber.generate.return_value = "hello world"
        result = _maybe_transcribe(
            Path("/mock/a.mp3"),
            metadata=MagicMock(duration=10.0),
            transcriber=transcriber,
            max_transcribe_seconds=600.0,
        )
        assert result == "hello world"
        transcriber.generate.assert_called_once_with("/mock/a.mp3")

    def test_maybe_transcribe_recoverable_error_degrades(self) -> None:
        """A RuntimeError during transcription degrades, not aborts."""
        from file_organizer.core.dispatcher import _maybe_transcribe

        transcriber = MagicMock(spec=["transcribe"])
        transcriber.transcribe.side_effect = RuntimeError("decode failed")
        result = _maybe_transcribe(
            Path("/mock/a.mp3"),
            metadata=MagicMock(duration=10.0),
            transcriber=transcriber,
            max_transcribe_seconds=None,
        )
        assert result is None

    def test_to_transcription_result_empty_returns_none(self) -> None:
        from file_organizer.core.dispatcher import _to_transcription_result

        assert _to_transcription_result(None, MagicMock(duration=5.0)) is None
        assert _to_transcription_result("", MagicMock(duration=5.0)) is None

    def test_to_transcription_result_wraps_text(self) -> None:
        from file_organizer.core.dispatcher import _to_transcription_result
        from file_organizer.services.audio.transcriber import TranscriptionResult

        out = _to_transcription_result("some words", MagicMock(duration=12.5))
        assert isinstance(out, TranscriptionResult)
        assert out.text == "some words"
        assert out.segments == []
        assert out.duration == 12.5

    def test_process_audio_attaches_transcript_and_passes_to_classifier(self) -> None:
        """End-to-end: transcript attaches to ProcessedFile and reaches classify()."""
        from file_organizer.core.dispatcher import process_audio_files

        audio_path = Path("/mock/podcasts/ep1.mp3")
        meta = MagicMock()
        meta.artist = None
        meta.title = None
        meta.duration = 30.0

        audio_type = MagicMock()
        audio_type.value = "podcast"
        classification = MagicMock()
        classification.audio_type = audio_type

        dest = MagicMock(spec=Path)
        dest.parent = MagicMock()
        dest.parent.as_posix.return_value = "Podcasts"
        dest.stem = "ep1"

        mock_extractor_instance = MagicMock()
        mock_extractor_instance.extract.return_value = meta
        mock_extractor_cls = MagicMock(return_value=mock_extractor_instance)

        mock_classifier_instance = MagicMock()
        mock_classifier_instance.classify.return_value = classification
        mock_organizer_instance = MagicMock()
        mock_organizer_instance.generate_path.return_value = dest

        from types import SimpleNamespace

        transcriber = MagicMock(spec=["transcribe"])
        transcriber.transcribe.return_value = SimpleNamespace(text="episode transcript text")

        with (
            patch(_AUDIO_CLASSIFIER_TARGET, return_value=mock_classifier_instance),
            patch(_AUDIO_ORGANIZER_TARGET, return_value=mock_organizer_instance),
        ):
            results = process_audio_files(
                [audio_path],
                extractor_cls=mock_extractor_cls,
                transcriber=transcriber,
                max_transcribe_seconds=600.0,
            )

        assert len(results) == 1
        assert results[0].transcript == "episode transcript text"
        # The classifier received a TranscriptionResult (not None).
        _, kwargs = mock_classifier_instance.classify.call_args
        assert kwargs["transcription"] is not None
        assert kwargs["transcription"].text == "episode transcript text"

    def test_process_audio_transcription_failure_does_not_fail_file(self) -> None:
        """A transcription failure degrades to metadata-only — file still classified."""
        from file_organizer.core.dispatcher import process_audio_files

        audio_path = Path("/mock/music/song.mp3")
        meta = MagicMock()
        meta.artist = "Band"
        meta.title = "Song"
        meta.duration = 20.0

        audio_type = MagicMock()
        audio_type.value = "music"
        classification = MagicMock()
        classification.audio_type = audio_type

        dest = MagicMock(spec=Path)
        dest.parent = MagicMock()
        dest.parent.as_posix.return_value = "Music/Band"
        dest.stem = "Song"

        mock_extractor_instance = MagicMock()
        mock_extractor_instance.extract.return_value = meta
        mock_extractor_cls = MagicMock(return_value=mock_extractor_instance)

        mock_classifier_instance = MagicMock()
        mock_classifier_instance.classify.return_value = classification
        mock_organizer_instance = MagicMock()
        mock_organizer_instance.generate_path.return_value = dest

        transcriber = MagicMock(spec=["transcribe"])
        transcriber.transcribe.side_effect = RuntimeError("whisper crashed")

        with (
            patch(_AUDIO_CLASSIFIER_TARGET, return_value=mock_classifier_instance),
            patch(_AUDIO_ORGANIZER_TARGET, return_value=mock_organizer_instance),
        ):
            results = process_audio_files(
                [audio_path],
                extractor_cls=mock_extractor_cls,
                transcriber=transcriber,
            )

        # File is NOT failed — it's classified from metadata, transcript is None.
        assert len(results) == 1
        assert results[0].error is None
        assert results[0].folder_name == "Music/Band"
        assert results[0].transcript is None


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
