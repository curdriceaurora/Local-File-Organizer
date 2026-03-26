"""Tests for file_organizer.cli.dedupe_hash helper module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console

from file_organizer.cli.dedupe_hash import (
    ProgressTracker,
    create_scan_options,
    initialize_hash_detector,
    scan_for_duplicates,
)

pytestmark = [pytest.mark.ci, pytest.mark.unit]


class TestProgressTracker:
    def test_without_tqdm_disables_progress(self) -> None:
        console = Console(record=True)
        import builtins

        original_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "tqdm":
                raise ImportError("missing")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            tracker = ProgressTracker(console)

        assert tracker.has_tqdm is False
        tracker.callback(1, 2)
        tracker.close()
        assert "Install tqdm for progress bars" in console.export_text()

    def test_callback_initializes_and_updates_progress_bar(self) -> None:
        console = Console()
        tracker = ProgressTracker(console)
        mock_progress = MagicMock()
        tracker.has_tqdm = True
        tracker.tqdm = MagicMock(return_value=mock_progress)

        tracker.callback(1, 3)
        tracker.callback(2, 3)
        tracker.close()

        tracker.tqdm.assert_called_once_with(total=3, desc="Hashing files", unit="files")
        assert mock_progress.update.call_count == 2
        mock_progress.close.assert_called_once()


class TestScanHelpers:
    def test_scan_for_duplicates_reports_empty_result(self) -> None:
        console = Console(record=True)
        detector = MagicMock()
        detector.get_duplicate_groups.return_value = {}
        tracker = MagicMock()

        result = scan_for_duplicates(Path("."), detector, MagicMock(), console, tracker)

        assert result == {}
        detector.scan_directory.assert_called_once()
        tracker.close.assert_called_once()
        assert "No duplicate files found" in console.export_text()

    def test_scan_for_duplicates_reports_groups(self) -> None:
        console = Console(record=True)
        detector = MagicMock()
        group = MagicMock()
        group.count = 3
        detector.get_duplicate_groups.return_value = {"abc": group}

        result = scan_for_duplicates(Path("."), detector, MagicMock(), console, None)

        assert result == {"abc": group}
        assert "Found 1 duplicate group(s) with 3 files total" in console.export_text()

    def test_create_scan_options_delegates_to_services_module(self) -> None:
        sentinel = object()
        with patch(
            "file_organizer.services.deduplication.detector.ScanOptions",
            return_value=sentinel,
        ) as mock_options:
            result = create_scan_options(
                algorithm="sha256",
                recursive=False,
                min_file_size=10,
                max_file_size=20,
                file_patterns=["*.txt"],
                exclude_patterns=["*.tmp"],
                progress_callback=None,
            )

        assert result is sentinel
        mock_options.assert_called_once()

    def test_initialize_hash_detector_delegates_to_services_module(self) -> None:
        sentinel = object()
        with patch(
            "file_organizer.services.deduplication.detector.DuplicateDetector",
            return_value=sentinel,
        ) as mock_detector:
            result = initialize_hash_detector()

        assert result is sentinel
        mock_detector.assert_called_once_with()
