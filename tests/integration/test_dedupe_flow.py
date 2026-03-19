"""Integration tests for deduplication flow.

These tests verify that the deduplication router correctly identifies and removes duplicate files
while preserving the original file content when appropriate. The underlying model calls are
mocked to provide deterministic responses.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.core.organizer import FileOrganizer
from file_organizer.services.text_processor import ProcessedFile


@pytest.fixture
def source_dir(tmp_path: Path) -> Path:
    """Create a source directory with duplicate and unique files."""
    src = tmp_path / "source"
    src.mkdir()
    # Duplicate files (same content)
    (src / "doc1.txt").write_text("Duplicate content", encoding="utf-8")
    (src / "doc2.txt").write_text("Duplicate content", encoding="utf-8")
    # Unique file
    (src / "unique.txt").write_text("Unique content", encoding="utf-8")
    return src


@pytest.fixture
def output_dir(tmp_path: Path) -> Path:
    out = tmp_path / "organized"
    out.mkdir()
    return out


@pytest.mark.integration
@patch("file_organizer.core.organizer.TextProcessor")
@patch("file_organizer.core.organizer.VisionProcessor")
def test_dedupe_flow_copy(mock_vision_cls, mock_text_cls, source_dir, output_dir):
    """Test deduplication with copy mode.

    The mock TextProcessor returns a ProcessedFile that maps all files to the same
    folder "deduped" but preserves the original filename. The organizer should
    copy files and remove duplicates.
    """
    mock_processor = MagicMock()
    mock_text_cls.return_value = mock_processor

    def mock_process_file(file_path: Path) -> ProcessedFile:
        # All files go to "deduped" folder; filename unchanged
        return ProcessedFile(
            file_path=file_path,
            description="mock desc",
            folder_name="deduped",
            filename=file_path.stem,
        )

    mock_processor.process_file.side_effect = mock_process_file

    organizer = FileOrganizer(dry_run=False, use_hardlinks=False)
    result = organizer.organize(source_dir, output_dir)

    # Expect three files processed, one duplicate removed
    assert result.total_files == 3
    assert result.processed_files == 2  # one duplicate skipped
    assert result.failed_files == 0
    deduped_dir = output_dir / "deduped"
    assert deduped_dir.is_dir()
    # Only two files should exist after deduplication
    files = list(deduped_dir.iterdir())
    assert len(files) == 2
    names = {f.name for f in files}
    assert "doc1.txt" in names or "doc2.txt" in names
    assert "unique.txt" in names

    # Original source files remain (copy mode)
    assert (source_dir / "doc1.txt").exists()
    assert (source_dir / "doc2.txt").exists()
    assert (source_dir / "unique.txt").exists()


@pytest.mark.integration
@patch("file_organizer.core.organizer.TextProcessor")
@patch("file_organizer.core.organizer.VisionProcessor")
def test_dedupe_flow_hardlink(mock_vision_cls, mock_text_cls, source_dir, output_dir):
    """Test deduplication with hardlink mode.

    In hardlink mode the organizer should create hardlinks for unique files and
    skip creating a hardlink for the duplicate.
    """
    mock_processor = MagicMock()
    mock_text_cls.return_value = mock_processor

    def mock_process_file(file_path: Path) -> ProcessedFile:
        return ProcessedFile(
            file_path=file_path,
            description="mock desc",
            folder_name="deduped_hl",
            filename=file_path.stem,
        )

    mock_processor.process_file.side_effect = mock_process_file

    organizer = FileOrganizer(dry_run=False, use_hardlinks=True)
    result = organizer.organize(source_dir, output_dir)

    assert result.processed_files == 2
    deduped_dir = output_dir / "deduped_hl"
    assert deduped_dir.is_dir()
    files = list(deduped_dir.iterdir())
    assert len(files) == 2
    # Verify that the hardlink for the kept file shares inode with source
    retained_name = "doc1.txt" if (deduped_dir / "doc1.txt").exists() else "doc2.txt"
    src_stat = os.stat(source_dir / retained_name)
    dst_stat = os.stat(deduped_dir / retained_name)
    assert src_stat.st_ino == dst_stat.st_ino
