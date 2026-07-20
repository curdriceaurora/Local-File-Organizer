"""Unit and integration coverage tests for file_organizer.cli.dedupe.

Targets 100% statement and branch coverage for Deduplication CLI commands.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import ANY, MagicMock, patch

import pytest

from file_organizer.cli.dedupe import DedupeConfig, dedupe_command

pytestmark = pytest.mark.unit


def test_dedupe_config_initialization() -> None:
    """Verify DedupeConfig properties and defaults."""
    dir_path = Path("/") / "mock" / "path"

    # Test default values
    config = DedupeConfig(directory=dir_path)
    assert config.directory == dir_path
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

    # Test custom values
    config_custom = DedupeConfig(
        directory=dir_path,
        algorithm="md5",
        dry_run=True,
        strategy="oldest",
        safe_mode=False,
        recursive=False,
        batch=True,
        min_size=100,
        max_size=5000,
        include_patterns=["*.mp3"],
        exclude_patterns=["*.tmp"],
    )
    assert config_custom.algorithm == "md5"
    assert config_custom.dry_run is True
    assert config_custom.strategy == "oldest"
    assert config_custom.safe_mode is False
    assert config_custom.recursive is False
    assert config_custom.batch is True
    assert config_custom.min_size == 100
    assert config_custom.max_size == 5000
    assert config_custom.include_patterns == ["*.mp3"]
    assert config_custom.exclude_patterns == ["*.tmp"]


def test_dedupe_command_help(capsys: pytest.CaptureFixture[str]) -> None:
    """Verify dedupe command help output triggers SystemExit."""
    with pytest.raises(SystemExit) as exc_info:
        dedupe_command(["--help"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "Find and remove duplicate files" in captured.out


def test_dedupe_command_directory_validation(tmp_path: Path) -> None:
    """Verify dedupe command validates directory existence and type."""
    # 1. Directory does not exist
    non_existent = tmp_path / "does_not_exist"
    exit_code = dedupe_command([str(non_existent)])
    assert exit_code == 1

    # 2. Path is a file, not a directory
    file_path = tmp_path / "file.txt"
    file_path.write_text("content")
    exit_code = dedupe_command([str(file_path)])
    assert exit_code == 1


def test_dedupe_command_no_duplicates_found(tmp_path: Path) -> None:
    """Verify dedupe command when no duplicates are found."""
    # Setup mocks
    mock_detector = MagicMock()
    mock_tracker = MagicMock(has_tqdm=True, callback=MagicMock())

    with (
        patch("file_organizer.cli.dedupe_display.display_banner"),
        patch("file_organizer.cli.dedupe_display.display_config"),
        patch("file_organizer.cli.dedupe.initialize_hash_detector", return_value=mock_detector),
        patch("file_organizer.services.deduplication.backup.BackupManager") as mock_backup_class,
        patch("file_organizer.cli.dedupe.ProgressTracker", return_value=mock_tracker),
        patch("file_organizer.cli.dedupe.create_scan_options"),
        patch("file_organizer.cli.dedupe.scan_for_duplicates", return_value={}) as mock_scan,
    ):
        exit_code = dedupe_command([str(tmp_path)])
        assert exit_code == 0
        mock_scan.assert_called_once()
        mock_backup_class.assert_called_once_with(tmp_path)


def test_dedupe_command_with_duplicates(tmp_path: Path) -> None:
    """Verify dedupe command processes, removes, and summarizes duplicates."""
    # Setup mock duplicates: 1 group with 2 duplicates
    mock_group = MagicMock()
    mock_group.count = 2
    mock_duplicates = {"hash123": mock_group}

    mock_detector = MagicMock()
    mock_tracker = MagicMock(has_tqdm=False)

    with (
        patch("file_organizer.cli.dedupe_display.display_banner"),
        patch("file_organizer.cli.dedupe_display.display_config"),
        patch("file_organizer.cli.dedupe.initialize_hash_detector", return_value=mock_detector),
        patch("file_organizer.services.deduplication.backup.BackupManager"),
        patch("file_organizer.cli.dedupe.ProgressTracker", return_value=mock_tracker),
        patch("file_organizer.cli.dedupe.create_scan_options"),
        patch("file_organizer.cli.dedupe.scan_for_duplicates", return_value=mock_duplicates),
        patch(
            "file_organizer.cli.dedupe_removal.process_duplicate_group", return_value=(1, 1024)
        ) as mock_process,
        patch("file_organizer.cli.dedupe_display.display_summary") as mock_summary,
        patch("file_organizer.cli.dedupe_display.display_backup_info") as mock_backup_info,
    ):
        # 1. Normal run with backups (safe_mode=True, dry_run=False)
        exit_code = dedupe_command([str(tmp_path), "--strategy", "oldest"])
        assert exit_code == 0
        mock_process.assert_called_once()
        mock_summary.assert_called_once_with(ANY, 1, 2, 1, 1024, False)
        mock_backup_info.assert_called_once()

        # Reset mocks
        mock_process.reset_mock()
        mock_summary.reset_mock()
        mock_backup_info.reset_mock()

        # 2. Dry run (dry_run=True)
        exit_code = dedupe_command([str(tmp_path), "--dry-run"])
        assert exit_code == 0
        mock_process.assert_called_once()
        mock_summary.assert_called_once_with(ANY, 1, 2, 1, 1024, True)
        mock_backup_info.assert_not_called()


def test_dedupe_command_keyboard_interrupt(tmp_path: Path) -> None:
    """Verify KeyboardInterrupt returns exit code 130."""
    with (
        patch("file_organizer.cli.dedupe_display.display_banner"),
        patch("file_organizer.cli.dedupe_display.display_config"),
        patch("file_organizer.cli.dedupe.initialize_hash_detector", side_effect=KeyboardInterrupt),
    ):
        exit_code = dedupe_command([str(tmp_path)])
        assert exit_code == 130


def test_dedupe_command_general_exception(tmp_path: Path) -> None:
    """Verify general exceptions return exit code 1 and log error."""
    with (
        patch("file_organizer.cli.dedupe_display.display_banner"),
        patch("file_organizer.cli.dedupe_display.display_config"),
        patch(
            "file_organizer.cli.dedupe.initialize_hash_detector",
            side_effect=RuntimeError("IO Failure"),
        ),
        patch("file_organizer.cli.dedupe.logger") as mock_logger,
    ):
        exit_code = dedupe_command([str(tmp_path)])
        assert exit_code == 1
        mock_logger.exception.assert_called_once_with("Deduplication failed")


def test_dedupe_command_verbose_logging(tmp_path: Path) -> None:
    """Verify --verbose and --no-safe-mode options are handled."""
    mock_detector = MagicMock()
    with (
        patch("file_organizer.cli.dedupe_display.display_banner"),
        patch("file_organizer.cli.dedupe_display.display_config"),
        patch("file_organizer.cli.dedupe.initialize_hash_detector", return_value=mock_detector),
        patch("file_organizer.cli.dedupe.scan_for_duplicates", return_value={}),
        patch("file_organizer.cli.dedupe.logger") as mock_logger,
    ):
        exit_code = dedupe_command(
            [
                str(tmp_path),
                "--verbose",
                "--no-safe-mode",
                "--no-recursive",
                "--min-size",
                "50",
                "--max-size",
                "500",
                "--include",
                "*.jpg",
                "--include",
                "*.png",
                "--exclude",
                "*.tmp",
            ]
        )
        assert exit_code == 0
        # Check logger configurations were updated (verbose branch calls remove() once)
        mock_logger.remove.assert_called_once()
