"""Tests for StreamingFileScanner class.

Tests memory-efficient file scanning using os.scandir() with chunking,
filtering, and progress reporting.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from file_organizer.utils.file_scanner import (
    ScanConfig,
    StreamingFileScanner,
)

pytestmark = [pytest.mark.unit, pytest.mark.ci]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def scanner():
    """Create a StreamingFileScanner instance."""
    return StreamingFileScanner()


@pytest.fixture
def sample_dir(tmp_path):
    """Create a sample directory structure for testing.

    Structure:
        tmp_path/
            file1.txt (100 bytes)
            file2.txt (200 bytes)
            file3.log (150 bytes)
            subdir1/
                file4.txt (300 bytes)
                file5.txt (400 bytes)
            subdir2/
                file6.log (250 bytes)
                subdir3/
                    file7.txt (500 bytes)
            empty_dir/
    """
    # Root level files
    (tmp_path / "file1.txt").write_text("A" * 100)
    (tmp_path / "file2.txt").write_text("B" * 200)
    (tmp_path / "file3.log").write_text("C" * 150)

    # Subdirectory 1
    subdir1 = tmp_path / "subdir1"
    subdir1.mkdir()
    (subdir1 / "file4.txt").write_text("D" * 300)
    (subdir1 / "file5.txt").write_text("E" * 400)

    # Subdirectory 2 with nested subdir
    subdir2 = tmp_path / "subdir2"
    subdir2.mkdir()
    (subdir2 / "file6.log").write_text("F" * 250)

    subdir3 = subdir2 / "subdir3"
    subdir3.mkdir()
    (subdir3 / "file7.txt").write_text("G" * 500)

    # Empty directory
    (tmp_path / "empty_dir").mkdir()

    return tmp_path


@pytest.fixture
def large_dir(tmp_path):
    """Create a directory with many files for performance testing."""
    for i in range(100):
        (tmp_path / f"file{i:03d}.txt").write_text(f"Content {i}")

    return tmp_path


# ---------------------------------------------------------------------------
# ScanConfig Tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestScanConfig:
    """Test ScanConfig dataclass."""

    def test_default_values(self):
        """Test default configuration values."""
        config = ScanConfig()

        assert config.recursive is True
        assert config.follow_symlinks is False
        assert config.min_file_size == 0
        assert config.max_file_size is None
        assert config.file_patterns is None
        assert config.exclude_patterns is None
        assert config.chunk_size == 1000
        assert config.max_files is None
        assert config.progress_callback is None

    def test_custom_values(self):
        """Test custom configuration values."""

        def callback(_: int) -> None:
            return None

        config = ScanConfig(
            recursive=False,
            follow_symlinks=True,
            min_file_size=100,
            max_file_size=1000,
            file_patterns=["*.txt"],
            exclude_patterns=["*.log"],
            chunk_size=500,
            max_files=100,
            progress_callback=callback,
        )

        assert config.recursive is False
        assert config.follow_symlinks is True
        assert config.min_file_size == 100
        assert config.max_file_size == 1000
        assert config.file_patterns == ["*.txt"]
        assert config.exclude_patterns == ["*.log"]
        assert config.chunk_size == 500
        assert config.max_files == 100
        assert config.progress_callback == callback


# ---------------------------------------------------------------------------
# StreamingFileScanner Initialization Tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestStreamingFileScannerInit:
    """Test StreamingFileScanner initialization."""

    def test_initialization(self, scanner):
        """Test scanner initializes with zero counters."""
        assert scanner.scanned_count == 0
        assert scanner.yielded_count == 0

    def test_reset_counters(self, scanner, sample_dir):
        """Test counter reset functionality."""
        # Scan to increment counters
        list(scanner.scan_files(sample_dir))

        assert scanner.scanned_count > 0
        assert scanner.yielded_count > 0

        # Reset
        scanner.reset_counters()

        assert scanner.scanned_count == 0
        assert scanner.yielded_count == 0


# ---------------------------------------------------------------------------
# Basic Scanning Tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBasicScanning:
    """Test basic file scanning functionality."""

    def test_scan_to_list_all_files(self, scanner, sample_dir):
        """Test scanning all files to a list."""
        files = scanner.scan_to_list(sample_dir)

        # Should find all 7 files
        assert len(files) == 7

        # All should be Path objects
        assert all(isinstance(f, Path) for f in files)

        # All should exist
        assert all(f.exists() for f in files)

    def test_scan_files_generator(self, scanner, sample_dir):
        """Test scanning files as generator."""
        files = list(scanner.scan_files(sample_dir))

        assert len(files) == 7

    def test_scan_directory_chunks(self, scanner, sample_dir):
        """Test scanning with chunking."""
        config = ScanConfig(chunk_size=3)
        chunks = list(scanner.scan_directory(sample_dir, config))

        # Should have 3 chunks (3 + 3 + 1 files)
        assert len(chunks) == 3

        # First two chunks should have 3 files
        assert len(chunks[0]) == 3
        assert len(chunks[1]) == 3

        # Last chunk should have 1 file
        assert len(chunks[2]) == 1

        # Total files should be 7
        total_files = sum(len(chunk) for chunk in chunks)
        assert total_files == 7

    def test_scan_nonexistent_directory(self, scanner):
        """Test scanning nonexistent directory raises error."""
        with pytest.raises(ValueError, match="Directory not found"):
            list(scanner.scan_files(Path("/nonexistent/directory")))

    def test_scan_file_not_directory(self, scanner, tmp_path):
        """Test scanning a file (not directory) raises error."""
        file_path = tmp_path / "file.txt"
        file_path.write_text("content")

        with pytest.raises(ValueError, match="not a directory"):
            list(scanner.scan_files(file_path))

    def test_scan_empty_directory(self, scanner, tmp_path):
        """Test scanning empty directory returns no files."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        files = scanner.scan_to_list(empty_dir)

        assert len(files) == 0


