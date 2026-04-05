"""Integration tests for cli/analytics.py and cli/marketplace.py.

analytics_command uses argparse and calls AnalyticsService; all external
calls are mocked so no real filesystem traversal or network access occurs.

marketplace_app is a Typer sub-app; the underlying _service() factory is
patched so every command runs without a real MarketplaceService backend.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.ci]


# ---------------------------------------------------------------------------
# Helpers for building analytics model instances
# ---------------------------------------------------------------------------


def _make_storage_stats(**kw: Any) -> Any:
    from file_organizer.models.analytics import StorageStats

    defaults: dict[str, Any] = {
        "total_size": 1024 * 1024,
        "organized_size": 512 * 1024,
        "saved_size": 200 * 1024,
        "file_count": 42,
        "directory_count": 5,
        "largest_files": [],
        "size_by_type": {},
        "size_by_category": {},
    }
    return StorageStats(**{**defaults, **kw})


def _make_quality_metrics(**kw: Any) -> Any:
    from file_organizer.models.analytics import QualityMetrics

    defaults: dict[str, Any] = {
        "quality_score": 75.0,
        "naming_compliance": 0.8,
        "structure_consistency": 0.9,
        "metadata_completeness": 0.7,
        "categorization_accuracy": 0.85,
        "improvement_rate": 0.05,
    }
    return QualityMetrics(**{**defaults, **kw})


def _make_duplicate_stats(**kw: Any) -> Any:
    from file_organizer.models.analytics import DuplicateStats

    defaults: dict[str, Any] = {
        "total_duplicates": 3,
        "duplicate_groups": 1,
        "space_wasted": 50 * 1024,
        "space_recoverable": 40 * 1024,
        "by_type": {},
        "largest_duplicate_group": 2,
    }
    return DuplicateStats(**{**defaults, **kw})


def _make_time_savings(**kw: Any) -> Any:
    from file_organizer.models.analytics import TimeSavings

    defaults: dict[str, Any] = {
        "total_operations": 100,
        "automated_operations": 90,
        "manual_time_seconds": 300.0,
        "automated_time_seconds": 30.0,
        "estimated_time_saved_seconds": 270.0,
    }
    return TimeSavings(**{**defaults, **kw})


def _make_file_distribution(**kw: Any) -> Any:
    from file_organizer.models.analytics import FileDistribution

    defaults: dict[str, Any] = {
        "by_type": {"pdf": 10, "jpg": 5},
        "by_category": {"documents": 10, "images": 5},
        "by_size_range": {"small": 12, "medium": 3},
        "total_files": 15,
    }
    return FileDistribution(**{**defaults, **kw})


def _make_dashboard() -> Any:
    from file_organizer.models.analytics import AnalyticsDashboard

    return AnalyticsDashboard(
        storage_stats=_make_storage_stats(),
        file_distribution=_make_file_distribution(),
        duplicate_stats=_make_duplicate_stats(),
        quality_metrics=_make_quality_metrics(),
        time_savings=_make_time_savings(),
        trends=[],
        generated_at=datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC),
    )


# ---------------------------------------------------------------------------
# _format_bytes
# ---------------------------------------------------------------------------


class TestFormatBytes:
    def test_bytes(self) -> None:
        from file_organizer.cli.analytics import _format_bytes

        assert _format_bytes(512) == "512.0 B"

    def test_kilobytes(self) -> None:
        from file_organizer.cli.analytics import _format_bytes

        assert _format_bytes(1024) == "1.0 KB"

    def test_megabytes(self) -> None:
        from file_organizer.cli.analytics import _format_bytes

        assert _format_bytes(1024 * 1024) == "1.0 MB"

    def test_gigabytes(self) -> None:
        from file_organizer.cli.analytics import _format_bytes

        assert _format_bytes(1024**3) == "1.0 GB"

    def test_terabytes(self) -> None:
        from file_organizer.cli.analytics import _format_bytes

        assert _format_bytes(1024**4) == "1.0 TB"

    def test_zero(self) -> None:
        from file_organizer.cli.analytics import _format_bytes

        assert _format_bytes(0) == "0.0 B"


# ---------------------------------------------------------------------------
# _format_duration
# ---------------------------------------------------------------------------


class TestFormatDuration:
    def test_seconds(self) -> None:
        from file_organizer.cli.analytics import _format_duration

        assert _format_duration(30.0) == "30.0s"

    def test_minutes(self) -> None:
        from file_organizer.cli.analytics import _format_duration

        assert _format_duration(90.0) == "1.5m"

    def test_hours(self) -> None:
        from file_organizer.cli.analytics import _format_duration

        assert _format_duration(7200.0) == "2.0h"

    def test_boundary_60s(self) -> None:
        from file_organizer.cli.analytics import _format_duration

        # exactly 60s → 1.0m
        assert _format_duration(60.0) == "1.0m"


# ---------------------------------------------------------------------------
# display_* helpers (smoke tests — just verify they don't raise)
# ---------------------------------------------------------------------------


class TestDisplayHelpers:
    def test_display_storage_stats_no_chart(self) -> None:
        from file_organizer.cli.analytics import display_storage_stats

        display_storage_stats(_make_storage_stats(), chart_gen=None)

    def test_display_storage_stats_with_size_by_type(self) -> None:
        from file_organizer.cli.analytics import display_storage_stats

        chart_gen = MagicMock()
        chart_gen.create_pie_chart.return_value = "pie"
        stats = _make_storage_stats(size_by_type={"pdf": 500, "jpg": 300})
        display_storage_stats(stats, chart_gen=chart_gen)
        chart_gen.create_pie_chart.assert_called_once()

    def test_display_quality_metrics(self) -> None:
        from file_organizer.cli.analytics import display_quality_metrics

        display_quality_metrics(_make_quality_metrics())

    def test_display_quality_metrics_low_score(self) -> None:
        from file_organizer.cli.analytics import display_quality_metrics

        display_quality_metrics(_make_quality_metrics(quality_score=30.0))

    def test_display_duplicate_stats(self) -> None:
        from file_organizer.cli.analytics import display_duplicate_stats

        display_duplicate_stats(_make_duplicate_stats())

    def test_display_time_savings(self) -> None:
        from file_organizer.cli.analytics import display_time_savings

        display_time_savings(_make_time_savings())

    def test_display_file_distribution_no_chart(self) -> None:
        from file_organizer.cli.analytics import display_file_distribution

        display_file_distribution(_make_file_distribution(), chart_gen=None)

    def test_display_file_distribution_with_chart(self) -> None:
        from file_organizer.cli.analytics import display_file_distribution

        chart_gen = MagicMock()
        chart_gen.create_bar_chart.return_value = "bar"
        display_file_distribution(_make_file_distribution(), chart_gen=chart_gen)


# ---------------------------------------------------------------------------
# analytics_command
# ---------------------------------------------------------------------------


class TestAnalyticsCommand:
    def _mock_service(self) -> MagicMock:
        svc = MagicMock()
        svc.generate_dashboard.return_value = _make_dashboard()
        return svc

    def test_returns_0_on_success(self, tmp_path: Path) -> None:
        from file_organizer.cli.analytics import analytics_command

        with (
            patch(
                "file_organizer.cli.analytics.AnalyticsService", return_value=self._mock_service()
            ),
            patch("file_organizer.cli.analytics.ChartGenerator"),
        ):
            code = analytics_command([str(tmp_path)])
        assert code == 0

    def test_returns_1_for_missing_directory(self, tmp_path: Path) -> None:
        from file_organizer.cli.analytics import analytics_command

        code = analytics_command([str(tmp_path / "nonexistent")])
        assert code == 1

    def test_returns_1_for_file_path(self, tmp_path: Path) -> None:
        from file_organizer.cli.analytics import analytics_command

        f = tmp_path / "file.txt"
        f.write_text("x")
        code = analytics_command([str(f)])
        assert code == 1

    def test_no_charts_flag(self, tmp_path: Path) -> None:
        from file_organizer.cli.analytics import analytics_command

        with patch(
            "file_organizer.cli.analytics.AnalyticsService", return_value=self._mock_service()
        ):
            code = analytics_command([str(tmp_path), "--no-charts"])
        assert code == 0

    def test_export_json(self, tmp_path: Path) -> None:
        from file_organizer.cli.analytics import analytics_command

        export_path = tmp_path / "report.json"
        with (
            patch(
                "file_organizer.cli.analytics.AnalyticsService", return_value=self._mock_service()
            ),
            patch("file_organizer.cli.analytics.ChartGenerator"),
        ):
            code = analytics_command([str(tmp_path), "--export", str(export_path)])
        assert code == 0

    def test_export_text_format(self, tmp_path: Path) -> None:
        from file_organizer.cli.analytics import analytics_command

        export_path = tmp_path / "report.txt"
        with (
            patch(
                "file_organizer.cli.analytics.AnalyticsService", return_value=self._mock_service()
            ),
            patch("file_organizer.cli.analytics.ChartGenerator"),
        ):
            code = analytics_command(
                [str(tmp_path), "--export", str(export_path), "--format", "text"]
            )
        assert code == 0

    def test_service_exception_returns_1(self, tmp_path: Path) -> None:
        from file_organizer.cli.analytics import analytics_command

        bad_svc = MagicMock()
        bad_svc.generate_dashboard.side_effect = RuntimeError("disk error")
        with patch("file_organizer.cli.analytics.AnalyticsService", return_value=bad_svc):
            code = analytics_command([str(tmp_path)])
        assert code == 1

    def test_max_depth_argument(self, tmp_path: Path) -> None:
        from file_organizer.cli.analytics import analytics_command

        svc = self._mock_service()
        with (
            patch("file_organizer.cli.analytics.AnalyticsService", return_value=svc),
            patch("file_organizer.cli.analytics.ChartGenerator"),
        ):
            code = analytics_command([str(tmp_path), "--max-depth", "3"])
        assert code == 0
        svc.generate_dashboard.assert_called_once_with(directory=tmp_path, max_depth=3)


# ---------------------------------------------------------------------------
# marketplace_app via Typer CliRunner
# ---------------------------------------------------------------------------


def _make_plugin(**kw: Any) -> MagicMock:
    p = MagicMock()
    p.name = kw.get("name", "cool-plugin")
    p.version = kw.get("version", "1.0.0")
    p.author = kw.get("author", "Alice")
    p.category = kw.get("category", "utility")
    p.rating = kw.get("rating", 4.5)
    p.downloads = kw.get("downloads", 1000)
    p.description = kw.get("description", "A cool plugin")
    p.tags = kw.get("tags", ["tag1"])
    p.dependencies = kw.get("dependencies", [])
    p.reviews_count = kw.get("reviews_count", 10)
    p.homepage = kw.get("homepage", "https://example.com")
    return p


class TestMarketplaceListCommand:
    def test_list_shows_plugins(self) -> None:
        from typer.testing import CliRunner

        from file_organizer.cli.marketplace import marketplace_app

        plugin = _make_plugin()
        mock_svc = MagicMock()
        mock_svc.list_plugins.return_value = ([plugin], 1)

        with patch("file_organizer.cli.marketplace._service", return_value=mock_svc):
            result = CliRunner().invoke(marketplace_app, ["list"])

        assert result.exit_code == 0
        assert "cool-plugin" in result.output

    def test_list_shows_count(self) -> None:
        from typer.testing import CliRunner

        from file_organizer.cli.marketplace import marketplace_app

        mock_svc = MagicMock()
        mock_svc.list_plugins.return_value = ([_make_plugin()], 5)

        with patch("file_organizer.cli.marketplace._service", return_value=mock_svc):
            result = CliRunner().invoke(marketplace_app, ["list"])

        assert "1 of 5" in result.output

    def test_list_marketplace_error(self) -> None:
        from typer.testing import CliRunner

        from file_organizer.cli.marketplace import marketplace_app
        from file_organizer.plugins.marketplace import MarketplaceError

        mock_svc = MagicMock()
        mock_svc.list_plugins.side_effect = MarketplaceError("network down")

        with patch("file_organizer.cli.marketplace._service", return_value=mock_svc):
            result = CliRunner().invoke(marketplace_app, ["list"])

        assert result.exit_code == 1
        assert "network down" in result.output


class TestMarketplaceSearchCommand:
    def test_search_returns_results(self) -> None:
        from typer.testing import CliRunner

        from file_organizer.cli.marketplace import marketplace_app

        mock_svc = MagicMock()
        mock_svc.list_plugins.return_value = ([_make_plugin(name="found-plugin")], 1)

        with patch("file_organizer.cli.marketplace._service", return_value=mock_svc):
            result = CliRunner().invoke(marketplace_app, ["search", "found"])

        assert result.exit_code == 0
        assert "found-plugin" in result.output

    def test_search_marketplace_error(self) -> None:
        from typer.testing import CliRunner

        from file_organizer.cli.marketplace import marketplace_app
        from file_organizer.plugins.marketplace import MarketplaceError

        mock_svc = MagicMock()
        mock_svc.list_plugins.side_effect = MarketplaceError("timeout")

        with patch("file_organizer.cli.marketplace._service", return_value=mock_svc):
            result = CliRunner().invoke(marketplace_app, ["search", "anything"])

        assert result.exit_code == 1


class TestMarketplaceInfoCommand:
    def test_info_shows_details(self) -> None:
        from typer.testing import CliRunner

        from file_organizer.cli.marketplace import marketplace_app

        plugin = _make_plugin(name="my-plugin", version="2.0.0")
        mock_svc = MagicMock()
        mock_svc.get_plugin.return_value = plugin
        mock_svc.get_average_rating.return_value = 4.2

        with patch("file_organizer.cli.marketplace._service", return_value=mock_svc):
            result = CliRunner().invoke(marketplace_app, ["info", "my-plugin"])

        assert result.exit_code == 0
        assert "my-plugin" in result.output
        assert "2.0.0" in result.output

    def test_info_marketplace_error(self) -> None:
        from typer.testing import CliRunner

        from file_organizer.cli.marketplace import marketplace_app
        from file_organizer.plugins.marketplace import MarketplaceError

        mock_svc = MagicMock()
        mock_svc.get_plugin.side_effect = MarketplaceError("not found")

        with patch("file_organizer.cli.marketplace._service", return_value=mock_svc):
            result = CliRunner().invoke(marketplace_app, ["info", "ghost"])

        assert result.exit_code == 1
        assert "not found" in result.output


class TestMarketplaceInstallCommand:
    def test_install_success(self) -> None:
        from typer.testing import CliRunner

        from file_organizer.cli.marketplace import marketplace_app

        installed = _make_plugin(name="new-plugin", version="1.0.0")
        mock_svc = MagicMock()
        mock_svc.install.return_value = installed

        with patch("file_organizer.cli.marketplace._service", return_value=mock_svc):
            result = CliRunner().invoke(marketplace_app, ["install", "new-plugin"])

        assert result.exit_code == 0
        assert "new-plugin" in result.output
        assert "Installed" in result.output

    def test_install_marketplace_error(self) -> None:
        from typer.testing import CliRunner

        from file_organizer.cli.marketplace import marketplace_app
        from file_organizer.plugins.marketplace import MarketplaceError

        mock_svc = MagicMock()
        mock_svc.install.side_effect = MarketplaceError("incompatible")

        with patch("file_organizer.cli.marketplace._service", return_value=mock_svc):
            result = CliRunner().invoke(marketplace_app, ["install", "bad-plugin"])

        assert result.exit_code == 1


class TestMarketplaceUninstallCommand:
    def test_uninstall_success(self) -> None:
        from typer.testing import CliRunner

        from file_organizer.cli.marketplace import marketplace_app

        mock_svc = MagicMock()
        mock_svc.uninstall.return_value = None

        with patch("file_organizer.cli.marketplace._service", return_value=mock_svc):
            result = CliRunner().invoke(marketplace_app, ["uninstall", "old-plugin"])

        assert result.exit_code == 0
        assert "Uninstalled" in result.output

    def test_uninstall_error(self) -> None:
        from typer.testing import CliRunner

        from file_organizer.cli.marketplace import marketplace_app
        from file_organizer.plugins.marketplace import MarketplaceError

        mock_svc = MagicMock()
        mock_svc.uninstall.side_effect = MarketplaceError("not installed")

        with patch("file_organizer.cli.marketplace._service", return_value=mock_svc):
            result = CliRunner().invoke(marketplace_app, ["uninstall", "ghost"])

        assert result.exit_code == 1


class TestMarketplaceUpdateCommand:
    def test_update_success(self) -> None:
        from typer.testing import CliRunner

        from file_organizer.cli.marketplace import marketplace_app

        updated = _make_plugin(name="my-plugin", version="2.0.1")
        mock_svc = MagicMock()
        mock_svc.update.return_value = updated

        with patch("file_organizer.cli.marketplace._service", return_value=mock_svc):
            result = CliRunner().invoke(marketplace_app, ["update", "my-plugin"])

        assert result.exit_code == 0
        assert "Updated" in result.output
        assert "2.0.1" in result.output

    def test_update_already_current(self) -> None:
        from typer.testing import CliRunner

        from file_organizer.cli.marketplace import marketplace_app

        mock_svc = MagicMock()
        mock_svc.update.return_value = None  # already up to date

        with patch("file_organizer.cli.marketplace._service", return_value=mock_svc):
            result = CliRunner().invoke(marketplace_app, ["update", "my-plugin"])

        assert result.exit_code == 0
        assert "up to date" in result.output

    def test_update_error(self) -> None:
        from typer.testing import CliRunner

        from file_organizer.cli.marketplace import marketplace_app
        from file_organizer.plugins.marketplace import MarketplaceError

        mock_svc = MagicMock()
        mock_svc.update.side_effect = MarketplaceError("registry down")

        with patch("file_organizer.cli.marketplace._service", return_value=mock_svc):
            result = CliRunner().invoke(marketplace_app, ["update", "my-plugin"])

        assert result.exit_code == 1


class TestMarketplaceInstalledCommand:
    def test_lists_installed(self) -> None:
        from typer.testing import CliRunner

        from file_organizer.cli.marketplace import marketplace_app

        item = MagicMock()
        item.name = "installed-plugin"
        item.version = "1.0.0"
        item.installed_at = "2026-01-01"
        mock_svc = MagicMock()
        mock_svc.list_installed.return_value = [item]

        with patch("file_organizer.cli.marketplace._service", return_value=mock_svc):
            result = CliRunner().invoke(marketplace_app, ["installed"])

        assert result.exit_code == 0
        assert "installed-plugin" in result.output

    def test_installed_error(self) -> None:
        from typer.testing import CliRunner

        from file_organizer.cli.marketplace import marketplace_app
        from file_organizer.plugins.marketplace import MarketplaceError

        mock_svc = MagicMock()
        mock_svc.list_installed.side_effect = MarketplaceError("cache corrupt")

        with patch("file_organizer.cli.marketplace._service", return_value=mock_svc):
            result = CliRunner().invoke(marketplace_app, ["installed"])

        assert result.exit_code == 1


class TestMarketplaceUpdatesCommand:
    def test_shows_updates_available(self) -> None:
        from typer.testing import CliRunner

        from file_organizer.cli.marketplace import marketplace_app

        mock_svc = MagicMock()
        mock_svc.check_updates.return_value = ["plugin-a 1.1.0", "plugin-b 2.0.0"]

        with patch("file_organizer.cli.marketplace._service", return_value=mock_svc):
            result = CliRunner().invoke(marketplace_app, ["updates"])

        assert result.exit_code == 0
        assert "plugin-a" in result.output

    def test_shows_all_up_to_date(self) -> None:
        from typer.testing import CliRunner

        from file_organizer.cli.marketplace import marketplace_app

        mock_svc = MagicMock()
        mock_svc.check_updates.return_value = []

        with patch("file_organizer.cli.marketplace._service", return_value=mock_svc):
            result = CliRunner().invoke(marketplace_app, ["updates"])

        assert result.exit_code == 0
        assert "up to date" in result.output

    def test_updates_error(self) -> None:
        from typer.testing import CliRunner

        from file_organizer.cli.marketplace import marketplace_app
        from file_organizer.plugins.marketplace import MarketplaceError

        mock_svc = MagicMock()
        mock_svc.check_updates.side_effect = MarketplaceError("network error")

        with patch("file_organizer.cli.marketplace._service", return_value=mock_svc):
            result = CliRunner().invoke(marketplace_app, ["updates"])

        assert result.exit_code == 1


class TestMarketplaceReviewCommand:
    def test_add_review_success(self) -> None:
        from typer.testing import CliRunner

        from file_organizer.cli.marketplace import marketplace_app

        mock_svc = MagicMock()
        mock_svc.add_review.return_value = None

        with patch("file_organizer.cli.marketplace._service", return_value=mock_svc):
            result = CliRunner().invoke(
                marketplace_app,
                [
                    "review",
                    "cool-plugin",
                    "--user",
                    "user123",
                    "--rating",
                    "5",
                    "--title",
                    "Great plugin",
                    "--content",
                    "Works well",
                ],
            )

        assert result.exit_code == 0
        assert "cool-plugin" in result.output

    def test_add_review_error(self) -> None:
        from typer.testing import CliRunner

        from file_organizer.cli.marketplace import marketplace_app
        from file_organizer.plugins.marketplace import MarketplaceError

        mock_svc = MagicMock()
        mock_svc.add_review.side_effect = MarketplaceError("plugin not found")

        with patch("file_organizer.cli.marketplace._service", return_value=mock_svc):
            result = CliRunner().invoke(
                marketplace_app,
                [
                    "review",
                    "ghost",
                    "--user",
                    "user123",
                    "--rating",
                    "3",
                    "--title",
                    "Meh",
                    "--content",
                    "Doesn't work",
                ],
            )

        assert result.exit_code == 1
