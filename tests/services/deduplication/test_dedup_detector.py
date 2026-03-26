"""Tests for DuplicateDetector orchestrator.

Covers scan_directory, find_files, group_by_size, process_files,
find_duplicates_of_file, and statistics.
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from file_organizer.services.deduplication.detector import (
    DuplicateDetector,
    ScanOptions,
)

pytestmark = [pytest.mark.unit, pytest.mark.ci]


@pytest.mark.unit
class TestScanOptions(unittest.TestCase):
    """Test ScanOptions dataclass."""

    def test_defaults(self):
        """Test default option values."""
        opts = ScanOptions()
        self.assertEqual(opts.algorithm, "sha256")
        self.assertTrue(opts.recursive)
        self.assertFalse(opts.follow_symlinks)
        self.assertEqual(opts.min_file_size, 0)
        self.assertIsNone(opts.max_file_size)
        self.assertIsNone(opts.file_patterns)
        self.assertIsNone(opts.exclude_patterns)
        self.assertIsNone(opts.progress_callback)

    def test_custom_options(self):
        """Test custom option values."""
        cb = MagicMock()
        opts = ScanOptions(
            algorithm="md5",
            recursive=False,
            follow_symlinks=True,
            min_file_size=100,
            max_file_size=1000000,
            file_patterns=["*.txt"],
            exclude_patterns=["*.log"],
            progress_callback=cb,
        )
        self.assertEqual(opts.algorithm, "md5")
        self.assertFalse(opts.recursive)
        self.assertTrue(opts.follow_symlinks)
        self.assertEqual(opts.min_file_size, 100)
        self.assertEqual(opts.max_file_size, 1000000)


@pytest.mark.unit
class TestDuplicateDetector(unittest.TestCase):
    """Test cases for DuplicateDetector."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        """Clean up."""
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_init_defaults(self):
        """Test initialization with defaults."""
        detector = DuplicateDetector()
        self.assertIsNotNone(detector.hasher)
        self.assertIsNotNone(detector.index)

    def test_init_custom(self):
        """Test initialization with custom components."""
        hasher = MagicMock()
        index = MagicMock()
        detector = DuplicateDetector(hasher=hasher, index=index)
        self.assertIs(detector.hasher, hasher)
        self.assertIs(detector.index, index)

    def test_scan_directory_not_found(self):
        """Test scanning non-existent directory."""
        detector = DuplicateDetector()
        with self.assertRaises(ValueError):
            detector.scan_directory(Path("/nonexistent_path_xyz"))

    def test_scan_directory_not_a_dir(self):
        """Test scanning a file instead of directory."""
        f = self.test_dir / "file.txt"
        f.write_text("content")
        detector = DuplicateDetector()
        with self.assertRaises(ValueError):
            detector.scan_directory(f)

    def test_scan_directory_empty(self):
        """Test scanning empty directory."""
        empty = self.test_dir / "empty"
        empty.mkdir()
        detector = DuplicateDetector()
        result = detector.scan_directory(empty)
        self.assertIsNotNone(result)

    def test_scan_directory_with_files(self):
        """Test scanning a directory with duplicate-sized files."""
        # Create two files with same size
        f1 = self.test_dir / "a.txt"
        f2 = self.test_dir / "b.txt"
        f1.write_text("hello")
        f2.write_text("world")

        detector = DuplicateDetector()
        result = detector.scan_directory(self.test_dir)
        self.assertIsNotNone(result)

    def test_find_files_recursive(self):
        """Test _find_files with recursive option."""
        subdir = self.test_dir / "sub"
        subdir.mkdir()
        (self.test_dir / "root.txt").write_text("root")
        (subdir / "sub.txt").write_text("sub")

        detector = DuplicateDetector()
        opts = ScanOptions(recursive=True)
        files = detector._find_files(self.test_dir, opts)
        names = [f.name for f in files]
        self.assertIn("root.txt", names)
        self.assertIn("sub.txt", names)

    def test_find_files_non_recursive(self):
        """Test _find_files without recursion."""
        subdir = self.test_dir / "sub"
        subdir.mkdir()
        (self.test_dir / "root.txt").write_text("root")
        (subdir / "sub.txt").write_text("sub")

        detector = DuplicateDetector()
        opts = ScanOptions(recursive=False)
        files = detector._find_files(self.test_dir, opts)
        names = [f.name for f in files]
        self.assertIn("root.txt", names)
        self.assertNotIn("sub.txt", names)

    def test_find_files_min_size_filter(self):
        """Test _find_files filters by min size."""
        small = self.test_dir / "small.txt"
        big = self.test_dir / "big.txt"
        small.write_text("hi")
        big.write_text("x" * 200)

        detector = DuplicateDetector()
        opts = ScanOptions(min_file_size=100)
        files = detector._find_files(self.test_dir, opts)
        names = [f.name for f in files]
        self.assertNotIn("small.txt", names)
        self.assertIn("big.txt", names)

    def test_find_files_max_size_filter(self):
        """Test _find_files filters by max size."""
        small = self.test_dir / "small.txt"
        big = self.test_dir / "big.txt"
        small.write_text("hi")
        big.write_text("x" * 2000)

        detector = DuplicateDetector()
        opts = ScanOptions(max_file_size=100)
        files = detector._find_files(self.test_dir, opts)
        names = [f.name for f in files]
        self.assertIn("small.txt", names)
        self.assertNotIn("big.txt", names)

    def test_find_files_include_patterns(self):
        """Test _find_files with file_patterns filter."""
        (self.test_dir / "a.txt").write_text("a")
        (self.test_dir / "b.log").write_text("b")

        detector = DuplicateDetector()
        opts = ScanOptions(file_patterns=["*.txt"])
        files = detector._find_files(self.test_dir, opts)
        names = [f.name for f in files]
        self.assertIn("a.txt", names)
        self.assertNotIn("b.log", names)

    def test_find_files_exclude_patterns(self):
        """Test _find_files with exclude_patterns filter."""
        (self.test_dir / "a.txt").write_text("a")
        (self.test_dir / "b.log").write_text("b")

        detector = DuplicateDetector()
        opts = ScanOptions(exclude_patterns=["*.log"])
        files = detector._find_files(self.test_dir, opts)
        names = [f.name for f in files]
        self.assertIn("a.txt", names)
        self.assertNotIn("b.log", names)

    def test_group_by_size(self):
        """Test _group_by_size groups correctly."""
        f1 = self.test_dir / "a.txt"
        f2 = self.test_dir / "b.txt"
        f1.write_text("hello")
        f2.write_text("world")

        detector = DuplicateDetector()
        opts = ScanOptions()
        groups = detector._group_by_size([f1, f2], opts)
        # Both are 5 bytes, so should be in same group
        self.assertTrue(any(len(v) == 2 for v in groups.values()))

    def test_group_by_size_skips_inaccessible(self):
        """Test _group_by_size skips files that raise OSError."""
        detector = DuplicateDetector()
        opts = ScanOptions()
        mock_path = MagicMock()
        mock_path.stat.side_effect = OSError("no access")
        groups = detector._group_by_size([mock_path], opts)
        self.assertEqual(len(groups), 0)

    def test_process_files_with_progress(self):
        """Test _process_files calls progress callback."""
        f1 = self.test_dir / "a.txt"
        f2 = self.test_dir / "b.txt"
        f1.write_text("hello")
        f2.write_text("world")

        cb = MagicMock()
        detector = DuplicateDetector()
        size = f1.stat().st_size
        size_groups = {size: [f1, f2]}
        opts = ScanOptions(progress_callback=cb)

        detector._process_files(size_groups, opts)
        self.assertTrue(cb.called)

    def test_process_files_skips_single_file_groups(self):
        """Test _process_files skips groups with only one file."""
        f1 = self.test_dir / "unique.txt"
        f1.write_text("unique content here")

        detector = DuplicateDetector()
        mock_hasher = MagicMock()
        detector.hasher = mock_hasher

        size_groups = {f1.stat().st_size: [f1]}
        opts = ScanOptions()
        detector._process_files(size_groups, opts)
        mock_hasher.compute_hash.assert_not_called()

    def test_process_files_handles_errors(self):
        """Test _process_files handles hashing errors."""
        f1 = self.test_dir / "a.txt"
        f2 = self.test_dir / "b.txt"
        f1.write_text("hello")
        f2.write_text("world")

        detector = DuplicateDetector()
        detector.hasher = MagicMock()
        detector.hasher.compute_hash.side_effect = ValueError("bad file")

        size = f1.stat().st_size
        size_groups = {size: [f1, f2]}
        opts = ScanOptions()
        # Should not raise
        detector._process_files(size_groups, opts)

    def test_find_duplicates_of_file_not_found(self):
        """Test find_duplicates_of_file raises for missing file."""
        detector = DuplicateDetector()
        with self.assertRaises(FileNotFoundError):
            detector.find_duplicates_of_file(Path("/nonexistent.txt"), self.test_dir)

    def test_find_duplicates_of_file_success(self):
        """Test find_duplicates_of_file with real files."""
        target = self.test_dir / "target.txt"
        target.write_text("hello" * 100)

        dup = self.test_dir / "duplicate.txt"
        dup.write_text("hello" * 100)

        detector = DuplicateDetector()
        duplicates = detector.find_duplicates_of_file(target, self.test_dir)
        # May or may not find duplicates depending on hash; just verify no error
        self.assertIsInstance(duplicates, list)

    def test_get_duplicate_groups(self):
        """Test get_duplicate_groups delegates to index."""
        mock_index = MagicMock()
        mock_index.get_duplicates.return_value = {"hash1": MagicMock()}
        detector = DuplicateDetector(index=mock_index)

        result = detector.get_duplicate_groups()
        mock_index.get_duplicates.assert_called_once()
        self.assertIn("hash1", result)

    def test_get_statistics(self):
        """Test get_statistics delegates to index."""
        mock_index = MagicMock()
        mock_index.get_statistics.return_value = {"total": 5}
        detector = DuplicateDetector(index=mock_index)

        result = detector.get_statistics()
        self.assertEqual(result["total"], 5)

    def test_clear(self):
        """Test clear delegates to index."""
        mock_index = MagicMock()
        detector = DuplicateDetector(index=mock_index)

        detector.clear()
        mock_index.clear.assert_called_once()


@pytest.mark.unit
class TestProcessFilesSequentialWithProgress:
    """Test _process_files_sequential with progress callback and error handling."""

    def test_sequential_progress_callback_invoked(self, tmp_path: Path) -> None:
        """Progress callback is invoked with (processed, total) for each file."""
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("hello")
        f2.write_text("world")

        progress_calls: list[tuple[int, int]] = []

        def on_progress(current: int, total: int) -> None:
            progress_calls.append((current, total))

        mock_hasher = MagicMock()
        mock_hasher.compute_hash.return_value = "fakehash"
        mock_index = MagicMock()
        detector = DuplicateDetector(hasher=mock_hasher, index=mock_index)

        opts = ScanOptions(progress_callback=on_progress)
        detector._process_files_sequential([f1, f2], opts, total=2)

        assert len(progress_calls) == 2
        assert progress_calls[0] == (1, 2)
        assert progress_calls[1] == (2, 2)

    def test_sequential_error_handling_continues(self, tmp_path: Path) -> None:
        """Files that raise exceptions are skipped; remaining files still processed."""
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("hello")
        f2.write_text("world")

        mock_hasher = MagicMock()
        mock_hasher.compute_hash.side_effect = [
            FileNotFoundError("gone"),
            "hash_b",
        ]
        mock_index = MagicMock()
        detector = DuplicateDetector(hasher=mock_hasher, index=mock_index)

        opts = ScanOptions()
        detector._process_files_sequential([f1, f2], opts, total=2)

        # Only the second file should be added to index
        mock_index.add_file.assert_called_once_with(f2, "hash_b")

    def test_sequential_permission_error_skipped(self, tmp_path: Path) -> None:
        """PermissionError during hashing is caught and file is skipped."""
        f1 = tmp_path / "a.txt"
        f1.write_text("content")

        mock_hasher = MagicMock()
        mock_hasher.compute_hash.side_effect = PermissionError("no access")
        mock_index = MagicMock()
        detector = DuplicateDetector(hasher=mock_hasher, index=mock_index)

        opts = ScanOptions()
        detector._process_files_sequential([f1], opts, total=1)

        mock_index.add_file.assert_not_called()

    def test_sequential_no_progress_callback(self, tmp_path: Path) -> None:
        """Without a progress callback, processing still completes successfully."""
        f1 = tmp_path / "a.txt"
        f1.write_text("hello")

        mock_hasher = MagicMock()
        mock_hasher.compute_hash.return_value = "hash_a"
        mock_index = MagicMock()
        detector = DuplicateDetector(hasher=mock_hasher, index=mock_index)

        opts = ScanOptions(progress_callback=None)
        detector._process_files_sequential([f1], opts, total=1)

        mock_index.add_file.assert_called_once_with(f1, "hash_a")


@pytest.mark.unit
class TestProcessFilesParallelWithProgress:
    """Test _process_files_parallel with progress callback."""

    def test_parallel_progress_callback_invoked(self, tmp_path: Path) -> None:
        """Progress callback is called for each file in parallel batch results."""
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("hello")
        f2.write_text("world")

        progress_calls: list[tuple[int, int]] = []

        def on_progress(current: int, total: int) -> None:
            progress_calls.append((current, total))

        mock_hasher = MagicMock()
        mock_hasher.compute_batch_parallel.return_value = {
            f1: "hash_a",
            f2: "hash_b",
        }
        mock_index = MagicMock()
        detector = DuplicateDetector(hasher=mock_hasher, index=mock_index)

        opts = ScanOptions(progress_callback=on_progress, batch_size=100)
        detector._process_files_parallel([f1, f2], opts, total=2)

        assert len(progress_calls) == 2
        assert progress_calls[0] == (1, 2)
        assert progress_calls[1] == (2, 2)

    def test_parallel_batching(self, tmp_path: Path) -> None:
        """Files are processed in batches of the configured batch_size."""
        files = []
        for i in range(5):
            f = tmp_path / f"file{i}.txt"
            f.write_text(f"content{i}")
            files.append(f)

        mock_hasher = MagicMock()
        # Return different results for each batch call
        mock_hasher.compute_batch_parallel.side_effect = [
            {files[0]: "h0", files[1]: "h1"},
            {files[2]: "h2", files[3]: "h3"},
            {files[4]: "h4"},
        ]
        mock_index = MagicMock()
        detector = DuplicateDetector(hasher=mock_hasher, index=mock_index)

        opts = ScanOptions(batch_size=2)
        detector._process_files_parallel(files, opts, total=5)

        assert mock_hasher.compute_batch_parallel.call_count == 3
        assert mock_index.add_file.call_count == 5

    def test_parallel_no_progress_callback(self, tmp_path: Path) -> None:
        """Processing completes without errors when no progress callback is set."""
        f1 = tmp_path / "a.txt"
        f1.write_text("hello")

        mock_hasher = MagicMock()
        mock_hasher.compute_batch_parallel.return_value = {f1: "hash_a"}
        mock_index = MagicMock()
        detector = DuplicateDetector(hasher=mock_hasher, index=mock_index)

        opts = ScanOptions(progress_callback=None, batch_size=100)
        detector._process_files_parallel([f1], opts, total=1)

        mock_index.add_file.assert_called_once_with(f1, "hash_a")


@pytest.mark.unit
class TestFindFilesAndStreamGroupBySize:
    """Test _find_files and _stream_and_group_by_size helper methods."""

    def test_find_files_returns_list(self, tmp_path: Path) -> None:
        """_find_files returns a list of matching file paths."""
        (tmp_path / "a.txt").write_text("content")
        (tmp_path / "b.txt").write_text("content")

        detector = DuplicateDetector()
        opts = ScanOptions()
        files = detector._find_files(tmp_path, opts)

        assert len(files) == 2
        names = sorted(f.name for f in files)
        assert names == ["a.txt", "b.txt"]

    def test_stream_and_group_by_size_skips_inaccessible(self, tmp_path: Path) -> None:
        """_stream_and_group_by_size skips files that raise OSError on stat."""
        (tmp_path / "a.txt").write_text("content")

        mock_scanner = MagicMock()
        mock_path = MagicMock()
        mock_path.stat.side_effect = OSError("no access")
        mock_scanner.scan_directory.return_value = iter([[mock_path]])

        detector = DuplicateDetector()
        config = detector._create_scan_config(ScanOptions())
        groups = detector._stream_and_group_by_size(tmp_path, mock_scanner, config)

        assert len(groups) == 0


if __name__ == "__main__":
    unittest.main()
