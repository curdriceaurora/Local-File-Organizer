"""Integration tests for plugins/api/endpoints.py and plugins/api/hooks.py.

Covers: list_files_for_plugins, get_file_metadata_for_plugins,
organize_file_for_plugins, get_config_for_plugins,
register_plugin_hook, unregister_plugin_hook, list_plugin_hooks,
trigger_plugin_hook_event, _collect_files, _plugin_identity,
_read_config_key, PluginHookManager (webhook lifecycle, trigger_event,
local hook delegation).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_settings
from file_organizer.api.exceptions import setup_exception_handlers
from file_organizer.plugins.api.endpoints import router as plugins_router

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def plugin_settings(tmp_path: Path) -> ApiSettings:
    return ApiSettings(
        allowed_paths=[str(tmp_path)],
        auth_enabled=False,
        auth_db_path=str(tmp_path / "auth.db"),
    )


@pytest.fixture()
def plugin_client(plugin_settings: ApiSettings) -> TestClient:
    from file_organizer.plugins.api.endpoints import get_hook_manager

    app = FastAPI()
    app.dependency_overrides[get_settings] = lambda: plugin_settings
    setup_exception_handlers(app)
    app.include_router(plugins_router, prefix="/api/v1")
    # Reset hook manager cache per test
    get_hook_manager.cache_clear()
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# list_files_for_plugins — GET /api/v1/plugins/files/list
# ---------------------------------------------------------------------------


class TestListFilesForPlugins:
    def test_list_files_returns_200(self, plugin_client: TestClient, tmp_path: Path) -> None:
        (tmp_path / "a.txt").write_text("hello")
        r = plugin_client.get("/api/v1/plugins/files/list", params={"path": str(tmp_path)})
        assert r.status_code == 200

    def test_list_files_response_shape(self, plugin_client: TestClient, tmp_path: Path) -> None:
        sub = tmp_path / "shape_dir"
        sub.mkdir()
        (sub / "b.txt").write_text("x")
        r = plugin_client.get("/api/v1/plugins/files/list", params={"path": str(sub)})
        body = r.json()
        assert "items" in body
        assert "total" in body
        assert len(body["items"]) == 1
        assert body["total"] == 1

    def test_list_files_nonexistent_returns_404(
        self, plugin_client: TestClient, tmp_path: Path
    ) -> None:
        r = plugin_client.get("/api/v1/plugins/files/list", params={"path": str(tmp_path / "gone")})
        assert r.status_code == 404

    def test_list_files_outside_root_returns_403(self, plugin_client: TestClient) -> None:
        r = plugin_client.get("/api/v1/plugins/files/list", params={"path": "/etc"})
        assert r.status_code == 403

    def test_list_files_recursive(self, plugin_client: TestClient, tmp_path: Path) -> None:
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "deep.txt").write_text("x")
        r = plugin_client.get(
            "/api/v1/plugins/files/list",
            params={"path": str(tmp_path), "recursive": "true"},
        )
        body = r.json()
        names = [item["name"] for item in body["items"]]
        assert "deep.txt" in names

    def test_list_files_hidden_excluded_by_default(
        self, plugin_client: TestClient, tmp_path: Path
    ) -> None:
        (tmp_path / ".hidden").write_text("secret")
        (tmp_path / "visible.txt").write_text("x")
        r = plugin_client.get("/api/v1/plugins/files/list", params={"path": str(tmp_path)})
        body = r.json()
        names = [item["name"] for item in body["items"]]
        assert ".hidden" not in names
        assert "visible.txt" in names

    def test_list_files_hidden_included_when_flag_set(
        self, plugin_client: TestClient, tmp_path: Path
    ) -> None:
        (tmp_path / ".hidden").write_text("secret")
        r = plugin_client.get(
            "/api/v1/plugins/files/list",
            params={"path": str(tmp_path), "include_hidden": "true"},
        )
        body = r.json()
        names = [item["name"] for item in body["items"]]
        assert ".hidden" in names

    def test_list_files_max_items(self, plugin_client: TestClient, tmp_path: Path) -> None:
        sub = tmp_path / "max_items_dir"
        sub.mkdir()
        for i in range(5):
            (sub / f"f{i}.txt").write_text("x")
        r = plugin_client.get(
            "/api/v1/plugins/files/list",
            params={"path": str(sub), "max_items": "2"},
        )
        body = r.json()
        assert len(body["items"]) == 2
        assert body["total"] == 5

    def test_list_single_file_path(self, plugin_client: TestClient, tmp_path: Path) -> None:
        f = tmp_path / "solo.txt"
        f.write_text("data")
        r = plugin_client.get("/api/v1/plugins/files/list", params={"path": str(f)})
        body = r.json()
        assert body["total"] == 1
        assert body["items"][0]["name"] == "solo.txt"


# ---------------------------------------------------------------------------
# get_file_metadata_for_plugins — GET /api/v1/plugins/files/metadata
# ---------------------------------------------------------------------------


class TestGetFileMetadata:
    def test_metadata_existing_file(self, plugin_client: TestClient, tmp_path: Path) -> None:
        f = tmp_path / "doc.txt"
        f.write_text("hello")
        r = plugin_client.get("/api/v1/plugins/files/metadata", params={"path": str(f)})
        assert r.status_code == 200
        body = r.json()
        assert body["name"] == "doc.txt"
        assert body["size"] == len("hello")

    def test_metadata_nonexistent_returns_404(
        self, plugin_client: TestClient, tmp_path: Path
    ) -> None:
        r = plugin_client.get(
            "/api/v1/plugins/files/metadata",
            params={"path": str(tmp_path / "missing.txt")},
        )
        assert r.status_code == 404

    def test_metadata_directory_returns_400(
        self, plugin_client: TestClient, tmp_path: Path
    ) -> None:
        sub = tmp_path / "subdir"
        sub.mkdir()
        r = plugin_client.get("/api/v1/plugins/files/metadata", params={"path": str(sub)})
        assert r.status_code == 400

    def test_metadata_outside_root_returns_403(self, plugin_client: TestClient) -> None:
        r = plugin_client.get("/api/v1/plugins/files/metadata", params={"path": "/etc/hosts"})
        assert r.status_code == 403


# ---------------------------------------------------------------------------
# organize_file_for_plugins — POST /api/v1/plugins/files/organize
# ---------------------------------------------------------------------------


class TestOrganizeFileForPlugins:
    def test_dry_run_returns_moved_false(self, plugin_client: TestClient, tmp_path: Path) -> None:
        src = tmp_path / "source.txt"
        src.write_text("data")
        dest = tmp_path / "dest.txt"
        r = plugin_client.post(
            "/api/v1/plugins/files/organize",
            json={
                "source_path": str(src),
                "destination_path": str(dest),
                "dry_run": True,
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["moved"] is False
        assert body["dry_run"] is True
        assert src.exists()

    def test_real_move(self, plugin_client: TestClient, tmp_path: Path) -> None:
        src = tmp_path / "to_move.txt"
        src.write_text("content")
        dest = tmp_path / "moved.txt"
        r = plugin_client.post(
            "/api/v1/plugins/files/organize",
            json={
                "source_path": str(src),
                "destination_path": str(dest),
                "dry_run": False,
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["moved"] is True
        assert not src.exists()
        assert dest.exists()

    def test_source_not_found_returns_404(self, plugin_client: TestClient, tmp_path: Path) -> None:
        r = plugin_client.post(
            "/api/v1/plugins/files/organize",
            json={
                "source_path": str(tmp_path / "missing.txt"),
                "destination_path": str(tmp_path / "dest.txt"),
            },
        )
        assert r.status_code == 404

    def test_destination_exists_no_overwrite_returns_409(
        self, plugin_client: TestClient, tmp_path: Path
    ) -> None:
        src = tmp_path / "src.txt"
        src.write_text("x")
        dest = tmp_path / "dest.txt"
        dest.write_text("y")
        r = plugin_client.post(
            "/api/v1/plugins/files/organize",
            json={
                "source_path": str(src),
                "destination_path": str(dest),
                "overwrite": False,
            },
        )
        assert r.status_code == 409


# ---------------------------------------------------------------------------
# Plugin hooks — POST /api/v1/plugins/hooks/register, unregister, list, trigger
# ---------------------------------------------------------------------------


class TestPluginHooks:
    def test_register_hook_returns_200(self, plugin_client: TestClient) -> None:
        r = plugin_client.post(
            "/api/v1/plugins/hooks/register",
            json={
                "event": "file.scanned",
                "callback_url": "http://localhost:9999/hook",
                "secret": None,
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["event"] == "file.scanned"
        assert body["registered"] is True

    def test_register_hook_invalid_url_returns_400(self, plugin_client: TestClient) -> None:
        r = plugin_client.post(
            "/api/v1/plugins/hooks/register",
            json={"event": "file.scanned", "callback_url": "not-a-url"},
        )
        assert r.status_code == 400

    def test_register_hook_duplicate_returns_registered_false(
        self, plugin_client: TestClient
    ) -> None:
        payload = {"event": "file.scanned", "callback_url": "http://localhost:9999/hook"}
        plugin_client.post("/api/v1/plugins/hooks/register", json=payload)
        r = plugin_client.post("/api/v1/plugins/hooks/register", json=payload)
        assert r.status_code == 200
        assert r.json()["registered"] is False

    def test_list_hooks_returns_registered(self, plugin_client: TestClient) -> None:
        plugin_client.post(
            "/api/v1/plugins/hooks/register",
            json={"event": "file.organized", "callback_url": "http://localhost:8888/cb"},
        )
        r = plugin_client.get("/api/v1/plugins/hooks")
        assert r.status_code == 200
        body = r.json()
        assert "items" in body
        assert len(body["items"]) >= 1

    def test_list_hooks_filter_by_event(self, plugin_client: TestClient) -> None:
        plugin_client.post(
            "/api/v1/plugins/hooks/register",
            json={"event": "file.scanned", "callback_url": "http://localhost:8001/a"},
        )
        plugin_client.post(
            "/api/v1/plugins/hooks/register",
            json={"event": "file.organized", "callback_url": "http://localhost:8002/b"},
        )
        r = plugin_client.get("/api/v1/plugins/hooks", params={"event": "file.scanned"})
        body = r.json()
        assert all(item["event"] == "file.scanned" for item in body["items"])

    def test_unregister_hook(self, plugin_client: TestClient) -> None:
        plugin_client.post(
            "/api/v1/plugins/hooks/register",
            json={"event": "file.deleted", "callback_url": "http://localhost:7777/del"},
        )
        r = plugin_client.post(
            "/api/v1/plugins/hooks/unregister",
            json={"event": "file.deleted", "callback_url": "http://localhost:7777/del"},
        )
        assert r.status_code == 200
        assert r.json()["removed"] is True

    def test_unregister_hook_not_registered(self, plugin_client: TestClient) -> None:
        r = plugin_client.post(
            "/api/v1/plugins/hooks/unregister",
            json={"event": "file.deleted", "callback_url": "http://localhost:1234/gone"},
        )
        assert r.status_code == 200
        assert r.json()["removed"] is False

    def test_trigger_hook_no_webhooks(self, plugin_client: TestClient) -> None:
        r = plugin_client.post(
            "/api/v1/plugins/hooks/trigger",
            json={"event": "para.categorized", "payload": {"category": "areas"}},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["event"] == "para.categorized"
        assert body["delivered"] == 0
        assert body["failed"] == 0

    def test_trigger_hook_with_webhook_delivery(self, plugin_client: TestClient) -> None:
        """Register a webhook, mock HTTP delivery, verify trigger response."""
        plugin_client.post(
            "/api/v1/plugins/hooks/register",
            json={
                "event": "organization.started",
                "callback_url": "http://localhost:5555/ev",
            },
        )
        from file_organizer.plugins.api.hooks import HookEvent, WebhookDeliveryResult

        mock_result = WebhookDeliveryResult(
            plugin_id="anonymous",
            event=HookEvent.ORGANIZATION_STARTED,
            callback_url="http://localhost:5555/ev",
            status_code=200,
            delivered=True,
        )
        with patch(
            "file_organizer.plugins.api.hooks.PluginHookManager.trigger_event",
            return_value=[mock_result],
        ):
            r = plugin_client.post(
                "/api/v1/plugins/hooks/trigger",
                json={"event": "organization.started", "payload": {}},
            )
        assert r.status_code == 200
        body = r.json()
        assert body["delivered"] == 1
        assert body["failed"] == 0


# ---------------------------------------------------------------------------
# PluginHookManager unit tests
# ---------------------------------------------------------------------------


class TestPluginHookManager:
    def test_register_webhook_creates_registration(self) -> None:
        from file_organizer.plugins.api.hooks import HookEvent, PluginHookManager

        manager = PluginHookManager()
        reg, created = manager.register_webhook(
            plugin_id="plugin-1",
            event=HookEvent.FILE_SCANNED,
            callback_url="http://example.com/hook",
        )
        assert created is True
        assert reg.plugin_id == "plugin-1"
        assert reg.event == HookEvent.FILE_SCANNED

    def test_register_webhook_duplicate_returns_false(self) -> None:
        from file_organizer.plugins.api.hooks import HookEvent, PluginHookManager

        manager = PluginHookManager()
        manager.register_webhook(
            plugin_id="p", event=HookEvent.FILE_ORGANIZED, callback_url="http://a.b/c"
        )
        _, created = manager.register_webhook(
            plugin_id="p", event=HookEvent.FILE_ORGANIZED, callback_url="http://a.b/c"
        )
        assert created is False

    def test_unregister_webhook(self) -> None:
        from file_organizer.plugins.api.hooks import HookEvent, PluginHookManager

        manager = PluginHookManager()
        manager.register_webhook(
            plugin_id="p", event=HookEvent.FILE_DELETED, callback_url="http://x.y/z"
        )
        removed = manager.unregister_webhook(
            plugin_id="p", event=HookEvent.FILE_DELETED, callback_url="http://x.y/z"
        )
        assert removed is True
        assert manager.list_webhooks(plugin_id="p") == []

    def test_unregister_nonexistent_returns_false(self) -> None:
        from file_organizer.plugins.api.hooks import HookEvent, PluginHookManager

        manager = PluginHookManager()
        removed = manager.unregister_webhook(
            plugin_id="x", event=HookEvent.FILE_SCANNED, callback_url="http://no.where/nope"
        )
        assert removed is False

    def test_list_webhooks_filter_by_event(self) -> None:
        from file_organizer.plugins.api.hooks import HookEvent, PluginHookManager

        manager = PluginHookManager()
        manager.register_webhook(
            plugin_id="p1", event=HookEvent.FILE_SCANNED, callback_url="http://a.com/1"
        )
        manager.register_webhook(
            plugin_id="p2", event=HookEvent.FILE_ORGANIZED, callback_url="http://b.com/2"
        )
        scanned = manager.list_webhooks(event=HookEvent.FILE_SCANNED)
        assert len(scanned) == 1
        assert scanned[0].event == HookEvent.FILE_SCANNED

    def test_trigger_event_empty_returns_empty(self) -> None:
        from file_organizer.plugins.api.hooks import HookEvent, PluginHookManager

        manager = PluginHookManager()
        results = manager.trigger_event(HookEvent.DEDUPLICATION_STARTED, {"key": "val"})
        assert results == []

    def test_trigger_event_http_error_marks_failed(self) -> None:
        import httpx

        from file_organizer.plugins.api.hooks import HookEvent, PluginHookManager

        def _failing_factory() -> httpx.Client:
            mock = MagicMock(spec=httpx.Client)
            mock.__enter__ = lambda s: s
            mock.__exit__ = MagicMock(return_value=False)
            mock.post.side_effect = httpx.ConnectError("refused")
            return mock

        manager = PluginHookManager(http_client_factory=_failing_factory)
        manager.register_webhook(
            plugin_id="p",
            event=HookEvent.FILE_SCANNED,
            callback_url="http://localhost:1/fail",
        )
        results = manager.trigger_event(HookEvent.FILE_SCANNED, {})
        assert len(results) == 1
        assert results[0].delivered is False
        assert results[0].error is not None

    def test_register_local_hook_and_trigger(self) -> None:
        from file_organizer.plugins.api.hooks import HookEvent, PluginHookManager

        manager = PluginHookManager()
        received: list[dict] = []
        manager.register_local_hook(
            HookEvent.FILE_SCANNED, lambda payload: received.append(payload)
        )
        manager.trigger_local_hooks(HookEvent.FILE_SCANNED, {"file": "a.txt"})
        assert len(received) == 1
        assert received[0]["file"] == "a.txt"

    def test_clear_removes_all(self) -> None:
        from file_organizer.plugins.api.hooks import HookEvent, PluginHookManager

        manager = PluginHookManager()
        manager.register_webhook(
            plugin_id="p", event=HookEvent.FILE_SCANNED, callback_url="http://a.b/c"
        )
        manager.clear()
        assert manager.list_webhooks() == []

    def test_validate_callback_url_raises_on_bad_scheme(self) -> None:
        from file_organizer.plugins.api.hooks import _validate_callback_url

        with pytest.raises(ValueError, match="http or https"):
            _validate_callback_url("ftp://example.com/hook")

    def test_validate_callback_url_raises_on_missing_host(self) -> None:
        from file_organizer.plugins.api.hooks import _validate_callback_url

        with pytest.raises(ValueError, match="host"):
            _validate_callback_url("http:///path")
