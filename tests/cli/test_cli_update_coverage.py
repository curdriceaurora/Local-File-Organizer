"""Coverage tests for file_organizer.cli.update — uncovered lines 30-44, 62-83, 89-96."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

pytestmark = pytest.mark.unit

runner = CliRunner()


# ---------------------------------------------------------------------------
# Stub types returned by UpdateManager / UpdateInstaller
# ---------------------------------------------------------------------------
@dataclass
class _FakeRelease:
    html_url: str = "https://github.com/example/repo/releases/tag/v1.0.0"
    body: str = "Release notes here"


@dataclass
class _FakeInstallResult:
    success: bool = True
    message: str = "Installed successfully"
    sha256: str = "abc123def456abc123def456abc123de"


@dataclass
class _FakeUpdateStatus:
    current_version: str = "0.9.0"
    latest_version: str = "1.0.0"
    available: bool = True
    release: Optional[_FakeRelease] = None
    install_result: Optional[_FakeInstallResult] = None


# ---------------------------------------------------------------------------
# Tests for `update check`
# ---------------------------------------------------------------------------
class TestUpdateCheck:
    """Covers lines 30-44."""

    def test_update_available(self) -> None:
        """When update is available with release info."""
        from file_organizer.cli.update import update_app

        fake_status = _FakeUpdateStatus(
            available=True,
            release=_FakeRelease(),
        )
        mock_mgr = MagicMock()
        mock_mgr.check.return_value = fake_status

        with patch("file_organizer.updater.UpdateManager", return_value=mock_mgr):
            result = runner.invoke(update_app, ["check"])

        assert result.exit_code == 0
        assert "1.0.0" in result.output
        assert "Update available" in result.output

    def test_already_up_to_date(self) -> None:
        """When already at latest version."""
        from file_organizer.cli.update import update_app

        fake_status = _FakeUpdateStatus(available=False, release=None)
        mock_mgr = MagicMock()
        mock_mgr.check.return_value = fake_status

        with patch("file_organizer.updater.UpdateManager", return_value=mock_mgr):
            result = runner.invoke(update_app, ["check"])

        assert result.exit_code == 0
        assert "up to date" in result.output

    def test_update_available_no_body(self) -> None:
        """Release exists but body is empty."""
        from file_organizer.cli.update import update_app

        release = _FakeRelease(body="")
        fake_status = _FakeUpdateStatus(available=True, release=release)
        mock_mgr = MagicMock()
        mock_mgr.check.return_value = fake_status

        with patch("file_organizer.updater.UpdateManager", return_value=mock_mgr):
            result = runner.invoke(update_app, ["check"])

        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Tests for `update install`
# ---------------------------------------------------------------------------
class TestUpdateInstall:
    """Covers lines 62-83."""

    def test_install_already_up_to_date(self) -> None:
        from file_organizer.cli.update import update_app

        fake_status = _FakeUpdateStatus(available=False, install_result=None)
        mock_mgr = MagicMock()
        mock_mgr.update.return_value = fake_status

        with patch("file_organizer.updater.UpdateManager", return_value=mock_mgr):
            result = runner.invoke(update_app, ["install"])

        assert result.exit_code == 0
        assert "up to date" in result.output

    def test_install_result_none(self) -> None:
        from file_organizer.cli.update import update_app

        fake_status = _FakeUpdateStatus(available=True, install_result=None)
        mock_mgr = MagicMock()
        mock_mgr.update.return_value = fake_status

        with patch("file_organizer.updater.UpdateManager", return_value=mock_mgr):
            result = runner.invoke(update_app, ["install"])

        assert result.exit_code == 1

    def test_install_success_with_sha(self) -> None:
        from file_organizer.cli.update import update_app

        fake_status = _FakeUpdateStatus(
            available=True,
            install_result=_FakeInstallResult(success=True, sha256="abcdef1234567890"),
        )
        mock_mgr = MagicMock()
        mock_mgr.update.return_value = fake_status

        with patch("file_organizer.updater.UpdateManager", return_value=mock_mgr):
            result = runner.invoke(update_app, ["install"])

        assert result.exit_code == 0
        assert "SHA256" in result.output

    def test_install_success_no_sha(self) -> None:
        from file_organizer.cli.update import update_app

        fake_status = _FakeUpdateStatus(
            available=True,
            install_result=_FakeInstallResult(success=True, sha256=""),
        )
        mock_mgr = MagicMock()
        mock_mgr.update.return_value = fake_status

        with patch("file_organizer.updater.UpdateManager", return_value=mock_mgr):
            result = runner.invoke(update_app, ["install"])

        assert result.exit_code == 0

    def test_install_failure(self) -> None:
        from file_organizer.cli.update import update_app

        fake_status = _FakeUpdateStatus(
            available=True,
            install_result=_FakeInstallResult(success=False, message="Download failed"),
        )
        mock_mgr = MagicMock()
        mock_mgr.update.return_value = fake_status

        with patch("file_organizer.updater.UpdateManager", return_value=mock_mgr):
            result = runner.invoke(update_app, ["install"])

        assert result.exit_code == 1
        assert "Download failed" in result.output


# ---------------------------------------------------------------------------
# Tests for `update rollback`
# ---------------------------------------------------------------------------
class TestUpdateRollback:
    """Covers lines 89-96."""

    def test_rollback_success(self) -> None:
        from file_organizer.cli.update import update_app

        mock_installer = MagicMock()
        mock_installer.rollback.return_value = True

        with patch("file_organizer.updater.UpdateInstaller", return_value=mock_installer):
            result = runner.invoke(update_app, ["rollback"])

        assert result.exit_code == 0
        assert "Rolled back" in result.output

    def test_rollback_no_backup(self) -> None:
        from file_organizer.cli.update import update_app

        mock_installer = MagicMock()
        mock_installer.rollback.return_value = False

        with patch("file_organizer.updater.UpdateInstaller", return_value=mock_installer):
            result = runner.invoke(update_app, ["rollback"])

        assert result.exit_code == 1
        assert "No backup" in result.output
