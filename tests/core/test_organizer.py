"""Tests for file_organizer.core.organizer module.

Covers _collect_files, _organize_files, _simulate_organization,
and _process_text_files (with mocked AI). Image processing is deferred.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.services.text_processor import ProcessedFile


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_organizer(**kwargs):
    """Create a FileOrganizer with all AI models mocked out."""
    with patch("file_organizer.core.organizer.TextModel") as MockText, patch(
        "file_organizer.core.organizer.VisionModel"
    ) as MockVision:
        MockText.get_default_config.return_value = MagicMock()
        MockVision.get_default_config.return_value = MagicMock()

        from file_organizer.core.organizer import FileOrganizer

        return FileOrganizer(dry_run=True, **kwargs)


# ---------------------------------------------------------------------------
# _collect_files
# ---------------------------------------------------------------------------


class TestCollectFiles:
    """Tests for FileOrganizer._collect_files."""

    def test_collects_regular_files(self, tmp_path: Path) -> None:
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.pdf").write_text("b")

        organizer = _make_organizer()
        files = organizer._collect_files(tmp_path)
        assert len(files) == 2

    def test_skips_hidden_files(self, tmp_path: Path) -> None:
        (tmp_path / "visible.txt").write_text("v")
        (tmp_path / ".hidden").write_text("h")

        organizer = _make_organizer()
        files = organizer._collect_files(tmp_path)
        names = [f.name for f in files]
        assert "visible.txt" in names
        assert ".hidden" not in names

    def test_walks_subdirectories(self, tmp_path: Path) -> None:
        sub = tmp_path / "sub"
        sub.mkdir()
        (tmp_path / "top.txt").write_text("t")
        (sub / "deep.txt").write_text("d")

        organizer = _make_organizer()
        files = organizer._collect_files(tmp_path)
        assert len(files) == 2

    def test_single_file_input(self, tmp_path: Path) -> None:
        f = tmp_path / "single.txt"
        f.write_text("content")

        organizer = _make_organizer()
        files = organizer._collect_files(f)
        assert len(files) == 1
        assert files[0] == f

    def test_empty_directory(self, tmp_path: Path) -> None:
        organizer = _make_organizer()
        files = organizer._collect_files(tmp_path)
        assert files == []


# ---------------------------------------------------------------------------
# _simulate_organization
# ---------------------------------------------------------------------------


class TestSimulateOrganization:
    """Tests for FileOrganizer._simulate_organization."""

    def test_groups_by_folder(self, tmp_path: Path) -> None:
        processed = [
            ProcessedFile(
                file_path=tmp_path / "a.txt",
                description="desc",
                folder_name="science",
                filename="research_paper",
            ),
            ProcessedFile(
                file_path=tmp_path / "b.txt",
                description="desc",
                folder_name="science",
                filename="data_analysis",
            ),
            ProcessedFile(
                file_path=tmp_path / "c.txt",
                description="desc",
                folder_name="finance",
                filename="budget_report",
            ),
        ]

        organizer = _make_organizer()
        result = organizer._simulate_organization(processed, tmp_path / "output")

        assert "science" in result
        assert len(result["science"]) == 2
        assert "finance" in result
        assert len(result["finance"]) == 1

    def test_skips_errored_files(self, tmp_path: Path) -> None:
        processed = [
            ProcessedFile(
                file_path=tmp_path / "ok.txt",
                description="desc",
                folder_name="docs",
                filename="ok_file",
            ),
            ProcessedFile(
                file_path=tmp_path / "bad.txt",
                description="",
                folder_name="errors",
                filename="bad_file",
                error="Read failed",
            ),
        ]

        organizer = _make_organizer()
        result = organizer._simulate_organization(processed, tmp_path / "out")
        assert "docs" in result
        assert "errors" not in result

    def test_empty_list(self, tmp_path: Path) -> None:
        organizer = _make_organizer()
        result = organizer._simulate_organization([], tmp_path / "out")
        assert result == {}

    def test_preserves_extension(self, tmp_path: Path) -> None:
        processed = [
            ProcessedFile(
                file_path=tmp_path / "doc.pdf",
                description="desc",
                folder_name="papers",
                filename="my_paper",
            ),
        ]

        organizer = _make_organizer()
        result = organizer._simulate_organization(processed, tmp_path / "out")
        assert "my_paper.pdf" in result["papers"]


# ---------------------------------------------------------------------------
# _organize_files (copy / link mode)
# ---------------------------------------------------------------------------


class TestOrganizeFiles:
    """Tests for FileOrganizer._organize_files with actual file operations."""

    def test_copy_mode(self, tmp_path: Path) -> None:
        src = tmp_path / "source" / "doc.txt"
        src.parent.mkdir()
        src.write_text("content")
        out = tmp_path / "output"

        processed = [
            ProcessedFile(
                file_path=src,
                description="desc",
                folder_name="documents",
                filename="organized_doc",
            ),
        ]

        organizer = _make_organizer()
        organizer.dry_run = False
        organizer.use_hardlinks = False
        result = organizer._organize_files(processed, out, skip_existing=True)

        assert "documents" in result
        assert (out / "documents" / "organized_doc.txt").exists()

    def test_skip_existing(self, tmp_path: Path) -> None:
        src = tmp_path / "src.txt"
        src.write_text("source")
        out = tmp_path / "output"
        (out / "docs").mkdir(parents=True)
        (out / "docs" / "file.txt").write_text("existing")

        processed = [
            ProcessedFile(
                file_path=src,
                description="desc",
                folder_name="docs",
                filename="file",
            ),
        ]

        organizer = _make_organizer()
        organizer.dry_run = False
        organizer.use_hardlinks = False
        result = organizer._organize_files(processed, out, skip_existing=True)

        # Should skip — existing file untouched
        assert result == {}
        assert (out / "docs" / "file.txt").read_text() == "existing"

    def test_duplicate_naming(self, tmp_path: Path) -> None:
        src1 = tmp_path / "a.txt"
        src1.write_text("first")
        src2 = tmp_path / "b.txt"
        src2.write_text("second")
        out = tmp_path / "output"

        processed = [
            ProcessedFile(
                file_path=src1,
                description="d",
                folder_name="docs",
                filename="same",
            ),
            ProcessedFile(
                file_path=src2,
                description="d",
                folder_name="docs",
                filename="same",
            ),
        ]

        organizer = _make_organizer()
        organizer.dry_run = False
        organizer.use_hardlinks = False
        result = organizer._organize_files(processed, out, skip_existing=False)

        assert "docs" in result
        # Both should be organized (second gets _1 suffix)
        assert (out / "docs" / "same.txt").exists()
        assert (out / "docs" / "same_1.txt").exists()

    def test_errored_files_skipped(self, tmp_path: Path) -> None:
        out = tmp_path / "output"

        processed = [
            ProcessedFile(
                file_path=tmp_path / "err.txt",
                description="",
                folder_name="errors",
                filename="err",
                error="failed to read",
            ),
        ]

        organizer = _make_organizer()
        organizer.dry_run = False
        result = organizer._organize_files(processed, out, skip_existing=True)
        assert result == {}


# ---------------------------------------------------------------------------
# _process_text_files (mocked AI)
# ---------------------------------------------------------------------------


class TestProcessTextFiles:
    """Tests for _process_text_files with mocked TextProcessor."""

    def test_processes_files(self, tmp_path: Path) -> None:
        f1 = tmp_path / "a.txt"
        f1.write_text("Content for file A")

        organizer = _make_organizer()

        mock_processor = MagicMock()
        mock_processor.process_file.return_value = ProcessedFile(
            file_path=f1,
            description="About A",
            folder_name="category_a",
            filename="file_a",
        )
        organizer.text_processor = mock_processor

        # Mock the parallel processor to just call the function directly
        mock_parallel = MagicMock()
        result_item = MagicMock()
        result_item.success = True
        result_item.result = ProcessedFile(
            file_path=f1,
            description="About A",
            folder_name="category_a",
            filename="file_a",
        )
        result_item.path = f1
        result_item.error = None
        mock_parallel.process_batch_iter.return_value = [result_item]
        organizer.parallel_processor = mock_parallel

        results = organizer._process_text_files([f1])
        assert len(results) == 1
        assert results[0].folder_name == "category_a"
