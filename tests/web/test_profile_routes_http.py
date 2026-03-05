"""HTTP-level tests for the profile_routes web endpoints.

Tests auth flow, session management, API keys, and workspace routes
via TestClient at the HTTP transport layer with mocked dependencies.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from starlette.testclient import TestClient

from file_organizer.api.auth import TokenBundle
from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_settings
from file_organizer.api.exceptions import setup_exception_handlers
from file_organizer.web.profile_routes import profile_router

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def settings(tmp_path):
    """Return ApiSettings with auth enabled pointing at temp dir."""
    return ApiSettings(
        allowed_paths=[str(tmp_path)],
        auth_enabled=True,
        auth_db_path=str(tmp_path / "auth.db"),
    )


@pytest.fixture()
def settings_no_auth(tmp_path):
    """Return ApiSettings with auth disabled."""
    return ApiSettings(
        allowed_paths=[str(tmp_path)],
        auth_enabled=False,
        auth_db_path=str(tmp_path / "auth.db"),
    )


@pytest.fixture()
def client(settings):
    """Create a TestClient with the profile router mounted (auth enabled)."""
    app = FastAPI()
    app.dependency_overrides[get_settings] = lambda: settings
    setup_exception_handlers(app)
    app.include_router(profile_router, prefix="/ui")
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture()
def client_no_auth(settings_no_auth):
    """Create a TestClient with auth disabled."""
    app = FastAPI()
    app.dependency_overrides[get_settings] = lambda: settings_no_auth
    setup_exception_handlers(app)
    app.include_router(profile_router, prefix="/ui")
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture()
def fake_user():
    """Return a mock User object."""
    user = MagicMock()
    user.id = "user-1"
    user.email = "test@example.com"
    user.display_name = "Test User"
    user.role = "admin"
    user.is_active = True
    user.created_at = datetime(2025, 1, 1, tzinfo=UTC)
    return user


# ---------------------------------------------------------------------------
# GET /profile (main profile page)
# ---------------------------------------------------------------------------


class TestProfilePage:
    """Test GET /ui/profile endpoint."""

    def test_profile_page_returns_200(self, client):
        with patch("file_organizer.web.profile_routes.templates") as mock_tpl:
            mock_tpl.TemplateResponse.return_value = HTMLResponse("<html>profile</html>")
            response = client.get("/ui/profile")
        assert response.status_code == 200

    def test_profile_uses_correct_template(self, client):
        with patch("file_organizer.web.profile_routes.templates") as mock_tpl:
            mock_tpl.TemplateResponse.return_value = HTMLResponse("<html></html>")
            client.get("/ui/profile")
        assert "profile/index.html" in str(mock_tpl.TemplateResponse.call_args)


# ---------------------------------------------------------------------------
# GET /profile/login
# ---------------------------------------------------------------------------


class TestLoginPage:
    """Test GET /ui/profile/login endpoint."""

    def test_login_page_returns_200(self, client):
        with patch("file_organizer.web.profile_routes.templates") as mock_tpl:
            mock_tpl.TemplateResponse.return_value = HTMLResponse("<html>login</html>")
            response = client.get("/ui/profile/login")
        assert response.status_code == 200

    def test_login_template(self, client):
        with patch("file_organizer.web.profile_routes.templates") as mock_tpl:
            mock_tpl.TemplateResponse.return_value = HTMLResponse("<html></html>")
            client.get("/ui/profile/login")
        assert "profile/login.html" in str(mock_tpl.TemplateResponse.call_args)


# ---------------------------------------------------------------------------
# POST /profile/login
# ---------------------------------------------------------------------------


class TestLoginPost:
    """Test POST /ui/profile/login endpoint."""

    def test_missing_credentials_returns_422(self, client):
        response = client.post(
            "/ui/profile/login",
            data={},
        )
        # FastAPI Form(...) rejects missing required fields with 422
        assert response.status_code == 422

    def test_invalid_credentials(self, client):
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with (
            patch("file_organizer.web.profile_routes.templates") as mock_tpl,
            patch(
                "file_organizer.web.profile_routes.create_session",
                return_value=mock_db,
            ),
        ):
            mock_tpl.TemplateResponse.return_value = HTMLResponse("<html>invalid</html>")
            response = client.post(
                "/ui/profile/login",
                data={"username": "wrong@test.com", "password": "bad"},
            )
        assert response.status_code == 200

    def test_successful_login(self, client, fake_user):
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = fake_user
        fake_user.hashed_password = "hashed"

        with (
            patch(
                "file_organizer.web.profile_routes.create_session",
                return_value=mock_db,
            ),
            patch(
                "file_organizer.web.profile_routes.verify_password",
                return_value=True,
            ),
            patch(
                "file_organizer.web.profile_routes.create_token_bundle",
                return_value=TokenBundle(
                    access_token="tok123",
                    refresh_token="ref456",
                    access_jti="jti-access-1",
                    refresh_jti="jti-refresh-1",
                    access_expires_at=datetime(2026, 6, 1, tzinfo=UTC) + timedelta(hours=1),
                    refresh_expires_at=datetime(2026, 6, 1, tzinfo=UTC) + timedelta(days=7),
                ),
            ),
        ):
            response = client.post(
                "/ui/profile/login",
                data={"username": "test@example.com", "password": "correct"},
                follow_redirects=False,
            )
        # Successful login redirects to profile
        assert response.status_code in {200, 302, 303}


# ---------------------------------------------------------------------------
# GET /profile/register
# ---------------------------------------------------------------------------


class TestRegisterPage:
    """Test GET /ui/profile/register endpoint."""

    def test_register_page_returns_200(self, client):
        with patch("file_organizer.web.profile_routes.templates") as mock_tpl:
            mock_tpl.TemplateResponse.return_value = HTMLResponse("<html>register</html>")
            response = client.get("/ui/profile/register")
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# POST /profile/register
# ---------------------------------------------------------------------------


class TestRegisterPost:
    """Test POST /ui/profile/register endpoint."""

    def test_register_with_missing_fields_returns_422(self, client):
        response = client.post(
            "/ui/profile/register",
            data={},
        )
        # FastAPI Form(...) rejects missing required fields with 422
        assert response.status_code == 422

    def test_register_with_valid_fields(self, client):
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with (
            patch("file_organizer.web.profile_routes.templates") as mock_tpl,
            patch(
                "file_organizer.web.profile_routes.create_session",
                return_value=mock_db,
            ),
        ):
            mock_tpl.TemplateResponse.return_value = HTMLResponse("<html>register</html>")
            response = client.post(
                "/ui/profile/register",
                data={
                    "username": "newuser",
                    "email": "new@test.com",
                    "password": "Password123!",
                    "full_name": "New User",
                },
            )
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# POST /profile/logout
# ---------------------------------------------------------------------------


class TestLogout:
    """Test POST /ui/profile/logout endpoint."""

    def test_logout_clears_session(self, client):
        response = client.post("/ui/profile/logout", follow_redirects=False)
        # Logout should redirect (302/303) to login page
        assert response.status_code in {200, 302, 303, 307}


# ---------------------------------------------------------------------------
# GET /profile/forgot-password
# ---------------------------------------------------------------------------


class TestForgotPassword:
    """Test GET /ui/profile/forgot-password endpoint."""

    def test_returns_200(self, client):
        with patch("file_organizer.web.profile_routes.templates") as mock_tpl:
            mock_tpl.TemplateResponse.return_value = HTMLResponse("<html>forgot</html>")
            response = client.get("/ui/profile/forgot-password")
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# GET /profile/api-keys (auth-protected)
# ---------------------------------------------------------------------------


class TestApiKeysPage:
    """Test GET /ui/profile/api-keys endpoint."""

    def test_unauthenticated_returns_html(self, client):
        with patch("file_organizer.web.profile_routes.templates") as mock_tpl:
            mock_tpl.TemplateResponse.return_value = HTMLResponse("<html>keys</html>")
            response = client.get("/ui/profile/api-keys")
        # Without session cookie, returns not-authenticated HTML
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# GET /profile/workspaces (auth-protected)
# ---------------------------------------------------------------------------


class TestWorkspacesPage:
    """Test GET /ui/profile/workspaces endpoint."""

    def test_unauthenticated_returns_html(self, client):
        with patch("file_organizer.web.profile_routes.templates") as mock_tpl:
            mock_tpl.TemplateResponse.return_value = HTMLResponse("<html>workspaces</html>")
            response = client.get("/ui/profile/workspaces")
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# GET /profile/activity (auth-protected)
# ---------------------------------------------------------------------------


class TestActivityPage:
    """Test GET /ui/profile/activity endpoint."""

    def test_unauthenticated(self, client):
        with patch("file_organizer.web.profile_routes.templates") as mock_tpl:
            mock_tpl.TemplateResponse.return_value = HTMLResponse("<html>activity</html>")
            response = client.get("/ui/profile/activity")
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# GET /profile/notifications (auth-protected)
# ---------------------------------------------------------------------------


class TestNotificationsPage:
    """Test GET /ui/profile/notifications endpoint."""

    def test_unauthenticated(self, client):
        with patch("file_organizer.web.profile_routes.templates") as mock_tpl:
            mock_tpl.TemplateResponse.return_value = HTMLResponse("<html>notifications</html>")
            response = client.get("/ui/profile/notifications")
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Auth disabled behavior
# ---------------------------------------------------------------------------


class TestAuthDisabled:
    """Test profile routes when auth is disabled."""

    def test_profile_page_auth_disabled(self, client_no_auth):
        with patch("file_organizer.web.profile_routes.templates") as mock_tpl:
            mock_tpl.TemplateResponse.return_value = HTMLResponse("<html>profile</html>")
            response = client_no_auth.get("/ui/profile")
        assert response.status_code == 200

    def test_login_page_auth_disabled(self, client_no_auth):
        with patch("file_organizer.web.profile_routes.templates") as mock_tpl:
            mock_tpl.TemplateResponse.return_value = HTMLResponse("<html>login</html>")
            response = client_no_auth.get("/ui/profile/login")
        assert response.status_code == 200
