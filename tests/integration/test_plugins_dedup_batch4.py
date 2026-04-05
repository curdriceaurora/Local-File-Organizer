"""Integration tests for plugin executor, SDK client, marketplace metadata,
and deduplication detector/document modules.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.ci]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_package_dict(**overrides: Any) -> dict[str, Any]:
    """Return a valid PluginPackage payload dict."""
    base: dict[str, Any] = {
        "name": "my-plugin",
        "version": "1.0.0",
        "author": "Test Author",
        "description": "A test plugin",
        "download_url": "https://example.com/my-plugin-1.0.0.tar.gz",
        "checksum_sha256": "a" * 64,
        "size_bytes": 1024,
    }
    base.update(overrides)
    return base


def _assert_bearer_auth(request: httpx.Request, token: str = "tok") -> None:
    assert request.headers["Authorization"] == f"Bearer {token}"


# ---------------------------------------------------------------------------
# TestPluginExecutor
# ---------------------------------------------------------------------------


class TestPluginExecutor:
    """Tests for PluginExecutor (plugins/executor.py)."""

    def test_init_default_name_from_path(self, tmp_path: Path) -> None:
        from file_organizer.plugins.executor import PluginExecutor

        plugin_file = tmp_path / "my_plugin.py"
        plugin_file.write_text("# dummy")
        executor = PluginExecutor(plugin_path=plugin_file)
        assert executor._plugin_name == "my_plugin"

    def test_init_explicit_name(self, tmp_path: Path) -> None:
        from file_organizer.plugins.executor import PluginExecutor

        plugin_file = tmp_path / "my_plugin.py"
        plugin_file.write_text("# dummy")
        executor = PluginExecutor(plugin_path=plugin_file, plugin_name="custom_name")
        assert executor._plugin_name == "custom_name"

    def test_init_default_policy_unrestricted(self, tmp_path: Path) -> None:
        from file_organizer.plugins.executor import PluginExecutor

        plugin_file = tmp_path / "my_plugin.py"
        plugin_file.write_text("# dummy")
        executor = PluginExecutor(plugin_path=plugin_file)
        assert executor._policy.allow_all_paths is True
        assert executor._policy.allow_all_operations is True

    def test_init_custom_policy(self, tmp_path: Path) -> None:
        from file_organizer.plugins.executor import PluginExecutor
        from file_organizer.plugins.security import PluginSecurityPolicy

        plugin_file = tmp_path / "my_plugin.py"
        plugin_file.write_text("# dummy")
        policy = PluginSecurityPolicy.from_permissions(allowed_operations=["read"])
        executor = PluginExecutor(plugin_path=plugin_file, policy=policy)
        assert executor._policy is policy

    def test_init_proc_is_none_before_start(self, tmp_path: Path) -> None:
        from file_organizer.plugins.executor import PluginExecutor

        plugin_file = tmp_path / "my_plugin.py"
        plugin_file.write_text("# dummy")
        executor = PluginExecutor(plugin_path=plugin_file)
        assert executor._proc is None

    def test_start_sets_proc(self, tmp_path: Path) -> None:
        from file_organizer.plugins.executor import PluginExecutor

        plugin_file = tmp_path / "my_plugin.py"
        plugin_file.write_text("# dummy")
        executor = PluginExecutor(plugin_path=plugin_file)
        with patch("subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_popen.return_value = mock_proc
            executor.start()
        assert executor._proc is mock_proc

    def test_start_idempotent(self, tmp_path: Path) -> None:
        from file_organizer.plugins.executor import PluginExecutor

        plugin_file = tmp_path / "my_plugin.py"
        plugin_file.write_text("# dummy")
        executor = PluginExecutor(plugin_path=plugin_file)
        with patch("subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_popen.return_value = mock_proc
            executor.start()
            executor.start()  # second call should be no-op
        assert mock_popen.call_count == 1

    def test_start_raises_plugin_load_error_on_oserror(self, tmp_path: Path) -> None:
        from file_organizer.plugins.errors import PluginLoadError
        from file_organizer.plugins.executor import PluginExecutor

        plugin_file = tmp_path / "my_plugin.py"
        plugin_file.write_text("# dummy")
        executor = PluginExecutor(plugin_path=plugin_file)
        with patch("subprocess.Popen", side_effect=OSError("no such file")):
            with pytest.raises(PluginLoadError, match="Failed to spawn worker"):
                executor.start()

    def test_stop_when_not_started_is_noop(self, tmp_path: Path) -> None:
        from file_organizer.plugins.executor import PluginExecutor

        plugin_file = tmp_path / "my_plugin.py"
        plugin_file.write_text("# dummy")
        executor = PluginExecutor(plugin_path=plugin_file)
        executor.stop()  # Must not raise
        assert executor._proc is None

    def test_stop_terminates_process(self, tmp_path: Path) -> None:
        from file_organizer.plugins.executor import PluginExecutor

        plugin_file = tmp_path / "my_plugin.py"
        plugin_file.write_text("# dummy")
        executor = PluginExecutor(plugin_path=plugin_file)
        mock_proc = MagicMock()
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = MagicMock()
        mock_proc.stderr = MagicMock()
        executor._proc = mock_proc
        executor.stop()
        mock_proc.terminate.assert_called_once()
        assert executor._proc is None

    def test_stop_kills_on_timeout(self, tmp_path: Path) -> None:
        import subprocess

        from file_organizer.plugins.executor import PluginExecutor

        plugin_file = tmp_path / "my_plugin.py"
        plugin_file.write_text("# dummy")
        executor = PluginExecutor(plugin_path=plugin_file)
        mock_proc = MagicMock()
        mock_proc.stdin = None
        mock_proc.stdout = None
        mock_proc.stderr = None
        # First wait call raises TimeoutExpired; second (after kill) succeeds
        mock_proc.wait.side_effect = [
            subprocess.TimeoutExpired(cmd="x", timeout=5),
            None,
        ]
        executor._proc = mock_proc
        executor.stop()
        mock_proc.kill.assert_called_once()
        assert executor._proc is None

    def test_context_manager_start_and_stop(self, tmp_path: Path) -> None:
        from file_organizer.plugins.executor import PluginExecutor

        plugin_file = tmp_path / "my_plugin.py"
        plugin_file.write_text("# dummy")
        executor = PluginExecutor(plugin_path=plugin_file)
        with patch("subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.stdin = None
            mock_proc.stdout = None
            mock_proc.stderr = None
            mock_proc.wait.return_value = 0
            mock_popen.return_value = mock_proc
            with executor as ex:
                assert ex is executor
                assert executor._proc is not None
        assert executor._proc is None

    def test_call_raises_runtime_error_when_not_started(self, tmp_path: Path) -> None:
        from file_organizer.plugins.executor import PluginExecutor

        plugin_file = tmp_path / "my_plugin.py"
        plugin_file.write_text("# dummy")
        executor = PluginExecutor(plugin_path=plugin_file)
        with pytest.raises(RuntimeError, match="not started"):
            executor.call("some_method")

    def test_call_raises_plugin_error_when_pipes_closed(self, tmp_path: Path) -> None:
        from file_organizer.plugins.errors import PluginError
        from file_organizer.plugins.executor import PluginExecutor

        plugin_file = tmp_path / "my_plugin.py"
        plugin_file.write_text("# dummy")
        executor = PluginExecutor(plugin_path=plugin_file)
        mock_proc = MagicMock()
        mock_proc.stdin = None
        mock_proc.stdout = None
        executor._proc = mock_proc
        with pytest.raises(PluginError, match="unexpectedly closed"):
            executor.call("some_method")

    def test_call_raises_plugin_error_on_broken_pipe(self, tmp_path: Path) -> None:
        from file_organizer.plugins.errors import PluginError
        from file_organizer.plugins.executor import PluginExecutor

        plugin_file = tmp_path / "my_plugin.py"
        plugin_file.write_text("# dummy")
        executor = PluginExecutor(plugin_path=plugin_file)
        mock_proc = MagicMock()
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = MagicMock()
        mock_proc.stdin.write.side_effect = BrokenPipeError("broken pipe")
        executor._proc = mock_proc
        with pytest.raises(PluginError, match="died before receiving"):
            executor.call("some_method")

    def test_call_raises_plugin_error_on_empty_response(self, tmp_path: Path) -> None:
        from file_organizer.plugins.errors import PluginError
        from file_organizer.plugins.executor import PluginExecutor

        plugin_file = tmp_path / "my_plugin.py"
        plugin_file.write_text("# dummy")
        executor = PluginExecutor(plugin_path=plugin_file)
        mock_proc = MagicMock()
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = MagicMock()
        mock_proc.stderr = MagicMock()
        mock_proc.stderr.read.return_value = b"some error"
        executor._proc = mock_proc

        with patch.object(executor, "_readline_with_timeout", return_value=b""):
            with pytest.raises(PluginError, match="closed stdout"):
                executor.call("some_method")

    def test_call_returns_return_value_on_success(self, tmp_path: Path) -> None:
        from file_organizer.plugins.executor import PluginExecutor
        from file_organizer.plugins.ipc import PluginResult, encode_result

        plugin_file = tmp_path / "my_plugin.py"
        plugin_file.write_text("# dummy")
        executor = PluginExecutor(plugin_path=plugin_file)
        mock_proc = MagicMock()
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = MagicMock()
        executor._proc = mock_proc

        result = PluginResult(success=True, return_value={"key": "value"})
        raw_line = encode_result(result)

        with patch.object(executor, "_readline_with_timeout", return_value=raw_line):
            ret = executor.call("some_method")
        assert ret == {"key": "value"}

    def test_call_raises_plugin_error_on_error_result(self, tmp_path: Path) -> None:
        from file_organizer.plugins.errors import PluginError
        from file_organizer.plugins.executor import PluginExecutor
        from file_organizer.plugins.ipc import PluginResult, encode_result

        plugin_file = tmp_path / "my_plugin.py"
        plugin_file.write_text("# dummy")
        executor = PluginExecutor(plugin_path=plugin_file)
        mock_proc = MagicMock()
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = MagicMock()
        executor._proc = mock_proc

        result = PluginResult(success=False, error="Something went wrong")
        raw_line = encode_result(result)

        with patch.object(executor, "_readline_with_timeout", return_value=raw_line):
            with pytest.raises(PluginError, match="raised an error"):
                executor.call("some_method")

    def test_call_on_load_raises_plugin_load_error(self, tmp_path: Path) -> None:
        from file_organizer.plugins.errors import PluginLoadError
        from file_organizer.plugins.executor import PluginExecutor
        from file_organizer.plugins.ipc import PluginResult, encode_result

        plugin_file = tmp_path / "my_plugin.py"
        plugin_file.write_text("# dummy")
        executor = PluginExecutor(plugin_path=plugin_file)
        mock_proc = MagicMock()
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = MagicMock()
        executor._proc = mock_proc

        result = PluginResult(success=False, error="Load failure")
        raw_line = encode_result(result)

        with patch.object(executor, "_readline_with_timeout", return_value=raw_line):
            with pytest.raises(PluginLoadError, match="Load failure"):
                executor.call("on_load")

    def test_call_raises_plugin_error_on_corrupt_ipc(self, tmp_path: Path) -> None:
        from file_organizer.plugins.errors import PluginError
        from file_organizer.plugins.executor import PluginExecutor

        plugin_file = tmp_path / "my_plugin.py"
        plugin_file.write_text("# dummy")
        executor = PluginExecutor(plugin_path=plugin_file)
        mock_proc = MagicMock()
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = MagicMock()
        executor._proc = mock_proc

        with patch.object(executor, "_readline_with_timeout", return_value=b"not valid json\n"):
            with pytest.raises(PluginError, match="Corrupt IPC"):
                executor.call("some_method")

    def test_readline_with_timeout_raises_when_no_proc(self, tmp_path: Path) -> None:
        from file_organizer.plugins.errors import PluginError
        from file_organizer.plugins.executor import PluginExecutor

        plugin_file = tmp_path / "my_plugin.py"
        plugin_file.write_text("# dummy")
        executor = PluginExecutor(plugin_path=plugin_file)
        with pytest.raises(PluginError, match="not running"):
            executor._readline_with_timeout()

    def test_plugin_path_stored_as_path_object(self, tmp_path: Path) -> None:
        from file_organizer.plugins.executor import PluginExecutor

        plugin_file = tmp_path / "my_plugin.py"
        plugin_file.write_text("# dummy")
        executor = PluginExecutor(plugin_path=str(plugin_file))
        assert isinstance(executor._plugin_path, Path)
        assert executor._plugin_path == plugin_file


# ---------------------------------------------------------------------------
# TestPluginClient
# ---------------------------------------------------------------------------


class TestPluginClient:
    """Tests for PluginClient (plugins/sdk/client.py)."""

    def _make_client(self, transport: Any = None) -> Any:
        from file_organizer.plugins.sdk.client import PluginClient

        return PluginClient(
            base_url="http://localhost:8000",
            token="test-token",
            transport=transport,
        )

    def test_init_rejects_invalid_scheme(self) -> None:
        from file_organizer.plugins.sdk.client import PluginClient

        with pytest.raises(ValueError, match="http:// or https://"):
            PluginClient(base_url="ftp://example.com", token="tok")

    def test_init_rejects_empty_token(self) -> None:
        from file_organizer.plugins.sdk.client import PluginClient

        with pytest.raises(ValueError, match="token must not be empty"):
            PluginClient(base_url="https://example.com", token="   ")

    def test_init_strips_trailing_slash(self) -> None:
        from file_organizer.plugins.sdk.client import PluginClient

        client = PluginClient(
            base_url="https://example.com/api/",
            token="tok",
            transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})),
        )
        assert client._client.base_url.path.rstrip("/") in ("", "/api", "/api/")
        client.close()

    def test_context_manager_closes_client(self) -> None:
        from file_organizer.plugins.sdk.client import PluginClient

        transport = httpx.MockTransport(lambda r: httpx.Response(200, json={}))
        client = PluginClient(base_url="https://example.com", token="tok", transport=transport)
        with client as c:
            assert c is client
        # close() must succeed without error — no exception raised

    def test_list_files_happy_path(self) -> None:
        from file_organizer.plugins.sdk.client import PluginClient

        items = [{"name": "file.txt", "path": "/data/file.txt"}]
        response_payload = {"items": items}

        def handler(request: httpx.Request) -> httpx.Response:
            _assert_bearer_auth(request)
            assert request.method == "GET"
            assert request.url.path == "/api/v1/plugins/files/list"
            assert request.url.params["path"] == "/data"
            assert request.url.params["recursive"] == "false"
            assert request.url.params["include_hidden"] == "false"
            assert request.url.params["max_items"] == "200"
            return httpx.Response(200, json=response_payload)

        client = PluginClient(
            base_url="http://localhost:8000",
            token="tok",
            transport=httpx.MockTransport(handler),
        )
        result = client.list_files(path="/data")
        assert result == items
        client.close()

    def test_list_files_raises_on_non_dict_response(self) -> None:
        from file_organizer.plugins.sdk.client import PluginClient, PluginClientError

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=["not", "a", "dict"])

        client = PluginClient(
            base_url="http://localhost:8000",
            token="tok",
            transport=httpx.MockTransport(handler),
        )
        with pytest.raises(PluginClientError, match="Unexpected response shape"):
            client.list_files(path="/data")
        client.close()

    def test_list_files_raises_on_invalid_items(self) -> None:
        from file_organizer.plugins.sdk.client import PluginClient, PluginClientError

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"items": "not-a-list"})

        client = PluginClient(
            base_url="http://localhost:8000",
            token="tok",
            transport=httpx.MockTransport(handler),
        )
        with pytest.raises(PluginClientError, match="Invalid items payload"):
            client.list_files(path="/data")
        client.close()

    def test_list_files_filters_non_dict_items(self) -> None:
        from file_organizer.plugins.sdk.client import PluginClient

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"items": [{"name": "ok"}, "bad", 42]})

        client = PluginClient(
            base_url="http://localhost:8000",
            token="tok",
            transport=httpx.MockTransport(handler),
        )
        result = client.list_files(path="/data")
        assert len(result) == 1
        assert result[0] == {"name": "ok"}
        client.close()

    def test_get_metadata_happy_path(self) -> None:
        from file_organizer.plugins.sdk.client import PluginClient

        meta = {"name": "file.txt", "size": 100}

        def handler(request: httpx.Request) -> httpx.Response:
            _assert_bearer_auth(request)
            assert request.method == "GET"
            assert request.url.path == "/api/v1/plugins/files/metadata"
            assert request.url.params["path"] == "/data/file.txt"
            return httpx.Response(200, json=meta)

        client = PluginClient(
            base_url="http://localhost:8000",
            token="tok",
            transport=httpx.MockTransport(handler),
        )
        result = client.get_metadata(path="/data/file.txt")
        assert result == meta
        client.close()

    def test_get_metadata_raises_on_non_dict(self) -> None:
        from file_organizer.plugins.sdk.client import PluginClient, PluginClientError

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=["list"])

        client = PluginClient(
            base_url="http://localhost:8000",
            token="tok",
            transport=httpx.MockTransport(handler),
        )
        with pytest.raises(PluginClientError, match="Unexpected response shape"):
            client.get_metadata(path="/data/file.txt")
        client.close()

    def test_organize_file_happy_path(self) -> None:
        from file_organizer.plugins.sdk.client import PluginClient

        resp = {"moved": True, "destination": "/dest/file.txt"}

        def handler(request: httpx.Request) -> httpx.Response:
            _assert_bearer_auth(request)
            assert request.method == "POST"
            assert request.url.path == "/api/v1/plugins/files/organize"
            assert json.loads(request.content.decode()) == {
                "source_path": "/data/file.txt",
                "destination_path": "/dest/file.txt",
                "overwrite": False,
                "dry_run": False,
            }
            return httpx.Response(200, json=resp)

        client = PluginClient(
            base_url="http://localhost:8000",
            token="tok",
            transport=httpx.MockTransport(handler),
        )
        result = client.organize_file(
            source_path="/data/file.txt", destination_path="/dest/file.txt"
        )
        assert result == resp
        client.close()

    def test_get_config_happy_path(self) -> None:
        from file_organizer.plugins.sdk.client import PluginClient

        def handler(request: httpx.Request) -> httpx.Response:
            _assert_bearer_auth(request)
            assert request.method == "GET"
            assert request.url.path == "/api/v1/plugins/config/get"
            assert request.url.params["key"] == "some_key"
            assert request.url.params["profile"] == "default"
            return httpx.Response(200, json={"value": "my-setting"})

        client = PluginClient(
            base_url="http://localhost:8000",
            token="tok",
            transport=httpx.MockTransport(handler),
        )
        result = client.get_config(key="some_key")
        assert result == "my-setting"
        client.close()

    def test_get_config_raises_on_missing_value(self) -> None:
        from file_organizer.plugins.sdk.client import PluginClient, PluginClientError

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"other": "stuff"})

        client = PluginClient(
            base_url="http://localhost:8000",
            token="tok",
            transport=httpx.MockTransport(handler),
        )
        with pytest.raises(PluginClientError, match="Unexpected response shape"):
            client.get_config(key="some_key")
        client.close()

    def test_register_hook_happy_path(self) -> None:
        from file_organizer.plugins.api.hooks import HookEvent
        from file_organizer.plugins.sdk.client import PluginClient

        resp = {"id": "reg-123", "event": "file.scanned"}

        def handler(request: httpx.Request) -> httpx.Response:
            _assert_bearer_auth(request)
            assert request.method == "POST"
            assert request.url.path == "/api/v1/plugins/hooks/register"
            assert json.loads(request.content.decode()) == {
                "event": "file.scanned",
                "callback_url": "http://cb.example.com/hook",
                "secret": None,
            }
            return httpx.Response(200, json=resp)

        client = PluginClient(
            base_url="http://localhost:8000",
            token="tok",
            transport=httpx.MockTransport(handler),
        )
        result = client.register_hook(
            event=HookEvent.FILE_SCANNED, callback_url="http://cb.example.com/hook"
        )
        assert result == resp
        client.close()

    def test_register_hook_with_string_event(self) -> None:
        from file_organizer.plugins.sdk.client import PluginClient

        resp = {"id": "reg-456"}

        def handler(request: httpx.Request) -> httpx.Response:
            _assert_bearer_auth(request)
            assert request.method == "POST"
            assert request.url.path == "/api/v1/plugins/hooks/register"
            assert json.loads(request.content.decode()) == {
                "event": "custom.event",
                "callback_url": "http://cb.example.com",
                "secret": None,
            }
            return httpx.Response(200, json=resp)

        client = PluginClient(
            base_url="http://localhost:8000",
            token="tok",
            transport=httpx.MockTransport(handler),
        )
        result = client.register_hook(event="custom.event", callback_url="http://cb.example.com")
        assert result == resp
        client.close()

    def test_unregister_hook_returns_true(self) -> None:
        from file_organizer.plugins.api.hooks import HookEvent
        from file_organizer.plugins.sdk.client import PluginClient

        def handler(request: httpx.Request) -> httpx.Response:
            _assert_bearer_auth(request)
            assert request.method == "POST"
            assert request.url.path == "/api/v1/plugins/hooks/unregister"
            assert json.loads(request.content.decode()) == {
                "event": "file.scanned",
                "callback_url": "http://cb.example.com/hook",
            }
            return httpx.Response(200, json={"removed": True})

        client = PluginClient(
            base_url="http://localhost:8000",
            token="tok",
            transport=httpx.MockTransport(handler),
        )
        result = client.unregister_hook(
            event=HookEvent.FILE_SCANNED, callback_url="http://cb.example.com/hook"
        )
        assert result is True
        client.close()

    def test_unregister_hook_returns_false_when_not_removed(self) -> None:
        from file_organizer.plugins.api.hooks import HookEvent
        from file_organizer.plugins.sdk.client import PluginClient

        def handler(request: httpx.Request) -> httpx.Response:
            _assert_bearer_auth(request)
            assert request.method == "POST"
            assert request.url.path == "/api/v1/plugins/hooks/unregister"
            assert json.loads(request.content.decode()) == {
                "event": "file.scanned",
                "callback_url": "http://cb.example.com/hook",
            }
            return httpx.Response(200, json={"removed": False})

        client = PluginClient(
            base_url="http://localhost:8000",
            token="tok",
            transport=httpx.MockTransport(handler),
        )
        result = client.unregister_hook(
            event=HookEvent.FILE_SCANNED, callback_url="http://cb.example.com/hook"
        )
        assert result is False
        client.close()

    def test_list_hooks_happy_path(self) -> None:
        from file_organizer.plugins.api.hooks import HookEvent
        from file_organizer.plugins.sdk.client import PluginClient

        items = [{"id": "h1", "event": "file.scanned"}]

        def handler(request: httpx.Request) -> httpx.Response:
            _assert_bearer_auth(request)
            assert request.method == "GET"
            assert request.url.path == "/api/v1/plugins/hooks"
            assert request.url.params["event"] == "file.scanned"
            return httpx.Response(200, json={"items": items})

        client = PluginClient(
            base_url="http://localhost:8000",
            token="tok",
            transport=httpx.MockTransport(handler),
        )
        result = client.list_hooks(event=HookEvent.FILE_SCANNED)
        assert len(result) == 1
        assert result[0] == items[0]
        client.close()

    def test_list_hooks_with_no_event_filter(self) -> None:
        from file_organizer.plugins.sdk.client import PluginClient

        items = [{"id": "h1"}, {"id": "h2"}]

        def handler(request: httpx.Request) -> httpx.Response:
            _assert_bearer_auth(request)
            assert request.method == "GET"
            assert request.url.path == "/api/v1/plugins/hooks"
            assert "event" not in request.url.params
            return httpx.Response(200, json={"items": items})

        client = PluginClient(
            base_url="http://localhost:8000",
            token="tok",
            transport=httpx.MockTransport(handler),
        )
        result = client.list_hooks()
        assert len(result) == 2
        client.close()

    def test_trigger_event_happy_path(self) -> None:
        from file_organizer.plugins.api.hooks import HookEvent
        from file_organizer.plugins.sdk.client import PluginClient

        resp = {"delivered": 1, "failed": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            _assert_bearer_auth(request)
            assert request.method == "POST"
            assert request.url.path == "/api/v1/plugins/hooks/trigger"
            assert json.loads(request.content.decode()) == {
                "event": "file.scanned",
                "payload": {"path": "/f.txt"},
            }
            return httpx.Response(200, json=resp)

        client = PluginClient(
            base_url="http://localhost:8000",
            token="tok",
            transport=httpx.MockTransport(handler),
        )
        result = client.trigger_event(event=HookEvent.FILE_SCANNED, payload={"path": "/f.txt"})
        assert result == resp
        client.close()

    def test_request_raises_plugin_client_error_on_http_error(self) -> None:
        from file_organizer.plugins.sdk.client import PluginClient, PluginClientError

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused")

        client = PluginClient(
            base_url="http://localhost:8000",
            token="tok",
            transport=httpx.MockTransport(handler),
        )
        with pytest.raises(PluginClientError, match="Failed to call plugin API"):
            client.list_files(path="/data")
        client.close()

    def test_request_raises_auth_error_on_401(self) -> None:
        from file_organizer.plugins.sdk.client import PluginClient, PluginClientAuthError

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401)

        client = PluginClient(
            base_url="http://localhost:8000",
            token="tok",
            transport=httpx.MockTransport(handler),
        )
        with pytest.raises(PluginClientAuthError, match="authentication failed"):
            client.list_files(path="/data")
        client.close()

    def test_request_raises_auth_error_on_403(self) -> None:
        from file_organizer.plugins.sdk.client import PluginClient, PluginClientAuthError

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(403)

        client = PluginClient(
            base_url="http://localhost:8000",
            token="tok",
            transport=httpx.MockTransport(handler),
        )
        with pytest.raises(PluginClientAuthError, match="authentication failed"):
            client.get_metadata(path="/x")
        client.close()

    def test_request_raises_plugin_client_error_on_500(self) -> None:
        from file_organizer.plugins.sdk.client import PluginClient, PluginClientError

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"message": "internal error"})

        client = PluginClient(
            base_url="http://localhost:8000",
            token="tok",
            transport=httpx.MockTransport(handler),
        )
        with pytest.raises(PluginClientError, match="request failed"):
            client.list_files(path="/data")
        client.close()

    def test_request_raises_on_non_json_success_response(self) -> None:
        from file_organizer.plugins.sdk.client import PluginClient, PluginClientError

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"not json", headers={"content-type": "text/plain"})

        client = PluginClient(
            base_url="http://localhost:8000",
            token="tok",
            transport=httpx.MockTransport(handler),
        )
        with pytest.raises(PluginClientError, match="non-JSON response"):
            client.get_metadata(path="/x")
        client.close()


# ---------------------------------------------------------------------------
# TestPluginMetadataStore
# ---------------------------------------------------------------------------


class TestPluginMetadataStore:
    """Tests for PluginMetadataStore (plugins/marketplace/metadata.py)."""

    def _make_store(self, tmp_path: Path) -> Any:
        from file_organizer.plugins.marketplace.metadata import PluginMetadataStore

        return PluginMetadataStore(db_path=tmp_path / "metadata.json")

    def _make_package(self, **overrides: Any) -> Any:
        from file_organizer.plugins.marketplace.models import PluginPackage

        return PluginPackage.from_dict(_make_package_dict(**overrides))

    def test_list_all_empty_when_no_db(self, tmp_path: Path) -> None:
        store = self._make_store(tmp_path)
        result = store.list_all()
        assert result == []

    def test_sync_and_list_all_roundtrip(self, tmp_path: Path) -> None:
        store = self._make_store(tmp_path)
        pkg = self._make_package(name="alpha-plugin", version="1.0.0")
        store.sync([pkg])
        result = store.list_all()
        assert len(result) == 1
        assert result[0].name == "alpha-plugin"

    def test_sync_replaces_existing_data(self, tmp_path: Path) -> None:
        store = self._make_store(tmp_path)
        pkg1 = self._make_package(name="alpha-plugin", version="1.0.0")
        store.sync([pkg1])
        pkg2 = self._make_package(name="beta-plugin", version="2.0.0")
        store.sync([pkg2])
        result = store.list_all()
        assert len(result) == 1
        assert result[0].name == "beta-plugin"

    def test_list_all_sorted_by_name_then_version(self, tmp_path: Path) -> None:
        store = self._make_store(tmp_path)
        pkgB = self._make_package(name="beta-plugin", version="1.0.0")
        pkgA2 = self._make_package(name="alpha-plugin", version="2.0.0")
        pkgA1 = self._make_package(name="alpha-plugin", version="1.0.0")
        store.sync([pkgB, pkgA2, pkgA1])
        result = store.list_all()
        assert result[0].name == "alpha-plugin"
        assert result[0].version == "1.0.0"
        assert result[1].name == "alpha-plugin"
        assert result[1].version == "2.0.0"
        assert result[2].name == "beta-plugin"

    def test_get_plugin_returns_none_for_missing(self, tmp_path: Path) -> None:
        store = self._make_store(tmp_path)
        store.sync([])
        result = store.get_plugin("nonexistent")
        assert result is None

    def test_get_plugin_returns_none_for_blank_name(self, tmp_path: Path) -> None:
        store = self._make_store(tmp_path)
        result = store.get_plugin("   ")
        assert result is None

    def test_get_plugin_returns_newest_version(self, tmp_path: Path) -> None:
        store = self._make_store(tmp_path)
        pkg1 = self._make_package(name="my-plugin", version="1.0.0")
        pkg2 = self._make_package(name="my-plugin", version="2.0.0")
        store.sync([pkg1, pkg2])
        result = store.get_plugin("my-plugin")
        assert result is not None
        assert result.version == "2.0.0"

    def test_get_plugin_case_insensitive(self, tmp_path: Path) -> None:
        store = self._make_store(tmp_path)
        pkg = self._make_package(name="My-Plugin", version="1.0.0")
        store.sync([pkg])
        result = store.get_plugin("MY-PLUGIN")
        assert result is not None
        assert result.name == "My-Plugin"

    def test_search_by_query_name_match(self, tmp_path: Path) -> None:
        store = self._make_store(tmp_path)
        pkg = self._make_package(name="image-organizer", version="1.0.0")
        store.sync([pkg])
        results = store.search("image")
        assert len(results) == 1
        assert results[0].name == "image-organizer"

    def test_search_empty_query_returns_all(self, tmp_path: Path) -> None:
        store = self._make_store(tmp_path)
        pkg1 = self._make_package(name="alpha-plugin", version="1.0.0")
        pkg2 = self._make_package(name="beta-plugin", version="1.0.0")
        store.sync([pkg1, pkg2])
        results = store.search("")
        assert len(results) == 2

    def test_search_returns_empty_on_no_match(self, tmp_path: Path) -> None:
        store = self._make_store(tmp_path)
        pkg = self._make_package(name="alpha-plugin", version="1.0.0")
        store.sync([pkg])
        results = store.search("xyz-nonexistent")
        assert results == []

    def test_search_by_category(self, tmp_path: Path) -> None:
        store = self._make_store(tmp_path)
        pkg = self._make_package(name="img-plugin", version="1.0.0", category="images")
        store.sync([pkg])
        results = store.search("", category="images")
        assert len(results) == 1
        assert results[0].category == "images"

    def test_search_category_no_match(self, tmp_path: Path) -> None:
        store = self._make_store(tmp_path)
        pkg = self._make_package(name="img-plugin", version="1.0.0", category="images")
        store.sync([pkg])
        results = store.search("", category="audio")
        assert results == []

    def test_search_by_tags(self, tmp_path: Path) -> None:
        store = self._make_store(tmp_path)
        pkg = self._make_package(name="tag-plugin", version="1.0.0", tags=["organizer", "images"])
        store.sync([pkg])
        results = store.search("", tags=["organizer"])
        assert len(results) == 1

    def test_search_tag_not_subset_excluded(self, tmp_path: Path) -> None:
        store = self._make_store(tmp_path)
        pkg = self._make_package(name="tag-plugin", version="1.0.0", tags=["organizer"])
        store.sync([pkg])
        results = store.search("", tags=["organizer", "images"])
        assert results == []

    def test_read_payload_raises_on_corrupt_json(self, tmp_path: Path) -> None:
        from file_organizer.plugins.marketplace.errors import MarketplaceRepositoryError

        db_path = tmp_path / "metadata.json"
        db_path.write_text("{ invalid json }", encoding="utf-8")
        store = self._make_store(tmp_path)
        with pytest.raises(MarketplaceRepositoryError, match="Failed to read"):
            store.list_all()

    def test_read_payload_raises_on_non_dict_root(self, tmp_path: Path) -> None:
        from file_organizer.plugins.marketplace.errors import MarketplaceRepositoryError

        db_path = tmp_path / "metadata.json"
        db_path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
        store = self._make_store(tmp_path)
        with pytest.raises(MarketplaceRepositoryError, match="root must be a JSON object"):
            store.list_all()

    def test_sync_creates_parent_directories(self, tmp_path: Path) -> None:
        from file_organizer.plugins.marketplace.metadata import PluginMetadataStore

        nested_path = tmp_path / "nested" / "deeply" / "metadata.json"
        store = PluginMetadataStore(db_path=nested_path)
        pkg = self._make_package(name="my-plugin", version="1.0.0")
        store.sync([pkg])
        assert nested_path.exists()

    def test_sync_uses_atomic_write(self, tmp_path: Path) -> None:
        """Sync should write via temp file (no partial writes visible)."""
        store = self._make_store(tmp_path)
        pkg = self._make_package(name="my-plugin", version="1.0.0")
        store.sync([pkg])
        # If file exists and is valid JSON, atomic write worked
        data = json.loads((tmp_path / "metadata.json").read_text())
        assert "plugins" in data

    def test_list_all_skips_non_dict_items(self, tmp_path: Path) -> None:
        db_path = tmp_path / "metadata.json"
        db_path.write_text(
            json.dumps({"plugins": [_make_package_dict(), "bad_item", 42]}), encoding="utf-8"
        )
        from file_organizer.plugins.marketplace.metadata import PluginMetadataStore

        store = PluginMetadataStore(db_path=db_path)
        result = store.list_all()
        assert len(result) == 1
        assert result[0].name == "my-plugin"


# ---------------------------------------------------------------------------
# TestDuplicateDetector
# ---------------------------------------------------------------------------


class TestDuplicateDetector:
    """Tests for DuplicateDetector (services/deduplication/detector.py)."""

    def test_init_creates_default_hasher_and_index(self) -> None:
        from file_organizer.services.deduplication.detector import DuplicateDetector

        detector = DuplicateDetector()
        assert detector.hasher is not None
        assert detector.index is not None

    def test_init_accepts_custom_hasher(self) -> None:
        from file_organizer.services.deduplication.detector import DuplicateDetector
        from file_organizer.services.deduplication.hasher import FileHasher

        custom_hasher = FileHasher()
        detector = DuplicateDetector(hasher=custom_hasher)
        assert detector.hasher is custom_hasher

    def test_init_creates_own_index(self) -> None:
        from file_organizer.services.deduplication.detector import DuplicateDetector
        from file_organizer.services.deduplication.index import DuplicateIndex

        detector = DuplicateDetector()
        assert isinstance(detector.index, DuplicateIndex)

    def test_scan_directory_raises_if_dir_not_exist(self, tmp_path: Path) -> None:
        from file_organizer.services.deduplication.detector import DuplicateDetector

        detector = DuplicateDetector()
        missing = tmp_path / "nonexistent"
        with pytest.raises(ValueError, match="Directory not found"):
            detector.scan_directory(missing)

    def test_scan_directory_raises_if_not_directory(self, tmp_path: Path) -> None:
        from file_organizer.services.deduplication.detector import DuplicateDetector

        f = tmp_path / "file.txt"
        f.write_text("hello")
        detector = DuplicateDetector()
        with pytest.raises(ValueError, match="not a directory"):
            detector.scan_directory(f)

    def test_scan_directory_empty_dir_returns_index(self, tmp_path: Path) -> None:
        from file_organizer.services.deduplication.detector import DuplicateDetector
        from file_organizer.services.deduplication.index import DuplicateIndex

        detector = DuplicateDetector()
        result = detector.scan_directory(tmp_path)
        assert isinstance(result, DuplicateIndex)
        assert len(result) == 0

    def test_scan_directory_detects_duplicate_files(self, tmp_path: Path) -> None:
        from file_organizer.services.deduplication.detector import DuplicateDetector

        content = b"duplicate content here"
        (tmp_path / "file1.txt").write_bytes(content)
        (tmp_path / "file2.txt").write_bytes(content)

        detector = DuplicateDetector()
        index = detector.scan_directory(tmp_path)
        assert index.has_duplicates() is True

    def test_scan_directory_no_duplicates_for_unique_files(self, tmp_path: Path) -> None:
        from file_organizer.services.deduplication.detector import DuplicateDetector

        (tmp_path / "file1.txt").write_bytes(b"content A")
        (tmp_path / "file2.txt").write_bytes(b"content B different")

        detector = DuplicateDetector()
        index = detector.scan_directory(tmp_path)
        assert index.has_duplicates() is False

    def test_scan_directory_calls_progress_callback(self, tmp_path: Path) -> None:
        from file_organizer.services.deduplication.detector import DuplicateDetector, ScanOptions

        content = b"same content"
        (tmp_path / "a.txt").write_bytes(content)
        (tmp_path / "b.txt").write_bytes(content)

        calls: list[tuple[int, int]] = []

        def cb(current: int, total: int) -> None:
            calls.append((current, total))

        opts = ScanOptions(progress_callback=cb)
        detector = DuplicateDetector()
        detector.scan_directory(tmp_path, opts)
        assert len(calls) >= 1

    def test_scan_directory_respects_min_file_size(self, tmp_path: Path) -> None:
        from file_organizer.services.deduplication.detector import DuplicateDetector, ScanOptions

        content = b"tiny"
        (tmp_path / "small1.txt").write_bytes(content)
        (tmp_path / "small2.txt").write_bytes(content)

        opts = ScanOptions(min_file_size=1000)  # bigger than file size
        detector = DuplicateDetector()
        index = detector.scan_directory(tmp_path, opts)
        assert index.has_duplicates() is False

    def test_scan_directory_respects_max_file_size(self, tmp_path: Path) -> None:
        from file_organizer.services.deduplication.detector import DuplicateDetector, ScanOptions

        content = b"x" * 100
        (tmp_path / "big1.txt").write_bytes(content)
        (tmp_path / "big2.txt").write_bytes(content)

        opts = ScanOptions(max_file_size=10)  # smaller than file size
        detector = DuplicateDetector()
        index = detector.scan_directory(tmp_path, opts)
        assert index.has_duplicates() is False

    def test_scan_directory_non_recursive_skips_subdirs(self, tmp_path: Path) -> None:
        from file_organizer.services.deduplication.detector import DuplicateDetector, ScanOptions

        content = b"same content"
        (tmp_path / "file1.txt").write_bytes(content)
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / "file2.txt").write_bytes(content)

        opts = ScanOptions(recursive=False)
        detector = DuplicateDetector()
        index = detector.scan_directory(tmp_path, opts)
        # Only file1.txt at top level, no duplicates within the non-recursive scan
        assert index.has_duplicates() is False

    def test_get_duplicate_groups_empty_initially(self) -> None:
        from file_organizer.services.deduplication.detector import DuplicateDetector

        detector = DuplicateDetector()
        groups = detector.get_duplicate_groups()
        assert groups == {}

    def test_get_statistics_initial_state(self) -> None:
        from file_organizer.services.deduplication.detector import DuplicateDetector

        detector = DuplicateDetector()
        stats = detector.get_statistics()
        assert stats["total_files"] == 0
        assert stats["duplicate_files"] == 0
        assert stats["duplicate_groups"] == 0
        assert stats["wasted_space"] == 0

    def test_clear_resets_index(self, tmp_path: Path) -> None:
        from file_organizer.services.deduplication.detector import DuplicateDetector

        content = b"same content"
        (tmp_path / "a.txt").write_bytes(content)
        (tmp_path / "b.txt").write_bytes(content)

        detector = DuplicateDetector()
        detector.scan_directory(tmp_path)
        assert detector.index.has_duplicates() is True

        detector.clear()
        assert len(detector.index) == 0
        assert detector.index.has_duplicates() is False

    def test_find_duplicates_of_file_raises_if_not_found(self, tmp_path: Path) -> None:
        from file_organizer.services.deduplication.detector import DuplicateDetector

        detector = DuplicateDetector()
        missing = tmp_path / "nonexistent.txt"
        with pytest.raises(FileNotFoundError, match="File not found"):
            detector.find_duplicates_of_file(missing, tmp_path)

    def test_find_duplicates_of_file_finds_copy(self, tmp_path: Path) -> None:
        from file_organizer.services.deduplication.detector import DuplicateDetector

        content = b"exact copy content"
        source = tmp_path / "original.txt"
        source.write_bytes(content)
        copy_dir = tmp_path / "copies"
        copy_dir.mkdir()
        copy = copy_dir / "copy.txt"
        copy.write_bytes(content)

        detector = DuplicateDetector()
        duplicates = detector.find_duplicates_of_file(source, tmp_path)
        assert len(duplicates) >= 1
        found_paths = [m.path.resolve() for m in duplicates]
        assert copy.resolve() in found_paths

    def test_find_duplicates_of_file_excludes_self(self, tmp_path: Path) -> None:
        from file_organizer.services.deduplication.detector import DuplicateDetector

        content = b"unique file content"
        source = tmp_path / "original.txt"
        source.write_bytes(content)

        detector = DuplicateDetector()
        duplicates = detector.find_duplicates_of_file(source, tmp_path)
        paths = [m.path.resolve() for m in duplicates]
        assert source.resolve() not in paths

    def test_scan_directory_with_symlink_skipped_by_default(self, tmp_path: Path) -> None:
        from file_organizer.services.deduplication.detector import DuplicateDetector

        real_file = tmp_path / "real.txt"
        real_file.write_bytes(b"content")
        link = tmp_path / "link.txt"
        try:
            link.symlink_to(real_file)
        except NotImplementedError:
            pytest.skip("Symlinks not supported on this platform")

        detector = DuplicateDetector()
        index = detector.scan_directory(tmp_path)
        # Symlink should be excluded so no duplicate
        assert index.has_duplicates() is False

    def test_get_statistics_after_scan(self, tmp_path: Path) -> None:
        from file_organizer.services.deduplication.detector import DuplicateDetector

        content = b"dup content"
        (tmp_path / "f1.txt").write_bytes(content)
        (tmp_path / "f2.txt").write_bytes(content)

        detector = DuplicateDetector()
        detector.scan_directory(tmp_path)
        stats = detector.get_statistics()
        assert stats["duplicate_groups"] == 1
        assert stats["duplicate_files"] == 2
        assert stats["wasted_space"] >= 1


# ---------------------------------------------------------------------------
# TestDocumentDeduplicator
# ---------------------------------------------------------------------------


class TestDocumentDeduplicator:
    """Tests for DocumentDeduplicator (services/deduplication/document_dedup.py)."""

    @pytest.fixture(autouse=True)
    def _require_sklearn(self) -> None:
        pytest.importorskip("sklearn")

    def test_init_default_params(self) -> None:
        from file_organizer.services.deduplication.document_dedup import DocumentDeduplicator

        dedup = DocumentDeduplicator()
        assert dedup.extractor is not None
        assert dedup.embedder is not None
        assert dedup.analyzer is not None

    def test_init_custom_threshold_and_features(self) -> None:
        from file_organizer.services.deduplication.document_dedup import DocumentDeduplicator

        dedup = DocumentDeduplicator(similarity_threshold=0.9, max_features=1000)
        assert dedup.analyzer.threshold == 0.9
        assert dedup.embedder.max_features == 1000

    def test_find_duplicates_empty_list(self) -> None:
        from file_organizer.services.deduplication.document_dedup import DocumentDeduplicator

        dedup = DocumentDeduplicator()
        result = dedup.find_duplicates([])
        assert result["duplicate_groups"] == []
        assert result["total_documents"] == 0
        assert result["analyzed_documents"] == 0
        assert result["space_wasted"] == 0

    def test_find_duplicates_insufficient_docs_returns_empty_groups(self, tmp_path: Path) -> None:
        from file_organizer.services.deduplication.document_dedup import DocumentDeduplicator

        f = tmp_path / "only.txt"
        f.write_text("Hello world this is some content long enough for text")

        dedup = DocumentDeduplicator()
        # Only one file → can't compare, returns early
        with patch.object(dedup.extractor, "supports_format", return_value=True):
            with patch.object(
                dedup.extractor,
                "extract_batch",
                return_value={f: "Hello world this is some content long enough"},
            ):
                result = dedup.find_duplicates([f], min_text_length=10)

        assert result["duplicate_groups"] == []
        assert result["analyzed_documents"] <= 1

    def test_find_duplicates_unsupported_formats_filtered(self, tmp_path: Path) -> None:
        from file_organizer.services.deduplication.document_dedup import DocumentDeduplicator

        f1 = tmp_path / "doc.xyz"
        f1.write_text("content")
        f2 = tmp_path / "doc2.xyz"
        f2.write_text("content")

        dedup = DocumentDeduplicator()
        with patch.object(dedup.extractor, "supports_format", return_value=False):
            result = dedup.find_duplicates([f1, f2])

        assert result["analyzed_documents"] == 0

    def test_find_duplicates_texts_too_short_filtered(self, tmp_path: Path) -> None:
        from file_organizer.services.deduplication.document_dedup import DocumentDeduplicator

        f1 = tmp_path / "short1.txt"
        f1.write_text("Hi")
        f2 = tmp_path / "short2.txt"
        f2.write_text("Hi")

        dedup = DocumentDeduplicator()
        with patch.object(dedup.extractor, "supports_format", return_value=True):
            with patch.object(
                dedup.extractor,
                "extract_batch",
                return_value={f1: "Hi", f2: "Hi"},
            ):
                result = dedup.find_duplicates([f1, f2], min_text_length=100)

        assert result["analyzed_documents"] == 0

    def test_find_duplicates_returns_expected_keys(self, tmp_path: Path) -> None:
        from file_organizer.services.deduplication.document_dedup import DocumentDeduplicator

        f1 = tmp_path / "doc1.txt"
        f2 = tmp_path / "doc2.txt"
        long_text = "a " * 60
        f1.write_text(long_text)
        f2.write_text(long_text)

        dedup = DocumentDeduplicator()
        mock_groups: list[Any] = []
        with patch.object(dedup.extractor, "supports_format", return_value=True):
            with patch.object(
                dedup.extractor,
                "extract_batch",
                return_value={f1: long_text, f2: long_text},
            ):
                with patch.object(dedup.embedder, "fit_transform", return_value=[[0.1], [0.1]]):
                    with patch.object(
                        dedup.analyzer, "get_duplicate_groups", return_value=mock_groups
                    ):
                        result = dedup.find_duplicates([f1, f2], min_text_length=10)

        assert "duplicate_groups" in result
        assert "total_documents" in result
        assert "analyzed_documents" in result
        assert "space_wasted" in result
        assert result["total_documents"] == 2

    def test_compare_documents_returns_none_on_extraction_failure(self, tmp_path: Path) -> None:
        from file_organizer.services.deduplication.document_dedup import DocumentDeduplicator

        f1 = tmp_path / "doc1.txt"
        f2 = tmp_path / "doc2.txt"
        f1.write_text("content")
        f2.write_text("content")

        dedup = DocumentDeduplicator()
        with patch.object(dedup.extractor, "extract_text", side_effect=ValueError("fail")):
            result = dedup.compare_documents(f1, f2)

        assert result is None

    def test_compare_documents_returns_none_on_empty_text(self, tmp_path: Path) -> None:
        from file_organizer.services.deduplication.document_dedup import DocumentDeduplicator

        f1 = tmp_path / "doc1.txt"
        f2 = tmp_path / "doc2.txt"
        f1.write_text("")
        f2.write_text("content")

        dedup = DocumentDeduplicator()
        with patch.object(dedup.extractor, "extract_text", return_value=""):
            result = dedup.compare_documents(f1, f2)

        assert result is None

    def test_compare_documents_returns_float_on_success(self, tmp_path: Path) -> None:
        from file_organizer.services.deduplication.document_dedup import DocumentDeduplicator

        f1 = tmp_path / "doc1.txt"
        f2 = tmp_path / "doc2.txt"
        f1.write_text("text")
        f2.write_text("text")

        dedup = DocumentDeduplicator()
        with patch.object(dedup.extractor, "extract_text", return_value="some text content"):
            with patch.object(
                dedup.embedder, "fit_transform", return_value=[[1.0, 0.0], [1.0, 0.0]]
            ):
                with patch.object(dedup.analyzer, "compute_similarity", return_value=0.95):
                    result = dedup.compare_documents(f1, f2)

        assert result is not None
        assert 0.0 <= result <= 1.0

    def test_calculate_space_wasted_empty_groups(self) -> None:
        from file_organizer.services.deduplication.document_dedup import DocumentDeduplicator

        dedup = DocumentDeduplicator()
        wasted = dedup._calculate_space_wasted([])
        assert wasted == 0

    def test_calculate_space_wasted_single_file_group(self, tmp_path: Path) -> None:
        from file_organizer.services.deduplication.document_dedup import DocumentDeduplicator

        f = tmp_path / "single.txt"
        f.write_text("content")

        dedup = DocumentDeduplicator()
        wasted = dedup._calculate_space_wasted([{"files": [str(f)]}])
        assert wasted == 0

    def test_calculate_space_wasted_nonexistent_files(self, tmp_path: Path) -> None:
        from file_organizer.services.deduplication.document_dedup import DocumentDeduplicator

        dedup = DocumentDeduplicator()
        groups = [{"files": ["/nonexistent/a.txt", "/nonexistent/b.txt"]}]
        # Should handle gracefully — nonexistent files have no stat
        wasted = dedup._calculate_space_wasted(groups)
        assert wasted == 0


# ---------------------------------------------------------------------------
# TestMisplacementDetector
# ---------------------------------------------------------------------------


class TestMisplacementDetector:
    """Tests for MisplacementDetector (services/misplacement_detector.py)."""

    def test_init_default_params(self) -> None:
        from file_organizer.services.misplacement_detector import MisplacementDetector

        detector = MisplacementDetector()
        assert detector.min_mismatch_score == 60.0
        assert detector.similarity_threshold == 0.7

    def test_init_custom_params(self) -> None:
        from file_organizer.services.misplacement_detector import MisplacementDetector

        detector = MisplacementDetector(min_mismatch_score=80.0, similarity_threshold=0.5)
        assert detector.min_mismatch_score == 80.0
        assert detector.similarity_threshold == 0.5

    def test_detect_misplaced_raises_on_invalid_directory(self, tmp_path: Path) -> None:
        from file_organizer.services.misplacement_detector import MisplacementDetector

        detector = MisplacementDetector()
        missing = tmp_path / "nonexistent"
        with pytest.raises(ValueError, match="Invalid directory"):
            detector.detect_misplaced(missing)

    def test_detect_misplaced_raises_on_file_path(self, tmp_path: Path) -> None:
        from file_organizer.services.misplacement_detector import MisplacementDetector

        f = tmp_path / "not_a_dir.txt"
        f.write_text("content")
        detector = MisplacementDetector()
        with pytest.raises(ValueError, match="Invalid directory"):
            detector.detect_misplaced(f)

    def test_detect_misplaced_empty_directory_returns_empty(self, tmp_path: Path) -> None:
        from file_organizer.services.misplacement_detector import MisplacementDetector

        detector = MisplacementDetector()
        result = detector.detect_misplaced(tmp_path)
        assert result == []

    def test_detect_misplaced_skips_hidden_files(self, tmp_path: Path) -> None:
        from file_organizer.services.misplacement_detector import MisplacementDetector

        hidden = tmp_path / ".hidden_file.txt"
        hidden.write_text("secret")
        detector = MisplacementDetector(min_mismatch_score=0.0)
        result = detector.detect_misplaced(tmp_path)
        # Hidden files must not be included
        paths = [m.file_path for m in result]
        assert hidden not in paths

    def test_detect_misplaced_returns_sorted_by_score(self, tmp_path: Path) -> None:
        from file_organizer.services.misplacement_detector import (
            MisplacementDetector,
        )

        # Create files with known types to get some mismatch
        (tmp_path / "image.jpg").write_bytes(b"\xff\xd8\xff" + b"x" * 100)
        (tmp_path / "script.py").write_text("print('hello')")
        (tmp_path / "audio.mp3").write_bytes(b"\xff\xfb" + b"x" * 100)

        detector = MisplacementDetector(min_mismatch_score=0.0)
        result = detector.detect_misplaced(tmp_path)
        # Sort is by score descending
        if len(result) >= 2:
            assert result[0].mismatch_score >= result[1].mismatch_score

    def test_analyze_context_returns_context_analysis(self, tmp_path: Path) -> None:
        from file_organizer.services.misplacement_detector import (
            ContextAnalysis,
            MisplacementDetector,
        )

        f = tmp_path / "test.txt"
        f.write_text("hello world")
        detector = MisplacementDetector()
        context = detector.analyze_context(f)
        assert isinstance(context, ContextAnalysis)
        assert context.file_path == f
        assert context.file_type == ".txt"
        assert context.directory == tmp_path

    def test_analyze_context_handles_oserror_on_stat(self, tmp_path: Path) -> None:
        from file_organizer.services.misplacement_detector import MisplacementDetector

        f = tmp_path / "test.txt"
        f.write_text("hello world")
        sibling = tmp_path / "other.txt"
        sibling.write_text("neighbor")
        detector = MisplacementDetector()
        real_stat = Path.stat

        def flaky_stat(path: Path, *args: Any, **kwargs: Any) -> Any:
            if path == sibling:
                raise OSError("permission denied")
            return real_stat(path, *args, **kwargs)

        with patch("pathlib.Path.stat", autospec=True, side_effect=flaky_stat):
            context = detector.analyze_context(f)
        assert context.file_path == f
        assert context.size > 0
        assert context.sibling_files == []

    def test_analyze_context_infers_sibling_types(self, tmp_path: Path) -> None:
        from file_organizer.services.misplacement_detector import MisplacementDetector

        (tmp_path / "sibling.py").write_text("# py file")
        (tmp_path / "sibling.js").write_text("// js file")
        f = tmp_path / "test.txt"
        f.write_text("hello")

        detector = MisplacementDetector()
        context = detector.analyze_context(f)
        assert ".py" in context.sibling_types
        assert ".js" in context.sibling_types

    def test_infer_category_from_type_known_types(self) -> None:
        from file_organizer.services.misplacement_detector import MisplacementDetector

        detector = MisplacementDetector()
        assert detector._infer_category_from_type(".pdf") == "documents"
        assert detector._infer_category_from_type(".jpg") == "images"
        assert detector._infer_category_from_type(".mp4") == "videos"
        assert detector._infer_category_from_type(".mp3") == "audio"
        assert detector._infer_category_from_type(".py") == "code"
        assert detector._infer_category_from_type(".zip") == "archives"

    def test_infer_category_from_type_unknown_type(self) -> None:
        from file_organizer.services.misplacement_detector import MisplacementDetector

        detector = MisplacementDetector()
        result = detector._infer_category_from_type(".xyz_unknown")
        assert result == "general"

    def test_calculate_mismatch_score_returns_bounded_value(self, tmp_path: Path) -> None:
        from file_organizer.services.misplacement_detector import MisplacementDetector
        from file_organizer.services.pattern_analyzer import PatternAnalysis

        detector = MisplacementDetector()
        f = tmp_path / "test.txt"
        f.write_text("content")
        context = detector.analyze_context(f)

        pattern_analysis = MagicMock(spec=PatternAnalysis)
        pattern_analysis.location_patterns = []
        pattern_analysis.content_clusters = []
        pattern_analysis.directory = tmp_path

        score = detector.calculate_mismatch_score(f, context, pattern_analysis)
        assert 0.0 <= score <= 100.0

    def test_check_type_mismatch_true_when_different_categories(self, tmp_path: Path) -> None:
        from file_organizer.services.misplacement_detector import MisplacementDetector

        (tmp_path / "sibling.mp3").write_bytes(b"audio")
        f = tmp_path / "script.py"
        f.write_text("code")
        detector = MisplacementDetector()
        context = detector.analyze_context(f)
        result = detector._check_type_mismatch(context)
        # .py (code) surrounded by .mp3 (audio) → different categories → True
        assert result is True

    def test_check_type_mismatch_false_when_same_category(self, tmp_path: Path) -> None:
        from file_organizer.services.misplacement_detector import MisplacementDetector

        (tmp_path / "sibling.py").write_text("code")
        f = tmp_path / "script.py"
        f.write_text("code")
        detector = MisplacementDetector()
        context = detector.analyze_context(f)
        result = detector._check_type_mismatch(context)
        assert result is False

    def test_find_correct_location_returns_path(self, tmp_path: Path) -> None:
        from file_organizer.services.misplacement_detector import MisplacementDetector
        from file_organizer.services.pattern_analyzer import PatternAnalysis

        f = tmp_path / "test.pdf"
        f.write_bytes(b"pdf content")

        pattern_analysis = MagicMock(spec=PatternAnalysis)
        pattern_analysis.location_patterns = []
        pattern_analysis.directory = tmp_path

        detector = MisplacementDetector()
        location = detector.find_correct_location(f, pattern_analysis)
        assert isinstance(location, Path)

    def test_find_similar_files_returns_empty_when_target_not_exist(self, tmp_path: Path) -> None:
        from file_organizer.services.misplacement_detector import MisplacementDetector
        from file_organizer.services.pattern_analyzer import PatternAnalysis

        f = tmp_path / "test.pdf"
        f.write_bytes(b"pdf")
        nonexistent_target = tmp_path / "nonexistent_dir"

        pattern_analysis = MagicMock(spec=PatternAnalysis)
        pattern_analysis.content_clusters = []

        detector = MisplacementDetector()
        result = detector.find_similar_files(f, nonexistent_target, pattern_analysis)
        assert result == []

    def test_detect_local_patterns_empty_files(self) -> None:
        from file_organizer.services.misplacement_detector import MisplacementDetector

        detector = MisplacementDetector()
        result = detector._detect_local_patterns([])
        assert result == []

    def test_detect_local_patterns_detects_date_pattern(self, tmp_path: Path) -> None:
        from file_organizer.services.misplacement_detector import MisplacementDetector

        files = [
            tmp_path / "2024-01-report.txt",
            tmp_path / "2024-02-report.txt",
            tmp_path / "2024-03-report.txt",
        ]
        for f in files:
            f.write_text("content")

        detector = MisplacementDetector()
        patterns = detector._detect_local_patterns(files)
        assert "date" in patterns

    def test_generate_mismatch_reasons_returns_list(self, tmp_path: Path) -> None:
        from file_organizer.services.misplacement_detector import MisplacementDetector

        f = tmp_path / "test.txt"
        f.write_text("content")
        detector = MisplacementDetector()
        context = detector.analyze_context(f)
        reasons = detector._generate_mismatch_reasons(f, context, 50.0)
        assert isinstance(reasons, list)
        assert len(reasons) >= 1

    def test_generate_mismatch_reasons_high_score_message(self, tmp_path: Path) -> None:
        from file_organizer.services.misplacement_detector import MisplacementDetector

        f = tmp_path / "test.txt"
        f.write_text("content")
        detector = MisplacementDetector()
        context = detector.analyze_context(f)
        reasons = detector._generate_mismatch_reasons(f, context, 85.0)
        # High score should include specific message
        combined = " ".join(reasons)
        assert "wrong location" in combined or "Strong" in combined

    def test_misplaced_file_to_dict_contains_expected_keys(self, tmp_path: Path) -> None:
        from file_organizer.services.misplacement_detector import MisplacedFile

        f = tmp_path / "test.txt"
        f.write_text("content")
        mf = MisplacedFile(
            file_path=f,
            current_location=tmp_path,
            suggested_location=tmp_path / "docs",
            mismatch_score=75.0,
            reasons=["type mismatch"],
        )
        d = mf.to_dict()
        assert "file_path" in d
        assert "current_location" in d
        assert "suggested_location" in d
        assert d["mismatch_score"] == 75.0
        assert d["reasons"] == ["type mismatch"]
        assert "detected_at" in d

    def test_context_analysis_to_dict(self, tmp_path: Path) -> None:
        from file_organizer.services.misplacement_detector import (
            MisplacementDetector,
        )

        f = tmp_path / "test.txt"
        f.write_text("hello")
        detector = MisplacementDetector()
        context = detector.analyze_context(f)
        d = context.to_dict()
        assert "file_path" in d
        assert "file_type" in d
        assert "sibling_count" in d
        assert isinstance(d["sibling_count"], int)

    def test_is_in_or_near_returns_true_for_child(self, tmp_path: Path) -> None:
        from file_organizer.services.misplacement_detector import MisplacementDetector

        subdir = tmp_path / "sub"
        subdir.mkdir()
        f = subdir / "file.txt"
        f.write_text("x")

        detector = MisplacementDetector()
        assert detector._is_in_or_near(f, subdir) is True

    def test_is_in_or_near_returns_false_for_deeply_unrelated_path(self, tmp_path: Path) -> None:
        from file_organizer.services.misplacement_detector import MisplacementDetector

        # Create a deeper nesting so parent.parent != target.parent
        base = tmp_path / "root"
        base.mkdir()
        other = base / "a" / "deep" / "other"
        other.mkdir(parents=True)
        target = tmp_path / "target"
        target.mkdir()
        f = other / "file.txt"
        f.write_text("x")

        detector = MisplacementDetector()
        # f's parent.parent is base/a/deep, target.parent is tmp_path
        # These differ, so _is_in_or_near returns False
        result = detector._is_in_or_near(f, target)
        assert result is False
