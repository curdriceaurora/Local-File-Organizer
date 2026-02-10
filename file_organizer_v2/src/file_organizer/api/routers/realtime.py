"""WebSocket endpoints for real-time updates."""
from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, status

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_settings
from file_organizer.api.realtime import realtime_manager

router = APIRouter(tags=["realtime"])


def _token_valid(token: Optional[str], settings: ApiSettings) -> bool:
    required = settings.websocket_token
    if not required:
        return True
    return token == required


async def _heartbeat(websocket: WebSocket, interval: int, stop: asyncio.Event) -> None:
    while not stop.is_set():
        await asyncio.sleep(interval)
        try:
            await websocket.send_json({"type": "ping"})
        except Exception:
            break


@router.websocket("/ws/{client_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    client_id: str,
    token: Optional[str] = None,
    settings: ApiSettings = Depends(get_settings),
) -> None:
    if not _token_valid(token, settings):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await realtime_manager.connect(websocket, client_id)
    stop_event = asyncio.Event()
    heartbeat_task = asyncio.create_task(
        _heartbeat(websocket, settings.websocket_ping_interval, stop_event)
    )
    try:
        while True:
            data = await websocket.receive_json()
            message_type = data.get("type")
            if message_type == "ping":
                await realtime_manager.send_personal_message({"type": "pong"}, websocket)
            elif message_type == "subscribe":
                channel = data.get("channel")
                if channel:
                    await realtime_manager.subscribe(websocket, channel)
                    await realtime_manager.send_personal_message(
                        {"type": "subscribed", "channel": channel},
                        websocket,
                    )
            elif message_type == "unsubscribe":
                channel = data.get("channel")
                if channel:
                    await realtime_manager.unsubscribe(websocket, channel)
                    await realtime_manager.send_personal_message(
                        {"type": "unsubscribed", "channel": channel},
                        websocket,
                    )
            else:
                await realtime_manager.send_personal_message(
                    {"type": "error", "message": "Unknown message type"},
                    websocket,
                )
    except WebSocketDisconnect:
        pass
    except ValueError:
        await realtime_manager.send_personal_message(
            {"type": "error", "message": "Invalid JSON payload"},
            websocket,
        )
    finally:
        stop_event.set()
        heartbeat_task.cancel()
        await realtime_manager.disconnect(websocket)
