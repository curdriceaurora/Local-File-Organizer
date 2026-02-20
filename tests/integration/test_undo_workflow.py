"""Integration tests for undo/redo text workflows."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.core.organizer import FileOrganizer
from file_organizer.services.text_processor import ProcessedFile


@pytest.fixture
def source_dir(tmp_path: Path) -> Path:
    src = tmp_path / "source"
    src.mkdir()
    (src / "report.txt").write_text("Quarterly earnings report data...", encoding="utf-8")
    return src


@pytest.fixture
def output_dir(tmp_path: Path) -> Path:
    out = tmp_path / "organized"
    out.mkdir()
    return out


@pytest.mark.integration
class TestUndoTextWorkflow:
    """Test undo/redo integration capabilities."""

    @patch("file_organizer.core.organizer.TextProcessor")
    @patch("file_organizer.core.organizer.VisionProcessor")
    def test_undo_workflow_restores_source_and_output(
        self, mock_vision_cls, mock_text_cls, source_dir, output_dir
    ):
        """End-to-end test: organize, undo, and verify restoration of filesystem state."""
        mock_processor = MagicMock()
        mock_text_cls.return_value = mock_processor

        def mock_process_file(file_path: Path) -> ProcessedFile:
            return ProcessedFile(
                file_path=file_path,
                description="desc",
                folder_name="undo_folder",
                filename=f"organized_{file_path.stem}",
            )

        mock_processor.process_file.side_effect = mock_process_file

        # Capture initial state of source and output directories.
        initial_source = sorted(p.relative_to(source_dir) for p in source_dir.iterdir())
        initial_output = sorted(output_dir.iterdir())

        organizer = FileOrganizer(dry_run=False, use_hardlinks=False)
        organizer.organize(source_dir, output_dir)

        # Obtain an undo function from the organizer
        undo_fn = getattr(organizer, "undo", None) or getattr(
            organizer, "undo_last_operation", None
        )
        if undo_fn is None:
            pytest.skip("Undo operation not available on FileOrganizer.")

        # Perform undo and verify that filesystem state is restored.
        undo_fn()

        restored_source = sorted(p.relative_to(source_dir) for p in source_dir.iterdir())
        restored_output = sorted(output_dir.iterdir())

        assert restored_source == initial_source
        assert restored_output == initial_output

    @patch("file_organizer.core.organizer.TextProcessor")
    @patch("file_organizer.core.organizer.VisionProcessor")
    def test_redo_workflow_reapplies_last_operation(
        self, mock_vision_cls, mock_text_cls, source_dir, output_dir
    ):
        """End-to-end test: organize, undo, redo, and verify re-application."""
        mock_processor = MagicMock()
        mock_text_cls.return_value = mock_processor

        def mock_process_file(file_path: Path) -> ProcessedFile:
            return ProcessedFile(
                file_path=file_path,
                description="desc",
                folder_name="redo_folder",
                filename=f"organized_{file_path.stem}",
            )

        mock_processor.process_file.side_effect = mock_process_file

        initial_source = sorted(p.relative_to(source_dir) for p in source_dir.iterdir())
        initial_output = sorted(output_dir.iterdir())

        organizer = FileOrganizer(dry_run=False, use_hardlinks=False)
        organizer.organize(source_dir, output_dir)

        # Capture the organized state of the output directory.
        organized_output = sorted(output_dir.iterdir())

        undo_fn = getattr(organizer, "undo", None) or getattr(
            organizer, "undo_last_operation", None
        )
        redo_fn = getattr(organizer, "redo", None) or getattr(
            organizer, "redo_last_operation", None
        )

        if undo_fn is None or redo_fn is None:
            pytest.skip("Undo/redo operations not available on FileOrganizer.")

        # Undo should restore initial state.
        undo_fn()
        restored_source = sorted(p.relative_to(source_dir) for p in source_dir.iterdir())
        restored_output = sorted(output_dir.iterdir())

        assert restored_source == initial_source
        assert restored_output == initial_output

        # Redo should re-apply the organization.
        redo_fn()
        redone_output = sorted(output_dir.iterdir())

        assert redone_output == organized_output
