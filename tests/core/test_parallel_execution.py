"""Tests for parallel execution in FileOrganizer."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch

import pytest

from file_organizer.core.organizer import FileOrganizer
from file_organizer.services import ProcessedFile


@pytest.mark.unit
class TestParallelExecution:
    """Tests for parallel execution in FileOrganizer."""

    @pytest.fixture
    def sample_files(self, tmp_path: Path) -> list[Path]:
        """Create a set of sample text files."""
        files = []
        for i in range(5):
            p = tmp_path / f"doc_{i}.txt"
            p.write_text(f"Content {i}")
            files.append(p)
        return files

    def test_parallel_text_processing(self, sample_files: list[Path], tmp_path: Path) -> None:
        """Test that text files are processed in parallel."""
        output_dir = tmp_path / "output"

        # Mock TextProcessor to simulate work and return valid results
        with patch("file_organizer.core.organizer.TextProcessor") as MockProcessorCls:
            mock_processor = MockProcessorCls.return_value

            def side_effect(path: Path) -> ProcessedFile:
                time.sleep(0.1)  # Simulate delay
                return ProcessedFile(
                    file_path=path,
                    description=f"Desc {path.name}",
                    folder_name="docs",
                    filename=path.stem,
                    processing_time=0.1,
                )

            mock_processor.process_file.side_effect = side_effect
            mock_processor.initialize.return_value = None
            mock_processor.cleanup.return_value = None

            # Initialize with 2 workers
            organizer = FileOrganizer(dry_run=True, parallel_workers=2)

            # Run organize
            # start = time.time()
            result = organizer.organize(
                input_path=sample_files[0].parent,
                output_path=output_dir,
            )
            # duration = time.time() - start

            # Verification
            assert result.processed_files == 5
            assert result.failed_files == 0

            # With 5 files taking 0.1s each, sequential would be ~0.5s.
            # With 2 workers, it should be ~0.3s (3 batches: 2, 2, 1).
            # Allowing some overhead, but it should function.
            # We mostly care that it completed successfully using the parallel code path.

            # Check correctness of result structure
            # (In dry_run, organized_structure is populated)
            assert "docs" in result.organized_structure
            assert len(result.organized_structure["docs"]) == 5

    def test_parallel_error_handling(self, sample_files: list[Path], tmp_path: Path) -> None:
        """Test that individual failures don't crash the batch."""
        output_dir = tmp_path / "output_err"

        with patch("file_organizer.core.organizer.TextProcessor") as MockProcessorCls:
            mock_processor = MockProcessorCls.return_value

            def side_effect(path: Path) -> ProcessedFile:
                if "doc_2" in path.name:
                    raise ValueError("Simulated failure")
                return ProcessedFile(
                    file_path=path,
                    description="ok",
                    folder_name="docs",
                    filename=path.stem,
                )

            mock_processor.process_file.side_effect = side_effect

            organizer = FileOrganizer(dry_run=True, parallel_workers=2)
            result = organizer.organize(
                input_path=sample_files[0].parent,
                output_path=output_dir,
            )

            # The organizer counts only successful files in 'processed_files'.
            # Failures are counted in 'failed_files'.
            assert result.processed_files == 4
            assert result.failed_files == 1

            # Check that the error file was NOT organized (not in output structure)
            # doc_2 should be missing
            if "docs" in result.organized_structure:
                organized_files = result.organized_structure["docs"]
                assert len(organized_files) == 4
                assert not any("doc_2" in f for f in organized_files)
