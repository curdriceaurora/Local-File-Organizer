"""Tests for file_organizer.cli.dedupe module.

Tests the argparse-based deduplication CLI including:
- dedupe_command function
- DedupeConfig
- Helper functions (format_size, format_datetime, select_files_to_keep, etc.)
- display_summary and display_duplicate_group
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console

from file_organizer.cli.dedupe import DedupeConfig, dedupe_command, main
from file_organizer.cli.dedupe_display import (
    display_duplicate_group,
    display_summary,
    format_datetime,
    format_size,
)
from file_organizer.cli.dedupe_removal import remove_files
from file_organizer.cli.dedupe_strategy import (
    get_user_selection,
    select_files_to_keep,
)

pytestmark = [pytest.mark.ci, pytest.mark.unit]

# ---------------------------------------------------------------------------
# Patch paths — dedupe_command uses *lazy imports* inside a try block.
# We must patch at the source-module level so the runtime import picks up
# our mocks.
# ---------------------------------------------------------------------------
_DETECTOR_PATH = "file_organizer.services.deduplication.detector.DuplicateDetector"
_SCAN_OPTS_PATH = "file_organizer.services.deduplication.detector.ScanOptions"
_BACKUP_MGR_PATH = "file_organizer.services.deduplication.backup.BackupManager"


def _ensure_dedup_modules_loaded():
    """Ensure the deduplication subpackage modules are in sys.modules.

    When pytest-cov is active it may remove modules from sys.modules during
    its cleanup phase.  ``unittest.mock.patch`` resolves the full dotted path
    by walking ``sys.modules``; if an intermediate package is missing it
    raises ``AttributeError``.

    This helper makes sure the two leaf modules we need for patching are
    importable.  We use ``importlib`` to handle the import so Python's normal
    import machinery (including parent-package initialisation) takes effect.
    """
    import importlib
    import sys

    for mod_name in (
        "file_organizer.services.deduplication.detector",
        "file_organizer.services.deduplication.backup",
    ):
        if mod_name not in sys.modules:
            try:
                importlib.import_module(mod_name)
            except Exception:
                # If the import fails (e.g. missing optional deps) we still
                # need *something* in sys.modules so ``patch()`` can resolve
                # the path.  Create stub entries for each segment.
                import types

                parts = mod_name.split(".")
                for i in range(len(parts)):
                    partial = ".".join(parts[: i + 1])
                    if partial not in sys.modules:
                        sys.modules[partial] = types.ModuleType(partial)


# Eagerly ensure modules are loaded at import time so all tests can patch.
_ensure_dedup_modules_loaded()


# ============================================================================
# DedupeConfig Tests
# ============================================================================


@pytest.mark.unit
class TestDedupeConfig:
    """Tests for the DedupeConfig dataclass."""

    def test_default_config(self, tmp_path):
        config = DedupeConfig(directory=tmp_path)
        assert config.directory == tmp_path
        assert config.algorithm == "sha256"
        assert config.dry_run is False
        assert config.strategy == "manual"
        assert config.safe_mode is True
        assert config.recursive is True
        assert config.batch is False
        assert config.min_size == 0
        assert config.max_size is None
        assert config.include_patterns == []
        assert config.exclude_patterns == []

    def test_custom_config(self, tmp_path):
        config = DedupeConfig(
            directory=tmp_path,
            algorithm="md5",
            dry_run=True,
            strategy="oldest",
            safe_mode=False,
            recursive=False,
            batch=True,
            min_size=1024,
            max_size=1048576,
            include_patterns=["*.jpg"],
            exclude_patterns=["*.tmp"],
        )
        assert config.algorithm == "md5"
        assert config.dry_run is True
        assert config.strategy == "oldest"
        assert config.safe_mode is False
        assert config.recursive is False
        assert config.batch is True
        assert config.min_size == 1024
        assert config.max_size == 1048576
        assert config.include_patterns == ["*.jpg"]
        assert config.exclude_patterns == ["*.tmp"]


# ============================================================================
# Helper Function Tests
# ============================================================================


@pytest.mark.unit
class TestFormatSize:
    """Tests for format_size helper."""

    def test_bytes(self):
        assert format_size(500) == "500.0 B"

    def test_kilobytes(self):
        result = format_size(2048)
        assert "KB" in result

    def test_megabytes(self):
        result = format_size(5 * 1024 * 1024)
        assert "MB" in result

    def test_gigabytes(self):
        result = format_size(3 * 1024 * 1024 * 1024)
        assert "GB" in result

    def test_terabytes(self):
        result = format_size(2 * 1024**4)
        assert "TB" in result

    def test_zero(self):
        assert format_size(0) == "0.0 B"


@pytest.mark.unit
class TestFormatDatetime:
    """Tests for format_datetime helper."""

    def test_valid_timestamp(self):
        result = format_datetime(1706745600)  # 2024-02-01 00:00:00 UTC approx
        assert isinstance(result, str)
        assert "-" in result  # Contains date separators

    def test_zero_timestamp(self):
        result = format_datetime(0)
        assert isinstance(result, str) and len(result) > 0
        assert "-" in result


@pytest.mark.unit
class TestSelectFilesToKeep:
    """Tests for select_files_to_keep."""

    def _make_files(self):
        return [
            {"path": Path("/a/file1.txt"), "size": 100, "mtime": 1000},
            {"path": Path("/a/file2.txt"), "size": 200, "mtime": 2000},
            {"path": Path("/a/file3.txt"), "size": 50, "mtime": 1500},
        ]

    def test_oldest_strategy(self):
        files = self._make_files()
        result = select_files_to_keep(files, "oldest")
        assert result[0].get("keep", False) is True  # file1 has mtime=1000

    def test_newest_strategy(self):
        files = self._make_files()
        result = select_files_to_keep(files, "newest")
        assert result[1].get("keep", False) is True  # file2 has mtime=2000

    def test_largest_strategy(self):
        files = self._make_files()
        result = select_files_to_keep(files, "largest")
        assert result[1].get("keep", False) is True  # file2 has size=200

    def test_smallest_strategy(self):
        files = self._make_files()
        result = select_files_to_keep(files, "smallest")
        assert result[2].get("keep", False) is True  # file3 has size=50

    def test_manual_strategy(self):
        files = self._make_files()
        result = select_files_to_keep(files, "manual")
        # No automatic marking in manual mode
        for f in result:
            assert f.get("keep", False) is False

    def test_does_not_mutate_input_list(self):
        files = self._make_files()
        original = [dict(file_info) for file_info in files]
        result = select_files_to_keep(files, "oldest")
        assert files == original
        assert result is not files

    def test_empty_list_returns_empty_list(self):
        assert select_files_to_keep([], "oldest") == []


@pytest.mark.unit
class TestGetUserSelection:
    """Tests for get_user_selection."""

    def test_batch_mode_automatic(self):
        files = [
            {"path": Path("/a/f1.txt"), "keep": True},
            {"path": Path("/a/f2.txt"), "keep": False},
            {"path": Path("/a/f3.txt"), "keep": False},
        ]
        result = get_user_selection(files, "oldest", batch=True)
        assert result == [1, 2]  # Indices of files not marked as keep

    def test_batch_mode_all_keep(self):
        files = [
            {"path": Path("/a/f1.txt"), "keep": True},
            {"path": Path("/a/f2.txt"), "keep": True},
        ]
        result = get_user_selection(files, "oldest", batch=True)
        assert result == []

    def test_keyboard_interrupt_is_reraised_for_auto_confirmation(self):
        files = [
            {"path": Path("/a/f1.txt"), "keep": True},
            {"path": Path("/a/f2.txt"), "keep": False},
        ]
        console = MagicMock(spec=Console)
        console.input.side_effect = KeyboardInterrupt

        with pytest.raises(KeyboardInterrupt):
            get_user_selection(files, "oldest", batch=False, console=console)


@pytest.mark.unit
class TestRemoveFiles:
    """Tests for file removal summary behavior."""

    def test_summary_reports_actual_successful_removals(self, tmp_path):
        first = tmp_path / "one.txt"
        second = tmp_path / "two.txt"
        first.write_text("one")
        second.write_text("two")
        console = Console(record=True)
        files = [
            {"path": first, "size": 3},
            {"path": second, "size": 3},
        ]

        with patch.object(Path, "unlink", side_effect=[None, OSError("boom")]):
            removed, space_saved = remove_files(files, [0, 1], None, False, console)

        assert removed == 1
        assert space_saved == 3


# ============================================================================
# dedupe_command Tests
# ============================================================================


@pytest.mark.unit
class TestDedupeCommand:
    """Tests for the main dedupe_command function."""

    def test_nonexistent_directory(self):
        result = dedupe_command(["/nonexistent/directory/xyz"])
        assert result == 1

    def test_file_instead_of_directory(self, tmp_path):
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello")
        result = dedupe_command([str(test_file)])
        assert result == 1

    def test_no_duplicates_found(self, tmp_path):
        # Create a unique file
        (tmp_path / "unique.txt").write_text("unique content")

        mock_detector = MagicMock()
        mock_detector.scan_directory.return_value = None
        mock_detector.get_duplicate_groups.return_value = {}

        with (
            patch(
                _DETECTOR_PATH,
                return_value=mock_detector,
            ) as _,
            patch(
                _BACKUP_MGR_PATH,
                return_value=MagicMock(),
            ),
            patch(
                _SCAN_OPTS_PATH,
            ),
        ):
            result = dedupe_command([str(tmp_path), "--dry-run"])
        assert result == 0

    def test_dry_run_flag(self, tmp_path):
        (tmp_path / "file.txt").write_text("content")

        mock_detector = MagicMock()
        mock_detector.scan_directory.return_value = None
        mock_detector.get_duplicate_groups.return_value = {}

        with (
            patch(
                _DETECTOR_PATH,
                return_value=mock_detector,
            ),
            patch(_BACKUP_MGR_PATH, return_value=MagicMock()),
            patch(_SCAN_OPTS_PATH),
        ):
            result = dedupe_command([str(tmp_path), "--dry-run"])
        assert result == 0

    def test_verbose_flag(self, tmp_path):
        (tmp_path / "file.txt").write_text("data")

        mock_detector = MagicMock()
        mock_detector.scan_directory.return_value = None
        mock_detector.get_duplicate_groups.return_value = {}

        with (
            patch(
                _DETECTOR_PATH,
                return_value=mock_detector,
            ),
            patch(_BACKUP_MGR_PATH, return_value=MagicMock()),
            patch(_SCAN_OPTS_PATH),
        ):
            result = dedupe_command([str(tmp_path), "--verbose", "--dry-run"])
        assert result == 0

    def test_algorithm_md5(self, tmp_path):
        (tmp_path / "f.txt").write_text("data")

        mock_detector = MagicMock()
        mock_detector.scan_directory.return_value = None
        mock_detector.get_duplicate_groups.return_value = {}

        with (
            patch(
                _DETECTOR_PATH,
                return_value=mock_detector,
            ),
            patch(_BACKUP_MGR_PATH, return_value=MagicMock()),
            patch(_SCAN_OPTS_PATH),
        ):
            result = dedupe_command([str(tmp_path), "--algorithm", "md5", "--dry-run"])
        assert result == 0

    def test_with_size_filters(self, tmp_path):
        (tmp_path / "f.txt").write_text("data")

        mock_detector = MagicMock()
        mock_detector.scan_directory.return_value = None
        mock_detector.get_duplicate_groups.return_value = {}

        with (
            patch(
                _DETECTOR_PATH,
                return_value=mock_detector,
            ),
            patch(_BACKUP_MGR_PATH, return_value=MagicMock()),
            patch(_SCAN_OPTS_PATH),
        ):
            result = dedupe_command(
                [str(tmp_path), "--min-size", "100", "--max-size", "1000000", "--dry-run"]
            )
        assert result == 0

    def test_include_exclude_patterns(self, tmp_path):
        (tmp_path / "f.txt").write_text("data")

        mock_detector = MagicMock()
        mock_detector.scan_directory.return_value = None
        mock_detector.get_duplicate_groups.return_value = {}

        with (
            patch(
                _DETECTOR_PATH,
                return_value=mock_detector,
            ),
            patch(_BACKUP_MGR_PATH, return_value=MagicMock()),
            patch(_SCAN_OPTS_PATH),
        ):
            result = dedupe_command(
                [str(tmp_path), "--include", "*.jpg", "--exclude", "*.tmp", "--dry-run"]
            )
        assert result == 0

    def test_no_recursive(self, tmp_path):
        (tmp_path / "f.txt").write_text("data")

        mock_detector = MagicMock()
        mock_detector.scan_directory.return_value = None
        mock_detector.get_duplicate_groups.return_value = {}

        with (
            patch(
                _DETECTOR_PATH,
                return_value=mock_detector,
            ),
            patch(_BACKUP_MGR_PATH, return_value=MagicMock()),
            patch(_SCAN_OPTS_PATH),
        ):
            result = dedupe_command([str(tmp_path), "--no-recursive", "--dry-run"])
        assert result == 0

    def test_no_safe_mode(self, tmp_path):
        (tmp_path / "f.txt").write_text("data")

        mock_detector = MagicMock()
        mock_detector.scan_directory.return_value = None
        mock_detector.get_duplicate_groups.return_value = {}

        with (
            patch(
                _DETECTOR_PATH,
                return_value=mock_detector,
            ),
            patch(_SCAN_OPTS_PATH),
        ):
            result = dedupe_command([str(tmp_path), "--no-safe-mode", "--dry-run"])
        assert result == 0

    def test_exception_during_scan(self, tmp_path):
        (tmp_path / "f.txt").write_text("data")

        with (
            patch(
                _DETECTOR_PATH,
                side_effect=RuntimeError("scan failed"),
            ),
            patch(_BACKUP_MGR_PATH, return_value=MagicMock()),
            patch(_SCAN_OPTS_PATH),
        ):
            result = dedupe_command([str(tmp_path), "--dry-run"])
        assert result == 1


# ============================================================================
# display_summary Tests
# ============================================================================


@pytest.mark.unit
class TestDisplaySummary:
    """Tests for display_summary output."""

    def test_dry_run_summary(self, capsys):
        console = Console(record=True)
        display_summary(
            console,
            total_groups=3,
            total_duplicates=10,
            total_removed=7,
            space_saved=1024 * 1024,
            dry_run=True,
        )
        output = console.export_text()
        assert "DRY RUN SUMMARY" in output
        assert "Duplicate groups found: 3" in output
        assert "Files that would be removed: 7" in output
        assert "Run without --dry-run to actually remove files." in output

    def test_live_run_summary(self, capsys):
        console = Console(record=True)
        display_summary(
            console,
            total_groups=2,
            total_duplicates=5,
            total_removed=3,
            space_saved=512,
            dry_run=False,
        )
        output = console.export_text()
        assert "DEDUPLICATION COMPLETE" in output
        assert "Duplicate groups found: 2" in output
        assert "Files removed: 3" in output
        assert "Space saved: 512.0 B" in output


# ============================================================================
# display_duplicate_group Tests
# ============================================================================


@pytest.mark.unit
class TestDisplayDuplicateGroup:
    """Tests for display_duplicate_group output."""

    def test_displays_group(self, capsys):
        console = Console(record=True)
        files = [
            {"path": Path("/a/file1.txt"), "size": 1024, "mtime": 1000.0, "keep": True},
            {"path": Path("/a/file2.txt"), "size": 1024, "mtime": 2000.0, "keep": False},
        ]
        display_duplicate_group(
            console,
            group_id=1,
            file_hash="abc123def456789012345678",
            files=files,
            total_groups=3,
        )
        output = console.export_text()
        assert "Duplicate Group 1/3" in output
        assert "abc123def4567890..." in output
        assert "/a/file1.txt" in output
        assert "/a/file2.txt" in output
        assert "Potential space savings: 1.0 KB" in output

    def test_displays_group_no_keep(self, capsys):
        console = Console(record=True)
        files = [
            {"path": Path("/x/y.txt"), "size": 500, "mtime": 100.0},
            {"path": Path("/x/z.txt"), "size": 500, "mtime": 200.0},
        ]
        display_duplicate_group(
            console,
            group_id=2,
            file_hash="0" * 64,
            files=files,
            total_groups=5,
        )
        output = console.export_text()
        assert "Duplicate Group 2/5" in output
        assert "/x/y.txt" in output
        assert "/x/z.txt" in output
        assert "Potential space savings: 500.0 B" in output


# ============================================================================
# get_user_selection — interactive mode tests
# ============================================================================


@pytest.mark.unit
class TestGetUserSelectionInteractive:
    """Tests for get_user_selection with manual strategy (interactive prompts)."""

    def test_manual_skip(self):
        """User types 's' to skip."""
        files = [
            {"path": Path("/a/f1.txt")},
            {"path": Path("/a/f2.txt")},
        ]
        with patch("file_organizer.cli.dedupe.console") as mock_console:
            mock_console.input.return_value = "s"
            result = get_user_selection(files, "manual", batch=False)
        assert result == []

    def test_manual_keep_all(self):
        """User types 'a' to keep all."""
        files = [
            {"path": Path("/a/f1.txt")},
            {"path": Path("/a/f2.txt")},
        ]
        with patch("file_organizer.cli.dedupe.console") as mock_console:
            mock_console.input.return_value = "a"
            result = get_user_selection(files, "manual", batch=False)
        assert result == []

    def test_manual_select_keep(self):
        """User types '1' to keep file 1, remove file 2."""
        files = [
            {"path": Path("/a/f1.txt")},
            {"path": Path("/a/f2.txt")},
        ]
        with patch("file_organizer.cli.dedupe.console") as mock_console:
            mock_console.input.return_value = "1"
            result = get_user_selection(files, "manual", batch=False)
        assert result == [1]  # Remove index 1

    def test_manual_invalid_then_valid(self):
        """User enters invalid input, then valid."""
        files = [
            {"path": Path("/a/f1.txt")},
            {"path": Path("/a/f2.txt")},
        ]
        with patch("file_organizer.cli.dedupe.console") as mock_console:
            mock_console.input.side_effect = ["xyz", "1"]
            result = get_user_selection(files, "manual", batch=False)
        assert result == [1]

    def test_manual_invalid_index_then_valid(self):
        """User enters out-of-range index, then valid."""
        files = [
            {"path": Path("/a/f1.txt")},
            {"path": Path("/a/f2.txt")},
        ]
        with patch("file_organizer.cli.dedupe.console") as mock_console:
            mock_console.input.side_effect = ["99", "1"]
            result = get_user_selection(files, "manual", batch=False)
        assert result == [1]

    def test_manual_keyboard_interrupt(self):
        """KeyboardInterrupt during manual selection is re-raised."""
        files = [{"path": Path("/a/f1.txt")}]
        with patch("file_organizer.cli.dedupe.console") as mock_console:
            mock_console.input.side_effect = KeyboardInterrupt
            with pytest.raises(KeyboardInterrupt):
                get_user_selection(files, "manual", batch=False)


@pytest.mark.unit
class TestGetUserSelectionConfirm:
    """Tests for get_user_selection with automatic strategy + non-batch (confirmation)."""

    def test_confirm_yes(self):
        files = [
            {"path": Path("/a/f1.txt"), "keep": True},
            {"path": Path("/a/f2.txt"), "keep": False},
        ]
        with patch("file_organizer.cli.dedupe.console") as mock_console:
            mock_console.input.return_value = "y"
            result = get_user_selection(files, "oldest", batch=False)
        assert result == [1]

    def test_confirm_no(self):
        files = [
            {"path": Path("/a/f1.txt"), "keep": True},
            {"path": Path("/a/f2.txt"), "keep": False},
        ]
        with patch("file_organizer.cli.dedupe.console") as mock_console:
            mock_console.input.return_value = "n"
            result = get_user_selection(files, "oldest", batch=False)
        assert result == []

    def test_confirm_skip(self):
        files = [
            {"path": Path("/a/f1.txt"), "keep": True},
            {"path": Path("/a/f2.txt"), "keep": False},
        ]
        with patch("file_organizer.cli.dedupe.console") as mock_console:
            mock_console.input.return_value = "skip"
            result = get_user_selection(files, "oldest", batch=False)
        assert result == []

    def test_confirm_invalid_then_yes(self):
        files = [
            {"path": Path("/a/f1.txt"), "keep": True},
            {"path": Path("/a/f2.txt"), "keep": False},
        ]
        with patch("file_organizer.cli.dedupe.console") as mock_console:
            mock_console.input.side_effect = ["maybe", "y"]
            result = get_user_selection(files, "oldest", batch=False)
        assert result == [1]


# ============================================================================
# dedupe_command — duplicate processing loop tests
# ============================================================================


@pytest.mark.unit
class TestDedupeCommandDuplicates:
    """Tests for dedupe_command when duplicates ARE found."""

    def _make_mock_group(self, paths, size=1024, mtime_start=1000):
        """Create a mock duplicate group with the given file paths."""
        from datetime import UTC
        from datetime import datetime as dt

        group = MagicMock()
        group.count = len(paths)
        group.files = []
        for i, p in enumerate(paths):
            fm = MagicMock()
            fm.path = Path(p)
            fm.size = size
            fm.modified_time = dt.fromtimestamp(mtime_start + i * 1000, tz=UTC)
            group.files.append(fm)
        return group

    def test_duplicates_found_dry_run_batch(self, tmp_path):
        """Dry-run + batch mode with duplicates exercises the full loop."""
        (tmp_path / "a.txt").write_text("data")
        (tmp_path / "b.txt").write_text("data")

        grp = self._make_mock_group([str(tmp_path / "a.txt"), str(tmp_path / "b.txt")])

        mock_detector = MagicMock()
        mock_detector.scan_directory.return_value = None
        mock_detector.get_duplicate_groups.return_value = {"hash1": grp}

        with (
            patch(_DETECTOR_PATH, return_value=mock_detector),
            patch(_BACKUP_MGR_PATH, return_value=MagicMock()),
            patch(_SCAN_OPTS_PATH),
        ):
            result = dedupe_command(
                [
                    str(tmp_path),
                    "--dry-run",
                    "--strategy",
                    "oldest",
                    "--batch",
                ]
            )
        assert result == 0

    def test_duplicates_found_interactive_confirm(self, tmp_path):
        """Interactive strategy=oldest, non-batch; user confirms with 'y'."""
        (tmp_path / "a.txt").write_text("data")
        (tmp_path / "b.txt").write_text("data")

        grp = self._make_mock_group([str(tmp_path / "a.txt"), str(tmp_path / "b.txt")])

        mock_detector = MagicMock()
        mock_detector.scan_directory.return_value = None
        mock_detector.get_duplicate_groups.return_value = {"hash1": grp}

        with (
            patch(_DETECTOR_PATH, return_value=mock_detector),
            patch(_BACKUP_MGR_PATH, return_value=MagicMock()),
            patch(_SCAN_OPTS_PATH),
            patch("file_organizer.cli.dedupe.console") as mock_console,
        ):
            mock_console.input.return_value = "y"
            # Need to allow print calls through
            mock_console.print = MagicMock()
            result = dedupe_command(
                [
                    str(tmp_path),
                    "--dry-run",
                    "--strategy",
                    "oldest",
                ]
            )
        assert result == 0

    def test_duplicates_skip_group(self, tmp_path):
        """User skips group — exercises the 'else' branch (Skipped)."""
        (tmp_path / "a.txt").write_text("data")
        (tmp_path / "b.txt").write_text("data")

        grp = self._make_mock_group([str(tmp_path / "a.txt"), str(tmp_path / "b.txt")])

        mock_detector = MagicMock()
        mock_detector.scan_directory.return_value = None
        mock_detector.get_duplicate_groups.return_value = {"hash1": grp}

        with (
            patch(_DETECTOR_PATH, return_value=mock_detector),
            patch(_BACKUP_MGR_PATH, return_value=MagicMock()),
            patch(_SCAN_OPTS_PATH),
            patch("file_organizer.cli.dedupe.console") as mock_console,
        ):
            mock_console.input.return_value = "n"
            mock_console.print = MagicMock()
            result = dedupe_command(
                [
                    str(tmp_path),
                    "--dry-run",
                    "--strategy",
                    "oldest",
                ]
            )
        assert result == 0

    def test_duplicates_live_remove_with_backup(self, tmp_path):
        """Live (non-dry-run) removal with safe_mode exercises backup + unlink."""
        a = tmp_path / "a.txt"
        b = tmp_path / "b.txt"
        a.write_text("data")
        b.write_text("data")

        grp = self._make_mock_group([str(a), str(b)])

        mock_detector = MagicMock()
        mock_detector.scan_directory.return_value = None
        mock_detector.get_duplicate_groups.return_value = {"hash1": grp}

        mock_bkp = MagicMock()
        mock_bkp.create_backup.return_value = Path("/tmp/backup")

        with (
            patch(_DETECTOR_PATH, return_value=mock_detector),
            patch(_BACKUP_MGR_PATH, return_value=mock_bkp),
            patch(_SCAN_OPTS_PATH),
        ):
            result = dedupe_command(
                [
                    str(tmp_path),
                    "--strategy",
                    "oldest",
                    "--batch",
                ]
            )
        assert result == 0

    def test_duplicates_error_during_remove(self, tmp_path):
        """Exception during file unlink is caught and logged."""
        a = tmp_path / "a.txt"
        b = tmp_path / "b.txt"
        a.write_text("data")
        b.write_text("data")

        grp = self._make_mock_group([str(a), str(b)])
        # Make the second file's path a MagicMock so unlink() raises
        grp.files[1].path = MagicMock()
        grp.files[1].path.unlink.side_effect = PermissionError("denied")
        grp.files[1].path.__str__ = lambda self: "/tmp/b.txt"

        mock_detector = MagicMock()
        mock_detector.scan_directory.return_value = None
        mock_detector.get_duplicate_groups.return_value = {"hash1": grp}

        with (
            patch(_DETECTOR_PATH, return_value=mock_detector),
            patch(_BACKUP_MGR_PATH, return_value=MagicMock()),
            patch(_SCAN_OPTS_PATH),
        ):
            result = dedupe_command(
                [
                    str(tmp_path),
                    "--strategy",
                    "oldest",
                    "--batch",
                    "--no-safe-mode",
                ]
            )
        # Should still return 0 (error is per-file, not fatal)
        assert result == 0

    def test_keyboard_interrupt_during_scan(self, tmp_path):
        """KeyboardInterrupt returns exit code 130."""
        (tmp_path / "f.txt").write_text("data")

        mock_detector = MagicMock()
        mock_detector.scan_directory.side_effect = KeyboardInterrupt

        with (
            patch(_DETECTOR_PATH, return_value=mock_detector),
            patch(_BACKUP_MGR_PATH, return_value=MagicMock()),
            patch(_SCAN_OPTS_PATH),
        ):
            result = dedupe_command([str(tmp_path), "--dry-run"])
        assert result == 130

    def test_no_safe_mode_warning_live(self, tmp_path):
        """Non-dry-run with --no-safe-mode exercises the warning branch."""
        (tmp_path / "f.txt").write_text("data")

        mock_detector = MagicMock()
        mock_detector.scan_directory.return_value = None
        mock_detector.get_duplicate_groups.return_value = {}

        with (
            patch(_DETECTOR_PATH, return_value=mock_detector),
            patch(_SCAN_OPTS_PATH),
        ):
            # Live run, no safe mode, but no duplicates found
            result = dedupe_command([str(tmp_path), "--no-safe-mode"])
        assert result == 0


# ============================================================================
# main() entry-point test
# ============================================================================


@pytest.mark.unit
class TestMain:
    """Tests for the main() entry point."""

    def test_main_calls_dedupe_command(self):
        with patch("file_organizer.cli.dedupe.dedupe_command", return_value=0) as mock_cmd:
            with pytest.raises(SystemExit) as exc_info:
                main()
            mock_cmd.assert_called_once()
            assert exc_info.value.code == 0

    def test_main_propagates_exit_code(self):
        with patch("file_organizer.cli.dedupe.dedupe_command", return_value=1):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# Wrapper function tests (compatibility shims in dedupe.py)
# ---------------------------------------------------------------------------


class TestDedupeWrappers:
    """Tests for the compatibility wrapper functions in dedupe.py."""

    def test_format_size_delegates(self) -> None:
        from file_organizer.cli.dedupe import format_size as wrapper_format_size
        from file_organizer.cli.dedupe_display import format_size as underlying

        assert wrapper_format_size(1024) == underlying(1024)
        assert wrapper_format_size(0) == underlying(0)

    def test_format_datetime_delegates(self) -> None:
        from file_organizer.cli.dedupe import format_datetime as wrapper_format_datetime
        from file_organizer.cli.dedupe_display import format_datetime as underlying

        ts = 1609459200.0
        assert wrapper_format_datetime(ts) == underlying(ts)

    def test_select_files_to_keep_delegates(self) -> None:
        from file_organizer.cli.dedupe import select_files_to_keep as wrapper_select

        files: list[dict] = [
            {"path": "/a.txt", "size": 100, "mtime": 1.0},
            {"path": "/b.txt", "size": 200, "mtime": 2.0},
        ]
        result = wrapper_select(files, "newest")
        assert result is files
        assert len(result) == 2
        assert sum(1 for f in result if f.get("keep") is True) == 1
        assert result[1].get("keep") is True

    def test_get_user_selection_batch_mode(self) -> None:
        from file_organizer.cli.dedupe import get_user_selection as wrapper_get_sel

        files = [
            {"path": "/a.txt", "size": 100, "mtime": 1.0, "keep": True},
            {"path": "/b.txt", "size": 200, "mtime": 2.0, "keep": False},
        ]
        result = wrapper_get_sel(files, "newest", batch=True)
        assert result == [1]

    def test_display_summary_delegates(self) -> None:
        from unittest.mock import patch

        from file_organizer.cli.dedupe import console as dedupe_console
        from file_organizer.cli.dedupe import display_summary as wrapper_summary

        with patch("file_organizer.cli.dedupe._display_summary") as mock_inner:
            wrapper_summary(5, 10, 3, 1024, dry_run=True)
            mock_inner.assert_called_once()
            args = mock_inner.call_args[0]
            assert args == (dedupe_console, 5, 10, 3, 1024, True)

    def test_display_duplicate_group_delegates(self) -> None:
        from unittest.mock import patch

        from file_organizer.cli.dedupe import console as dedupe_console
        from file_organizer.cli.dedupe import (
            display_duplicate_group as wrapper_display,
        )

        files = [
            {"path": "/a.txt", "size": 100, "mtime": 1.0, "keep": True},
            {"path": "/b.txt", "size": 100, "mtime": 2.0, "keep": False},
        ]
        with patch("file_organizer.cli.dedupe._display_duplicate_group") as mock_inner:
            wrapper_display(1, "abc123", files, 5)
            mock_inner.assert_called_once()
            args = mock_inner.call_args[0]
            assert args == (dedupe_console, 1, "abc123", files, 5)
