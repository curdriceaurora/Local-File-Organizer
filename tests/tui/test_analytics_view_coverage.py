"""Coverage tests for file_organizer.tui.analytics_view module.

Targets uncovered branches: AnalyticsView._load_analytics worker,
action_refresh_analytics, and _set_status.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, PropertyMock, call, patch

import pytest

from file_organizer.tui.analytics_view import (
    AnalyticsView,
    DuplicateStatsPanel,
    FileDistributionPanel,
    QualityScorePanel,
    StorageOverviewPanel,
    _format_bytes,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# _format_bytes edge cases
# ---------------------------------------------------------------------------


class TestFormatBytesCoverage:
    """Additional edge cases for _format_bytes."""

    def test_negative_bytes(self) -> None:
        """Negative bytes should still work (absolute comparison)."""
        result = _format_bytes(-1024)
        assert "KB" in result

    def test_large_value(self) -> None:
        result = _format_bytes(1024**6)
        assert "PB" in result


# ---------------------------------------------------------------------------
# AnalyticsView - _load_analytics worker
# ---------------------------------------------------------------------------


class TestAnalyticsViewLoadAnalytics:
    """Test _load_analytics worker thread paths."""

    def test_load_analytics_success(self) -> None:
        view = AnalyticsView()
        storage_panel = MagicMock()
        distribution_panel = MagicMock()
        quality_panel = MagicMock()
        duplicate_panel = MagicMock()

        def _query_side_effect(panel_type):
            mapping = {
                StorageOverviewPanel: storage_panel,
                FileDistributionPanel: distribution_panel,
                QualityScorePanel: quality_panel,
                DuplicateStatsPanel: duplicate_panel,
            }
            return mapping[panel_type]

        view.query_one = MagicMock(side_effect=_query_side_effect)

        mock_dashboard = SimpleNamespace(
            storage_stats=SimpleNamespace(
                formatted_total_size="10 GB",
                file_count=100,
                directory_count=10,
                organized_size=5_000_000,
                formatted_saved_size="2 GB",
                size_by_type={".txt": 1000, ".py": 2000},
            ),
            quality_metrics=SimpleNamespace(
                grade="B",
                naming_compliance=0.8,
                structure_consistency=0.7,
                metadata_completeness=0.6,
                categorization_accuracy=0.9,
            ),
            duplicate_stats=SimpleNamespace(
                duplicate_groups=3,
                formatted_space_wasted="500 MB",
                formatted_recoverable="300 MB",
            ),
        )

        mock_service = MagicMock()
        mock_service.generate_dashboard.return_value = mock_dashboard

        mock_app = MagicMock()
        mock_app.call_from_thread.side_effect = lambda fn, *a, **kw: fn(*a, **kw)
        with (
            patch(
                "file_organizer.services.analytics.analytics_service.AnalyticsService",
                return_value=mock_service,
            ),
            patch.object(type(view), "app", new_callable=PropertyMock, return_value=mock_app),
        ):
            AnalyticsView._load_analytics.__wrapped__(view)

        storage_panel.set_stats.assert_called_once_with(
            total_size="10 GB",
            file_count=100,
            dir_count=10,
            organized_size=_format_bytes(5_000_000),
            saved_size="2 GB",
        )
        distribution_panel.set_distribution.assert_called_once_with({".txt": 1000, ".py": 2000})
        quality_panel.set_metrics.assert_called_once_with(
            grade="B",
            naming=0.8,
            structure=0.7,
            metadata=0.6,
            categorization=0.9,
        )
        duplicate_panel.set_stats.assert_called_once_with(
            groups=3,
            space_wasted="500 MB",
            recoverable="300 MB",
        )
        assert mock_app.call_from_thread.call_count == 5
        assert mock_app.call_from_thread.call_args_list[-1] == call(
            view._set_status,
            "Analytics loaded",
        )

    def test_load_analytics_exception(self) -> None:
        view = AnalyticsView()
        storage_panel = MagicMock()
        distribution_panel = MagicMock()
        quality_panel = MagicMock()
        duplicate_panel = MagicMock()

        def _query_side_effect(panel_type):
            mapping = {
                StorageOverviewPanel: storage_panel,
                FileDistributionPanel: distribution_panel,
                QualityScorePanel: quality_panel,
                DuplicateStatsPanel: duplicate_panel,
            }
            return mapping[panel_type]

        view.query_one = MagicMock(side_effect=_query_side_effect)

        mock_app = MagicMock()
        mock_app.call_from_thread.side_effect = lambda fn, *a, **kw: fn(*a, **kw)
        with (
            patch(
                "file_organizer.services.analytics.analytics_service.AnalyticsService",
                side_effect=RuntimeError("service error"),
            ),
            patch.object(type(view), "app", new_callable=PropertyMock, return_value=mock_app),
        ):
            AnalyticsView._load_analytics.__wrapped__(view)

        assert mock_app.call_from_thread.call_count == 4
        for panel in (storage_panel, distribution_panel, quality_panel, duplicate_panel):
            panel.update.assert_called_once()
            assert panel.update.call_args.args[0].startswith("[red]Analytics unavailable:[/red]")

    def test_action_refresh_analytics(self) -> None:
        view = AnalyticsView()
        mock_panel = MagicMock()
        view.query_one = MagicMock(return_value=mock_panel)
        view._load_analytics = MagicMock()
        view.action_refresh_analytics()
        view._load_analytics.assert_called_once()

    def test_set_status_no_app(self) -> None:
        view = AnalyticsView()
        view._set_status("test")  # Should not crash

    def test_set_status_with_app(self) -> None:
        view = AnalyticsView()
        mock_bar = MagicMock()
        mock_app = MagicMock()
        mock_app.query_one.return_value = mock_bar
        with patch.object(type(view), "app", new_callable=PropertyMock, return_value=mock_app):
            view._set_status("loaded")
