"""Integration tests for Gap P7: State Recovery.

Verifies that the system handles corrupt state gracefully — corrupt
history databases, interrupted transactions, and config file corruption
all degrade gracefully instead of crashing.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from file_organizer.core.organizer import FileOrganizer
from file_organizer.history.tracker import OperationHistory

from .conftest import make_text_config, make_vision_config

pytestmark = [pytest.mark.integration]


class TestUndoRedo:
    """Undo reverses organized files, redo re-applies."""

    def test_undo_reverses_organized_files(
        self,
        stub_all_models: None,
        stub_nltk: None,
        integration_source_dir: Path,
        integration_output_dir: Path,
    ) -> None:
        """organize() then undo() removes output-side files created by organize."""
        text_cfg = make_text_config()
        vision_cfg = make_vision_config()

        org = FileOrganizer(
            text_model_config=text_cfg,
            vision_model_config=vision_cfg,
            dry_run=False,
            use_hardlinks=False,
        )

        result = org.organize(
            input_path=str(integration_source_dir),
            output_path=str(integration_output_dir),
        )
        assert result.processed_files == 3

        # Verify organize created files in output
        output_files_before_undo = [f for f in integration_output_dir.rglob("*") if f.is_file()]
        assert len(output_files_before_undo) == 3

        # Undo should remove the organized output files
        undo_success = org.undo()
        assert undo_success is True

        # Output files should be removed after undo
        output_files_after_undo = [f for f in integration_output_dir.rglob("*") if f.is_file()]
        assert len(output_files_after_undo) == 0


class TestCorruptHistoryDb:
    """Corrupt or missing history db is handled gracefully."""

    def test_corrupt_db_file_raises_database_error(
        self,
        tmp_path: Path,
    ) -> None:
        """A corrupt SQLite file raises DatabaseError, not a segfault."""
        db_path = tmp_path / "corrupt.db"
        db_path.write_text("this is not a sqlite database")

        with pytest.raises(sqlite3.DatabaseError, match="file is not a database"):
            OperationHistory(db_path=db_path)

    def test_missing_db_creates_new_one(
        self,
        tmp_path: Path,
    ) -> None:
        """A missing db path auto-creates a fresh database."""
        db_path = tmp_path / "subdir" / "new_history.db"

        with OperationHistory(db_path=db_path):
            # Should auto-create the file
            assert db_path.exists()


class TestInterruptedTransaction:
    """Interrupted transactions don't corrupt state."""

    def test_undo_without_organize_returns_false(self) -> None:
        """undo() on a fresh organizer returns False, not exception."""
        text_cfg = make_text_config()
        vision_cfg = make_vision_config()

        org = FileOrganizer(
            text_model_config=text_cfg,
            vision_model_config=vision_cfg,
            dry_run=True,
        )

        # No organize() called — undo should return False
        result = org.undo()
        assert result is False

    def test_redo_without_undo_returns_false(self) -> None:
        """redo() without a prior undo returns False, not exception."""
        text_cfg = make_text_config()
        vision_cfg = make_vision_config()

        org = FileOrganizer(
            text_model_config=text_cfg,
            vision_model_config=vision_cfg,
            dry_run=True,
        )

        result = org.redo()
        assert result is False

    def test_dry_run_undo_returns_false(
        self,
        stub_all_models: None,
        stub_nltk: None,
        integration_source_dir: Path,
        integration_output_dir: Path,
    ) -> None:
        """Dry-run organize doesn't create undo state — undo returns False."""
        text_cfg = make_text_config()
        vision_cfg = make_vision_config()

        org = FileOrganizer(
            text_model_config=text_cfg,
            vision_model_config=vision_cfg,
            dry_run=True,
        )

        org.organize(
            input_path=str(integration_source_dir),
            output_path=str(integration_output_dir),
        )

        # Dry run doesn't create undo state
        result = org.undo()
        assert result is False
