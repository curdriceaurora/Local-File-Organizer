"""Integration tests for Text Workflows.

Tests the end-to-end flow of organizing text files using the FileOrganizer,
but performing actual file system operations (dry_run=False), while mocking
the underlying AI responses to avoid slow external dependencies.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.core.organizer import FileOrganizer
from file_organizer.services.text_processor import ProcessedFile


@pytest.fixture
def source_dir(tmp_path: Path) -> Path:
    """Create a source directory with sample text files."""
    src = tmp_path / "source"
    src.mkdir()

    # Create a simple txt file
    (src / "report.txt").write_text("Quarterly earnings report data...", encoding="utf-8")

    # Create fake pdf, docx, csv
    (src / "invoice.pdf").write_bytes(b"%PDF-1.4 mock pdf content")
    (src / "meeting.docx").write_text("Mock docx XML content...", encoding="utf-8")
    (src / "data.csv").write_text("id,name\n1,test", encoding="utf-8")

    return src


@pytest.fixture
def output_dir(tmp_path: Path) -> Path:
    """Create a temporary output directory."""
    out = tmp_path / "organized"
    out.mkdir()
    return out


@pytest.mark.integration
class TestTextWorkflowsIntegration:
    """Integration tests for text file organization workflow."""

    @patch("file_organizer.core.organizer.TextProcessor")
    @patch("file_organizer.core.organizer.VisionProcessor")
    def test_end_to_end_text_organization_copy(
        self, mock_vision_cls, mock_text_cls, source_dir, output_dir
    ):
        """Test organizing text files with physical copying."""
        # Setup mock TextProcessor to return deterministic ProcessedFile objects
        mock_processor = MagicMock()
        mock_text_cls.return_value = mock_processor

        # When process_file is called, return a mapped ProcessedFile
        def mock_process_file(file_path: Path) -> ProcessedFile:
            name = file_path.stem
            return ProcessedFile(
                file_path=file_path,
                description=f"Mock description for {name}",
                folder_name="financials" if name in ("report", "invoice") else "documents",
                filename=f"processed_{name}",
            )

        mock_processor.process_file.side_effect = mock_process_file

        # Run organizer
        organizer = FileOrganizer(dry_run=False, use_hardlinks=False)
        result = organizer.organize(source_dir, output_dir)

        # Verify the result structure
        assert result.total_files == 4
        assert result.processed_files == 4
        assert result.failed_files == 0
        assert "financials" in result.organized_structure
        assert "documents" in result.organized_structure

        # Verify actual files were copied
        financials_dir = output_dir / "financials"
        documents_dir = output_dir / "documents"

        assert financials_dir.exists() and financials_dir.is_dir()
        assert documents_dir.exists() and documents_dir.is_dir()

        # Check specific files
        assert (financials_dir / "processed_report.txt").exists()
        assert (financials_dir / "processed_invoice.pdf").exists()
        assert (documents_dir / "processed_meeting.docx").exists()
        assert (documents_dir / "processed_data.csv").exists()

        # Verify original files still exist (copy mode)
        assert (source_dir / "report.txt").exists()

    @pytest.mark.skipif(
        sys.platform == "win32", reason="Hardlinks require admin privileges on Windows"
    )
    @patch("file_organizer.core.organizer.TextProcessor")
    @patch("file_organizer.core.organizer.VisionProcessor")
    def test_end_to_end_text_organization_hardlink(
        self, mock_vision_cls, mock_text_cls, source_dir, output_dir
    ):
        """Test organizing text files with hardlinks."""
        mock_processor = MagicMock()
        mock_text_cls.return_value = mock_processor

        def mock_process_file(file_path: Path) -> ProcessedFile:
            return ProcessedFile(
                file_path=file_path,
                description="desc",
                folder_name="auto_sorted",
                filename=f"linked_{file_path.stem}",
            )

        mock_processor.process_file.side_effect = mock_process_file

        organizer = FileOrganizer(dry_run=False, use_hardlinks=True)
        result = organizer.organize(source_dir, output_dir)

        assert result.processed_files == 4

        auto_sorted_dir = output_dir / "auto_sorted"
        assert auto_sorted_dir.exists()

        # Check hardlinks share the same inode
        src_stat = os.stat(source_dir / "report.txt")
        dst_stat = os.stat(auto_sorted_dir / "linked_report.txt")
        assert src_stat.st_ino == dst_stat.st_ino

    @patch("file_organizer.core.organizer.TextProcessor")
    @patch("file_organizer.core.organizer.VisionProcessor")
    def test_end_to_end_collision_handling(
        self, mock_vision_cls, mock_text_cls, source_dir, output_dir
    ):
        """Test the workflow correctly handles filename collisions during live run."""
        mock_processor = MagicMock()
        mock_text_cls.return_value = mock_processor

        # Force a collision by mapping everything to the exact same folder and filename
        # but with their original extension preserved by the organizer
        def mock_process_file_collision(file_path: Path) -> ProcessedFile:
            return ProcessedFile(
                file_path=file_path,
                description="desc",
                folder_name="collide_folder",
                filename="duplicate_name",
            )

        mock_processor.process_file.side_effect = mock_process_file_collision

        # Create two files with the same extension to force an actual collision
        (source_dir / "extra1.txt").write_text("Hello")
        (source_dir / "extra2.txt").write_text("World")

        # We only want to test the two text files to guarantee a collision
        for f in source_dir.iterdir():
            if f.name not in ["extra1.txt", "extra2.txt"]:
                f.unlink()

        organizer = FileOrganizer(dry_run=False, use_hardlinks=False)
        # Setting skip_existing=False to force it to use incrementing suffix
        result = organizer.organize(source_dir, output_dir, skip_existing=False)
        assert result.processed_files == 2

        collide_dir = output_dir / "collide_folder"
        assert collide_dir.exists()

        files = list(collide_dir.iterdir())
        assert len(files) == 2
        names = {f.name for f in files}

        assert "duplicate_name.txt" in names
        assert "duplicate_name_1.txt" in names
