"""Tests for file_organizer.cli.analytics module.

Tests the argparse-based analytics CLI including:
- analytics_command main function
- _format_bytes and _format_duration helpers
- display_storage_stats, display_quality_metrics, display_duplicate_stats
- display_time_savings, display_file_distribution
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.cli.analytics import (
    _format_bytes,
    _format_duration,
    analytics_command,
    display_duplicate_stats,
    display_file_distribution,
    display_quality_metrics,
    display_storage_stats,
    display_time_savings,
)

pytestmark = [pytest.mark.unit]


# ============================================================================
# Helper Function Tests
# ============================================================================


@pytest.mark.unit
class TestFormatBytes:
    """Tests for _format_bytes helper."""

    def test_bytes(self):
        assert _format_bytes(500) == "500.0 B"

    def test_kilobytes(self):
        result = _format_bytes(2048)
        assert "KB" in result

    def test_megabytes(self):
        result = _format_bytes(5 * 1024 * 1024)
        assert "MB" in result

    def test_gigabytes(self):
        result = _format_bytes(3 * 1024 * 1024 * 1024)
        assert "GB" in result

    def test_terabytes(self):
        result = _format_bytes(2 * 1024**4)
        assert "TB" in result

    def test_zero(self):
        assert _format_bytes(0) == "0.0 B"

    def test_petabytes(self):
        result = _format_bytes(2 * 1024**5)
        assert "PB" in result


@pytest.mark.unit
class TestFormatDuration:
    """Tests for _format_duration helper."""

    def test_seconds(self):
        result = _format_duration(30.0)
        assert result == "30.0s"

    def test_minutes(self):
        result = _format_duration(120.0)
        assert "m" in result

    def test_hours(self):
        result = _format_duration(7200.0)
        assert "h" in result

    def test_zero(self):
        result = _format_duration(0.0)
        assert result == "0.0s"


# ============================================================================
# display_storage_stats Tests
# ============================================================================


@pytest.mark.unit
class TestDisplayStorageStats:
    """Tests for display_storage_stats."""

    def test_basic_stats(self):
        stats = MagicMock()
        stats.formatted_total_size = "1.5 GB"
        stats.file_count = 500
        stats.directory_count = 20
        stats.formatted_saved_size = "200 MB"
        stats.savings_percentage = 15.3
        stats.size_by_type = {}
        stats.largest_files = []

        # Should not raise
        display_storage_stats(stats, chart_gen=None)

    def test_with_chart_gen(self):
        stats = MagicMock()
        stats.formatted_total_size = "1.5 GB"
        stats.file_count = 500
        stats.directory_count = 20
        stats.formatted_saved_size = "200 MB"
        stats.savings_percentage = 15.3
        stats.size_by_type = {".pdf": 1024, ".jpg": 2048}
        stats.largest_files = []

        mock_chart_gen = MagicMock()
        mock_chart_gen.create_pie_chart.return_value = "PIE CHART"

        display_storage_stats(stats, chart_gen=mock_chart_gen)
        mock_chart_gen.create_pie_chart.assert_called_once()

    def test_with_largest_files(self):
        file_info = MagicMock()
        file_info.size = 1024 * 1024
        file_info.type = ".pdf"
        file_info.path = Path("/docs/big.pdf")

        stats = MagicMock()
        stats.formatted_total_size = "1.5 GB"
        stats.file_count = 500
        stats.directory_count = 20
        stats.formatted_saved_size = "200 MB"
        stats.savings_percentage = 15.3
        stats.size_by_type = {}
        stats.largest_files = [file_info]

        display_storage_stats(stats, chart_gen=None)

    def test_empty_size_by_type_with_chart_gen(self):
        """Chart gen present but size_by_type is empty (falsy)."""
        stats = MagicMock()
        stats.formatted_total_size = "0 B"
        stats.file_count = 0
        stats.directory_count = 0
        stats.formatted_saved_size = "0 B"
        stats.savings_percentage = 0.0
        stats.size_by_type = {}
        stats.largest_files = []

        mock_chart_gen = MagicMock()
        display_storage_stats(stats, chart_gen=mock_chart_gen)
        mock_chart_gen.create_pie_chart.assert_not_called()


# ============================================================================
# display_quality_metrics Tests
# ============================================================================


@pytest.mark.unit
class TestDisplayQualityMetrics:
    """Tests for display_quality_metrics."""

    def test_high_score(self):
        metrics = MagicMock()
        metrics.quality_score = 85
        metrics.formatted_score = "85/100"
        metrics.naming_compliance = 0.90
        metrics.structure_consistency = 0.85
        metrics.metadata_completeness = 0.75
        metrics.categorization_accuracy = 0.80

        display_quality_metrics(metrics)  # Should not raise

    def test_medium_score(self):
        metrics = MagicMock()
        metrics.quality_score = 55
        metrics.formatted_score = "55/100"
        metrics.naming_compliance = 0.60
        metrics.structure_consistency = 0.50
        metrics.metadata_completeness = 0.45
        metrics.categorization_accuracy = 0.55

        display_quality_metrics(metrics)

    def test_low_score(self):
        metrics = MagicMock()
        metrics.quality_score = 30
        metrics.formatted_score = "30/100"
        metrics.naming_compliance = 0.30
        metrics.structure_consistency = 0.25
        metrics.metadata_completeness = 0.20
        metrics.categorization_accuracy = 0.35

        display_quality_metrics(metrics)


# ============================================================================
# display_duplicate_stats Tests
# ============================================================================


@pytest.mark.unit
class TestDisplayDuplicateStats:
    """Tests for display_duplicate_stats."""

    def test_no_duplicates(self):
        stats = MagicMock()
        stats.total_duplicates = 0

        display_duplicate_stats(stats)  # Should print "No duplicates"

    def test_with_duplicates(self):
        stats = MagicMock()
        stats.total_duplicates = 15
        stats.duplicate_groups = 5
        stats.formatted_space_wasted = "500 MB"
        stats.formatted_recoverable = "400 MB"
        stats.by_type = {".jpg": 10, ".pdf": 5}

        display_duplicate_stats(stats)

    def test_with_duplicates_no_by_type(self):
        stats = MagicMock()
        stats.total_duplicates = 3
        stats.duplicate_groups = 1
        stats.formatted_space_wasted = "10 MB"
        stats.formatted_recoverable = "5 MB"
        stats.by_type = {}

        display_duplicate_stats(stats)


# ============================================================================
# display_time_savings Tests
# ============================================================================


@pytest.mark.unit
class TestDisplayTimeSavings:
    """Tests for display_time_savings."""

    def test_with_data(self):
        savings = MagicMock()
        savings.formatted_time_saved = "2.5 hours"
        savings.total_operations = 100
        savings.automated_operations = 80
        savings.automation_percentage = 80.0
        savings.manual_time_seconds = 3600.0
        savings.automated_time_seconds = 900.0

        display_time_savings(savings)  # Should not raise


# ============================================================================
# display_file_distribution Tests
# ============================================================================


@pytest.mark.unit
class TestDisplayFileDistribution:
    """Tests for display_file_distribution."""

    def test_with_chart_gen(self):
        distribution = MagicMock()
        distribution.total_files = 100
        distribution.by_type = {".txt": 50, ".pdf": 30, ".jpg": 20}
        distribution.by_size_range = {"small": 60, "medium": 30, "large": 10}

        mock_chart_gen = MagicMock()
        mock_chart_gen.create_bar_chart.return_value = "BAR CHART"

        display_file_distribution(distribution, chart_gen=mock_chart_gen)
        mock_chart_gen.create_bar_chart.assert_called_once()

    def test_without_chart_gen(self):
        distribution = MagicMock()
        distribution.total_files = 100
        distribution.by_type = {}
        distribution.by_size_range = {"small": 60, "medium": 30, "large": 10}

        display_file_distribution(distribution, chart_gen=None)

    def test_empty_distribution(self):
        distribution = MagicMock()
        distribution.total_files = 0
        distribution.by_type = {}
        distribution.by_size_range = {}

        display_file_distribution(distribution, chart_gen=None)

    def test_zero_total_files_with_size_range(self):
        """Zero total_files should avoid division by zero."""
        distribution = MagicMock()
        distribution.total_files = 0
        distribution.by_type = {}
        distribution.by_size_range = {"small": 0}

        display_file_distribution(distribution, chart_gen=None)


# ============================================================================
# analytics_command Tests
# ============================================================================


@pytest.mark.unit
class TestAnalyticsCommand:
    """Tests for the main analytics_command function."""

    def test_nonexistent_directory(self):
        result = analytics_command(["/nonexistent/directory/xyz"])
        assert result == 1

    def test_file_instead_of_directory(self, tmp_path):
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello")
        result = analytics_command([str(test_file)])
        assert result == 1

    def test_success(self, tmp_path):
        (tmp_path / "file.txt").write_text("content")

        mock_dashboard = MagicMock()
        mock_dashboard.storage_stats = MagicMock()
        mock_dashboard.quality_metrics = MagicMock()
        mock_dashboard.duplicate_stats = MagicMock()
        mock_dashboard.time_savings = MagicMock()
        mock_dashboard.file_distribution = MagicMock()
        mock_dashboard.generated_at = MagicMock()
        mock_dashboard.generated_at.strftime.return_value = "2024-01-01 00:00:00"

        mock_service = MagicMock()
        mock_service.generate_dashboard.return_value = mock_dashboard

        with (
            patch("file_organizer.cli.analytics.AnalyticsService", return_value=mock_service),
            patch("file_organizer.cli.analytics.ChartGenerator", return_value=MagicMock()),
            patch("file_organizer.cli.analytics.display_storage_stats"),
            patch("file_organizer.cli.analytics.display_quality_metrics"),
            patch("file_organizer.cli.analytics.display_duplicate_stats"),
            patch("file_organizer.cli.analytics.display_time_savings"),
            patch("file_organizer.cli.analytics.display_file_distribution"),
        ):
            result = analytics_command([str(tmp_path)])
        assert result == 0

    def test_with_max_depth(self, tmp_path):
        (tmp_path / "file.txt").write_text("content")

        mock_dashboard = MagicMock()
        mock_dashboard.generated_at = MagicMock()
        mock_dashboard.generated_at.strftime.return_value = "2024-01-01 00:00:00"

        mock_service = MagicMock()
        mock_service.generate_dashboard.return_value = mock_dashboard

        with (
            patch("file_organizer.cli.analytics.AnalyticsService", return_value=mock_service),
            patch("file_organizer.cli.analytics.ChartGenerator", return_value=MagicMock()),
            patch("file_organizer.cli.analytics.display_storage_stats"),
            patch("file_organizer.cli.analytics.display_quality_metrics"),
            patch("file_organizer.cli.analytics.display_duplicate_stats"),
            patch("file_organizer.cli.analytics.display_time_savings"),
            patch("file_organizer.cli.analytics.display_file_distribution"),
        ):
            result = analytics_command([str(tmp_path), "--max-depth", "3"])
        assert result == 0
        call_kwargs = mock_service.generate_dashboard.call_args
        assert call_kwargs[1]["max_depth"] == 3

    def test_no_charts_flag(self, tmp_path):
        (tmp_path / "file.txt").write_text("content")

        mock_dashboard = MagicMock()
        mock_dashboard.generated_at = MagicMock()
        mock_dashboard.generated_at.strftime.return_value = "2024-01-01 00:00:00"

        mock_service = MagicMock()
        mock_service.generate_dashboard.return_value = mock_dashboard

        with (
            patch("file_organizer.cli.analytics.AnalyticsService", return_value=mock_service),
            patch("file_organizer.cli.analytics.ChartGenerator") as mock_chart_cls,
            patch("file_organizer.cli.analytics.display_storage_stats") as mock_display,
            patch("file_organizer.cli.analytics.display_quality_metrics"),
            patch("file_organizer.cli.analytics.display_duplicate_stats"),
            patch("file_organizer.cli.analytics.display_time_savings"),
            patch("file_organizer.cli.analytics.display_file_distribution"),
        ):
            result = analytics_command([str(tmp_path), "--no-charts"])
        assert result == 0
        mock_chart_cls.assert_not_called()
        # chart_gen should be None
        call_args = mock_display.call_args
        assert call_args[0][1] is None

    def test_export_to_json(self, tmp_path):
        (tmp_path / "file.txt").write_text("content")
        export_file = tmp_path / "report.json"

        mock_dashboard = MagicMock()
        mock_dashboard.generated_at = MagicMock()
        mock_dashboard.generated_at.strftime.return_value = "2024-01-01 00:00:00"

        mock_service = MagicMock()
        mock_service.generate_dashboard.return_value = mock_dashboard

        with (
            patch("file_organizer.cli.analytics.AnalyticsService", return_value=mock_service),
            patch("file_organizer.cli.analytics.ChartGenerator", return_value=MagicMock()),
            patch("file_organizer.cli.analytics.display_storage_stats"),
            patch("file_organizer.cli.analytics.display_quality_metrics"),
            patch("file_organizer.cli.analytics.display_duplicate_stats"),
            patch("file_organizer.cli.analytics.display_time_savings"),
            patch("file_organizer.cli.analytics.display_file_distribution"),
        ):
            result = analytics_command([str(tmp_path), "--export", str(export_file)])
        assert result == 0
        mock_service.export_dashboard.assert_called_once()

    def test_export_text_format(self, tmp_path):
        (tmp_path / "file.txt").write_text("content")
        export_file = tmp_path / "report.txt"

        mock_dashboard = MagicMock()
        mock_dashboard.generated_at = MagicMock()
        mock_dashboard.generated_at.strftime.return_value = "2024-01-01 00:00:00"

        mock_service = MagicMock()
        mock_service.generate_dashboard.return_value = mock_dashboard

        with (
            patch("file_organizer.cli.analytics.AnalyticsService", return_value=mock_service),
            patch("file_organizer.cli.analytics.ChartGenerator", return_value=MagicMock()),
            patch("file_organizer.cli.analytics.display_storage_stats"),
            patch("file_organizer.cli.analytics.display_quality_metrics"),
            patch("file_organizer.cli.analytics.display_duplicate_stats"),
            patch("file_organizer.cli.analytics.display_time_savings"),
            patch("file_organizer.cli.analytics.display_file_distribution"),
        ):
            result = analytics_command(
                [str(tmp_path), "--export", str(export_file), "--format", "text"]
            )
        assert result == 0
        call_kwargs = mock_service.export_dashboard.call_args
        assert call_kwargs[1]["format"] == "text"

    def test_verbose_flag(self, tmp_path):
        (tmp_path / "file.txt").write_text("content")

        mock_dashboard = MagicMock()
        mock_dashboard.generated_at = MagicMock()
        mock_dashboard.generated_at.strftime.return_value = "2024-01-01 00:00:00"

        mock_service = MagicMock()
        mock_service.generate_dashboard.return_value = mock_dashboard

        with (
            patch("file_organizer.cli.analytics.AnalyticsService", return_value=mock_service),
            patch("file_organizer.cli.analytics.ChartGenerator", return_value=MagicMock()),
            patch("file_organizer.cli.analytics.display_storage_stats"),
            patch("file_organizer.cli.analytics.display_quality_metrics"),
            patch("file_organizer.cli.analytics.display_duplicate_stats"),
            patch("file_organizer.cli.analytics.display_time_savings"),
            patch("file_organizer.cli.analytics.display_file_distribution"),
        ):
            result = analytics_command([str(tmp_path), "--verbose"])
        assert result == 0

    def test_exception_during_analysis(self, tmp_path):
        (tmp_path / "file.txt").write_text("data")

        with patch(
            "file_organizer.cli.analytics.AnalyticsService",
            side_effect=RuntimeError("service error"),
        ):
            result = analytics_command([str(tmp_path)])
        assert result == 1

    def test_keyboard_interrupt(self, tmp_path):
        (tmp_path / "file.txt").write_text("data")

        with patch(
            "file_organizer.cli.analytics.AnalyticsService",
            side_effect=KeyboardInterrupt,
        ):
            result = analytics_command([str(tmp_path)])
        assert result == 130
