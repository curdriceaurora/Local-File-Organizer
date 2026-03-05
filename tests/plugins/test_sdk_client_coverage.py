"""Coverage tests for plugins.sdk.client module."""

from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest

from file_organizer.plugins.api.hooks import HookEvent
from file_organizer.plugins.sdk.client import (
    PluginClient,
    PluginClientAuthError,
    PluginClientError,
)

pytestmark = pytest.mark.unit


def _mock_transport(status_code: int = 200, json_body: dict | None = None):
    """Create a mock transport that returns a fixed response."""
    transport = MagicMock(spec=httpx.BaseTransport)
    response = httpx.Response(
        status_code=status_code,
        json=json_body or {},
        request=httpx.Request("GET", "http://test"),
    )
    transport.handle_request.return_value = response
    return transport


class TestPluginClientInit:
    def test_valid_init(self):
        client = PluginClient(base_url="http://localhost:8000", token="abc123")
        client.close()

    def test_invalid_base_url_raises(self):
        with pytest.raises(ValueError, match="http:// or https://"):
            PluginClient(base_url="ftp://bad", token="tok")

    def test_empty_token_raises(self):
        with pytest.raises(ValueError, match="token must not be empty"):
            PluginClient(base_url="http://localhost", token="  ")

    def test_trailing_slash_stripped(self):
        client = PluginClient(base_url="http://localhost:8000///", token="tok")
        client.close()


class TestPluginClientContextManager:
    def test_context_manager(self):
        with PluginClient(base_url="http://localhost", token="tok") as client:
            assert client is not None


class TestPluginClientRequest:
    def test_auth_error_on_401(self):
        transport = _mock_transport(status_code=401)
        client = PluginClient(base_url="http://test", token="tok", transport=transport)
        with pytest.raises(PluginClientAuthError, match="authentication failed"):
            client._request("GET", "/test")
        client.close()

    def test_auth_error_on_403(self):
        transport = _mock_transport(status_code=403)
        client = PluginClient(base_url="http://test", token="tok", transport=transport)
        with pytest.raises(PluginClientAuthError, match="authentication failed"):
            client._request("GET", "/test")
        client.close()

    def test_error_with_json_body(self):
        transport = _mock_transport(status_code=500, json_body={"message": "server down"})
        client = PluginClient(base_url="http://test", token="tok", transport=transport)
        with pytest.raises(PluginClientError, match="server down"):
            client._request("GET", "/test")
        client.close()

    def test_http_error_wraps(self):
        transport = MagicMock(spec=httpx.BaseTransport)
        transport.handle_request.side_effect = httpx.ConnectError("refused")
        client = PluginClient(base_url="http://test", token="tok", transport=transport)
        with pytest.raises(PluginClientError, match="Failed to call"):
            client._request("GET", "/test")
        client.close()

    def test_non_json_response_raises(self):
        transport = MagicMock(spec=httpx.BaseTransport)
        response = httpx.Response(
            status_code=200,
            content=b"not json",
            request=httpx.Request("GET", "http://test"),
        )
        transport.handle_request.return_value = response
        client = PluginClient(base_url="http://test", token="tok", transport=transport)
        with pytest.raises(PluginClientError, match="non-JSON response"):
            client._request("GET", "/test")
        client.close()


class TestPluginClientListFiles:
    def test_valid_response(self):
        transport = _mock_transport(json_body={"items": [{"name": "a.txt"}]})
        client = PluginClient(base_url="http://test", token="tok", transport=transport)
        result = client.list_files(path="/data")
        assert result == [{"name": "a.txt"}]
        client.close()

    def test_non_dict_response_raises(self):
        transport = MagicMock(spec=httpx.BaseTransport)
        response = httpx.Response(
            status_code=200,
            json=[1, 2, 3],
            request=httpx.Request("GET", "http://test"),
        )
        transport.handle_request.return_value = response
        client = PluginClient(base_url="http://test", token="tok", transport=transport)
        with pytest.raises(PluginClientError, match="Unexpected response"):
            client.list_files(path="/data")
        client.close()

    def test_invalid_items_raises(self):
        transport = _mock_transport(json_body={"items": "not-list"})
        client = PluginClient(base_url="http://test", token="tok", transport=transport)
        with pytest.raises(PluginClientError, match="Invalid items"):
            client.list_files(path="/data")
        client.close()


