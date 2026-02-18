"""Integration tests for plugin API endpoints."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from file_organizer.api.test_utils import create_auth_client
from file_organizer.plugins.api import endpoints
from file_organizer.plugins.api.hooks import PluginHookManager

pytestmark = pytest.mark.ci


class _FakeResponse:
    def __init__(self, status_code: int = 200, text: str = "ok") -> None:
        self.status_code = status_code
        self.text = text

    @property
    def is_success(self) -> bool:
        return 200 <= self.status_code < 300


class _FakeHttpClient:
    def __init__(self, sink: list[dict[str, Any]]) -> None:
        self._sink = sink

    def __enter__(self) -> _FakeHttpClient:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def post(
        self,
        url: str,
        *,
        json: dict[str, Any],
        headers: dict[str, str],
        timeout: float,
    ) -> _FakeResponse:
        self._sink.append(
            {
                "url": url,
                "json": json,
                "headers": headers,
                "timeout": timeout,
            }
        )
        return _FakeResponse(status_code=202)


def _client(tmp_path: Path, allowed_paths: list[str]) -> tuple[TestClient, dict[str, str]]:
    client, headers, _ = create_auth_client(tmp_path, allowed_paths=allowed_paths)
    return client, headers


def test_plugin_files_metadata_and_organize(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    source = data_dir / "source.txt"
    source.write_text("content", encoding="utf-8")

    client, headers = _client(tmp_path, [str(data_dir)])

    list_resp = client.get(
        "/api/v1/plugins/files/list",
        params={"path": str(data_dir), "recursive": False},
        headers=headers,
    )
    assert list_resp.status_code == 200
    assert list_resp.json()["total"] == 1

    metadata_resp = client.get(
        "/api/v1/plugins/files/metadata",
        params={"path": str(source)},
        headers=headers,
    )
    assert metadata_resp.status_code == 200
    assert metadata_resp.json()["name"] == "source.txt"

    destination = data_dir / "organized" / "source.txt"
    dry_run_resp = client.post(
        "/api/v1/plugins/files/organize",
        json={
            "source_path": str(source),
            "destination_path": str(destination),
            "dry_run": True,
            "overwrite": False,
        },
        headers=headers,
    )
    assert dry_run_resp.status_code == 200
    assert dry_run_resp.json()["dry_run"] is True
    assert source.exists()

    move_resp = client.post(
        "/api/v1/plugins/files/organize",
        json={
            "source_path": str(source),
            "destination_path": str(destination),
            "dry_run": False,
            "overwrite": False,
        },
        headers=headers,
    )
    assert move_resp.status_code == 200
    assert move_resp.json()["moved"] is True
    assert destination.exists()


def test_plugin_config_get(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    client, headers = _client(tmp_path, [str(data_dir)])
    resp = client.get(
        "/api/v1/plugins/config/get",
        params={"key": "default_methodology"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["key"] == "default_methodology"


def test_plugin_hooks_register_list_trigger_unregister(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    client, headers = _client(tmp_path, [str(data_dir)])

    outbound_calls: list[dict[str, Any]] = []
    hook_manager = PluginHookManager(http_client_factory=lambda: _FakeHttpClient(outbound_calls))
    client.app.dependency_overrides[endpoints.get_hook_manager] = lambda: hook_manager

    try:
        register_resp = client.post(
            "/api/v1/plugins/hooks/register",
            json={
                "event": "file.organized",
                "callback_url": "http://localhost:9999/plugin-hook",
            },
            headers=headers,
        )
        assert register_resp.status_code == 200

        list_resp = client.get("/api/v1/plugins/hooks", headers=headers)
        assert list_resp.status_code == 200
        assert len(list_resp.json()["items"]) == 1

        trigger_resp = client.post(
            "/api/v1/plugins/hooks/trigger",
            json={
                "event": "file.organized",
                "payload": {"source_path": "in.txt", "destination_path": "out.txt"},
            },
            headers=headers,
        )
        assert trigger_resp.status_code == 200
        payload = trigger_resp.json()
        assert payload["delivered"] == 1
        assert payload["failed"] == 0
        assert len(outbound_calls) == 1
        assert outbound_calls[0]["json"]["payload"]["triggered_by"]

        unregister_resp = client.post(
            "/api/v1/plugins/hooks/unregister",
            json={
                "event": "file.organized",
                "callback_url": "http://localhost:9999/plugin-hook",
            },
            headers=headers,
        )
        assert unregister_resp.status_code == 200
        assert unregister_resp.json()["removed"] is True

        post_list = client.get("/api/v1/plugins/hooks", headers=headers)
        assert post_list.status_code == 200
        assert post_list.json()["items"] == []
    finally:
        client.app.dependency_overrides.clear()


def test_plugin_hook_register_rejects_invalid_callback(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    client, headers = _client(tmp_path, [str(data_dir)])

    register_resp = client.post(
        "/api/v1/plugins/hooks/register",
        json={
            "event": "file.organized",
            "callback_url": "not-a-valid-url",
        },
        headers=headers,
    )
    assert register_resp.status_code == 400
