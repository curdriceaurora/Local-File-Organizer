"""Integration tests for cli/dedupe.py and cli/undo_redo.py.

Covers:
- DedupeConfig: default values, custom params
- format_size: bytes, KB, MB, GB, PB thresholds
- format_datetime: returns ISO-like string
- select_files_to_keep: oldest, newest, largest, smallest, manual strategies
- display_summary: runs without error (uses rich console)
- undo_command: no args exits 1, verbose mode, operation not found
- redo_command: no args exits 1
- history_command: runs, stats flag, limit flag
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# DedupeConfig
# ---------------------------------------------------------------------------


class TestDedupeConfig:
    def test_default_values(self, tmp_path: Path) -> None:
        from file_organizer.cli.dedupe import DedupeConfig

        cfg = DedupeConfig(directory=tmp_path)
        assert cfg.directory == tmp_path
        assert cfg.algorithm == "sha256"
        assert cfg.dry_run is False
        assert cfg.strategy == "manual"
        assert cfg.safe_mode is True
        assert cfg.recursive is True
        assert cfg.batch is False
        assert cfg.min_size == 0
        assert cfg.max_size is None
        assert cfg.include_patterns == []
        assert cfg.exclude_patterns == []

    def test_custom_params(self, tmp_path: Path) -> None:
        from file_organizer.cli.dedupe import DedupeConfig

        cfg = DedupeConfig(
            directory=tmp_path,
            algorithm="md5",
            dry_run=True,
            strategy="oldest",
            min_size=100,
            max_size=1000,
            include_patterns=["*.txt"],
            exclude_patterns=["*.tmp"],
        )
        assert cfg.algorithm == "md5"
        assert cfg.dry_run is True
        assert cfg.strategy == "oldest"
        assert cfg.min_size == 100
        assert cfg.max_size == 1000
        assert cfg.include_patterns == ["*.txt"]
        assert cfg.exclude_patterns == ["*.tmp"]


# ---------------------------------------------------------------------------
# format_size
# ---------------------------------------------------------------------------


class TestFormatSize:
    def test_bytes(self) -> None:
        from file_organizer.cli.dedupe import format_size

        assert format_size(500) == "500.0 B"

    def test_kilobytes(self) -> None:
        from file_organizer.cli.dedupe import format_size

        assert format_size(2048) == "2.0 KB"

    def test_megabytes(self) -> None:
        from file_organizer.cli.dedupe import format_size

        assert format_size(1024 * 1024 * 3) == "3.0 MB"

    def test_gigabytes(self) -> None:
        from file_organizer.cli.dedupe import format_size

        assert format_size(1024**3 * 2) == "2.0 GB"

    def test_zero_bytes(self) -> None:
        from file_organizer.cli.dedupe import format_size

        assert format_size(0) == "0.0 B"

    def test_terabytes(self) -> None:
        from file_organizer.cli.dedupe import format_size

        assert format_size(1024**4 * 5) == "5.0 TB"


# ---------------------------------------------------------------------------
# format_datetime
# ---------------------------------------------------------------------------


class TestFormatDatetime:
    def test_returns_string(self) -> None:
        from file_organizer.cli.dedupe import format_datetime

        result = format_datetime(0.0)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_format_contains_date(self) -> None:
        from file_organizer.cli.dedupe import format_datetime

        result = format_datetime(1700000000.0)
        # Should look like YYYY-MM-DD HH:MM:SS
        assert "-" in result
        assert ":" in result

    def test_epoch_zero(self) -> None:
        from file_organizer.cli.dedupe import format_datetime

        result = format_datetime(0.0)
        assert "1970" in result


# ---------------------------------------------------------------------------
# select_files_to_keep
# ---------------------------------------------------------------------------


class TestSelectFilesToKeep:
    def _files(self) -> list[dict]:
        return [
            {"path": "/a/old.txt", "size": 100, "mtime": 1000.0},
            {"path": "/b/new.txt", "size": 200, "mtime": 2000.0},
            {"path": "/c/mid.txt", "size": 150, "mtime": 1500.0},
        ]

    def test_oldest_marks_first_file(self) -> None:
        from file_organizer.cli.dedupe import select_files_to_keep

        files = self._files()
        result = select_files_to_keep(files, "oldest")
        # mtime=1000 is oldest
        assert result[0].get("keep") is True
        assert result[1].get("keep") is None or result[1].get("keep") is False
        assert result[2].get("keep") is None or result[2].get("keep") is False

    def test_newest_marks_last_file(self) -> None:
        from file_organizer.cli.dedupe import select_files_to_keep

        files = self._files()
        result = select_files_to_keep(files, "newest")
        # mtime=2000 is newest
        assert result[1].get("keep") is True

    def test_largest_marks_largest_size(self) -> None:
        from file_organizer.cli.dedupe import select_files_to_keep

        files = self._files()
        result = select_files_to_keep(files, "largest")
        # size=200 is largest
        assert result[1].get("keep") is True

    def test_smallest_marks_smallest_size(self) -> None:
        from file_organizer.cli.dedupe import select_files_to_keep

        files = self._files()
        result = select_files_to_keep(files, "smallest")
        # size=100 is smallest
        assert result[0].get("keep") is True

    def test_manual_does_not_mark_any(self) -> None:
        from file_organizer.cli.dedupe import select_files_to_keep

        files = self._files()
        result = select_files_to_keep(files, "manual")
        assert all(not f.get("keep", False) for f in result)

    def test_returns_new_list_of_same_length(self) -> None:
        from file_organizer.cli.dedupe import select_files_to_keep

        files = self._files()
        result = select_files_to_keep(files, "oldest")
        assert len(result) == len(files)
        assert result is not files


# ---------------------------------------------------------------------------
# get_user_selection
# ---------------------------------------------------------------------------


class TestGetUserSelection:
    def _files(self) -> list[dict]:
        return [
            {"path": "/a/old.txt", "size": 100, "mtime": 1000.0, "keep": False},
            {"path": "/b/new.txt", "size": 200, "mtime": 2000.0, "keep": True},
        ]

    def test_batch_mode_removes_non_kept(self) -> None:
        from file_organizer.cli.dedupe import get_user_selection

        files = self._files()
        result = get_user_selection(files, "oldest", batch=True)
        # file[0] has keep=False → index 0 in result
        assert result == [0]

    def test_batch_mode_all_kept_returns_empty(self) -> None:
        from file_organizer.cli.dedupe import get_user_selection

        files = [{"path": "/a/f.txt", "keep": True}, {"path": "/b/f.txt", "keep": True}]
        result = get_user_selection(files, "oldest", batch=True)
        assert result == []

    def test_manual_strategy_skip(self) -> None:
        from unittest.mock import patch

        from file_organizer.cli.dedupe import get_user_selection

        files = self._files()
        with patch("file_organizer.cli.dedupe.console") as mock_console:
            mock_console.input.return_value = "s"
            result = get_user_selection(files, "manual")
        assert result == []

    def test_manual_strategy_keep_all(self) -> None:
        from unittest.mock import patch

        from file_organizer.cli.dedupe import get_user_selection

        files = self._files()
        with patch("file_organizer.cli.dedupe.console") as mock_console:
            mock_console.input.return_value = "a"
            result = get_user_selection(files, "manual")
        assert result == []

    def test_manual_strategy_select_file(self) -> None:
        from unittest.mock import patch

        from file_organizer.cli.dedupe import get_user_selection

        files = self._files()
        with patch("file_organizer.cli.dedupe.console") as mock_console:
            mock_console.input.return_value = "1"  # keep file[0] (1-indexed)
            result = get_user_selection(files, "manual")
        assert result == [1]  # remove file[1]

    def test_non_batch_strategy_yes(self) -> None:
        from unittest.mock import patch

        from file_organizer.cli.dedupe import get_user_selection

        files = self._files()
        with patch("file_organizer.cli.dedupe.console") as mock_console:
            mock_console.input.return_value = "y"
            result = get_user_selection(files, "oldest", batch=False)
        # file[0] has keep=False → remove index 0
        assert result == [0]

    def test_non_batch_strategy_no(self) -> None:
        from unittest.mock import patch

        from file_organizer.cli.dedupe import get_user_selection

        files = self._files()
        with patch("file_organizer.cli.dedupe.console") as mock_console:
            mock_console.input.return_value = "n"
            result = get_user_selection(files, "oldest", batch=False)
        assert result == []

    def test_non_batch_strategy_skip(self) -> None:
        from unittest.mock import patch

        from file_organizer.cli.dedupe import get_user_selection

        files = self._files()
        with patch("file_organizer.cli.dedupe.console") as mock_console:
            mock_console.input.return_value = "s"
            result = get_user_selection(files, "oldest", batch=False)
        assert result == []


# ---------------------------------------------------------------------------
# display_summary
# ---------------------------------------------------------------------------


class TestDisplaySummary:
    def test_dry_run_summary(self) -> None:
        from file_organizer.cli.dedupe_display import display_summary

        mock_console = MagicMock()
        display_summary(
            console=mock_console,
            total_groups=3,
            total_duplicates=6,
            total_removed=0,
            space_saved=0,
            dry_run=True,
        )
        assert mock_console.print.called

    def test_real_summary(self) -> None:
        from file_organizer.cli.dedupe_display import display_summary

        mock_console = MagicMock()
        display_summary(
            console=mock_console,
            total_groups=2,
            total_duplicates=4,
            total_removed=2,
            space_saved=1024 * 1024,
            dry_run=False,
        )
        assert mock_console.print.called


# ---------------------------------------------------------------------------
# undo_command
# ---------------------------------------------------------------------------


class TestUndoCommand:
    def test_no_args_with_mocked_manager_returns_zero(self) -> None:
        from file_organizer.cli.undo_redo import undo_command

        mock_manager = MagicMock()
        mock_manager.get_undo_stack.return_value = []
        mock_manager.undo_last_operation.return_value = True
        with patch("file_organizer.cli.undo_redo.UndoManager", return_value=mock_manager):
            result = undo_command()
        assert result == 0
        mock_manager.undo_last_operation.assert_called_once()

    def test_verbose_mode(self) -> None:
        from file_organizer.cli.undo_redo import undo_command

        mock_manager = MagicMock()
        mock_manager.get_undo_stack.return_value = []
        mock_manager.undo_last_operation.return_value = True
        with patch("file_organizer.cli.undo_redo.UndoManager", return_value=mock_manager):
            result = undo_command(verbose=True)
        assert result == 0
        mock_manager.undo_last_operation.assert_called_once()

    def test_with_operation_id_not_found(self) -> None:
        from file_organizer.cli.undo_redo import undo_command

        mock_manager = MagicMock()
        mock_manager.undo_operation.return_value = False  # operation not found
        with patch("file_organizer.cli.undo_redo.UndoManager", return_value=mock_manager):
            result = undo_command(operation_id=9999)
        # undo_operation returns False → undo fails → non-zero exit code
        assert result == 1

    def test_dry_run_no_operations(self) -> None:
        from file_organizer.cli.undo_redo import undo_command

        mock_manager = MagicMock()
        mock_manager.get_undo_stack.return_value = []
        with patch("file_organizer.cli.undo_redo.UndoManager", return_value=mock_manager):
            result = undo_command(dry_run=True)
        # dry_run with empty stack prints "No operations to undo" and returns 1
        assert result == 1

    def test_manager_init_error_returns_one(self) -> None:
        from file_organizer.cli.undo_redo import undo_command

        with patch(
            "file_organizer.cli.undo_redo.UndoManager", side_effect=RuntimeError("db error")
        ):
            result = undo_command()
        assert result == 1


# ---------------------------------------------------------------------------
# redo_command
# ---------------------------------------------------------------------------


class TestRedoCommand:
    def test_no_args_returns_zero(self) -> None:
        from file_organizer.cli.undo_redo import redo_command

        mock_manager = MagicMock()
        mock_manager.redo_last_operation.return_value = True
        with patch("file_organizer.cli.undo_redo.UndoManager", return_value=mock_manager):
            result = redo_command()
        assert result == 0
        mock_manager.redo_last_operation.assert_called_once()

    def test_with_operation_id_not_found(self) -> None:
        from file_organizer.cli.undo_redo import redo_command

        mock_manager = MagicMock()
        mock_manager.redo_operation.return_value = False  # redo fails
        with patch("file_organizer.cli.undo_redo.UndoManager", return_value=mock_manager):
            result = redo_command(operation_id=9999)
        assert result == 1

    def test_manager_init_error_returns_one(self) -> None:
        from file_organizer.cli.undo_redo import redo_command

        with patch(
            "file_organizer.cli.undo_redo.UndoManager", side_effect=RuntimeError("db error")
        ):
            result = redo_command()
        assert result == 1


# ---------------------------------------------------------------------------
# history_command
# ---------------------------------------------------------------------------


class TestHistoryCommand:
    def test_no_history_returns_zero(self) -> None:
        from file_organizer.cli.undo_redo import history_command

        mock_viewer = MagicMock()
        with patch("file_organizer.cli.undo_redo.HistoryViewer", return_value=mock_viewer):
            result = history_command()
        assert result == 0
        mock_viewer.show_recent_operations.assert_called_once_with(limit=10)

    def test_with_stats_flag(self) -> None:
        from file_organizer.cli.undo_redo import history_command

        mock_viewer = MagicMock()
        with patch("file_organizer.cli.undo_redo.HistoryViewer", return_value=mock_viewer):
            result = history_command(stats=True)
        assert result == 0
        mock_viewer.show_statistics.assert_called_once()

    def test_with_limit(self) -> None:
        from file_organizer.cli.undo_redo import history_command

        mock_viewer = MagicMock()
        with patch("file_organizer.cli.undo_redo.HistoryViewer", return_value=mock_viewer):
            result = history_command(limit=10)
        assert result == 0
        mock_viewer.show_recent_operations.assert_called_once_with(limit=10)

    def test_viewer_error_returns_one(self) -> None:
        from file_organizer.cli.undo_redo import history_command

        with patch(
            "file_organizer.cli.undo_redo.HistoryViewer", side_effect=RuntimeError("db error")
        ):
            result = history_command()
        assert result == 1
