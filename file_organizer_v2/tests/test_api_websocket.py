"""API tests for WebSocket endpoints."""
from __future__ import annotations

from typing import Optional

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from file_organizer.api.config import ApiSettings
from file_organizer.api.main import create_app
from file_organizer.api.realtime import realtime_manager

pytestmark = pytest.mark.ci


def _client(token: Optional[str] = None) -> TestClient:
    settings = ApiSettings(
        environment="test",
        enable_docs=False,
        allowed_paths=[],
        websocket_token=token,
    )
    app = create_app(settings)
    return TestClient(app)


def test_websocket_connect_and_ping() -> None:
    client = _client()
    with client.websocket_connect("/api/v1/ws/test-client") as websocket:
        message = websocket.receive_json()
        assert message["type"] == "connection"
        assert message["status"] == "connected"
        websocket.send_json({"type": "ping"})
        response = websocket.receive_json()
        assert response["type"] == "pong"


def test_websocket_subscribe_and_broadcast() -> None:
    client = _client()
    with client.websocket_connect("/api/v1/ws/test-client") as websocket:
        websocket.receive_json()
        websocket.send_json({"type": "subscribe", "channel": "jobs"})
        ack = websocket.receive_json()
        assert ack["type"] == "subscribed"
        assert ack["channel"] == "jobs"

        enqueued = realtime_manager.enqueue_event(
            {"type": "job.updated", "job_id": "job-123"},
            channel="jobs",
        )
        assert enqueued is True
        event = None
        for _ in range(5):
            message = websocket.receive_json()
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
        message = websocket.receive_json()
        assert message["type"] == "connection"
