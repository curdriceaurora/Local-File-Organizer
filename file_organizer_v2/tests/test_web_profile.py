"""Tests for the web profile UI routes."""

from __future__ import annotations

import html
from pathlib import Path

from fastapi.testclient import TestClient

from file_organizer.api.auth import hash_password
from file_organizer.api.auth_db import create_session
from file_organizer.api.auth_models import User
from file_organizer.api.config import ApiSettings
from file_organizer.api.main import create_app
from file_organizer.api.test_utils import build_test_settings


def _build_settings(tmp_path: Path, auth_enabled: bool = True) -> ApiSettings:
    return build_test_settings(
        tmp_path,
        allowed_paths=[],
        auth_overrides={"auth_enabled": auth_enabled},
    )


def _build_client(tmp_path: Path, auth_enabled: bool = True) -> TestClient:
    settings = _build_settings(tmp_path, auth_enabled=auth_enabled)
    app = create_app(settings)
    return TestClient(app)


def _seed_user(
    settings: ApiSettings, username: str = "alice", email: str = "alice@example.com"
) -> User:
    """Create a user directly in the auth database and return it."""
    db = create_session(settings.auth_db_path)
    try:
        user = User(
            username=username,
            email=email,
            hashed_password=hash_password("password1"),
            full_name="Alice Test",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    finally:
        db.close()


def _login(client: TestClient, username: str = "alice", password: str = "password1") -> TestClient:
    """Log in via the web form and persist the session cookie on the client."""
    response = client.post(
        "/ui/profile/login",
        data={"username": username, "password": password},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/ui/profile"
    # The session cookie is automatically stored on the TestClient
    return client


# ---------------------------------------------------------------------------
# Profile page rendering
# ---------------------------------------------------------------------------


class TestProfilePage:
    """Tests for the main /ui/profile page."""

    def test_unauthenticated_shows_sign_in(self, tmp_path: Path) -> None:
        client = _build_client(tmp_path, auth_enabled=True)
        response = client.get("/ui/profile")
        assert response.status_code == 200
        assert "Sign in" in response.text
        assert "Log out" not in response.text

    def test_auth_disabled_shows_disabled_message(self, tmp_path: Path) -> None:
        client = _build_client(tmp_path, auth_enabled=False)
        response = client.get("/ui/profile")
        assert response.status_code == 200
        assert "Authentication is disabled" in response.text

    def test_authenticated_shows_profile(self, tmp_path: Path) -> None:
        settings = _build_settings(tmp_path)
        _seed_user(settings)
        app = create_app(settings)
        client = TestClient(app)
        _login(client)

        response = client.get("/ui/profile")
        assert response.status_code == 200
        assert "Alice Test" in response.text
        assert "Log out" in response.text
        assert "Sign in" not in response.text


# ---------------------------------------------------------------------------
# Login / Register forms
# ---------------------------------------------------------------------------


class TestLoginForm:
    """Tests for login form rendering and submission."""

    def test_login_form_renders(self, tmp_path: Path) -> None:
        client = _build_client(tmp_path)
        response = client.get("/ui/profile/login")
        assert response.status_code == 200
        assert "Login" in response.text
        assert 'name="username"' in response.text

    def test_login_wrong_password(self, tmp_path: Path) -> None:
        settings = _build_settings(tmp_path)
        _seed_user(settings)
        app = create_app(settings)
        client = TestClient(app)

        response = client.post(
            "/ui/profile/login",
            data={"username": "alice", "password": "wrong"},
            follow_redirects=False,
        )
        # Should re-render the login form with error, not redirect
        assert response.status_code == 200
        assert "Incorrect username or password" in response.text

    def test_login_success_sets_cookie(self, tmp_path: Path) -> None:
        settings = _build_settings(tmp_path)
        _seed_user(settings)
        app = create_app(settings)
        client = TestClient(app)

        response = client.post(
            "/ui/profile/login",
            data={"username": "alice", "password": "password1"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert "fo_session" in response.cookies


class TestRegisterForm:
    """Tests for registration form rendering and submission."""

    def test_register_form_renders(self, tmp_path: Path) -> None:
        client = _build_client(tmp_path)
        response = client.get("/ui/profile/register")
        assert response.status_code == 200
        assert "Register" in response.text
        assert 'name="email"' in response.text

    def test_register_success_redirects_to_login(self, tmp_path: Path) -> None:
        client = _build_client(tmp_path)
        response = client.post(
            "/ui/profile/register",
            data={
                "username": "bob",
                "email": "bob@example.com",
                "password": "password1",
                "full_name": "Bob User",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/ui/profile/login"

    def test_register_duplicate_username(self, tmp_path: Path) -> None:
        settings = _build_settings(tmp_path)
        _seed_user(settings)
        app = create_app(settings)
        client = TestClient(app)

        response = client.post(
            "/ui/profile/register",
            data={
                "username": "alice",
                "email": "alice2@example.com",
                "password": "password1",
            },
            follow_redirects=False,
        )
        assert response.status_code == 200
        assert "Username already taken" in response.text

    def test_register_weak_password(self, tmp_path: Path) -> None:
        client = _build_client(tmp_path)
        response = client.post(
            "/ui/profile/register",
            data={
                "username": "charlie",
                "email": "charlie@example.com",
                "password": "short",
            },
            follow_redirects=False,
        )
        assert response.status_code == 200
        assert "Password must be at least" in response.text


# ---------------------------------------------------------------------------
# Full register -> login -> profile flow
# ---------------------------------------------------------------------------


class TestFullAuthFlow:
    """Test the complete registration, login, profile view cycle."""

    def test_register_login_view_profile(self, tmp_path: Path) -> None:
        client = _build_client(tmp_path)

        # Register
        reg = client.post(
            "/ui/profile/register",
            data={
                "username": "testuser",
                "email": "testuser@example.com",
                "password": "password1",
                "full_name": "Test User",
            },
            follow_redirects=False,
        )
        assert reg.status_code == 303

        # Login
        login = client.post(
            "/ui/profile/login",
            data={"username": "testuser", "password": "password1"},
            follow_redirects=False,
        )
        assert login.status_code == 303

        # View profile
        profile = client.get("/ui/profile")
        assert profile.status_code == 200
        assert "Test User" in profile.text


# ---------------------------------------------------------------------------
# Profile edit
# ---------------------------------------------------------------------------


class TestProfileEdit:
    """Tests for profile editing."""

    def test_edit_partial_unauthenticated(self, tmp_path: Path) -> None:
        client = _build_client(tmp_path)
        response = client.get("/ui/profile/edit")
        assert response.status_code == 200
        assert "Not authenticated" in response.text

    def test_edit_partial_renders(self, tmp_path: Path) -> None:
        settings = _build_settings(tmp_path)
        _seed_user(settings)
        app = create_app(settings)
        client = TestClient(app)
        _login(client)

        response = client.get("/ui/profile/edit")
        assert response.status_code == 200
        assert "alice" in response.text
        assert "alice@example.com" in response.text

    def test_edit_submit_updates_profile(self, tmp_path: Path) -> None:
        settings = _build_settings(tmp_path)
        _seed_user(settings)
        app = create_app(settings)
        client = TestClient(app)
        _login(client)

        response = client.post(
            "/ui/profile/edit",
            data={"full_name": "Alice Updated", "email": "alice_new@example.com"},
        )
        assert response.status_code == 200
        assert "Profile updated" in response.text
        assert "Alice Updated" in response.text


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------


class TestLogout:
    """Tests for logout."""

    def test_logout_clears_session(self, tmp_path: Path) -> None:
        settings = _build_settings(tmp_path)
        _seed_user(settings)
        app = create_app(settings)
        client = TestClient(app)
        _login(client)

        # Confirm authenticated
        profile = client.get("/ui/profile")
        assert "Alice Test" in profile.text

        # Logout
        logout = client.post("/ui/profile/logout", follow_redirects=False)
        assert logout.status_code == 303
        assert logout.headers["location"] == "/ui/profile"

        # After following redirect, the cookie should be cleared so we see sign in
        profile_after = client.get("/ui/profile")
        assert "Sign in" in profile_after.text


# ---------------------------------------------------------------------------
# API key management
# ---------------------------------------------------------------------------


class TestApiKeys:
    """Tests for API key generation and revocation."""

    def test_api_keys_unauthenticated(self, tmp_path: Path) -> None:
        client = _build_client(tmp_path)
        response = client.get("/ui/profile/api-keys")
        assert response.status_code == 200
        assert "Not authenticated" in response.text

    def test_api_keys_empty_list(self, tmp_path: Path) -> None:
        settings = _build_settings(tmp_path)
        _seed_user(settings)
        app = create_app(settings)
        client = TestClient(app)
        _login(client)

        response = client.get("/ui/profile/api-keys")
        assert response.status_code == 200
        assert "No active API keys" in response.text

    def test_generate_api_key(self, tmp_path: Path) -> None:
        settings = _build_settings(tmp_path)
        _seed_user(settings)
        app = create_app(settings)
        client = TestClient(app)
        _login(client)

        response = client.post(
            "/ui/profile/api-keys/generate",
            data={"label": "my-key"},
        )
        assert response.status_code == 200
        assert "New API key created" in response.text
        assert "fo_" in response.text
        assert "my-key" in response.text

    def test_revoke_api_key(self, tmp_path: Path) -> None:
        settings = _build_settings(tmp_path)
        _seed_user(settings)
        app = create_app(settings)
        client = TestClient(app)
        _login(client)

        # Generate a key first
        gen = client.post(
            "/ui/profile/api-keys/generate",
            data={"label": "to-revoke"},
        )
        assert gen.status_code == 200
        assert "to-revoke" in gen.text

        # Find the key_id from the response (it's in a hidden input)
        import re

        match = re.search(r'name="key_id" value="([^"]+)"', gen.text)
        assert match is not None
        key_id = match.group(1)

        # Revoke it
        revoke = client.post(
            "/ui/profile/api-keys/revoke",
            data={"key_id": key_id},
        )
        assert revoke.status_code == 200
        assert "No active API keys" in revoke.text


class TestPasswordResetFlow:
    """Tests for forgot/reset password routes."""

    def test_forgot_password_form_renders(self, tmp_path: Path) -> None:
        client = _build_client(tmp_path)
        response = client.get("/ui/profile/forgot-password")
        assert response.status_code == 200
        assert "Forgot Password" in response.text

    def test_forgot_and_reset_password_success(self, tmp_path: Path) -> None:
        settings = _build_settings(tmp_path)
        _seed_user(settings)
        app = create_app(settings)
        client = TestClient(app)

        forgot = client.post("/ui/profile/forgot-password", data={"email": "alice@example.com"})
        assert forgot.status_code == 200
        assert "Local dev token" in forgot.text

        import re

        token_match = re.search(r"<code>([^<]+)</code>", forgot.text)
        assert token_match is not None
        token = token_match.group(1)

        reset = client.post(
            "/ui/profile/reset-password",
            data={
                "token": token,
                "new_password": "newpassword1",
                "confirm_password": "newpassword1",
            },
        )
        assert reset.status_code == 200
        assert "Password reset complete" in reset.text

        login = client.post(
            "/ui/profile/login",
            data={"username": "alice", "password": "newpassword1"},
            follow_redirects=False,
        )
        assert login.status_code == 303


class TestWorkspaceAndTeamUi:
    """Tests for workspace/team/sharing partials."""

    def test_workspace_create_and_switch(self, tmp_path: Path) -> None:
        settings = _build_settings(tmp_path)
        _seed_user(settings)
        app = create_app(settings)
        client = TestClient(app)
        _login(client)

        create_one = client.post(
            "/ui/profile/workspaces/create",
            data={"name": "Alpha", "root_path": "/tmp/alpha", "description": "A"},
        )
        assert create_one.status_code == 200
        assert "Alpha" in create_one.text

        create_two = client.post(
            "/ui/profile/workspaces/create",
            data={"name": "Beta", "root_path": "/tmp/beta", "description": "B"},
        )
        assert create_two.status_code == 200
        assert "Beta" in create_two.text

        import re

        ids = re.findall(r'name="workspace_id" value="([^"]+)"', create_two.text)
        assert ids
        switch = client.post("/ui/profile/workspaces/switch", data={"workspace_id": ids[-1]})
        assert switch.status_code == 200
        assert "Active" in switch.text

    def test_team_invite_and_role_update(self, tmp_path: Path) -> None:
        settings = _build_settings(tmp_path)
        _seed_user(settings)
        app = create_app(settings)
        client = TestClient(app)
        _login(client)

        invite = client.post(
            "/ui/profile/team/invite",
            data={"email": "teammate@example.com", "role": "viewer"},
        )
        assert invite.status_code == 200
        assert "teammate@example.com" in invite.text

        import re

        member_match = re.search(r'name="member_id" value="([^"]+)"', invite.text)
        assert member_match is not None
        member_id = member_match.group(1)

        update = client.post(
            "/ui/profile/team/role",
            data={"member_id": member_id, "role": "admin"},
        )
        assert update.status_code == 200
        assert "admin" in update.text

    def test_shared_folder_add_and_remove(self, tmp_path: Path) -> None:
        settings = _build_settings(tmp_path)
        _seed_user(settings)
        app = create_app(settings)
        client = TestClient(app)
        _login(client)

        add = client.post(
            "/ui/profile/shared/add",
            data={"folder_path": "/tmp/shared", "permission": "edit"},
        )
        assert add.status_code == 200
        assert "/tmp/shared" in add.text

        import re

        folder_match = re.search(r'name="folder_id" value="([^"]+)"', add.text)
        assert folder_match is not None
        folder_id = folder_match.group(1)

        remove = client.post("/ui/profile/shared/remove", data={"folder_id": folder_id})
        assert remove.status_code == 200
        assert "/tmp/shared" not in remove.text


class TestAccountSettingsAndFeeds:
    """Tests for account settings, activity log, and notifications."""

    def test_change_password_and_toggle_2fa(self, tmp_path: Path) -> None:
        settings = _build_settings(tmp_path)
        _seed_user(settings)
        app = create_app(settings)
        client = TestClient(app)
        _login(client)

        change = client.post(
            "/ui/profile/account-settings/password",
            data={
                "current_password": "password1",
                "new_password": "password2",
                "confirm_password": "password2",
            },
        )
        assert change.status_code == 200
        assert "Password updated" in change.text

        toggle = client.post("/ui/profile/account-settings/2fa", data={"enabled": "1"})
        assert toggle.status_code == 200
        assert "Two-factor preference updated" in toggle.text

        relogin = client.post(
            "/ui/profile/login",
            data={"username": "alice", "password": "password2"},
            follow_redirects=False,
        )
        assert relogin.status_code == 303

    def test_activity_and_notifications_render(self, tmp_path: Path) -> None:
        settings = _build_settings(tmp_path)
        _seed_user(settings)
        app = create_app(settings)
        client = TestClient(app)
        _login(client)

        client.post(
            "/ui/profile/workspaces/create",
            data={"name": "Work", "root_path": "/tmp/work", "description": ""},
        )

        activity = client.get("/ui/profile/activity")
        assert activity.status_code == 200
        assert "Created workspace" in activity.text

        notifications = client.get("/ui/profile/notifications")
        assert notifications.status_code == 200
        assert "Workspace 'Work' was created" in html.unescape(notifications.text)
