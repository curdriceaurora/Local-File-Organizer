# tests/integration/test_dedupe_hash_integration.py
"""Integration tests for file_organizer.cli.dedupe_hash.

Exercises scan_for_duplicates(), create_scan_options(), and
initialize_hash_detector() against a real temporary filesystem.
ProgressTracker is tested without tqdm dependency so the suite
always runs in CI.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from rich.console import Console

from file_organizer.cli.dedupe_hash import (
    ProgressTracker,
    create_scan_options,
    initialize_hash_detector,
    scan_for_duplicates,
)

pytestmark = [pytest.mark.integration, pytest.mark.ci]


@pytest.fixture()
def console() -> Console:
    return Console(quiet=True)


@pytest.fixture()
def dir_with_duplicates(tmp_path: Path) -> Path:
    """Directory containing one duplicate pair and one unique file."""
    content = b"identical bytes for duplicate detection"
    (tmp_path / "alpha.txt").write_bytes(content)
    (tmp_path / "beta.txt").write_bytes(content)
    (tmp_path / "unique.txt").write_bytes(b"something different")
    return tmp_path


@pytest.fixture()
def dir_no_duplicates(tmp_path: Path) -> Path:
    """Directory with no duplicates."""
    (tmp_path / "a.txt").write_bytes(b"aaa")
    (tmp_path / "b.txt").write_bytes(b"bbb")
    return tmp_path


class TestInitializeHashDetector:
    def test_returns_duplicate_detector(self) -> None:
        from file_organizer.services.deduplication.detector import DuplicateDetector

        detector = initialize_hash_detector()
        assert isinstance(detector, DuplicateDetector)

    def test_each_call_returns_new_instance(self) -> None:
        d1 = initialize_hash_detector()
        d2 = initialize_hash_detector()
        assert d1 is not d2


class TestCreateScanOptions:
    def test_defaults(self) -> None:
        from file_organizer.services.deduplication.detector import ScanOptions

        opts = create_scan_options("sha256")
        assert isinstance(opts, ScanOptions)
        assert opts.algorithm == "sha256"
        assert opts.recursive is True
        assert opts.min_file_size == 0
        assert opts.max_file_size is None
        assert opts.file_patterns is None
        assert opts.exclude_patterns is None

    def test_custom_values(self) -> None:
        opts = create_scan_options(
            "md5",
            recursive=False,
            min_file_size=512,
            max_file_size=1024 * 1024,
            file_patterns=["*.jpg"],
            exclude_patterns=["*.tmp"],
        )
        assert opts.algorithm == "md5"
        assert opts.recursive is False
        assert opts.min_file_size == 512
        assert opts.max_file_size == 1024 * 1024
        assert opts.file_patterns == ["*.jpg"]
        assert opts.exclude_patterns == ["*.tmp"]

    def test_progress_callback_is_stored(self) -> None:
        cb = MagicMock()
        opts = create_scan_options("sha256", progress_callback=cb)
        assert opts.progress_callback is cb


class TestProgressTracker:
    def test_callback_no_tqdm_is_noop(self, console: Console) -> None:
        """When tqdm is absent, callback() must not raise."""
        tracker = ProgressTracker(console)
        tracker.has_tqdm = False  # force the no-tqdm path
        tracker.callback(1, 10)  # should not raise
        tracker.close()  # should not raise

    def test_close_with_no_bar_is_safe(self, console: Console) -> None:
        tracker = ProgressTracker(console)
        tracker.progress_bar = None
        tracker.close()  # must not raise


class TestScanForDuplicates:
    def test_finds_duplicate_pair(self, dir_with_duplicates: Path, console: Console) -> None:
        detector = initialize_hash_detector()
        opts = create_scan_options("sha256")
        groups = scan_for_duplicates(dir_with_duplicates, detector, opts, console)

        assert len(groups) == 1
        group = next(iter(groups.values()))
        assert group.count == 2
        found_names = {f.path.name for f in group.files}
        assert found_names == {"alpha.txt", "beta.txt"}

    def test_returns_empty_when_no_duplicates(
        self, dir_no_duplicates: Path, console: Console
    ) -> None:
        detector = initialize_hash_detector()
        opts = create_scan_options("sha256")
        groups = scan_for_duplicates(dir_no_duplicates, detector, opts, console)

        assert groups == {}

    def test_progress_tracker_closed_after_scan(
        self, dir_with_duplicates: Path, console: Console
    ) -> None:
        detector = initialize_hash_detector()
        opts = create_scan_options("sha256")
        tracker = ProgressTracker(console)
        tracker.progress_bar = MagicMock()  # sentinel: proves close() was called
        scan_for_duplicates(dir_with_duplicates, detector, opts, console, tracker)
        assert tracker.progress_bar is None  # closed after scan
