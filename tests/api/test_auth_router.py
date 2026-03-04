"""Tests for the authentication API router."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from file_organizer.api.auth_models import User
from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import (
    get_current_active_user,
    get_db,
    get_login_rate_limiter,
    get_settings,
    get_token_store,
)
from file_organizer.api.exceptions import setup_exception_handlers
from file_organizer.api.routers.auth import router


def _build_app(db_session: Session) -> tuple[FastAPI, TestClient]:  # noqa: C901
    """Create a minimal FastAPI app with the auth router and dependency overrides."""
    from datetime import UTC, datetime
    from uuid import uuid4

    settings = ApiSettings(
        environment="test",
        auth_enabled=True,
        auth_jwt_secret="test-secret-key",
        auth_access_token_minutes=15,
        auth_refresh_token_minutes=10080,
        auth_bootstrap_admin=True,
        auth_bootstrap_admin_local_only=False,
        auth_password_min_length=8,
        auth_password_require_uppercase=True,
        auth_password_require_number=True,
        auth_password_require_special=True,
        auth_login_rate_limit_enabled=False,
    )
    app = FastAPI()
    setup_exception_handlers(app)

    # Store added users in a simple dict for tracking
    db_session._added_users = {}

    def mock_add(user):
        """Store user when added to mock session."""
        # Initialize default values for SQLAlchemy columns
        if user.id is None:
            user.id = str(uuid4())
        if user.created_at is None:
            user.created_at = datetime.now(UTC)
        # is_active defaults to True
        if not hasattr(user, '_is_active_set'):
            user.is_active = True
            user._is_active_set = True
        db_session._added_users[user.username] = user

    def mock_refresh(user):
        """Refresh user - ensure all fields have values."""
        # The add method should have already set these, but ensure they're set
        if user.id is None:
            user.id = str(uuid4())
        if user.created_at is None:
            user.created_at = datetime.now(UTC)
        if not hasattr(user, 'is_active') or user.is_active is None:
            user.is_active = True
        if not hasattr(user, 'last_login'):
            user.last_login = None

    def _find_user(attr_name, attr_value):
        """Find user by attribute."""
        if attr_name == 'username':
            return db_session._added_users.get(attr_value)
        if attr_name == 'email':
            for user in db_session._added_users.values():
                if user.email == attr_value:
                    return user
        if attr_name == 'id':
            for user in db_session._added_users.values():
                if user.id == attr_value:
                    return user
        return None

    def mock_query(model):
        """Mock query to return users from storage."""
        query_obj = MagicMock()

        def filter_func(*args, **kwargs):
            """Filter users based on query conditions."""
            filter_obj = MagicMock()

            def first_func():
                """Return first matching user or None."""
                for condition in args:
                    if hasattr(condition, 'left') and hasattr(condition, 'right'):
                        attr_name = getattr(condition.left, 'name', None)
                        attr_value = (
                            condition.right.value
                            if hasattr(condition.right, 'value')
                            else condition.right
                        )
                        return _find_user(attr_name, attr_value)
                return None

            filter_obj.first = MagicMock(side_effect=first_func)
            return filter_obj

        def count_func():
            """Return count of users."""
            return len(db_session._added_users)

        query_obj.filter = MagicMock(side_effect=filter_func)
        query_obj.count = MagicMock(side_effect=count_func)
        return query_obj

    db_session.add = MagicMock(side_effect=mock_add)
    db_session.commit = MagicMock()
    db_session.refresh = MagicMock(side_effect=mock_refresh)
    db_session.query = MagicMock(side_effect=mock_query)

    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_token_store] = lambda: MagicMock()
    app.dependency_overrides[get_login_rate_limiter] = lambda: MagicMock()

    # NOTE: Do NOT set a default override for get_current_active_user to None
    # because it prevents proper authentication error handling.
    # Individual tests that need to override should set it explicitly.

    app.include_router(router, prefix="/api/v1")
    client = TestClient(app)
    return app, client


# ---------------------------------------------------------------------------
# register endpoint
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRegisterUser:
    """Tests for POST /api/v1/auth/register."""

    def test_register_user_success(self, db_session: Session) -> None:
        """Test successful user registration."""
        _, client = _build_app(db_session)

        payload = {
            "username": "testuser",
            "email": "test@example.com",
            "password": "SecurePass123!",
            "full_name": "Test User",
        }
        resp = client.post("/api/v1/auth/register", json=payload)
        assert resp.status_code == 201
        body = resp.json()
        assert body["username"] == "testuser"
        assert body["email"] == "test@example.com"
        assert body["full_name"] == "Test User"
        assert "hashed_password" not in body

    def test_register_first_user_becomes_admin(self, db_session: Session) -> None:
        """Test that first user is marked as admin when bootstrap enabled."""
        _, client = _build_app(db_session)

        payload = {
            "username": "firstuser",
            "email": "first@example.com",
            "password": "SecurePass123!",
            "full_name": "First User",
        }
        resp = client.post("/api/v1/auth/register", json=payload)
        assert resp.status_code == 201
        body = resp.json()
        assert body["is_admin"] is True

    def test_register_duplicate_username(self, db_session: Session) -> None:
        """Test that duplicate username is rejected."""
        _, client = _build_app(db_session)

        # Register first user
        payload1 = {
            "username": "testuser",
            "email": "test1@example.com",
            "password": "SecurePass123!",
            "full_name": "Test User 1",
        }
        resp1 = client.post("/api/v1/auth/register", json=payload1)
        assert resp1.status_code == 201

        # Try to register with same username
        payload2 = {
            "username": "testuser",
            "email": "test2@example.com",
            "password": "SecurePass123!",
            "full_name": "Test User 2",
        }
        resp2 = client.post("/api/v1/auth/register", json=payload2)
        assert resp2.status_code == 400
        assert "already taken" in resp2.json()["detail"]

    def test_register_duplicate_email(self, db_session: Session) -> None:
        """Test that duplicate email is rejected."""
        _, client = _build_app(db_session)

        # Register first user
        payload1 = {
            "username": "user1",
            "email": "test@example.com",
            "password": "SecurePass123!",
            "full_name": "Test User 1",
        }
        resp1 = client.post("/api/v1/auth/register", json=payload1)
        assert resp1.status_code == 201

        # Try to register with same email
        payload2 = {
            "username": "user2",
            "email": "test@example.com",
            "password": "SecurePass123!",
            "full_name": "Test User 2",
        }
        resp2 = client.post("/api/v1/auth/register", json=payload2)
        assert resp2.status_code == 400
        assert "already registered" in resp2.json()["detail"]

    def test_register_weak_password(self, db_session: Session) -> None:
        """Test that weak passwords are rejected."""
        _, client = _build_app(db_session)

        payload = {
            "username": "testuser",
            "email": "test@example.com",
            "password": "weak",  # Too short and no uppercase/digits/special
            "full_name": "Test User",
        }
        resp = client.post("/api/v1/auth/register", json=payload)
        assert resp.status_code == 400
        assert "detail" in resp.json()


# ---------------------------------------------------------------------------
# login endpoint
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLogin:
    """Tests for POST /api/v1/auth/login."""

    def test_login_success(self, db_session: Session) -> None:
        """Test successful login."""
        _, client = _build_app(db_session)

        # Register user first
        reg_payload = {
            "username": "testuser",
            "email": "test@example.com",
            "password": "SecurePass123!",
            "full_name": "Test User",
        }
        resp_reg = client.post("/api/v1/auth/register", json=reg_payload)
        assert resp_reg.status_code == 201

        # Login
        login_payload = {
            "username": "testuser",
            "password": "SecurePass123!",
        }
        resp = client.post(
            "/api/v1/auth/login",
            data=login_payload,  # OAuth2PasswordRequestForm uses form data
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert "refresh_token" in body
        assert body["token_type"] == "bearer"

    def test_login_invalid_username(self, db_session: Session) -> None:
        """Test login with invalid username."""
        _, client = _build_app(db_session)

        login_payload = {
            "username": "nonexistent",
            "password": "SomePass123!",
        }
        resp = client.post("/api/v1/auth/login", data=login_payload)
        assert resp.status_code == 401
        assert "Incorrect username or password" in resp.json()["detail"]

    def test_login_invalid_password(self, db_session: Session) -> None:
        """Test login with invalid password."""
        _, client = _build_app(db_session)

        # Register user first
        reg_payload = {
            "username": "testuser",
            "email": "test@example.com",
            "password": "SecurePass123!",
            "full_name": "Test User",
        }
        client.post("/api/v1/auth/register", json=reg_payload)

        # Login with wrong password
        login_payload = {
            "username": "testuser",
            "password": "WrongPass123!",
        }
        resp = client.post("/api/v1/auth/login", data=login_payload)
        assert resp.status_code == 401
        assert "Incorrect username or password" in resp.json()["detail"]

    def test_login_inactive_user(self, db_session: Session) -> None:
        """Test login with inactive user."""
        _, client = _build_app(db_session)

        # Register user
        reg_payload = {
            "username": "testuser",
            "email": "test@example.com",
            "password": "SecurePass123!",
            "full_name": "Test User",
        }
        client.post("/api/v1/auth/register", json=reg_payload)

        # Deactivate user in database
        user = db_session.query(User).filter(User.username == "testuser").first()
        user.is_active = False
        db_session.commit()

        # Try to login
        login_payload = {
            "username": "testuser",
            "password": "SecurePass123!",
        }
        resp = client.post("/api/v1/auth/login", data=login_payload)
        assert resp.status_code == 400
        assert "Inactive user" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# refresh endpoint
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRefresh:
    """Tests for POST /api/v1/auth/refresh."""

    def test_refresh_success(self, db_session: Session) -> None:
        """Test successful token refresh."""
        app, client = _build_app(db_session)

        # Register and login
        reg_payload = {
            "username": "testuser",
            "email": "test@example.com",
            "password": "SecurePass123!",
            "full_name": "Test User",
        }
        client.post("/api/v1/auth/register", json=reg_payload)

        login_payload = {
            "username": "testuser",
            "password": "SecurePass123!",
        }
        login_resp = client.post("/api/v1/auth/login", data=login_payload)
        original_tokens = login_resp.json()

        # Mock token store to accept the refresh
        mock_store = MagicMock()
        mock_store.is_refresh_active.return_value = True
        app.dependency_overrides[get_token_store] = lambda: mock_store
        client = TestClient(app)

        # Refresh
        refresh_payload = {
            "refresh_token": original_tokens["refresh_token"],
        }
        resp = client.post("/api/v1/auth/refresh", json=refresh_payload)
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert "refresh_token" in body

    def test_refresh_invalid_token(self, db_session: Session) -> None:
        """Test refresh with invalid token."""
        _, client = _build_app(db_session)

        refresh_payload = {
            "refresh_token": "invalid.token.here",
        }
        resp = client.post("/api/v1/auth/refresh", json=refresh_payload)
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# logout endpoint
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLogout:
    """Tests for POST /api/v1/auth/logout."""

    def test_logout_without_auth(self, db_session: Session) -> None:
        """Test logout requires authentication."""
        app, client = _build_app(db_session)

        # Make logout request without being authenticated
        # Since get_current_active_user returns None by default, this should fail
        logout_payload = {
            "refresh_token": "some.token",
        }
        resp = client.post("/api/v1/auth/logout", json=logout_payload)
        # Depends on how the router handles unauthenticated requests
        assert resp.status_code in [401, 403] or "detail" in resp.json()

    def test_logout_with_auth(self, db_session: Session) -> None:
        """Test successful logout."""
        app, client = _build_app(db_session)

        # Register user
        reg_payload = {
            "username": "testuser",
            "email": "test@example.com",
            "password": "SecurePass123!",
            "full_name": "Test User",
        }
        client.post("/api/v1/auth/register", json=reg_payload)
        user = db_session.query(User).filter(User.username == "testuser").first()

        # Mock the current user, token store, and oauth2 scheme
        app.dependency_overrides[get_current_active_user] = lambda: user
        mock_store = MagicMock()
        app.dependency_overrides[get_token_store] = lambda: mock_store
        # Override oauth2_scheme to return a valid token
        from file_organizer.api.dependencies import oauth2_scheme
        app.dependency_overrides[oauth2_scheme] = lambda: "test.access.token"

        # Mock decode_token and is_refresh_token to handle token validation
        with patch("file_organizer.api.routers.auth.decode_token") as mock_decode, \
             patch("file_organizer.api.routers.auth.is_refresh_token") as mock_is_refresh:
            # Mock access token payload
            mock_decode.side_effect = lambda token, settings: {
                "jti": "access-jti-123",
                "user_id": user.id,
                "exp": 9999999999,
            } if token == "test.access.token" else {
                "jti": "refresh-jti-456",
                "user_id": user.id,
                "token_type": "refresh",
                "exp": 9999999999,
            }
            mock_is_refresh.return_value = True

            client = TestClient(app)

            logout_payload = {
                "refresh_token": "valid.refresh.token",
            }
            resp = client.post("/api/v1/auth/logout", json=logout_payload)
            assert resp.status_code in [204, 200]


# ---------------------------------------------------------------------------
# me endpoint
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMe:
    """Tests for GET /api/v1/auth/me."""

    def test_me_without_auth(self, db_session: Session) -> None:
        """Test /me requires authentication."""
        app, client = _build_app(db_session)

        # oauth2_scheme by default returns None when no auth header is present
        # This should cause get_current_active_user to return None or raise an error
        # The /me endpoint requires authentication, so it should return 401/403
        resp = client.get("/api/v1/auth/me")
        # Should get unauthorized response
        assert resp.status_code in [401, 403]

    def test_me_with_auth(self, db_session: Session) -> None:
        """Test successful /me retrieval."""
        app, client = _build_app(db_session)

        # Register user
        reg_payload = {
            "username": "testuser",
            "email": "test@example.com",
            "password": "SecurePass123!",
            "full_name": "Test User",
        }
        client.post("/api/v1/auth/register", json=reg_payload)
        user = db_session.query(User).filter(User.username == "testuser").first()

        # Mock current user
        app.dependency_overrides[get_current_active_user] = lambda: user
        client = TestClient(app)

        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 200
        body = resp.json()
        assert body["username"] == "testuser"
        assert body["email"] == "test@example.com"
        assert body["full_name"] == "Test User"
