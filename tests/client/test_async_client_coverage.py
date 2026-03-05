"""Coverage tests for client.async_client module."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import pytest_asyncio

from file_organizer.client.async_client import AsyncFileOrganizerClient
from file_organizer.client.exceptions import (
    AuthenticationError,
    ClientError,
    NotFoundError,
    ServerError,
    ValidationError,
)

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


def _mock_response(status_code: int = 200, json_data: dict | None = None):
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.is_success = 200 <= status_code < 300
    resp.text = ""
    if json_data is not None:
        resp.json.return_value = json_data
    else:
        resp.json.side_effect = ValueError("no json")
    return resp


NOW = datetime.now(tz=UTC).isoformat()


@pytest_asyncio.fixture
async def client():
    """Provide an AsyncFileOrganizerClient that auto-closes after the test."""
    c = AsyncFileOrganizerClient()
    yield c
    await c.aclose()


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


class TestAsyncClientAuth:
    async def test_login(self, client):
        resp = _mock_response(
            200,
            {"access_token": "tok", "refresh_token": "ref", "token_type": "bearer"},
        )
        client._client.post = AsyncMock(return_value=resp)
        result = await client.login("user", "pass")
        assert result.access_token == "tok"

    async def test_register(self, client):
        resp = _mock_response(
            200,
            {
                "id": "1",
                "username": "u",
                "email": "e@e.com",
                "is_active": True,
                "is_admin": False,
                "created_at": NOW,
            },
        )
        client._client.post = AsyncMock(return_value=resp)
        result = await client.register("u", "e@e.com", "p", full_name="F")
        assert result.username == "u"

    async def test_refresh_token(self, client):
        resp = _mock_response(
            200,
            {"access_token": "new", "refresh_token": "ref2", "token_type": "bearer"},
        )
        client._client.post = AsyncMock(return_value=resp)
        result = await client.refresh_token("ref1")
        assert result.access_token == "new"

    async def test_logout(self, client):
        resp = _mock_response(200, {})
        client._client.post = AsyncMock(return_value=resp)
        await client.logout("ref1")

    async def test_me(self, client):
        resp = _mock_response(
            200,
            {
                "id": "1",
                "username": "u",
                "email": "e@e.com",
                "is_active": True,
                "is_admin": False,
                "created_at": NOW,
            },
        )
        client._client.get = AsyncMock(return_value=resp)
        result = await client.me()
        assert result.username == "u"


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------


class TestAsyncClientFiles:
    async def test_list_files(self, client):
        resp = _mock_response(200, {"items": [], "total": 0, "skip": 0, "limit": 100})
        client._client.get = AsyncMock(return_value=resp)
        result = await client.list_files("/tmp", file_type="txt")
        assert result.total == 0

    async def test_get_file_info(self, client):
        resp = _mock_response(
            200,
            {
                "path": "/tmp/a.txt",
                "name": "a.txt",
                "size": 100,
                "created": NOW,
                "modified": NOW,
                "file_type": "txt",
            },
        )
        client._client.get = AsyncMock(return_value=resp)
        result = await client.get_file_info("/tmp/a.txt")
        assert result.name == "a.txt"

    async def test_read_file_content(self, client):
        resp = _mock_response(
            200,
            {
                "path": "/tmp/a.txt",
                "content": "hello",
                "encoding": "utf-8",
                "truncated": False,
                "size": 5,
            },
        )
        client._client.get = AsyncMock(return_value=resp)
        result = await client.read_file_content("/tmp/a.txt")
        assert result.content == "hello"

    async def test_move_file(self, client):
        resp = _mock_response(
            200,
            {"source": "/a", "destination": "/b", "moved": True, "dry_run": False},
        )
        client._client.post = AsyncMock(return_value=resp)
        result = await client.move_file("/a", "/b")
        assert result.moved is True

    async def test_delete_file(self, client):
        resp = _mock_response(200, {"path": "/a", "deleted": True, "dry_run": False})
        client._client.request = AsyncMock(return_value=resp)
        result = await client.delete_file("/a")
        assert result.deleted is True


# ---------------------------------------------------------------------------
# Organize
# ---------------------------------------------------------------------------


class TestAsyncClientOrganize:
    async def test_scan(self, client):
        resp = _mock_response(200, {"input_dir": "/tmp", "total_files": 5, "counts": {"txt": 5}})
        client._client.post = AsyncMock(return_value=resp)
        result = await client.scan("/tmp")
        assert result.total_files == 5

    async def test_preview_organize(self, client):
        resp = _mock_response(
            200,
            {
                "total_files": 3,
                "processed_files": 3,
                "skipped_files": 0,
                "failed_files": 0,
                "processing_time": 1.0,
                "organized_structure": {},
                "errors": [],
            },
        )
        client._client.post = AsyncMock(return_value=resp)
        result = await client.preview_organize("/in", "/out")
        assert result.total_files == 3

    async def test_organize(self, client):
        resp = _mock_response(200, {"status": "queued", "job_id": "j1"})
        client._client.post = AsyncMock(return_value=resp)
        result = await client.organize("/in", "/out")
        assert result.job_id == "j1"

    async def test_get_job(self, client):
        resp = _mock_response(
            200,
            {
                "job_id": "j1",
                "status": "completed",
                "created_at": NOW,
                "updated_at": NOW,
            },
        )
        client._client.get = AsyncMock(return_value=resp)
        result = await client.get_job("j1")
        assert result.status == "completed"


# ---------------------------------------------------------------------------
# System
# ---------------------------------------------------------------------------


class TestAsyncClientSystem:
    async def test_health(self, client):
        resp = _mock_response(
            200,
            {
                "status": "ok",
                "readiness": "ready",
                "version": "1.0",
                "ollama": True,
                "uptime": 100.0,
            },
        )
        client._client.get = AsyncMock(return_value=resp)
        result = await client.health()
        assert result.status == "ok"

    async def test_system_status(self, client):
        resp = _mock_response(
            200,
            {
                "app": "fo",
                "version": "1.0",
                "environment": "dev",
                "disk_total": 100,
                "disk_used": 50,
                "disk_free": 50,
                "active_jobs": 0,
            },
        )
        client._client.get = AsyncMock(return_value=resp)
        result = await client.system_status()
        assert result.disk_free == 50

    async def test_get_config(self, client):
        resp = _mock_response(200, {"profile": "default", "config": {}, "profiles": ["default"]})
        client._client.get = AsyncMock(return_value=resp)
        result = await client.get_config()
        assert result.profile == "default"

    async def test_update_config(self, client):
        resp = _mock_response(
            200,
            {"profile": "default", "config": {"k": "v"}, "profiles": ["default"]},
        )
        client._client.patch = AsyncMock(return_value=resp)
        result = await client.update_config({"k": "v"})
        assert result.config == {"k": "v"}

    async def test_system_stats(self, client):
        resp = _mock_response(
            200,
            {
                "total_size": 1000,
                "organized_size": 500,
                "saved_size": 200,
                "file_count": 10,
                "directory_count": 3,
                "size_by_type": {},
                "largest_files": [],
            },
        )
        client._client.get = AsyncMock(return_value=resp)
        result = await client.system_stats(max_depth=2)
        assert result.file_count == 10


# ---------------------------------------------------------------------------
# Dedupe
# ---------------------------------------------------------------------------


class TestAsyncClientDedupe:
    async def test_dedupe_scan(self, client):
        resp = _mock_response(200, {"path": "/tmp", "duplicates": [], "stats": {"total": 0}})
        client._client.post = AsyncMock(return_value=resp)
        result = await client.dedupe_scan("/tmp")
        assert result.path == "/tmp"

    async def test_dedupe_preview(self, client):
        resp = _mock_response(200, {"path": "/tmp", "preview": [], "stats": {"total": 0}})
        client._client.post = AsyncMock(return_value=resp)
        result = await client.dedupe_preview("/tmp")
        assert result.path == "/tmp"

    async def test_dedupe_execute(self, client):
        resp = _mock_response(
            200,
            {"path": "/tmp", "removed": [], "dry_run": True, "stats": {"total": 0}},
        )
        client._client.post = AsyncMock(return_value=resp)
        result = await client.dedupe_execute("/tmp")
        assert result.dry_run is True


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------


class TestAsyncClientContextManager:
    async def test_async_context_manager(self):
        c = AsyncFileOrganizerClient()
        c._client.aclose = AsyncMock()

        async with c as ctx:
            assert ctx is c

        c._client.aclose.assert_awaited_once()


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestAsyncClientErrorHandling:
    async def test_401_raises_auth_error(self, client):
        resp = _mock_response(401, {"detail": "unauthorized"})
        client._client.get = AsyncMock(return_value=resp)
        with pytest.raises(AuthenticationError, match="401"):
            await client.health()

    async def test_404_raises_not_found(self, client):
        resp = _mock_response(404, {"detail": "not found"})
        client._client.get = AsyncMock(return_value=resp)
        with pytest.raises(NotFoundError, match="404"):
            await client.get_file_info("/missing")

    async def test_500_raises_server_error(self, client):
        resp = _mock_response(500, {"detail": "internal error"})
        client._client.get = AsyncMock(return_value=resp)
        with pytest.raises(ServerError, match="500"):
            await client.health()

    async def test_generic_4xx_raises_client_error(self, client):
        resp = _mock_response(400, {"detail": "bad request"})
        client._client.get = AsyncMock(return_value=resp)
        with pytest.raises(ClientError, match="400"):
            await client.health()

    async def test_set_token(self, client):
        client.set_token("new-token")
        assert client._client.headers["Authorization"] == "Bearer new-token"

    async def test_init_with_api_key_and_token(self):
        c = AsyncFileOrganizerClient(api_key="key123", token="tok456")
        assert "X-API-Key" in c._client.headers
        assert "Authorization" in c._client.headers
        await c.aclose()

    async def test_403_raises_auth_error(self, client):
        resp = _mock_response(403, {"detail": "forbidden"})
        client._client.get = AsyncMock(return_value=resp)
        with pytest.raises(AuthenticationError, match="403"):
            await client.health()

    async def test_422_raises_validation_error(self, client):
        resp = _mock_response(422, {"detail": "invalid field"})
        client._client.post = AsyncMock(return_value=resp)
        with pytest.raises(ValidationError, match="422"):
            await client.login("u", "p")

    async def test_502_raises_server_error(self, client):
        resp = _mock_response(502, {"detail": "bad gateway"})
        client._client.get = AsyncMock(return_value=resp)
        with pytest.raises(ServerError, match="502"):
            await client.health()

    async def test_error_response_no_json(self, client):
        """When response.json() raises, fallback to response.text."""
        resp = _mock_response(500)
        resp.text = "plain text error"
        client._client.get = AsyncMock(return_value=resp)
        with pytest.raises(ServerError, match="plain text error"):
            await client.health()

    async def test_error_response_message_key(self, client):
        """When body has 'message' instead of 'detail'."""
        resp = _mock_response(400, {"message": "custom msg"})
        client._client.get = AsyncMock(return_value=resp)
        with pytest.raises(ClientError, match="custom msg"):
            await client.health()


# ---------------------------------------------------------------------------
# Init parameter combinations
# ---------------------------------------------------------------------------


class TestAsyncClientInit:
    async def test_init_token_only(self):
        c = AsyncFileOrganizerClient(token="tok-only")
        assert "Authorization" in c._client.headers
        assert "X-API-Key" not in c._client.headers
        await c.aclose()

    async def test_init_api_key_only(self):
        c = AsyncFileOrganizerClient(api_key="key-only")
        assert "X-API-Key" in c._client.headers
        assert "Authorization" not in c._client.headers
        await c.aclose()

    async def test_init_defaults(self):
        c = AsyncFileOrganizerClient()
        assert "Authorization" not in c._client.headers
        assert "X-API-Key" not in c._client.headers
        assert c._base_url == "http://localhost:8000"
        await c.aclose()

    async def test_init_custom_base_url(self):
        c = AsyncFileOrganizerClient(base_url="http://custom:9000")
        assert c._base_url == "http://custom:9000"
        await c.aclose()


# ---------------------------------------------------------------------------
# Context manager edge cases
# ---------------------------------------------------------------------------


class TestAsyncClientContextManagerEdge:
    async def test_aclose_idempotent(self):
        c = AsyncFileOrganizerClient()
        c._client.aclose = AsyncMock()
        await c.aclose()
        await c.aclose()
        assert c._client.aclose.await_count == 2


# ---------------------------------------------------------------------------
# Optional parameter branches
# ---------------------------------------------------------------------------


class TestAsyncClientOptionalParams:
    async def test_register_without_full_name(self, client):
        resp = _mock_response(
            200,
            {
                "id": "1",
                "username": "u",
                "email": "e@e.com",
                "is_active": True,
                "is_admin": False,
                "created_at": NOW,
            },
        )
        client._client.post = AsyncMock(return_value=resp)
        result = await client.register("u", "e@e.com", "p")
        assert result.username == "u"
        # Verify full_name not in payload
        call_kwargs = client._client.post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert "full_name" not in payload

    async def test_list_files_no_file_type(self, client):
        resp = _mock_response(200, {"items": [], "total": 0, "skip": 0, "limit": 100})
        client._client.get = AsyncMock(return_value=resp)
        result = await client.list_files("/tmp")
        assert result.total == 0
        call_kwargs = client._client.get.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params")
        assert "file_type" not in params

    async def test_dedupe_scan_with_max_file_size(self, client):
        resp = _mock_response(200, {"path": "/tmp", "duplicates": [], "stats": {"total": 0}})
        client._client.post = AsyncMock(return_value=resp)
        result = await client.dedupe_scan("/tmp", max_file_size=1024)
        assert result.path == "/tmp"
        call_kwargs = client._client.post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert payload["max_file_size"] == 1024

    async def test_system_stats_no_max_depth(self, client):
        resp = _mock_response(
            200,
            {
                "total_size": 1000,
                "organized_size": 500,
                "saved_size": 200,
                "file_count": 10,
                "directory_count": 3,
                "size_by_type": {},
                "largest_files": [],
            },
        )
        client._client.get = AsyncMock(return_value=resp)
        result = await client.system_stats()
        assert result.file_count == 10
        call_kwargs = client._client.get.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params")
        assert "max_depth" not in params
