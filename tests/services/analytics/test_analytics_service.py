"""Tests for AnalyticsService."""

from __future__ import annotations

import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.models.analytics import (
    AnalyticsDashboard,
    DuplicateStats,
    FileDistribution,
    QualityMetrics,
    StorageStats,
    TimeSavings,
)
from file_organizer.services.analytics import AnalyticsService
from file_organizer.services.analytics.metrics_calculator import MetricsCalculator
from file_organizer.services.analytics.storage_analyzer import StorageAnalyzer


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


@pytest.fixture
def mock_storage_analyzer():
    """Create a mock StorageAnalyzer with preset returns."""
    analyzer = MagicMock(spec=StorageAnalyzer)
    analyzer.analyze_directory.return_value = StorageStats(
        total_size=5000,
        organized_size=4000,
        saved_size=1000,
        file_count=10,
        directory_count=3,
    )
    analyzer.calculate_size_distribution.return_value = FileDistribution(
        by_type={".txt": 5, ".jpg": 3, ".pdf": 2},
        total_files=10,
    )
    return analyzer


@pytest.fixture
def mock_metrics_calculator():
    """Create a mock MetricsCalculator with preset returns."""
    calc = MagicMock(spec=MetricsCalculator)
    calc.measure_naming_compliance.return_value = 0.85
    calc.calculate_quality_score.return_value = 75.0
    return calc


@pytest.fixture
def mock_service(mock_storage_analyzer, mock_metrics_calculator):
    """Create an AnalyticsService with mocked dependencies."""
    return AnalyticsService(
        storage_analyzer=mock_storage_analyzer,
        metrics_calculator=mock_metrics_calculator,
    )


@pytest.mark.unit
class TestAnalyticsServiceInit:
    """Test AnalyticsService initialization."""

    def test_default_initialization(self):
        """Test service creates default dependencies when none provided."""
        service = AnalyticsService()
        assert isinstance(service.storage_analyzer, StorageAnalyzer)
        assert isinstance(service.metrics_calculator, MetricsCalculator)

    def test_custom_storage_analyzer(self):
        """Test service accepts custom storage analyzer."""
        custom_analyzer = MagicMock(spec=StorageAnalyzer)
        service = AnalyticsService(storage_analyzer=custom_analyzer)
        assert service.storage_analyzer is custom_analyzer
        assert isinstance(service.metrics_calculator, MetricsCalculator)

    def test_custom_metrics_calculator(self):
        """Test service accepts custom metrics calculator."""
        custom_calc = MagicMock(spec=MetricsCalculator)
        service = AnalyticsService(metrics_calculator=custom_calc)
        assert isinstance(service.storage_analyzer, StorageAnalyzer)
        assert service.metrics_calculator is custom_calc

    def test_both_custom_dependencies(self, mock_storage_analyzer, mock_metrics_calculator):
        """Test service accepts both custom dependencies."""
        service = AnalyticsService(
            storage_analyzer=mock_storage_analyzer,
            metrics_calculator=mock_metrics_calculator,
        )
        assert service.storage_analyzer is mock_storage_analyzer
        assert service.metrics_calculator is mock_metrics_calculator


@pytest.mark.unit
class TestGetStorageStats:
    """Test get_storage_stats method."""

    def test_delegates_to_storage_analyzer(self, mock_service, mock_storage_analyzer):
        """Test that get_storage_stats delegates to storage analyzer."""
        directory = Path("/fake/dir")
        result = mock_service.get_storage_stats(directory)

        mock_storage_analyzer.analyze_directory.assert_called_once_with(directory, None)
        assert isinstance(result, StorageStats)
        assert result.file_count == 10

    def test_passes_max_depth(self, mock_service, mock_storage_analyzer):
        """Test that max_depth parameter is forwarded."""
        directory = Path("/fake/dir")
        mock_service.get_storage_stats(directory, max_depth=2)

        mock_storage_analyzer.analyze_directory.assert_called_once_with(directory, 2)

    def test_real_directory(self, temp_directory):
        """Test with real filesystem directory."""
        service = AnalyticsService()
        stats = service.get_storage_stats(temp_directory)

        assert isinstance(stats, StorageStats)
        assert stats.file_count == 6
        assert stats.directory_count == 3
        assert stats.total_size > 0


