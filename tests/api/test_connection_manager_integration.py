"""Integration tests for ConnectionManager in api/realtime.py.

Uses a real FastAPI app + Starlette TestClient WebSocket to exercise
the full async connect/subscribe/broadcast/disconnect lifecycle.
"""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI, WebSocket
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from file_organizer.api.realtime import ConnectionManager


def _make_ws_app() -> tuple[FastAPI, ConnectionManager]:
    """Build a minimal FastAPI app that exposes a WebSocket using ConnectionManager."""
    manager = ConnectionManager()
    app = FastAPI()

    @app.websocket("/ws/{client_id}")
    async def ws_endpoint(websocket: WebSocket, client_id: str):
        await manager.connect(websocket, client_id)
        try:
            while True:
                data = await websocket.receive_text()
                msg = json.loads(data)
                if msg.get("type") == "subscribe":
                    await manager.subscribe(websocket, msg["channel"])
                elif msg.get("type") == "unsubscribe":
                    await manager.unsubscribe(websocket, msg["channel"])
                elif msg.get("type") == "broadcast":
                    await manager.broadcast(msg["payload"], msg.get("channel", "global"))
                elif msg.get("type") == "disconnect":
                    break
        except WebSocketDisconnect:
            pass
        finally:
            await manager.disconnect(websocket)

    return app, manager


@pytest.mark.integration
class TestConnectionManagerLifecycle:
    """Full connect / subscribe / broadcast / disconnect via real WebSocket."""

    @pytest.mark.ci
    def test_connect_and_receive_broadcast(self):
        app, _ = _make_ws_app()
        with TestClient(app) as client:
            with client.websocket_connect("/ws/client1") as ws:
                # Consume the initial "connection" message sent by connect()
                ws.receive_text()
                ws.send_text(json.dumps({"type": "subscribe", "channel": "global"}))
                ws.send_text(
                    json.dumps(
                        {
                            "type": "broadcast",
                            "payload": {"event": "test"},
                            "channel": "global",
                        }
                    )
                )
                msg = ws.receive_text()
                data = json.loads(msg)
                assert data["event"] == "test"

    def test_disconnect_removes_client(self):
        app, manager = _make_ws_app()
        with TestClient(app) as client:
            with client.websocket_connect("/ws/cdisc"):
                pass  # connect then close
        assert len(manager._connections) == 0

    def test_subscribe_then_unsubscribe(self):
        app, _ = _make_ws_app()
        with TestClient(app) as client:
            with client.websocket_connect("/ws/csub") as ws:
                # Consume the initial connection message
                ws.receive_text()
                ws.send_text(json.dumps({"type": "subscribe", "channel": "news"}))
                ws.send_text(json.dumps({"type": "unsubscribe", "channel": "news"}))
                # No error expected — just verifying it doesn't raise

    @pytest.mark.ci
    def test_broadcast_to_named_channel_reaches_subscriber(self):
        """Client subscribed to a named channel receives broadcasts on that channel."""
        app, _ = _make_ws_app()
        with TestClient(app) as client:
            with client.websocket_connect("/ws/cnamed") as ws:
                ws.receive_text()  # initial connection message
                ws.send_text(json.dumps({"type": "subscribe", "channel": "alpha"}))
                ws.send_text(
                    json.dumps(
                        {
                            "type": "broadcast",
                            "payload": {"event": "named"},
                            "channel": "alpha",
                        }
                    )
                )
                msg = ws.receive_text()
                data = json.loads(msg)
                assert data["event"] == "named"

    @pytest.mark.ci
    def test_enqueue_event_returns_false_when_uninitialised(self):
        """enqueue_event returns False before _loop/_queue are initialised."""
        from file_organizer.api.realtime import ConnectionManager as CM

        m = CM()
        queued = m.enqueue_event({"test": True}, channel="orphan")
        assert queued is False
