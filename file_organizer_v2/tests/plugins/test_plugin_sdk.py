"""Unit tests for plugin SDK client and decorators."""
from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from file_organizer.plugins.api.hooks import HookEvent
from file_organizer.plugins.sdk import (
    PluginClient,
    PluginClientAuthError,
    PluginClientError,
    command,
    get_command_metadata,
    get_hook_metadata,
    hook,
)


@hook(HookEvent.FILE_ORGANIZED, priority=7)
@command("sync-index", description="Sync plugin index")
def _sample_handler(_: dict[str, Any]) -> dict[str, bool]:
    return {"ok": True}


def test_decorator_metadata() -> None:
    hook_metadata = get_hook_metadata(_sample_handler)
    command_metadata = get_command_metadata(_sample_handler)
    assert hook_metadata == (HookEvent.FILE_ORGANIZED.value, 7)
    assert command_metadata == ("sync-index", "Sync plugin index")


def test_plugin_client_happy_path() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer token-123"

        if request.url.path == "/api/v1/plugins/files/list":
            return httpx.Response(200, json={"items": [{"name": "demo.txt"}], "total": 1})
        if request.url.path == "/api/v1/plugins/files/metadata":
            return httpx.Response(200, json={"name": "demo.txt", "path": "demo.txt"})
        if request.url.path == "/api/v1/plugins/files/organize":
            payload = json.loads(request.content.decode("utf-8"))
            return httpx.Response(200, json={"moved": not payload["dry_run"]})
        if request.url.path == "/api/v1/plugins/config/get":
            return httpx.Response(200, json={"key": "default_methodology", "value": "para"})
        if request.url.path == "/api/v1/plugins/hooks/register":
            return httpx.Response(200, json={"registered": True})
        if request.url.path == "/api/v1/plugins/hooks":
            return httpx.Response(200, json={"items": []})
        if request.url.path == "/api/v1/plugins/hooks/unregister":
            return httpx.Response(200, json={"removed": True})
        if request.url.path == "/api/v1/plugins/hooks/trigger":
            return httpx.Response(200, json={"delivered": 0, "failed": 0, "results": []})

        return httpx.Response(404, json={"message": "not found"})

    transport = httpx.MockTransport(handler)
    with PluginClient(
        base_url="http://plugins.local",
        token="token-123",
        transport=transport,
    ) as client:
        items = client.list_files(path="./demo")
        assert items == [{"name": "demo.txt"}]

        metadata = client.get_metadata(path="./demo/demo.txt")
        assert metadata["name"] == "demo.txt"

        organize = client.organize_file(
            source_path="./demo/in.txt",
            destination_path="./demo/out.txt",
            dry_run=False,
        )
        assert organize["moved"] is True

        config_value = client.get_config(key="default_methodology")
        assert config_value == "para"

        register = client.register_hook(
            event=HookEvent.FILE_ORGANIZED,
            callback_url="http://localhost:9999/hook",
        )
        assert register["registered"] is True

        assert client.list_hooks() == []
        assert client.unregister_hook(
            event=HookEvent.FILE_ORGANIZED,
            callback_url="http://localhost:9999/hook",
        )
        trigger_payload = client.trigger_event(
            event=HookEvent.FILE_ORGANIZED,
            payload={"source_path": "in", "destination_path": "out"},
        )
        assert trigger_payload["results"] == []


def test_plugin_client_error_paths() -> None:
    def auth_handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"message": "forbidden"})

    auth_client = PluginClient(
        base_url="http://plugins.local",
        token="token-123",
        transport=httpx.MockTransport(auth_handler),
    )
    with pytest.raises(PluginClientAuthError):
        auth_client.list_files(path="./demo")
    auth_client.close()

    def error_handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"message": "boom"})

    error_client = PluginClient(
        base_url="http://plugins.local",
        token="token-123",
        transport=httpx.MockTransport(error_handler),
    )
    with pytest.raises(PluginClientError):
        error_client.get_metadata(path="./demo/demo.txt")
    error_client.close()

    with pytest.raises(ValueError):
        PluginClient(base_url="plugins.local", token="token")
