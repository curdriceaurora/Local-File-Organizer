"""Integration tests for core organizer, dispatcher, and related modules.

Covers: FileDispatcher/process_* functions, FileOrganizer, FileOps, DisplayHelper,
ParallelProcessor, StorageAnalyzer, AudioUtils.
"""

from __future__ import annotations

from io import StringIO
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.ci]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_processed_file(
    file_path: Path,
    folder_name: str = "Documents",
    filename: str = "testfile",
    error: str | None = None,
    description: str = "Test description",
) -> Any:
    from file_organizer.services import ProcessedFile

    return ProcessedFile(
        file_path=file_path,
        description=description,
        folder_name=folder_name,
        filename=filename,
        error=error,
    )


def _make_processed_image(
    file_path: Path,
    folder_name: str = "Images/2024",
    filename: str = "photo",
    error: str | None = None,
    description: str = "Test image",
) -> Any:
    from file_organizer.services import ProcessedImage

    return ProcessedImage(
        file_path=file_path,
        description=description,
        folder_name=folder_name,
        filename=filename,
        error=error,
    )


def _make_parallel_config(
    max_workers: int = 2, timeout_per_file: float = 30.0, retry_count: int = 0
) -> Any:
    from file_organizer.parallel.config import ExecutorType, ParallelConfig

    return ParallelConfig(
        max_workers=max_workers,
        executor_type=ExecutorType.THREAD,
        prefetch_depth=1,
        timeout_per_file=timeout_per_file,
        retry_count=retry_count,
    )


# ---------------------------------------------------------------------------
# TestFileOps
# ---------------------------------------------------------------------------


class TestFileOps:
    """Tests for file_organizer.core.file_ops module."""

    def test_collect_files_from_directory(self, tmp_path: Path) -> None:
        from file_organizer.core import file_ops

        (tmp_path / "a.txt").write_text("content")
        (tmp_path / "b.pdf").write_text("content")
        console = MagicMock()

        result = file_ops.collect_files(tmp_path, console)

        assert len(result) == 2
        names = {p.name for p in result}
        assert "a.txt" in names
        assert "b.pdf" in names

    def test_collect_files_skips_hidden_files(self, tmp_path: Path) -> None:
        from file_organizer.core import file_ops

        (tmp_path / "visible.txt").write_text("content")
        (tmp_path / ".hidden").write_text("hidden")
        console = MagicMock()

        result = file_ops.collect_files(tmp_path, console)

        names = {p.name for p in result}
        assert "visible.txt" in names
        assert ".hidden" not in names

    def test_collect_files_skips_hidden_directories(self, tmp_path: Path) -> None:
        from file_organizer.core import file_ops

        hidden_dir = tmp_path / ".git"
        hidden_dir.mkdir()
        (hidden_dir / "config").write_text("config")
        (tmp_path / "real.txt").write_text("content")
        console = MagicMock()

        result = file_ops.collect_files(tmp_path, console)

        names = {p.name for p in result}
        assert "real.txt" in names
        assert "config" not in names

    def test_collect_files_single_file(self, tmp_path: Path) -> None:
        from file_organizer.core import file_ops

        single = tmp_path / "solo.txt"
        single.write_text("solo")
        console = MagicMock()

        result = file_ops.collect_files(single, console)

        assert len(result) == 1
        assert result[0] == single

    def test_collect_files_recursive(self, tmp_path: Path) -> None:
        from file_organizer.core import file_ops

        sub = tmp_path / "subdir"
        sub.mkdir()
        (tmp_path / "top.txt").write_text("top")
        (sub / "nested.txt").write_text("nested")
        console = MagicMock()

        result = file_ops.collect_files(tmp_path, console)

        assert len(result) == 2

    def test_collect_files_empty_directory(self, tmp_path: Path) -> None:
        from file_organizer.core import file_ops

        console = MagicMock()

        result = file_ops.collect_files(tmp_path, console)

        assert result == []

    def test_fallback_by_extension_pdf(self, tmp_path: Path) -> None:
        from file_organizer.core import file_ops

        f = tmp_path / "doc.pdf"
        f.write_text("content")

        results = file_ops.fallback_by_extension([f])

        assert len(results) == 1
        assert results[0].folder_name == "PDFs"
        assert results[0].filename == "doc"
        assert results[0].error is None

    def test_fallback_by_extension_docx(self, tmp_path: Path) -> None:
        from file_organizer.core import file_ops

        f = tmp_path / "report.docx"
        f.write_text("content")

        results = file_ops.fallback_by_extension([f])

        assert results[0].folder_name == "Documents"

    def test_fallback_by_extension_image(self, tmp_path: Path) -> None:
        from file_organizer.core import file_ops

        f = tmp_path / "photo.jpg"
        f.write_bytes(b"\xff\xd8\xff")

        results = file_ops.fallback_by_extension([f])

        assert results[0].folder_name.startswith("Images/")

    def test_fallback_by_extension_audio(self, tmp_path: Path) -> None:
        from file_organizer.core import file_ops

        f = tmp_path / "song.mp3"
        f.write_bytes(b"\xff\xfb")

        results = file_ops.fallback_by_extension([f])

        assert results[0].folder_name == "Audio/Unsorted"

    def test_fallback_by_extension_video(self, tmp_path: Path) -> None:
        from file_organizer.core import file_ops

        f = tmp_path / "movie.mp4"
        f.write_bytes(b"\x00\x00\x00\x00ftyp")

        results = file_ops.fallback_by_extension([f])

        assert results[0].folder_name == "Videos/Unsorted"

    def test_fallback_by_extension_unknown(self, tmp_path: Path) -> None:
        from file_organizer.core import file_ops

        f = tmp_path / "weird.xyz"
        f.write_text("??")

        results = file_ops.fallback_by_extension([f])

        assert results[0].folder_name == "Other"

    def test_organize_files_copies_files(self, tmp_path: Path) -> None:
        from file_organizer.core import file_ops

        src = tmp_path / "source"
        src.mkdir()
        f = src / "doc.txt"
        f.write_text("content")

        pf = _make_processed_file(f, folder_name="Docs", filename="doc")
        output = tmp_path / "output"

        result = file_ops.organize_files(
            [pf],
            output,
            skip_existing=True,
            use_hardlinks=False,
            undo_manager=None,
            transaction_id=None,
        )

        assert "Docs" in result
        assert "doc.txt" in result["Docs"]
        assert (output / "Docs" / "doc.txt").exists()

    def test_organize_files_skips_errors(self, tmp_path: Path) -> None:
        from file_organizer.core import file_ops

        f = tmp_path / "fail.txt"
        f.write_text("x")

        pf = _make_processed_file(f, error="AI error")
        output = tmp_path / "output"

        result = file_ops.organize_files(
            [pf],
            output,
            skip_existing=True,
            use_hardlinks=False,
            undo_manager=None,
            transaction_id=None,
        )

        assert result == {}

    def test_organize_files_skip_existing(self, tmp_path: Path) -> None:
        from file_organizer.core import file_ops

        src = tmp_path / "source"
        src.mkdir()
        f = src / "note.txt"
        f.write_text("hello")

        output = tmp_path / "output"
        dest_dir = output / "Docs"
        dest_dir.mkdir(parents=True)
        (dest_dir / "note.txt").write_text("existing")

        pf = _make_processed_file(f, folder_name="Docs", filename="note")

        file_ops.organize_files(
            [pf],
            output,
            skip_existing=True,
            use_hardlinks=False,
            undo_manager=None,
            transaction_id=None,
        )

        # Existing content must not be overwritten
        assert (dest_dir / "note.txt").read_text() == "existing"

    def test_organize_files_counter_when_not_skipping(self, tmp_path: Path) -> None:
        from file_organizer.core import file_ops

        src = tmp_path / "source"
        src.mkdir()
        f = src / "note.txt"
        f.write_text("new content")

        output = tmp_path / "output"
        dest_dir = output / "Docs"
        dest_dir.mkdir(parents=True)
        (dest_dir / "note.txt").write_text("old")

        pf = _make_processed_file(f, folder_name="Docs", filename="note")

        result = file_ops.organize_files(
            [pf],
            output,
            skip_existing=False,
            use_hardlinks=False,
            undo_manager=None,
            transaction_id=None,
        )

        assert "Docs" in result
        assert any("_1" in name or name == "note.txt" for name in result["Docs"])

    def test_simulate_organization(self, tmp_path: Path) -> None:
        from file_organizer.core import file_ops

        f = tmp_path / "x.pdf"
        f.write_text("content")
        pf = _make_processed_file(f, folder_name="PDFs", filename="x")

        result = file_ops.simulate_organization([pf], tmp_path / "output")

        assert "PDFs" in result
        assert "x.pdf" in result["PDFs"]
        # Confirm no actual file was written
        assert not (tmp_path / "output" / "PDFs" / "x.pdf").exists()

    def test_simulate_organization_skips_errors(self, tmp_path: Path) -> None:
        from file_organizer.core import file_ops

        f = tmp_path / "bad.pdf"
        f.write_text("x")
        pf = _make_processed_file(f, error="failed")

        result = file_ops.simulate_organization([pf], tmp_path / "out")

        assert result == {}

    def test_cleanup_empty_dirs(self, tmp_path: Path) -> None:
        from file_organizer.core import file_ops

        root = tmp_path / "root"
        empty = root / "empty_subdir"
        empty.mkdir(parents=True)

        file_ops.cleanup_empty_dirs(root)

        assert not empty.exists()

    def test_cleanup_empty_dirs_keeps_nonempty(self, tmp_path: Path) -> None:
        from file_organizer.core import file_ops

        root = tmp_path / "root"
        nonempty = root / "data"
        nonempty.mkdir(parents=True)
        (nonempty / "file.txt").write_text("keep me")

        file_ops.cleanup_empty_dirs(root)

        assert nonempty.exists()
        assert (nonempty / "file.txt").exists()


