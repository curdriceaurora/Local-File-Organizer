"""Integration tests targeting coverage gaps in API, Web, and CSRF components.

Files covered:
- file_organizer/web/csrf.py
- file_organizer/api/repositories/session_repo.py
- file_organizer/api/api_keys.py
- file_organizer/api/routers/realtime.py
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response
from starlette.testclient import TestClient

# 3. API Keys
from file_organizer.api.api_keys import (
    _main,
    _write_key,
    api_key_identifier,
    generate_api_key,
    hash_api_key,
    match_api_key_hash,
    verify_api_key,
)

# 2. Session Repo
from file_organizer.api.auth_models import Base, User
from file_organizer.api.config import ApiSettings
from file_organizer.api.db_models import UserSession
from file_organizer.api.dependencies import get_db, get_settings, get_token_store
from file_organizer.api.repositories.session_repo import SessionRepository

# 4. Realtime
from file_organizer.api.routers.realtime import router as realtime_router

# 1. CSRF
from file_organizer.web.csrf import CSRFMiddleware, validate_csrf_token

pytestmark = pytest.mark.integration


# ===========================================================================
# 1. file_organizer/web/csrf.py Tests
# ===========================================================================


class TestWebCSRFProtection:
    def test_csrf_token_validation(self) -> None:
        assert validate_csrf_token(cookie_token=None, submitted_token="foo") is False
        assert validate_csrf_token(cookie_token="foo", submitted_token=None) is False
        assert validate_csrf_token(cookie_token="foo", submitted_token="bar") is False
        assert validate_csrf_token(cookie_token="foo", submitted_token="foo") is True
        # Non-ASCII rejection
        assert validate_csrf_token(cookie_token="foo\u1234", submitted_token="foo") is False
        assert validate_csrf_token(cookie_token="foo", submitted_token="foo\u1234") is False

    def test_csrf_middleware_exempt_paths(self) -> None:
        middleware = CSRFMiddleware(app=None, exempt_paths=["/api/", "/auth"])
        assert middleware._is_exempt("/api/v1/users") is True
        assert middleware._is_exempt("/auth") is True
        assert middleware._is_exempt("/auth/login") is True
        assert middleware._is_exempt("/home") is False  # noqa: test-hardcoded-paths

    def test_csrf_middleware_flow(self) -> None:
        app = FastAPI()
        app.add_middleware(CSRFMiddleware, exempt_paths=["/exempt"])

        @app.get("/test")
        def get_test(request: Request) -> Response:
            return PlainTextResponse("get success")

        @app.post("/test")
        def post_test(request: Request) -> Response:
            return PlainTextResponse("post success")

        client = TestClient(app)

        # GET request sets the CSRF cookie
        res = client.get("/test")
        assert res.status_code == 200
        assert "_csrf_token" in client.cookies
        token = client.cookies["_csrf_token"]

        # POST request without token fails (403)
        res_fail = client.post("/test")
        assert res_fail.status_code == 403
        assert "CSRF token missing or invalid" in res_fail.json()["detail"]

        # POST request with matching header succeeds
        res_success_header = client.post("/test", headers={"x-csrf-token": token})
        assert res_success_header.status_code == 200
        assert res_success_header.text == "post success"

        # POST request with matching urlencoded form field succeeds
        res_success_form = client.post("/test", data={"csrf_token": token})
        assert res_success_form.status_code == 200
        assert res_success_form.text == "post success"

        # POST request with multipart form data succeeds
        res_success_multipart = client.post("/test", files={"csrf_token": (None, token)})
        assert res_success_multipart.status_code == 200
        assert res_success_multipart.text == "post success"

        # POST request to exempt path succeeds without token
        @app.post("/exempt")
        def post_exempt() -> Response:
            return PlainTextResponse("exempt success")

        res_exempt = client.post("/exempt")
        assert res_exempt.status_code == 200
        assert res_exempt.text == "exempt success"

        # UnicodeDecodeError in parse_qs path (invalid UTF-8 bytes in urlencoded data)
        with patch("starlette.requests.Request.body", return_value=b"csrf_token=%FF"):
            res_bad_decode = client.post(
                "/test", headers={"content-type": "application/x-www-form-urlencoded"}
            )
            assert res_bad_decode.status_code == 403


# ===========================================================================
# 2. file_organizer/api/repositories/session_repo.py Tests
# ===========================================================================


class TestSessionRepository:
    @pytest.fixture(autouse=True)
    def setup_db(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        TestingSession = sessionmaker(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        self.db = TestingSession()

        # Create a dummy user
        self.user = User(
            id="user_1",
            username="testuser",
            email="test@example.com",
            hashed_password="pw",
            is_active=True,
        )
        self.db.add(self.user)
        self.db.commit()

        yield

        self.db.close()
        Base.metadata.drop_all(bind=self.engine)

    def test_session_lifecycle(self) -> None:
        now = datetime.now(UTC)
        expires = now + timedelta(days=1)

        # 1. Create a session
        session_row = SessionRepository.create(
            self.db,
            user_id="user_1",
            token_hash="hash_1",
            expires_at=expires,
            refresh_token_hash="refresh_hash_1",
            user_agent="Mozilla",
            ip_address="127.0.0.1",
        )
        assert session_row.id is not None
        assert session_row.user_id == "user_1"
        assert session_row.token_hash == "hash_1"

        # 2. Get active by token hash
        active = SessionRepository.get_active_by_token_hash(self.db, "hash_1", now=now)
        assert active is not None
        assert active.id == session_row.id

        # Non-matching token hash
        assert SessionRepository.get_active_by_token_hash(self.db, "non_existent", now=now) is None

        # 3. List active sessions for user
        active_list = SessionRepository.list_active_for_user(self.db, "user_1", now=now)
        assert len(active_list) == 1
        assert active_list[0].id == session_row.id

        # 4. Revoke session
        assert SessionRepository.revoke(self.db, session_row.id) is True
        # Already revoked session shouldn't be active
        assert SessionRepository.get_active_by_token_hash(self.db, "hash_1", now=now) is None

        # Revoke non-existent session
        assert SessionRepository.revoke(self.db, "non_existent") is False

        # 5. Prune expired and revoked sessions
        # Since we just revoked the session, it should be pruned
        pruned_count = SessionRepository.prune_expired(self.db, now=now)
        assert pruned_count == 1

        # Check that it's actually deleted
        assert self.db.get(UserSession, session_row.id) is None


# ===========================================================================
# 3. file_organizer/api/api_keys.py Tests
# ===========================================================================


class TestAPIKeys:
    def test_api_key_operations(self, tmp_path: Path) -> None:
        # 1. Generate and hash key
        key = generate_api_key(prefix="test")
        assert key.startswith("test_")

        hashed = hash_api_key(key)
        assert hashed is not None

        # 2. Match and verify
        hashes = [hashed, "invalid_hash"]
        assert match_api_key_hash(key, hashes) == hashed
        assert match_api_key_hash("invalid_key", hashes) is None
        assert verify_api_key(key, hashes) is True
        assert verify_api_key("invalid_key", hashes) is False

        # ValueError/TypeError exceptions in checkpw
        bad_hashes = ["bad_hash"]
        assert match_api_key_hash(key, bad_hashes) is None

        # 3. Identifier
        assert api_key_identifier(key, hashes) is not None
        # Non-matching
        assert api_key_identifier("invalid_key", hashes) is None
        # Non-prefixed or custom structure
        parts = key.split("_")
        assert api_key_identifier(key, hashes) == parts[1]

        # If parts don't match or key is structured differently
        with patch("bcrypt.checkpw", return_value=True):
            assert api_key_identifier("malformedkey", ["dummy_hash"]) == "dummy_hash"[-12:]

        # 4. Write key file
        output_file = tmp_path / "keys" / "key.txt"
        _write_key(output_file, key)
        assert output_file.exists()
        assert output_file.read_text(encoding="utf-8") == key

    def test_api_keys_main_cli(self, tmp_path: Path) -> None:
        # 1. Help flag
        with patch("builtins.print") as mock_print:
            assert _main(["--help"]) == 0
            mock_print.assert_called_with(
                "Usage: fo api-keys generate --output PATH [--prefix PREFIX]"
            )

        # 2. Missing output path
        with patch("builtins.print") as mock_print:
            assert _main([]) == 1
            mock_print.assert_any_call(
                "Missing --output PATH to safely store the generated API key."
            )

        # 3. Output without path argument
        assert _main(["--output"]) == 1

        # 4. Prefix without prefix argument
        assert _main(["--output", str(tmp_path / "key.txt"), "--prefix"]) == 1

        # 5. Successful generation
        output_file = tmp_path / "generated_key.txt"
        assert _main(["--output", str(output_file), "--prefix", "custom"]) == 0
        assert output_file.exists()
        key_content = output_file.read_text()
        assert key_content.startswith("custom_")


# ===========================================================================
# 4. file_organizer/api/routers/realtime.py Tests
# ===========================================================================


class TestRealtimeWebSocket:
    @pytest.fixture
    def app(self) -> FastAPI:
        app = FastAPI()
        app.include_router(realtime_router)
        return app

    def test_websocket_auth_bypass_when_disabled(self, app: FastAPI) -> None:
        # Auth disabled, websocket_token not set -> Should connect immediately
        settings = ApiSettings(auth_enabled=False, websocket_token=None, websocket_ping_interval=10)
        app.dependency_overrides[get_settings] = lambda: settings
        app.dependency_overrides[get_db] = lambda: MagicMock()
        app.dependency_overrides[get_token_store] = lambda: MagicMock()

        client = TestClient(app)
        with client.websocket_connect("/ws/client_1") as websocket:
            welcome = websocket.receive_json()
            assert welcome["type"] == "connection"
            assert welcome["status"] == "connected"

            # Send ping, should receive pong
            websocket.send_json({"type": "ping"})
            data = websocket.receive_json()
            assert data == {"type": "pong"}

    def test_websocket_auth_token_required_in_settings(self, app: FastAPI) -> None:
        # Auth disabled, but websocket_token is set
        settings = ApiSettings(
            auth_enabled=False, websocket_token="secret_token", websocket_ping_interval=10
        )
        app.dependency_overrides[get_settings] = lambda: settings
        app.dependency_overrides[get_db] = lambda: MagicMock()
        app.dependency_overrides[get_token_store] = lambda: MagicMock()

        client = TestClient(app)

        # 1. Connect without token -> should fail
        with pytest.raises(Exception):  # noqa: B017, pytest-raises-hygiene
            with client.websocket_connect("/ws/client_1") as websocket:
                pass

        # 2. Connect with invalid token -> should fail
        with pytest.raises(Exception):  # noqa: B017, pytest-raises-hygiene
            with client.websocket_connect("/ws/client_1?token=wrong") as websocket:
                pass

        # 3. Connect with valid token in query param -> should succeed
        with client.websocket_connect("/ws/client_1?token=secret_token") as websocket:
            welcome = websocket.receive_json()
            assert welcome["type"] == "connection"
            websocket.send_json({"type": "ping"})
            assert websocket.receive_json() == {"type": "pong"}

        # 4. Connect with valid token in Authorization header -> should succeed
        with client.websocket_connect(
            "/ws/client_1", headers={"authorization": "Bearer secret_token"}
        ) as websocket:
            welcome = websocket.receive_json()
            assert welcome["type"] == "connection"
            websocket.send_json({"type": "ping"})
            assert websocket.receive_json() == {"type": "pong"}

    def test_websocket_jwt_auth_enabled(self, app: FastAPI) -> None:
        # Auth enabled
        settings = ApiSettings(auth_enabled=True, websocket_token=None, websocket_ping_interval=10)

        mock_db = MagicMock()
        mock_token_store = MagicMock()
        mock_token_store.is_access_revoked.return_value = False

        # Mock decode_token and is_access_token
        mock_payload = {"jti": "jti_val", "user_id": "user_val", "type": "access"}

        # Active user
        mock_user = MagicMock(is_active=True)
        mock_db.query().filter().first.return_value = mock_user

        app.dependency_overrides[get_settings] = lambda: settings
        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_token_store] = lambda: mock_token_store

        client = TestClient(app)

        with patch("file_organizer.api.routers.realtime.decode_token", return_value=mock_payload):
            with patch("file_organizer.api.routers.realtime.is_access_token", return_value=True):
                # Valid JWT token
                with client.websocket_connect("/ws/client_1?token=valid_jwt") as websocket:
                    welcome = websocket.receive_json()
                    assert welcome["type"] == "connection"
                    websocket.send_json({"type": "ping"})
                    assert websocket.receive_json() == {"type": "pong"}

                # Invalid User or inactive
                mock_user.is_active = False
                with pytest.raises(Exception):  # noqa: B017, pytest-raises-hygiene
                    with client.websocket_connect("/ws/client_1?token=valid_jwt") as websocket:
                        pass

                # Revoked token
                mock_user.is_active = True
                mock_token_store.is_access_revoked.return_value = True
                with pytest.raises(Exception):  # noqa: B017, pytest-raises-hygiene
                    with client.websocket_connect("/ws/client_1?token=valid_jwt") as websocket:
                        pass

    def test_websocket_messaging_and_subscription(self, app: FastAPI) -> None:
        settings = ApiSettings(auth_enabled=False, websocket_token=None, websocket_ping_interval=10)
        app.dependency_overrides[get_settings] = lambda: settings
        app.dependency_overrides[get_db] = lambda: MagicMock()
        app.dependency_overrides[get_token_store] = lambda: MagicMock()

        client = TestClient(app)
        with client.websocket_connect("/ws/client_1") as websocket:
            welcome = websocket.receive_json()
            assert welcome["type"] == "connection"

            # 1. Subscribe to channel
            websocket.send_json({"type": "subscribe", "channel": "events"})
            assert websocket.receive_json() == {"type": "subscribed", "channel": "events"}

            # 2. Unsubscribe from channel
            websocket.send_json({"type": "unsubscribe", "channel": "events"})
            assert websocket.receive_json() == {"type": "unsubscribed", "channel": "events"}

            # 3. Subscribe validation errors
            websocket.send_json({"type": "subscribe"})  # missing channel
            assert websocket.receive_json() == {
                "type": "error",
                "message": "Invalid or missing 'channel' field for subscribe; expected a non-empty string",
            }

            websocket.send_json({"type": "unsubscribe"})  # missing channel
            assert websocket.receive_json() == {
                "type": "error",
                "message": "Invalid or missing 'channel' field for unsubscribe; expected a non-empty string",
            }

            # 4. Unknown message type
            websocket.send_json({"type": "unknown_action"})
            assert websocket.receive_json() == {"type": "error", "message": "Unknown message type"}

            # 5. Invalid message type field
            websocket.send_json({"type": 123})
            assert websocket.receive_json() == {
                "type": "error",
                "message": "Invalid or missing 'type' field in message",
            }

            # 6. Invalid JSON format (not a dict)
            websocket.send_json(["not", "a", "dict"])
            assert websocket.receive_json() == {
                "type": "error",
                "message": "Invalid message format; expected a JSON object",
            }

            # 7. Invalid JSON payload
            websocket.send_text("{invalid json")
            assert websocket.receive_json() == {"type": "error", "message": "Invalid JSON payload"}

    def test_websocket_heartbeat(self, app: FastAPI) -> None:
        settings = ApiSettings(auth_enabled=False, websocket_token=None, websocket_ping_interval=10)
        app.dependency_overrides[get_settings] = lambda: settings
        app.dependency_overrides[get_db] = lambda: MagicMock()
        app.dependency_overrides[get_token_store] = lambda: MagicMock()

        client = TestClient(app)

        call_count = 0

        async def mock_wait_for(fut, timeout):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise TimeoutError()
            return await fut

        with patch(
            "file_organizer.api.routers.realtime.asyncio.wait_for", side_effect=mock_wait_for
        ):
            with client.websocket_connect("/ws/client_1") as websocket:
                # Welcome message
                welcome = websocket.receive_json()
                assert welcome["type"] == "connection"

                # Ping message sent by heartbeat
                ping_msg = websocket.receive_json()
                assert ping_msg == {"type": "ping"}

    def test_websocket_endpoint_pong_message(self, app: FastAPI) -> None:
        settings = ApiSettings(auth_enabled=False, websocket_token=None, websocket_ping_interval=10)
        app.dependency_overrides[get_settings] = lambda: settings
        app.dependency_overrides[get_db] = lambda: MagicMock()
        app.dependency_overrides[get_token_store] = lambda: MagicMock()

        client = TestClient(app)
        with client.websocket_connect("/ws/client_1") as websocket:
            welcome = websocket.receive_json()
            assert welcome["type"] == "connection"

            # Send pong (should be ignored, no response sent)
            websocket.send_json({"type": "pong"})

            # Send ping to make sure connection is still alive
            websocket.send_json({"type": "ping"})
            assert websocket.receive_json() == {"type": "pong"}


class TestRealtimeWebSocketPrivateHelpers:
    def test_extract_token_direct(self) -> None:
        from starlette.websockets import WebSocket

        from file_organizer.api.routers.realtime import _extract_token

        # 1. token passed directly
        assert _extract_token(None, "my_token") == "my_token"

        # 2. token from auth header (Bearer)
        mock_ws = MagicMock(spec=WebSocket)
        mock_ws.headers = {"authorization": "Bearer my_token"}
        assert _extract_token(mock_ws, None) == "my_token"

        # 3. token from auth header (no authorization header)
        mock_ws.headers = {}
        assert _extract_token(mock_ws, None) is None

        # 4. token from auth header (non-Bearer / length != 2)
        mock_ws.headers = {"authorization": "Bearer"}
        assert _extract_token(mock_ws, None) == "Bearer"

        mock_ws.headers = {"authorization": "Basic secret_base64"}
        assert _extract_token(mock_ws, None) == "Basic secret_base64"

    def test_jwt_valid_direct(self) -> None:
        from file_organizer.api.auth import TokenError
        from file_organizer.api.routers.realtime import _jwt_valid

        mock_db = MagicMock()
        mock_token_store = MagicMock()
        settings = ApiSettings(auth_enabled=True, websocket_token=None, websocket_ping_interval=10)

        # 1. TokenError raised in decode_token
        with patch(
            "file_organizer.api.routers.realtime.decode_token", side_effect=TokenError("invalid")
        ):
            assert _jwt_valid("token", settings, mock_db, mock_token_store) is False

        # 2. is_access_token returns False
        with patch(
            "file_organizer.api.routers.realtime.decode_token",
            return_value={"jti": "jti_val", "user_id": "user_id"},
        ):
            with patch("file_organizer.api.routers.realtime.is_access_token", return_value=False):
                assert _jwt_valid("token", settings, mock_db, mock_token_store) is False

        # 3. user_id not a string
        with patch(
            "file_organizer.api.routers.realtime.decode_token",
            return_value={"jti": "jti_val", "user_id": 123},
        ):
            with patch("file_organizer.api.routers.realtime.is_access_token", return_value=True):
                assert _jwt_valid("token", settings, mock_db, mock_token_store) is False

    def test_token_valid_direct(self) -> None:
        from file_organizer.api.routers.realtime import _token_valid

        mock_db = MagicMock()
        mock_token_store = MagicMock()

        # 1. auth_enabled=True, token matches static websocket_token
        settings = ApiSettings(
            auth_enabled=True, websocket_token="static_token", websocket_ping_interval=10
        )
        with patch("file_organizer.api.routers.realtime._jwt_valid", return_value=False):
            assert _token_valid("static_token", settings, mock_db, mock_token_store) is True
            assert _token_valid("wrong_token", settings, mock_db, mock_token_store) is False
            assert _token_valid(None, settings, mock_db, mock_token_store) is False

    @pytest.mark.asyncio
    async def test_send_error_direct(self) -> None:
        from starlette.websockets import WebSocket, WebSocketState

        from file_organizer.api.routers.realtime import _send_error

        # 1. client state is not connected
        mock_ws = MagicMock(spec=WebSocket)
        mock_ws.client_state = WebSocketState.DISCONNECTED
        await _send_error(mock_ws, "error msg")

        # 2. send raises Exception
        mock_ws.client_state = WebSocketState.CONNECTED
        with patch(
            "file_organizer.api.routers.realtime.realtime_manager.send_personal_message",
            side_effect=Exception("failed"),
        ):
            # Should catch exception and log it
            await _send_error(mock_ws, "error msg")

    @pytest.mark.asyncio
    async def test_heartbeat_direct(self) -> None:
        from starlette.websockets import WebSocket

        from file_organizer.api.routers.realtime import _heartbeat

        mock_ws = MagicMock(spec=WebSocket)
        # 1. send_json raises exception
        mock_ws.send_json = MagicMock(side_effect=Exception("disconnected"))

        call_count = 0

        async def mock_wait_for(fut, timeout):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise TimeoutError()
            return await fut

        stop_event = asyncio.Event()
        with patch(
            "file_organizer.api.routers.realtime.asyncio.wait_for", side_effect=mock_wait_for
        ):
            # This should try to send, catch the exception, and break
            await _heartbeat(mock_ws, 10, stop_event)
            assert call_count == 1

        # 2. wait_for returns successfully (break loop)
        async def mock_wait_for_success(fut, timeout):
            return None

        stop_event = asyncio.Event()
        with patch(
            "file_organizer.api.routers.realtime.asyncio.wait_for",
            side_effect=mock_wait_for_success,
        ):
            await _heartbeat(mock_ws, 10, stop_event)