@pytest.mark.unit
class TestGetDuplicateStats:
    """Test get_duplicate_stats method."""

    def test_empty_groups(self):
        """Test with no duplicate groups."""
        service = AnalyticsService()
        stats = service.get_duplicate_stats([], total_size=1000)

        assert isinstance(stats, DuplicateStats)
        assert stats.total_duplicates == 0
        assert stats.duplicate_groups == 0
        assert stats.space_wasted == 0
        assert stats.space_recoverable == 0

    def test_single_group_with_string_paths(self, temp_directory):
        """Test duplicate stats with string file paths."""
        dup1 = temp_directory / "dup1.txt"
        dup2 = temp_directory / "dup2.txt"
        dup1.write_text("duplicate content")
        dup2.write_text("duplicate content")

        service = AnalyticsService()
        groups = [{"files": [str(dup1), str(dup2)]}]
        stats = service.get_duplicate_stats(groups, total_size=10000)

        assert stats.duplicate_groups == 1
        assert stats.total_duplicates == 1  # extra copies only
        assert stats.space_wasted > 0
        assert stats.space_recoverable == stats.space_wasted

    def test_single_group_with_path_objects(self, temp_directory):
        """Test duplicate stats with Path objects instead of strings."""
        dup1 = temp_directory / "dup_a.txt"
        dup2 = temp_directory / "dup_b.txt"
        dup1.write_text("same content here")
        dup2.write_text("same content here")

        service = AnalyticsService()
        groups = [{"files": [dup1, dup2]}]
        stats = service.get_duplicate_stats(groups, total_size=10000)

        assert stats.duplicate_groups == 1
        assert stats.total_duplicates == 1
        assert stats.space_wasted > 0

    def test_multiple_duplicate_groups(self, temp_directory):
        """Test with multiple duplicate groups."""
        # Group 1: 3 files
        g1f1 = temp_directory / "g1_a.txt"
        g1f2 = temp_directory / "g1_b.txt"
        g1f3 = temp_directory / "g1_c.txt"
        for f in [g1f1, g1f2, g1f3]:
            f.write_text("group1 content")

        # Group 2: 2 files (larger)
        g2f1 = temp_directory / "g2_a.dat"
        g2f2 = temp_directory / "g2_b.dat"
        for f in [g2f1, g2f2]:
            f.write_bytes(b"x" * 10000)

        service = AnalyticsService()
        groups = [
            {"files": [str(g1f1), str(g1f2), str(g1f3)]},
            {"files": [str(g2f1), str(g2f2)]},
        ]
        stats = service.get_duplicate_stats(groups, total_size=50000)

        assert stats.duplicate_groups == 2
        assert stats.total_duplicates == 3  # 2 extra from group1 + 1 extra from group2
        assert stats.space_wasted > 0
        assert ".txt" in stats.by_type
        assert ".dat" in stats.by_type
        assert stats.largest_duplicate_group is not None

    def test_single_file_group_ignored(self, temp_directory):
        """Test that groups with only one file are ignored."""
        single = temp_directory / "single.txt"
        single.write_text("only one")

        service = AnalyticsService()
        groups = [{"files": [str(single)]}]
        stats = service.get_duplicate_stats(groups, total_size=10000)

        assert stats.duplicate_groups == 0
        assert stats.total_duplicates == 0
        assert stats.space_wasted == 0

    def test_empty_files_list_in_group(self):
        """Test group with empty files list."""
        service = AnalyticsService()
        groups = [{"files": []}]
        stats = service.get_duplicate_stats(groups, total_size=10000)

        assert stats.duplicate_groups == 0
        assert stats.total_duplicates == 0

    def test_nonexistent_file_in_group(self, temp_directory):
        """Test group where the first file does not exist on disk."""
        service = AnalyticsService()
        groups = [
            {
                "files": [
                    str(temp_directory / "nonexistent.txt"),
                    str(temp_directory / "also_gone.txt"),
                ]
            }
        ]
        stats = service.get_duplicate_stats(groups, total_size=10000)

        # Group is counted but no space calculated since file doesn't exist
        assert stats.duplicate_groups == 1
        assert stats.total_duplicates == 1
        assert stats.space_wasted == 0

    def test_no_extension_file(self, temp_directory):
        """Test duplicate files without extensions."""
        dup1 = temp_directory / "Makefile"
        dup2 = temp_directory / "Dockerfile"
        dup1.write_text("content")
        dup2.write_text("content")

        service = AnalyticsService()
        groups = [{"files": [str(dup1), str(dup2)]}]
        stats = service.get_duplicate_stats(groups, total_size=10000)

        # Files without extension get "no_extension" in by_type
        # Makefile has no suffix, so it falls to "no_extension"
        # Note: "Makefile" has no suffix, so suffix.lower() == ""
        assert stats.duplicate_groups == 1

    def test_largest_group_tracking(self, temp_directory):
        """Test that the largest duplicate group is correctly tracked."""
        # Small group
        s1 = temp_directory / "small1.txt"
        s2 = temp_directory / "small2.txt"
        s1.write_text("tiny")
        s2.write_text("tiny")

        # Large group (bigger files, more copies)
        l1 = temp_directory / "large1.bin"
        l2 = temp_directory / "large2.bin"
        l3 = temp_directory / "large3.bin"
        for f in [l1, l2, l3]:
            f.write_bytes(b"x" * 50000)

        service = AnalyticsService()
        groups = [
            {"files": [str(s1), str(s2)]},
            {"files": [str(l1), str(l2), str(l3)]},
        ]
        stats = service.get_duplicate_stats(groups, total_size=200000)

        assert stats.largest_duplicate_group is not None
        assert stats.largest_duplicate_group["count"] == 3
        assert stats.largest_duplicate_group["size"] == 50000
        assert stats.largest_duplicate_group["wasted"] == 100000

    def test_group_missing_files_key(self):
        """Test group dict without 'files' key defaults to empty list."""
        service = AnalyticsService()
        groups = [{}]
        stats = service.get_duplicate_stats(groups, total_size=10000)

        assert stats.duplicate_groups == 0
        assert stats.total_duplicates == 0


