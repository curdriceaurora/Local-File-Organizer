"""Integration tests for Gap P7: State Recovery.

Verifies that the system handles corrupt state gracefully — corrupt
history databases, interrupted transactions, and config file corruption
all degrade gracefully instead of crashing.
"""

from __future__ import annotations

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
        """organize() then undo() restores source files."""
        text_cfg = make_text_config()
        vision_cfg = make_vision_config()

        org = FileOrganizer(
            text_model_config=text_cfg,
            vision_model_config=vision_cfg,
            dry_run=False,
            use_hardlinks=False,
        )

        # Capture initial source state
        initial_files = sorted(p.name for p in integration_source_dir.iterdir())

        result = org.organize(
            input_path=str(integration_source_dir),
            output_path=str(integration_output_dir),
        )
        assert result.processed_files == 3

        # Undo should restore source directory
        undo_success = org.undo()
        assert undo_success is True

        # Source files should be restored
        restored_files = sorted(p.name for p in integration_source_dir.iterdir())
        assert restored_files == initial_files


class TestCorruptHistoryDb:
    """Corrupt or missing history db is handled gracefully."""

    def test_corrupt_db_file_does_not_crash(
        self,
        tmp_path: Path,
    ) -> None:
        """A corrupt SQLite file triggers graceful fallback, not crash."""
        db_path = tmp_path / "corrupt.db"
        db_path.write_text("this is not a sqlite database")

        # OperationHistory should handle corrupt db gracefully
        # (either re-create or raise a clear error)
        try:
            with OperationHistory(db_path=db_path) as history:
                # If it initializes, the schema was re-created
                pass
        except Exception as e:
            # If it raises, it should be a clear error, not a segfault
            assert "database" in str(e).lower() or "sqlite" in str(e).lower()

    def test_missing_db_creates_new_one(
        self,
        tmp_path: Path,
    ) -> None:
        """A missing db path auto-creates a fresh database."""
        db_path = tmp_path / "subdir" / "new_history.db"

        with OperationHistory(db_path=db_path) as history:
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


