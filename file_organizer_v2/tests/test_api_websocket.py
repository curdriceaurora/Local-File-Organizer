"""API tests for WebSocket endpoints."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from pathlib import Path
from typing import Any, Optional

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from file_organizer.api.realtime import realtime_manager
from file_organizer.api.test_utils import create_auth_client

pytestmark = pytest.mark.ci
_RECEIVE_TIMEOUT = 1.0


def _client(tmp_path: Path, token: Optional[str] = None) -> tuple[TestClient, str]:
    client, _, tokens = create_auth_client(tmp_path, [], websocket_token=token)
    return client, tokens["access_token"]


def _receive_json(websocket: Any, timeout: float = _RECEIVE_TIMEOUT) -> dict[str, Any]:
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(websocket.receive_json)
        try:
            return future.result(timeout=timeout)
        except FutureTimeout as exc:
            future.cancel()
            raise AssertionError(
                f"Timed out waiting for websocket message after {timeout:.2f}s"
            ) from exc


def _broadcast_sync(payload: dict[str, Any], channel: str = "global") -> None:
    loop = realtime_manager._loop
    assert loop is not None
    future = asyncio.run_coroutine_threadsafe(
        realtime_manager.broadcast(payload, channel=channel),
        loop,
    )
    future.result(timeout=2.0)


def test_websocket_connect_and_ping(tmp_path: Path) -> None:
    client, access_token = _client(tmp_path)
    with client.websocket_connect(
        "/api/v1/ws/test-client",
        headers={"Authorization": f"Bearer {access_token}"},
    ) as websocket:
        message = _receive_json(websocket)
        assert message["type"] == "connection"
        assert message["status"] == "connected"
        websocket.send_json({"type": "ping"})
        response = _receive_json(websocket)
        assert response["type"] == "pong"


def test_websocket_subscribe_and_broadcast(tmp_path: Path) -> None:
    client, access_token = _client(tmp_path)
    with client.websocket_connect(
        "/api/v1/ws/test-client",
        headers={"Authorization": f"Bearer {access_token}"},
    ) as websocket:
        _receive_json(websocket)
        websocket.send_json({"type": "subscribe", "channel": "jobs"})
        ack = _receive_json(websocket)
        assert ack["type"] == "subscribed"
        assert ack["channel"] == "jobs"

        enqueued = realtime_manager.enqueue_event(
            {"type": "job.updated", "job_id": "job-123"},
            channel="jobs",
        )
        assert enqueued is True
        event = None
        for _ in range(5):
            message = _receive_json(websocket)
            if message.get("type") == "job.updated":
                event = message
                break
        assert event is not None
        assert event["job_id"] == "job-123"


def test_websocket_requires_token(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/api/v1/ws/test-client"):
            pass


def test_websocket_accepts_valid_token(tmp_path: Path) -> None:
    client, access_token = _client(tmp_path)
    with client.websocket_connect(f"/api/v1/ws/test-client?token={access_token}") as websocket:
        message = _receive_json(websocket)
        assert message["type"] == "connection"


def test_websocket_accepts_header_token(tmp_path: Path) -> None:
    client, access_token = _client(tmp_path)
    with client.websocket_connect(
        "/api/v1/ws/test-client",
        headers={"Authorization": f"Bearer {access_token}"},
    ) as websocket:
        message = _receive_json(websocket)
        assert message["type"] == "connection"


def test_websocket_accepts_shared_secret(tmp_path: Path) -> None:
    client, _, _ = create_auth_client(tmp_path, [], websocket_token="secret")
    with client.websocket_connect("/api/v1/ws/test-client?token=secret") as websocket:
        message = _receive_json(websocket)
        assert message["type"] == "connection"


def test_websocket_rejects_non_object_messages(tmp_path: Path) -> None:
    client, access_token = _client(tmp_path)
    with client.websocket_connect(
        "/api/v1/ws/test-client",
        headers={"Authorization": f"Bearer {access_token}"},
    ) as websocket:
        _receive_json(websocket)
        websocket.send_json(["invalid"])
        response = _receive_json(websocket)
        assert response["type"] == "error"


def test_websocket_ignores_pong(tmp_path: Path) -> None:
    client, access_token = _client(tmp_path)
    with client.websocket_connect(
        "/api/v1/ws/test-client",
        headers={"Authorization": f"Bearer {access_token}"},
    ) as websocket:
        _receive_json(websocket)
        websocket.send_json({"type": "pong"})
        websocket.send_json({"type": "subscribe", "channel": "jobs"})
        response = _receive_json(websocket)
        assert response["type"] == "subscribed"


def test_websocket_rejects_invalid_channel(tmp_path: Path) -> None:
    client, access_token = _client(tmp_path)
    with client.websocket_connect(
        "/api/v1/ws/test-client",
        headers={"Authorization": f"Bearer {access_token}"},
    ) as websocket:
        _receive_json(websocket)
        websocket.send_json({"type": "subscribe", "channel": {}})
        response = _receive_json(websocket)
        assert response["type"] == "error"


def test_websocket_global_broadcast_reaches_all(tmp_path: Path) -> None:
    client, access_token = _client(tmp_path)
    headers = {"Authorization": f"Bearer {access_token}"}
    with (
        client.websocket_connect(
            "/api/v1/ws/first",
            headers=headers,
        ) as first,
        client.websocket_connect(
            "/api/v1/ws/second",
            headers=headers,
        ) as second,
    ):
        _receive_json(first)
        _receive_json(second)
        _broadcast_sync({"type": "announcement"}, channel="global")
        first_msg = None
        for _ in range(5):
            message = _receive_json(first, timeout=2.0)
            if message.get("type") == "announcement":
                first_msg = message
                break
        second_msg = None
        for _ in range(5):
            message = _receive_json(second, timeout=2.0)
            if message.get("type") == "announcement":
                second_msg = message
                break
        assert first_msg is not None
        assert second_msg is not None