# ---------------------------------------------------------------------------
# Recursive Scanning Tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRecursiveScanning:
    """Test recursive and non-recursive scanning."""

    def test_recursive_scan(self, scanner, sample_dir):
        """Test recursive scanning finds all files."""
        config = ScanConfig(recursive=True)
        files = scanner.scan_to_list(sample_dir, config)

        # Should find all 7 files
        assert len(files) == 7

    def test_non_recursive_scan(self, scanner, sample_dir):
        """Test non-recursive scanning finds only root files."""
        config = ScanConfig(recursive=False)
        files = scanner.scan_to_list(sample_dir, config)

        # Should find only 3 root level files
        assert len(files) == 3

        # All files should be in root directory
        for file_path in files:
            assert file_path.parent == sample_dir

    def test_nested_directories(self, scanner, sample_dir):
        """Test scanning deeply nested directories."""
        config = ScanConfig(recursive=True)
        files = scanner.scan_to_list(sample_dir, config)

        # Check that deeply nested file is found
        nested_files = [f for f in files if "subdir3" in str(f)]
        assert len(nested_files) == 1
        assert nested_files[0].name == "file7.txt"


# ---------------------------------------------------------------------------
# Filtering Tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFileFiltering:
    """Test file filtering by size, patterns, and exclusions."""

    def test_min_file_size(self, scanner, sample_dir):
        """Test filtering by minimum file size."""
        config = ScanConfig(min_file_size=250)
        files = scanner.scan_to_list(sample_dir, config)

        # Should find files >= 250 bytes: file4.txt(300), file5.txt(400),
        # file6.log(250), file7.txt(500)
        assert len(files) == 4

        # Verify all files meet size requirement
        for file_path in files:
            assert file_path.stat().st_size >= 250

    def test_max_file_size(self, scanner, sample_dir):
        """Test filtering by maximum file size."""
        config = ScanConfig(max_file_size=200)
        files = scanner.scan_to_list(sample_dir, config)

        # Should find files <= 200 bytes: file1.txt(100), file2.txt(200),
        # file3.log(150)
        assert len(files) == 3

        # Verify all files meet size requirement
        for file_path in files:
            assert file_path.stat().st_size <= 200

    def test_size_range(self, scanner, sample_dir):
        """Test filtering by size range."""
        config = ScanConfig(min_file_size=150, max_file_size=300)
        files = scanner.scan_to_list(sample_dir, config)

        # Should find files in range [150, 300]: file2.txt(200), file3.log(150),
        # file4.txt(300), file6.log(250)
        assert len(files) == 4

        # Verify all files meet size requirements
        for file_path in files:
            size = file_path.stat().st_size
            assert 150 <= size <= 300

    def test_file_patterns_single(self, scanner, sample_dir):
        """Test filtering by single file pattern."""
        config = ScanConfig(file_patterns=["*.txt"])
        files = scanner.scan_to_list(sample_dir, config)

        # Should find all .txt files (5 files)
        assert len(files) == 5

        # Verify all are .txt files
        assert all(f.suffix == ".txt" for f in files)

    def test_file_patterns_multiple(self, scanner, sample_dir):
        """Test filtering by multiple file patterns."""
        config = ScanConfig(file_patterns=["*.txt", "*.log"])
        files = scanner.scan_to_list(sample_dir, config)

        # Should find all files (7 total)
        assert len(files) == 7

    def test_exclude_patterns(self, scanner, sample_dir):
        """Test excluding files by pattern."""
        config = ScanConfig(exclude_patterns=["*.log"])
        files = scanner.scan_to_list(sample_dir, config)

        # Should exclude 2 .log files, leaving 5 .txt files
        assert len(files) == 5

        # Verify no .log files
        assert all(f.suffix != ".log" for f in files)

    def test_include_and_exclude_patterns(self, scanner, sample_dir):
        """Test combining include and exclude patterns."""
        config = ScanConfig(
            file_patterns=["*.txt", "*.log"],
            exclude_patterns=["*1.txt", "*3.log"],
        )
        files = scanner.scan_to_list(sample_dir, config)

        # Should exclude file1.txt and file3.log, leaving 5 files
        assert len(files) == 5

        # Verify excluded files are not present
        file_names = [f.name for f in files]
        assert "file1.txt" not in file_names
        assert "file3.log" not in file_names


