"""Coverage tests for client.async_client module."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from file_organizer.client.async_client import AsyncFileOrganizerClient
from file_organizer.client.exceptions import (
    AuthenticationError,
    ClientError,
    NotFoundError,
    ServerError,
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


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


class TestAsyncClientAuth:
    async def test_login(self):
        client = AsyncFileOrganizerClient()
        resp = _mock_response(
            200,
            {
                "access_token": "tok",
                "refresh_token": "ref",
                "token_type": "bearer",
            },
        )
        client._client.post = AsyncMock(return_value=resp)
        result = await client.login("user", "pass")
        assert result.access_token == "tok"
        await client.aclose()

    async def test_register(self):
        client = AsyncFileOrganizerClient()
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
        await client.aclose()

    async def test_refresh_token(self):
        client = AsyncFileOrganizerClient()
        resp = _mock_response(
            200,
            {
                "access_token": "new",
                "refresh_token": "ref2",
                "token_type": "bearer",
            },
        )
        client._client.post = AsyncMock(return_value=resp)
        result = await client.refresh_token("ref1")
        assert result.access_token == "new"
        await client.aclose()

    async def test_logout(self):
        client = AsyncFileOrganizerClient()
        resp = _mock_response(200, {})
        client._client.post = AsyncMock(return_value=resp)
        await client.logout("ref1")  # Should not raise
        await client.aclose()

    async def test_me(self):
        client = AsyncFileOrganizerClient()
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
        await client.aclose()


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------


class TestAsyncClientFiles:
    async def test_list_files(self):
        client = AsyncFileOrganizerClient()
        resp = _mock_response(
            200,
            {
                "items": [],
                "total": 0,
                "skip": 0,
                "limit": 100,
            },
        )
        client._client.get = AsyncMock(return_value=resp)
        result = await client.list_files("/tmp", file_type="txt")
        assert result.total == 0
        await client.aclose()

    async def test_get_file_info(self):
        client = AsyncFileOrganizerClient()
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
        await client.aclose()

    async def test_read_file_content(self):
        client = AsyncFileOrganizerClient()
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
        await client.aclose()

    async def test_move_file(self):
        client = AsyncFileOrganizerClient()
        resp = _mock_response(
            200,
            {
                "source": "/a",
                "destination": "/b",
                "moved": True,
                "dry_run": False,
            },
        )
        client._client.post = AsyncMock(return_value=resp)
        result = await client.move_file("/a", "/b")
        assert result.moved is True
        await client.aclose()

    async def test_delete_file(self):
        client = AsyncFileOrganizerClient()
        resp = _mock_response(
            200,
            {
                "path": "/a",
                "deleted": True,
                "dry_run": False,
            },
        )
        client._client.request = AsyncMock(return_value=resp)
        result = await client.delete_file("/a")
        assert result.deleted is True
        await client.aclose()


# ---------------------------------------------------------------------------
# Organize
# ---------------------------------------------------------------------------


class TestAsyncClientOrganize:
    async def test_scan(self):
        client = AsyncFileOrganizerClient()
        resp = _mock_response(
            200,
            {
                "input_dir": "/tmp",
                "total_files": 5,
                "counts": {"txt": 5},
            },
        )
        client._client.post = AsyncMock(return_value=resp)
        result = await client.scan("/tmp")
        assert result.total_files == 5
        await client.aclose()

    async def test_preview_organize(self):
        client = AsyncFileOrganizerClient()
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
        await client.aclose()

    async def test_organize(self):
        client = AsyncFileOrganizerClient()
        resp = _mock_response(200, {"status": "queued", "job_id": "j1"})
        client._client.post = AsyncMock(return_value=resp)
        result = await client.organize("/in", "/out")
        assert result.job_id == "j1"
        await client.aclose()

    async def test_get_job(self):
        client = AsyncFileOrganizerClient()
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
        await client.aclose()


# ---------------------------------------------------------------------------
# System
# ---------------------------------------------------------------------------


class TestAsyncClientSystem:
    async def test_health(self):
        client = AsyncFileOrganizerClient()
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
        await client.aclose()

    async def test_system_status(self):
        client = AsyncFileOrganizerClient()
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
        await client.aclose()

    async def test_get_config(self):
        client = AsyncFileOrganizerClient()
        resp = _mock_response(
            200,
            {
                "profile": "default",
                "config": {},
                "profiles": ["default"],
            },
        )
        client._client.get = AsyncMock(return_value=resp)
        result = await client.get_config()
        assert result.profile == "default"
        await client.aclose()

    async def test_update_config(self):
        client = AsyncFileOrganizerClient()
        resp = _mock_response(
            200,
            {
                "profile": "default",
                "config": {"k": "v"},
                "profiles": ["default"],
            },
        )
        client._client.patch = AsyncMock(return_value=resp)
        result = await client.update_config({"k": "v"})
        assert result.config == {"k": "v"}
        await client.aclose()

    async def test_system_stats(self):
        client = AsyncFileOrganizerClient()
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
        await client.aclose()


# ---------------------------------------------------------------------------
# Dedupe
# ---------------------------------------------------------------------------


class TestAsyncClientDedupe:
    async def test_dedupe_scan(self):
        client = AsyncFileOrganizerClient()
        resp = _mock_response(
            200,
            {
                "path": "/tmp",
                "duplicates": [],
                "stats": {"total": 0},
            },
        )
        client._client.post = AsyncMock(return_value=resp)
        result = await client.dedupe_scan("/tmp")
        assert result.path == "/tmp"
        await client.aclose()

    async def test_dedupe_preview(self):
        client = AsyncFileOrganizerClient()
        resp = _mock_response(
            200,
            {
                "path": "/tmp",
                "preview": [],
                "stats": {"total": 0},
            },
        )
        client._client.post = AsyncMock(return_value=resp)
        result = await client.dedupe_preview("/tmp")
        assert result.path == "/tmp"
        await client.aclose()

    async def test_dedupe_execute(self):
        client = AsyncFileOrganizerClient()
        resp = _mock_response(
            200,
            {
                "path": "/tmp",
                "removed": [],
                "dry_run": True,
                "stats": {"total": 0},
            },
        )
        client._client.post = AsyncMock(return_value=resp)
        result = await client.dedupe_execute("/tmp")
        assert result.dry_run is True
        await client.aclose()


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------


class TestAsyncClientContextManager:
    async def test_async_context_manager(self):
        client = AsyncFileOrganizerClient()
        client._client.aclose = AsyncMock()

        async with client as c:
            assert c is client

        client._client.aclose.assert_awaited_once()


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestAsyncClientErrorHandling:
    async def test_401_raises_auth_error(self):
        client = AsyncFileOrganizerClient()
        resp = _mock_response(401, {"detail": "unauthorized"})
        client._client.get = AsyncMock(return_value=resp)
        with pytest.raises(AuthenticationError, match="401"):
            await client.health()
        await client.aclose()

    async def test_404_raises_not_found(self):
        client = AsyncFileOrganizerClient()
        resp = _mock_response(404, {"detail": "not found"})
        client._client.get = AsyncMock(return_value=resp)
        with pytest.raises(NotFoundError, match="404"):
            await client.get_file_info("/missing")
        await client.aclose()

    async def test_500_raises_server_error(self):
        client = AsyncFileOrganizerClient()
        resp = _mock_response(500, {"detail": "internal error"})
        client._client.get = AsyncMock(return_value=resp)
        with pytest.raises(ServerError, match="500"):
            await client.health()
        await client.aclose()

    async def test_generic_4xx_raises_client_error(self):
        client = AsyncFileOrganizerClient()
        resp = _mock_response(400, {"detail": "bad request"})
        client._client.get = AsyncMock(return_value=resp)
        with pytest.raises(ClientError, match="400"):
            await client.health()
        await client.aclose()

    async def test_set_token(self):
        client = AsyncFileOrganizerClient()
        client.set_token("new-token")
        assert client._client.headers["Authorization"] == "Bearer new-token"
        await client.aclose()

    async def test_init_with_api_key_and_token(self):
        client = AsyncFileOrganizerClient(
            api_key="key123",
            token="tok456",
        )
        assert "X-API-Key" in client._client.headers
        assert "Authorization" in client._client.headers
        await client.aclose()
