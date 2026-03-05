"""Coverage tests for file_organizer.models.analytics — uncovered branches."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from file_organizer.models.analytics import (
    DuplicateStats,
    FileDistribution,
    QualityMetrics,
    StorageStats,
    TimeSavings,
    TrendData,
)

pytestmark = pytest.mark.unit


class TestStorageStats:
    """Covers formatted size, savings percentage, and size formatting edge cases."""

    def test_formatted_total_size(self) -> None:
        stats = StorageStats(
            total_size=2048,
            organized_size=1024,
            saved_size=1024,
            file_count=10,
            directory_count=2,
        )
        assert "KB" in stats.formatted_total_size

    def test_formatted_saved_size(self) -> None:
        stats = StorageStats(
            total_size=2048,
            organized_size=1024,
            saved_size=512,
            file_count=10,
            directory_count=2,
        )
        assert "B" in stats.formatted_saved_size or "KB" in stats.formatted_saved_size

    def test_savings_percentage_zero_total(self) -> None:
        stats = StorageStats(
            total_size=0,
            organized_size=0,
            saved_size=0,
            file_count=0,
            directory_count=0,
        )
        assert stats.savings_percentage == 0.0

    def test_savings_percentage_nonzero(self) -> None:
        stats = StorageStats(
            total_size=1000,
            organized_size=500,
            saved_size=200,
            file_count=5,
            directory_count=1,
        )
        assert stats.savings_percentage == 20.0

    def test_format_size_bytes(self) -> None:
        assert "B" in StorageStats._format_size(100)

    def test_format_size_kb(self) -> None:
        assert "KB" in StorageStats._format_size(2048)

    def test_format_size_mb(self) -> None:
        assert "MB" in StorageStats._format_size(2 * 1024**2)

    def test_format_size_gb(self) -> None:
        assert "GB" in StorageStats._format_size(2 * 1024**3)

    def test_format_size_tb(self) -> None:
        assert "TB" in StorageStats._format_size(2 * 1024**4)

    def test_format_size_pb(self) -> None:
        assert "PB" in StorageStats._format_size(2 * 1024**5)


class TestFileDistribution:
    """Covers get_type_percentage."""

    def test_type_percentage_zero_files(self) -> None:
        fd = FileDistribution(total_files=0)
        assert fd.get_type_percentage(".pdf") == 0.0

    def test_type_percentage_with_files(self) -> None:
        fd = FileDistribution(
            by_type={".pdf": 5, ".txt": 15},
            total_files=20,
        )
        assert fd.get_type_percentage(".pdf") == 25.0

    def test_type_percentage_missing_type(self) -> None:
        fd = FileDistribution(total_files=10)
        assert fd.get_type_percentage(".xyz") == 0.0


class TestDuplicateStats:
    """Covers formatted properties."""

    def test_formatted_space_wasted(self) -> None:
        ds = DuplicateStats(
            total_duplicates=5,
            duplicate_groups=2,
            space_wasted=1024,
            space_recoverable=512,
        )
        assert "KB" in ds.formatted_space_wasted or "B" in ds.formatted_space_wasted

    def test_formatted_recoverable(self) -> None:
        ds = DuplicateStats(
            total_duplicates=5,
            duplicate_groups=2,
            space_wasted=1024,
            space_recoverable=2 * 1024 * 1024,
        )
        assert "MB" in ds.formatted_recoverable


class TestQualityMetrics:
    """Covers grade property all branches."""

    @pytest.mark.parametrize(
        "score,expected_grade",
        [
            (95.0, "A"),
            (85.0, "B"),
            (75.0, "C"),
            (65.0, "D"),
            (50.0, "F"),
        ],
    )
    def test_grade(self, score: float, expected_grade: str) -> None:
        qm = QualityMetrics(
            quality_score=score,
            naming_compliance=0.8,
            structure_consistency=0.9,
            metadata_completeness=0.7,
            categorization_accuracy=0.8,
        )
        assert qm.grade == expected_grade

    def test_formatted_score(self) -> None:
        qm = QualityMetrics(
            quality_score=85.0,
            naming_compliance=0.8,
            structure_consistency=0.9,
            metadata_completeness=0.7,
            categorization_accuracy=0.8,
        )
        assert "85.0/100" in qm.formatted_score
        assert "B" in qm.formatted_score


class TestTimeSavings:
    """Covers automation_percentage and format_duration branches."""

    def test_automation_percentage_zero_ops(self) -> None:
        ts = TimeSavings(
            total_operations=0,
            automated_operations=0,
            manual_time_seconds=0,
            automated_time_seconds=0,
            estimated_time_saved_seconds=0,
        )
        assert ts.automation_percentage == 0.0

    def test_automation_percentage_nonzero(self) -> None:
        ts = TimeSavings(
            total_operations=10,
            automated_operations=7,
            manual_time_seconds=100,
            automated_time_seconds=30,
            estimated_time_saved_seconds=70,
        )
        assert ts.automation_percentage == 70.0

    def test_format_duration_seconds(self) -> None:
        assert "s" in TimeSavings._format_duration(30)

    def test_format_duration_minutes(self) -> None:
        result = TimeSavings._format_duration(120)
        assert "m" in result

    def test_format_duration_hours(self) -> None:
        result = TimeSavings._format_duration(7200)
        assert "h" in result

    def test_format_duration_days(self) -> None:
        result = TimeSavings._format_duration(90000)
        assert "d" in result

    def test_formatted_time_saved(self) -> None:
        ts = TimeSavings(
            total_operations=10,
            automated_operations=7,
            manual_time_seconds=100,
            automated_time_seconds=30,
            estimated_time_saved_seconds=3700,
        )
        assert "h" in ts.formatted_time_saved


class TestTrendData:
    """Covers trend_direction branches."""

    def test_trend_stable_insufficient_data(self) -> None:
        td = TrendData(metric_name="test")
        assert td.trend_direction == "stable"

    def test_trend_up(self) -> None:
        td = TrendData(
            metric_name="test",
            values=[10, 12, 15, 20, 30],
            timestamps=[datetime.now(tz=UTC)] * 5,
        )
        assert td.trend_direction == "up"

    def test_trend_down(self) -> None:
        td = TrendData(
            metric_name="test",
            values=[30, 25, 20, 12, 10],
            timestamps=[datetime.now(tz=UTC)] * 5,
        )
        assert td.trend_direction == "down"

    def test_trend_stable(self) -> None:
        td = TrendData(
            metric_name="test",
            values=[10, 10, 10, 10, 10],
            timestamps=[datetime.now(tz=UTC)] * 5,
        )
        assert td.trend_direction == "stable"

    def test_add_data_point(self) -> None:
        td = TrendData(metric_name="test")
        now = datetime.now(tz=UTC)
        td.add_data_point(42.0, now)
        assert td.values == [42.0]
        assert td.timestamps == [now]