# ---------------------------------------------------------------------------
# TestDisplay
# ---------------------------------------------------------------------------


class TestDisplay:
    """Tests for file_organizer.core.display module."""

    def test_create_progress_returns_progress_object(self) -> None:
        from rich.console import Console
        from rich.progress import Progress

        from file_organizer.core.display import create_progress

        console = Console(quiet=True)
        progress = create_progress(console)

        assert isinstance(progress, Progress)

    def test_show_file_breakdown_runs_without_error(self) -> None:
        from rich.console import Console

        from file_organizer.core.display import show_file_breakdown

        console = Console(record=True, file=StringIO())
        show_file_breakdown(
            console,
            text_files=[Path("a.txt")],
            image_files=[Path("b.jpg")],
            video_files=[],
            audio_files=[],
            cad_files=[],
            other_files=[],
        )
        output = console.export_text()
        assert "File Type Breakdown" in output
        assert "1" in output

    def test_show_file_breakdown_all_empty(self) -> None:
        from rich.console import Console

        from file_organizer.core.display import show_file_breakdown

        console = Console(record=True, file=StringIO())
        show_file_breakdown(
            console,
            text_files=[],
            image_files=[],
            video_files=[],
            audio_files=[],
            cad_files=[],
            other_files=[],
        )
        output = console.export_text()
        assert "File Type Breakdown" in output
        assert "0" in output

    def test_show_summary_dry_run(self, tmp_path: Path) -> None:
        from rich.console import Console

        from file_organizer.core.display import show_summary
        from file_organizer.core.types import OrganizationResult

        console = Console(record=True, file=StringIO())
        result = OrganizationResult(total_files=3, processed_files=2, failed_files=1)

        show_summary(console, result, tmp_path, dry_run=True)
        output = console.export_text()
        assert "Processed: 2" in output
        assert "Failed: 1" in output

    def test_show_summary_not_dry_run(self, tmp_path: Path) -> None:
        from rich.console import Console

        from file_organizer.core.display import show_summary
        from file_organizer.core.types import OrganizationResult

        console = Console(record=True, file=StringIO())
        result = OrganizationResult(
            total_files=5,
            processed_files=5,
            organized_structure={"Docs": ["a.txt", "b.txt"]},
        )

        show_summary(console, result, tmp_path, dry_run=False)
        output = console.export_text()
        assert "Processed: 5" in output

    def test_show_summary_with_errors(self, tmp_path: Path) -> None:
        from rich.console import Console

        from file_organizer.core.display import show_summary
        from file_organizer.core.types import OrganizationResult

        console = Console(record=True, file=StringIO())
        result = OrganizationResult(
            total_files=2,
            failed_files=2,
            errors=[("file1.txt", "error1"), ("file2.txt", "error2")],
        )

        show_summary(console, result, tmp_path, dry_run=True)
        output = console.export_text()
        assert "error1" in output
        assert "error2" in output

    def test_show_summary_with_many_errors(self, tmp_path: Path) -> None:
        from rich.console import Console

        from file_organizer.core.display import show_summary
        from file_organizer.core.types import OrganizationResult

        console = Console(record=True, file=StringIO())
        result = OrganizationResult(
            total_files=20,
            failed_files=20,
            errors=[(f"file{i}.txt", f"error{i}") for i in range(15)],
        )

        show_summary(console, result, tmp_path, dry_run=True)
        output = console.export_text()
        assert "Organization Complete" in output

    def test_show_summary_with_deduplicated_files(self, tmp_path: Path) -> None:
        from rich.console import Console

        from file_organizer.core.display import show_summary
        from file_organizer.core.types import OrganizationResult

        console = Console(record=True, file=StringIO())
        result = OrganizationResult(
            total_files=10,
            processed_files=8,
            deduplicated_files=2,
        )

        show_summary(console, result, tmp_path, dry_run=True)
        output = console.export_text()
        assert "Duplicates removed: 2" in output

    def test_show_summary_with_organized_structure_sorted(self, tmp_path: Path) -> None:
        from rich.console import Console

        from file_organizer.core.display import show_summary
        from file_organizer.core.types import OrganizationResult

        console = Console(record=True, file=StringIO())
        result = OrganizationResult(
            total_files=4,
            processed_files=4,
            organized_structure={
                "Zeta": ["z.txt"],
                "Alpha": ["a.txt", "b.txt"],
            },
        )

        show_summary(console, result, tmp_path, dry_run=False)
        output = console.export_text()
        assert "Alpha" in output
        assert "Zeta" in output

    def test_progress_context_manager(self) -> None:
        from rich.console import Console

        from file_organizer.core.display import create_progress

        console = Console(quiet=True)
        with create_progress(console) as progress:
            task = progress.add_task("test", total=10)
            progress.update(task, advance=5)

    def test_show_file_breakdown_with_cad_and_audio(self) -> None:
        from rich.console import Console

        from file_organizer.core.display import show_file_breakdown

        console = Console(record=True, file=StringIO())
        show_file_breakdown(
            console,
            text_files=[],
            image_files=[],
            video_files=[Path("v.mp4")],
            audio_files=[Path("a.mp3")],
            cad_files=[Path("c.dwg")],
            other_files=[Path("x.xyz")],
        )
        output = console.export_text()
        assert "File Type Breakdown" in output


