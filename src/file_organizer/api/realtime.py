"""Real-time connection manager for WebSocket updates."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from fastapi import WebSocket
from loguru import logger
from starlette.websockets import WebSocketState


@dataclass(frozen=True)
class BroadcastEvent:
    """A broadcast event with channel and payload."""

    channel: str
    payload: dict[str, Any]


class ConnectionManager:
    """Manage WebSocket connections and broadcast events."""

    def __init__(self) -> None:
        """Initialize ConnectionManager with empty connections and subscriptions."""
        self._connections: set[WebSocket] = set()
        self._subscriptions: dict[WebSocket, set[str]] = {}
        self._lock: asyncio.Lock | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._queue: asyncio.Queue[BroadcastEvent] | None = None
        self._queue_task: asyncio.Task[None] | None = None

    def _ensure_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def connect(self, websocket: WebSocket, client_id: str) -> None:
        """Accept a WebSocket connection and register it."""
        await websocket.accept()
        current_loop = asyncio.get_running_loop()
        if self._loop is None or self._loop.is_closed() or self._loop is not current_loop:
            self._loop = current_loop
            self._queue = None
            self._queue_task = None
            self._lock = asyncio.Lock()
        elif self._lock is None:
            self._lock = asyncio.Lock()
        if self._queue is None or (self._queue_task is not None and self._queue_task.done()):
            self._queue = asyncio.Queue()
            self._queue_task = asyncio.create_task(self._queue_consumer())
        async with self._ensure_lock():
            self._connections.add(websocket)
            self._subscriptions[websocket] = set()
        await self.send_personal_message(
            {"type": "connection", "status": "connected", "client_id": client_id},
            websocket,
        )

    async def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection from the manager."""
        async with self._ensure_lock():
            self._connections.discard(websocket)
            self._subscriptions.pop(websocket, None)

    def reset(self) -> None:
        """Cancel the queue consumer and clear all connections."""
        task = self._queue_task
        loop = self._loop
        self._queue_task = None
        if task is not None:
            task.cancel()
            if loop is not None and loop.is_running():
                try:
                    future = asyncio.run_coroutine_threadsafe(
                        self._await_task(task),
                        loop,
                    )
                    future.result(timeout=2)
                except Exception:
                    logger.exception("Failed to await websocket queue task shutdown")
        if self._queue is not None:
            while not self._queue.empty():
                try:
                    self._queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
        self._connections.clear()
        self._subscriptions.clear()
        self._lock = None
        self._loop = None
        self._queue = None

    async def _await_task(self, task: asyncio.Task[None]) -> None:
        try:
            await task
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("WebSocket queue task failed during reset")

    async def send_personal_message(self, message: dict[str, Any], websocket: WebSocket) -> None:
        """Send a message directly to a single WebSocket connection."""
        if websocket.client_state != WebSocketState.CONNECTED:
            return
        await websocket.send_json(message)

    async def broadcast(self, message: dict[str, Any], channel: str = "global") -> None:
        """Broadcast a message to all connections subscribed to channel."""
        async with self._ensure_lock():
            if channel == "global":
                targets = list(self._connections)
            else:
                targets = [
                    ws
                    for ws, subscriptions in self._subscriptions.items()
                    if channel in subscriptions
                ]
        for websocket in targets:
            try:
                await websocket.send_json(message)
            except Exception as exc:
                logger.debug("WebSocket broadcast failed: {}", exc)
                await self.disconnect(websocket)

    async def subscribe(self, websocket: WebSocket, channel: str) -> None:
        """Subscribe a WebSocket to receive events on channel."""
        async with self._ensure_lock():
            if websocket in self._subscriptions:
                self._subscriptions[websocket].add(channel)

    async def unsubscribe(self, websocket: WebSocket, channel: str) -> None:
        """Unsubscribe a WebSocket from events on channel."""
        async with self._ensure_lock():
            if websocket in self._subscriptions:
                self._subscriptions[websocket].discard(channel)

    async def publish_event(self, payload: dict[str, Any], channel: str = "global") -> None:
        """Enqueue a broadcast event for async delivery."""
        if self._queue is None:
            return
        await self._queue.put(BroadcastEvent(channel=channel, payload=payload))

    def enqueue_event(self, payload: dict[str, Any], channel: str = "global") -> bool:
        """Enqueue an event from a synchronous context using run_coroutine_threadsafe."""
        if self._loop is None or self._queue is None:
            return False
        try:
            asyncio.run_coroutine_threadsafe(
                self._queue.put(BroadcastEvent(channel=channel, payload=payload)),
                self._loop,
            )
            return True
        except RuntimeError as exc:
            logger.debug("Failed to enqueue websocket event: {}", exc)
            return False

    async def _queue_consumer(self) -> None:
        if self._queue is None:
            return
        while True:
            try:
                event = await self._queue.get()
                await self.broadcast(event.payload, channel=event.channel)
            except Exception:
                logger.exception("WebSocket queue consumer error")


realtime_manager = ConnectionManager()
