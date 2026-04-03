"""Integration tests for authenticated profile routes in web/profile_routes.py.

Covers helper functions and authenticated routes (lines ~521-1262) including:
- _sanitize_profile_state, _append_activity, _append_notification (direct calls)
- get_current_web_user with auth_enabled=True but missing/invalid cookie
- reset_password_submit success path (user exists, valid password)
- profile_edit_partial / profile_edit_submit (GET+POST, email-in-use error)
- workspaces_partial / workspace_create / workspace_switch
- team_partial / team_invite (valid role, invalid role fallback)
- team_update_role
- shared_partial / shared_add (permission normalization) / shared_remove
- activity_partial / notifications_partial / notification_mark_read
- account_settings_partial / account_settings_change_password / account_settings_toggle_2fa
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
from file_organizer.api.routers.auth import router as auth_api_router
from file_organizer.web.profile_routes import (
    _PASSWORD_RESET_TOKENS,
    _append_activity,
    _append_notification,
    _sanitize_profile_state,
    profile_router,
)

pytestmark = pytest.mark.integration


def _html_response() -> HTMLResponse:
    return HTMLResponse("<html><body>stub</body></html>")


def _assert_authenticated_template_response(response: HTMLResponse, templates_mock: object) -> None:
    """Ensure the authenticated route path rendered a template response."""
    assert response.status_code == 200
    assert b"Not authenticated" not in response.content
    assert templates_mock.TemplateResponse.called


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_settings(tmp_path: Path) -> ApiSettings:
    return ApiSettings(
        allowed_paths=[str(tmp_path)],
        auth_enabled=True,
        auth_db_path=str(tmp_path / "auth.db"),
        auth_secret_key="test-secret-key-32chars-minimum!!",
        auth_access_token_minutes=60,
    )


def _make_app(settings: ApiSettings) -> FastAPI:
    app = FastAPI()
    app.dependency_overrides[get_settings] = lambda: settings
    setup_exception_handlers(app)
    app.include_router(auth_api_router, prefix="/api/v1")
    app.include_router(profile_router, prefix="/ui")
    return app


def _register_and_login(client: TestClient, username: str, password: str) -> str:
    """Register a user and return the session cookie value."""
    register_response = client.post(
        "/api/v1/auth/register",
        json={
            "username": username,
            "email": f"{username}@example.com",
            "password": password,
            "full_name": "Test User",
        },
    )
    assert register_response.status_code < 400
    with patch("file_organizer.web.profile_routes.templates") as tpl:
        tpl.TemplateResponse.side_effect = lambda *args, **kwargs: _html_response()
        r = client.post(
            "/ui/profile/login",
            data={"username": username, "password": password},
            follow_redirects=False,
        )
    cookie = r.cookies.get("fo_session", "")
    assert cookie, "expected /ui/profile/login to set fo_session"
    return cookie


@pytest.fixture()
def auth_settings(tmp_path: Path) -> ApiSettings:
    return _make_settings(tmp_path)


@pytest.fixture()
def auth_client(auth_settings: ApiSettings) -> TestClient:
    app = _make_app(auth_settings)
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture()
def logged_in_client(auth_client: TestClient) -> TestClient:
    """Return a client with fo_session cookie set for a registered+logged-in user."""
    cookie = _register_and_login(auth_client, "authuser", "T3stP@ssword1!")
    auth_client.cookies.set("fo_session", cookie)
    return auth_client


# ---------------------------------------------------------------------------
# Helper function unit tests (no HTTP)
# ---------------------------------------------------------------------------


class TestSanitizeProfileState:
    def test_non_dict_returns_defaults(self) -> None:
        result = _sanitize_profile_state("bad input")
        assert result["active_workspace_id"] == ""
        assert result["team_members"] == []
        assert result["two_factor_enabled"] is False

    def test_valid_dict_preserves_values(self) -> None:
        raw = {
            "active_workspace_id": "ws-123",
            "team_members": [{"id": "m1"}],
            "shared_folders": [{"id": "f1"}],
            "activity_log": [{"id": "a1"}],
            "notifications": [{"id": "n1"}],
            "two_factor_enabled": True,
        }
        result = _sanitize_profile_state(raw)
        assert result["active_workspace_id"] == "ws-123"
        assert len(result["team_members"]) == 1  # type: ignore[arg-type]
        assert result["two_factor_enabled"] is True

    def test_wrong_type_fields_use_defaults(self) -> None:
        raw = {
            "active_workspace_id": 42,
            "team_members": "not-a-list",
            "two_factor_enabled": "yes",
        }
        result = _sanitize_profile_state(raw)
        assert result["active_workspace_id"] == ""
        assert result["team_members"] == []
        assert result["two_factor_enabled"] is False


class TestAppendActivity:
    def test_inserts_at_front(self) -> None:
        state: dict = {"activity_log": []}
        _append_activity(state, "first event")
        _append_activity(state, "second event")
        log = state["activity_log"]
        assert log[0]["message"] == "second event"
        assert log[1]["message"] == "first event"

    def test_entry_has_required_keys(self) -> None:
        state: dict = {}
        _append_activity(state, "test message")
        entry = state["activity_log"][0]
        assert "id" in entry
        assert entry["message"] == "test message"
        assert "timestamp" in entry

    def test_non_list_activity_log_is_replaced(self) -> None:
        state: dict = {"activity_log": "broken"}
        _append_activity(state, "new entry")
        assert isinstance(state["activity_log"], list)
        assert len(state["activity_log"]) == 1


class TestAppendNotification:
    def test_inserts_notification_with_read_false(self) -> None:
        state: dict = {}
        _append_notification(state, "you have mail")
        notif = state["notifications"][0]
        assert notif["message"] == "you have mail"
        assert notif["read"] is False
        assert "created_at" in notif

    def test_non_list_notifications_replaced(self) -> None:
        state: dict = {"notifications": 999}
        _append_notification(state, "ping")
        assert isinstance(state["notifications"], list)
        assert len(state["notifications"]) == 1
        assert state["notifications"][0]["message"] == "ping"


# ---------------------------------------------------------------------------
# get_current_web_user: auth_enabled=True, missing cookie → None
# ---------------------------------------------------------------------------


class TestGetCurrentWebUser:
    def test_missing_cookie_returns_none(self, auth_settings: ApiSettings) -> None:
        from unittest.mock import MagicMock

        from file_organizer.web.profile_routes import get_current_web_user

        req = MagicMock()
        req.cookies = {}
        result = get_current_web_user(req, auth_settings)
        assert result is None

    def test_invalid_token_returns_none(self, auth_settings: ApiSettings) -> None:
        from unittest.mock import MagicMock

        from file_organizer.web.profile_routes import get_current_web_user

        req = MagicMock()
        req.cookies = {"fo_session": "totally.invalid.token"}
        result = get_current_web_user(req, auth_settings)
        assert result is None


# ---------------------------------------------------------------------------
# reset_password_submit: success path (user exists, valid password)
# ---------------------------------------------------------------------------


class TestResetPasswordSuccess:
    def setup_method(self) -> None:
        _PASSWORD_RESET_TOKENS.clear()

    def test_success_clears_token_and_returns_200(self, auth_client: TestClient) -> None:
        with patch("file_organizer.web.profile_routes.templates") as tpl:
            tpl.TemplateResponse.side_effect = lambda *args, **kwargs: _html_response()
            auth_client.post(
                "/api/v1/auth/register",
                json={
                    "username": "rp_success",
                    "email": "rp_success@example.com",
                    "password": "T3stP@ssword1!",
                    "full_name": "Reset User",
                },
            )
            auth_client.post(
                "/ui/profile/forgot-password",
                data={"email": "rp_success@example.com"},
            )
        assert len(_PASSWORD_RESET_TOKENS) == 1
        token = next(iter(_PASSWORD_RESET_TOKENS))

        with patch("file_organizer.web.profile_routes.templates") as tpl:
            tpl.TemplateResponse.side_effect = lambda *args, **kwargs: _html_response()
            r = auth_client.post(
                "/ui/profile/reset-password",
                data={
                    "token": token,
                    "new_password": "NewP@ssword1!",
                    "confirm_password": "NewP@ssword1!",
                },
            )
        assert r.status_code == 200
        assert token not in _PASSWORD_RESET_TOKENS
        call_args = str(tpl.TemplateResponse.call_args)
        assert "reset_password" in call_args


# ---------------------------------------------------------------------------
# Unauthenticated access to protected partials
# ---------------------------------------------------------------------------


class TestProtectedRoutesWithoutAuth:
    """All auth-required routes must return a non-5xx response (unauthenticated branch)."""

    def _get(self, auth_client: TestClient, path: str) -> int:
        with patch("file_organizer.web.profile_routes.templates") as tpl:
            tpl.TemplateResponse.side_effect = lambda *args, **kwargs: _html_response()
            r = auth_client.get(path)
        return r.status_code

    def test_profile_edit_partial_no_cookie(self, auth_client: TestClient) -> None:
        r = auth_client.get("/ui/profile/edit")
        assert r.status_code == 200
        assert b"Not authenticated" in r.content

    def test_workspaces_partial_no_cookie(self, auth_client: TestClient) -> None:
        r = auth_client.get("/ui/profile/workspaces")
        assert r.status_code == 200
        assert b"Not authenticated" in r.content

    def test_team_partial_no_cookie(self, auth_client: TestClient) -> None:
        r = auth_client.get("/ui/profile/team")
        assert r.status_code == 200
        assert b"Not authenticated" in r.content

    def test_shared_partial_no_cookie(self, auth_client: TestClient) -> None:
        r = auth_client.get("/ui/profile/shared")
        assert r.status_code == 200
        assert b"Not authenticated" in r.content

    def test_activity_partial_no_cookie(self, auth_client: TestClient) -> None:
        r = auth_client.get("/ui/profile/activity")
        assert r.status_code == 200
        assert b"Not authenticated" in r.content

    def test_notifications_partial_no_cookie(self, auth_client: TestClient) -> None:
        r = auth_client.get("/ui/profile/notifications")
        assert r.status_code == 200
        assert b"Not authenticated" in r.content

    def test_account_settings_partial_no_cookie(self, auth_client: TestClient) -> None:
        r = auth_client.get("/ui/profile/account-settings")
        assert r.status_code == 200
        assert b"Not authenticated" in r.content


# ---------------------------------------------------------------------------
# Authenticated routes: profile edit
# ---------------------------------------------------------------------------


class TestProfileEditAuthenticated:
    def test_profile_edit_get_returns_200(self, logged_in_client: TestClient) -> None:
        with patch("file_organizer.web.profile_routes.templates") as tpl:
            tpl.TemplateResponse.side_effect = lambda *args, **kwargs: _html_response()
            r = logged_in_client.get("/ui/profile/edit")
        _assert_authenticated_template_response(r, tpl)

    def test_profile_edit_post_success(self, logged_in_client: TestClient) -> None:
        with patch("file_organizer.web.profile_routes.templates") as tpl:
            tpl.TemplateResponse.side_effect = lambda *args, **kwargs: _html_response()
            r = logged_in_client.post(
                "/ui/profile/edit",
                data={"full_name": "Updated Name", "email": "authuser@example.com"},
            )
        _assert_authenticated_template_response(r, tpl)
        call_args = str(tpl.TemplateResponse.call_args)
        assert "_edit" in call_args

    def test_profile_edit_post_email_already_in_use(
        self, auth_client: TestClient, auth_settings: ApiSettings
    ) -> None:
        cookie1 = _register_and_login(auth_client, "edituser1", "T3stP@ssword1!")
        _register_and_login(auth_client, "edituser2", "T3stP@ssword1!")
        auth_client.cookies.set("fo_session", cookie1)
        with patch("file_organizer.web.profile_routes.templates") as tpl:
            tpl.TemplateResponse.side_effect = lambda *args, **kwargs: _html_response()
            r = auth_client.post(
                "/ui/profile/edit",
                data={"full_name": "X", "email": "edituser2@example.com"},
            )
        _assert_authenticated_template_response(r, tpl)
        call_args = str(tpl.TemplateResponse.call_args_list)
        assert "_edit" in call_args


# ---------------------------------------------------------------------------
# Authenticated routes: workspaces
# ---------------------------------------------------------------------------


class TestWorkspacesAuthenticated:
    def test_workspaces_get_returns_200(self, logged_in_client: TestClient) -> None:
        with patch("file_organizer.web.profile_routes.templates") as tpl:
            tpl.TemplateResponse.side_effect = lambda *args, **kwargs: _html_response()
            r = logged_in_client.get("/ui/profile/workspaces")
        _assert_authenticated_template_response(r, tpl)

    def test_workspace_create_returns_200(
        self, logged_in_client: TestClient, tmp_path: Path
    ) -> None:
        with patch("file_organizer.web.profile_routes.templates") as tpl:
            tpl.TemplateResponse.side_effect = lambda *args, **kwargs: _html_response()
            r = logged_in_client.post(
                "/ui/profile/workspaces/create",
                data={"name": "My WS", "root_path": str(tmp_path), "description": ""},
            )
        _assert_authenticated_template_response(r, tpl)

    def test_workspace_switch_unknown_id_still_returns_200(
        self, logged_in_client: TestClient
    ) -> None:
        with patch("file_organizer.web.profile_routes.templates") as tpl:
            tpl.TemplateResponse.side_effect = lambda *args, **kwargs: _html_response()
            r = logged_in_client.post(
                "/ui/profile/workspaces/switch",
                data={"workspace_id": "nonexistent-id"},
            )
        _assert_authenticated_template_response(r, tpl)


# ---------------------------------------------------------------------------
# Authenticated routes: team
# ---------------------------------------------------------------------------


class TestTeamAuthenticated:
    def test_team_partial_get_returns_200(self, logged_in_client: TestClient) -> None:
        with patch("file_organizer.web.profile_routes.templates") as tpl:
            tpl.TemplateResponse.side_effect = lambda *args, **kwargs: _html_response()
            r = logged_in_client.get("/ui/profile/team")
        _assert_authenticated_template_response(r, tpl)

    def test_team_invite_valid_role(self, logged_in_client: TestClient) -> None:
        with patch("file_organizer.web.profile_routes.templates") as tpl:
            tpl.TemplateResponse.side_effect = lambda *args, **kwargs: _html_response()
            r = logged_in_client.post(
                "/ui/profile/team/invite",
                data={"email": "colleague@example.com", "role": "editor"},
            )
        _assert_authenticated_template_response(r, tpl)

    def test_team_invite_invalid_role_falls_back_to_viewer(
        self, logged_in_client: TestClient
    ) -> None:
        with patch("file_organizer.web.profile_routes.templates") as tpl:
            tpl.TemplateResponse.side_effect = lambda *args, **kwargs: _html_response()
            r = logged_in_client.post(
                "/ui/profile/team/invite",
                data={"email": "new@example.com", "role": "superadmin"},
            )
        _assert_authenticated_template_response(r, tpl)
        ctx = tpl.TemplateResponse.call_args[0][2]
        member = next(
            (m for m in ctx.get("team_members", []) if m.get("email") == "new@example.com"),
            None,
        )
        assert member is not None
        assert member["role"] == "viewer"

    def test_team_update_role(self, logged_in_client: TestClient) -> None:
        with patch("file_organizer.web.profile_routes.templates") as tpl:
            tpl.TemplateResponse.side_effect = lambda *args, **kwargs: _html_response()
            r = logged_in_client.post(
                "/ui/profile/team/role",
                data={"member_id": "nonexistent-member", "role": "admin"},
            )
        _assert_authenticated_template_response(r, tpl)


# ---------------------------------------------------------------------------
# Authenticated routes: shared folders
# ---------------------------------------------------------------------------


class TestSharedFoldersAuthenticated:
    def test_shared_partial_get_returns_200(self, logged_in_client: TestClient) -> None:
        with patch("file_organizer.web.profile_routes.templates") as tpl:
            tpl.TemplateResponse.side_effect = lambda *args, **kwargs: _html_response()
            r = logged_in_client.get("/ui/profile/shared")
        _assert_authenticated_template_response(r, tpl)

    def test_shared_add_valid_permission(
        self, logged_in_client: TestClient, tmp_path: Path
    ) -> None:
        with patch("file_organizer.web.profile_routes.templates") as tpl:
            tpl.TemplateResponse.side_effect = lambda *args, **kwargs: _html_response()
            r = logged_in_client.post(
                "/ui/profile/shared/add",
                data={"folder_path": str(tmp_path), "permission": "edit"},
            )
        _assert_authenticated_template_response(r, tpl)

    def test_shared_add_invalid_permission_falls_back_to_view(
        self, logged_in_client: TestClient, tmp_path: Path
    ) -> None:
        with patch("file_organizer.web.profile_routes.templates") as tpl:
            tpl.TemplateResponse.side_effect = lambda *args, **kwargs: _html_response()
            r = logged_in_client.post(
                "/ui/profile/shared/add",
                data={"folder_path": str(tmp_path), "permission": "superpower"},
            )
        _assert_authenticated_template_response(r, tpl)
        ctx = tpl.TemplateResponse.call_args[0][2]
        shared = ctx.get("shared_folders", [])
        added = next((f for f in shared if str(tmp_path) in f.get("path", "")), None)
        assert added is not None
        assert added["permission"] == "view"

    def test_shared_remove_returns_200(self, logged_in_client: TestClient) -> None:
        with patch("file_organizer.web.profile_routes.templates") as tpl:
            tpl.TemplateResponse.side_effect = lambda *args, **kwargs: _html_response()
            r = logged_in_client.post(
                "/ui/profile/shared/remove",
                data={"folder_id": "nonexistent-folder-id"},
            )
        _assert_authenticated_template_response(r, tpl)


# ---------------------------------------------------------------------------
# Authenticated routes: activity, notifications
# ---------------------------------------------------------------------------


class TestActivityAndNotifications:
    def test_activity_partial_returns_200(self, logged_in_client: TestClient) -> None:
        with patch("file_organizer.web.profile_routes.templates") as tpl:
            tpl.TemplateResponse.side_effect = lambda *args, **kwargs: _html_response()
            r = logged_in_client.get("/ui/profile/activity")
        _assert_authenticated_template_response(r, tpl)

    def test_notifications_partial_returns_200(self, logged_in_client: TestClient) -> None:
        with patch("file_organizer.web.profile_routes.templates") as tpl:
            tpl.TemplateResponse.side_effect = lambda *args, **kwargs: _html_response()
            r = logged_in_client.get("/ui/profile/notifications")
        _assert_authenticated_template_response(r, tpl)

    def test_notification_mark_read_returns_200(self, logged_in_client: TestClient) -> None:
        with patch("file_organizer.web.profile_routes.templates") as tpl:
            tpl.TemplateResponse.side_effect = lambda *args, **kwargs: _html_response()
            r = logged_in_client.post(
                "/ui/profile/notifications/mark-read",
                data={"notification_id": "nonexistent-id"},
            )
        _assert_authenticated_template_response(r, tpl)


# ---------------------------------------------------------------------------
# Authenticated routes: account settings (password + 2FA)
# ---------------------------------------------------------------------------


class TestAccountSettingsAuthenticated:
    def test_account_settings_get_returns_200(self, logged_in_client: TestClient) -> None:
        with patch("file_organizer.web.profile_routes.templates") as tpl:
            tpl.TemplateResponse.side_effect = lambda *args, **kwargs: _html_response()
            r = logged_in_client.get("/ui/profile/account-settings")
        _assert_authenticated_template_response(r, tpl)

    def test_change_password_wrong_current_returns_200(self, logged_in_client: TestClient) -> None:
        with patch("file_organizer.web.profile_routes.templates") as tpl:
            tpl.TemplateResponse.side_effect = lambda *args, **kwargs: _html_response()
            r = logged_in_client.post(
                "/ui/profile/account-settings/password",
                data={
                    "current_password": "WrongPassword!",
                    "new_password": "NewP@ssword1!",
                    "confirm_password": "NewP@ssword1!",
                },
            )
        _assert_authenticated_template_response(r, tpl)
        call_args = str(tpl.TemplateResponse.call_args)
        assert "_account_settings" in call_args

    def test_change_password_mismatch_returns_200(self, logged_in_client: TestClient) -> None:
        with patch("file_organizer.web.profile_routes.templates") as tpl:
            tpl.TemplateResponse.side_effect = lambda *args, **kwargs: _html_response()
            r = logged_in_client.post(
                "/ui/profile/account-settings/password",
                data={
                    "current_password": "T3stP@ssword1!",
                    "new_password": "NewP@ssword1!",
                    "confirm_password": "DifferentP@ssword1!",
                },
            )
        _assert_authenticated_template_response(r, tpl)

    def test_change_password_weak_new_returns_200(self, logged_in_client: TestClient) -> None:
        with patch("file_organizer.web.profile_routes.templates") as tpl:
            tpl.TemplateResponse.side_effect = lambda *args, **kwargs: _html_response()
            r = logged_in_client.post(
                "/ui/profile/account-settings/password",
                data={
                    "current_password": "T3stP@ssword1!",
                    "new_password": "abc",
                    "confirm_password": "abc",
                },
            )
        _assert_authenticated_template_response(r, tpl)

    def test_change_password_success_returns_200(self, logged_in_client: TestClient) -> None:
        with patch("file_organizer.web.profile_routes.templates") as tpl:
            tpl.TemplateResponse.side_effect = lambda *args, **kwargs: _html_response()
            r = logged_in_client.post(
                "/ui/profile/account-settings/password",
                data={
                    "current_password": "T3stP@ssword1!",
                    "new_password": "NewP@ssword1!",
                    "confirm_password": "NewP@ssword1!",
                },
            )
        _assert_authenticated_template_response(r, tpl)
        call_args = str(tpl.TemplateResponse.call_args)
        assert "_account_settings" in call_args

    def test_toggle_2fa_on_returns_200(self, logged_in_client: TestClient) -> None:
        with patch("file_organizer.web.profile_routes.templates") as tpl:
            tpl.TemplateResponse.side_effect = lambda *args, **kwargs: _html_response()
            r = logged_in_client.post("/ui/profile/account-settings/2fa", data={"enabled": "1"})
        _assert_authenticated_template_response(r, tpl)

    def test_toggle_2fa_off_returns_200(self, logged_in_client: TestClient) -> None:
        with patch("file_organizer.web.profile_routes.templates") as tpl:
            tpl.TemplateResponse.side_effect = lambda *args, **kwargs: _html_response()
            r = logged_in_client.post("/ui/profile/account-settings/2fa", data={})
        _assert_authenticated_template_response(r, tpl)
