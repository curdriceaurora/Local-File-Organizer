"""Tests for the update CLI sub-app (update.py).

Tests ``update check``, ``update install``, and ``update rollback`` commands.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from file_organizer.cli.main import app

pytestmark = [pytest.mark.unit]

runner = CliRunner()


def _make_status(
    available: bool = False,
    current_version: str = "2.0.0",
    latest_version: str = "2.1.0",
    release: MagicMock | None = None,
    install_result: MagicMock | None = None,
) -> MagicMock:
    """Create a mock update status."""
    status = MagicMock()
    status.available = available
    status.current_version = current_version
    status.latest_version = latest_version
    status.release = release
    status.install_result = install_result
    return status


def _make_release(
    html_url: str = "https://github.com/example/repo/releases/v2.1.0",
    body: str = "Bug fixes and improvements",
) -> MagicMock:
    """Create a mock release object."""
    release = MagicMock()
    release.html_url = html_url
    release.body = body
    return release


def _make_install_result(
    success: bool = True,
    message: str = "Updated successfully",
    sha256: str = "abc123def456",
) -> MagicMock:
    """Create a mock install result."""
    result = MagicMock()
    result.success = success
    result.message = message
    result.sha256 = sha256
    return result


# ---------------------------------------------------------------------------
# update check
# ---------------------------------------------------------------------------


class TestUpdateCheck:
    """Tests for ``update check``."""

    @patch("file_organizer.updater.UpdateManager")
    def test_check_up_to_date(self, mock_cls: MagicMock) -> None:
        mock_mgr = MagicMock()
        mock_cls.return_value = mock_mgr
        mock_mgr.check.return_value = _make_status(available=False)

        result = runner.invoke(app, ["update", "check"])
        assert result.exit_code == 0
        assert "up to date" in result.output.lower()

    @patch("file_organizer.updater.UpdateManager")
    def test_check_update_available(self, mock_cls: MagicMock) -> None:
        mock_mgr = MagicMock()
        mock_cls.return_value = mock_mgr
        release = _make_release()
        mock_mgr.check.return_value = _make_status(available=True, release=release)

        result = runner.invoke(app, ["update", "check"])
        assert result.exit_code == 0
        assert "Update available" in result.output or "available" in result.output.lower()

    @patch("file_organizer.updater.UpdateManager")
    def test_check_with_repo_option(self, mock_cls: MagicMock) -> None:
        mock_mgr = MagicMock()
        mock_cls.return_value = mock_mgr
        mock_mgr.check.return_value = _make_status(available=False)

        result = runner.invoke(
            app,
            ["update", "check", "--repo", "myorg/myrepo"],
        )
        assert result.exit_code == 0
        mock_cls.assert_called_once_with(repo="myorg/myrepo", include_prereleases=False)

    @patch("file_organizer.updater.UpdateManager")
    def test_check_with_prerelease(self, mock_cls: MagicMock) -> None:
        mock_mgr = MagicMock()
        mock_cls.return_value = mock_mgr
        mock_mgr.check.return_value = _make_status(available=False)

        result = runner.invoke(app, ["update", "check", "--pre"])
        assert result.exit_code == 0
        mock_cls.assert_called_once_with(
            repo="curdriceaurora/Local-File-Organizer",
            include_prereleases=True,
        )


# ---------------------------------------------------------------------------
# update install
# ---------------------------------------------------------------------------


class TestUpdateInstall:
    """Tests for ``update install``."""

    @patch("file_organizer.updater.UpdateManager")
    def test_install_up_to_date(self, mock_cls: MagicMock) -> None:
        mock_mgr = MagicMock()
        mock_cls.return_value = mock_mgr
        mock_mgr.update.return_value = _make_status(available=False)

        result = runner.invoke(app, ["update", "install"])
        assert result.exit_code == 0
        assert "up to date" in result.output.lower()

    @patch("file_organizer.updater.UpdateManager")
    def test_install_success(self, mock_cls: MagicMock) -> None:
        mock_mgr = MagicMock()
        mock_cls.return_value = mock_mgr

        install_result = _make_install_result(success=True)
        mock_mgr.update.return_value = _make_status(available=True, install_result=install_result)

        result = runner.invoke(app, ["update", "install"])
        assert result.exit_code == 0
        assert "Updated successfully" in result.output

    @patch("file_organizer.updater.UpdateManager")
    def test_install_failure(self, mock_cls: MagicMock) -> None:
        mock_mgr = MagicMock()
        mock_cls.return_value = mock_mgr

        install_result = _make_install_result(success=False, message="Download failed")
        mock_mgr.update.return_value = _make_status(available=True, install_result=install_result)

        result = runner.invoke(app, ["update", "install"])
        assert result.exit_code == 1
        assert "Download failed" in result.output

    @patch("file_organizer.updater.UpdateManager")
    def test_install_no_result(self, mock_cls: MagicMock) -> None:
        mock_mgr = MagicMock()
        mock_cls.return_value = mock_mgr
        mock_mgr.update.return_value = _make_status(available=True, install_result=None)

        result = runner.invoke(app, ["update", "install"])
        assert result.exit_code == 1
        assert "failed" in result.output.lower()

    @patch("file_organizer.updater.UpdateManager")
    def test_install_dry_run(self, mock_cls: MagicMock) -> None:
        mock_mgr = MagicMock()
        mock_cls.return_value = mock_mgr

        install_result = _make_install_result(success=True)
        mock_mgr.update.return_value = _make_status(available=True, install_result=install_result)

        result = runner.invoke(app, ["update", "install", "--dry-run"])
        assert result.exit_code == 0
        mock_mgr.update.assert_called_once_with(dry_run=True)


# ---------------------------------------------------------------------------
# update rollback
# ---------------------------------------------------------------------------


class TestUpdateRollback:
    """Tests for ``update rollback``."""

    @patch("file_organizer.updater.UpdateInstaller")
    def test_rollback_success(self, mock_cls: MagicMock) -> None:
        mock_installer = MagicMock()
        mock_cls.return_value = mock_installer
        mock_installer.rollback.return_value = True

        result = runner.invoke(app, ["update", "rollback"])
        assert result.exit_code == 0
        assert "Rolled back" in result.output

    @patch("file_organizer.updater.UpdateInstaller")
    def test_rollback_no_backup(self, mock_cls: MagicMock) -> None:
        mock_installer = MagicMock()
        mock_cls.return_value = mock_installer
        mock_installer.rollback.return_value = False

        result = runner.invoke(app, ["update", "rollback"])
        assert result.exit_code == 1
        assert "No backup" in result.output
