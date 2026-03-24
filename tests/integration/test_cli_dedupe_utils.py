"""Integration tests for cli/dedupe.py pure helper functions.

Covers: format_size, format_datetime, DedupeConfig, select_files_to_keep
(all five strategies), display_summary (dry-run / live), display_duplicate_group,
and get_user_selection (batch mode for automatic strategies).
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.integration]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_file(path: str, size: int = 1024, mtime: float | None = None) -> dict:
    return {
        "path": path,
        "size": size,
        "mtime": mtime if mtime is not None else time.time(),
        "keep": False,
    }


# ---------------------------------------------------------------------------
# format_size
# ---------------------------------------------------------------------------


class TestFormatSize:
    def test_bytes_range(self) -> None:
        from file_organizer.cli.dedupe import format_size

        assert "B" in format_size(0)
        assert "B" in format_size(500)

    def test_kb_range(self) -> None:
        from file_organizer.cli.dedupe import format_size

        result = format_size(2048)
        assert "KB" in result

    def test_mb_range(self) -> None:
        from file_organizer.cli.dedupe import format_size

        result = format_size(2 * 1024 * 1024)
        assert "MB" in result

    def test_gb_range(self) -> None:
        from file_organizer.cli.dedupe import format_size

        result = format_size(3 * 1024 * 1024 * 1024)
        assert "GB" in result

    def test_tb_range(self) -> None:
        from file_organizer.cli.dedupe import format_size

        result = format_size(2 * 1024**4)
        assert "TB" in result

    def test_pb_fallback(self) -> None:
        from file_organizer.cli.dedupe import format_size

        result = format_size(2 * 1024**5)
        assert "PB" in result

    def test_exact_kb(self) -> None:
        from file_organizer.cli.dedupe import format_size

        result = format_size(1024)
        assert "1.0 KB" in result


# ---------------------------------------------------------------------------
# format_datetime
# ---------------------------------------------------------------------------


class TestFormatDatetime:
    def test_returns_string(self) -> None:
        from file_organizer.cli.dedupe import format_datetime

        result = format_datetime(0.0)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_format_shape(self) -> None:
        from file_organizer.cli.dedupe import format_datetime

        result = format_datetime(1_700_000_000.0)
        parts = result.split(" ")
        assert len(parts) == 2
        assert "-" in parts[0]
        assert ":" in parts[1]

    def test_epoch_zero(self) -> None:
        from file_organizer.cli.dedupe import format_datetime

        result = format_datetime(0.0)
        assert "1970-01-01" in result


# ---------------------------------------------------------------------------
# DedupeConfig
# ---------------------------------------------------------------------------


class TestDedupeConfig:
    def test_defaults(self, tmp_path) -> None:
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

    def test_custom_values(self, tmp_path) -> None:
        from file_organizer.cli.dedupe import DedupeConfig

        cfg = DedupeConfig(
            directory=tmp_path,
            algorithm="md5",
            dry_run=True,
            strategy="oldest",
            safe_mode=False,
            recursive=False,
            batch=True,
            min_size=1024,
            max_size=10240,
            include_patterns=["*.jpg"],
            exclude_patterns=["*.tmp"],
        )
        assert cfg.algorithm == "md5"
        assert cfg.dry_run is True
        assert cfg.strategy == "oldest"
        assert cfg.safe_mode is False
        assert cfg.recursive is False
        assert cfg.batch is True
        assert cfg.min_size == 1024
        assert cfg.max_size == 10240
        assert cfg.include_patterns == ["*.jpg"]
        assert cfg.exclude_patterns == ["*.tmp"]


# ---------------------------------------------------------------------------
# select_files_to_keep
# ---------------------------------------------------------------------------


class TestSelectFilesToKeep:
    def _files(self) -> list[dict]:
        return [
            _make_file("/a/old.txt", size=500, mtime=1000.0),
            _make_file("/a/new.txt", size=2000, mtime=2000.0),
            _make_file("/a/mid.txt", size=1000, mtime=1500.0),
        ]

    def test_strategy_oldest_marks_oldest(self) -> None:
        from file_organizer.cli.dedupe import select_files_to_keep

        files = self._files()
        result = select_files_to_keep(files, "oldest")
        assert result[0]["keep"] is True
        assert result[1]["keep"] is False
        assert result[2]["keep"] is False

    def test_strategy_newest_marks_newest(self) -> None:
        from file_organizer.cli.dedupe import select_files_to_keep

        files = self._files()
        result = select_files_to_keep(files, "newest")
        assert result[1]["keep"] is True
        assert result[0]["keep"] is False

    def test_strategy_largest_marks_largest(self) -> None:
        from file_organizer.cli.dedupe import select_files_to_keep

        files = self._files()
        result = select_files_to_keep(files, "largest")
        assert result[1]["keep"] is True

    def test_strategy_smallest_marks_smallest(self) -> None:
        from file_organizer.cli.dedupe import select_files_to_keep

        files = self._files()
        result = select_files_to_keep(files, "smallest")
        assert result[0]["keep"] is True

    def test_strategy_manual_marks_nothing(self) -> None:
        from file_organizer.cli.dedupe import select_files_to_keep

        files = self._files()
        result = select_files_to_keep(files, "manual")
        assert all(not f["keep"] for f in result)

    def test_unknown_strategy_marks_nothing(self) -> None:
        from file_organizer.cli.dedupe import select_files_to_keep

        files = self._files()
        result = select_files_to_keep(files, "unknown_strategy")
        assert all(not f["keep"] for f in result)

    def test_returns_same_list_object(self) -> None:
        from file_organizer.cli.dedupe import select_files_to_keep

        files = self._files()
        result = select_files_to_keep(files, "oldest")
        assert result is files

    def test_two_file_oldest(self) -> None:
        from file_organizer.cli.dedupe import select_files_to_keep

        files = [_make_file("/a.txt", mtime=100.0), _make_file("/b.txt", mtime=200.0)]
        result = select_files_to_keep(files, "oldest")
        assert result[0]["keep"] is True
        assert result[1]["keep"] is False

    def test_two_file_newest(self) -> None:
        from file_organizer.cli.dedupe import select_files_to_keep

        files = [_make_file("/a.txt", mtime=100.0), _make_file("/b.txt", mtime=200.0)]
        result = select_files_to_keep(files, "newest")
        assert result[1]["keep"] is True
        assert result[0]["keep"] is False


# ---------------------------------------------------------------------------
# get_user_selection — batch mode (no interactive input needed)
# ---------------------------------------------------------------------------


class TestGetUserSelectionBatch:
    def test_batch_mode_returns_indices_to_remove(self) -> None:
        from file_organizer.cli.dedupe import get_user_selection

        files = [_make_file("/a.txt"), _make_file("/b.txt"), _make_file("/c.txt")]
        files[0]["keep"] = True
        files[1]["keep"] = False
        files[2]["keep"] = False
        result = get_user_selection(files, "oldest", batch=True)
        assert set(result) == {1, 2}

    def test_batch_mode_all_kept_returns_empty(self) -> None:
        from file_organizer.cli.dedupe import get_user_selection

        files = [_make_file("/a.txt"), _make_file("/b.txt")]
        files[0]["keep"] = True
        files[1]["keep"] = True
        result = get_user_selection(files, "oldest", batch=True)
        assert result == []


# ---------------------------------------------------------------------------
# display_summary
# ---------------------------------------------------------------------------


class TestDisplaySummary:
    @pytest.mark.parametrize(
        ("total_groups", "total_duplicates", "total_removed", "space_saved", "dry_run"),
        [
            pytest.param(5, 12, 10, 1024 * 1024, True, id="dry_run_mode"),
            pytest.param(3, 8, 6, 512 * 1024, False, id="live_run_mode"),
            pytest.param(0, 0, 0, 0, False, id="zero_files"),
        ],
    )
    def test_display_summary(
        self,
        total_groups: int,
        total_duplicates: int,
        total_removed: int,
        space_saved: int,
        dry_run: bool,
    ) -> None:
        from file_organizer.cli.dedupe import display_summary

        mock_console = MagicMock()
        with patch("file_organizer.cli.dedupe.console", mock_console):
            display_summary(total_groups, total_duplicates, total_removed, space_saved, dry_run)
        assert mock_console.print.call_count == 4
        # Verify the Panel content (4th print call, 1st positional arg)
        panel = mock_console.print.call_args_list[3][0][0]
        content = str(panel.renderable)
        assert "Duplicate groups found:" in content
        assert f"{total_groups}" in content
        assert f"{total_duplicates}" in content
        if dry_run:
            assert "DRY RUN SUMMARY" in content
            assert "would be removed" in content
        else:
            assert "DEDUPLICATION COMPLETE" in content
            assert "Files removed:" in content


# ---------------------------------------------------------------------------
# display_duplicate_group
# ---------------------------------------------------------------------------


class TestDisplayDuplicateGroup:
    def test_does_not_raise(self) -> None:
        from file_organizer.cli.dedupe import display_duplicate_group

        files = [
            _make_file("/a/file1.txt", size=1024),
            _make_file("/b/file2.txt", size=1024),
        ]
        mock_console = MagicMock()
        with patch("file_organizer.cli.dedupe.console", mock_console):
            display_duplicate_group(1, "abc123", files, 3)
        assert mock_console.print.call_count == 4

    def test_single_file_group(self) -> None:
        from file_organizer.cli.dedupe import display_duplicate_group

        files = [_make_file("/a/only.txt", size=2048)]
        mock_console = MagicMock()
        with patch("file_organizer.cli.dedupe.console", mock_console):
            display_duplicate_group(2, "deadbeef", files, 5)
        assert mock_console.print.call_count == 4