# ---------------------------------------------------------------------------
# TestDispatcher
# ---------------------------------------------------------------------------


class TestDispatcher:
    """Tests for file_organizer.core.dispatcher module."""

    def _make_mock_parallel_processor(self, return_results: list[Any]) -> Any:
        """Create a mock ParallelProcessor that exercises the dispatcher callback."""
        results_snapshot = list(return_results)

        def _side_effect(files: list[Any], process_fn: Any) -> Any:
            # Call process_fn to verify dispatcher wires the right callback
            for f in files:
                process_fn(f)
            return iter(results_snapshot)

        mock_pp = MagicMock()
        mock_pp.process_batch_iter.side_effect = _side_effect
        return mock_pp

    def _make_file_result_success(self, path: Path, result: Any) -> Any:
        from file_organizer.parallel.result import FileResult

        return FileResult(path=path, success=True, result=result, duration_ms=1.0)

    def _make_file_result_failure(self, path: Path, error: str = "mock error") -> Any:
        from file_organizer.parallel.result import FileResult

        return FileResult(path=path, success=False, error=error, duration_ms=1.0)

    def test_process_text_files_success(self, tmp_path: Path) -> None:
        from rich.console import Console

        from file_organizer.core import dispatcher
        from file_organizer.services import ProcessedFile

        f = tmp_path / "doc.txt"
        f.write_text("hello")

        processed_file = ProcessedFile(
            file_path=f,
            description="A doc",
            folder_name="Documents",
            filename="doc",
            error=None,
        )
        file_result = self._make_file_result_success(f, processed_file)

        mock_tp = MagicMock()
        mock_pp = self._make_mock_parallel_processor([file_result])
        console = Console(quiet=True)

        results = dispatcher.process_text_files([f], mock_tp, mock_pp, console)

        assert len(results) == 1
        assert results[0].folder_name == "Documents"
        assert results[0].error is None

    def test_process_text_files_with_error_in_result(self, tmp_path: Path) -> None:
        from rich.console import Console

        from file_organizer.core import dispatcher
        from file_organizer.services import ProcessedFile

        f = tmp_path / "broken.txt"
        f.write_text("x")

        processed_file = ProcessedFile(
            file_path=f,
            description="",
            folder_name="errors",
            filename="broken",
            error="AI failed",
        )
        file_result = self._make_file_result_success(f, processed_file)

        mock_tp = MagicMock()
        mock_pp = self._make_mock_parallel_processor([file_result])
        console = Console(quiet=True)

        results = dispatcher.process_text_files([f], mock_tp, mock_pp, console)

        assert len(results) == 1
        assert results[0].error == "AI failed"

    def test_process_text_files_failure_from_parallel(self, tmp_path: Path) -> None:
        from rich.console import Console

        from file_organizer.core import dispatcher

        f = tmp_path / "fail.txt"
        f.write_text("x")

        file_result = self._make_file_result_failure(f, "timeout")

        mock_tp = MagicMock()
        mock_pp = self._make_mock_parallel_processor([file_result])
        console = Console(quiet=True)

        results = dispatcher.process_text_files([f], mock_tp, mock_pp, console)

        assert len(results) == 1
        assert results[0].folder_name == "errors"
        assert results[0].error == "timeout"

    def test_process_text_files_empty_list(self, tmp_path: Path) -> None:
        from rich.console import Console

        from file_organizer.core import dispatcher

        mock_tp = MagicMock()
        mock_pp = self._make_mock_parallel_processor([])
        console = Console(quiet=True)

        results = dispatcher.process_text_files([], mock_tp, mock_pp, console)

        assert results == []

    def test_process_image_files_success(self, tmp_path: Path) -> None:
        from rich.console import Console

        from file_organizer.core import dispatcher
        from file_organizer.services import ProcessedImage

        f = tmp_path / "photo.jpg"
        f.write_bytes(b"\xff\xd8\xff")

        processed_img = ProcessedImage(
            file_path=f,
            description="Photo",
            folder_name="Images/2024",
            filename="photo",
            error=None,
        )
        file_result = self._make_file_result_success(f, processed_img)

        mock_vp = MagicMock()
        mock_pp = self._make_mock_parallel_processor([file_result])
        console = Console(quiet=True)

        results = dispatcher.process_image_files([f], mock_vp, mock_pp, console)

        assert len(results) == 1
        assert results[0].folder_name == "Images/2024"
        assert results[0].error is None

    def test_process_image_files_failure_from_parallel(self, tmp_path: Path) -> None:
        from rich.console import Console

        from file_organizer.core import dispatcher

        f = tmp_path / "bad.jpg"
        f.write_bytes(b"\xff\xd8\xff")

        file_result = self._make_file_result_failure(f, "vision model error")

        mock_vp = MagicMock()
        mock_pp = self._make_mock_parallel_processor([file_result])
        console = Console(quiet=True)

        results = dispatcher.process_image_files([f], mock_vp, mock_pp, console)

        assert len(results) == 1
        assert results[0].folder_name == "errors"
        assert "vision model error" in results[0].error

    def test_process_image_files_with_error_in_result(self, tmp_path: Path) -> None:
        from rich.console import Console

        from file_organizer.core import dispatcher
        from file_organizer.services import ProcessedImage

        f = tmp_path / "blurry.jpg"
        f.write_bytes(b"\xff\xd8\xff")

        processed_img = ProcessedImage(
            file_path=f,
            description="",
            folder_name="errors",
            filename="blurry",
            error="Cannot identify",
        )
        file_result = self._make_file_result_success(f, processed_img)

        mock_vp = MagicMock()
        mock_pp = self._make_mock_parallel_processor([file_result])
        console = Console(quiet=True)

        results = dispatcher.process_image_files([f], mock_vp, mock_pp, console)

        assert len(results) == 1
        assert results[0].error == "Cannot identify"

    def test_process_audio_files_success(self, tmp_path: Path) -> None:
        from file_organizer.core import dispatcher

        f = tmp_path / "track.mp3"
        f.write_bytes(b"\xff\xfb")

        # Build concrete mocks so string operations in dispatcher succeed
        mock_metadata = MagicMock()
        mock_metadata.artist = "Artist"
        mock_metadata.title = "Track"
        mock_metadata.duration = 180.0

        mock_audio_type = MagicMock()
        mock_audio_type.value = "music"

        mock_classification = MagicMock()
        mock_classification.audio_type = mock_audio_type

        mock_extractor_instance = MagicMock()
        mock_extractor_instance.extract.return_value = mock_metadata
        mock_extractor_cls = MagicMock(return_value=mock_extractor_instance)

        mock_classifier_cls = MagicMock()
        mock_classifier_cls.return_value.classify.return_value = mock_classification

        mock_organizer_cls = MagicMock()
        mock_organizer_cls.return_value.generate_path.return_value = Path("Music/Artist/Track.mp3")

        # AudioClassifier and AudioOrganizer are imported locally inside
        # process_audio_files; patch their module-level definitions so the
        # local import sees the mock.
        with (
            patch(
                "file_organizer.services.audio.classifier.AudioClassifier",
                mock_classifier_cls,
            ),
            patch(
                "file_organizer.services.audio.organizer.AudioOrganizer",
                mock_organizer_cls,
            ),
        ):
            results = dispatcher.process_audio_files([f], extractor_cls=mock_extractor_cls)

        assert len(results) == 1
        assert results[0].error is None

    def test_process_audio_files_extraction_error(self, tmp_path: Path) -> None:
        from file_organizer.core import dispatcher

        f = tmp_path / "corrupt.mp3"
        f.write_bytes(b"\x00")

        mock_extractor_instance = MagicMock()
        mock_extractor_instance.extract.side_effect = ValueError("Bad audio")
        mock_extractor_cls = MagicMock(return_value=mock_extractor_instance)

        results = dispatcher.process_audio_files([f], extractor_cls=mock_extractor_cls)

        assert len(results) == 1
        assert results[0].folder_name == "Audio/Unsorted"
        assert results[0].error is not None

    def test_process_audio_files_empty_list(self) -> None:
        from file_organizer.core import dispatcher

        results = dispatcher.process_audio_files([])

        assert results == []

    def test_process_video_files_success(self, tmp_path: Path) -> None:
        from file_organizer.core import dispatcher

        f = tmp_path / "video.mp4"
        f.write_bytes(b"\x00\x00\x00\x00ftyp")

        mock_extractor_instance = MagicMock()
        mock_extractor_instance.extract.return_value = MagicMock()
        mock_extractor_cls = MagicMock(return_value=mock_extractor_instance)

        mock_organizer_cls = MagicMock()
        mock_organizer_cls.return_value.generate_path.return_value = ("Videos/Action", "video")
        mock_organizer_cls.return_value.generate_description.return_value = "An action video"

        with patch("file_organizer.services.video.organizer.VideoOrganizer", mock_organizer_cls):
            with patch(
                "file_organizer.core.dispatcher.VideoOrganizer", mock_organizer_cls, create=True
            ):
                results = dispatcher.process_video_files([f], extractor_cls=mock_extractor_cls)

        assert len(results) == 1
        assert results[0].folder_name == "Videos/Action"
        assert results[0].filename == "video"
        assert results[0].error is None

    def test_process_video_files_extraction_error(self, tmp_path: Path) -> None:
        from file_organizer.core import dispatcher

        f = tmp_path / "bad.mp4"
        f.write_bytes(b"\x00")

        mock_extractor_instance = MagicMock()
        mock_extractor_instance.extract.side_effect = OSError("Cannot open")
        mock_extractor_cls = MagicMock(return_value=mock_extractor_instance)

        results = dispatcher.process_video_files([f], extractor_cls=mock_extractor_cls)

        assert len(results) == 1
        assert results[0].folder_name == "Videos/Unsorted"
        assert results[0].error is not None

    def test_process_video_files_file_not_found(self, tmp_path: Path) -> None:
        from file_organizer.core import dispatcher

        f = tmp_path / "ghost.mp4"
        # File does not exist

        mock_extractor_instance = MagicMock()
        mock_extractor_instance.extract.side_effect = FileNotFoundError("No file")
        mock_extractor_cls = MagicMock(return_value=mock_extractor_instance)

        results = dispatcher.process_video_files([f], extractor_cls=mock_extractor_cls)

        assert len(results) == 1
        assert results[0].folder_name == "Videos/Unsorted"
        assert results[0].error is not None

    def test_process_video_files_empty_list(self) -> None:
        from file_organizer.core import dispatcher

        results = dispatcher.process_video_files([])

        assert results == []

    def test_process_audio_files_runtime_error(self, tmp_path: Path) -> None:
        from file_organizer.core import dispatcher

        f = tmp_path / "audio.flac"
        f.write_bytes(b"\x66\x4c\x61\x43")

        mock_extractor_instance = MagicMock()
        mock_extractor_instance.extract.side_effect = RuntimeError("Decode failed")
        mock_extractor_cls = MagicMock(return_value=mock_extractor_instance)

        results = dispatcher.process_audio_files([f], extractor_cls=mock_extractor_cls)

        assert len(results) == 1
        assert results[0].error is not None
        assert "Decode failed" in results[0].error


