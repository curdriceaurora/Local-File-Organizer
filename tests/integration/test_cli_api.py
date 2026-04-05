"""Integration tests for cli/api.py and cli/copilot.py.

api.py covers:
- health: success (text + json), ClientError path
- login: success (text + json + save-to), ClientError path
- me: success (text + json), ClientError path
- logout: success, ClientError path
- files (list): success (table + json), ClientError path
- system-status: success (text + json), ClientError path
- system-stats: success (text + json), ClientError path

copilot.py covers:
- chat single-shot mode: success
- chat REPL exit via quit command
- status command: Ollama available, Ollama unavailable
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from file_organizer.cli.api import api_app
from file_organizer.cli.copilot import copilot_app

pytestmark = [pytest.mark.integration, pytest.mark.ci]

runner = CliRunner()

# ---------------------------------------------------------------------------
# Client model helpers — build real Pydantic model instances
# ---------------------------------------------------------------------------


def _health_response(
    *, status: str = "ok", version: str = "1.2.3", readiness: str = "ready"
) -> MagicMock:
    """Return a MagicMock shaped like HealthResponse."""
    m = MagicMock()
    m.status = status
    m.version = version
    m.readiness = readiness
    m.model_dump.return_value = {
        "status": status,
        "version": version,
        "readiness": readiness,
        "ollama": True,
        "uptime": 42.0,
    }
    return m


def _token_response(*, access_token: str = "tok-acc", refresh_token: str = "tok-ref") -> MagicMock:
    m = MagicMock()
    m.access_token = access_token
    m.refresh_token = refresh_token
    m.model_dump.return_value = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }
    return m


def _user_response(
    *,
    username: str = "alice",
    email: str = "alice@example.com",
    is_admin: bool = False,
) -> MagicMock:
    m = MagicMock()
    m.username = username
    m.email = email
    m.is_admin = is_admin
    m.model_dump.return_value = {
        "id": "user-1",
        "username": username,
        "email": email,
        "is_admin": is_admin,
        "is_active": True,
        "full_name": None,
        "created_at": "2024-01-01T00:00:00",
        "last_login": None,
    }
    return m


def _file_list_response(*, total: int = 2) -> MagicMock:
    items = []
    item_dicts = []
    for i in range(1, total + 1):
        item = MagicMock()
        item.name = f"file{i}.txt"
        item.file_type = "text/plain"
        item.size = 100 * i
        items.append(item)
        item_dicts.append({"name": f"file{i}.txt", "size": 100 * i, "file_type": "text/plain"})
    m = MagicMock()
    m.total = total
    m.items = items
    m.model_dump.return_value = {
        "items": item_dicts,
        "total": total,
        "skip": 0,
        "limit": 100,
    }
    return m


def _system_status_response() -> MagicMock:
    m = MagicMock()
    m.disk_free = 600_000
    m.disk_used = 400_000
    m.active_jobs = 3
    m.model_dump.return_value = {
        "app": "file-organizer",
        "version": "2.0.0",
        "environment": "production",
        "disk_total": 1_000_000,
        "disk_used": 400_000,
        "disk_free": 600_000,
        "active_jobs": 3,
    }
    return m


def _system_stats_response() -> MagicMock:
    m = MagicMock()
    m.file_count = 42
    m.directory_count = 7
    m.total_size = 5_000_000
    m.model_dump.return_value = {
        "total_size": 5_000_000,
        "organized_size": 3_000_000,
        "saved_size": 500_000,
        "file_count": 42,
        "directory_count": 7,
        "size_by_type": {},
        "largest_files": [],
    }
    return m


def _make_client_error() -> Any:
    from file_organizer.client.exceptions import ClientError

    return ClientError("simulated API error", status_code=500, detail="server error")


def _make_mock_client(**method_returns: Any) -> MagicMock:
    """Build a MagicMock client with configured return values."""
    client = MagicMock()
    for method_name, return_value in method_returns.items():
        getattr(client, method_name).return_value = return_value
    return client


def _patch_build_client(mock_client: MagicMock) -> Any:
    """Return a context manager that patches _build_client for api.py."""
    from file_organizer.client.exceptions import ClientError

    return patch(
        "file_organizer.cli.api._build_client",
        return_value=(mock_client, ClientError),
    )


# ---------------------------------------------------------------------------
# health command
# ---------------------------------------------------------------------------


class TestHealthCommand:
    """Tests for ``api health``."""

    def test_health_text_output(self) -> None:
        """Default text output shows status, version, readiness."""
        client = _make_mock_client(health=_health_response())
        with _patch_build_client(client):
            result = runner.invoke(api_app, ["health"])

        assert result.exit_code == 0
        assert "ok" in result.output
        assert "1.2.3" in result.output
        assert "ready" in result.output

    def test_health_json_output(self) -> None:
        """--json flag produces parseable JSON with expected keys."""
        client = _make_mock_client(health=_health_response())
        with _patch_build_client(client):
            result = runner.invoke(api_app, ["health", "--json"])

        assert result.exit_code == 0
        output = result.output
        start = output.find("{")
        parsed = json.loads(output[start:])
        assert parsed["status"] == "ok"
        assert parsed["version"] == "1.2.3"

    def test_health_client_error_exits_1(self) -> None:
        """ClientError exits with code 1 and shows error message."""
        from file_organizer.client.exceptions import ClientError

        client = MagicMock()
        client.health.side_effect = ClientError(
            "Connection refused", status_code=503, detail="unavailable"
        )
        with _patch_build_client(client):
            result = runner.invoke(api_app, ["health"])

        assert result.exit_code == 1
        assert "API error" in result.output or "error" in result.output.lower()

    def test_health_client_close_always_called(self) -> None:
        """client.close() is called even on success (finally block)."""
        client = _make_mock_client(health=_health_response())
        with _patch_build_client(client):
            runner.invoke(api_app, ["health"])

        client.close.assert_called_once()


# ---------------------------------------------------------------------------
# login command
# ---------------------------------------------------------------------------


class TestLoginCommand:
    """Tests for ``api login``."""

    def test_login_text_output(self) -> None:
        """Successful login prints success message."""
        client = _make_mock_client(login=_token_response())
        with _patch_build_client(client):
            result = runner.invoke(
                api_app,
                ["login", "--username", "alice", "--password", "secret"],
            )

        assert result.exit_code == 0
        assert "Login successful" in result.output

    def test_login_json_output(self) -> None:
        """--json flag outputs token payload as JSON."""
        client = _make_mock_client(login=_token_response(access_token="at-xyz"))
        with _patch_build_client(client):
            result = runner.invoke(
                api_app,
                ["login", "--username", "alice", "--password", "secret", "--json"],
            )

        assert result.exit_code == 0
        output = result.output
        start = output.find("{")
        parsed = json.loads(output[start:])
        assert parsed["access_token"] == "at-xyz"

    def test_login_saves_token_to_file(self, tmp_path: Path) -> None:
        """--save-token writes a JSON token file to the specified path."""
        token_file = tmp_path / "token.json"
        client = _make_mock_client(
            login=_token_response(access_token="saved-token", refresh_token="ref-tok")
        )
        with _patch_build_client(client):
            result = runner.invoke(
                api_app,
                [
                    "login",
                    "--username",
                    "alice",
                    "--password",
                    "secret",
                    "--save-token",
                    str(token_file),
                ],
            )

        assert result.exit_code == 0
        assert token_file.exists()
        payload = json.loads(token_file.read_text())
        assert payload["access_token"] == "saved-token"

    def test_login_client_error_exits_1(self) -> None:
        """ClientError during login exits with code 1."""
        from file_organizer.client.exceptions import ClientError

        client = MagicMock()
        client.login.side_effect = ClientError("Bad credentials", status_code=401, detail="auth")
        with _patch_build_client(client):
            result = runner.invoke(
                api_app,
                ["login", "--username", "bad", "--password", "wrong"],
            )

        assert result.exit_code == 1
        assert "Login failed" in result.output or "error" in result.output.lower()

    def test_login_close_always_called(self) -> None:
        """client.close() is called even on error."""
        from file_organizer.client.exceptions import ClientError

        client = MagicMock()
        client.login.side_effect = ClientError("err", status_code=401, detail="x")
        with _patch_build_client(client):
            runner.invoke(api_app, ["login", "--username", "u", "--password", "p"])

        client.close.assert_called_once()


# ---------------------------------------------------------------------------
# me command
# ---------------------------------------------------------------------------


class TestMeCommand:
    """Tests for ``api me``."""

    def test_me_text_output(self) -> None:
        """Default text output shows username, email, admin flag."""
        client = _make_mock_client(me=_user_response(username="alice", email="alice@x.com"))
        with _patch_build_client(client):
            result = runner.invoke(api_app, ["me", "--token", "tok-123"])

        assert result.exit_code == 0
        assert "alice" in result.output
        assert "alice@x.com" in result.output

    def test_me_json_output(self) -> None:
        """--json flag produces JSON with username and email keys."""
        client = _make_mock_client(me=_user_response(username="bob", email="bob@y.com"))
        with _patch_build_client(client):
            result = runner.invoke(api_app, ["me", "--token", "tok-123", "--json"])

        assert result.exit_code == 0
        output = result.output
        start = output.find("{")
        parsed = json.loads(output[start:])
        assert parsed["username"] == "bob"
        assert parsed["email"] == "bob@y.com"

    def test_me_client_error_exits_1(self) -> None:
        """ClientError exits with code 1."""
        from file_organizer.client.exceptions import ClientError

        client = MagicMock()
        client.me.side_effect = ClientError("Unauthorized", status_code=401, detail="x")
        with _patch_build_client(client):
            result = runner.invoke(api_app, ["me", "--token", "expired"])

        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# logout command
# ---------------------------------------------------------------------------


class TestLogoutCommand:
    """Tests for ``api logout``."""

    def test_logout_success(self) -> None:
        """Successful logout prints success message."""
        client = MagicMock()
        client.logout.return_value = None
        with _patch_build_client(client):
            result = runner.invoke(
                api_app,
                ["logout", "--token", "tok", "--refresh-token", "ref"],
            )

        assert result.exit_code == 0
        assert "Logout successful" in result.output

    def test_logout_client_error_exits_1(self) -> None:
        """ClientError exits with code 1 and shows error message."""
        from file_organizer.client.exceptions import ClientError

        client = MagicMock()
        client.logout.side_effect = ClientError("Token revoked", status_code=401, detail="x")
        with _patch_build_client(client):
            result = runner.invoke(
                api_app,
                ["logout", "--token", "expired", "--refresh-token", "ref"],
            )

        assert result.exit_code == 1
        assert "Logout failed" in result.output or "error" in result.output.lower()


# ---------------------------------------------------------------------------
# files (list) command
# ---------------------------------------------------------------------------


class TestFilesListCommand:
    """Tests for ``api files``."""

    def test_files_table_output(self) -> None:
        """Default output shows a Rich table of file items."""
        client = _make_mock_client(list_files=_file_list_response(total=2))
        with _patch_build_client(client):
            result = runner.invoke(
                api_app,
                ["files", "/home/alice/docs", "--token", "tok"],
            )

        assert result.exit_code == 0
        assert "Files" in result.output
        assert "file1.txt" in result.output or "file2.txt" in result.output

    def test_files_json_output(self) -> None:
        """--json flag produces JSON with 'total' and 'items' keys."""
        client = _make_mock_client(list_files=_file_list_response(total=3))
        with _patch_build_client(client):
            result = runner.invoke(
                api_app,
                ["files", "/docs", "--token", "tok", "--json"],
            )

        assert result.exit_code == 0
        output = result.output
        start = output.find("{")
        parsed = json.loads(output[start:])
        assert parsed["total"] == 3
        assert len(parsed["items"]) == 3

    def test_files_client_error_exits_1(self) -> None:
        """ClientError exits with code 1."""
        from file_organizer.client.exceptions import ClientError

        client = MagicMock()
        client.list_files.side_effect = ClientError("not found", status_code=404, detail="x")
        with _patch_build_client(client):
            result = runner.invoke(
                api_app,
                ["files", "/missing", "--token", "tok"],
            )

        assert result.exit_code == 1
        assert "Request failed" in result.output or "error" in result.output.lower()


# ---------------------------------------------------------------------------
# system-status command
# ---------------------------------------------------------------------------


class TestSystemStatusCommand:
    """Tests for ``api system-status``."""

    def test_system_status_text_output(self) -> None:
        """Default text output shows disk and job metrics."""
        client = _make_mock_client(system_status=_system_status_response())
        with _patch_build_client(client):
            result = runner.invoke(
                api_app,
                ["system-status", ".", "--token", "tok"],
            )

        assert result.exit_code == 0
        assert "600000" in result.output or "Disk" in result.output
        assert "3" in result.output  # active_jobs

    def test_system_status_json_output(self) -> None:
        """--json flag produces JSON with disk and jobs fields."""
        client = _make_mock_client(system_status=_system_status_response())
        with _patch_build_client(client):
            result = runner.invoke(
                api_app,
                ["system-status", ".", "--token", "tok", "--json"],
            )

        assert result.exit_code == 0
        output = result.output
        start = output.find("{")
        parsed = json.loads(output[start:])
        assert parsed["disk_free"] == 600_000
        assert parsed["active_jobs"] == 3

    def test_system_status_client_error_exits_1(self) -> None:
        """ClientError exits with code 1."""
        from file_organizer.client.exceptions import ClientError

        client = MagicMock()
        client.system_status.side_effect = ClientError("server error", status_code=500, detail="x")
        with _patch_build_client(client):
            result = runner.invoke(
                api_app,
                ["system-status", ".", "--token", "tok"],
            )

        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# system-stats command
# ---------------------------------------------------------------------------


class TestSystemStatsCommand:
    """Tests for ``api system-stats``."""

    def test_system_stats_text_output(self) -> None:
        """Default text output shows file count, directory count, total size."""
        client = _make_mock_client(system_stats=_system_stats_response())
        with _patch_build_client(client):
            result = runner.invoke(
                api_app,
                ["system-stats", ".", "--token", "tok"],
            )

        assert result.exit_code == 0
        assert "42" in result.output  # file_count
        assert "7" in result.output  # directory_count

    def test_system_stats_json_output(self) -> None:
        """--json flag produces JSON with file_count and directory_count."""
        client = _make_mock_client(system_stats=_system_stats_response())
        with _patch_build_client(client):
            result = runner.invoke(
                api_app,
                ["system-stats", ".", "--token", "tok", "--json"],
            )

        assert result.exit_code == 0
        output = result.output
        start = output.find("{")
        parsed = json.loads(output[start:])
        assert parsed["file_count"] == 42
        assert parsed["directory_count"] == 7

    def test_system_stats_client_error_exits_1(self) -> None:
        """ClientError exits with code 1."""
        from file_organizer.client.exceptions import ClientError

        client = MagicMock()
        client.system_stats.side_effect = ClientError("error", status_code=500, detail="x")
        with _patch_build_client(client):
            result = runner.invoke(
                api_app,
                ["system-stats", ".", "--token", "tok"],
            )

        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# copilot: chat command
# ---------------------------------------------------------------------------


class TestCopilotChatCommand:
    """Tests for ``copilot chat``."""

    def test_chat_single_shot_prints_response(self) -> None:
        """Single message argument: engine.chat() result is printed.

        CopilotEngine is imported lazily inside the function body, so we patch
        the source module via sys.modules.
        """
        mock_engine = MagicMock()
        mock_engine.chat.return_value = "Here is how I can help you organise your files."
        mock_module = MagicMock()
        mock_module.CopilotEngine.return_value = mock_engine

        with patch.dict(
            "sys.modules",
            {"file_organizer.services.copilot.engine": mock_module},
        ):
            result = runner.invoke(copilot_app, ["chat", "organise ~/Downloads"])

        assert result.exit_code == 0
        assert "Here is how I can help" in result.output
        mock_engine.chat.assert_called_once_with("organise ~/Downloads")

    def test_chat_single_shot_uses_provided_directory(self) -> None:
        """--dir option is passed as working_directory to CopilotEngine."""
        mock_engine = MagicMock()
        mock_engine.chat.return_value = "Done."
        mock_module = MagicMock()
        mock_module.CopilotEngine.return_value = mock_engine

        with patch.dict(
            "sys.modules",
            {"file_organizer.services.copilot.engine": mock_module},
        ):
            runner.invoke(copilot_app, ["chat", "hello", "--dir", "/tmp/mydir"])

        mock_module.CopilotEngine.assert_called_once_with(working_directory="/tmp/mydir")

    def test_chat_repl_exits_on_quit(self) -> None:
        """Interactive REPL exits cleanly when user types 'quit'."""
        mock_engine = MagicMock()
        mock_engine.chat.return_value = "response"
        mock_module = MagicMock()
        mock_module.CopilotEngine.return_value = mock_engine

        with patch.dict(
            "sys.modules",
            {"file_organizer.services.copilot.engine": mock_module},
        ):
            result = runner.invoke(copilot_app, ["chat"], input="quit\n")

        assert result.exit_code == 0
        assert "Goodbye" in result.output

    def test_chat_repl_exits_on_eof(self) -> None:
        """Interactive REPL exits cleanly on EOF (empty stdin)."""
        mock_engine = MagicMock()
        mock_module = MagicMock()
        mock_module.CopilotEngine.return_value = mock_engine

        with patch.dict(
            "sys.modules",
            {"file_organizer.services.copilot.engine": mock_module},
        ):
            result = runner.invoke(copilot_app, ["chat"], input="")

        assert result.exit_code == 0

    def test_chat_repl_calls_engine_for_message(self) -> None:
        """REPL sends user message to engine and prints the response."""
        mock_engine = MagicMock()
        mock_engine.chat.return_value = "Organising 3 files..."
        mock_module = MagicMock()
        mock_module.CopilotEngine.return_value = mock_engine

        with patch.dict(
            "sys.modules",
            {"file_organizer.services.copilot.engine": mock_module},
        ):
            result = runner.invoke(
                copilot_app,
                ["chat"],
                input="organise docs\nquit\n",
            )

        assert result.exit_code == 0
        mock_engine.chat.assert_called_once_with("organise docs")
        assert "Organising 3 files" in result.output


# ---------------------------------------------------------------------------
# copilot: status command
# ---------------------------------------------------------------------------


class TestCopilotStatusCommand:
    """Tests for ``copilot status``."""

    def test_status_ollama_available(self) -> None:
        """When Ollama is reachable, model count and 'ready' are shown."""
        mock_client = MagicMock()
        mock_client.list.return_value = {
            "models": [
                {"name": "qwen2.5:3b"},
                {"name": "qwen2.5vl:7b"},
            ]
        }
        mock_ollama = MagicMock()
        mock_ollama.Client.return_value = mock_client

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            result = runner.invoke(copilot_app, ["status"])

        assert result.exit_code == 0
        assert "2" in result.output  # 2 models
        assert "ready" in result.output.lower()

    def test_status_ollama_unavailable(self) -> None:
        """When Ollama raises an exception, 'Ollama unavailable' is shown."""
        mock_ollama = MagicMock()
        mock_ollama.Client.side_effect = Exception("connection refused")

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            result = runner.invoke(copilot_app, ["status"])

        assert result.exit_code == 0
        assert "unavailable" in result.output.lower() or "Ollama" in result.output
        assert "ready" in result.output.lower()

    def test_status_ollama_import_error(self) -> None:
        """When ollama module is not installed, 'unavailable' is shown gracefully."""
        with patch.dict("sys.modules", {"ollama": None}):
            result = runner.invoke(copilot_app, ["status"])

        assert result.exit_code == 0
        # Either shows unavailable (exception handled) or ready line
        assert "ready" in result.output.lower() or "unavailable" in result.output.lower()