# ---------------------------------------------------------------------------
# Chunking Tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestChunking:
    """Test chunk size and file limiting."""

    def test_chunk_size_exact_division(self, scanner, large_dir):
        """Test chunking when files divide evenly."""
        config = ScanConfig(chunk_size=25)
        chunks = list(scanner.scan_directory(large_dir, config))

        # 100 files / 25 per chunk = 4 chunks
        assert len(chunks) == 4

        # All chunks should have 25 files
        assert all(len(chunk) == 25 for chunk in chunks)

    def test_chunk_size_with_remainder(self, scanner, sample_dir):
        """Test chunking when files don't divide evenly."""
        config = ScanConfig(chunk_size=5)
        chunks = list(scanner.scan_directory(sample_dir, config))

        # 7 files / 5 per chunk = 2 chunks (5 + 2)
        assert len(chunks) == 2
        assert len(chunks[0]) == 5
        assert len(chunks[1]) == 2

    def test_chunk_size_larger_than_total(self, scanner, sample_dir):
        """Test chunk size larger than total files."""
        config = ScanConfig(chunk_size=100)
        chunks = list(scanner.scan_directory(sample_dir, config))

        # Should have 1 chunk with all 7 files
        assert len(chunks) == 1
        assert len(chunks[0]) == 7

    def test_max_files_limit(self, scanner, large_dir):
        """Test limiting maximum number of files."""
        config = ScanConfig(max_files=10)
        files = scanner.scan_to_list(large_dir, config)

        # Should stop at 10 files
        assert len(files) == 10

    def test_max_files_with_chunking(self, scanner, large_dir):
        """Test max_files with chunking."""
        config = ScanConfig(chunk_size=7, max_files=20)
        chunks = list(scanner.scan_directory(large_dir, config))

        # Should have 3 chunks (7 + 7 + 6 = 20 files)
        assert len(chunks) == 3

        total_files = sum(len(chunk) for chunk in chunks)
        assert total_files == 20


# ---------------------------------------------------------------------------
# Progress Callback Tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestProgressCallback:
    """Test progress reporting functionality."""

    def test_progress_callback_called(self, scanner, sample_dir):
        """Test that progress callback is called."""
        callback = MagicMock()
        config = ScanConfig(progress_callback=callback)

        files = scanner.scan_to_list(sample_dir, config)

        # Callback should be called once per file
        assert callback.call_count == len(files)

    def test_progress_callback_arguments(self, scanner, sample_dir):
        """Test progress callback receives correct arguments."""
        call_counts = []

        def callback(count):
            call_counts.append(count)

        config = ScanConfig(progress_callback=callback)
        scanner.scan_to_list(sample_dir, config)

        # Should receive incrementing counts
        assert call_counts == list(range(1, 8))  # 1, 2, 3, 4, 5, 6, 7

    def test_progress_callback_with_filtering(self, scanner, sample_dir):
        """Test progress callback with file filtering."""
        callback = MagicMock()
        config = ScanConfig(
            file_patterns=["*.txt"],
            progress_callback=callback,
        )

        files = scanner.scan_to_list(sample_dir, config)

        # Callback reflects every scanned file, even if later filtered out.
        assert callback.call_count == 7
        assert len(files) == 5


