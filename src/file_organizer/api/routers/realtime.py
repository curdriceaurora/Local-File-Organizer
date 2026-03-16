"""WebSocket endpoints for real-time updates."""

from __future__ import annotations

import asyncio
import hmac
import logging
from typing import Optional

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, status
from sqlalchemy.orm import Session
from starlette.websockets import WebSocketState

from file_organizer.api.auth import TokenError, decode_token, is_access_token
from file_organizer.api.auth_models import User
from file_organizer.api.auth_store import TokenStore
from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_db, get_settings, get_token_store
from file_organizer.api.realtime import realtime_manager

router = APIRouter(tags=["realtime"])
logger = logging.getLogger(__name__)


def _jwt_valid(
    token: str,
    settings: ApiSettings,
    db: Session,
    token_store: TokenStore,
) -> bool:
    try:
        payload = decode_token(token, settings)
    except TokenError:
        return False
    if not is_access_token(payload):
        return False
    jti = payload.get("jti")
    if isinstance(jti, str) and token_store.is_access_revoked(jti):
        return False
    user_id = payload.get("user_id")
    if not isinstance(user_id, str):
        return False
    user = db.query(User).filter(User.id == user_id).first()
    if user is None or not user.is_active:
        return False
    return True


def _token_valid(
    token: Optional[str],
    settings: ApiSettings,
    db: Session,
    token_store: TokenStore,
) -> bool:
    if settings.auth_enabled:
        if token and _jwt_valid(token, settings, db, token_store):
            return True
        required = settings.websocket_token
        if required and token is not None and hmac.compare_digest(token, required):
            return True
        return False

    required = settings.websocket_token
    if not required:
        return True
    if token is None:
        return False
    return hmac.compare_digest(token, required)


def _extract_token(websocket: WebSocket, token: Optional[str]) -> Optional[str]:
    if token:
        return token
    auth_header = websocket.headers.get("authorization")
    if not auth_header:
        return None
    parts = auth_header.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    return auth_header


async def _heartbeat(websocket: WebSocket, interval: int, stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
            break
        except TimeoutError:
            pass
        try:
            await websocket.send_json({"type": "ping"})
        except Exception:
            logger.debug("Websocket heartbeat ping failed; ending heartbeat loop", exc_info=True)
            break


async def _send_error(websocket: WebSocket, message: str) -> None:
    if websocket.client_state != WebSocketState.CONNECTED:
        return
    try:
        await realtime_manager.send_personal_message(
            {"type": "error", "message": message},
            websocket,
        )
    except Exception:
        logger.debug("Failed to send websocket error message", exc_info=True)


@router.websocket("/ws/{client_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    client_id: str,
    token: Optional[str] = None,
    settings: ApiSettings = Depends(get_settings),
    db: Session = Depends(get_db),
    token_store: TokenStore = Depends(get_token_store),
) -> None:
    """Handle WebSocket connections for real-time event streaming."""
    provided_token = _extract_token(websocket, token)
    if not _token_valid(provided_token, settings, db, token_store):
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
            if not isinstance(data, dict):
                await _send_error(websocket, "Invalid message format; expected a JSON object")
                continue
            message_type = data.get("type")
            if not isinstance(message_type, str):
                await _send_error(websocket, "Invalid or missing 'type' field in message")
                continue
            if message_type == "ping":
                await realtime_manager.send_personal_message({"type": "pong"}, websocket)
            elif message_type == "pong":
                pass
            elif message_type == "subscribe":
                channel = data.get("channel")
                if not isinstance(channel, str) or not channel.strip():
                    await _send_error(
                        websocket,
                        "Invalid or missing 'channel' field for subscribe; expected a non-empty string",
                    )
                    continue
                await realtime_manager.subscribe(websocket, channel)
                await realtime_manager.send_personal_message(
                    {"type": "subscribed", "channel": channel},
                    websocket,
                )
            elif message_type == "unsubscribe":
                channel = data.get("channel")
                if not isinstance(channel, str) or not channel.strip():
                    await _send_error(
                        websocket,
                        "Invalid or missing 'channel' field for unsubscribe; expected a non-empty string",
                    )
                    continue
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
        await _send_error(websocket, "Invalid JSON payload")
    finally:
        stop_event.set()
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass
        await realtime_manager.disconnect(websocket)
