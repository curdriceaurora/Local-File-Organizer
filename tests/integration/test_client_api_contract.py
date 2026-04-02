"""Integration-style contract tests for sync and async API clients."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from file_organizer.client.async_client import AsyncFileOrganizerClient
from file_organizer.client.exceptions import (
    AuthenticationError,
    NotFoundError,
    ServerError,
    ValidationError,
)
from file_organizer.client.sync_client import FileOrganizerClient

pytestmark = pytest.mark.integration


def _file_info_payload(path: str) -> dict[str, Any]:
    now = datetime.now(UTC).isoformat()
    return {
        "path": path,
        "name": Path(path).name,
        "size": 12,
        "created": now,
        "modified": now,
        "file_type": "text",
        "mime_type": "text/plain",
    }


def _json_payload(request: httpx.Request) -> dict[str, Any]:
    return json.loads(request.content.decode("utf-8"))


def _ok_response(payload: dict[str, Any]) -> httpx.Response:
    return httpx.Response(200, json=payload)


def _handle_files_request(request: httpx.Request, path: str) -> httpx.Response | None:
    if path.endswith("/files") and request.method == "GET":
        requested_path = request.url.params["path"]
        return _ok_response(
            {
                "items": [_file_info_payload(str(Path(requested_path) / "alpha.txt"))],
                "total": 1,
                "skip": 0,
                "limit": 100,
            }
        )
    if path.endswith("/files/content"):
        requested_path = request.url.params["path"]
        return _ok_response(
            {
                "path": requested_path,
                "content": "hello world",
                "encoding": request.url.params.get("encoding", "utf-8"),
                "truncated": False,
                "size": 11,
                "mime_type": "text/plain",
            }
        )
    if path.endswith("/files/move"):
        payload = _json_payload(request)
        return _ok_response(
            {
                "source": payload["source"],
                "destination": payload["destination"],
                "moved": True,
                "dry_run": payload["dry_run"],
            }
        )
    if path.endswith("/files") and request.method == "DELETE":
        payload = _json_payload(request)
        return _ok_response(
            {
                "path": payload["path"],
                "deleted": True,
                "dry_run": payload["dry_run"],
                "trashed_path": None if payload["permanent"] else f"{payload['path']}.trash",
            }
        )
    return None


def _handle_organize_request(request: httpx.Request, path: str) -> httpx.Response | None:
    if path.endswith("/organize/scan"):
        payload = _json_payload(request)
        return _ok_response(
            {
                "input_dir": payload["input_dir"],
                "total_files": 3,
                "counts": {"text": 2, "image": 1},
            }
        )
    if path.endswith("/organize/preview"):
        return _ok_response(
            {
                "total_files": 3,
                "processed_files": 3,
                "skipped_files": 0,
                "failed_files": 0,
                "processing_time": 0.12,
                "organized_structure": {"documents": ["alpha.txt", "beta.txt"]},
                "errors": [],
            }
        )
    if path.endswith("/organize/execute"):
        payload = _json_payload(request)
        if payload["run_in_background"]:
            return _ok_response({"status": "queued", "job_id": "job-123"})
        return _ok_response(
            {
                "status": "completed",
                "result": {
                    "total_files": 1,
                    "processed_files": 1,
                    "skipped_files": 0,
                    "failed_files": 0,
                    "processing_time": 0.05,
                    "organized_structure": {"documents": ["gamma.txt"]},
                    "errors": [],
                },
                "job_id": None,
                "error": None,
            }
        )
    if "/organize/status/" in path:
        return _ok_response(
            {
                "job_id": path.rsplit("/", 1)[-1],
                "status": "completed",
                "created_at": datetime.now(UTC).isoformat(),
                "updated_at": datetime.now(UTC).isoformat(),
                "result": {
                    "total_files": 1,
                    "processed_files": 1,
                    "skipped_files": 0,
                    "failed_files": 0,
                    "processing_time": 0.05,
                    "organized_structure": {"documents": ["gamma.txt"]},
                    "errors": [],
                },
                "error": None,
            }
        )
    return None


def _handle_system_request(request: httpx.Request, path: str) -> httpx.Response | None:
    if path.endswith("/system/status"):
        return _ok_response(
            {
                "app": "file-organizer",
                "version": "2.0.0",
                "environment": "test",
                "disk_total": 1000,
                "disk_used": 250,
                "disk_free": 750,
                "active_jobs": 2,
            }
        )
    if path.endswith("/system/stats"):
        requested_path = request.url.params["path"]
        return _ok_response(
            {
                "total_size": 2048,
                "organized_size": 1024,
                "saved_size": 512,
                "file_count": 4,
                "directory_count": 2,
                "size_by_type": {"text": 1024, "image": 1024},
                "largest_files": [_file_info_payload(str(Path(requested_path) / "large.txt"))],
            }
        )
    if path.endswith("/system/config") and request.method == "GET":
        return _ok_response(
            {
                "profile": "default",
                "config": {"organization_method": "para"},
                "profiles": ["default"],
            }
        )
    if path.endswith("/system/config") and request.method == "PATCH":
        payload = request.read().decode("utf-8")
        return _ok_response(
            {
                "profile": "default",
                "config": {"raw_payload": payload},
                "profiles": ["default"],
            }
        )
    return None


def _handle_dedupe_request(request: httpx.Request, path: str) -> httpx.Response | None:
    if path.endswith("/dedupe/scan"):
        payload = _json_payload(request)
        return _ok_response(
            {
                "path": payload["path"],
                "duplicates": [{"keep": "a.txt", "remove": ["a-copy.txt"]}],
                "stats": {"groups": 1, "files": 2},
            }
        )
    if path.endswith("/dedupe/preview"):
        payload = _json_payload(request)
        return _ok_response(
            {
                "path": payload["path"],
                "preview": [{"keep": "a.txt", "remove": ["a-copy.txt"]}],
                "stats": {"groups": 1, "files": 2},
            }
        )
    if path.endswith("/dedupe/execute"):
        payload = _json_payload(request)
        return _ok_response(
            {
                "path": payload["path"],
                "removed": [] if payload["dry_run"] else ["a-copy.txt"],
                "dry_run": payload["dry_run"],
                "stats": {"removed": 0 if payload["dry_run"] else 1},
            }
        )
    return None


def _mock_handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path.endswith("/health"):
        return _ok_response(
            {
                "status": "ok",
                "readiness": "ready",
                "version": "2.0.0",
                "ollama": False,
                "uptime": 1.5,
            }
        )
    for handler in (
        _handle_files_request,
        _handle_organize_request,
        _handle_system_request,
        _handle_dedupe_request,
    ):
        response = handler(request, path)
        if response is not None:
            return response
    if "auth-401" in path:
        return httpx.Response(401, json={"message": "unauthorized"})
    if "not-found-404" in path:
        return httpx.Response(404, json={"message": "missing"})
    if "invalid-422" in path:
        return httpx.Response(422, json={"detail": "bad payload"})
    if "server-500" in path:
        return httpx.Response(500, json={"message": "exploded"})
    return httpx.Response(200, json={})


def _sync_client() -> FileOrganizerClient:
    client = FileOrganizerClient.__new__(FileOrganizerClient)
    client._base_url = "http://test"
    client._client = httpx.Client(
        transport=httpx.MockTransport(_mock_handler),
        base_url="http://test",
    )
    return client


def _async_client() -> AsyncFileOrganizerClient:
    client = AsyncFileOrganizerClient.__new__(AsyncFileOrganizerClient)
    client._base_url = "http://test"
    client._client = httpx.AsyncClient(
        transport=httpx.MockTransport(_mock_handler),
        base_url="http://test",
    )
    return client


def test_sync_client_maps_success_responses() -> None:
    client = _sync_client()

    health = client.health()
    assert health.status == "ok"

    files = client.list_files("/workspace")
    assert files.total == 1
    assert files.items[0].name == "alpha.txt"

    content = client.read_file_content("/workspace/alpha.txt")
    assert content.content == "hello world"

    moved = client.move_file("/workspace/alpha.txt", "/workspace/archive/alpha.txt", dry_run=True)
    assert moved.dry_run is True

    deleted = client.delete_file("/workspace/alpha.txt", dry_run=True)
    assert deleted.trashed_path == "/workspace/alpha.txt.trash"

    scan = client.scan("/workspace")
    assert scan.counts["text"] == 2

    preview = client.preview_organize("/workspace/in", "/workspace/out")
    assert preview.processed_files == 3

    execute = client.organize("/workspace/in", "/workspace/out")
    assert execute.job_id == "job-123"

    completed = client.organize(
        "/workspace/in",
        "/workspace/out",
        run_in_background=False,
    )
    assert completed.result is not None
    assert completed.result.organized_structure["documents"] == ["gamma.txt"]

    job = client.get_job("job-123")
    assert job.status == "completed"

    status = client.system_status("/workspace")
    assert status.active_jobs == 2

    config = client.get_config()
    assert config.profile == "default"

    updated = client.update_config({"organization_method": "johnny_decimal"})
    assert "organization_method" in updated.config["raw_payload"]

    stats = client.system_stats(path="/workspace", max_depth=2)
    assert stats.total_size == 2048
    assert stats.largest_files[0].name == "large.txt"

    dedupe_scan = client.dedupe_scan("/workspace")
    assert dedupe_scan.stats["groups"] == 1

    dedupe_preview = client.dedupe_preview("/workspace")
    assert dedupe_preview.preview[0]["keep"] == "a.txt"

    dedupe_execute = client.dedupe_execute("/workspace", dry_run=False)
    assert dedupe_execute.removed == ["a-copy.txt"]
    client.close()


@pytest.mark.asyncio
async def test_async_client_maps_success_responses() -> None:
    client = _async_client()

    health = await client.health()
    assert health.status == "ok"

    files = await client.list_files("/workspace")
    assert files.total == 1
    assert files.items[0].name == "alpha.txt"

    content = await client.read_file_content("/workspace/alpha.txt")
    assert content.mime_type == "text/plain"

    moved = await client.move_file(
        "/workspace/alpha.txt",
        "/workspace/archive/alpha.txt",
        dry_run=True,
    )
    assert moved.moved is True

    deleted = await client.delete_file("/workspace/alpha.txt", dry_run=True)
    assert deleted.deleted is True

    scan = await client.scan("/workspace")
    assert scan.total_files == 3

    preview = await client.preview_organize("/workspace/in", "/workspace/out")
    assert preview.failed_files == 0

    execute = await client.organize("/workspace/in", "/workspace/out")
    assert execute.status == "queued"

    completed = await client.organize(
        "/workspace/in",
        "/workspace/out",
        run_in_background=False,
    )
    assert completed.result is not None
    assert completed.result.total_files == 1

    job = await client.get_job("job-123")
    assert job.job_id == "job-123"

    status = await client.system_status("/workspace")
    assert status.disk_free == 750

    config = await client.get_config()
    assert config.profile == "default"

    updated = await client.update_config({"organization_method": "para"})
    assert "organization_method" in updated.config["raw_payload"]

    stats = await client.system_stats(path="/workspace", max_depth=1)
    assert stats.directory_count == 2

    dedupe_scan = await client.dedupe_scan("/workspace")
    assert dedupe_scan.duplicates[0]["remove"] == ["a-copy.txt"]

    dedupe_preview = await client.dedupe_preview("/workspace")
    assert dedupe_preview.stats["files"] == 2

    dedupe_execute = await client.dedupe_execute("/workspace", dry_run=False)
    assert dedupe_execute.stats["removed"] == 1
    await client.aclose()


def test_sync_client_error_mapping() -> None:
    client = _sync_client()
    with pytest.raises(AuthenticationError):
        client._raise_for_status(httpx.Response(401, json={"message": "unauthorized"}))
    with pytest.raises(NotFoundError):
        client._raise_for_status(httpx.Response(404, json={"message": "missing"}))
    with pytest.raises(ValidationError):
        client._raise_for_status(httpx.Response(422, json={"detail": "bad payload"}))
    with pytest.raises(ServerError):
        client._raise_for_status(httpx.Response(500, json={"message": "exploded"}))
    client.close()


@pytest.mark.asyncio
async def test_async_client_error_mapping() -> None:
    client = _async_client()
    with pytest.raises(AuthenticationError):
        client._raise_for_status(httpx.Response(401, json={"message": "unauthorized"}))
    with pytest.raises(NotFoundError):
        client._raise_for_status(httpx.Response(404, json={"message": "missing"}))
    with pytest.raises(ValidationError):
        client._raise_for_status(httpx.Response(422, json={"detail": "bad payload"}))
    with pytest.raises(ServerError):
        client._raise_for_status(httpx.Response(500, json={"message": "exploded"}))
    await client.aclose()
