"""Tests for TUI analytics dashboard view."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from file_organizer.tui.analytics_view import (
    AnalyticsView,
    DuplicateStatsPanel,
    FileDistributionPanel,
    QualityScorePanel,
    StorageOverviewPanel,
    _format_bytes,
)


def _get_content(widget: object) -> str:
    """Extract the text content from a Static widget."""
    # Textual stores update() content in the _content attribute
    return str(getattr(widget, "_content", ""))


@pytest.mark.unit
class TestFormatBytes:
    """Unit tests for the _format_bytes helper."""

    def test_zero(self) -> None:
        assert _format_bytes(0) == "0 B"

    def test_bytes(self) -> None:
        assert _format_bytes(512) == "512 B"

    def test_kilobytes(self) -> None:
        result = _format_bytes(1536)
        assert "KB" in result

    def test_megabytes(self) -> None:
        result = _format_bytes(5 * 1024 * 1024)
        assert "MB" in result

    def test_gigabytes(self) -> None:
        result = _format_bytes(2 * 1024 * 1024 * 1024)
        assert "GB" in result


@pytest.mark.unit
class TestStorageOverviewPanel:
    """Unit tests for StorageOverviewPanel."""

    def test_set_stats(self) -> None:
        panel = StorageOverviewPanel()
        panel.set_stats(
            total_size="1.5 GB",
            file_count=1234,
            dir_count=56,
            organized_size="1.2 GB",
            saved_size="300 MB",
        )
        content = _get_content(panel)
        assert "1.5 GB" in content
        assert "1,234" in content
        assert "300 MB" in content


@pytest.mark.unit
class TestFileDistributionPanel:
    """Unit tests for FileDistributionPanel."""

    def test_empty_distribution(self) -> None:
        panel = FileDistributionPanel()
        panel.set_distribution({})
        assert "No data" in _get_content(panel)

    def test_with_data(self) -> None:
        panel = FileDistributionPanel()
        panel.set_distribution(
            {
                ".pdf": 5_000_000,
                ".jpg": 3_000_000,
                ".txt": 500_000,
            }
        )
        content = _get_content(panel)
        assert ".pdf" in content
        assert ".jpg" in content


@pytest.mark.unit
class TestQualityScorePanel:
    """Unit tests for QualityScorePanel."""

    def test_set_metrics(self) -> None:
        panel = QualityScorePanel()
        panel.set_metrics(
            grade="B+",
            naming=0.8,
            structure=0.7,
            metadata=0.6,
            categorization=0.9,
        )
        content = _get_content(panel)
        assert "B+" in content
        assert "80%" in content
        assert "90%" in content


@pytest.mark.unit
class TestDuplicateStatsPanel:
    """Unit tests for DuplicateStatsPanel."""

    def test_set_stats(self) -> None:
        panel = DuplicateStatsPanel()
        panel.set_stats(groups=12, space_wasted="250 MB", recoverable="200 MB")
        content = _get_content(panel)
        assert "12" in content
        assert "250 MB" in content
        assert "200 MB" in content


@pytest.mark.unit
class TestAnalyticsView:
    """Tests for AnalyticsView."""

    def test_default_init(self) -> None:
        view = AnalyticsView(id="view")
        assert str(view._directory) == "."

    def test_custom_directory(self) -> None:
        view = AnalyticsView(directory="/tmp/data", id="view")
        assert str(view._directory) == "/tmp/data"


@pytest.mark.asyncio
async def test_analytics_view_mounts() -> None:
    """AnalyticsView should mount with all four panels."""
    from file_organizer.tui.app import FileOrganizerApp

    with patch.object(AnalyticsView, "_load_analytics"):
        app = FileOrganizerApp()
        async with app.run_test() as pilot:
            await app.action_switch_view("analytics")
            await pilot.pause()
            view = app.query_one("#view", AnalyticsView)
            assert view is not None
            assert view.query_one(StorageOverviewPanel) is not None
            assert view.query_one(FileDistributionPanel) is not None
            assert view.query_one(QualityScorePanel) is not None
            assert view.query_one(DuplicateStatsPanel) is not None
            await pilot.press("q")


@pytest.mark.asyncio
async def test_refresh_binding() -> None:
    """Pressing 'r' should trigger a refresh."""
    from file_organizer.tui.app import FileOrganizerApp

    with patch.object(AnalyticsView, "_load_analytics") as mock_load:
        app = FileOrganizerApp()
        async with app.run_test() as pilot:
            await app.action_switch_view("analytics")
            await pilot.pause()
            mock_load.reset_mock()
            view = app.query_one("#view", AnalyticsView)
            view.action_refresh_analytics()
            await pilot.pause()
            mock_load.assert_called()
