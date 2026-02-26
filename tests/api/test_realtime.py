"""Tests for real-time WebSocket connection manager."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.websockets import WebSocketState

from file_organizer.api.realtime import BroadcastEvent, ConnectionManager


class TestBroadcastEvent:
    """Tests for BroadcastEvent dataclass."""

    def test_creation(self):
        event = BroadcastEvent(channel="test", payload={"msg": "hello"})
        assert event.channel == "test"
        assert event.payload == {"msg": "hello"}

    def test_frozen(self):
        event = BroadcastEvent(channel="test", payload={})
        with pytest.raises(AttributeError):
            event.channel = "other"  # type: ignore[misc]


class TestConnectionManager:
    """Tests for ConnectionManager."""

    @pytest.fixture
    def manager(self):
        return ConnectionManager()

    @pytest.fixture
    def mock_ws(self):
        ws = AsyncMock()
        ws.client_state = WebSocketState.CONNECTED
        ws.accept = AsyncMock()
        ws.send_json = AsyncMock()
        return ws

    @pytest.mark.asyncio
    async def test_connect_accepts_and_registers(self, manager, mock_ws):
        await manager.connect(mock_ws, "client-1")
        mock_ws.accept.assert_awaited_once()
        assert mock_ws in manager._connections
        assert mock_ws in manager._subscriptions

    @pytest.mark.asyncio
    async def test_connect_sends_connected_message(self, manager, mock_ws):
        await manager.connect(mock_ws, "client-42")
        mock_ws.send_json.assert_awaited()
        call_args = mock_ws.send_json.call_args[0][0]
        assert call_args["type"] == "connection"
        assert call_args["status"] == "connected"
        assert call_args["client_id"] == "client-42"

    @pytest.mark.asyncio
    async def test_disconnect_removes_connection(self, manager, mock_ws):
        await manager.connect(mock_ws, "client-1")
        await manager.disconnect(mock_ws)
        assert mock_ws not in manager._connections
        assert mock_ws not in manager._subscriptions

    @pytest.mark.asyncio
    async def test_disconnect_nonexistent_is_safe(self, manager, mock_ws):
        # Should not raise
        await manager.disconnect(mock_ws)

    @pytest.mark.asyncio
    async def test_send_personal_message(self, manager, mock_ws):
        msg = {"type": "test", "data": "hello"}
        await manager.send_personal_message(msg, mock_ws)
        mock_ws.send_json.assert_awaited_once_with(msg)

    @pytest.mark.asyncio
    async def test_send_personal_message_skips_disconnected(self, manager, mock_ws):
        mock_ws.client_state = WebSocketState.DISCONNECTED
        await manager.send_personal_message({"data": "hi"}, mock_ws)
        mock_ws.send_json.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_broadcast_global_sends_to_all(self, manager, mock_ws):
        ws2 = AsyncMock()
        ws2.client_state = WebSocketState.CONNECTED
        ws2.accept = AsyncMock()
        ws2.send_json = AsyncMock()

        await manager.connect(mock_ws, "c1")
        await manager.connect(ws2, "c2")

        # Reset send_json mock call counts from connect messages
        mock_ws.send_json.reset_mock()
        ws2.send_json.reset_mock()

        msg = {"type": "update"}
        await manager.broadcast(msg, channel="global")
        mock_ws.send_json.assert_awaited_once_with(msg)
        ws2.send_json.assert_awaited_once_with(msg)

    @pytest.mark.asyncio
    async def test_broadcast_channel_sends_only_to_subscribers(self, manager, mock_ws):
        ws2 = AsyncMock()
        ws2.client_state = WebSocketState.CONNECTED
        ws2.accept = AsyncMock()
        ws2.send_json = AsyncMock()

        await manager.connect(mock_ws, "c1")
        await manager.connect(ws2, "c2")

        await manager.subscribe(mock_ws, "files")

        mock_ws.send_json.reset_mock()
        ws2.send_json.reset_mock()

        msg = {"type": "file_update"}
        await manager.broadcast(msg, channel="files")
        mock_ws.send_json.assert_awaited_once_with(msg)
        ws2.send_json.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_broadcast_handles_send_failure(self, manager, mock_ws):
        await manager.connect(mock_ws, "c1")
        mock_ws.send_json.side_effect = [None, RuntimeError("closed")]
        mock_ws.send_json.reset_mock()
        mock_ws.send_json.side_effect = RuntimeError("closed")

        await manager.broadcast({"type": "test"}, channel="global")
        # Connection should have been removed after failure
        assert mock_ws not in manager._connections

    @pytest.mark.asyncio
    async def test_subscribe(self, manager, mock_ws):
        await manager.connect(mock_ws, "c1")
        await manager.subscribe(mock_ws, "events")
        assert "events" in manager._subscriptions[mock_ws]

    @pytest.mark.asyncio
    async def test_subscribe_unknown_ws_is_safe(self, manager, mock_ws):
        # Subscribing a websocket that isn't connected should not raise
        await manager.subscribe(mock_ws, "events")

    @pytest.mark.asyncio
    async def test_unsubscribe(self, manager, mock_ws):
        await manager.connect(mock_ws, "c1")
        await manager.subscribe(mock_ws, "events")
        await manager.unsubscribe(mock_ws, "events")
        assert "events" not in manager._subscriptions[mock_ws]

    @pytest.mark.asyncio
    async def test_unsubscribe_unknown_ws_is_safe(self, manager, mock_ws):
        await manager.unsubscribe(mock_ws, "events")

    @pytest.mark.asyncio
    async def test_unsubscribe_channel_not_subscribed(self, manager, mock_ws):
        await manager.connect(mock_ws, "c1")
        # Should not raise
        await manager.unsubscribe(mock_ws, "nonexistent")

    @pytest.mark.asyncio
    async def test_publish_event_enqueues(self, manager, mock_ws):
        await manager.connect(mock_ws, "c1")
        await manager.publish_event({"data": "test"}, channel="global")
        # Give queue consumer a moment to process
        await asyncio.sleep(0.1)
        # The event should have been broadcast
        calls = mock_ws.send_json.call_args_list
        assert any(c[0][0].get("data") == "test" for c in calls)

    @pytest.mark.asyncio
    async def test_publish_event_no_queue_is_noop(self, manager):
        # No queue initialized (no connections)
        assert manager._queue is None
        await manager.publish_event({"data": "test"})  # Should not raise

    def test_enqueue_event_no_loop_returns_false(self, manager):
        assert manager.enqueue_event({"data": "test"}) is False

    @pytest.mark.asyncio
    async def test_enqueue_event_from_sync_context(self, manager, mock_ws):
        await manager.connect(mock_ws, "c1")
        result = manager.enqueue_event({"data": "sync-test"}, channel="global")
        assert result is True
        await asyncio.sleep(0.1)

    def test_enqueue_event_no_queue_returns_false(self, manager):
        manager._loop = asyncio.new_event_loop()
        manager._queue = None
        result = manager.enqueue_event({"data": "test"})
        assert result is False
        manager._loop.close()

    def test_reset_clears_state(self, manager):
        manager._connections.add(MagicMock())
        manager._subscriptions[MagicMock()] = {"ch1"}
        manager.reset()
        assert len(manager._connections) == 0
        assert len(manager._subscriptions) == 0
        assert manager._lock is None
        assert manager._loop is None
        assert manager._queue is None

    @pytest.mark.asyncio
    async def test_reset_cancels_queue_task(self, manager, mock_ws):
        await manager.connect(mock_ws, "c1")
        assert manager._queue_task is not None
        manager.reset()
        assert manager._queue_task is None

    @pytest.mark.asyncio
    async def test_connect_reinitializes_on_new_loop(self, manager, mock_ws):
        """When the event loop changes, lock/queue should be re-created."""
        await manager.connect(mock_ws, "c1")
        _old_lock = manager._lock
        _old_queue = manager._queue

        # Simulate a loop change by clearing the loop reference
        manager._loop = None
        ws2 = AsyncMock()
        ws2.client_state = WebSocketState.CONNECTED
        ws2.accept = AsyncMock()
        ws2.send_json = AsyncMock()
        await manager.connect(ws2, "c2")
        # Lock and queue should have been re-created
        assert manager._lock is not _old_lock
        assert manager._queue is not _old_queue

    @pytest.mark.asyncio
    async def test_ensure_lock_creates_when_none(self, manager):
        assert manager._lock is None
        lock = manager._ensure_lock()
        assert lock is not None
        assert manager._lock is lock

    @pytest.mark.asyncio
    async def test_connect_creates_lock_when_loop_matches_but_lock_none(self, manager, mock_ws):
        """If loop matches but lock was set to None, a new lock is created."""
        await manager.connect(mock_ws, "c1")
        # Set lock to None but keep loop
        manager._lock = None

        ws2 = AsyncMock()
        ws2.client_state = WebSocketState.CONNECTED
        ws2.accept = AsyncMock()
        ws2.send_json = AsyncMock()
        await manager.connect(ws2, "c2")
        assert manager._lock is not None

    @pytest.mark.asyncio
    async def test_connect_restarts_queue_when_task_done(self, manager, mock_ws):
        """If the queue task completed, a new one should be started on connect."""
        await manager.connect(mock_ws, "c1")
        # Simulate task being done
        old_task = manager._queue_task
        old_task.cancel()
        try:
            await old_task
        except asyncio.CancelledError:
            pass

        ws2 = AsyncMock()
        ws2.client_state = WebSocketState.CONNECTED
        ws2.accept = AsyncMock()
        ws2.send_json = AsyncMock()
        await manager.connect(ws2, "c2")
        assert manager._queue_task is not None
        assert manager._queue_task is not old_task

    @pytest.mark.asyncio
    async def test_reset_drains_queue(self, manager, mock_ws):
        """Reset should drain pending items from the queue."""
        await manager.connect(mock_ws, "c1")
        # Put items directly on the queue
        assert manager._queue is not None
        await manager._queue.put(BroadcastEvent(channel="ch", payload={"a": 1}))
        await manager._queue.put(BroadcastEvent(channel="ch", payload={"b": 2}))
        manager.reset()
        # Queue reference should be cleared
        assert manager._queue is None

    @pytest.mark.asyncio
    async def test_await_task_handles_cancelled_error(self, manager):
        """_await_task should silently handle CancelledError."""
        task = asyncio.create_task(asyncio.sleep(100))
        task.cancel()
        # Should not raise
        await manager._await_task(task)

    @pytest.mark.asyncio
    async def test_await_task_handles_generic_exception(self, manager):
        """_await_task should log but not raise on generic exceptions."""

        async def failing_coro():
            raise ValueError("something went wrong")

        task = asyncio.create_task(failing_coro())
        await asyncio.sleep(0.01)
        # Should not raise, just log
        await manager._await_task(task)

    @pytest.mark.asyncio
    async def test_enqueue_event_runtime_error(self, manager, mock_ws):
        """enqueue_event should return False on RuntimeError."""
        await manager.connect(mock_ws, "c1")
        # Patch run_coroutine_threadsafe to raise RuntimeError
        with patch("file_organizer.api.realtime.asyncio.run_coroutine_threadsafe") as mock_rcts:
            mock_rcts.side_effect = RuntimeError("loop closed")
            result = manager.enqueue_event({"data": "test"})
        assert result is False

    @pytest.mark.asyncio
    async def test_queue_consumer_returns_when_no_queue(self, manager):
        """_queue_consumer returns early if queue is None."""
        manager._queue = None
        # Should return immediately without error
        await manager._queue_consumer()

    @pytest.mark.asyncio
    async def test_queue_consumer_handles_broadcast_error(self, manager, mock_ws):
        """_queue_consumer should handle exceptions during broadcast."""
        await manager.connect(mock_ws, "c1")

        call_count = 0

        async def failing_broadcast(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("broadcast error")
            # Cancel on second call to exit loop
            raise asyncio.CancelledError()

        manager.broadcast = failing_broadcast
        # Put an event to trigger the error path
        await manager._queue.put(BroadcastEvent(channel="global", payload={"x": 1}))
        # Put second event to trigger the cancel
        await manager._queue.put(BroadcastEvent(channel="global", payload={"y": 2}))
        # Give consumer time to process both events
        await asyncio.sleep(0.2)
        assert call_count >= 1