class TestPluginClientGetMetadata:
    def test_valid_response(self):
        transport = _mock_transport(json_body={"name": "file.txt", "size": 100})
        client = PluginClient(base_url="http://test", token="tok", transport=transport)
        result = client.get_metadata(path="/file.txt")
        assert result["name"] == "file.txt"
        client.close()

    def test_non_dict_raises(self):
        transport = MagicMock(spec=httpx.BaseTransport)
        response = httpx.Response(
            status_code=200,
            json=[],
            request=httpx.Request("GET", "http://test"),
        )
        transport.handle_request.return_value = response
        client = PluginClient(base_url="http://test", token="tok", transport=transport)
        with pytest.raises(PluginClientError, match="Unexpected response"):
            client.get_metadata(path="/x")
        client.close()


class TestPluginClientOrganizeFile:
    def test_valid_response(self):
        transport = _mock_transport(json_body={"status": "moved"})
        client = PluginClient(base_url="http://test", token="tok", transport=transport)
        result = client.organize_file(source_path="/a", destination_path="/b")
        assert result["status"] == "moved"
        client.close()


class TestPluginClientGetConfig:
    def test_valid_response(self):
        transport = _mock_transport(json_body={"value": 42})
        client = PluginClient(base_url="http://test", token="tok", transport=transport)
        result = client.get_config(key="setting")
        assert result == 42
        client.close()

    def test_missing_value_raises(self):
        transport = _mock_transport(json_body={"other": "stuff"})
        client = PluginClient(base_url="http://test", token="tok", transport=transport)
        with pytest.raises(PluginClientError, match="Unexpected response"):
            client.get_config(key="setting")
        client.close()


class TestPluginClientHooks:
    def test_register_hook_with_enum(self):
        transport = _mock_transport(json_body={"id": "hook1"})
        client = PluginClient(base_url="http://test", token="tok", transport=transport)
        result = client.register_hook(
            event=HookEvent.FILE_SCANNED,
            callback_url="http://callback",
        )
        assert result["id"] == "hook1"
        client.close()

    def test_register_hook_with_string(self):
        transport = _mock_transport(json_body={"id": "hook2"})
        client = PluginClient(base_url="http://test", token="tok", transport=transport)
        result = client.register_hook(
            event="custom.event",
            callback_url="http://callback",
            secret="s3cret",
        )
        assert result["id"] == "hook2"
        client.close()

    def test_unregister_hook(self):
        transport = _mock_transport(json_body={"removed": True})
        client = PluginClient(base_url="http://test", token="tok", transport=transport)
        result = client.unregister_hook(
            event=HookEvent.FILE_DELETED,
            callback_url="http://cb",
        )
        assert result is True
        client.close()

    def test_list_hooks_with_event(self):
        transport = _mock_transport(json_body={"items": [{"event": "file.scanned"}]})
        client = PluginClient(base_url="http://test", token="tok", transport=transport)
        result = client.list_hooks(event=HookEvent.FILE_SCANNED)
        assert len(result) == 1
        client.close()

    def test_list_hooks_no_filter(self):
        transport = _mock_transport(json_body={"items": []})
        client = PluginClient(base_url="http://test", token="tok", transport=transport)
        result = client.list_hooks()
        assert result == []
        client.close()

    def test_list_hooks_string_event(self):
        transport = _mock_transport(json_body={"items": []})
        client = PluginClient(base_url="http://test", token="tok", transport=transport)
        result = client.list_hooks(event="custom")
        assert result == []
        client.close()

    def test_trigger_event(self):
        transport = _mock_transport(json_body={"delivered": 2})
        client = PluginClient(base_url="http://test", token="tok", transport=transport)
        result = client.trigger_event(
            event=HookEvent.FILE_ORGANIZED,
            payload={"file": "test.txt"},
        )
        assert result["delivered"] == 2
        client.close()