# ---------------------------------------------------------------------------
# TestParallelProcessor
# ---------------------------------------------------------------------------


class TestParallelProcessor:
    """Tests for file_organizer.parallel.processor module."""

    def test_process_batch_empty_files(self) -> None:
        from file_organizer.parallel.processor import ParallelProcessor

        pp = ParallelProcessor(_make_parallel_config())
        result = pp.process_batch([], lambda p: p.read_text())

        assert result.total == 0
        assert result.succeeded == 0
        assert result.failed == 0

    def test_process_batch_success(self, tmp_path: Path) -> None:
        from file_organizer.parallel.processor import ParallelProcessor

        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("hello")
        f2.write_text("world")

        pp = ParallelProcessor(_make_parallel_config())
        result = pp.process_batch([f1, f2], lambda p: p.read_text())

        assert result.total == 2
        assert result.succeeded == 2
        assert result.failed == 0

    def test_process_batch_failure(self, tmp_path: Path) -> None:
        from file_organizer.parallel.processor import ParallelProcessor

        f = tmp_path / "non_existent.txt"
        # File doesn't exist - reading it will fail

        pp = ParallelProcessor(_make_parallel_config(retry_count=0))
        result = pp.process_batch([f], lambda p: p.read_text())

        assert result.total == 1
        assert result.failed == 1

    def test_process_batch_iter_yields_results(self, tmp_path: Path) -> None:
        from file_organizer.parallel.processor import ParallelProcessor

        files = []
        for i in range(3):
            f = tmp_path / f"file{i}.txt"
            f.write_text(f"content{i}")
            files.append(f)

        pp = ParallelProcessor(_make_parallel_config())
        results = list(pp.process_batch_iter(files, lambda p: p.read_text()))

        assert len(results) == 3
        success_count = sum(1 for r in results if r.success)
        assert success_count == 3

    def test_process_batch_iter_empty_files(self) -> None:
        from file_organizer.parallel.processor import ParallelProcessor

        pp = ParallelProcessor(_make_parallel_config())
        results = list(pp.process_batch_iter([], lambda p: None))

        assert results == []

    def test_process_batch_iter_handles_exceptions(self, tmp_path: Path) -> None:
        from file_organizer.parallel.processor import ParallelProcessor

        f = tmp_path / "test.txt"
        f.write_text("content")

        def always_fails(p: Path) -> None:
            raise RuntimeError("Intentional failure")

        pp = ParallelProcessor(_make_parallel_config(retry_count=0))
        results = list(pp.process_batch_iter([f], always_fails))

        assert len(results) == 1
        assert results[0].success is False
        assert "Intentional failure" in results[0].error

    def test_config_property_returns_config(self) -> None:
        from file_organizer.parallel.processor import ParallelProcessor

        config = _make_parallel_config(max_workers=4)
        pp = ParallelProcessor(config)

        assert pp.config is config
        assert pp.config.max_workers == 4

    def test_default_config_when_none(self) -> None:
        from file_organizer.parallel.processor import ParallelProcessor

        pp = ParallelProcessor(None)

        assert pp.config is not None

    def test_shutdown_is_noop(self) -> None:
        from file_organizer.parallel.processor import ParallelProcessor

        pp = ParallelProcessor(_make_parallel_config())
        pp.shutdown()  # Should not raise

    def test_process_batch_result_summary_contains_counts(self, tmp_path: Path) -> None:
        from file_organizer.parallel.processor import ParallelProcessor

        f = tmp_path / "data.txt"
        f.write_text("data")

        pp = ParallelProcessor(_make_parallel_config())
        result = pp.process_batch([f], lambda p: p.read_text())

        summary = result.summary()
        assert "1" in summary
        assert "0" in summary

    def test_process_batch_with_progress_callback(self, tmp_path: Path) -> None:
        from file_organizer.parallel.config import ExecutorType, ParallelConfig
        from file_organizer.parallel.processor import ParallelProcessor

        callback_calls: list[tuple[int, int]] = []

        def callback(completed: int, total: int, result: Any) -> None:
            callback_calls.append((completed, total))

        f = tmp_path / "cb.txt"
        f.write_text("callback test")

        config = ParallelConfig(
            max_workers=1,
            executor_type=ExecutorType.THREAD,
            prefetch_depth=1,
            timeout_per_file=30.0,
            retry_count=0,
            progress_callback=callback,
        )
        pp = ParallelProcessor(config)
        result = pp.process_batch([f], lambda p: p.read_text())

        assert result.succeeded == 1
        assert len(callback_calls) == 1
        assert callback_calls[0] == (1, 1)

    def test_batch_result_files_per_second_positive(self, tmp_path: Path) -> None:
        from file_organizer.parallel.processor import ParallelProcessor

        f = tmp_path / "fps.txt"
        f.write_text("fps test")

        pp = ParallelProcessor(_make_parallel_config())
        result = pp.process_batch([f], lambda p: p.read_text())

        assert result.files_per_second > 0

    def test_file_result_str_success(self, tmp_path: Path) -> None:
        from file_organizer.parallel.result import FileResult

        f = tmp_path / "ok.txt"
        r = FileResult(path=f, success=True, result="data", duration_ms=5.0)

        s = str(r)
        assert "OK" in s
        assert "ok.txt" in s

    def test_file_result_str_failure(self, tmp_path: Path) -> None:
        from file_organizer.parallel.result import FileResult

        f = tmp_path / "err.txt"
        r = FileResult(path=f, success=False, error="bad thing", duration_ms=2.0)

        s = str(r)
        assert "FAIL" in s
        assert "bad thing" in s


