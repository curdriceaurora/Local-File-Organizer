"""Tests for CLI API sub-commands."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from file_organizer.cli.api import api_app
from file_organizer.client.exceptions import ClientError

runner = CliRunner()


@pytest.fixture
def mock_client_cls():
    """Mock the FileOrganizerClient class."""
    with patch("file_organizer.cli.api.FileOrganizerClient") as mock:
        yield mock


def test_health_command(mock_client_cls):
    """Test the health command success."""
    mock_instance = MagicMock()
    mock_instance.health.return_value = MagicMock(
        status="ok", version="1.0.0", environment="test"
    )
    mock_client_cls.return_value = mock_instance

    result = runner.invoke(api_app, ["health"])

    assert result.exit_code == 0
    assert "ok" in result.stdout
    assert "1.0.0" in result.stdout
    mock_instance.close.assert_called_once()


def test_health_command_json(mock_client_cls):
    """Test the health command JSON output."""
    mock_instance = MagicMock()
    mock_health = MagicMock()
    mock_health.model_dump.return_value = {"status": "ok", "version": "1.0.0"}
    mock_instance.health.return_value = mock_health
    mock_client_cls.return_value = mock_instance

    result = runner.invoke(api_app, ["health", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["status"] == "ok"


def test_health_command_error(mock_client_cls):
    """Test health command handles errors."""
    mock_instance = MagicMock()
    mock_instance.health.side_effect = ClientError("Connection failed")
    mock_client_cls.return_value = mock_instance

    result = runner.invoke(api_app, ["health"])

    assert result.exit_code == 1
    assert "API error:" in result.stdout
    assert "Connection failed" in result.stdout


def test_login_command(mock_client_cls, tmp_path):
    """Test the login command success."""
    mock_instance = MagicMock()
    mock_tokens = MagicMock()
    mock_tokens.model_dump.return_value = {"access_token": "abc", "refresh_token": "def"}
    mock_instance.login.return_value = mock_tokens
    mock_client_cls.return_value = mock_instance

    token_file = tmp_path / "token.json"

    result = runner.invoke(
        api_app,
        ["login", "--save-token", str(token_file)],
        input="user\npass\n"
    )

    assert result.exit_code == 0
    assert "Login successful" in result.stdout
    mock_instance.login.assert_called_once_with("user", "pass")

    assert token_file.exists()
    saved = json.loads(token_file.read_text())
    assert saved["access_token"] == "abc"


def test_login_command_error(mock_client_cls):
    """Test the login command failure."""
    mock_instance = MagicMock()
    mock_instance.login.side_effect = ClientError("Invalid credentials")
    mock_client_cls.return_value = mock_instance

    result = runner.invoke(api_app, ["login"], input="user\npass\n")

    assert result.exit_code == 1
    assert "Login failed" in result.stdout


def test_me_command(mock_client_cls):
    """Test the me command."""
    mock_instance = MagicMock()
    mock_instance.me.return_value = MagicMock(
        username="admin", email="admin@test.com", is_admin=True
    )
    mock_client_cls.return_value = mock_instance

    result = runner.invoke(api_app, ["me", "--token", "abc"])

    assert result.exit_code == 0
    assert "User: admin" in result.stdout
    assert "admin@test.com" in result.stdout


def test_logout_command(mock_client_cls):
    """Test the logout command."""
    mock_instance = MagicMock()
    mock_client_cls.return_value = mock_instance

    result = runner.invoke(api_app, ["logout", "--token", "abc", "--refresh-token", "def"])

    assert result.exit_code == 0
    assert "Logout successful" in result.stdout
    mock_instance.logout.assert_called_once_with("def")


def test_files_list_command(mock_client_cls):
    """Test the files list command."""
    mock_instance = MagicMock()

    # Mock items
    item1 = MagicMock(name="f1.txt", file_type="file", size=100)
    item1.name = "f1.txt" # Need to set explicitly due to MagicMock behavior

    result_obj = MagicMock(total=1, items=[item1])
    mock_instance.list_files.return_value = result_obj
    mock_client_cls.return_value = mock_instance

    result = runner.invoke(api_app, ["files", ".", "--token", "abc"])

    assert result.exit_code == 0
    assert "Files (1)" in result.stdout
    assert "f1.txt" in result.stdout

    mock_instance.list_files.assert_called_once_with(
        ".", recursive=False, include_hidden=False, limit=100
    )


def test_system_status_command(mock_client_cls):
    """Test system status command."""
    mock_instance = MagicMock()
    mock_instance.system_status.return_value = MagicMock(
        disk_free="10GB", disk_used="90GB", active_jobs=5
    )
    mock_client_cls.return_value = mock_instance

    result = runner.invoke(api_app, ["system-status", ".", "--token", "abc"])

    assert result.exit_code == 0
    assert "10GB" in result.stdout
    assert "5" in result.stdout


def test_system_stats_command(mock_client_cls):
    """Test system stats command."""
    mock_instance = MagicMock()
    mock_instance.system_stats.return_value = MagicMock(
        file_count=100, directory_count=10, total_size="1MB"
    )
    mock_client_cls.return_value = mock_instance

    result = runner.invoke(api_app, ["system-stats", ".", "--token", "abc"])

    assert result.exit_code == 0
    assert "100" in result.stdout
    assert "1MB" in result.stdout