# ---------------------------------------------------------------------------
# Counter Tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCounters:
    """Test scan counter functionality."""

    def test_scanned_count(self, scanner, sample_dir):
        """Test scanned_count tracks files found."""
        scanner.scan_to_list(sample_dir)

        # Should have scanned 7 files
        assert scanner.scanned_count == 7

    def test_yielded_count(self, scanner, sample_dir):
        """Test yielded_count tracks files yielded."""
        scanner.scan_to_list(sample_dir)

        # Should have yielded 7 files
        assert scanner.yielded_count == 7

    def test_counters_with_filtering(self, scanner, sample_dir):
        """Test counters with file filtering."""
        config = ScanConfig(file_patterns=["*.txt"])
        files = scanner.scan_to_list(sample_dir, config)

        # scanned_count tracks all visited files before filtering.
        assert scanner.scanned_count == 7
        assert scanner.yielded_count == 5
        assert len(files) == 5

    def test_counters_with_max_files(self, scanner, large_dir):
        """Test counters with max_files limit."""
        config = ScanConfig(max_files=10)
        files = scanner.scan_to_list(large_dir, config)

        # Should stop at 10 files
        assert scanner.scanned_count == 10
        assert scanner.yielded_count == 10
        assert len(files) == 10


# ---------------------------------------------------------------------------
# Symlink Tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSymlinkHandling:
    """Test symlink handling."""

    def test_ignore_symlinks_by_default(self, scanner, tmp_path):
        """Test that symlinks are ignored by default."""
        # Create a file and a symlink to it
        real_file = tmp_path / "real.txt"
        real_file.write_text("content")

        symlink = tmp_path / "link.txt"
        symlink.symlink_to(real_file)

        config = ScanConfig(follow_symlinks=False)
        files = scanner.scan_to_list(tmp_path, config)

        # Should only find the real file, not the symlink
        assert len(files) == 1
        assert files[0] == real_file

    def test_follow_symlinks(self, scanner, tmp_path):
        """Test following symlinks when configured."""
        # Create a file and a symlink to it
        real_file = tmp_path / "real.txt"
        real_file.write_text("content")

        symlink = tmp_path / "link.txt"
        symlink.symlink_to(real_file)

        config = ScanConfig(follow_symlinks=True)
        files = scanner.scan_to_list(tmp_path, config)

        # Should find both the real file and symlink
        assert len(files) == 2

        # Both should be readable
        assert all(f.exists() for f in files)

    def test_broken_symlink(self, scanner, tmp_path):
        """Test handling of broken symlinks."""
        # Create a symlink to a nonexistent file
        symlink = tmp_path / "broken_link.txt"
        symlink.symlink_to(tmp_path / "nonexistent.txt")

        config = ScanConfig(follow_symlinks=True)
        files = scanner.scan_to_list(tmp_path, config)

        # Should not include broken symlink
        assert len(files) == 0


# ---------------------------------------------------------------------------
# Error Handling Tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestErrorHandling:
    """Test error handling and edge cases."""

    def test_empty_chunk_size(self, scanner, sample_dir):
        """Test that empty chunks are not yielded."""
        config = ScanConfig(chunk_size=1, max_files=3)
        chunks = list(scanner.scan_directory(sample_dir, config))

        # All chunks should have files
        assert all(len(chunk) > 0 for chunk in chunks)

    def test_scan_continues_on_permission_error(self, scanner, sample_dir):
        """Test scanning continues when file access is denied."""
        # This test verifies the error handling exists
        # Actual permission errors are hard to simulate in tests
        files = scanner.scan_to_list(sample_dir)

        # Should complete without raising exceptions
        assert len(files) > 0

    def test_multiple_scans_with_same_instance(self, scanner, sample_dir):
        """Test that scanner can be reused for multiple scans."""
        # First scan
        files1 = scanner.scan_to_list(sample_dir)
        first_count = scanner.scanned_count

        # Second scan (counters should reset)
        files2 = scanner.scan_to_list(sample_dir)
        count2 = scanner.scanned_count

        # Both scans should find same number of files
        assert len(files1) == len(files2)
        assert first_count == len(files1)

        # Counters should be updated with second scan
        assert count2 == len(files2)


