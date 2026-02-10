"""API tests for WebSocket endpoints."""
from __future__ import annotations

import json
from typing import Any, Optional

import anyio
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from file_organizer.api.config import ApiSettings
from file_organizer.api.main import create_app
from file_organizer.api.realtime import realtime_manager

pytestmark = pytest.mark.ci
_RECEIVE_TIMEOUT = 1.0


def _client(token: Optional[str] = None) -> TestClient:
    settings = ApiSettings(
        environment="test",
        enable_docs=False,
        allowed_paths=[],
        websocket_token=token,
    )
    app = create_app(settings)
    return TestClient(app)


def _receive_json(websocket: Any, timeout: float = _RECEIVE_TIMEOUT) -> dict[str, Any]:
    async def _receive() -> dict[str, Any]:
        with anyio.fail_after(timeout):
            message = await websocket._send_rx.receive()
        websocket._raise_on_close(message)
        text = message["text"]
        return json.loads(text)

    return websocket.portal.call(_receive)


def test_websocket_connect_and_ping() -> None:
    client = _client()
    with client.websocket_connect("/api/v1/ws/test-client") as websocket:
        message = _receive_json(websocket)
        assert message["type"] == "connection"
        assert message["status"] == "connected"
        websocket.send_json({"type": "ping"})
        response = _receive_json(websocket)
        assert response["type"] == "pong"


def test_websocket_subscribe_and_broadcast() -> None:
    client = _client()
    with client.websocket_connect("/api/v1/ws/test-client") as websocket:
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


def test_websocket_requires_token() -> None:
    client = _client(token="secret")
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/api/v1/ws/test-client"):
            pass


def test_websocket_accepts_valid_token() -> None:
    client = _client(token="secret")
    with client.websocket_connect("/api/v1/ws/test-client?token=secret") as websocket:
        message = _receive_json(websocket)
        assert message["type"] == "connection"


def test_websocket_accepts_header_token() -> None:
    client = _client(token="secret")
    with client.websocket_connect(
        "/api/v1/ws/test-client",
        headers={"Authorization": "Bearer secret"},
    ) as websocket:
        message = _receive_json(websocket)
        assert message["type"] == "connection"


def test_websocket_rejects_non_object_messages() -> None:
    client = _client()
    with client.websocket_connect("/api/v1/ws/test-client") as websocket:
        _receive_json(websocket)
        websocket.send_json(["invalid"])
        response = _receive_json(websocket)
        assert response["type"] == "error"
