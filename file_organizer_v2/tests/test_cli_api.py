"""Tests for API CLI wrapper commands."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from file_organizer.cli.main import app
from file_organizer.client.exceptions import ClientError

runner = CliRunner()


@dataclass
class _Model:
    payload: dict[str, Any]

    def model_dump(self) -> dict[str, Any]:
        return dict(self.payload)

    def __getattr__(self, item: str) -> Any:
        return self.payload[item]


class _FakeClient:
    def health(self) -> _Model:
        return _Model(
            {
                "status": "ok",
                "version": "1.0.0",
                "environment": "test",
            }
        )

    def login(self, _username: str, _password: str) -> _Model:
        return _Model(
            {
                "access_token": "access",
                "refresh_token": "refresh",
                "token_type": "bearer",
            }
        )

    def list_files(
        self,
        _path: str,
        *,
        recursive: bool = False,
        include_hidden: bool = False,
        limit: int = 100,
    ) -> _Model:
        _ = (recursive, include_hidden, limit)
        return _Model(
            {
                "total": 1,
                "items": [type("File", (), {"name": "a.txt", "file_type": "text", "size": 5})()],
            }
        )

    def system_stats(
        self,
        *,
        path: str,
        max_depth: int | None = None,
        use_cache: bool = True,
    ) -> _Model:
        _ = (path, max_depth, use_cache)
        return _Model(
            {
                "file_count": 3,
                "directory_count": 1,
                "total_size": 42,
            }
        )

    def close(self) -> None:
        return None


def test_api_help() -> None:
    result = runner.invoke(app, ["api", "--help"])
    assert result.exit_code == 0
    assert "Remote API operations" in result.stdout


def test_api_health(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("file_organizer.cli.api._build_client", lambda **_: _FakeClient())
    result = runner.invoke(app, ["api", "health"])
    assert result.exit_code == 0
    assert "Status:" in result.stdout


def test_api_login_json_and_save_token(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("file_organizer.cli.api._build_client", lambda **_: _FakeClient())
    token_file = tmp_path / "tokens.json"
    result = runner.invoke(
        app,
        [
            "api",
            "login",
            "--username",
            "user",
            "--password",
            "pass",
            "--save-token",
            str(token_file),
            "--json",
        ],
    )
    assert result.exit_code == 0
    assert token_file.exists()
    assert "access_token" in token_file.read_text(encoding="utf-8")


def test_api_error_exit_code(monkeypatch: pytest.MonkeyPatch) -> None:
    class _ErrorClient(_FakeClient):
        def health(self) -> _Model:
            raise ClientError("boom", status_code=500)

    monkeypatch.setattr("file_organizer.cli.api._build_client", lambda **_: _ErrorClient())
    result = runner.invoke(app, ["api", "health"])
    assert result.exit_code == 1
    assert "API error" in result.stdout
