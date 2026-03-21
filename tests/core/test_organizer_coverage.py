"""Coverage tests for FileOrganizer — targets uncovered branches."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.core.organizer import FileOrganizer

pytestmark = pytest.mark.unit


@pytest.fixture()
def organizer():
    mock_text_cfg = MagicMock()
    mock_vision_cfg = MagicMock()
    with patch(
        "file_organizer.config.provider_env.get_model_configs",
        return_value=(mock_text_cfg, mock_vision_cfg),
    ):
        org = FileOrganizer(dry_run=True)
    return org


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------


class TestInit:
    def test_default_init(self, organizer):
        assert organizer.dry_run is True
        assert organizer._undo_manager is None


# ---------------------------------------------------------------------------
# _collect_files
# ---------------------------------------------------------------------------


class TestCollectFiles:
    def test_collect_single_file(self, organizer, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello")
        files = organizer._collect_files(f)
        assert len(files) == 1
        assert f in files

    def test_collect_directory(self, organizer, tmp_path):
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")
        (tmp_path / ".hidden").write_text("skip")
        files = organizer._collect_files(tmp_path)
        assert len(files) == 2  # hidden skipped
        assert tmp_path / "a.txt" in files
        assert tmp_path / "b.txt" in files

    def test_collect_empty(self, organizer, tmp_path):
        files = organizer._collect_files(tmp_path)
        assert len(files) == 0


# ---------------------------------------------------------------------------
# _simulate_organization
# ---------------------------------------------------------------------------


class TestSimulateOrganization:
    def test_simulates_grouping(self, organizer, tmp_path):
        mock_processed = MagicMock()
        mock_processed.error = None
        mock_processed.folder_name = "Documents"
        mock_processed.filename = "test"
        mock_processed.file_path = tmp_path / "test.txt"

        result = organizer._simulate_organization([mock_processed], tmp_path / "out")
        assert "Documents" in result
        assert "test.txt" in result["Documents"]

    def test_skips_errors(self, organizer, tmp_path):
        mock_processed = MagicMock()
        mock_processed.error = "some error"
        result = organizer._simulate_organization([mock_processed], tmp_path / "out")
        assert result == {}


# ---------------------------------------------------------------------------
# _cleanup_empty_dirs
# ---------------------------------------------------------------------------


class TestCleanupEmptyDirs:
    def test_removes_empty_subdirs(self, organizer, tmp_path):
        sub = tmp_path / "a" / "b"
        sub.mkdir(parents=True)
        organizer._cleanup_empty_dirs(tmp_path)
        assert not sub.exists()
        assert tmp_path.exists()  # root preserved

    def test_keeps_non_empty(self, organizer, tmp_path):
        sub = tmp_path / "a"
        sub.mkdir()
        (sub / "f.txt").write_text("data")
        organizer._cleanup_empty_dirs(tmp_path)
        assert sub.exists()


# ---------------------------------------------------------------------------
# undo / redo
# ---------------------------------------------------------------------------


class TestUndoRedo:
    def test_undo_no_manager(self, organizer):
        assert organizer.undo() is False

    def test_redo_no_manager(self, organizer):
        assert organizer.redo() is False

    def test_undo_no_transaction(self, organizer):
        organizer._undo_manager = MagicMock()
        organizer._last_transaction_id = None
        assert organizer.undo() is False

    def test_redo_no_transaction(self, organizer):
        organizer._undo_manager = MagicMock()
        organizer._last_transaction_id = None
        assert organizer.redo() is False

    def test_undo_calls_manager(self, organizer, tmp_path):
        organizer._undo_manager = MagicMock()
        organizer._undo_manager.undo_transaction.return_value = True
        organizer._last_transaction_id = "txn-1"
        organizer._last_output_path = tmp_path
        assert organizer.undo() is True
        organizer._undo_manager.undo_transaction.assert_called_once_with("txn-1")

    def test_redo_calls_manager(self, organizer):
        organizer._undo_manager = MagicMock()
        organizer._undo_manager.redo_transaction.return_value = True
        organizer._last_transaction_id = "txn-1"
        assert organizer.redo() is True
        organizer._undo_manager.redo_transaction.assert_called_once_with("txn-1")


# ---------------------------------------------------------------------------
# organize — validation
# ---------------------------------------------------------------------------


class TestOrganize:
    def test_nonexistent_input(self, organizer):
        with pytest.raises(ValueError, match="Input path does not exist"):
            organizer.organize(Path("nonexistent"), Path("output"))

    def test_empty_directory(self, organizer, tmp_path):
        result = organizer.organize(tmp_path, tmp_path / "output")
        assert result.total_files == 0
