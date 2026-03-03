"""Tests for analytics data models: storage stats, quality metrics, trends, and dashboard."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from file_organizer.models.analytics import (
    AnalyticsDashboard,
    DuplicateStats,
    FileDistribution,
    FileInfo,
    QualityMetrics,
    StorageStats,
    TimeSavings,
    TrendData,
)


@pytest.mark.unit
class TestFileInfo:
    """Tests for FileInfo data model."""

    def test_create_file_info(self) -> None:
        """Test basic FileInfo creation."""
        path = Path("/home/user/test.txt")
        now = datetime.now(tz=UTC)
        info = FileInfo(path=path, size=1024, type="text", modified=now)

        assert info.path == path
        assert info.size == 1024
        assert info.type == "text"
        assert info.modified == now
        assert info.category is None

    def test_file_info_with_category(self) -> None:
        """Test FileInfo with category."""
        info = FileInfo(
            path=Path("file.txt"),
            size=2048,
            type="text",
            modified=datetime.now(tz=UTC),
            category="documents",
        )
        assert info.category == "documents"

    def test_file_info_zero_size(self) -> None:
        """Test FileInfo with zero size."""
        info = FileInfo(
            path=Path("empty.txt"),
            size=0,
            type="text",
            modified=datetime.now(tz=UTC),
        )
        assert info.size == 0

    def test_file_info_large_size(self) -> None:
        """Test FileInfo with large size."""
        info = FileInfo(
            path=Path("large.iso"),
            size=5_000_000_000,  # 5GB
            type="archive",
            modified=datetime.now(tz=UTC),
        )
        assert info.size == 5_000_000_000


@pytest.mark.unit
class TestStorageStats:
    """Tests for StorageStats data model."""

    def test_create_storage_stats(self) -> None:
        """Test basic StorageStats creation."""
        stats = StorageStats(
            total_size=10_000_000,
            organized_size=8_000_000,
            saved_size=2_000_000,
            file_count=150,
            directory_count=10,
        )

        assert stats.total_size == 10_000_000
        assert stats.organized_size == 8_000_000
        assert stats.saved_size == 2_000_000
        assert stats.file_count == 150
        assert stats.directory_count == 10

    def test_formatted_total_size(self) -> None:
        """Test human-readable total size."""
        stats = StorageStats(
            total_size=1024,
            organized_size=0,
            saved_size=0,
            file_count=0,
            directory_count=0,
        )
        assert stats.formatted_total_size == "1.00 KB"

    def test_formatted_size_bytes(self) -> None:
        """Test size formatting for bytes."""
        stats = StorageStats(
            total_size=512,
            organized_size=0,
            saved_size=0,
            file_count=0,
            directory_count=0,
        )
        assert stats.formatted_total_size == "512.00 B"

    def test_formatted_size_megabytes(self) -> None:
        """Test size formatting for megabytes."""
        stats = StorageStats(
            total_size=5_242_880,  # 5 MB
            organized_size=0,
            saved_size=0,
            file_count=0,
            directory_count=0,
        )
        assert stats.formatted_total_size == "5.00 MB"

    def test_formatted_size_gigabytes(self) -> None:
        """Test size formatting for gigabytes."""
        stats = StorageStats(
            total_size=1_073_741_824,  # 1 GB
            organized_size=0,
            saved_size=0,
            file_count=0,
            directory_count=0,
        )
        assert stats.formatted_total_size == "1.00 GB"

    def test_formatted_size_terabytes(self) -> None:
        """Test size formatting for terabytes."""
        stats = StorageStats(
            total_size=1_099_511_627_776,  # 1 TB
            organized_size=0,
            saved_size=0,
            file_count=0,
            directory_count=0,
        )
        assert stats.formatted_total_size == "1.00 TB"

    def test_savings_percentage(self) -> None:
        """Test savings percentage calculation."""
        stats = StorageStats(
            total_size=1000,
            organized_size=800,
            saved_size=200,
            file_count=0,
            directory_count=0,
        )
        assert stats.savings_percentage == 20.0

    def test_savings_percentage_zero_total(self) -> None:
        """Test savings percentage with zero total size."""
        stats = StorageStats(
            total_size=0,
            organized_size=0,
            saved_size=0,
            file_count=0,
            directory_count=0,
        )
        assert stats.savings_percentage == 0.0

    def test_savings_percentage_full(self) -> None:
        """Test savings percentage when fully saved."""
        stats = StorageStats(
            total_size=1000,
            organized_size=1000,
            saved_size=1000,
            file_count=0,
            directory_count=0,
        )
        assert stats.savings_percentage == 100.0

    def test_with_largest_files(self) -> None:
        """Test StorageStats with largest files list."""
        file1 = FileInfo(
            path=Path("large1.iso"),
            size=1_000_000,
            type="archive",
            modified=datetime.now(tz=UTC),
        )
        file2 = FileInfo(
            path=Path("large2.iso"),
            size=500_000,
            type="archive",
            modified=datetime.now(tz=UTC),
        )
        stats = StorageStats(
            total_size=2_000_000,
            organized_size=1_500_000,
            saved_size=500_000,
            file_count=10,
            directory_count=2,
            largest_files=[file1, file2],
        )
        assert len(stats.largest_files) == 2
        assert stats.largest_files[0].size == 1_000_000

    def test_with_size_by_type(self) -> None:
        """Test StorageStats with size by type dict."""
        stats = StorageStats(
            total_size=1000,
            organized_size=800,
            saved_size=200,
            file_count=10,
            directory_count=2,
            size_by_type={"pdf": 400, "txt": 300, "img": 300},
        )
        assert stats.size_by_type["pdf"] == 400
        assert sum(stats.size_by_type.values()) == 1000

    def test_with_size_by_category(self) -> None:
        """Test StorageStats with size by category dict."""
        stats = StorageStats(
            total_size=1000,
            organized_size=800,
            saved_size=200,
            file_count=10,
            directory_count=2,
            size_by_category={"documents": 500, "media": 400, "archives": 100},
        )
        assert stats.size_by_category["documents"] == 500


@pytest.mark.unit
class TestFileDistribution:
    """Tests for FileDistribution data model."""

    def test_create_distribution(self) -> None:
        """Test basic FileDistribution creation."""
        dist = FileDistribution(
            by_type={"pdf": 10, "txt": 20},
            by_category={"documents": 30},
            total_files=30,
        )
        assert dist.total_files == 30
        assert dist.by_type["pdf"] == 10

    def test_get_type_percentage(self) -> None:
        """Test type percentage calculation."""
        dist = FileDistribution(
            by_type={"pdf": 25, "txt": 75},
            total_files=100,
        )
        assert dist.get_type_percentage("pdf") == 25.0
        assert dist.get_type_percentage("txt") == 75.0

    def test_get_type_percentage_zero_files(self) -> None:
        """Test type percentage with zero files."""
        dist = FileDistribution(total_files=0)
        assert dist.get_type_percentage("pdf") == 0.0

    def test_get_type_percentage_missing_type(self) -> None:
        """Test type percentage for missing type."""
        dist = FileDistribution(
            by_type={"pdf": 50},
            total_files=100,
        )
        assert dist.get_type_percentage("missing") == 0.0

    def test_with_size_range(self) -> None:
        """Test FileDistribution with size ranges."""
        dist = FileDistribution(
            by_type={"pdf": 10},
            by_category={"documents": 10},
            by_size_range={"<1MB": 5, "1-10MB": 4, ">10MB": 1},
            total_files=10,
        )
        assert dist.by_size_range["<1MB"] == 5
        assert sum(dist.by_size_range.values()) == 10


@pytest.mark.unit
class TestDuplicateStats:
    """Tests for DuplicateStats data model."""

    def test_create_duplicate_stats(self) -> None:
        """Test basic DuplicateStats creation."""
        stats = DuplicateStats(
            total_duplicates=50,
            duplicate_groups=10,
            space_wasted=5_000_000,
            space_recoverable=4_500_000,
        )
        assert stats.total_duplicates == 50
        assert stats.duplicate_groups == 10

    def test_formatted_space_wasted(self) -> None:
        """Test human-readable wasted space."""
        stats = DuplicateStats(
            total_duplicates=10,
            duplicate_groups=2,
            space_wasted=5_242_880,  # 5 MB
            space_recoverable=5_000_000,
        )
        assert stats.formatted_space_wasted == "5.00 MB"

    def test_formatted_recoverable(self) -> None:
        """Test human-readable recoverable space."""
        stats = DuplicateStats(
            total_duplicates=10,
            duplicate_groups=2,
            space_wasted=5_242_880,
            space_recoverable=4_718_592,  # 4.5 MB
        )
        assert stats.formatted_recoverable == "4.50 MB"

    def test_with_by_type(self) -> None:
        """Test DuplicateStats with duplicate types."""
        stats = DuplicateStats(
            total_duplicates=50,
            duplicate_groups=10,
            space_wasted=5_000_000,
            space_recoverable=4_500_000,
            by_type={"pdf": 20, "jpg": 30},
        )
        assert stats.by_type["pdf"] == 20

    def test_with_largest_group(self) -> None:
        """Test DuplicateStats with largest group info."""
        largest_group = {
            "count": 5,
            "size_per_file": 1_000_000,
            "total_wasted": 4_000_000,
            "file_type": "iso",
        }
        stats = DuplicateStats(
            total_duplicates=50,
            duplicate_groups=10,
            space_wasted=5_000_000,
            space_recoverable=4_500_000,
            largest_duplicate_group=largest_group,
        )
        assert stats.largest_duplicate_group["count"] == 5


@pytest.mark.unit
class TestQualityMetrics:
    """Tests for QualityMetrics data model."""

    def test_create_quality_metrics(self) -> None:
        """Test basic QualityMetrics creation."""
        metrics = QualityMetrics(
            quality_score=85.5,
            naming_compliance=0.9,
            structure_consistency=0.8,
            metadata_completeness=0.7,
            categorization_accuracy=0.85,
        )
        assert metrics.quality_score == 85.5
        assert metrics.naming_compliance == 0.9

    def test_grade_a(self) -> None:
        """Test grade calculation for A."""
        metrics = QualityMetrics(
            quality_score=95.0,
            naming_compliance=0.9,
            structure_consistency=0.9,
            metadata_completeness=0.9,
            categorization_accuracy=0.9,
        )
        assert metrics.grade == "A"

    def test_grade_b(self) -> None:
        """Test grade calculation for B."""
        metrics = QualityMetrics(
            quality_score=85.0,
            naming_compliance=0.8,
            structure_consistency=0.8,
            metadata_completeness=0.8,
            categorization_accuracy=0.8,
        )
        assert metrics.grade == "B"

    def test_grade_c(self) -> None:
        """Test grade calculation for C."""
        metrics = QualityMetrics(
            quality_score=75.0,
            naming_compliance=0.7,
            structure_consistency=0.7,
            metadata_completeness=0.7,
            categorization_accuracy=0.7,
        )
        assert metrics.grade == "C"

    def test_grade_d(self) -> None:
        """Test grade calculation for D."""
        metrics = QualityMetrics(
            quality_score=65.0,
            naming_compliance=0.6,
            structure_consistency=0.6,
            metadata_completeness=0.6,
            categorization_accuracy=0.6,
        )
        assert metrics.grade == "D"

    def test_grade_f(self) -> None:
        """Test grade calculation for F."""
        metrics = QualityMetrics(
            quality_score=45.0,
            naming_compliance=0.4,
            structure_consistency=0.4,
            metadata_completeness=0.4,
            categorization_accuracy=0.4,
        )
        assert metrics.grade == "F"

    def test_formatted_score(self) -> None:
        """Test formatted quality score."""
        metrics = QualityMetrics(
            quality_score=85.5,
            naming_compliance=0.8,
            structure_consistency=0.8,
            metadata_completeness=0.8,
            categorization_accuracy=0.8,
        )
        assert metrics.formatted_score == "85.5/100 (B)"

    def test_with_improvement_rate(self) -> None:
        """Test QualityMetrics with improvement rate."""
        metrics = QualityMetrics(
            quality_score=85.0,
            naming_compliance=0.8,
            structure_consistency=0.8,
            metadata_completeness=0.8,
            categorization_accuracy=0.8,
            improvement_rate=5.5,
        )
        assert metrics.improvement_rate == 5.5


@pytest.mark.unit
class TestTimeSavings:
    """Tests for TimeSavings data model."""

    def test_create_time_savings(self) -> None:
        """Test basic TimeSavings creation."""
        savings = TimeSavings(
            total_operations=100,
            automated_operations=85,
            manual_time_seconds=3600,
            automated_time_seconds=600,
            estimated_time_saved_seconds=2400,
        )
        assert savings.total_operations == 100
        assert savings.automated_operations == 85

    def test_automation_percentage(self) -> None:
        """Test automation percentage calculation."""
        savings = TimeSavings(
            total_operations=100,
            automated_operations=75,
            manual_time_seconds=3600,
            automated_time_seconds=900,
            estimated_time_saved_seconds=2700,
        )
        assert savings.automation_percentage == 75.0

    def test_automation_percentage_zero(self) -> None:
        """Test automation percentage with zero operations."""
        savings = TimeSavings(
            total_operations=0,
            automated_operations=0,
            manual_time_seconds=0,
            automated_time_seconds=0,
            estimated_time_saved_seconds=0,
        )
        assert savings.automation_percentage == 0.0

    def test_formatted_time_saved_seconds(self) -> None:
        """Test formatted time saved in seconds."""
        savings = TimeSavings(
            total_operations=10,
            automated_operations=10,
            manual_time_seconds=100,
            automated_time_seconds=10,
            estimated_time_saved_seconds=30,
        )
        assert savings.formatted_time_saved == "30s"

    def test_formatted_time_saved_minutes(self) -> None:
        """Test formatted time saved in minutes."""
        savings = TimeSavings(
            total_operations=10,
            automated_operations=10,
            manual_time_seconds=1000,
            automated_time_seconds=100,
            estimated_time_saved_seconds=300,  # 5 minutes
        )
        assert savings.formatted_time_saved == "5.0m"

    def test_formatted_time_saved_hours(self) -> None:
        """Test formatted time saved in hours."""
        savings = TimeSavings(
            total_operations=100,
            automated_operations=100,
            manual_time_seconds=36000,
            automated_time_seconds=3600,
            estimated_time_saved_seconds=7200,  # 2 hours
        )
        assert savings.formatted_time_saved == "2.0h"

    def test_formatted_time_saved_days(self) -> None:
        """Test formatted time saved in days."""
        savings = TimeSavings(
            total_operations=1000,
            automated_operations=1000,
            manual_time_seconds=864000,
            automated_time_seconds=86400,
            estimated_time_saved_seconds=259200,  # 3 days
        )
        assert savings.formatted_time_saved == "3.0d"


@pytest.mark.unit
class TestTrendData:
    """Tests for TrendData data model."""

    def test_create_trend_data(self) -> None:
        """Test basic TrendData creation."""
        trend = TrendData(metric_name="organization_rate")
        assert trend.metric_name == "organization_rate"
        assert len(trend.values) == 0
        assert len(trend.timestamps) == 0

    def test_add_data_point(self) -> None:
        """Test adding data points to trend."""
        trend = TrendData(metric_name="quality_score")
        now = datetime.now(tz=UTC)
        trend.add_data_point(80.0, now)
        trend.add_data_point(82.5, now)

        assert len(trend.values) == 2
        assert trend.values[0] == 80.0
        assert trend.values[1] == 82.5

    def test_trend_direction_up(self) -> None:
        """Test trend direction detection for upward trend."""
        trend = TrendData(metric_name="quality_score")
        now = datetime.now(tz=UTC)
        # Gradually increasing values
        trend.add_data_point(50.0, now)
        trend.add_data_point(60.0, now)
        trend.add_data_point(70.0, now)
        trend.add_data_point(80.0, now)
        trend.add_data_point(90.0, now)

        assert trend.trend_direction == "up"

    def test_trend_direction_down(self) -> None:
        """Test trend direction detection for downward trend."""
        trend = TrendData(metric_name="errors")
        now = datetime.now(tz=UTC)
        # Gradually decreasing values
        trend.add_data_point(100.0, now)
        trend.add_data_point(80.0, now)
        trend.add_data_point(60.0, now)
        trend.add_data_point(40.0, now)
        trend.add_data_point(20.0, now)

        assert trend.trend_direction == "down"

    def test_trend_direction_stable(self) -> None:
        """Test trend direction detection for stable trend."""
        trend = TrendData(metric_name="metric")
        now = datetime.now(tz=UTC)
        # Stable values
        trend.add_data_point(50.0, now)
        trend.add_data_point(50.5, now)
        trend.add_data_point(49.8, now)
        trend.add_data_point(50.2, now)
        trend.add_data_point(50.0, now)

        assert trend.trend_direction == "stable"

    def test_trend_direction_single_point(self) -> None:
        """Test trend direction with single data point."""
        trend = TrendData(metric_name="metric")
        now = datetime.now(tz=UTC)
        trend.add_data_point(75.0, now)

        assert trend.trend_direction == "stable"

    def test_trend_direction_empty(self) -> None:
        """Test trend direction with no data points."""
        trend = TrendData(metric_name="metric")
        assert trend.trend_direction == "stable"


@pytest.mark.unit
class TestAnalyticsDashboard:
    """Tests for AnalyticsDashboard data model."""

    @pytest.fixture
    def sample_dashboard(self) -> AnalyticsDashboard:
        """Create a sample dashboard for testing."""
        storage = StorageStats(
            total_size=10_000_000,
            organized_size=8_000_000,
            saved_size=2_000_000,
            file_count=150,
            directory_count=10,
        )
        distribution = FileDistribution(
            by_type={"pdf": 50, "txt": 100},
            by_category={"documents": 150},
            total_files=150,
        )
        duplicates = DuplicateStats(
            total_duplicates=10,
            duplicate_groups=3,
            space_wasted=1_000_000,
            space_recoverable=900_000,
        )
        quality = QualityMetrics(
            quality_score=85.0,
            naming_compliance=0.85,
            structure_consistency=0.8,
            metadata_completeness=0.75,
            categorization_accuracy=0.9,
        )
        time_savings = TimeSavings(
            total_operations=150,
            automated_operations=135,
            manual_time_seconds=3600,
            automated_time_seconds=600,
            estimated_time_saved_seconds=2400,
        )

        return AnalyticsDashboard(
            storage_stats=storage,
            file_distribution=distribution,
            duplicate_stats=duplicates,
            quality_metrics=quality,
            time_savings=time_savings,
        )

    def test_create_dashboard(self, sample_dashboard: AnalyticsDashboard) -> None:
        """Test creating a dashboard."""
        assert sample_dashboard.storage_stats.file_count == 150
        assert sample_dashboard.quality_metrics.quality_score == 85.0

    def test_dashboard_generated_at(self, sample_dashboard: AnalyticsDashboard) -> None:
        """Test that generated_at timestamp is set."""
        assert sample_dashboard.generated_at is not None
        assert isinstance(sample_dashboard.generated_at, datetime)

    def test_dashboard_to_dict(self, sample_dashboard: AnalyticsDashboard) -> None:
        """Test converting dashboard to dictionary."""
        data = sample_dashboard.to_dict()

        assert "storage_stats" in data
        assert "file_distribution" in data
        assert "duplicate_stats" in data
        assert "quality_metrics" in data
        assert "time_savings" in data
        assert "generated_at" in data

    def test_dashboard_dict_values(
        self, sample_dashboard: AnalyticsDashboard
    ) -> None:
        """Test dictionary content values."""
        data = sample_dashboard.to_dict()

        assert data["storage_stats"]["total_size"] == 10_000_000
        assert data["storage_stats"]["file_count"] == 150
        assert data["quality_metrics"]["quality_score"] == 85.0
        assert data["quality_metrics"]["grade"] == "B"
        assert data["duplicate_stats"]["total_duplicates"] == 10
        assert data["file_distribution"]["total_files"] == 150

    def test_dashboard_with_trends(self, sample_dashboard: AnalyticsDashboard) -> None:
        """Test dashboard with trend data."""
        now = datetime.now(tz=UTC)
        trend = TrendData(metric_name="quality_score")
        trend.add_data_point(80.0, now)
        trend.add_data_point(85.0, now)

        sample_dashboard.trends["quality_score"] = trend

        assert "quality_score" in sample_dashboard.trends
        assert len(sample_dashboard.trends["quality_score"].values) == 2
