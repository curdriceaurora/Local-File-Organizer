"""Tests for file_organizer.cli.update module.

Tests the auto-update management CLI commands:
- check: Check for available updates
- install: Install the latest update
- rollback: Rollback to previous version
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from file_organizer.cli.update import update_app

runner = CliRunner()

pytestmark = [pytest.mark.unit]


class TestUpdateCheck:
    """Tests for update check command."""

    @patch("file_organizer.updater.UpdateManager")
    def test_check_update_available(self, mock_mgr_cls):
        """Test checking when update is available."""
        mock_mgr = MagicMock()
        mock_status = MagicMock()
        mock_status.current_version = "1.0.0"
        mock_status.latest_version = "1.1.0"
        mock_status.available = True
        mock_status.release = MagicMock()
        mock_status.release.html_url = "https://github.com/curdriceaurora/Local-File-Organizer/releases/tag/v1.1.0"
        mock_status.release.body = "Bug fixes and improvements"
        mock_mgr.check.return_value = mock_status
        mock_mgr_cls.return_value = mock_mgr

        result = runner.invoke(update_app, ["check"])

        assert result.exit_code == 0
        assert "1.0.0" in result.stdout
        assert "1.1.0" in result.stdout
        assert "Update available" in result.stdout

    @patch("file_organizer.updater.UpdateManager")
    def test_check_no_update_available(self, mock_mgr_cls):
        """Test checking when already up to date."""
        mock_mgr = MagicMock()
        mock_status = MagicMock()
        mock_status.current_version = "1.1.0"
        mock_status.available = False
        mock_mgr.check.return_value = mock_status
        mock_mgr_cls.return_value = mock_mgr

        result = runner.invoke(update_app, ["check"])

        assert result.exit_code == 0
        assert "Already up to date" in result.stdout

    @patch("file_organizer.updater.UpdateManager")
    def test_check_custom_repo(self, mock_mgr_cls):
        """Test checking with custom repository."""
        mock_mgr = MagicMock()
        mock_status = MagicMock()
        mock_status.current_version = "1.0.0"
        mock_status.available = False
        mock_mgr.check.return_value = mock_status
        mock_mgr_cls.return_value = mock_mgr

        result = runner.invoke(
            update_app, ["check", "--repo", "user/custom-repo"]
        )

        assert result.exit_code == 0
        mock_mgr_cls.assert_called_once_with(
            repo="user/custom-repo", include_prereleases=False
        )

    @patch("file_organizer.updater.UpdateManager")
    def test_check_include_prerelease(self, mock_mgr_cls):
        """Test checking with pre-release versions included."""
        mock_mgr = MagicMock()
        mock_status = MagicMock()
        mock_status.current_version = "1.0.0"
        mock_status.available = False
        mock_mgr.check.return_value = mock_status
        mock_mgr_cls.return_value = mock_mgr

        result = runner.invoke(update_app, ["check", "--pre"])

        assert result.exit_code == 0
        mock_mgr_cls.assert_called_once_with(
            repo="curdriceaurora/Local-File-Organizer", include_prereleases=True
        )

    @patch("file_organizer.updater.UpdateManager")
    def test_check_shows_release_notes(self, mock_mgr_cls):
        """Test check command displays release notes."""
        mock_mgr = MagicMock()
        mock_status = MagicMock()
        mock_status.current_version = "1.0.0"
        mock_status.latest_version = "1.1.0"
        mock_status.available = True
        mock_status.release = MagicMock()
        mock_status.release.html_url = "https://github.com/.../v1.1.0"
        mock_status.release.body = "Major improvements and bug fixes"
        mock_mgr.check.return_value = mock_status
        mock_mgr_cls.return_value = mock_mgr

        result = runner.invoke(update_app, ["check"])

        assert result.exit_code == 0
        assert "Major improvements" in result.stdout or "v1.1.0" in result.stdout


class TestUpdateInstall:
    """Tests for update install command."""

    @patch("file_organizer.updater.UpdateManager")
    def test_install_success(self, mock_mgr_cls):
        """Test successful update installation."""
        mock_mgr = MagicMock()
        mock_status = MagicMock()
        mock_status.available = True
        mock_status.install_result = MagicMock()
        mock_status.install_result.success = True
        mock_status.install_result.message = "Update installed successfully"
        mock_status.install_result.sha256 = "abcdef123456789"
        mock_mgr.update.return_value = mock_status
        mock_mgr_cls.return_value = mock_mgr

        result = runner.invoke(update_app, ["install"])

        assert result.exit_code == 0
        assert "Update installed successfully" in result.stdout

    @patch("file_organizer.updater.UpdateManager")
    def test_install_no_update_available(self, mock_mgr_cls):
        """Test install when no update is available."""
        mock_mgr = MagicMock()
        mock_status = MagicMock()
        mock_status.available = False
        mock_mgr.update.return_value = mock_status
        mock_mgr_cls.return_value = mock_mgr

        result = runner.invoke(update_app, ["install"])

        assert result.exit_code == 0
        assert "Already up to date" in result.stdout

    @patch("file_organizer.updater.UpdateManager")
    def test_install_failure(self, mock_mgr_cls):
        """Test handling installation failure."""
        mock_mgr = MagicMock()
        mock_status = MagicMock()
        mock_status.available = True
        mock_status.install_result = MagicMock()
        mock_status.install_result.success = False
        mock_status.install_result.message = "Installation failed"
        mock_mgr.update.return_value = mock_status
        mock_mgr_cls.return_value = mock_mgr

        result = runner.invoke(update_app, ["install"])

        assert result.exit_code == 1
        assert "Installation failed" in result.stdout

    @patch("file_organizer.updater.UpdateManager")
    def test_install_with_dry_run(self, mock_mgr_cls):
        """Test install with dry-run flag."""
        mock_mgr = MagicMock()
        mock_status = MagicMock()
        mock_status.available = True
        mock_status.install_result = MagicMock()
        mock_status.install_result.success = True
        mock_status.install_result.message = "Would install successfully"
        mock_mgr.update.return_value = mock_status
        mock_mgr_cls.return_value = mock_mgr

        result = runner.invoke(update_app, ["install", "--dry-run"])

        assert result.exit_code == 0
        mock_mgr.update.assert_called_once_with(dry_run=True)

    @patch("file_organizer.updater.UpdateManager")
    def test_install_shows_checksum(self, mock_mgr_cls):
        """Test install displays SHA256 checksum."""
        mock_mgr = MagicMock()
        mock_status = MagicMock()
        mock_status.available = True
        mock_status.install_result = MagicMock()
        mock_status.install_result.success = True
        mock_status.install_result.message = "Update installed"
        mock_status.install_result.sha256 = "abc123def456"
        mock_mgr.update.return_value = mock_status
        mock_mgr_cls.return_value = mock_mgr

        result = runner.invoke(update_app, ["install"])

        assert result.exit_code == 0
        assert "SHA256" in result.stdout or "abc123" in result.stdout

    @patch("file_organizer.updater.UpdateManager")
    def test_install_null_install_result(self, mock_mgr_cls):
        """Test handling when install result is None."""
        mock_mgr = MagicMock()
        mock_status = MagicMock()
        mock_status.available = True
        mock_status.install_result = None
        mock_mgr.update.return_value = mock_status
        mock_mgr_cls.return_value = mock_mgr

        result = runner.invoke(update_app, ["install"])

        assert result.exit_code == 1
        assert "failed" in result.stdout or "Error" in result.stdout

    @patch("file_organizer.updater.UpdateManager")
    def test_install_custom_repo(self, mock_mgr_cls):
        """Test install with custom repository."""
        mock_mgr = MagicMock()
        mock_status = MagicMock()
        mock_status.available = False
        mock_mgr.update.return_value = mock_status
        mock_mgr_cls.return_value = mock_mgr

        result = runner.invoke(
            update_app, ["install", "--repo", "user/repo"]
        )

        assert result.exit_code == 0
        mock_mgr_cls.assert_called_once_with(
            repo="user/repo", include_prereleases=False
        )


class TestUpdateRollback:
    """Tests for update rollback command."""

    @patch("file_organizer.updater.UpdateInstaller")
    def test_rollback_success(self, mock_installer_cls):
        """Test successful rollback."""
        mock_installer = MagicMock()
        mock_installer.rollback.return_value = True
        mock_installer_cls.return_value = mock_installer

        result = runner.invoke(update_app, ["rollback"])

        assert result.exit_code == 0
        assert "Rolled back" in result.stdout
        mock_installer.rollback.assert_called_once()

    @patch("file_organizer.updater.UpdateInstaller")
    def test_rollback_no_backup(self, mock_installer_cls):
        """Test rollback when no backup exists."""
        mock_installer = MagicMock()
        mock_installer.rollback.return_value = False
        mock_installer_cls.return_value = mock_installer

        result = runner.invoke(update_app, ["rollback"])

        assert result.exit_code == 1
        assert "No backup" in result.stdout

    @patch("file_organizer.updater.UpdateInstaller")
    def test_rollback_shows_message(self, mock_installer_cls):
        """Test rollback displays appropriate message."""
        mock_installer = MagicMock()
        mock_installer.rollback.return_value = True
        mock_installer_cls.return_value = mock_installer

        result = runner.invoke(update_app, ["rollback"])

        assert result.exit_code == 0
        assert "previous version" in result.stdout
