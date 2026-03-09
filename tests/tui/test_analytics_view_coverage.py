"""Coverage tests for file_organizer.tui.analytics_view module.

Targets uncovered branches: AnalyticsView._load_analytics worker,
action_refresh_analytics, and _set_status.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from file_organizer.tui.analytics_view import (
    AnalyticsView,
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
        view.query_one = MagicMock()

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
        with (
            patch(
                "file_organizer.services.analytics.analytics_service.AnalyticsService",
                return_value=mock_service,
            ),
            patch.object(type(view), "app", new_callable=PropertyMock, return_value=mock_app),
        ):
            AnalyticsView._load_analytics.__wrapped__(view)

        # Should call call_from_thread multiple times for each panel
        assert mock_app.call_from_thread.call_count >= 5

    def test_load_analytics_exception(self) -> None:
        view = AnalyticsView()
        view.query_one = MagicMock()

        mock_app = MagicMock()
        with (
            patch(
                "file_organizer.services.analytics.analytics_service.AnalyticsService",
                side_effect=RuntimeError("service error"),
            ),
            patch.object(type(view), "app", new_callable=PropertyMock, return_value=mock_app),
        ):
            AnalyticsView._load_analytics.__wrapped__(view)

        # Should call update on all panels with error message
        assert mock_app.call_from_thread.call_count >= 1

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
