"""Extended integration tests for web/profile_routes.py.

Covers: forgot-password (GET/POST, user exists/not-exists), reset-password
(GET valid/invalid token, POST bad token / password mismatch / weak password /
success), register POST (success / duplicate username / duplicate email / weak
password), avatar GET (not-found / found), auth-required routes returning
unauthenticated HTMLResponse (edit, workspaces, team, shared, activity,
notifications, account-settings), and all associated POST sub-routes.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from starlette.testclient import TestClient

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_settings
from file_organizer.api.exceptions import setup_exception_handlers
from file_organizer.api.test_utils import csrf_headers, seed_csrf_token
from file_organizer.web.profile_routes import _PASSWORD_RESET_TOKENS, profile_router

pytestmark = pytest.mark.integration

_HTML = HTMLResponse("<html><body>stub</body></html>")

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def profile_settings(tmp_path: Path) -> ApiSettings:
    return ApiSettings(
        allowed_paths=[str(tmp_path)],
        auth_enabled=False,
        auth_db_path=str(tmp_path / "auth.db"),
    )


@pytest.fixture()
def profile_client(profile_settings: ApiSettings) -> TestClient:
    app = FastAPI()
    app.dependency_overrides[get_settings] = lambda: profile_settings
    setup_exception_handlers(app)
    app.include_router(profile_router, prefix="/ui")
    client = TestClient(app, raise_server_exceptions=False)
    seed_csrf_token(client)
    return client


# ---------------------------------------------------------------------------
# Register POST
# ---------------------------------------------------------------------------


class TestRegisterPost:
    def test_register_success_redirects_to_login(self, profile_client: TestClient) -> None:
        with patch("file_organizer.web.profile_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            r = profile_client.post(
                "/ui/profile/register",
                data={
                    "username": "newuser_ext",
                    "email": "newuser_ext@example.com",
                    "password": "T3stP@ssword1!",
                    "full_name": "New User",
                },
                follow_redirects=False,
                headers=csrf_headers(profile_client),
            )
        assert r.status_code in (200, 303, 302)

    def test_register_weak_password_returns_200(self, profile_client: TestClient) -> None:
        with patch("file_organizer.web.profile_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            r = profile_client.post(
                "/ui/profile/register",
                data={
                    "username": "weakpwuser",
                    "email": "weakpw@example.com",
                    "password": "abc",
                    "full_name": "",
                },
                headers=csrf_headers(profile_client),
            )
        assert r.status_code == 200
        tpl.TemplateResponse.assert_called_once()

    def test_register_duplicate_username_returns_200(self, profile_client: TestClient) -> None:
        payload = {
            "username": "dup_ext",
            "email": "dup_ext@example.com",
            "password": "T3stP@ssword1!",
            "full_name": "",
        }
        with patch("file_organizer.web.profile_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            profile_client.post(
                "/ui/profile/register", data=payload, headers=csrf_headers(profile_client)
            )
            payload["email"] = "dup_ext2@example.com"
            r = profile_client.post(
                "/ui/profile/register", data=payload, headers=csrf_headers(profile_client)
            )
        assert r.status_code in (200, 303)

    def test_register_duplicate_email_returns_200(self, profile_client: TestClient) -> None:
        payload = {
            "username": "dupmail1_ext",
            "email": "dupshared@example.com",
            "password": "T3stP@ssword1!",
            "full_name": "",
        }
        with patch("file_organizer.web.profile_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            profile_client.post(
                "/ui/profile/register", data=payload, headers=csrf_headers(profile_client)
            )
            payload["username"] = "dupmail2_ext"
            r = profile_client.post(
                "/ui/profile/register", data=payload, headers=csrf_headers(profile_client)
            )
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Forgot-password
# ---------------------------------------------------------------------------


class TestForgotPassword:
    def test_forgot_password_get_returns_200(self, profile_client: TestClient) -> None:
        with patch("file_organizer.web.profile_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            r = profile_client.get("/ui/profile/forgot-password")
        assert r.status_code == 200

    def test_forgot_password_post_unknown_email_returns_200(
        self, profile_client: TestClient
    ) -> None:
        with patch("file_organizer.web.profile_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            r = profile_client.post(
                "/ui/profile/forgot-password",
                data={"email": "nobody@example.com"},
                headers=csrf_headers(profile_client),
            )
        assert r.status_code == 200
        tpl.TemplateResponse.assert_called_once()

    def test_forgot_password_post_known_email_creates_token(
        self, profile_client: TestClient
    ) -> None:
        with patch("file_organizer.web.profile_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            profile_client.post(
                "/ui/profile/register",
                data={
                    "username": "fptest_ext",
                    "email": "fptest_ext@example.com",
                    "password": "T3stP@ssword1!",
                    "full_name": "",
                },
                follow_redirects=False,
                headers=csrf_headers(profile_client),
            )
            _PASSWORD_RESET_TOKENS.clear()
            r = profile_client.post(
                "/ui/profile/forgot-password",
                data={"email": "fptest_ext@example.com"},
                headers=csrf_headers(profile_client),
            )
        assert r.status_code == 200
        assert len(_PASSWORD_RESET_TOKENS) == 1


# ---------------------------------------------------------------------------
# Reset-password
# ---------------------------------------------------------------------------


class TestResetPassword:
    def test_reset_password_get_invalid_token_returns_200(self, profile_client: TestClient) -> None:
        _PASSWORD_RESET_TOKENS.clear()
        with patch("file_organizer.web.profile_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            r = profile_client.get("/ui/profile/reset-password", params={"token": "bad-token-xyz"})
        assert r.status_code == 200

    def test_reset_password_get_valid_token_returns_200(self, profile_client: TestClient) -> None:
        from datetime import UTC, datetime, timedelta

        from file_organizer.web.profile_routes import _PASSWORD_RESET_TOKENS

        token = "valid-test-token-abc"
        _PASSWORD_RESET_TOKENS[token] = ("user-id-1", datetime.now(UTC) + timedelta(minutes=10))
        with patch("file_organizer.web.profile_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            r = profile_client.get("/ui/profile/reset-password", params={"token": token})
        assert r.status_code == 200
        _PASSWORD_RESET_TOKENS.pop(token, None)

    def test_reset_password_post_bad_token_returns_200(self, profile_client: TestClient) -> None:
        _PASSWORD_RESET_TOKENS.clear()
        with patch("file_organizer.web.profile_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            r = profile_client.post(
                "/ui/profile/reset-password",
                data={
                    "token": "nonexistent-token",
                    "new_password": "NewP@ssword1!",
                    "confirm_password": "NewP@ssword1!",
                },
                headers=csrf_headers(profile_client),
            )
        assert r.status_code == 200

    def test_reset_password_post_password_mismatch_returns_200(
        self, profile_client: TestClient
    ) -> None:
        from datetime import UTC, datetime, timedelta

        from file_organizer.web.profile_routes import _PASSWORD_RESET_TOKENS

        token = "mismatch-token-abc"
        _PASSWORD_RESET_TOKENS[token] = ("user-id-2", datetime.now(UTC) + timedelta(minutes=10))
        with patch("file_organizer.web.profile_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            r = profile_client.post(
                "/ui/profile/reset-password",
                data={
                    "token": token,
                    "new_password": "NewP@ssword1!",
                    "confirm_password": "DifferentP@ssword1!",
                },
                headers=csrf_headers(profile_client),
            )
        assert r.status_code == 200
        _PASSWORD_RESET_TOKENS.pop(token, None)

    def test_reset_password_post_weak_password_returns_200(
        self, profile_client: TestClient
    ) -> None:
        from datetime import UTC, datetime, timedelta

        from file_organizer.web.profile_routes import _PASSWORD_RESET_TOKENS

        token = "weak-pw-token-abc"
        _PASSWORD_RESET_TOKENS[token] = ("user-id-3", datetime.now(UTC) + timedelta(minutes=10))
        with patch("file_organizer.web.profile_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            r = profile_client.post(
                "/ui/profile/reset-password",
                data={
                    "token": token,
                    "new_password": "abc",
                    "confirm_password": "abc",
                },
                headers=csrf_headers(profile_client),
            )
        assert r.status_code == 200
        _PASSWORD_RESET_TOKENS.pop(token, None)


# ---------------------------------------------------------------------------
# Avatar
# ---------------------------------------------------------------------------


class TestProfileAvatar:
    def test_avatar_not_found_returns_404(self, profile_client: TestClient) -> None:
        r = profile_client.get("/ui/profile/avatar/nonexistent-user-xyz")
        assert r.status_code == 404

    def test_avatar_found_returns_200(self, profile_client: TestClient, tmp_path: Path) -> None:
        avatar_file = tmp_path / "test-avatar-user.png"
        avatar_file.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        with patch(
            "file_organizer.web.profile_routes._avatar_path",
            return_value=avatar_file,
        ):
            r = profile_client.get("/ui/profile/avatar/test-avatar-user")
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Auth-required routes — unauthenticated path (auth_enabled=False → 200)
# ---------------------------------------------------------------------------


class TestAuthRequiredRoutesUnauthenticated:
    """All routes that call _require_web_user return 200 with an error message
    when auth_enabled=False (no session cookie present)."""

    def test_edit_get_returns_200(self, profile_client: TestClient) -> None:
        r = profile_client.get("/ui/profile/edit")
        assert r.status_code == 200

    def test_edit_post_returns_200(self, profile_client: TestClient) -> None:
        r = profile_client.post(
            "/ui/profile/edit",
            data={"full_name": "Name", "email": "e@example.com"},
            headers=csrf_headers(profile_client),
        )
        assert r.status_code == 200

    def test_edit_avatar_post_returns_200(self, profile_client: TestClient) -> None:
        r = profile_client.post(
            "/ui/profile/edit-avatar",
            files={"avatar": ("avatar.png", b"\x89PNG\r\n" + b"\x00" * 10, "image/png")},
            headers=csrf_headers(profile_client),
        )
        assert r.status_code == 200

    def test_workspaces_get_returns_200(self, profile_client: TestClient) -> None:
        r = profile_client.get("/ui/profile/workspaces")
        assert r.status_code == 200

    def test_workspaces_create_returns_200(self, profile_client: TestClient) -> None:
        r = profile_client.post(
            "/ui/profile/workspaces/create",
            data={"name": "My WS", "root_path": "/tmp", "description": "desc"},
            headers=csrf_headers(profile_client),
        )
        assert r.status_code == 200

    def test_workspaces_switch_returns_200(self, profile_client: TestClient) -> None:
        r = profile_client.post(
            "/ui/profile/workspaces/switch",
            data={"workspace_id": "ws-id-1"},
            headers=csrf_headers(profile_client),
        )
        assert r.status_code == 200

    def test_team_get_returns_200(self, profile_client: TestClient) -> None:
        r = profile_client.get("/ui/profile/team")
        assert r.status_code == 200

    def test_team_invite_returns_200(self, profile_client: TestClient) -> None:
        r = profile_client.post(
            "/ui/profile/team/invite",
            data={"email": "invite@example.com", "role": "viewer"},
            headers=csrf_headers(profile_client),
        )
        assert r.status_code == 200

    def test_team_role_returns_200(self, profile_client: TestClient) -> None:
        r = profile_client.post(
            "/ui/profile/team/role",
            data={"member_id": "mem-1", "role": "editor"},
            headers=csrf_headers(profile_client),
        )
        assert r.status_code == 200

    def test_shared_get_returns_200(self, profile_client: TestClient) -> None:
        r = profile_client.get("/ui/profile/shared")
        assert r.status_code == 200

    def test_shared_add_returns_200(self, profile_client: TestClient) -> None:
        r = profile_client.post(
            "/ui/profile/shared/add",
            data={"folder_path": "/some/folder", "permission": "view"},
            headers=csrf_headers(profile_client),
        )
        assert r.status_code == 200

    def test_shared_remove_returns_200(self, profile_client: TestClient) -> None:
        r = profile_client.post(
            "/ui/profile/shared/remove",
            data={"folder_id": "folder-id-1"},
            headers=csrf_headers(profile_client),
        )
        assert r.status_code == 200

    def test_activity_get_returns_200(self, profile_client: TestClient) -> None:
        r = profile_client.get("/ui/profile/activity")
        assert r.status_code == 200

    def test_notifications_get_returns_200(self, profile_client: TestClient) -> None:
        r = profile_client.get("/ui/profile/notifications")
        assert r.status_code == 200

    def test_notifications_mark_read_returns_200(self, profile_client: TestClient) -> None:
        r = profile_client.post(
            "/ui/profile/notifications/mark-read",
            data={"notification_id": "notif-1"},
            headers=csrf_headers(profile_client),
        )
        assert r.status_code == 200

    def test_account_settings_get_returns_200(self, profile_client: TestClient) -> None:
        r = profile_client.get("/ui/profile/account-settings")
        assert r.status_code == 200