@pytest.mark.unit
class TestGetQualityMetrics:
    """Test get_quality_metrics method."""

    def test_basic_quality_metrics(self, temp_directory):
        """Test basic quality metrics calculation."""
        service = AnalyticsService()
        metrics = service.get_quality_metrics(temp_directory, total_files=6, organized_size=1000)

        assert isinstance(metrics, QualityMetrics)
        assert 0 <= metrics.quality_score <= 100
        assert 0 <= metrics.naming_compliance <= 1
        assert 0 <= metrics.structure_consistency <= 1
        assert metrics.metadata_completeness == 0.5
        assert metrics.categorization_accuracy == 0.7

    def test_quality_with_mocked_dependencies(self, mock_service, temp_directory):
        """Test quality metrics with mocked calculator."""
        metrics = mock_service.get_quality_metrics(
            temp_directory, total_files=10, organized_size=500
        )

        assert isinstance(metrics, QualityMetrics)
        assert metrics.quality_score == 75.0
        assert metrics.naming_compliance == 0.85

    def test_quality_zero_total_files(self, temp_directory):
        """Test quality metrics when total_files is zero."""
        service = AnalyticsService()
        metrics = service.get_quality_metrics(temp_directory, total_files=0, organized_size=0)

        assert isinstance(metrics, QualityMetrics)
        # structure_consistency uses max(total_files, 1) to avoid division by zero
        assert metrics.structure_consistency >= 0

    def test_quality_score_boundaries(self, temp_directory):
        """Test quality score stays within valid range."""
        service = AnalyticsService()
        for total_files in [0, 1, 10, 100, 1000]:
            metrics = service.get_quality_metrics(
                temp_directory, total_files=total_files, organized_size=100
            )
            assert 0 <= metrics.quality_score <= 100

    def test_empty_directory_quality(self):
        """Test quality metrics for empty directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            service = AnalyticsService()
            metrics = service.get_quality_metrics(Path(tmpdir), total_files=0, organized_size=0)
            assert isinstance(metrics, QualityMetrics)


@pytest.mark.unit
class TestCalculateTimeSaved:
    """Test calculate_time_saved method."""

    def test_basic_time_savings(self):
        """Test standard time savings calculation."""
        service = AnalyticsService()
        savings = service.calculate_time_saved(total_files=100, duplicates_removed=10)

        assert savings.total_operations == 100
        assert savings.automated_operations == 100
        # manual_time = 100*30 + 10*60 = 3600
        assert savings.manual_time_seconds == 3600
        # automated_time = 100
        assert savings.automated_time_seconds == 100
        # time_saved = 3600 - 100 = 3500
        assert savings.estimated_time_saved_seconds == 3500

    def test_zero_files(self):
        """Test time savings with zero files."""
        service = AnalyticsService()
        savings = service.calculate_time_saved(total_files=0, duplicates_removed=0)

        assert savings.total_operations == 0
        assert savings.automated_operations == 0
        assert savings.manual_time_seconds == 0
        assert savings.automated_time_seconds == 0
        assert savings.estimated_time_saved_seconds == 0

    def test_no_duplicates(self):
        """Test time savings with no duplicates removed."""
        service = AnalyticsService()
        savings = service.calculate_time_saved(total_files=50, duplicates_removed=0)

        assert savings.total_operations == 50
        assert savings.manual_time_seconds == 50 * 30
        assert savings.automated_time_seconds == 50
        assert savings.estimated_time_saved_seconds == (50 * 30) - 50

    def test_large_scale(self):
        """Test time savings with large file count."""
        service = AnalyticsService()
        savings = service.calculate_time_saved(total_files=10000, duplicates_removed=500)

        assert savings.total_operations == 10000
        expected_manual = 10000 * 30 + 500 * 60
        assert savings.manual_time_seconds == expected_manual
        assert savings.estimated_time_saved_seconds == expected_manual - 10000

    def test_automation_percentage(self):
        """Test that automation percentage is always 100% (all ops automated)."""
        service = AnalyticsService()
        savings = service.calculate_time_saved(total_files=100, duplicates_removed=10)
        assert savings.automation_percentage == 100.0


@pytest.mark.unit
class TestGenerateDashboard:
    """Test generate_dashboard method."""

    def test_dashboard_with_real_directory(self, temp_directory):
        """Test complete dashboard generation with real filesystem."""
        service = AnalyticsService()
        dashboard = service.generate_dashboard(temp_directory)

        assert isinstance(dashboard, AnalyticsDashboard)
        assert dashboard.storage_stats is not None
        assert dashboard.file_distribution is not None
        assert dashboard.duplicate_stats is not None
        assert dashboard.quality_metrics is not None
        assert dashboard.time_savings is not None
        assert isinstance(dashboard.generated_at, datetime)

    def test_dashboard_with_mocked_deps(self, mock_service, mock_storage_analyzer):
        """Test dashboard generation with mocked dependencies."""
        directory = Path("/fake/dir")

        # Need to mock rglob for quality metrics
        with patch.object(Path, "rglob", return_value=iter([])):
            dashboard = mock_service.generate_dashboard(directory)

        assert isinstance(dashboard, AnalyticsDashboard)
        assert dashboard.storage_stats.file_count == 10
        assert dashboard.duplicate_stats.total_duplicates == 0

    def test_dashboard_with_duplicate_groups(self, temp_directory):
        """Test dashboard generation with explicit duplicate groups."""
        dup1 = temp_directory / "dup_x.txt"
        dup2 = temp_directory / "dup_y.txt"
        dup1.write_text("same content")
        dup2.write_text("same content")

        service = AnalyticsService()
        dashboard = service.generate_dashboard(
            temp_directory,
            duplicate_groups=[{"files": [str(dup1), str(dup2)]}],
        )

        assert dashboard.duplicate_stats.duplicate_groups == 1
        assert dashboard.duplicate_stats.total_duplicates == 1
        assert dashboard.duplicate_stats.space_wasted > 0

    def test_dashboard_with_max_depth(self, temp_directory):
        """Test dashboard respects max_depth parameter."""
        (temp_directory / "level1" / "level2" / "level3").mkdir(parents=True)
        (temp_directory / "level1" / "level2" / "level3" / "deep.txt").write_text("deep file")

        service = AnalyticsService()
        dashboard = service.generate_dashboard(temp_directory, max_depth=1)

        assert isinstance(dashboard, AnalyticsDashboard)

    def test_dashboard_generated_at_is_recent(self, temp_directory):
        """Test that generated_at timestamp is close to current time."""
        service = AnalyticsService()
        before = datetime.now(UTC)
        dashboard = service.generate_dashboard(temp_directory)
        after = datetime.now(UTC)

        assert before <= dashboard.generated_at <= after


@pytest.mark.unit
class TestExportDashboard:
    """Test export_dashboard method."""

    def test_export_json(self, temp_directory):
        """Test exporting dashboard to JSON format."""
        service = AnalyticsService()
        dashboard = service.generate_dashboard(temp_directory)

        output_file = temp_directory / "analytics.json"
        service.export_dashboard(dashboard, output_file, format="json")

        assert output_file.exists()
        assert output_file.stat().st_size > 0

        data = json.loads(output_file.read_text())
        assert "storage_stats" in data
        assert "quality_metrics" in data
        assert "duplicate_stats" in data
        assert "time_savings" in data
        assert "generated_at" in data

    def test_export_json_structure(self, temp_directory):
        """Test JSON export has correct nested structure."""
        service = AnalyticsService()
        dashboard = service.generate_dashboard(temp_directory)

        output_file = temp_directory / "export.json"
        service.export_dashboard(dashboard, output_file, format="json")

        data = json.loads(output_file.read_text())
        assert "file_count" in data["storage_stats"]
        assert "quality_score" in data["quality_metrics"]
        assert "total_duplicates" in data["duplicate_stats"]
        assert "automation_percentage" in data["time_savings"]

    def test_export_text(self, temp_directory):
        """Test exporting dashboard to text format."""
        service = AnalyticsService()
        dashboard = service.generate_dashboard(temp_directory)

        output_file = temp_directory / "analytics.txt"
        service.export_dashboard(dashboard, output_file, format="text")

        assert output_file.exists()
        content = output_file.read_text()
        assert "Analytics Dashboard" in content
        assert "STORAGE STATISTICS" in content
        assert "QUALITY METRICS" in content
        assert "DUPLICATE STATISTICS" in content
        assert "TIME SAVINGS" in content
        assert "FILE DISTRIBUTION" in content

    def test_export_invalid_format_raises(self, temp_directory):
        """Test that invalid format raises ValueError."""
        service = AnalyticsService()
        dashboard = service.generate_dashboard(temp_directory)

        with pytest.raises(ValueError, match="Unsupported format"):
            service.export_dashboard(dashboard, temp_directory / "out.xml", format="xml")

    def test_export_invalid_format_csv(self, temp_directory):
        """Test that csv format also raises ValueError."""
        service = AnalyticsService()
        dashboard = service.generate_dashboard(temp_directory)

        with pytest.raises(ValueError, match="Unsupported format: csv"):
            service.export_dashboard(dashboard, temp_directory / "out.csv", format="csv")


@pytest.mark.unit
class TestFormatDashboardText:
    """Test _format_dashboard_text private method."""

    def _make_dashboard(self) -> AnalyticsDashboard:
        """Create a minimal dashboard for testing text formatting."""
        return AnalyticsDashboard(
            storage_stats=StorageStats(
                total_size=1048576,
                organized_size=900000,
                saved_size=148576,
                file_count=42,
                directory_count=5,
            ),
            file_distribution=FileDistribution(
                by_type={".txt": 20, ".jpg": 15, ".pdf": 7},
                total_files=42,
            ),
            duplicate_stats=DuplicateStats(
                total_duplicates=3,
                duplicate_groups=2,
                space_wasted=50000,
                space_recoverable=50000,
            ),
            quality_metrics=QualityMetrics(
                quality_score=82.5,
                naming_compliance=0.9,
                structure_consistency=0.75,
                metadata_completeness=0.6,
                categorization_accuracy=0.8,
            ),
            time_savings=TimeSavings(
                total_operations=42,
                automated_operations=42,
                manual_time_seconds=1260,
                automated_time_seconds=42,
                estimated_time_saved_seconds=1218,
            ),
        )

    def test_text_contains_all_sections(self):
        """Test that formatted text contains all expected sections."""
        service = AnalyticsService()
        dashboard = self._make_dashboard()
        text = service._format_dashboard_text(dashboard)

        assert "File Organizer Analytics Dashboard" in text
        assert "STORAGE STATISTICS" in text
        assert "QUALITY METRICS" in text
        assert "DUPLICATE STATISTICS" in text
        assert "TIME SAVINGS" in text
        assert "FILE DISTRIBUTION" in text

    def test_text_contains_storage_values(self):
        """Test that storage stats values appear in text."""
        service = AnalyticsService()
        dashboard = self._make_dashboard()
        text = service._format_dashboard_text(dashboard)

        assert "Files: 42" in text
        assert "Directories: 5" in text

    def test_text_contains_quality_values(self):
        """Test that quality metric values appear in text."""
        service = AnalyticsService()
        dashboard = self._make_dashboard()
        text = service._format_dashboard_text(dashboard)

        assert "82.5/100" in text
        assert "90.0%" in text  # naming_compliance * 100
        assert "75.0%" in text  # structure_consistency * 100

    def test_text_contains_duplicate_values(self):
        """Test that duplicate stat values appear in text."""
        service = AnalyticsService()
        dashboard = self._make_dashboard()
        text = service._format_dashboard_text(dashboard)

        assert "Duplicate Groups: 2" in text
        assert "Total Duplicates: 3" in text

    def test_text_contains_time_savings_values(self):
        """Test that time savings values appear in text."""
        service = AnalyticsService()
        dashboard = self._make_dashboard()
        text = service._format_dashboard_text(dashboard)

        assert "100.0%" in text  # automation rate
        assert "Total Operations: 42" in text

    def test_text_contains_distribution_values(self):
        """Test that file distribution values appear in text."""
        service = AnalyticsService()
        dashboard = self._make_dashboard()
        text = service._format_dashboard_text(dashboard)

        assert "Total Files: 42" in text
        assert "File Types: 3" in text

    def test_text_contains_generated_timestamp(self):
        """Test that generated_at timestamp appears in text."""
        service = AnalyticsService()
        dashboard = self._make_dashboard()
        text = service._format_dashboard_text(dashboard)

        assert "Generated:" in text


@pytest.mark.unit
class TestDashboardToDict:
    """Test dashboard.to_dict() serialization."""

    def test_to_dict_structure(self, temp_directory):
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

    def test_to_dict_json_serializable(self, temp_directory):
        """Test that to_dict output is JSON-serializable."""
        service = AnalyticsService()
        dashboard = service.generate_dashboard(temp_directory)

        # Should not raise
        json_str = json.dumps(dashboard.to_dict())
        assert len(json_str) > 0


@pytest.mark.unit
class TestEmptyDirectoryHandling:
    """Test handling of empty directories."""

    def test_empty_dir_storage_stats(self):
        """Test storage stats for empty directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            service = AnalyticsService()
            stats = service.get_storage_stats(Path(tmpdir))

            assert stats.file_count == 0
            assert stats.total_size == 0
            assert stats.directory_count == 0

    def test_empty_dir_full_dashboard(self):
        """Test full dashboard generation for empty directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            service = AnalyticsService()
            dashboard = service.generate_dashboard(Path(tmpdir))

            assert isinstance(dashboard, AnalyticsDashboard)
            assert dashboard.storage_stats.file_count == 0
            assert dashboard.duplicate_stats.total_duplicates == 0
            assert dashboard.time_savings.total_operations == 0


@pytest.mark.unit
class TestLargeFilesIdentification:
    """Test identification of large files in storage stats."""

    def test_large_file_appears_in_stats(self, temp_directory):
        """Test that large files are tracked in storage stats."""
        large_file = temp_directory / "large.bin"
        large_file.write_bytes(b"x" * (200 * 1024 * 1024))  # 200MB

        service = AnalyticsService()
        stats = service.get_storage_stats(temp_directory)

        assert any(f.path == large_file for f in stats.largest_files)
        largest = next(f for f in stats.largest_files if f.path == large_file)
        assert largest.size > 100 * 1024 * 1024
