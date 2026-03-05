"""Coverage tests for AsyncFileOrganizerClient."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import httpx
import pytest

from file_organizer.client.async_client import AsyncFileOrganizerClient
from file_organizer.client.exceptions import (
    AuthenticationError,
    ClientError,
    NotFoundError,
    ServerError,
    ValidationError,
)

pytestmark = pytest.mark.unit

_NOW = datetime.now(tz=UTC).isoformat()


def _ok(body: dict, status: int = 200) -> httpx.Response:
    """Build a successful httpx.Response from a dict body."""
    return httpx.Response(
        status_code=status, json=body, request=httpx.Request("GET", "http://test")
    )


def _err(status: int, detail: str = "error") -> httpx.Response:
    return httpx.Response(
        status_code=status,
        json={"detail": detail},
        request=httpx.Request("GET", "http://test"),
    )


@pytest.mark.asyncio
class TestAsyncClientAuth:
    async def test_login(self):
        client = AsyncFileOrganizerClient(base_url="http://test")
        resp = _ok({"access_token": "tok", "refresh_token": "ref", "token_type": "bearer"})
        client._client = AsyncMock()
        client._client.post = AsyncMock(return_value=resp)

        tokens = await client.login("user", "pass")
        assert tokens.access_token == "tok"
        assert tokens.refresh_token == "ref"

    async def test_register(self):
        client = AsyncFileOrganizerClient()
        resp = _ok(
            {
                "id": "1",
                "username": "u",
                "email": "e@e.com",
                "is_active": True,
                "is_admin": False,
                "created_at": _NOW,
            }
        )
        client._client = AsyncMock()
        client._client.post = AsyncMock(return_value=resp)

        user = await client.register("u", "e@e.com", "p", full_name="F")
        assert user.username == "u"

    async def test_register_without_full_name(self):
        client = AsyncFileOrganizerClient()
        resp = _ok(
            {
                "id": "1",
                "username": "u",
                "email": "e@e.com",
                "is_active": True,
                "is_admin": False,
                "created_at": _NOW,
            }
        )
        client._client = AsyncMock()
        client._client.post = AsyncMock(return_value=resp)

        user = await client.register("u", "e@e.com", "p")
        assert user.username == "u"

    async def test_refresh_token(self):
        client = AsyncFileOrganizerClient()
        resp = _ok({"access_token": "new_tok", "refresh_token": "new_ref", "token_type": "bearer"})
        client._client = AsyncMock()
        client._client.post = AsyncMock(return_value=resp)

        tokens = await client.refresh_token("old_ref")
        assert tokens.access_token == "new_tok"

    async def test_me(self):
        client = AsyncFileOrganizerClient()
        resp = _ok(
            {
                "id": "1",
                "username": "me",
                "email": "me@e.com",
                "is_active": True,
                "is_admin": False,
                "created_at": _NOW,
            }
        )
        client._client = AsyncMock()
        client._client.get = AsyncMock(return_value=resp)

        user = await client.me()
        assert user.username == "me"

    async def test_logout(self):
        client = AsyncFileOrganizerClient()
        resp = _ok({})
        client._client = AsyncMock()
        client._client.post = AsyncMock(return_value=resp)

        await client.logout("ref")


@pytest.mark.asyncio
class TestAsyncClientFiles:
    async def test_list_files(self):
        client = AsyncFileOrganizerClient()
        resp = _ok(
            {
                "items": [
                    {
                        "path": "/f.txt",
                        "name": "f.txt",
                        "size": 100,
                        "created": _NOW,
                        "modified": _NOW,
                        "file_type": "txt",
                    }
                ],
                "total": 1,
                "skip": 0,
                "limit": 100,
            }
        )
        client._client = AsyncMock()
        client._client.get = AsyncMock(return_value=resp)

        result = await client.list_files("/tmp", file_type="txt")
        assert result.total == 1

    async def test_get_file_info(self):
        client = AsyncFileOrganizerClient()
        resp = _ok(
            {
                "path": "/f.txt",
                "name": "f.txt",
                "size": 100,
                "created": _NOW,
                "modified": _NOW,
                "file_type": "txt",
            }
        )
        client._client = AsyncMock()
        client._client.get = AsyncMock(return_value=resp)

        info = await client.get_file_info("/f.txt")
        assert info.name == "f.txt"

    async def test_read_file_content(self):
        client = AsyncFileOrganizerClient()
        resp = _ok(
            {
                "path": "/f.txt",
                "content": "hello",
                "encoding": "utf-8",
                "truncated": False,
                "size": 5,
            }
        )
        client._client = AsyncMock()
        client._client.get = AsyncMock(return_value=resp)

        content = await client.read_file_content("/f.txt")
        assert content.content == "hello"

    async def test_move_file(self):
        client = AsyncFileOrganizerClient()
        resp = _ok({"source": "/a", "destination": "/b", "moved": True, "dry_run": False})
        client._client = AsyncMock()
        client._client.post = AsyncMock(return_value=resp)

        result = await client.move_file("/a", "/b")
        assert result.moved is True

    async def test_delete_file(self):
        client = AsyncFileOrganizerClient()
        resp = _ok({"path": "/f.txt", "deleted": True, "dry_run": False})
        client._client = AsyncMock()
        client._client.request = AsyncMock(return_value=resp)

        result = await client.delete_file("/f.txt", permanent=True)
        assert result.deleted is True


@pytest.mark.asyncio
class TestAsyncClientOrganize:
    async def test_scan(self):
        client = AsyncFileOrganizerClient()
        resp = _ok({"input_dir": "/tmp", "total_files": 10, "counts": {"txt": 5}})
        client._client = AsyncMock()
        client._client.post = AsyncMock(return_value=resp)

        result = await client.scan("/tmp")
        assert result.total_files == 10

    async def test_preview_organize(self):
        client = AsyncFileOrganizerClient()
        resp = _ok(
            {
                "total_files": 5,
                "processed_files": 5,
                "skipped_files": 0,
                "failed_files": 0,
                "processing_time": 1.0,
                "organized_structure": {},
                "errors": [],
            }
        )
        client._client = AsyncMock()
        client._client.post = AsyncMock(return_value=resp)

        result = await client.preview_organize("/in", "/out")
        assert result.total_files == 5

    async def test_organize(self):
        client = AsyncFileOrganizerClient()
        resp = _ok({"status": "queued", "job_id": "j1"})
        client._client = AsyncMock()
        client._client.post = AsyncMock(return_value=resp)

        result = await client.organize("/in", "/out")
        assert result.job_id == "j1"

    async def test_get_job(self):
        client = AsyncFileOrganizerClient()
        resp = _ok(
            {
                "job_id": "j1",
                "status": "completed",
                "created_at": _NOW,
                "updated_at": _NOW,
            }
        )
        client._client = AsyncMock()
        client._client.get = AsyncMock(return_value=resp)

        result = await client.get_job("j1")
        assert result.status == "completed"


@pytest.mark.asyncio
class TestAsyncClientSystem:
    async def test_health(self):
        client = AsyncFileOrganizerClient()
        resp = _ok(
            {
                "status": "ok",
                "readiness": "ready",
                "version": "2.0",
                "ollama": True,
                "uptime": 100.0,
            }
        )
        client._client = AsyncMock()
        client._client.get = AsyncMock(return_value=resp)

        health = await client.health()
        assert health.status == "ok"

    async def test_system_status(self):
        client = AsyncFileOrganizerClient()
        resp = _ok(
            {
                "app": "fo",
                "version": "2.0",
                "environment": "dev",
                "disk_total": 100,
                "disk_used": 50,
                "disk_free": 50,
                "active_jobs": 0,
            }
        )
        client._client = AsyncMock()
        client._client.get = AsyncMock(return_value=resp)

        result = await client.system_status()
        assert result.version == "2.0"

    async def test_get_config(self):
        client = AsyncFileOrganizerClient()
        resp = _ok({"profile": "default", "config": {}, "profiles": ["default"]})
        client._client = AsyncMock()
        client._client.get = AsyncMock(return_value=resp)

        result = await client.get_config()
        assert result.profile == "default"

    async def test_update_config(self):
        client = AsyncFileOrganizerClient()
        resp = _ok({"profile": "default", "config": {"key": "val"}, "profiles": ["default"]})
        client._client = AsyncMock()
        client._client.patch = AsyncMock(return_value=resp)

        result = await client.update_config({"key": "val"})
        assert result.config["key"] == "val"

    async def test_system_stats(self):
        client = AsyncFileOrganizerClient()
        resp = _ok(
            {
                "total_size": 1000,
                "organized_size": 500,
                "saved_size": 100,
                "file_count": 50,
                "directory_count": 5,
                "size_by_type": {},
                "largest_files": [],
            }
        )
        client._client = AsyncMock()
        client._client.get = AsyncMock(return_value=resp)

        result = await client.system_stats(max_depth=2)
        assert result.file_count == 50


@pytest.mark.asyncio
class TestAsyncClientDedupe:
    async def test_dedupe_scan(self):
        client = AsyncFileOrganizerClient()
        resp = _ok({"path": "/tmp", "duplicates": [], "stats": {"total": 0}})
        client._client = AsyncMock()
        client._client.post = AsyncMock(return_value=resp)

        result = await client.dedupe_scan("/tmp", max_file_size=1000)
        assert result.path == "/tmp"

    async def test_dedupe_preview(self):
        client = AsyncFileOrganizerClient()
        resp = _ok({"path": "/tmp", "preview": [], "stats": {"total": 0}})
        client._client = AsyncMock()
        client._client.post = AsyncMock(return_value=resp)

        result = await client.dedupe_preview("/tmp")
        assert result.path == "/tmp"

    async def test_dedupe_execute(self):
        client = AsyncFileOrganizerClient()
        resp = _ok({"path": "/tmp", "removed": [], "dry_run": True, "stats": {"total": 0}})
        client._client = AsyncMock()
        client._client.post = AsyncMock(return_value=resp)

        result = await client.dedupe_execute("/tmp")
        assert result.dry_run is True


@pytest.mark.asyncio
class TestAsyncClientContextManager:
    async def test_async_context_manager(self):
        async with AsyncFileOrganizerClient() as client:
            assert client is not None

    async def test_aclose(self):
        client = AsyncFileOrganizerClient()
        client._client = AsyncMock()
        client._client.aclose = AsyncMock()
        await client.aclose()
        client._client.aclose.assert_awaited_once()


@pytest.mark.asyncio
class TestAsyncClientErrorHandling:
    async def test_401_raises_authentication_error(self):
        client = AsyncFileOrganizerClient()
        client._client = AsyncMock()
        client._client.get = AsyncMock(return_value=_err(401, "unauthorized"))

        with pytest.raises(AuthenticationError):
            await client.health()

    async def test_403_raises_authentication_error(self):
        client = AsyncFileOrganizerClient()
        client._client = AsyncMock()
        client._client.get = AsyncMock(return_value=_err(403, "forbidden"))

        with pytest.raises(AuthenticationError):
            await client.health()

    async def test_404_raises_not_found_error(self):
        client = AsyncFileOrganizerClient()
        client._client = AsyncMock()
        client._client.get = AsyncMock(return_value=_err(404, "not found"))

        with pytest.raises(NotFoundError):
            await client.health()

    async def test_422_raises_validation_error(self):
        client = AsyncFileOrganizerClient()
        client._client = AsyncMock()
        client._client.get = AsyncMock(return_value=_err(422, "invalid"))

        with pytest.raises(ValidationError):
            await client.health()

    async def test_500_raises_server_error(self):
        client = AsyncFileOrganizerClient()
        client._client = AsyncMock()
        client._client.get = AsyncMock(return_value=_err(500, "internal"))

        with pytest.raises(ServerError):
            await client.health()

    async def test_400_raises_client_error(self):
        client = AsyncFileOrganizerClient()
        client._client = AsyncMock()
        client._client.get = AsyncMock(return_value=_err(400, "bad request"))

        with pytest.raises(ClientError):
            await client.health()

    async def test_error_with_non_json_body(self):
        """Non-JSON error body should use response text."""
        resp = httpx.Response(
            status_code=502,
            text="Bad Gateway",
            request=httpx.Request("GET", "http://test"),
        )
        client = AsyncFileOrganizerClient()
        client._client = AsyncMock()
        client._client.get = AsyncMock(return_value=resp)

        with pytest.raises(ServerError):
            await client.health()


@pytest.mark.asyncio
class TestAsyncClientSetToken:
    async def test_set_token_updates_header(self):
        client = AsyncFileOrganizerClient()
        client.set_token("new_token")
        assert client._client.headers["Authorization"] == "Bearer new_token"


class TestAsyncClientInitHeaders:
    def test_init_with_token(self):
        client = AsyncFileOrganizerClient(token="my_token")
        assert "Authorization" in client._client.headers

    def test_init_with_api_key(self):
        client = AsyncFileOrganizerClient(api_key="my_key")
        assert "X-API-Key" in client._client.headers