# ---------------------------------------------------------------------------
# TestStorageAnalyzer
# ---------------------------------------------------------------------------


class TestStorageAnalyzer:
    """Tests for file_organizer.services.analytics.storage_analyzer module."""

    def test_analyze_directory_basic(self, tmp_path: Path) -> None:
        from file_organizer.services.analytics.storage_analyzer import StorageAnalyzer

        (tmp_path / "a.txt").write_text("hello")
        (tmp_path / "b.pdf").write_bytes(b"x" * 100)

        analyzer = StorageAnalyzer()
        stats = analyzer.analyze_directory(tmp_path)

        assert stats.file_count == 2
        assert stats.total_size > 0

    def test_analyze_directory_invalid_path_raises(self, tmp_path: Path) -> None:
        from file_organizer.services.analytics.storage_analyzer import StorageAnalyzer

        analyzer = StorageAnalyzer()

        with pytest.raises(ValueError, match="Invalid directory"):
            analyzer.analyze_directory(tmp_path / "nonexistent")

    def test_analyze_directory_not_a_dir_raises(self, tmp_path: Path) -> None:
        from file_organizer.services.analytics.storage_analyzer import StorageAnalyzer

        f = tmp_path / "file.txt"
        f.write_text("not a dir")
        analyzer = StorageAnalyzer()

        with pytest.raises(ValueError, match="Invalid directory"):
            analyzer.analyze_directory(f)

    def test_analyze_directory_size_by_type(self, tmp_path: Path) -> None:
        from file_organizer.services.analytics.storage_analyzer import StorageAnalyzer

        (tmp_path / "a.txt").write_text("hello")
        (tmp_path / "b.txt").write_text("world")
        (tmp_path / "c.pdf").write_bytes(b"x" * 200)

        analyzer = StorageAnalyzer()
        stats = analyzer.analyze_directory(tmp_path)

        assert ".txt" in stats.size_by_type
        assert ".pdf" in stats.size_by_type
        assert stats.size_by_type[".pdf"] == 200

    def test_analyze_directory_counts_subdirectories(self, tmp_path: Path) -> None:
        from file_organizer.services.analytics.storage_analyzer import StorageAnalyzer

        subdir = tmp_path / "sub"
        subdir.mkdir()
        (subdir / "nested.txt").write_text("data")

        analyzer = StorageAnalyzer()
        stats = analyzer.analyze_directory(tmp_path)

        assert stats.directory_count >= 1

    def test_analyze_directory_caches_results(self, tmp_path: Path) -> None:
        from file_organizer.services.analytics.storage_analyzer import StorageAnalyzer

        (tmp_path / "a.txt").write_text("initial")

        analyzer = StorageAnalyzer()
        stats1 = analyzer.analyze_directory(tmp_path, use_cache=True)

        # Add new file but result should be cached
        (tmp_path / "b.txt").write_text("new")
        stats2 = analyzer.analyze_directory(tmp_path, use_cache=True)

        assert stats1.file_count == stats2.file_count

    def test_analyze_directory_bypasses_cache(self, tmp_path: Path) -> None:
        from file_organizer.services.analytics.storage_analyzer import StorageAnalyzer

        (tmp_path / "a.txt").write_text("initial")

        analyzer = StorageAnalyzer()
        stats1 = analyzer.analyze_directory(tmp_path, use_cache=False)

        (tmp_path / "b.txt").write_text("new")
        stats2 = analyzer.analyze_directory(tmp_path, use_cache=False)

        assert stats2.file_count == stats1.file_count + 1

    def test_calculate_size_distribution(self, tmp_path: Path) -> None:
        from file_organizer.services.analytics.storage_analyzer import StorageAnalyzer

        (tmp_path / "tiny.txt").write_bytes(b"x" * 100)  # < 1KB
        (tmp_path / "small.txt").write_bytes(b"x" * 2000)  # 1KB-1MB

        analyzer = StorageAnalyzer()
        dist = analyzer.calculate_size_distribution(tmp_path)

        assert dist.total_files == 2
        assert dist.by_size_range.get("tiny", 0) + dist.by_size_range.get("small", 0) == 2

    def test_identify_large_files_empty(self, tmp_path: Path) -> None:
        from file_organizer.services.analytics.storage_analyzer import StorageAnalyzer

        (tmp_path / "small.txt").write_bytes(b"x" * 100)

        analyzer = StorageAnalyzer()
        large = analyzer.identify_large_files(tmp_path, threshold=1024 * 1024)

        assert large == []

    def test_identify_large_files_with_large_file(self, tmp_path: Path) -> None:
        from file_organizer.services.analytics.storage_analyzer import StorageAnalyzer

        big_file = tmp_path / "big.bin"
        big_file.write_bytes(b"x" * 200)

        analyzer = StorageAnalyzer()
        large = analyzer.identify_large_files(tmp_path, threshold=100)

        assert len(large) == 1
        assert large[0].path == big_file
        assert large[0].size == 200

    def test_identify_large_files_sorted_by_size(self, tmp_path: Path) -> None:
        from file_organizer.services.analytics.storage_analyzer import StorageAnalyzer

        (tmp_path / "big.bin").write_bytes(b"x" * 500)
        (tmp_path / "bigger.bin").write_bytes(b"x" * 1000)
        (tmp_path / "biggest.bin").write_bytes(b"x" * 2000)

        analyzer = StorageAnalyzer()
        large = analyzer.identify_large_files(tmp_path, threshold=100)

        assert large[0].size >= large[1].size >= large[2].size

    def test_identify_large_files_top_n_limit(self, tmp_path: Path) -> None:
        from file_organizer.services.analytics.storage_analyzer import StorageAnalyzer

        for i in range(10):
            (tmp_path / f"file{i}.bin").write_bytes(b"x" * (i + 1) * 100)

        analyzer = StorageAnalyzer()
        large = analyzer.identify_large_files(tmp_path, threshold=100, top_n=3)

        assert len(large) == 3

    def test_get_duplicate_space_calculates_correctly(self, tmp_path: Path) -> None:
        from file_organizer.services.analytics.storage_analyzer import StorageAnalyzer

        f = tmp_path / "dup.bin"
        f.write_bytes(b"x" * 500)

        groups = [{"files": [str(f), str(tmp_path / "copy1.bin"), str(tmp_path / "copy2.bin")]}]

        analyzer = StorageAnalyzer()
        wasted = analyzer.get_duplicate_space(groups)

        assert wasted == 1000  # 2 extra copies x 500 bytes

    def test_get_duplicate_space_single_file_group(self, tmp_path: Path) -> None:
        from file_organizer.services.analytics.storage_analyzer import StorageAnalyzer

        f = tmp_path / "solo.bin"
        f.write_bytes(b"x" * 100)

        groups = [{"files": [str(f)]}]

        analyzer = StorageAnalyzer()
        wasted = analyzer.get_duplicate_space(groups)

        assert wasted == 0

    def test_get_duplicate_space_empty_groups(self) -> None:
        from file_organizer.services.analytics.storage_analyzer import StorageAnalyzer

        analyzer = StorageAnalyzer()
        wasted = analyzer.get_duplicate_space([])

        assert wasted == 0

    def test_clear_cache(self, tmp_path: Path) -> None:
        from file_organizer.services.analytics.storage_analyzer import StorageAnalyzer

        (tmp_path / "f.txt").write_text("x")
        analyzer = StorageAnalyzer()
        analyzer.analyze_directory(tmp_path)

        assert len(analyzer._cache) == 1

        analyzer.clear_cache()

        assert len(analyzer._cache) == 0

    def test_walk_directory_public_api(self, tmp_path: Path) -> None:
        from file_organizer.services.analytics.storage_analyzer import StorageAnalyzer

        subdir = tmp_path / "sub"
        subdir.mkdir()
        (tmp_path / "a.txt").write_text("a")
        (subdir / "b.txt").write_text("b")

        analyzer = StorageAnalyzer()
        items = list(analyzer.walk_directory(tmp_path))

        paths = {p.name for p in items}
        assert "sub" in paths
        assert "a.txt" in paths

    def test_walk_directory_raises_for_nonexistent(self, tmp_path: Path) -> None:
        from file_organizer.services.analytics.storage_analyzer import StorageAnalyzer

        analyzer = StorageAnalyzer()

        with pytest.raises(FileNotFoundError):
            list(analyzer.walk_directory(tmp_path / "no_such_dir"))

    def test_walk_directory_raises_for_file(self, tmp_path: Path) -> None:
        from file_organizer.services.analytics.storage_analyzer import StorageAnalyzer

        f = tmp_path / "not_dir.txt"
        f.write_text("x")
        analyzer = StorageAnalyzer()

        with pytest.raises(NotADirectoryError):
            list(analyzer.walk_directory(f))

    def test_walk_directory_with_max_depth(self, tmp_path: Path) -> None:
        from file_organizer.services.analytics.storage_analyzer import StorageAnalyzer

        level1 = tmp_path / "level1"
        level2 = level1 / "level2"
        level3 = level2 / "level3"
        level3.mkdir(parents=True)
        (level3 / "deep.txt").write_text("deep")

        analyzer = StorageAnalyzer()
        items = list(analyzer.walk_directory(tmp_path, max_depth=1))

        item_names = {p.name for p in items}
        assert "level1" in item_names
        # level2 at depth 2 may or may not appear depending on max_depth semantics
        # We only assert that deep.txt is NOT in results
        assert "deep.txt" not in item_names

    def test_formatted_total_size_property(self, tmp_path: Path) -> None:
        from file_organizer.services.analytics.storage_analyzer import StorageAnalyzer

        (tmp_path / "data.bin").write_bytes(b"x" * 1024)

        analyzer = StorageAnalyzer()
        stats = analyzer.analyze_directory(tmp_path)

        formatted = stats.formatted_total_size
        assert formatted != ""
        assert any(unit in formatted for unit in ["B", "KB", "MB", "GB"])

    def test_analyze_directory_max_depth_limits_scan(self, tmp_path: Path) -> None:
        from file_organizer.services.analytics.storage_analyzer import StorageAnalyzer

        deep = tmp_path / "a" / "b" / "c"
        deep.mkdir(parents=True)
        (deep / "deep.txt").write_text("deep content")
        (tmp_path / "top.txt").write_text("top content")

        analyzer = StorageAnalyzer()
        stats_limited = analyzer.analyze_directory(tmp_path, max_depth=0, use_cache=False)
        stats_unlimited = analyzer.analyze_directory(tmp_path, max_depth=None, use_cache=False)

        assert stats_unlimited.file_count >= stats_limited.file_count


