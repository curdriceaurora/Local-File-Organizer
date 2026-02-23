"""Tests for the ``serve`` CLI command."""

from __future__ import annotations

import re
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from file_organizer.cli.main import app

runner = CliRunner()

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from *text* for portable string assertions."""
    return _ANSI_RE.sub("", text)


def test_serve_help():
    """``serve --help`` exits 0 and documents host/port/reload options."""
    result = runner.invoke(app, ["serve", "--help"])
    assert result.exit_code == 0
    plain = _strip_ansi(result.output)
    assert "--host" in plain
    assert "--port" in plain
    assert "--reload" in plain


def test_serve_registers_in_app():
    """The ``serve`` command is registered on the Typer app."""
    command_names = [cmd.name or cmd.callback.__name__ for cmd in app.registered_commands]
    assert "serve" in command_names


@patch("uvicorn.run")
def test_serve_calls_uvicorn_run(mock_uvicorn_run: MagicMock):
    """Invoking ``serve`` with defaults calls uvicorn.run with expected args."""
    result = runner.invoke(app, ["serve"])
    assert result.exit_code == 0
    mock_uvicorn_run.assert_called_once_with(
        "file_organizer.api.main:create_app",
        factory=True,
        host="0.0.0.0",
        port=8000,
        reload=False,
        workers=1,
    )


@patch("uvicorn.run")
def test_serve_custom_host_port(mock_uvicorn_run: MagicMock):
    """Custom --host and --port values are forwarded to uvicorn."""
    result = runner.invoke(app, ["serve", "--host", "127.0.0.1", "--port", "9000"])
    assert result.exit_code == 0
    mock_uvicorn_run.assert_called_once_with(
        "file_organizer.api.main:create_app",
        factory=True,
        host="127.0.0.1",
        port=9000,
        reload=False,
        workers=1,
    )


@patch("uvicorn.run")
def test_serve_reload_flag(mock_uvicorn_run: MagicMock):
    """--reload is forwarded to uvicorn."""
    result = runner.invoke(app, ["serve", "--reload"])
    assert result.exit_code == 0
    mock_uvicorn_run.assert_called_once_with(
        "file_organizer.api.main:create_app",
        factory=True,
        host="0.0.0.0",
        port=8000,
        reload=True,
        workers=1,
    )


@patch("uvicorn.run")
def test_serve_workers_flag(mock_uvicorn_run: MagicMock):
    """--workers value is forwarded to uvicorn."""
    result = runner.invoke(app, ["serve", "--workers", "4"])
    assert result.exit_code == 0
    mock_uvicorn_run.assert_called_once_with(
        "file_organizer.api.main:create_app",
        factory=True,
        host="0.0.0.0",
        port=8000,
        reload=False,
        workers=4,
    )


@patch("uvicorn.run", side_effect=OSError("Address already in use"))
def test_serve_handles_port_in_use(mock_uvicorn_run: MagicMock):
    """OSError from uvicorn results in exit code 1 with helpful message."""
    result = runner.invoke(app, ["serve"])
    assert result.exit_code == 1
    output_lower = result.stdout.lower()
    assert "port" in output_lower or "address" in output_lower


@patch.dict("sys.modules", {"uvicorn": None})
def test_serve_handles_import_error():
    """Missing uvicorn results in exit code 1 with install instructions."""
    result = runner.invoke(app, ["serve"])
    assert result.exit_code == 1
    assert "uvicorn" in result.stdout.lower()
