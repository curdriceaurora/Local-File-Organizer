"""Coverage tests for file_organizer.cli.api — uncovered error branches."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

pytestmark = pytest.mark.unit

runner = CliRunner()


def _mock_client_and_error(error_msg: str = "connection refused"):
    """Return a mock client that raises ClientError and the ClientError class."""
    mock_error_cls = type("ClientError", (Exception,), {})
    mock_client = MagicMock()
    return mock_client, mock_error_cls, mock_error_cls(error_msg)


class TestApiHealth:
    """Covers health error branch (line 88)."""

    def test_health_error(self) -> None:
        from file_organizer.cli.api import api_app

        client, err_cls, err = _mock_client_and_error()
        client.health.side_effect = err

        with patch("file_organizer.cli.api._build_client", return_value=(client, err_cls)):
            result = runner.invoke(api_app, ["health"])

        assert result.exit_code == 1
        assert "error" in result.output.lower()


class TestApiLogin:
    """Covers login error branches (lines 111-112, 116-118)."""

    def test_login_error(self) -> None:
        from file_organizer.cli.api import api_app

        client, err_cls, err = _mock_client_and_error("invalid credentials")
        client.login.side_effect = err

        with patch("file_organizer.cli.api._build_client", return_value=(client, err_cls)):
            result = runner.invoke(
                api_app,
                ["login", "--username", "user", "--password", "pass"],
            )

        assert result.exit_code == 1


class TestApiMe:
    """Covers me error branch (lines 135-137)."""

    def test_me_error(self) -> None:
        from file_organizer.cli.api import api_app

        client, err_cls, err = _mock_client_and_error()
        client.me.side_effect = err

        with patch("file_organizer.cli.api._build_client", return_value=(client, err_cls)):
            result = runner.invoke(api_app, ["me", "--token", "fake-token"])

        assert result.exit_code == 1


class TestApiLogout:
    """Covers logout error branch (lines 163-164)."""

    def test_logout_error(self) -> None:
        from file_organizer.cli.api import api_app

        client, err_cls, err = _mock_client_and_error()
        client.logout.side_effect = err

        with patch("file_organizer.cli.api._build_client", return_value=(client, err_cls)):
            result = runner.invoke(
                api_app,
                [
                    "logout",
                    "--token",
                    "fake-token",
                    "--refresh-token",
                    "fake-refresh",
                ],
            )

        assert result.exit_code == 1


class TestApiFiles:
    """Covers files error branch (lines 172-174)."""

    def test_files_error(self) -> None:
        from file_organizer.cli.api import api_app

        client, err_cls, err = _mock_client_and_error()
        client.list_files.side_effect = err

        with patch("file_organizer.cli.api._build_client", return_value=(client, err_cls)):
            result = runner.invoke(
                api_app,
                ["files", "/tmp", "--token", "fake-token"],
            )

        assert result.exit_code == 1


class TestApiSystemStatus:
    """Covers system-status error branch (lines 192-193, 197-199)."""

    def test_system_status_error(self) -> None:
        from file_organizer.cli.api import api_app

        client, err_cls, err = _mock_client_and_error()
        client.system_status.side_effect = err

        with patch("file_organizer.cli.api._build_client", return_value=(client, err_cls)):
            result = runner.invoke(
                api_app,
                ["system-status", ".", "--token", "fake-token"],
            )

        assert result.exit_code == 1


class TestApiSystemStats:
    """Covers system-stats error branch (lines 219-220, 224-226)."""

    def test_system_stats_error(self) -> None:
        from file_organizer.cli.api import api_app

        client, err_cls, err = _mock_client_and_error()
        client.system_stats.side_effect = err

        with patch("file_organizer.cli.api._build_client", return_value=(client, err_cls)):
            result = runner.invoke(
                api_app,
                ["system-stats", ".", "--token", "fake-token"],
            )

        assert result.exit_code == 1