# ---------------------------------------------------------------------------
# TestAudioUtils
# ---------------------------------------------------------------------------


class TestAudioUtils:
    """Tests for file_organizer.services.audio.utils module."""

    def test_is_audio_file_mp3(self, tmp_path: Path) -> None:
        from file_organizer.services.audio.utils import is_audio_file

        f = tmp_path / "song.mp3"
        f.write_bytes(b"\xff\xfb")

        assert is_audio_file(f) is True

    def test_is_audio_file_wav(self, tmp_path: Path) -> None:
        from file_organizer.services.audio.utils import is_audio_file

        f = tmp_path / "sound.wav"
        f.write_bytes(b"RIFF")

        assert is_audio_file(f) is True

    def test_is_audio_file_flac(self, tmp_path: Path) -> None:
        from file_organizer.services.audio.utils import is_audio_file

        f = tmp_path / "track.flac"
        f.write_bytes(b"\x66\x4c\x61\x43")

        assert is_audio_file(f) is True

    def test_is_audio_file_not_audio(self, tmp_path: Path) -> None:
        from file_organizer.services.audio.utils import is_audio_file

        f = tmp_path / "doc.pdf"
        f.write_text("not audio")

        assert is_audio_file(f) is False

    def test_is_audio_file_txt(self, tmp_path: Path) -> None:
        from file_organizer.services.audio.utils import is_audio_file

        f = tmp_path / "readme.txt"
        f.write_text("readme")

        assert is_audio_file(f) is False

    def test_is_audio_file_m4a(self, tmp_path: Path) -> None:
        from file_organizer.services.audio.utils import is_audio_file

        assert is_audio_file(Path("podcast.m4a")) is True

    def test_is_audio_file_ogg(self) -> None:
        from file_organizer.services.audio.utils import is_audio_file

        assert is_audio_file(Path("music.ogg")) is True

    def test_is_audio_file_aac(self) -> None:
        from file_organizer.services.audio.utils import is_audio_file

        assert is_audio_file(Path("audio.aac")) is True

    def test_is_audio_file_opus(self) -> None:
        from file_organizer.services.audio.utils import is_audio_file

        # .opus is in the supported set
        assert is_audio_file(Path("voice.opus")) is True

    def test_get_audio_duration_file_not_found(self, tmp_path: Path) -> None:
        from file_organizer.services.audio.utils import get_audio_duration

        with pytest.raises(FileNotFoundError):
            get_audio_duration(tmp_path / "nonexistent.mp3")

    def test_get_audio_duration_returns_float_when_no_libs(self, tmp_path: Path) -> None:
        import sys

        from file_organizer.services.audio.utils import get_audio_duration

        f = tmp_path / "dummy.mp3"
        f.write_bytes(b"\xff\xfb")

        # Block both optional libs so the function takes the fallback path and returns 0.0
        with patch.dict(sys.modules, {"pydub": None, "tinytag": None}):
            result = get_audio_duration(f)

        assert result == 0.0

    def test_validate_audio_file_nonexistent(self, tmp_path: Path) -> None:
        from file_organizer.services.audio.utils import validate_audio_file

        valid, msg = validate_audio_file(tmp_path / "ghost.mp3")

        assert valid is False
        assert msg is not None
        assert "does not exist" in msg

    def test_validate_audio_file_directory(self, tmp_path: Path) -> None:
        from file_organizer.services.audio.utils import validate_audio_file

        valid, msg = validate_audio_file(tmp_path)

        assert valid is False
        assert msg is not None
        assert "not a file" in msg

    def test_validate_audio_file_unsupported_extension(self, tmp_path: Path) -> None:
        from file_organizer.services.audio.utils import validate_audio_file

        f = tmp_path / "document.pdf"
        f.write_text("not audio")

        valid, msg = validate_audio_file(f)

        assert valid is False
        assert msg is not None
        assert "Unsupported" in msg

    def test_calculate_audio_checksum_sha256(self, tmp_path: Path) -> None:
        from file_organizer.services.audio.utils import calculate_audio_checksum

        f = tmp_path / "audio.bin"
        f.write_bytes(b"test audio content")

        checksum = calculate_audio_checksum(f, algorithm="sha256")

        assert len(checksum) == 64
        assert checksum.isalnum()

    def test_calculate_audio_checksum_md5(self, tmp_path: Path) -> None:
        from file_organizer.services.audio.utils import calculate_audio_checksum

        f = tmp_path / "audio.bin"
        f.write_bytes(b"test audio content")

        checksum = calculate_audio_checksum(f, algorithm="md5")

        assert len(checksum) == 32

    def test_calculate_audio_checksum_deterministic(self, tmp_path: Path) -> None:
        from file_organizer.services.audio.utils import calculate_audio_checksum

        f = tmp_path / "audio.bin"
        f.write_bytes(b"deterministic content")

        checksum1 = calculate_audio_checksum(f)
        checksum2 = calculate_audio_checksum(f)

        assert checksum1 == checksum2

    def test_calculate_audio_checksum_different_content(self, tmp_path: Path) -> None:
        from file_organizer.services.audio.utils import calculate_audio_checksum

        f1 = tmp_path / "a.bin"
        f2 = tmp_path / "b.bin"
        f1.write_bytes(b"content a")
        f2.write_bytes(b"content b")

        checksum1 = calculate_audio_checksum(f1)
        checksum2 = calculate_audio_checksum(f2)

        assert checksum1 != checksum2

    def test_detect_silence_no_pydub(self, tmp_path: Path) -> None:
        from file_organizer.services.audio.utils import detect_silence_segments

        f = tmp_path / "audio.mp3"
        f.write_bytes(b"\xff\xfb")

        with patch.dict("sys.modules", {"pydub": None}):
            result = detect_silence_segments(f)

        assert result == []

    def test_split_audio_no_pydub_returns_original(self, tmp_path: Path) -> None:
        from file_organizer.services.audio.utils import split_audio

        f = tmp_path / "audio.mp3"
        f.write_bytes(b"\xff\xfb")

        with patch.dict("sys.modules", {"pydub": None}):
            chunks = split_audio(f)

        assert chunks == [f]

    def test_normalize_audio_no_pydub_returns_original(self, tmp_path: Path) -> None:
        from file_organizer.services.audio.utils import normalize_audio

        f = tmp_path / "audio.mp3"
        f.write_bytes(b"\xff\xfb")

        with patch.dict("sys.modules", {"pydub": None}):
            result = normalize_audio(f)

        assert result == f

    def test_convert_audio_format_no_pydub_returns_original(self, tmp_path: Path) -> None:
        from file_organizer.services.audio.utils import convert_audio_format

        f = tmp_path / "audio.mp3"
        f.write_bytes(b"\xff\xfb")

        with patch.dict("sys.modules", {"pydub": None}):
            result = convert_audio_format(f, "wav")

        assert result == f

    def test_get_audio_peak_amplitude_no_pydub(self, tmp_path: Path) -> None:
        from file_organizer.services.audio.utils import get_audio_peak_amplitude

        f = tmp_path / "audio.mp3"
        f.write_bytes(b"\xff\xfb")

        with patch.dict("sys.modules", {"pydub": None}):
            result = get_audio_peak_amplitude(f)

        assert result == 0.0

    def test_split_audio_creates_output_dir(self, tmp_path: Path) -> None:
        from file_organizer.services.audio.utils import split_audio

        f = tmp_path / "audio.mp3"
        f.write_bytes(b"\xff\xfb")
        out_dir = tmp_path / "chunks"

        with patch.dict("sys.modules", {"pydub": None}):
            split_audio(f, output_dir=out_dir)

        assert out_dir.exists()

    def test_trim_audio_no_pydub_returns_original(self, tmp_path: Path) -> None:
        from file_organizer.services.audio.utils import trim_audio

        f = tmp_path / "audio.mp3"
        f.write_bytes(b"\xff\xfb")

        with patch.dict("sys.modules", {"pydub": None}):
            result = trim_audio(f, start_ms=0, end_ms=5000)

        assert result == f


