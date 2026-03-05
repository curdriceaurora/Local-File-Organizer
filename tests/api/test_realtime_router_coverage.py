"""Coverage tests for file_organizer.api.routers.realtime — uncovered branches."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


class TestJwtValid:
    """Covers _jwt_valid helper."""

    def test_token_error(self) -> None:
        from file_organizer.api.auth import TokenError
        from file_organizer.api.routers.realtime import _jwt_valid

        with patch(
            "file_organizer.api.routers.realtime.decode_token",
            side_effect=TokenError("bad"),
        ):
            assert _jwt_valid("tok", MagicMock(), MagicMock(), MagicMock()) is False

    def test_not_access_token(self) -> None:
        from file_organizer.api.routers.realtime import _jwt_valid

        with (
            patch(
                "file_organizer.api.routers.realtime.decode_token",
                return_value={"token_type": "refresh"},
            ),
            patch("file_organizer.api.routers.realtime.is_access_token", return_value=False),
        ):
            assert _jwt_valid("tok", MagicMock(), MagicMock(), MagicMock()) is False

    def test_revoked_jti(self) -> None:
        from file_organizer.api.routers.realtime import _jwt_valid

        store = MagicMock()
        store.is_access_revoked.return_value = True
        with (
            patch(
                "file_organizer.api.routers.realtime.decode_token",
                return_value={"jti": "j1", "user_id": "u1"},
            ),
            patch("file_organizer.api.routers.realtime.is_access_token", return_value=True),
        ):
            assert _jwt_valid("tok", MagicMock(), MagicMock(), store) is False

    def test_invalid_user_id(self) -> None:
        from file_organizer.api.routers.realtime import _jwt_valid

        store = MagicMock()
        store.is_access_revoked.return_value = False
        with (
            patch(
                "file_organizer.api.routers.realtime.decode_token",
                return_value={"jti": "j1", "user_id": 123},
            ),
            patch("file_organizer.api.routers.realtime.is_access_token", return_value=True),
        ):
            assert _jwt_valid("tok", MagicMock(), MagicMock(), store) is False

    def test_user_not_found(self) -> None:
        from file_organizer.api.routers.realtime import _jwt_valid

        store = MagicMock()
        store.is_access_revoked.return_value = False
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        with (
            patch(
                "file_organizer.api.routers.realtime.decode_token",
                return_value={"jti": "j1", "user_id": "u1"},
            ),
            patch("file_organizer.api.routers.realtime.is_access_token", return_value=True),
        ):
            assert _jwt_valid("tok", MagicMock(), db, store) is False

    def test_user_inactive(self) -> None:
        from file_organizer.api.routers.realtime import _jwt_valid

        store = MagicMock()
        store.is_access_revoked.return_value = False
        user = MagicMock()
        user.is_active = False
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = user
        with (
            patch(
                "file_organizer.api.routers.realtime.decode_token",
                return_value={"jti": "j1", "user_id": "u1"},
            ),
            patch("file_organizer.api.routers.realtime.is_access_token", return_value=True),
        ):
            assert _jwt_valid("tok", MagicMock(), db, store) is False

    def test_valid_user(self) -> None:
        from file_organizer.api.routers.realtime import _jwt_valid

        store = MagicMock()
        store.is_access_revoked.return_value = False
        user = MagicMock()
        user.is_active = True
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = user
        with (
            patch(
                "file_organizer.api.routers.realtime.decode_token",
                return_value={"jti": "j1", "user_id": "u1"},
            ),
            patch("file_organizer.api.routers.realtime.is_access_token", return_value=True),
        ):
            assert _jwt_valid("tok", MagicMock(), db, store) is True


class TestTokenValid:
    """Covers _token_valid helper."""

    def test_auth_disabled_no_ws_token(self) -> None:
        from file_organizer.api.routers.realtime import _token_valid

        settings = MagicMock()
        settings.auth_enabled = False
        settings.websocket_token = ""
        assert _token_valid(None, settings, MagicMock(), MagicMock()) is True

    def test_auth_disabled_ws_token_required(self) -> None:
        from file_organizer.api.routers.realtime import _token_valid

        settings = MagicMock()
        settings.auth_enabled = False
        settings.websocket_token = "secret"
        assert _token_valid(None, settings, MagicMock(), MagicMock()) is False
        assert _token_valid("secret", settings, MagicMock(), MagicMock()) is True
        assert _token_valid("wrong", settings, MagicMock(), MagicMock()) is False

    def test_auth_enabled_jwt_valid(self) -> None:
        from file_organizer.api.routers.realtime import _token_valid

        settings = MagicMock()
        settings.auth_enabled = True
        settings.websocket_token = ""
        with patch("file_organizer.api.routers.realtime._jwt_valid", return_value=True):
            assert _token_valid("jwt", settings, MagicMock(), MagicMock()) is True

    def test_auth_enabled_ws_token_fallback(self) -> None:
        from file_organizer.api.routers.realtime import _token_valid

        settings = MagicMock()
        settings.auth_enabled = True
        settings.websocket_token = "secret"
        with patch("file_organizer.api.routers.realtime._jwt_valid", return_value=False):
            assert _token_valid("secret", settings, MagicMock(), MagicMock()) is True

    def test_auth_enabled_no_token(self) -> None:
        from file_organizer.api.routers.realtime import _token_valid

        settings = MagicMock()
        settings.auth_enabled = True
        settings.websocket_token = ""
        assert _token_valid(None, settings, MagicMock(), MagicMock()) is False


class TestExtractToken:
    """Covers _extract_token helper."""

    def test_query_param_token(self) -> None:
        from file_organizer.api.routers.realtime import _extract_token

        ws = MagicMock()
        assert _extract_token(ws, "my-token") == "my-token"

    def test_bearer_header(self) -> None:
        from file_organizer.api.routers.realtime import _extract_token

        ws = MagicMock()
        ws.headers = {"authorization": "Bearer abc123"}
        assert _extract_token(ws, None) == "abc123"

    def test_raw_header(self) -> None:
        from file_organizer.api.routers.realtime import _extract_token

        ws = MagicMock()
        ws.headers = {"authorization": "raw-token"}
        assert _extract_token(ws, None) == "raw-token"

    def test_no_header(self) -> None:
        from file_organizer.api.routers.realtime import _extract_token

        ws = MagicMock()
        ws.headers = {}
        assert _extract_token(ws, None) is None


class TestSendError:
    """Covers _send_error helper."""

    @pytest.mark.asyncio
    async def test_send_error_connected(self) -> None:
        from starlette.websockets import WebSocketState

        from file_organizer.api.routers.realtime import _send_error

        ws = MagicMock()
        ws.client_state = WebSocketState.CONNECTED
        with patch("file_organizer.api.routers.realtime.realtime_manager") as mgr:
            mgr.send_personal_message = AsyncMock()
            await _send_error(ws, "test error")
            mgr.send_personal_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_error_disconnected(self) -> None:
        from starlette.websockets import WebSocketState

        from file_organizer.api.routers.realtime import _send_error

        ws = MagicMock()
        ws.client_state = WebSocketState.DISCONNECTED
        with patch("file_organizer.api.routers.realtime.realtime_manager") as mgr:
            mgr.send_personal_message = AsyncMock()
            await _send_error(ws, "test error")
            mgr.send_personal_message.assert_not_called()


class TestHeartbeat:
    """Covers _heartbeat helper."""

    @pytest.mark.asyncio
    async def test_heartbeat_stops_on_event(self) -> None:
        import asyncio

        from file_organizer.api.routers.realtime import _heartbeat

        ws = MagicMock()
        ws.send_json = AsyncMock()
        stop = asyncio.Event()
        stop.set()
        await _heartbeat(ws, interval=1, stop=stop)