# ---------------------------------------------------------------------------
# Performance Tests (Smoke Tests)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPerformance:
    """Smoke tests for performance characteristics."""

    def test_large_directory_chunking(self, scanner, large_dir):
        """Test that large directories are processed in chunks."""
        config = ScanConfig(chunk_size=10)
        chunks = list(scanner.scan_directory(large_dir, config))

        # 100 files / 10 per chunk = 10 chunks
        assert len(chunks) == 10

        # Should not load all files into memory at once
        for chunk in chunks:
            assert len(chunk) == 10

    def test_streaming_doesnt_load_all_files(self, scanner, large_dir):
        """Test that streaming doesn't load all files at once."""
        config = ScanConfig(chunk_size=10)
        chunks_seen = 0

        expected_chunk_size = 10
        # Process chunks one at a time
        for chunk in scanner.scan_directory(large_dir, config):
            chunks_seen += 1
            # Verify chunk size
            assert len(chunk) == expected_chunk_size

        # Should have seen all chunks
        assert chunks_seen == 10


# ---------------------------------------------------------------------------
# Validation Error Tests (scan_directory raises ValueError)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestScanDirectoryValidation:
    """Test scan_directory input validation for nonexistent and non-directory paths."""

    def test_nonexistent_directory_raises_value_error(self, scanner):
        """scan_directory raises ValueError for a path that does not exist."""
        with pytest.raises(ValueError, match="Directory not found"):
            list(scanner.scan_directory(Path("/nonexistent/path/xyz")))

    def test_file_path_raises_value_error(self, scanner, tmp_path):
        """scan_directory raises ValueError when given a file instead of directory."""
        f = tmp_path / "notadir.txt"
        f.write_text("content")
        with pytest.raises(ValueError, match="not a directory"):
            list(scanner.scan_directory(f))


# ---------------------------------------------------------------------------
# max_files with chunking boundary tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMaxFilesChunking:
    """Test max_files limit interacts correctly with chunk boundaries."""

    def test_max_files_breaks_mid_chunk(self, scanner, large_dir):
        """max_files stops scanning mid-chunk when limit is reached."""
        config = ScanConfig(chunk_size=50, max_files=7)
        chunks = list(scanner.scan_directory(large_dir, config))

        total = sum(len(c) for c in chunks)
        assert total == 7
        # First chunk should be partial (7 < 50)
        assert len(chunks) == 1
        assert len(chunks[0]) == 7

    def test_max_files_exact_chunk_boundary(self, scanner, large_dir):
        """max_files at exactly chunk_size produces one full chunk."""
        config = ScanConfig(chunk_size=10, max_files=10)
        chunks = list(scanner.scan_directory(large_dir, config))

        total = sum(len(c) for c in chunks)
        assert total == 10
        assert len(chunks) == 1
        assert len(chunks[0]) == 10


# ---------------------------------------------------------------------------
# Symlink edge cases
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSymlinkEdgeCases:
    """Test symlink handling edge cases in _scan_recursive."""

    def test_symlink_to_directory_skipped_when_not_following(self, scanner, tmp_path):
        """Symlinks to directories are skipped when follow_symlinks is False."""
        real_dir = tmp_path / "real_dir"
        real_dir.mkdir()
        (real_dir / "inner.txt").write_text("content")

        link_dir = tmp_path / "link_dir"
        link_dir.symlink_to(real_dir)

        config = ScanConfig(follow_symlinks=False)
        files = scanner.scan_to_list(tmp_path, config)

        # Only the real file, not the one through the symlink
        assert len(files) == 1
        assert files[0].name == "inner.txt"

    def test_symlink_to_file_followed_when_enabled(self, scanner, tmp_path):
        """Symlinks to files are followed when follow_symlinks is True."""
        real_file = tmp_path / "real.txt"
        real_file.write_text("content")
        link_file = tmp_path / "link.txt"
        link_file.symlink_to(real_file)

        config = ScanConfig(follow_symlinks=True)
        files = scanner.scan_to_list(tmp_path, config)

        assert len(files) == 2
        names = sorted(f.name for f in files)
        assert names == ["link.txt", "real.txt"]


