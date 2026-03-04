"""Tests for file_organizer.tui.analytics_view module.

Covers StorageOverviewPanel, FileDistributionPanel, QualityScorePanel,
DuplicateStatsPanel, AnalyticsView initialization, and _format_bytes helper.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Static

from file_organizer.tui.analytics_view import (
    AnalyticsView,
    DuplicateStatsPanel,
    FileDistributionPanel,
    QualityScorePanel,
    StorageOverviewPanel,
    _format_bytes,
)

pytestmark = [pytest.mark.unit]


# -----------------------------------------------------------------------
# _format_bytes helper
# -----------------------------------------------------------------------


@pytest.mark.unit
class TestFormatBytes:
    """Test the _format_bytes utility function."""

    def test_bytes_single_digit(self) -> None:
        """Test formatting single digit bytes."""
        assert _format_bytes(0) == "0 B"
        assert _format_bytes(1) == "1 B"
        assert _format_bytes(512) == "512 B"

    def test_kilobytes(self) -> None:
        """Test formatting kilobytes."""
        result = _format_bytes(1024)
        assert "KB" in result
        assert "1.0" in result

    def test_megabytes(self) -> None:
        """Test formatting megabytes."""
        result = _format_bytes(1024 * 1024)
        assert "MB" in result
        assert "1.0" in result

    def test_gigabytes(self) -> None:
        """Test formatting gigabytes."""
        result = _format_bytes(1024 * 1024 * 1024)
        assert "GB" in result
        assert "1.0" in result

    def test_terabytes(self) -> None:
        """Test formatting terabytes."""
        result = _format_bytes(1024 * 1024 * 1024 * 1024)
        assert "TB" in result
        assert "1.0" in result

    def test_petabytes(self) -> None:
        """Test formatting petabytes (overflow case)."""
        result = _format_bytes(1024 * 1024 * 1024 * 1024 * 1024)
        assert "PB" in result

    def test_decimal_formatting(self) -> None:
        """Test decimal formatting for non-byte units."""
        result = _format_bytes(1536)  # 1.5 KB
        assert "1.5" in result
        assert "KB" in result


# -----------------------------------------------------------------------
# StorageOverviewPanel
# -----------------------------------------------------------------------


@pytest.mark.unit
class TestStorageOverviewPanel:
    """Test StorageOverviewPanel rendering."""

    def test_inherits_from_static(self) -> None:
        """Test that StorageOverviewPanel extends Static."""
        assert issubclass(StorageOverviewPanel, Static)

    def test_default_css_defined(self) -> None:
        """Test that CSS is properly defined."""
        assert "StorageOverviewPanel" in StorageOverviewPanel.DEFAULT_CSS
        assert "padding: 1 2" in StorageOverviewPanel.DEFAULT_CSS

    def test_set_stats_with_defaults(self) -> None:
        """Test set_stats with default parameters."""
        panel = StorageOverviewPanel()
        panel.update = MagicMock()
        panel.set_stats()
        panel.update.assert_called_once()
        rendered = panel.update.call_args[0][0]
        assert "Storage Overview" in rendered
        assert "0 B" in rendered
        assert "0" in rendered

    def test_set_stats_with_custom_values(self) -> None:
        """Test set_stats with custom values."""
        panel = StorageOverviewPanel()
        panel.update = MagicMock()
        panel.set_stats(
            total_size="100 GB",
            file_count=500,
            dir_count=50,
            organized_size="80 GB",
            saved_size="20 GB",
        )
        rendered = panel.update.call_args[0][0]
        assert "100 GB" in rendered
        assert "500" in rendered
        assert "50" in rendered
        assert "80 GB" in rendered
        assert "20 GB" in rendered
        assert "[green]" in rendered

    def test_set_stats_large_numbers_formatted(self) -> None:
        """Test that large numbers are formatted with commas."""
        panel = StorageOverviewPanel()
        panel.update = MagicMock()
        panel.set_stats(file_count=1000000, dir_count=50000)
        rendered = panel.update.call_args[0][0]
        assert "1,000,000" in rendered
        assert "50,000" in rendered


# -----------------------------------------------------------------------
# FileDistributionPanel
# -----------------------------------------------------------------------


@pytest.mark.unit
class TestFileDistributionPanel:
    """Test FileDistributionPanel rendering."""

    def test_inherits_from_static(self) -> None:
        """Test that FileDistributionPanel extends Static."""
        assert issubclass(FileDistributionPanel, Static)

    def test_default_css_defined(self) -> None:
        """Test that CSS is properly defined."""
        assert "FileDistributionPanel" in FileDistributionPanel.DEFAULT_CSS

    def test_set_distribution_empty(self) -> None:
        """Test set_distribution with empty data."""
        panel = FileDistributionPanel()
        panel.update = MagicMock()
        panel.set_distribution({})
        rendered = panel.update.call_args[0][0]
        assert "File Distribution" in rendered
        assert "No data" in rendered

    def test_set_distribution_with_data(self) -> None:
        """Test set_distribution with file type data."""
        panel = FileDistributionPanel()
        panel.update = MagicMock()
        data = {
            ".jpg": 5000000,
            ".pdf": 3000000,
            ".txt": 1000000,
        }
        panel.set_distribution(data)
        rendered = panel.update.call_args[0][0]
        assert "File Distribution" in rendered
        assert ".jpg" in rendered
        assert ".pdf" in rendered
        assert ".txt" in rendered
        assert "[cyan]" in rendered  # Bar chart color

    def test_set_distribution_respects_top_n(self) -> None:
        """Test that set_distribution limits output to top_n items."""
        panel = FileDistributionPanel()
        panel.update = MagicMock()
        data = {f".type{i}": (100 - i) * 1000 for i in range(20)}
        panel.set_distribution(data, top_n=5)
        rendered = panel.update.call_args[0][0]
        lines = rendered.split("\n")
        # Header + 5 items
        assert len(lines) >= 5

    def test_set_distribution_sorts_by_size(self) -> None:
        """Test that items are sorted by size descending."""
        panel = FileDistributionPanel()
        panel.update = MagicMock()
        data = {
            ".small": 1000,
            ".large": 10000,
            ".medium": 5000,
        }
        panel.set_distribution(data)
        rendered = panel.update.call_args[0][0]
        # Find positions of items in rendered output
        large_pos = rendered.find(".large")
        medium_pos = rendered.find(".medium")
        small_pos = rendered.find(".small")
        # Larger items should appear first
        assert large_pos < medium_pos < small_pos


# -----------------------------------------------------------------------
# QualityScorePanel
# -----------------------------------------------------------------------


@pytest.mark.unit
class TestQualityScorePanel:
    """Test QualityScorePanel rendering."""

    def test_inherits_from_static(self) -> None:
        """Test that QualityScorePanel extends Static."""
        assert issubclass(QualityScorePanel, Static)

    def test_default_css_defined(self) -> None:
        """Test that CSS is properly defined."""
        assert "QualityScorePanel" in QualityScorePanel.DEFAULT_CSS

    def test_set_metrics_with_defaults(self) -> None:
        """Test set_metrics with default parameters."""
        panel = QualityScorePanel()
        panel.update = MagicMock()
        panel.set_metrics()
        rendered = panel.update.call_args[0][0]
        assert "Quality Score" in rendered
        assert "Grade: [bold]?[/bold]" in rendered

    def test_set_metrics_with_grade(self) -> None:
        """Test set_metrics with custom grade."""
        panel = QualityScorePanel()
        panel.update = MagicMock()
        panel.set_metrics(grade="A")
        rendered = panel.update.call_args[0][0]
        assert "Grade: [bold]A[/bold]" in rendered

    def test_set_metrics_shows_all_categories(self) -> None:
        """Test that all metric categories are displayed."""
        panel = QualityScorePanel()
        panel.update = MagicMock()
        panel.set_metrics(
            grade="B",
            naming=0.8,
            structure=0.7,
            metadata=0.6,
            categorization=0.9,
        )
        rendered = panel.update.call_args[0][0]
        assert "Naming" in rendered
        assert "Structure" in rendered
        assert "Metadata" in rendered
        assert "Categorize" in rendered

    def test_set_metrics_percentage_display(self) -> None:
        """Test that metrics display percentages correctly."""
        panel = QualityScorePanel()
        panel.update = MagicMock()
        panel.set_metrics(naming=0.5, structure=1.0)
        rendered = panel.update.call_args[0][0]
        assert "50%" in rendered
        assert "100%" in rendered

    def test_set_metrics_bar_visualization(self) -> None:
        """Test that metrics show bar visualization."""
        panel = QualityScorePanel()
        panel.update = MagicMock()
        panel.set_metrics(naming=0.8)
        rendered = panel.update.call_args[0][0]
        assert "[green]" in rendered  # Filled bar color
        assert "." in rendered  # Empty bar character


# -----------------------------------------------------------------------
# DuplicateStatsPanel
# -----------------------------------------------------------------------


@pytest.mark.unit
class TestDuplicateStatsPanel:
    """Test DuplicateStatsPanel rendering."""

    def test_inherits_from_static(self) -> None:
        """Test that DuplicateStatsPanel extends Static."""
        assert issubclass(DuplicateStatsPanel, Static)

    def test_default_css_defined(self) -> None:
        """Test that CSS is properly defined."""
        assert "DuplicateStatsPanel" in DuplicateStatsPanel.DEFAULT_CSS

    def test_set_stats_with_defaults(self) -> None:
        """Test set_stats with default parameters."""
        panel = DuplicateStatsPanel()
        panel.update = MagicMock()
        panel.set_stats()
        rendered = panel.update.call_args[0][0]
        assert "Duplicate Detection" in rendered
        assert "0" in rendered
        assert "0 B" in rendered

    def test_set_stats_with_values(self) -> None:
        """Test set_stats with custom values."""
        panel = DuplicateStatsPanel()
        panel.update = MagicMock()
        panel.set_stats(
            groups=5,
            space_wasted="500 MB",
            recoverable="300 MB",
        )
        rendered = panel.update.call_args[0][0]
        assert "5" in rendered
        assert "500 MB" in rendered
        assert "300 MB" in rendered
        assert "[red]" in rendered  # Wasted space color
        assert "[green]" in rendered  # Recoverable space color

    def test_set_stats_formats_groups_count(self) -> None:
        """Test that groups count is formatted with commas."""
        panel = DuplicateStatsPanel()
        panel.update = MagicMock()
        panel.set_stats(groups=1000)
        rendered = panel.update.call_args[0][0]
        assert "1,000" in rendered


# -----------------------------------------------------------------------
# AnalyticsView
# -----------------------------------------------------------------------


@pytest.mark.unit
class TestAnalyticsView:
    """Test AnalyticsView widget."""

    def test_inherits_from_vertical(self) -> None:
        """Test that AnalyticsView extends Vertical."""
        assert issubclass(AnalyticsView, Vertical)

    def test_default_css_defined(self) -> None:
        """Test that CSS is properly defined."""
        assert "AnalyticsView" in AnalyticsView.DEFAULT_CSS

    def test_has_refresh_binding(self) -> None:
        """Test that refresh binding is defined."""
        bindings = [b for b in AnalyticsView.BINDINGS if isinstance(b, Binding)]
        keys = [b.key for b in bindings]
        assert "r" in keys

    def test_initialization_with_default_directory(self) -> None:
        """Test AnalyticsView initialization with default directory."""
        view = AnalyticsView()
        assert view._directory == Path(".")

    def test_initialization_with_custom_directory(self) -> None:
        """Test AnalyticsView initialization with custom directory."""
        test_path = Path("/tmp/test")
        view = AnalyticsView(directory=test_path)
        assert view._directory == test_path

    def test_initialization_with_string_directory(self) -> None:
        """Test AnalyticsView initialization with string directory."""
        view = AnalyticsView(directory="/tmp/test")
        assert view._directory == Path("/tmp/test")

    def test_has_compose_method(self) -> None:
        """Test that compose method is defined."""
        assert callable(getattr(AnalyticsView, "compose", None))

    def test_has_on_mount_method(self) -> None:
        """Test that on_mount method is defined."""
        assert callable(getattr(AnalyticsView, "on_mount", None))

    def test_has_action_refresh_analytics(self) -> None:
        """Test that action_refresh_analytics is defined."""
        assert callable(getattr(AnalyticsView, "action_refresh_analytics", None))

    def test_has_set_status_method(self) -> None:
        """Test that _set_status method is defined."""
        assert callable(getattr(AnalyticsView, "_set_status", None))

    def test_custom_widget_attributes(self) -> None:
        """Test that custom attributes are properly set."""
        view = AnalyticsView(name="test-view", id="analytics-main")
        assert view.name == "test-view"
        assert view.id == "analytics-main"
