"""Tests for file_organizer.cli.marketplace module.

Tests the Typer-based marketplace CLI commands including:
- list, search, info, install, uninstall, update
- installed, updates, review
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from file_organizer.cli.marketplace import marketplace_app
from file_organizer.plugins.marketplace import MarketplaceError

pytestmark = [pytest.mark.unit]


@pytest.fixture
def runner():
    """Create a Typer CLI test runner."""
    return CliRunner()


@pytest.fixture
def sample_plugin():
    """Create a mock PluginPackage."""
    pkg = MagicMock()
    pkg.name = "file-sorter"
    pkg.version = "1.2.0"
    pkg.author = "Test Author"
    pkg.description = "Sorts files automatically"
    pkg.category = "organization"
    pkg.rating = 4.5
    pkg.downloads = 1200
    pkg.tags = ["sort", "organize"]
    pkg.dependencies = ["numpy"]
    pkg.reviews_count = 25
    pkg.homepage = "https://example.com"
    return pkg


@pytest.fixture
def mock_service(sample_plugin):
    """Create a mock MarketplaceService."""
    svc = MagicMock()
    svc.list_plugins.return_value = ([sample_plugin], 1)
    svc.get_plugin.return_value = sample_plugin
    svc.get_average_rating.return_value = 4.3
    return svc


# ============================================================================
# List Tests
# ============================================================================


@pytest.mark.unit
class TestListPlugins:
    """Tests for the 'list' subcommand."""

    def test_list_plugins(self, runner, mock_service):
        with patch("file_organizer.cli.marketplace._service", return_value=mock_service):
            result = runner.invoke(marketplace_app, ["list"])
        assert result.exit_code == 0
        assert "file-sorter" in result.output

    def test_list_plugins_with_pagination(self, runner, mock_service):
        with patch("file_organizer.cli.marketplace._service", return_value=mock_service):
            result = runner.invoke(marketplace_app, ["list", "--page", "2", "--per-page", "10"])
        assert result.exit_code == 0
        mock_service.list_plugins.assert_called_once_with(
            page=2, per_page=10, category=None, tags=None
        )

    def test_list_plugins_with_category(self, runner, mock_service):
        with patch("file_organizer.cli.marketplace._service", return_value=mock_service):
            result = runner.invoke(marketplace_app, ["list", "--category", "utilities"])
        assert result.exit_code == 0
        mock_service.list_plugins.assert_called_once_with(
            page=1, per_page=20, category="utilities", tags=None
        )

    def test_list_plugins_with_tags(self, runner, mock_service):
        with patch("file_organizer.cli.marketplace._service", return_value=mock_service):
            result = runner.invoke(marketplace_app, ["list", "--tag", "sort", "--tag", "files"])
        assert result.exit_code == 0

    def test_list_plugins_marketplace_error(self, runner):
        mock_svc = MagicMock()
        mock_svc.list_plugins.side_effect = MarketplaceError("Connection failed")
        with patch("file_organizer.cli.marketplace._service", return_value=mock_svc):
            result = runner.invoke(marketplace_app, ["list"])
        assert result.exit_code == 1
        assert "Marketplace error" in result.output

    def test_list_shows_total(self, runner, mock_service):
        with patch("file_organizer.cli.marketplace._service", return_value=mock_service):
            result = runner.invoke(marketplace_app, ["list"])
        assert "1 of 1" in result.output


# ============================================================================
# Search Tests
# ============================================================================


@pytest.mark.unit
class TestSearchPlugins:
    """Tests for the 'search' subcommand."""

    def test_search_plugins(self, runner, mock_service):
        with patch("file_organizer.cli.marketplace._service", return_value=mock_service):
            result = runner.invoke(marketplace_app, ["search", "sorter"])
        assert result.exit_code == 0
        assert "file-sorter" in result.output

    def test_search_with_category(self, runner, mock_service):
        with patch("file_organizer.cli.marketplace._service", return_value=mock_service):
            result = runner.invoke(
                marketplace_app, ["search", "sort", "--category", "organization"]
            )
        assert result.exit_code == 0

    def test_search_marketplace_error(self, runner):
        mock_svc = MagicMock()
        mock_svc.list_plugins.side_effect = MarketplaceError("timeout")
        with patch("file_organizer.cli.marketplace._service", return_value=mock_svc):
            result = runner.invoke(marketplace_app, ["search", "test"])
        assert result.exit_code == 1

    def test_search_shows_found_count(self, runner, mock_service):
        with patch("file_organizer.cli.marketplace._service", return_value=mock_service):
            result = runner.invoke(marketplace_app, ["search", "sort"])
        assert "Found 1" in result.output


# ============================================================================
# Info Tests
# ============================================================================


@pytest.mark.unit
class TestPluginInfo:
    """Tests for the 'info' subcommand."""

    def test_info_success(self, runner, mock_service):
        with patch("file_organizer.cli.marketplace._service", return_value=mock_service):
            result = runner.invoke(marketplace_app, ["info", "file-sorter"])
        assert result.exit_code == 0
        assert "file-sorter" in result.output
        assert "1.2.0" in result.output
        assert "Test Author" in result.output
        assert "sort" in result.output
        assert "numpy" in result.output

    def test_info_with_version(self, runner, mock_service):
        with patch("file_organizer.cli.marketplace._service", return_value=mock_service):
            result = runner.invoke(
                marketplace_app, ["info", "file-sorter", "--version", "1.0.0"]
            )
        assert result.exit_code == 0
        mock_service.get_plugin.assert_called_once_with("file-sorter", version="1.0.0")

    def test_info_marketplace_error(self, runner):
        mock_svc = MagicMock()
        mock_svc.get_plugin.side_effect = MarketplaceError("Not found")
        with patch("file_organizer.cli.marketplace._service", return_value=mock_svc):
            result = runner.invoke(marketplace_app, ["info", "nonexistent"])
        assert result.exit_code == 1
        assert "Marketplace error" in result.output

    def test_info_no_tags_or_deps(self, runner):
        mock_svc = MagicMock()
        pkg = MagicMock()
        pkg.name = "minimal"
        pkg.version = "0.1.0"
        pkg.author = "Author"
        pkg.description = "Minimal plugin"
        pkg.category = "misc"
        pkg.tags = []
        pkg.dependencies = []
        pkg.rating = 3.0
        pkg.reviews_count = 0
        pkg.downloads = 0
        pkg.homepage = None
        mock_svc.get_plugin.return_value = pkg
        mock_svc.get_average_rating.return_value = 0.0
        with patch("file_organizer.cli.marketplace._service", return_value=mock_svc):
            result = runner.invoke(marketplace_app, ["info", "minimal"])
        assert result.exit_code == 0
        assert "-" in result.output  # placeholder for empty tags/deps/homepage


# ============================================================================
# Install Tests
# ============================================================================


@pytest.mark.unit
class TestInstallPlugin:
    """Tests for the 'install' subcommand."""

    def test_install_success(self, runner):
        mock_svc = MagicMock()
        installed = MagicMock()
        installed.name = "file-sorter"
        installed.version = "1.2.0"
        mock_svc.install.return_value = installed
        with patch("file_organizer.cli.marketplace._service", return_value=mock_svc):
            result = runner.invoke(marketplace_app, ["install", "file-sorter"])
        assert result.exit_code == 0
        assert "Installed" in result.output
        assert "file-sorter" in result.output

    def test_install_specific_version(self, runner):
        mock_svc = MagicMock()
        installed = MagicMock()
        installed.name = "file-sorter"
        installed.version = "1.0.0"
        mock_svc.install.return_value = installed
        with patch("file_organizer.cli.marketplace._service", return_value=mock_svc):
            result = runner.invoke(
                marketplace_app, ["install", "file-sorter", "--version", "1.0.0"]
            )
        assert result.exit_code == 0
        mock_svc.install.assert_called_once_with("file-sorter", version="1.0.0")

    def test_install_marketplace_error(self, runner):
        mock_svc = MagicMock()
        mock_svc.install.side_effect = MarketplaceError("Download failed")
        with patch("file_organizer.cli.marketplace._service", return_value=mock_svc):
            result = runner.invoke(marketplace_app, ["install", "bad-plugin"])
        assert result.exit_code == 1
        assert "Marketplace error" in result.output


# ============================================================================
# Uninstall Tests
# ============================================================================


@pytest.mark.unit
class TestUninstallPlugin:
    """Tests for the 'uninstall' subcommand."""

    def test_uninstall_success(self, runner):
        mock_svc = MagicMock()
        with patch("file_organizer.cli.marketplace._service", return_value=mock_svc):
            result = runner.invoke(marketplace_app, ["uninstall", "file-sorter"])
        assert result.exit_code == 0
        assert "Uninstalled" in result.output
        mock_svc.uninstall.assert_called_once_with("file-sorter")

    def test_uninstall_marketplace_error(self, runner):
        mock_svc = MagicMock()
        mock_svc.uninstall.side_effect = MarketplaceError("Not installed")
        with patch("file_organizer.cli.marketplace._service", return_value=mock_svc):
            result = runner.invoke(marketplace_app, ["uninstall", "missing"])
        assert result.exit_code == 1


# ============================================================================
# Update Tests
# ============================================================================


@pytest.mark.unit
class TestUpdatePlugin:
    """Tests for the 'update' subcommand."""

    def test_update_success(self, runner):
        mock_svc = MagicMock()
        updated = MagicMock()
        updated.name = "file-sorter"
        updated.version = "2.0.0"
        mock_svc.update.return_value = updated
        with patch("file_organizer.cli.marketplace._service", return_value=mock_svc):
            result = runner.invoke(marketplace_app, ["update", "file-sorter"])
        assert result.exit_code == 0
        assert "Updated" in result.output
        assert "2.0.0" in result.output

    def test_update_already_latest(self, runner):
        mock_svc = MagicMock()
        mock_svc.update.return_value = None
        with patch("file_organizer.cli.marketplace._service", return_value=mock_svc):
            result = runner.invoke(marketplace_app, ["update", "file-sorter"])
        assert result.exit_code == 0
        assert "up to date" in result.output

    def test_update_marketplace_error(self, runner):
        mock_svc = MagicMock()
        mock_svc.update.side_effect = MarketplaceError("Update failed")
        with patch("file_organizer.cli.marketplace._service", return_value=mock_svc):
            result = runner.invoke(marketplace_app, ["update", "bad-plugin"])
        assert result.exit_code == 1


# ============================================================================
# Installed Tests
# ============================================================================


@pytest.mark.unit
class TestListInstalled:
    """Tests for the 'installed' subcommand."""

    def test_list_installed(self, runner):
        mock_svc = MagicMock()
        item = MagicMock()
        item.name = "file-sorter"
        item.version = "1.2.0"
        item.installed_at = "2024-01-15"
        mock_svc.list_installed.return_value = [item]
        with patch("file_organizer.cli.marketplace._service", return_value=mock_svc):
            result = runner.invoke(marketplace_app, ["installed"])
        assert result.exit_code == 0
        assert "file-sorter" in result.output
        assert "Total installed: 1" in result.output

    def test_list_installed_empty(self, runner):
        mock_svc = MagicMock()
        mock_svc.list_installed.return_value = []
        with patch("file_organizer.cli.marketplace._service", return_value=mock_svc):
            result = runner.invoke(marketplace_app, ["installed"])
        assert result.exit_code == 0
        assert "Total installed: 0" in result.output

    def test_list_installed_marketplace_error(self, runner):
        mock_svc = MagicMock()
        mock_svc.list_installed.side_effect = MarketplaceError("DB error")
        with patch("file_organizer.cli.marketplace._service", return_value=mock_svc):
            result = runner.invoke(marketplace_app, ["installed"])
        assert result.exit_code == 1


# ============================================================================
# Updates Tests
# ============================================================================


@pytest.mark.unit
class TestAvailableUpdates:
    """Tests for the 'updates' subcommand."""

    def test_no_updates(self, runner):
        mock_svc = MagicMock()
        mock_svc.check_updates.return_value = []
        with patch("file_organizer.cli.marketplace._service", return_value=mock_svc):
            result = runner.invoke(marketplace_app, ["updates"])
        assert result.exit_code == 0
        assert "up to date" in result.output

    def test_updates_available(self, runner):
        mock_svc = MagicMock()
        mock_svc.check_updates.return_value = ["file-sorter", "image-viewer"]
        with patch("file_organizer.cli.marketplace._service", return_value=mock_svc):
            result = runner.invoke(marketplace_app, ["updates"])
        assert result.exit_code == 0
        assert "Updates available" in result.output
        assert "file-sorter" in result.output
        assert "image-viewer" in result.output

    def test_updates_marketplace_error(self, runner):
        mock_svc = MagicMock()
        mock_svc.check_updates.side_effect = MarketplaceError("Network error")
        with patch("file_organizer.cli.marketplace._service", return_value=mock_svc):
            result = runner.invoke(marketplace_app, ["updates"])
        assert result.exit_code == 1


# ============================================================================
# Review Tests
# ============================================================================


@pytest.mark.unit
class TestAddReview:
    """Tests for the 'review' subcommand."""

    def test_add_review_success(self, runner):
        mock_svc = MagicMock()
        with patch("file_organizer.cli.marketplace._service", return_value=mock_svc):
            result = runner.invoke(
                marketplace_app,
                [
                    "review",
                    "file-sorter",
                    "--user",
                    "user123",
                    "--rating",
                    "5",
                    "--title",
                    "Great plugin",
                    "--content",
                    "Works perfectly",
                ],
            )
        assert result.exit_code == 0
        assert "Saved review" in result.output
        mock_svc.add_review.assert_called_once()

    def test_add_review_marketplace_error(self, runner):
        mock_svc = MagicMock()
        mock_svc.add_review.side_effect = MarketplaceError("Review failed")
        with patch("file_organizer.cli.marketplace._service", return_value=mock_svc):
            result = runner.invoke(
                marketplace_app,
                [
                    "review",
                    "file-sorter",
                    "--user",
                    "user123",
                    "--rating",
                    "3",
                    "--title",
                    "OK",
                    "--content",
                    "Average",
                ],
            )
        assert result.exit_code == 1
        assert "Marketplace error" in result.output

    def test_review_missing_required_args(self, runner):
        """Missing --user, --rating, --title, --content should fail."""
        mock_svc = MagicMock()
        with patch("file_organizer.cli.marketplace._service", return_value=mock_svc):
            result = runner.invoke(marketplace_app, ["review", "file-sorter"])
        assert result.exit_code != 0
