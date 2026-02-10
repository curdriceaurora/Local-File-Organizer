"""Real-time connection manager for WebSocket updates."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Optional

from fastapi import WebSocket
from loguru import logger
from starlette.websockets import WebSocketState


@dataclass(frozen=True)
class BroadcastEvent:
    channel: str
    payload: dict[str, Any]


class ConnectionManager:
    """Manage WebSocket connections and broadcast events."""

    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._subscriptions: dict[WebSocket, set[str]] = {}
        self._lock: Optional[asyncio.Lock] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._queue: Optional[asyncio.Queue[BroadcastEvent]] = None
        self._queue_task: Optional[asyncio.Task[None]] = None

    def _ensure_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def connect(self, websocket: WebSocket, client_id: str) -> None:
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
        async with self._ensure_lock():
            self._connections.discard(websocket)
            self._subscriptions.pop(websocket, None)

    def reset(self) -> None:
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
        if websocket.client_state != WebSocketState.CONNECTED:
            return
        await websocket.send_json(message)

    async def broadcast(self, message: dict[str, Any], channel: str = "global") -> None:
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
        async with self._ensure_lock():
            if websocket in self._subscriptions:
                self._subscriptions[websocket].add(channel)

    async def unsubscribe(self, websocket: WebSocket, channel: str) -> None:
        async with self._ensure_lock():
            if websocket in self._subscriptions:
                self._subscriptions[websocket].discard(channel)

    async def publish_event(self, payload: dict[str, Any], channel: str = "global") -> None:
        if self._queue is None:
            return
        await self._queue.put(BroadcastEvent(channel=channel, payload=payload))

    def enqueue_event(self, payload: dict[str, Any], channel: str = "global") -> bool:
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
