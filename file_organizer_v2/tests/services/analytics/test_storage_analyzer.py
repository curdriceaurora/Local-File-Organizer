"""Tests for StorageAnalyzer."""

import tempfile
from pathlib import Path

import pytest

from file_organizer.models.analytics import FileDistribution, StorageStats
from file_organizer.services.analytics import StorageAnalyzer


@pytest.fixture
def temp_directory():
    """Create a temporary directory with test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # Create test structure
        (tmp_path / "folder1").mkdir()
        (tmp_path / "folder2").mkdir()

        (tmp_path / "file1.txt").write_text("test content")
        (tmp_path / "folder1" / "file2.py").write_text("print('hello')")
        (tmp_path / "folder2" / "file3.jpg").write_bytes(b"fake image" * 100)

        yield tmp_path


class TestStorageAnalyzer:
    """Test suite for StorageAnalyzer."""

    def test_initialization(self):
        """Test analyzer initialization."""
        analyzer = StorageAnalyzer()
        assert analyzer.cache_ttl == 3600
        assert isinstance(analyzer._cache, dict)

    def test_analyze_directory(self, temp_directory):
        """Test directory analysis."""
        analyzer = StorageAnalyzer()
        stats = analyzer.analyze_directory(temp_directory)

        assert isinstance(stats, StorageStats)
        assert stats.file_count == 3
        assert stats.directory_count == 2
        assert stats.total_size > 0

    def test_analyze_invalid_directory(self):
        """Test error handling for invalid directory."""
        analyzer = StorageAnalyzer()

        with pytest.raises(ValueError, match="Invalid directory"):
            analyzer.analyze_directory(Path("/nonexistent/path"))

    def test_analyze_file_instead_of_directory(self, temp_directory):
        """Test error handling when given a file instead of directory."""
        analyzer = StorageAnalyzer()
        file_path = temp_directory / "file1.txt"

        with pytest.raises(ValueError, match="Invalid directory"):
            analyzer.analyze_directory(file_path)

    def test_calculate_size_distribution(self, temp_directory):
        """Test file size distribution calculation."""
        analyzer = StorageAnalyzer()
        distribution = analyzer.calculate_size_distribution(temp_directory)

        assert isinstance(distribution, FileDistribution)
        assert distribution.total_files == 3
        assert len(distribution.by_type) > 0
        assert ".txt" in distribution.by_type or ".py" in distribution.by_type

    def test_identify_large_files(self, temp_directory):
        """Test large file identification."""
        # Create a large file
        large_file = temp_directory / "large.bin"
        large_file.write_bytes(b"x" * (150 * 1024 * 1024))  # 150MB

        analyzer = StorageAnalyzer()
        large_files = analyzer.identify_large_files(
            temp_directory, threshold=100 * 1024 * 1024
        )

        assert len(large_files) == 1
        assert large_files[0].path == large_file
        assert large_files[0].size > 100 * 1024 * 1024

    def test_get_duplicate_space(self, temp_directory):
        """Test duplicate space calculation."""
        # Create duplicate files
        dup1 = temp_directory / "dup1.txt"
        dup2 = temp_directory / "dup2.txt"
        content = "duplicate content" * 100
        dup1.write_text(content)
        dup2.write_text(content)

        analyzer = StorageAnalyzer()
        duplicate_groups = [{"files": [str(dup1), str(dup2)]}]

        wasted_space = analyzer.get_duplicate_space(duplicate_groups)

        assert wasted_space > 0
        # Wasted space should be the size of one file (keeping one, removing one)
        assert wasted_space == dup1.stat().st_size

    def test_caching(self, temp_directory):
        """Test result caching."""
        analyzer = StorageAnalyzer()

        # First call - should cache
        stats1 = analyzer.analyze_directory(temp_directory, use_cache=True)

        # Second call - should use cache
        stats2 = analyzer.analyze_directory(temp_directory, use_cache=True)

        # Results should be identical
        assert stats1.file_count == stats2.file_count
        assert stats1.total_size == stats2.total_size

    def test_cache_clear(self, temp_directory):
        """Test cache clearing."""
        analyzer = StorageAnalyzer()

        # Populate cache
        analyzer.analyze_directory(temp_directory)
        assert len(analyzer._cache) > 0

        # Clear cache
        analyzer.clear_cache()
        assert len(analyzer._cache) == 0

    def test_max_depth_parameter(self, temp_directory):
        """Test max depth parameter."""
        # Create nested structure
        (temp_directory / "d1" / "d2" / "d3").mkdir(parents=True)
        (temp_directory / "d1" / "d2" / "d3" / "deep.txt").write_text("deep")

        analyzer = StorageAnalyzer()

        # Analyze with depth limit
        stats_limited = analyzer.analyze_directory(temp_directory, max_depth=1)
        stats_unlimited = analyzer.analyze_directory(temp_directory, max_depth=None)

        # Unlimited should find more files
        assert stats_unlimited.file_count >= stats_limited.file_count

    def test_size_by_type(self, temp_directory):
        """Test size breakdown by file type."""
        analyzer = StorageAnalyzer()
        stats = analyzer.analyze_directory(temp_directory)

        assert len(stats.size_by_type) > 0
        assert all(size >= 0 for size in stats.size_by_type.values())

    def test_largest_files_ordering(self, temp_directory):
        """Test that largest files are properly ordered."""
        # Create files of different sizes
        (temp_directory / "small.txt").write_text("x" * 100)
        (temp_directory / "medium.txt").write_text("x" * 1000)
        (temp_directory / "large.txt").write_text("x" * 10000)

        analyzer = StorageAnalyzer()
        stats = analyzer.analyze_directory(temp_directory)

        # Largest files should be in descending order
        for i in range(len(stats.largest_files) - 1):
            assert stats.largest_files[i].size >= stats.largest_files[i + 1].size

    def test_empty_directory(self):
        """Test handling of empty directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            analyzer = StorageAnalyzer()
            stats = analyzer.analyze_directory(tmp_path)

            assert stats.file_count == 0
            assert stats.total_size == 0
            assert len(stats.largest_files) == 0

    def test_size_distribution_ranges(self, temp_directory):
        """Test size distribution range categorization."""
        # Create files in different size ranges
        (temp_directory / "tiny.txt").write_bytes(b"x" * 100)  # < 1KB
        (temp_directory / "small.txt").write_bytes(b"x" * 10000)  # ~10KB
        (temp_directory / "medium.txt").write_bytes(b"x" * 2_000_000)  # ~2MB

        analyzer = StorageAnalyzer()
        distribution = analyzer.calculate_size_distribution(temp_directory)

        assert "tiny" in distribution.by_size_range
        assert "small" in distribution.by_size_range
        assert distribution.total_files >= 3
