"""Coverage tests for file_organizer.api.routers.realtime — WebSocket endpoint.

Targets lines 83-182: _heartbeat, _send_error, websocket_endpoint message
handling (ping/pong/subscribe/unsubscribe/unknown/invalid), auth rejection,
and WebSocketDisconnect/ValueError cleanup paths.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from file_organizer.api.config import ApiSettings

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# _heartbeat helper
# ---------------------------------------------------------------------------


class TestHeartbeat:
    """Tests for the _heartbeat coroutine."""

    @pytest.mark.asyncio
    async def test_heartbeat_stops_when_event_set(self) -> None:
        """_heartbeat exits immediately when stop event is pre-set."""
        from file_organizer.api.routers.realtime import _heartbeat

        ws = AsyncMock()
        stop = asyncio.Event()
        stop.set()

        await _heartbeat(ws, interval=1, stop=stop)
        ws.send_json.assert_not_called()

    @pytest.mark.asyncio
    async def test_heartbeat_sends_ping_then_stops(self) -> None:
        """_heartbeat sends a ping on each interval tick, stops on event."""
        from file_organizer.api.routers.realtime import _heartbeat

        ws = AsyncMock()
        stop = asyncio.Event()
        received_payloads: list = []

        async def _send(data):
            received_payloads.append(data)
            stop.set()

        ws.send_json = _send

        await asyncio.wait_for(_heartbeat(ws, interval=0, stop=stop), timeout=2)
        assert len(received_payloads) >= 1
        assert received_payloads[0] == {"type": "ping"}

    @pytest.mark.asyncio
    async def test_heartbeat_exits_on_send_error(self) -> None:
        """_heartbeat breaks out of loop when send_json raises."""
        from file_organizer.api.routers.realtime import _heartbeat

        ws = AsyncMock()
        ws.send_json.side_effect = RuntimeError("connection closed")
        stop = asyncio.Event()

        await asyncio.wait_for(_heartbeat(ws, interval=0, stop=stop), timeout=2)
        ws.send_json.assert_called_once_with({"type": "ping"})


# ---------------------------------------------------------------------------
# _send_error helper
# ---------------------------------------------------------------------------


class TestSendError:
    """Tests for the _send_error coroutine."""

    @pytest.mark.asyncio
    async def test_send_error_when_connected(self) -> None:
        """_send_error sends error message when WebSocket is CONNECTED."""
        from starlette.websockets import WebSocketState

        from file_organizer.api.routers.realtime import _send_error

        ws = AsyncMock()
        ws.client_state = WebSocketState.CONNECTED

        with patch("file_organizer.api.routers.realtime.realtime_manager") as mock_mgr:
            mock_mgr.send_personal_message = AsyncMock()
            await _send_error(ws, "something went wrong")
            mock_mgr.send_personal_message.assert_called_once_with(
                {"type": "error", "message": "something went wrong"}, ws
            )

    @pytest.mark.asyncio
    async def test_send_error_when_disconnected(self) -> None:
        """_send_error is a no-op when WebSocket is not CONNECTED."""
        from starlette.websockets import WebSocketState

        from file_organizer.api.routers.realtime import _send_error

        ws = AsyncMock()
        ws.client_state = WebSocketState.DISCONNECTED

        with patch("file_organizer.api.routers.realtime.realtime_manager") as mock_mgr:
            mock_mgr.send_personal_message = AsyncMock()
            await _send_error(ws, "ignored")
            mock_mgr.send_personal_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_error_swallows_exception(self) -> None:
        """_send_error does not propagate exceptions from send_personal_message."""
        from starlette.websockets import WebSocketState

        from file_organizer.api.routers.realtime import _send_error

        ws = AsyncMock()
        ws.client_state = WebSocketState.CONNECTED

        with patch("file_organizer.api.routers.realtime.realtime_manager") as mock_mgr:
            mock_mgr.send_personal_message = AsyncMock(side_effect=RuntimeError("network error"))
            await _send_error(ws, "test")  # must not raise


# ---------------------------------------------------------------------------
# WebSocket endpoint — auth rejection
# ---------------------------------------------------------------------------


class TestWebSocketAuth:
    """Tests for WebSocket auth rejection."""

    @pytest.mark.asyncio
    async def test_websocket_rejected_when_token_required_missing(self) -> None:
        """websocket_endpoint closes with 1008 when a token is required but absent."""
        from fastapi import status as ws_status

        from file_organizer.api.routers import realtime as rt_module

        ws = AsyncMock()
        ws.headers = MagicMock()
        ws.headers.get = MagicMock(return_value=None)  # no auth header
        ws.close = AsyncMock()

        settings = ApiSettings(
            environment="test",
            auth_enabled=False,
            websocket_token="secret-tok",  # token required
            websocket_ping_interval=60,
        )

        await rt_module.websocket_endpoint(
            websocket=ws,
            client_id="test-client",
            token=None,
            settings=settings,
            db=MagicMock(),
            token_store=MagicMock(),
        )

        ws.close.assert_called_once_with(code=ws_status.WS_1008_POLICY_VIOLATION)

    @pytest.mark.asyncio
    async def test_websocket_accepted_without_token_requirement(self) -> None:
        """websocket_endpoint accepts connection when no token is required."""
        from fastapi import WebSocketDisconnect

        from file_organizer.api.routers import realtime as rt_module

        ws = AsyncMock()
        ws.headers = MagicMock()
        ws.headers.get = MagicMock(return_value=None)
        ws.client_state = MagicMock()
        ws.receive_json = AsyncMock(side_effect=WebSocketDisconnect())

        settings = ApiSettings(
            environment="test",
            auth_enabled=False,
            websocket_token=None,  # no token required
            websocket_ping_interval=60,
        )

        with patch.object(rt_module, "realtime_manager") as mock_mgr:
            mock_mgr.connect = AsyncMock()
            mock_mgr.disconnect = AsyncMock()
            mock_mgr.send_personal_message = AsyncMock()

            await rt_module.websocket_endpoint(
                websocket=ws,
                client_id="test-client",
                token=None,
                settings=settings,
                db=MagicMock(),
                token_store=MagicMock(),
            )

        # Connection was accepted — manager.connect() was called, close() was not
        mock_mgr.connect.assert_called_once()
        ws.close.assert_not_called()


# ---------------------------------------------------------------------------
# WebSocket endpoint — message handling
# ---------------------------------------------------------------------------


class TestWebSocketMessages:
    """Tests for WebSocket message type handling."""

    @pytest.mark.asyncio
    async def test_ping_message_returns_pong(self) -> None:
        """Ping message should trigger a pong response via realtime_manager."""
        from file_organizer.api.routers import realtime as rt_module

        ws = AsyncMock()
        ws.client_state = MagicMock()
        ws.headers = MagicMock()
        ws.headers.get = MagicMock(return_value=None)

        call_count = 0

        async def _receive():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"type": "ping"}
            from fastapi import WebSocketDisconnect
            raise WebSocketDisconnect()

        ws.receive_json = _receive

        settings = ApiSettings(environment="test", auth_enabled=False, websocket_ping_interval=60)
        db = MagicMock()
        token_store = MagicMock()

        with patch.object(rt_module, "realtime_manager") as mock_mgr:
            mock_mgr.connect = AsyncMock()
            mock_mgr.disconnect = AsyncMock()
            mock_mgr.send_personal_message = AsyncMock()
            mock_mgr.subscribe = AsyncMock()
            mock_mgr.unsubscribe = AsyncMock()

            with patch.object(rt_module, "_token_valid", return_value=True):
                await rt_module.websocket_endpoint(
                    websocket=ws,
                    client_id="test-client",
                    token=None,
                    settings=settings,
                    db=db,
                    token_store=token_store,
                )

        mock_mgr.send_personal_message.assert_any_call({"type": "pong"}, ws)

    @pytest.mark.asyncio
    async def test_subscribe_message(self) -> None:
        """Subscribe message should call realtime_manager.subscribe."""
        from file_organizer.api.routers import realtime as rt_module

        ws = AsyncMock()
        ws.headers = MagicMock()
        ws.headers.get = MagicMock(return_value=None)
        call_count = 0

        async def _receive():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"type": "subscribe", "channel": "jobs"}
            from fastapi import WebSocketDisconnect
            raise WebSocketDisconnect()

        ws.receive_json = _receive

        settings = ApiSettings(environment="test", auth_enabled=False, websocket_ping_interval=60)

        with patch.object(rt_module, "realtime_manager") as mock_mgr:
            mock_mgr.connect = AsyncMock()
            mock_mgr.disconnect = AsyncMock()
            mock_mgr.send_personal_message = AsyncMock()
            mock_mgr.subscribe = AsyncMock()
            mock_mgr.unsubscribe = AsyncMock()

            with patch.object(rt_module, "_token_valid", return_value=True):
                await rt_module.websocket_endpoint(
                    websocket=ws,
                    client_id="test-client",
                    token=None,
                    settings=settings,
                    db=MagicMock(),
                    token_store=MagicMock(),
                )

        mock_mgr.subscribe.assert_called_once_with(ws, "jobs")

    @pytest.mark.asyncio
    async def test_unsubscribe_message(self) -> None:
        """Unsubscribe message should call realtime_manager.unsubscribe."""
        from file_organizer.api.routers import realtime as rt_module

        ws = AsyncMock()
        ws.headers = MagicMock()
        ws.headers.get = MagicMock(return_value=None)
        call_count = 0

        async def _receive():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"type": "unsubscribe", "channel": "jobs"}
            from fastapi import WebSocketDisconnect
            raise WebSocketDisconnect()

        ws.receive_json = _receive

        settings = ApiSettings(environment="test", auth_enabled=False, websocket_ping_interval=60)

        with patch.object(rt_module, "realtime_manager") as mock_mgr:
            mock_mgr.connect = AsyncMock()
            mock_mgr.disconnect = AsyncMock()
            mock_mgr.send_personal_message = AsyncMock()
            mock_mgr.subscribe = AsyncMock()
            mock_mgr.unsubscribe = AsyncMock()

            with patch.object(rt_module, "_token_valid", return_value=True):
                await rt_module.websocket_endpoint(
                    websocket=ws,
                    client_id="test-client",
                    token=None,
                    settings=settings,
                    db=MagicMock(),
                    token_store=MagicMock(),
                )

        mock_mgr.unsubscribe.assert_called_once_with(ws, "jobs")

    @pytest.mark.asyncio
    async def test_unknown_message_type(self) -> None:
        """Unknown message type triggers error response."""
        from file_organizer.api.routers import realtime as rt_module

        ws = AsyncMock()
        ws.headers = MagicMock()
        ws.headers.get = MagicMock(return_value=None)
        call_count = 0

        async def _receive():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"type": "unknown_action"}
            from fastapi import WebSocketDisconnect
            raise WebSocketDisconnect()

        ws.receive_json = _receive

        settings = ApiSettings(environment="test", auth_enabled=False, websocket_ping_interval=60)

        with patch.object(rt_module, "realtime_manager") as mock_mgr:
            mock_mgr.connect = AsyncMock()
            mock_mgr.disconnect = AsyncMock()
            mock_mgr.send_personal_message = AsyncMock()

            with patch.object(rt_module, "_token_valid", return_value=True):
                await rt_module.websocket_endpoint(
                    websocket=ws,
                    client_id="test-client",
                    token=None,
                    settings=settings,
                    db=MagicMock(),
                    token_store=MagicMock(),
                )

        # Should send exactly "Unknown message type" error
        calls = mock_mgr.send_personal_message.call_args_list
        error_calls = [c for c in calls if c[0][0].get("type") == "error"]
        assert len(error_calls) >= 1
        assert error_calls[0][0][0] == {"type": "error", "message": "Unknown message type"}

    @pytest.mark.asyncio
    async def test_invalid_json_payload(self) -> None:
        """ValueError from receive_json triggers _send_error."""
        from file_organizer.api.routers import realtime as rt_module

        ws = AsyncMock()
        ws.headers = MagicMock()
        ws.headers.get = MagicMock(return_value=None)
        ws.client_state = MagicMock()
        call_count = 0

        async def _receive():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("not json")
            from fastapi import WebSocketDisconnect
            raise WebSocketDisconnect()

        ws.receive_json = _receive

        settings = ApiSettings(environment="test", auth_enabled=False, websocket_ping_interval=60)

        with patch.object(rt_module, "realtime_manager") as mock_mgr:
            mock_mgr.connect = AsyncMock()
            mock_mgr.disconnect = AsyncMock()
            mock_mgr.send_personal_message = AsyncMock()

            with (
                patch.object(rt_module, "_token_valid", return_value=True),
                patch.object(rt_module, "_send_error", new=AsyncMock()) as mock_send_err,
            ):
                await rt_module.websocket_endpoint(
                    websocket=ws,
                    client_id="test-client",
                    token=None,
                    settings=settings,
                    db=MagicMock(),
                    token_store=MagicMock(),
                )

        mock_send_err.assert_called_once_with(ws, "Invalid JSON payload")

    @pytest.mark.asyncio
    async def test_non_dict_message(self) -> None:
        """Non-dict message triggers invalid format error."""
        from file_organizer.api.routers import realtime as rt_module

        ws = AsyncMock()
        ws.headers = MagicMock()
        ws.headers.get = MagicMock(return_value=None)
        ws.client_state = MagicMock()
        call_count = 0

        async def _receive():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return ["not", "a", "dict"]
            from fastapi import WebSocketDisconnect
            raise WebSocketDisconnect()

        ws.receive_json = _receive

        settings = ApiSettings(environment="test", auth_enabled=False, websocket_ping_interval=60)

        with patch.object(rt_module, "realtime_manager") as mock_mgr:
            mock_mgr.connect = AsyncMock()
            mock_mgr.disconnect = AsyncMock()
            mock_mgr.send_personal_message = AsyncMock()

            with (
                patch.object(rt_module, "_token_valid", return_value=True),
                patch.object(rt_module, "_send_error", new=AsyncMock()) as mock_send_err,
            ):
                await rt_module.websocket_endpoint(
                    websocket=ws,
                    client_id="test-client",
                    token=None,
                    settings=settings,
                    db=MagicMock(),
                    token_store=MagicMock(),
                )

        mock_send_err.assert_called_once()
        assert "format" in mock_send_err.call_args[0][1].lower()

    @pytest.mark.asyncio
    async def test_subscribe_missing_channel(self) -> None:
        """Subscribe with missing channel triggers error response."""
        from file_organizer.api.routers import realtime as rt_module

        ws = AsyncMock()
        ws.headers = MagicMock()
        ws.headers.get = MagicMock(return_value=None)
        ws.client_state = MagicMock()
        call_count = 0

        async def _receive():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"type": "subscribe"}  # no channel
            from fastapi import WebSocketDisconnect
            raise WebSocketDisconnect()

        ws.receive_json = _receive

        settings = ApiSettings(environment="test", auth_enabled=False, websocket_ping_interval=60)

        with patch.object(rt_module, "realtime_manager") as mock_mgr:
            mock_mgr.connect = AsyncMock()
            mock_mgr.disconnect = AsyncMock()
            mock_mgr.send_personal_message = AsyncMock()
            mock_mgr.subscribe = AsyncMock()

            with (
                patch.object(rt_module, "_token_valid", return_value=True),
                patch.object(rt_module, "_send_error", new=AsyncMock()) as mock_send_err,
            ):
                await rt_module.websocket_endpoint(
                    websocket=ws,
                    client_id="test-client",
                    token=None,
                    settings=settings,
                    db=MagicMock(),
                    token_store=MagicMock(),
                )

        mock_send_err.assert_called_once()
        mock_mgr.subscribe.assert_not_called()

    @pytest.mark.asyncio
    async def test_pong_message_is_ignored(self) -> None:
        """Pong message is silently accepted with no response."""
        from file_organizer.api.routers import realtime as rt_module

        ws = AsyncMock()
        ws.headers = MagicMock()
        ws.headers.get = MagicMock(return_value=None)
        call_count = 0

        async def _receive():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"type": "pong"}
            from fastapi import WebSocketDisconnect
            raise WebSocketDisconnect()

        ws.receive_json = _receive

        settings = ApiSettings(environment="test", auth_enabled=False, websocket_ping_interval=60)

        with patch.object(rt_module, "realtime_manager") as mock_mgr:
            mock_mgr.connect = AsyncMock()
            mock_mgr.disconnect = AsyncMock()
            mock_mgr.send_personal_message = AsyncMock()

            with patch.object(rt_module, "_token_valid", return_value=True):
                await rt_module.websocket_endpoint(
                    websocket=ws,
                    client_id="test-client",
                    token=None,
                    settings=settings,
                    db=MagicMock(),
                    token_store=MagicMock(),
                )

        # pong is silently accepted — no outbound message of any kind
        mock_mgr.send_personal_message.assert_not_called()
