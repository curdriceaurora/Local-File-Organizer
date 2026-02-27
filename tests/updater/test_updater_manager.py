"""Tests for file_organizer.updater.manager module.

Covers UpdateStatus, UpdateManager.check, update (with dry_run), and rollback.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from file_organizer.updater.checker import AssetInfo, ReleaseInfo
from file_organizer.updater.installer import InstallResult
from file_organizer.updater.manager import UpdateManager, UpdateStatus

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# UpdateStatus
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestUpdateStatus:
    """Test UpdateStatus dataclass and message property."""

    def test_defaults(self):
        s = UpdateStatus()
        assert s.available is False
        assert s.current_version == ""

    def test_message_up_to_date(self):
        s = UpdateStatus(available=False, current_version="1.0.0")
        assert "Up to date" in s.message
        assert "1.0.0" in s.message

    def test_message_available(self):
        s = UpdateStatus(
            available=True, current_version="1.0.0", latest_version="2.0.0"
        )
        assert "Update available" in s.message
        assert "1.0.0" in s.message
        assert "2.0.0" in s.message

    def test_message_with_install_result(self):
        s = UpdateStatus(
            available=True,
            install_result=InstallResult(success=True, message="Updated!"),
        )
        assert s.message == "Updated!"


# ---------------------------------------------------------------------------
# UpdateManager — check
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestUpdateManagerCheck:
    """Test UpdateManager.check method."""

    @patch("file_organizer.updater.manager.UpdateChecker")
    @patch("file_organizer.updater.manager.UpdateInstaller")
    def test_no_update(self, mock_installer_cls, mock_checker_cls):
        mock_checker = MagicMock()
        mock_checker.current_version = "1.0.0"
        mock_checker.check.return_value = None
        mock_checker_cls.return_value = mock_checker
        mock_installer_cls.return_value = MagicMock()

        mgr = UpdateManager(current_version="1.0.0")
        status = mgr.check()
        assert status.available is False
        assert status.current_version == "1.0.0"

    @patch("file_organizer.updater.manager.UpdateChecker")
    @patch("file_organizer.updater.manager.UpdateInstaller")
    def test_update_available(self, mock_installer_cls, mock_checker_cls):
        release = ReleaseInfo(tag="v2.0.0", version="2.0.0")
        mock_checker = MagicMock()
        mock_checker.current_version = "1.0.0"
        mock_checker.check.return_value = release
        mock_checker_cls.return_value = mock_checker
        mock_installer_cls.return_value = MagicMock()

        mgr = UpdateManager(current_version="1.0.0")
        status = mgr.check()
        assert status.available is True
        assert status.latest_version == "2.0.0"
        assert status.release is release


# ---------------------------------------------------------------------------
# UpdateManager — update
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestUpdateManagerUpdate:
    """Test UpdateManager.update method."""

    @patch("file_organizer.updater.manager.UpdateChecker")
    @patch("file_organizer.updater.manager.UpdateInstaller")
    def test_no_update_available(self, mock_installer_cls, mock_checker_cls):
        mock_checker = MagicMock()
        mock_checker.current_version = "1.0.0"
        mock_checker.check.return_value = None
        mock_checker_cls.return_value = mock_checker
        mock_installer_cls.return_value = MagicMock()

        mgr = UpdateManager(current_version="1.0.0")
        status = mgr.update()
        assert status.available is False

    @patch("file_organizer.updater.manager.UpdateChecker")
    @patch("file_organizer.updater.manager.UpdateInstaller")
    def test_no_compatible_asset(self, mock_installer_cls, mock_checker_cls):
        release = ReleaseInfo(tag="v2.0.0", version="2.0.0", assets=[])
        mock_checker = MagicMock()
        mock_checker.current_version = "1.0.0"
        mock_checker.check.return_value = release
        mock_checker_cls.return_value = mock_checker

        mock_installer = MagicMock()
        mock_installer.select_asset.return_value = None
        mock_installer_cls.return_value = mock_installer

        mgr = UpdateManager(current_version="1.0.0")
        status = mgr.update()
        assert status.install_result is not None
        assert status.install_result.success is False
        assert "No compatible" in status.install_result.message

    @patch("file_organizer.updater.manager.UpdateChecker")
    @patch("file_organizer.updater.manager.UpdateInstaller")
    def test_download_failed(self, mock_installer_cls, mock_checker_cls):
        asset = AssetInfo(name="app.bin", url="https://example.com/app.bin", size=100)
        release = ReleaseInfo(tag="v2.0.0", version="2.0.0", assets=[asset])

        mock_checker = MagicMock()
        mock_checker.current_version = "1.0.0"
        mock_checker.check.return_value = release
        mock_checker_cls.return_value = mock_checker

        mock_installer = MagicMock()
        mock_installer.select_asset.return_value = asset
        mock_installer.find_checksum.return_value = ""
        mock_installer.download_asset.return_value = None
        mock_installer_cls.return_value = mock_installer

        mgr = UpdateManager(current_version="1.0.0")
        status = mgr.update()
        assert status.install_result is not None
        assert status.install_result.success is False
        assert "Download failed" in status.install_result.message

    @patch("file_organizer.updater.manager.UpdateChecker")
    @patch("file_organizer.updater.manager.UpdateInstaller")
    def test_dry_run(self, mock_installer_cls, mock_checker_cls, tmp_path):
        asset = AssetInfo(name="app.bin", url="https://example.com/app.bin", size=100)
        release = ReleaseInfo(tag="v2.0.0", version="2.0.0", assets=[asset])

        mock_checker = MagicMock()
        mock_checker.current_version = "1.0.0"
        mock_checker.check.return_value = release
        mock_checker_cls.return_value = mock_checker

        downloaded = tmp_path / "downloaded.bin"
        downloaded.write_bytes(b"binary")

        mock_installer = MagicMock()
        mock_installer.select_asset.return_value = asset
        mock_installer.find_checksum.return_value = "abc"
        mock_installer.download_asset.return_value = downloaded
        mock_installer_cls.return_value = mock_installer

        mgr = UpdateManager(current_version="1.0.0")
        status = mgr.update(dry_run=True)
        assert status.install_result is not None
        assert status.install_result.success is True
        assert "Dry run" in status.install_result.message

    @patch("file_organizer.updater.manager.UpdateChecker")
    @patch("file_organizer.updater.manager.UpdateInstaller")
    def test_full_install(self, mock_installer_cls, mock_checker_cls, tmp_path):
        asset = AssetInfo(name="app.bin", url="https://example.com/app.bin", size=100)
        release = ReleaseInfo(tag="v2.0.0", version="2.0.0", assets=[asset])

        mock_checker = MagicMock()
        mock_checker.current_version = "1.0.0"
        mock_checker.check.return_value = release
        mock_checker_cls.return_value = mock_checker

        downloaded = tmp_path / "downloaded.bin"
        downloaded.write_bytes(b"binary")

        install_result = InstallResult(success=True, message="Done!")
        mock_installer = MagicMock()
        mock_installer.select_asset.return_value = asset
        mock_installer.find_checksum.return_value = ""
        mock_installer.download_asset.return_value = downloaded
        mock_installer.install.return_value = install_result
        mock_installer_cls.return_value = mock_installer

        mgr = UpdateManager(current_version="1.0.0")
        status = mgr.update()
        assert status.install_result is install_result


# ---------------------------------------------------------------------------
# UpdateManager — rollback
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestUpdateManagerRollback:
    """Test UpdateManager.rollback method."""

    @patch("file_organizer.updater.manager.UpdateChecker")
    @patch("file_organizer.updater.manager.UpdateInstaller")
    def test_rollback_delegates(self, mock_installer_cls, mock_checker_cls):
        mock_installer = MagicMock()
        mock_installer.rollback.return_value = True
        mock_installer_cls.return_value = mock_installer
        mock_checker_cls.return_value = MagicMock()

        mgr = UpdateManager(current_version="1.0.0")
        assert mgr.rollback() is True
        mock_installer.rollback.assert_called_once()

    @patch("file_organizer.updater.manager.UpdateChecker")
    @patch("file_organizer.updater.manager.UpdateInstaller")
    def test_current_version_property(self, mock_installer_cls, mock_checker_cls):
        mock_checker = MagicMock()
        mock_checker.current_version = "3.0.0"
        mock_checker_cls.return_value = mock_checker
        mock_installer_cls.return_value = MagicMock()

        mgr = UpdateManager(current_version="3.0.0")
        assert mgr.current_version == "3.0.0"
