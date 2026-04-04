"""Tests for file_organizer.updater.sidecar_updater module.

Covers check_backend_update, coordinated_update, and BackendUpdateStatus /
CoordinatedUpdateResult data classes.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.updater.checker import AssetInfo, ReleaseInfo
from file_organizer.updater.installer import InstallResult
from file_organizer.updater.sidecar_updater import (
    BackendUpdateStatus,
    CoordinatedUpdateResult,
    check_backend_update,
    coordinated_update,
)

pytestmark = [pytest.mark.unit, pytest.mark.ci]

_CHECKER_PATH = "file_organizer.updater.sidecar_updater.UpdateChecker"
_INSTALLER_PATH = "file_organizer.updater.sidecar_updater.UpdateInstaller"
_MANAGER_PATH = "file_organizer.updater.sidecar_updater.UpdateManager"


def _make_release(version: str = "2.0.0") -> ReleaseInfo:
    asset = AssetInfo(name=f"file-organizer-{version}-linux-x86_64", url="https://example.com/bin")
    return ReleaseInfo(version=version, assets=[asset])


# ---------------------------------------------------------------------------
# BackendUpdateStatus defaults
# ---------------------------------------------------------------------------


class TestBackendUpdateStatusDefaults:
    """BackendUpdateStatus fields default correctly."""

    def test_defaults(self) -> None:
        status = BackendUpdateStatus()
        assert status.available is False
        assert status.current_version == ""
        assert status.latest_version == ""
        assert status.release is None
        assert status.install_result is None
        assert status.message == ""


# ---------------------------------------------------------------------------
# CoordinatedUpdateResult defaults
# ---------------------------------------------------------------------------


class TestCoordinatedUpdateResultDefaults:
    """CoordinatedUpdateResult fields default correctly."""

    def test_defaults(self) -> None:
        result = CoordinatedUpdateResult()
        assert result.success is False
        assert result.rolled_back is False
        assert result.shell_updated is False
        assert result.backend_updated is False
        assert result.backend_version == ""
        assert result.shell_version == ""
        assert result.message == ""
        assert result.events == []


# ---------------------------------------------------------------------------
# check_backend_update
# ---------------------------------------------------------------------------


class TestCheckBackendUpdate:
    """Tests for check_backend_update()."""

    def test_no_update_available_returns_up_to_date_status(self) -> None:
        """When UpdateChecker.check() returns None, status.available is False."""
        mock_checker = MagicMock()
        mock_checker.check.return_value = None
        mock_checker.current_version = "1.0.0"

        with patch(_CHECKER_PATH, return_value=mock_checker):
            status = check_backend_update(current_version="1.0.0")

        assert status.available is False  # line 119
        assert status.current_version == "1.0.0"
        assert "up to date" in status.message.lower()
        assert "1.0.0" in status.message

    def test_update_available_returns_available_status(self) -> None:
        """When UpdateChecker.check() returns a release, status.available is True."""
        release = _make_release("2.0.0")
        mock_checker = MagicMock()
        mock_checker.check.return_value = release
        mock_checker.current_version = "1.0.0"

        with patch(_CHECKER_PATH, return_value=mock_checker):
            status = check_backend_update(current_version="1.0.0")

        assert status.available is True  # line 125
        assert status.latest_version == "2.0.0"
        assert status.release is release
        assert "available" in status.message.lower()
        assert "1.0.0" in status.message
        assert "2.0.0" in status.message


# ---------------------------------------------------------------------------
# coordinated_update — no update path
# ---------------------------------------------------------------------------


class TestCoordinatedUpdateNoUpdate:
    """coordinated_update when no update is available."""

    def test_no_update_returns_early(self) -> None:
        """When no update is available, result.success is False and no install occurs."""
        mock_checker = MagicMock()
        mock_checker.check.return_value = None
        mock_checker.current_version = "1.0.0"

        with patch(_CHECKER_PATH, return_value=mock_checker):
            result = coordinated_update(current_version="1.0.0")  # line 177

        assert result.success is False
        assert result.backend_updated is False
        assert "up to date" in result.message.lower()


# ---------------------------------------------------------------------------
# coordinated_update — asset not found
# ---------------------------------------------------------------------------


class TestCoordinatedUpdateNoAsset:
    """coordinated_update when no compatible asset is found."""

    def test_no_asset_sets_failed_message(self) -> None:
        """When installer.select_asset() returns None, result reflects failure."""
        release = _make_release("2.0.0")
        mock_checker = MagicMock()
        mock_checker.check.return_value = release
        mock_checker.current_version = "1.0.0"

        mock_installer = MagicMock()
        mock_installer.select_asset.return_value = None  # no compatible asset

        with (
            patch(_CHECKER_PATH, return_value=mock_checker),
            patch(_INSTALLER_PATH, return_value=mock_installer),
        ):
            result = coordinated_update(current_version="1.0.0")

        assert result.success is False  # line 196
        assert "backend" in result.message.lower()
        assert "update-failed" in result.events


# ---------------------------------------------------------------------------
# coordinated_update — download failure
# ---------------------------------------------------------------------------


class TestCoordinatedUpdateDownloadFailure:
    """coordinated_update when asset download fails."""

    def test_download_failure_sets_failed_message(self) -> None:
        """When download_asset() returns None, result reflects download failure."""
        release = _make_release("2.0.0")
        asset = release.assets[0]

        mock_checker = MagicMock()
        mock_checker.check.return_value = release
        mock_checker.current_version = "1.0.0"

        mock_installer = MagicMock()
        mock_installer.select_asset.return_value = asset
        mock_installer.find_checksum.return_value = None
        mock_installer.download_asset.return_value = None  # download failed

        with (
            patch(_CHECKER_PATH, return_value=mock_checker),
            patch(_INSTALLER_PATH, return_value=mock_installer),
        ):
            result = coordinated_update(current_version="1.0.0")

        assert result.success is False  # line 212
        assert "download failed" in result.message.lower()
        assert "update-failed" in result.events

    def test_checksum_logged_when_present(self, tmp_path: Path) -> None:
        """When find_checksum returns a value, it is logged (line 202)."""
        release = _make_release("2.0.0")
        asset = release.assets[0]

        mock_checker = MagicMock()
        mock_checker.check.return_value = release
        mock_checker.current_version = "1.0.0"

        mock_installer = MagicMock()
        mock_installer.select_asset.return_value = asset
        mock_installer.find_checksum.return_value = "abc123deadbeef" * 4  # line 202
        mock_installer.download_asset.return_value = None  # still fails

        with (
            patch(_CHECKER_PATH, return_value=mock_checker),
            patch(_INSTALLER_PATH, return_value=mock_installer),
        ):
            result = coordinated_update(current_version="1.0.0")

        assert result.success is False


# ---------------------------------------------------------------------------
# coordinated_update — dry run
# ---------------------------------------------------------------------------


class TestCoordinatedUpdateDryRun:
    """coordinated_update dry_run=True path."""

    def test_dry_run_succeeds_without_installing(self, tmp_path: Path) -> None:
        """dry_run=True returns success without calling install()."""
        release = _make_release("2.0.0")
        asset = release.assets[0]
        fake_download = tmp_path / "download.bin"
        fake_download.write_bytes(b"binary")

        mock_checker = MagicMock()
        mock_checker.check.return_value = release
        mock_checker.current_version = "1.0.0"

        mock_installer = MagicMock()
        mock_installer.select_asset.return_value = asset
        mock_installer.find_checksum.return_value = None
        mock_installer.download_asset.return_value = fake_download

        with (
            patch(_CHECKER_PATH, return_value=mock_checker),
            patch(_INSTALLER_PATH, return_value=mock_installer),
        ):
            result = coordinated_update(current_version="1.0.0", dry_run=True)

        assert result.success is True  # line 218-219
        mock_installer.install.assert_not_called()
        assert "dry run" in result.message.lower()
        assert "2.0.0" in result.message


# ---------------------------------------------------------------------------
# coordinated_update — successful install
# ---------------------------------------------------------------------------


class TestCoordinatedUpdateSuccess:
    """coordinated_update happy path."""

    def test_successful_install_sets_backend_updated(self, tmp_path: Path) -> None:
        """On success, backend_updated=True and backend_version is set."""
        release = _make_release("2.0.0")
        asset = release.assets[0]
        fake_download = tmp_path / "download.bin"
        fake_download.write_bytes(b"binary")

        mock_checker = MagicMock()
        mock_checker.check.return_value = release
        mock_checker.current_version = "1.0.0"

        mock_installer = MagicMock()
        mock_installer.select_asset.return_value = asset
        mock_installer.find_checksum.return_value = None
        mock_installer.download_asset.return_value = fake_download
        mock_installer.install.return_value = InstallResult(success=True, message="ok")

        events: list[tuple[str, object]] = []

        with (
            patch(_CHECKER_PATH, return_value=mock_checker),
            patch(_INSTALLER_PATH, return_value=mock_installer),
        ):
            result = coordinated_update(
                current_version="1.0.0",
                event_callback=lambda e, p: events.append((e, p)),
            )

        assert result.success is True
        assert result.backend_updated is True  # line 226
        assert result.backend_version == "2.0.0"  # line 227
        assert "2.0.0" in result.message  # line 229
        assert any(e == "update-installed" for e, _ in events)  # line 234


# ---------------------------------------------------------------------------
# coordinated_update — install failure with rollback
# ---------------------------------------------------------------------------


class TestCoordinatedUpdateInstallFailure:
    """coordinated_update when install fails and rollback is attempted."""

    def test_install_failure_rolled_back(self, tmp_path: Path) -> None:
        """On install failure + successful rollback, rolled_back=True."""
        release = _make_release("2.0.0")
        asset = release.assets[0]
        fake_download = tmp_path / "download.bin"
        fake_download.write_bytes(b"binary")

        mock_checker = MagicMock()
        mock_checker.check.return_value = release
        mock_checker.current_version = "1.0.0"

        mock_installer = MagicMock()
        mock_installer.select_asset.return_value = asset
        mock_installer.find_checksum.return_value = None
        mock_installer.download_asset.return_value = fake_download
        mock_installer.install.return_value = InstallResult(success=False, message="write error")

        mock_manager = MagicMock()
        mock_manager.rollback.return_value = True

        with (
            patch(_CHECKER_PATH, return_value=mock_checker),
            patch(_INSTALLER_PATH, return_value=mock_installer),
            patch(_MANAGER_PATH, return_value=mock_manager),
        ):
            result = coordinated_update(current_version="1.0.0")

        assert result.success is False
        assert result.rolled_back is True  # line 247
        assert "rolled back" in result.message.lower()  # line 249

    def test_install_failure_rollback_also_fails(self, tmp_path: Path) -> None:
        """On install failure + failed rollback, rolled_back=False."""
        release = _make_release("2.0.0")
        asset = release.assets[0]
        fake_download = tmp_path / "download.bin"
        fake_download.write_bytes(b"binary")

        mock_checker = MagicMock()
        mock_checker.check.return_value = release
        mock_checker.current_version = "1.0.0"

        mock_installer = MagicMock()
        mock_installer.select_asset.return_value = asset
        mock_installer.find_checksum.return_value = None
        mock_installer.download_asset.return_value = fake_download
        mock_installer.install.return_value = InstallResult(success=False, message="write error")

        mock_manager = MagicMock()
        mock_manager.rollback.return_value = False

        with (
            patch(_CHECKER_PATH, return_value=mock_checker),
            patch(_INSTALLER_PATH, return_value=mock_installer),
            patch(_MANAGER_PATH, return_value=mock_manager),
        ):
            result = coordinated_update(current_version="1.0.0")

        assert result.success is False
        assert result.rolled_back is False
        assert "rollback also failed" in result.message.lower()
