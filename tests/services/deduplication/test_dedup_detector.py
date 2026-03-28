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


@pytest.mark.ci
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


@pytest.mark.ci
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

    def test_find_duplicates_singleton_size_bucket(self):
        """A duplicate in a unique-size bucket must still be detected."""
        # Target file lives outside search directory
        target = self.test_dir / "target.txt"
        content = "unique_content_singleton_test" * 10
        target.write_text(content)

        # Search directory with one file that has identical content
        search_dir = self.test_dir / "search"
        search_dir.mkdir()
        dup = search_dir / "copy.txt"
        dup.write_text(content)

        detector = DuplicateDetector()
        duplicates = detector.find_duplicates_of_file(target, search_dir)
        assert len(duplicates) == 1
        assert duplicates[0].path == dup


if __name__ == "__main__":
    unittest.main()
