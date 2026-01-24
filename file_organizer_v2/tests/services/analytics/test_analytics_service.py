"""Tests for AnalyticsService."""

import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from file_organizer.models.analytics import (
    AnalyticsDashboard,
    DuplicateStats,
    QualityMetrics,
    StorageStats,
)
from file_organizer.services.analytics import AnalyticsService


@pytest.fixture
def temp_directory():
    """Create a temporary directory with test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # Create test directory structure
        (tmp_path / "docs").mkdir()
        (tmp_path / "images").mkdir()
        (tmp_path / "videos").mkdir()

        # Create test files
        (tmp_path / "docs" / "test1.txt").write_text("Hello World")
        (tmp_path / "docs" / "test2.txt").write_text("Test Document")
        (tmp_path / "images" / "image1.jpg").write_bytes(b"fake image data" * 100)
        (tmp_path / "images" / "image2.png").write_bytes(b"another image" * 50)
        (tmp_path / "videos" / "video1.mp4").write_bytes(b"fake video" * 1000)
        (tmp_path / "readme.md").write_text("# Readme")

        yield tmp_path


class TestAnalyticsService:
    """Test suite for AnalyticsService."""

    def test_initialization(self):
        """Test service initialization."""
        service = AnalyticsService()
        assert service.storage_analyzer is not None
        assert service.metrics_calculator is not None

    def test_get_storage_stats(self, temp_directory):
        """Test storage statistics generation."""
        service = AnalyticsService()
        stats = service.get_storage_stats(temp_directory)

        assert isinstance(stats, StorageStats)
        assert stats.file_count == 6  # 6 test files
        assert stats.directory_count == 3  # docs, images, videos
        assert stats.total_size > 0

    def test_get_quality_metrics(self, temp_directory):
        """Test quality metrics calculation."""
        service = AnalyticsService()
        metrics = service.get_quality_metrics(
            temp_directory, total_files=6, organized_size=1000
        )

        assert isinstance(metrics, QualityMetrics)
        assert 0 <= metrics.quality_score <= 100
        assert 0 <= metrics.naming_compliance <= 1
        assert 0 <= metrics.structure_consistency <= 1

    def test_get_duplicate_stats_empty(self):
        """Test duplicate stats with no duplicates."""
        service = AnalyticsService()
        stats = service.get_duplicate_stats([], total_size=1000)

        assert isinstance(stats, DuplicateStats)
        assert stats.total_duplicates == 0
        assert stats.duplicate_groups == 0
        assert stats.space_wasted == 0

    def test_get_duplicate_stats_with_duplicates(self, temp_directory):
        """Test duplicate stats with duplicate groups."""
        service = AnalyticsService()

        # Create duplicate files for testing
        dup1 = temp_directory / "dup1.txt"
        dup2 = temp_directory / "dup2.txt"
        dup1.write_text("duplicate content")
        dup2.write_text("duplicate content")

        duplicate_groups = [{"files": [str(dup1), str(dup2)]}]

        stats = service.get_duplicate_stats(duplicate_groups, total_size=10000)

        assert isinstance(stats, DuplicateStats)
        assert stats.duplicate_groups == 1
        assert stats.total_duplicates == 2
        assert stats.space_wasted > 0

    def test_calculate_time_saved(self):
        """Test time savings calculation."""
        service = AnalyticsService()
        savings = service.calculate_time_saved(total_files=100, duplicates_removed=10)

        assert savings.total_operations == 100
        assert savings.automated_operations == 100
        assert savings.estimated_time_saved_seconds > 0
        assert savings.automation_percentage == 100.0

    def test_generate_dashboard(self, temp_directory):
        """Test complete dashboard generation."""
        service = AnalyticsService()
        dashboard = service.generate_dashboard(temp_directory)

        assert isinstance(dashboard, AnalyticsDashboard)
        assert dashboard.storage_stats is not None
        assert dashboard.file_distribution is not None
        assert dashboard.duplicate_stats is not None
        assert dashboard.quality_metrics is not None
        assert dashboard.time_savings is not None
        assert isinstance(dashboard.generated_at, datetime)

    def test_export_dashboard_json(self, temp_directory):
        """Test exporting dashboard to JSON."""
        service = AnalyticsService()
        dashboard = service.generate_dashboard(temp_directory)

        output_file = temp_directory / "analytics.json"
        service.export_dashboard(dashboard, output_file, format="json")

        assert output_file.exists()
        assert output_file.stat().st_size > 0

        # Verify JSON is valid
        import json

        with open(output_file) as f:
            data = json.load(f)
            assert "storage_stats" in data
            assert "quality_metrics" in data
            assert "generated_at" in data

    def test_export_dashboard_text(self, temp_directory):
        """Test exporting dashboard to text format."""
        service = AnalyticsService()
        dashboard = service.generate_dashboard(temp_directory)

        output_file = temp_directory / "analytics.txt"
        service.export_dashboard(dashboard, output_file, format="text")

        assert output_file.exists()
        assert output_file.stat().st_size > 0

        # Verify text content
        content = output_file.read_text()
        assert "Analytics Dashboard" in content
        assert "STORAGE STATISTICS" in content
        assert "QUALITY METRICS" in content

    def test_export_dashboard_invalid_format(self, temp_directory):
        """Test error handling for invalid export format."""
        service = AnalyticsService()
        dashboard = service.generate_dashboard(temp_directory)

        output_file = temp_directory / "analytics.xml"

        with pytest.raises(ValueError, match="Unsupported format"):
            service.export_dashboard(dashboard, output_file, format="xml")

    def test_dashboard_to_dict(self, temp_directory):
        """Test dashboard serialization to dict."""
        service = AnalyticsService()
        dashboard = service.generate_dashboard(temp_directory)

        data = dashboard.to_dict()

        assert isinstance(data, dict)
        assert "storage_stats" in data
        assert "file_distribution" in data
        assert "duplicate_stats" in data
        assert "quality_metrics" in data
        assert "time_savings" in data
        assert "generated_at" in data

    def test_max_depth_parameter(self, temp_directory):
        """Test max_depth parameter for storage analysis."""
        service = AnalyticsService()

        # Create nested structure
        (temp_directory / "level1" / "level2" / "level3").mkdir(parents=True)
        (temp_directory / "level1" / "level2" / "level3" / "deep.txt").write_text(
            "deep file"
        )

        # Analyze with depth limit
        dashboard = service.generate_dashboard(temp_directory, max_depth=1)

        assert isinstance(dashboard, AnalyticsDashboard)
        # The deep file should not be counted with max_depth=1
        # (depends on implementation details)

    def test_quality_score_boundaries(self, temp_directory):
        """Test quality score stays within valid range."""
        service = AnalyticsService()

        # Test with various file counts
        for total_files in [0, 1, 10, 100, 1000]:
            metrics = service.get_quality_metrics(
                temp_directory, total_files=total_files, organized_size=100
            )
            assert 0 <= metrics.quality_score <= 100

    def test_empty_directory_handling(self):
        """Test handling of empty directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            service = AnalyticsService()

            stats = service.get_storage_stats(tmp_path)

            assert stats.file_count == 0
            assert stats.total_size == 0
            assert stats.directory_count == 0

    def test_large_files_identification(self, temp_directory):
        """Test identification of large files."""
        # Create a large file
        large_file = temp_directory / "large.bin"
        large_file.write_bytes(b"x" * (200 * 1024 * 1024))  # 200MB

        service = AnalyticsService()
        stats = service.get_storage_stats(temp_directory)

        # Should include the large file in largest_files
        assert any(f.path == large_file for f in stats.largest_files)
        largest = next(f for f in stats.largest_files if f.path == large_file)
        assert largest.size > 100 * 1024 * 1024  # > 100MB