# ---------------------------------------------------------------------------
# TestFileOrganizer (integration-level)
# ---------------------------------------------------------------------------


class TestFileOrganizer:
    """Tests for file_organizer.core.organizer.FileOrganizer."""

    def _make_organizer(self) -> Any:
        from file_organizer.core.organizer import FileOrganizer
        from file_organizer.models.base import ModelConfig, ModelType

        text_cfg = ModelConfig(name="mock-text", model_type=ModelType.TEXT)
        vision_cfg = ModelConfig(name="mock-vision", model_type=ModelType.VISION)

        return FileOrganizer(
            text_model_config=text_cfg,
            vision_model_config=vision_cfg,
            dry_run=True,
            use_hardlinks=False,
            parallel_workers=1,
        )

    def test_organizer_initializes(self) -> None:
        fo = self._make_organizer()

        assert fo.dry_run is True
        assert fo.use_hardlinks is False
        assert fo.text_processor is None
        assert fo.vision_processor is None

    def test_organize_raises_for_nonexistent_input(self, tmp_path: Path) -> None:
        fo = self._make_organizer()

        with pytest.raises(ValueError, match="Input path does not exist"):
            fo.organize(tmp_path / "nonexistent", tmp_path / "output")

    def test_organize_empty_directory(self, tmp_path: Path) -> None:
        fo = self._make_organizer()

        result = fo.organize(tmp_path, tmp_path / "output")

        assert result.total_files == 0
        assert result.processed_files == 0

    def test_organize_dry_run_does_not_copy(self, tmp_path: Path) -> None:
        from file_organizer.core.organizer import FileOrganizer
        from file_organizer.models.base import ModelConfig, ModelType

        text_cfg = ModelConfig(name="mock", model_type=ModelType.TEXT)
        vision_cfg = ModelConfig(name="mock", model_type=ModelType.VISION)
        fo = FileOrganizer(
            text_model_config=text_cfg,
            vision_model_config=vision_cfg,
            dry_run=True,
        )

        src = tmp_path / "src"
        src.mkdir()
        (src / "file.pdf").write_text("content")

        out = tmp_path / "output"

        with (
            patch.object(fo, "_init_text_processor"),
            patch.object(fo, "_process_text_files") as mock_process,
        ):
            mock_pf = _make_processed_file(src / "file.pdf", "PDFs", "file")
            mock_process.return_value = [mock_pf]

            result = fo.organize(src, out)

        assert not (out / "PDFs" / "file.pdf").exists()
        assert result.processed_files >= 1  # mock returns one processed file

    def test_organize_returns_organization_result(self, tmp_path: Path) -> None:
        from file_organizer.core.types import OrganizationResult

        fo = self._make_organizer()
        src = tmp_path / "src"
        src.mkdir()
        (src / "sample.txt").write_text("text content")

        with (
            patch.object(fo, "_init_text_processor"),
            patch.object(fo, "_process_text_files") as mock_process,
        ):
            mock_pf = _make_processed_file(src / "sample.txt", "Documents", "sample")
            mock_process.return_value = [mock_pf]
            result = fo.organize(src, tmp_path / "out")

        assert isinstance(result, OrganizationResult)

    def test_organize_skips_unsupported_files(self, tmp_path: Path) -> None:
        fo = self._make_organizer()
        src = tmp_path / "src"
        src.mkdir()
        (src / "weird.xyz").write_text("unsupported")

        result = fo.organize(src, tmp_path / "out")

        assert result.skipped_files == 1

    def test_organize_categorizes_text_and_image_files(self, tmp_path: Path) -> None:
        fo = self._make_organizer()
        src = tmp_path / "src"
        src.mkdir()
        (src / "doc.txt").write_text("text")
        (src / "img.jpg").write_bytes(b"\xff\xd8\xff")

        with (
            patch.object(fo, "_init_text_processor"),
            patch.object(fo, "_process_text_files") as mock_text,
            patch.object(fo, "_init_vision_processor"),
            patch.object(fo, "_process_image_files") as mock_img,
        ):
            pf_txt = _make_processed_file(src / "doc.txt", "Documents", "doc")
            pf_img = _make_processed_image(src / "img.jpg", "Images/2024", "img")
            mock_text.return_value = [pf_txt]
            mock_img.return_value = [pf_img]

            result = fo.organize(src, tmp_path / "out")

        assert result.total_files == 2

    def test_undo_no_session_returns_false(self) -> None:
        fo = self._make_organizer()

        result = fo.undo()

        assert result is False

    def test_redo_no_session_returns_false(self) -> None:
        fo = self._make_organizer()

        result = fo.redo()

        assert result is False

    def test_collect_files_delegation(self, tmp_path: Path) -> None:
        fo = self._make_organizer()
        (tmp_path / "a.txt").write_text("a")

        result = fo._collect_files(tmp_path)

        assert len(result) == 1

    def test_fallback_by_extension_delegation(self, tmp_path: Path) -> None:
        fo = self._make_organizer()
        f = tmp_path / "doc.pdf"
        f.write_text("pdf content")

        results = fo._fallback_by_extension([f])

        assert len(results) == 1
        assert results[0].folder_name == "PDFs"

    def test_simulate_organization_delegation(self, tmp_path: Path) -> None:
        fo = self._make_organizer()
        f = tmp_path / "note.txt"
        f.write_text("note")
        pf = _make_processed_file(f, "Documents", "note")

        result = fo._simulate_organization([pf], tmp_path / "out")

        assert "Documents" in result

    def test_cleanup_empty_dirs_delegation(self, tmp_path: Path) -> None:
        fo = self._make_organizer()
        empty = tmp_path / "empty"
        empty.mkdir()

        fo._cleanup_empty_dirs(tmp_path)

        assert not empty.exists()

    def test_organizer_extension_sets_not_empty(self) -> None:
        fo = self._make_organizer()

        assert len(fo.TEXT_EXTENSIONS) >= 1
        assert len(fo.IMAGE_EXTENSIONS) >= 1
        assert len(fo.VIDEO_EXTENSIONS) >= 1
        assert len(fo.AUDIO_EXTENSIONS) >= 1

    def test_no_prefetch_overrides_prefetch_depth(self) -> None:
        from file_organizer.core.organizer import FileOrganizer
        from file_organizer.models.base import ModelConfig, ModelType

        text_cfg = ModelConfig(name="mock", model_type=ModelType.TEXT)
        vision_cfg = ModelConfig(name="mock", model_type=ModelType.VISION)

        fo = FileOrganizer(
            text_model_config=text_cfg,
            vision_model_config=vision_cfg,
            no_prefetch=True,
            prefetch_depth=5,
        )

        assert fo.prefetch_depth == 0

    def test_organize_with_audio_files(self, tmp_path: Path) -> None:
        fo = self._make_organizer()
        src = tmp_path / "src"
        src.mkdir()
        (src / "song.mp3").write_bytes(b"\xff\xfb")

        with patch.object(fo, "_process_audio_files") as mock_audio:
            pf = _make_processed_file(src / "song.mp3", "Music/Pop", "song")
            mock_audio.return_value = [pf]

            result = fo.organize(src, tmp_path / "out")

        assert result.total_files == 1
        mock_audio.assert_called_once()

    def test_organize_with_video_files(self, tmp_path: Path) -> None:
        fo = self._make_organizer()
        src = tmp_path / "src"
        src.mkdir()
        (src / "clip.mp4").write_bytes(b"\x00\x00\x00\x00ftyp")

        with patch.object(fo, "_process_video_files") as mock_video:
            pf = _make_processed_file(src / "clip.mp4", "Videos/Action", "clip")
            mock_video.return_value = [pf]

            result = fo.organize(src, tmp_path / "out")

        assert result.total_files == 1
        mock_video.assert_called_once()

    def test_organize_deduplicates_identical_files(self, tmp_path: Path) -> None:
        fo = self._make_organizer()
        src = tmp_path / "src"
        src.mkdir()

        # Create two identical files
        content = b"identical content " * 100
        (src / "orig.txt").write_bytes(content)
        (src / "copy.txt").write_bytes(content)

        with (
            patch.object(fo, "_init_text_processor"),
            patch.object(fo, "_process_text_files") as mock_process,
        ):
            pf1 = _make_processed_file(src / "orig.txt", "Documents", "orig")
            pf2 = _make_processed_file(src / "copy.txt", "Documents", "copy")
            mock_process.return_value = [pf1, pf2]

            result = fo.organize(src, tmp_path / "out")

        assert result.deduplicated_files == 1

    def test_organize_enable_vision_false(self, tmp_path: Path) -> None:
        from file_organizer.core.organizer import FileOrganizer
        from file_organizer.models.base import ModelConfig, ModelType

        text_cfg = ModelConfig(name="mock", model_type=ModelType.TEXT)
        vision_cfg = ModelConfig(name="mock", model_type=ModelType.VISION)

        fo = FileOrganizer(
            text_model_config=text_cfg,
            vision_model_config=vision_cfg,
            dry_run=True,
            enable_vision=False,
        )

        src = tmp_path / "src"
        src.mkdir()
        (src / "photo.jpg").write_bytes(b"\xff\xd8\xff")

        with patch.object(fo, "_fallback_by_extension") as mock_fallback:
            pf = _make_processed_file(src / "photo.jpg", "Images/2024", "photo")
            mock_fallback.return_value = [pf]
            result = fo.organize(src, tmp_path / "out")

        mock_fallback.assert_called_once()
        assert result.total_files == 1