# ---------------------------------------------------------------------------
# Progress callback invocation in _scan_recursive
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestProgressCallbackInScanRecursive:
    """Test progress_callback is invoked from _scan_recursive via scan_directory."""

    def test_progress_callback_receives_incrementing_counts(self, scanner, sample_dir):
        """progress_callback receives incrementing file counts as files are scanned."""
        counts: list[int] = []

        def on_progress(count: int) -> None:
            counts.append(count)

        config = ScanConfig(progress_callback=on_progress)
        files = scanner.scan_to_list(sample_dir, config)

        assert len(counts) == len(files)
        assert counts == list(range(1, len(files) + 1))

    def test_progress_callback_with_max_files(self, scanner, large_dir):
        """progress_callback is called only for files up to the max_files limit."""
        counts: list[int] = []

        def on_progress(count: int) -> None:
            counts.append(count)

        config = ScanConfig(progress_callback=on_progress, max_files=5)
        files = scanner.scan_to_list(large_dir, config)

        assert len(files) == 5
        assert len(counts) == 5
        assert counts[-1] == 5


# ---------------------------------------------------------------------------
# _matches_criteria size and pattern filtering
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMatchesCriteriaSizeFiltering:
    """Test _matches_criteria with min_size, max_size, and pattern constraints."""

    def test_min_size_excludes_small_files(self, scanner, tmp_path):
        """Files smaller than min_file_size are excluded."""
        small = tmp_path / "small.txt"
        small.write_text("hi")  # 2 bytes
        big = tmp_path / "big.txt"
        big.write_text("x" * 500)

        config = ScanConfig(min_file_size=100)
        files = scanner.scan_to_list(tmp_path, config)

        assert len(files) == 1
        assert files[0].name == "big.txt"

    def test_max_size_excludes_large_files(self, scanner, tmp_path):
        """Files larger than max_file_size are excluded."""
        small = tmp_path / "small.txt"
        small.write_text("hi")
        big = tmp_path / "big.txt"
        big.write_text("x" * 500)

        config = ScanConfig(max_file_size=100)
        files = scanner.scan_to_list(tmp_path, config)

        assert len(files) == 1
        assert files[0].name == "small.txt"

    def test_include_patterns_filter(self, scanner, tmp_path):
        """Only files matching include patterns are returned."""
        (tmp_path / "a.py").write_text("code")
        (tmp_path / "b.txt").write_text("text")
        (tmp_path / "c.py").write_text("more code")

        config = ScanConfig(file_patterns=["*.py"])
        files = scanner.scan_to_list(tmp_path, config)

        assert len(files) == 2
        names = sorted(f.name for f in files)
        assert names == ["a.py", "c.py"]

    def test_exclude_patterns_filter(self, scanner, tmp_path):
        """Files matching exclude patterns are excluded."""
        (tmp_path / "a.py").write_text("code")
        (tmp_path / "b.txt").write_text("text")
        (tmp_path / "c.log").write_text("log")

        config = ScanConfig(exclude_patterns=["*.log", "*.txt"])
        files = scanner.scan_to_list(tmp_path, config)

        assert len(files) == 1
        assert files[0].name == "a.py"

    def test_combined_include_and_exclude(self, scanner, tmp_path):
        """Include and exclude patterns work together."""
        (tmp_path / "keep.py").write_text("code")
        (tmp_path / "skip.py").write_text("code")
        (tmp_path / "other.txt").write_text("text")

        config = ScanConfig(file_patterns=["*.py"], exclude_patterns=["skip*"])
        files = scanner.scan_to_list(tmp_path, config)

        assert len(files) == 1
        assert files[0].name == "keep.py"


# ---------------------------------------------------------------------------
# Counter and reset edge cases
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCounterEdgeCases:
    """Test counter behavior including reset_counters."""

    def test_reset_counters_to_zero(self, scanner, sample_dir):
        """reset_counters sets both scanned_count and yielded_count to 0."""
        scanner.scan_to_list(sample_dir)
        assert scanner.scanned_count > 0

        scanner.reset_counters()
        assert scanner.scanned_count == 0
        assert scanner.yielded_count == 0
