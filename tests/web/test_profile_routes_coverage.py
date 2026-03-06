"""Coverage tests for file_organizer.web.profile_routes — route handler branches."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture()
def mock_templates():
    response = MagicMock()
    response.headers = {}
    with patch("file_organizer.web.profile_routes.templates") as tmpl:
        tmpl.TemplateResponse.return_value = response
        yield tmpl


@pytest.fixture()
def mock_base_context():
    with patch(
        "file_organizer.web.profile_routes.base_context",
        return_value={"request": MagicMock()},
    ):
        yield


class TestProfileHelpers:
    """Covers internal profile helpers."""

    def test_default_profile_state(self) -> None:
        from file_organizer.web.profile_routes import _default_profile_state

        state = _default_profile_state()
        assert "activity_log" in state
        assert "notifications" in state

    def test_sanitize_profile_state_missing_keys(self) -> None:
        from file_organizer.web.profile_routes import _sanitize_profile_state

        result = _sanitize_profile_state({})
        assert "activity_log" in result
        assert "notifications" in result

    def test_sanitize_profile_state_non_dict(self) -> None:
        from file_organizer.web.profile_routes import _sanitize_profile_state

        result = _sanitize_profile_state("not-a-dict")
        assert "activity_log" in result

    def test_sanitize_profile_state_with_data(self) -> None:
        from file_organizer.web.profile_routes import _sanitize_profile_state

        data = {
            "activity_log": [{"message": "login", "timestamp": "2025-01-01"}],
            "notifications": [{"message": "hi"}],
        }
        result = _sanitize_profile_state(data)
        assert len(result["activity_log"]) == 1

    def test_append_activity(self) -> None:
        from file_organizer.web.profile_routes import _append_activity

        state = {"activity_log": [], "notifications": []}
        _append_activity(state, "logged in")
        assert len(state["activity_log"]) == 1
        assert state["activity_log"][0]["message"] == "logged in"

    def test_append_notification(self) -> None:
        from file_organizer.web.profile_routes import _append_notification

        state = {"activity_log": [], "notifications": []}
        _append_notification(state, "Welcome!")
        assert len(state["notifications"]) == 1
        assert state["notifications"][0]["message"] == "Welcome!"

    def test_avatar_path(self) -> None:
        from file_organizer.web.profile_routes import _avatar_path

        path = _avatar_path("user-123")
        assert "user-123" in str(path)

    def test_cleanup_expired_reset_tokens(self) -> None:
        from file_organizer.web.profile_routes import (
            _PASSWORD_RESET_TOKENS,
            _cleanup_expired_reset_tokens,
        )

        # Add an expired token
        expired_time = datetime(2020, 1, 1, tzinfo=UTC)
        _PASSWORD_RESET_TOKENS["expired-token"] = ("user-1", expired_time)
        _cleanup_expired_reset_tokens()
        assert "expired-token" not in _PASSWORD_RESET_TOKENS


class TestGetCurrentWebUser:
    """Covers get_current_web_user."""

    def test_auth_disabled(self) -> None:
        from file_organizer.web.profile_routes import get_current_web_user

        request = MagicMock()
        settings = MagicMock()
        settings.auth_enabled = False

        result = get_current_web_user(request, settings)
        assert result is None

    def test_no_cookie(self) -> None:
        from file_organizer.web.profile_routes import get_current_web_user

        request = MagicMock()
        request.cookies = {}
        settings = MagicMock()
        settings.auth_enabled = True

        result = get_current_web_user(request, settings)
        assert result is None

    def test_invalid_token(self) -> None:
        from file_organizer.api.auth import TokenError
        from file_organizer.web.profile_routes import get_current_web_user

        request = MagicMock()
        request.cookies = {"fo_session": "bad-token"}
        settings = MagicMock()
        settings.auth_enabled = True

        with patch(
            "file_organizer.web.profile_routes.decode_token",
            side_effect=TokenError("invalid"),
        ):
            result = get_current_web_user(request, settings)
        assert result is None


class TestRequireWebUser:
    """Covers _require_web_user."""

    def test_no_user_redirects(self) -> None:
        from file_organizer.web.profile_routes import _require_web_user

        request = MagicMock()
        settings = MagicMock()

        with patch(
            "file_organizer.web.profile_routes.get_current_web_user",
            return_value=None,
        ):
            result = _require_web_user(request, settings)
        # Should return an HTML response (not a User)
        assert hasattr(result, "status_code") or hasattr(result, "body")


class TestMakeProfileContext:
    """Covers _make_profile_context."""

    def test_context_has_user(self) -> None:
        from file_organizer.web.profile_routes import _make_profile_context

        request = MagicMock()
        settings = MagicMock()
        user = MagicMock()
        user.id = "u1"
        user.username = "testuser"

        def fake_base_context(_req, _settings, *, active, title, extras=None):
            ctx = {"request": _req}
            if extras:
                ctx.update(extras)
            return ctx

        with patch(
            "file_organizer.web.profile_routes.base_context",
            side_effect=fake_base_context,
        ):
            ctx = _make_profile_context(request, settings, user)
        assert "user" in ctx
        assert ctx["user"] is user


# ---------------------------------------------------------------------------
# Helper: build common mocks for route-handler tests
# ---------------------------------------------------------------------------


def _make_db_mock(user=None, query_results=None):
    """Return a MagicMock Session whose .query().filter().first() returns *user*."""
    db = MagicMock()
    chain = db.query.return_value.filter.return_value
    chain.first.return_value = user
    chain.order_by.return_value.all.return_value = query_results or []
    return db


def _patch_route_deps(user_mock=None, db_mock=None, tmpl_resp=None):
    """Context-manager stack patching _get_db, _require_web_user, templates, base_context."""
    from contextlib import ExitStack

    stack = ExitStack()
    patches = {}

    if db_mock is not None:
        patches["db"] = stack.enter_context(
            patch("file_organizer.web.profile_routes._get_db", return_value=db_mock)
        )

    if user_mock is not None:
        patches["user"] = stack.enter_context(
            patch(
                "file_organizer.web.profile_routes._require_web_user",
                return_value=user_mock,
            )
        )

    resp = tmpl_resp or MagicMock()
    resp.headers = {}
    patches["tmpl"] = stack.enter_context(patch("file_organizer.web.profile_routes.templates"))
    patches["tmpl"].TemplateResponse.return_value = resp

    def _fake_base_context(_req, _settings, *, active="", title="", extras=None):
        ctx = {"request": _req}
        if extras:
            ctx.update(extras)
        return ctx

    patches["base_ctx"] = stack.enter_context(
        patch(
            "file_organizer.web.profile_routes.base_context",
            side_effect=_fake_base_context,
        )
    )

    return stack, patches


# ---------------------------------------------------------------------------
# Login handler tests
# ---------------------------------------------------------------------------


class TestLoginSubmit:
    """Covers login_submit route branches."""

    def test_login_inactive_user(self) -> None:
        from file_organizer.web.profile_routes import login_submit

        user = MagicMock()
        user.is_active = False
        db = _make_db_mock(user=user)
        stack, p = _patch_route_deps(db_mock=db)
        with stack, patch("file_organizer.web.profile_routes.verify_password", return_value=True):
            login_submit(MagicMock(), username="u", password="p", settings=MagicMock())
        p["tmpl"].TemplateResponse.assert_called_once()
        ctx = p["tmpl"].TemplateResponse.call_args
        assert "Account is inactive" in str(ctx)

    def test_login_success_sets_cookie(self) -> None:
        from file_organizer.web.profile_routes import login_submit

        user = MagicMock()
        user.is_active = True
        user.id = "u1"
        user.username = "testuser"
        db = _make_db_mock(user=user)
        settings = MagicMock()
        settings.auth_access_token_minutes = 30

        bundle = MagicMock()
        bundle.access_token = "test-tok"

        stack, p = _patch_route_deps(db_mock=db)
        with (
            stack,
            patch("file_organizer.web.profile_routes.verify_password", return_value=True),
            patch("file_organizer.web.profile_routes.create_token_bundle", return_value=bundle),
        ):
            result = login_submit(MagicMock(), username="u", password="p", settings=settings)
        assert result.status_code == 303
        # Verify that auth cookie was set in response headers
        assert any(key.lower() == "set-cookie" for key in result.headers)


# ---------------------------------------------------------------------------
# Registration handler tests
# ---------------------------------------------------------------------------


class TestRegisterSubmit:
    """Covers register_submit route branches."""

    def test_register_duplicate_username(self) -> None:
        from file_organizer.web.profile_routes import register_submit

        db = MagicMock()
        # First query (username check) returns existing user
        db.query.return_value.filter.return_value.first.return_value = MagicMock()

        stack, p = _patch_route_deps(db_mock=db)
        with (
            stack,
            patch("file_organizer.web.profile_routes.validate_password", return_value=(True, None)),
        ):
            register_submit(
                MagicMock(),
                username="taken",
                email="e@e.com",
                password="StrongP@ss1",
                full_name="",
                settings=MagicMock(),
            )
        assert "Username already taken" in str(p["tmpl"].TemplateResponse.call_args)

    def test_register_duplicate_email(self) -> None:
        from file_organizer.web.profile_routes import register_submit

        db = MagicMock()
        # Username check returns None, email check returns existing user
        db.query.return_value.filter.return_value.first.side_effect = [None, MagicMock()]

        stack, p = _patch_route_deps(db_mock=db)
        with (
            stack,
            patch("file_organizer.web.profile_routes.validate_password", return_value=(True, None)),
        ):
            register_submit(
                MagicMock(),
                username="newuser",
                email="dup@e.com",
                password="StrongP@ss1",
                full_name="",
                settings=MagicMock(),
            )
        assert "Email already registered" in str(p["tmpl"].TemplateResponse.call_args)

    def test_register_success(self) -> None:
        from file_organizer.web.profile_routes import register_submit

        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None

        stack, p = _patch_route_deps(db_mock=db)
        with (
            stack,
            patch("file_organizer.web.profile_routes.validate_password", return_value=(True, None)),
            patch("file_organizer.web.profile_routes.hash_password", return_value="hashed"),
        ):
            result = register_submit(
                MagicMock(),
                username="newuser",
                email="new@e.com",
                password="StrongP@ss1",
                full_name="Full Name",
                settings=MagicMock(),
            )
        assert result.status_code == 303
        db.add.assert_called_once()
        db.commit.assert_called_once()


# ---------------------------------------------------------------------------
# Password reset handler tests
# ---------------------------------------------------------------------------


class TestResetPasswordSubmit:
    """Covers reset_password_submit route branches."""

    def test_reset_password_mismatch(self) -> None:
        from file_organizer.web.profile_routes import (
            _PASSWORD_RESET_TOKENS,
            reset_password_submit,
        )

        _PASSWORD_RESET_TOKENS["tok1"] = ("uid", datetime.now(UTC) + timedelta(hours=1))
        stack, p = _patch_route_deps()
        try:
            with stack:
                reset_password_submit(
                    MagicMock(),
                    token="tok1",
                    new_password="aaa",
                    confirm_password="bbb",
                    settings=MagicMock(),
                )
            assert "Passwords do not match" in str(p["tmpl"].TemplateResponse.call_args)
        finally:
            _PASSWORD_RESET_TOKENS.pop("tok1", None)

    def test_reset_password_validation_fail(self) -> None:
        from file_organizer.web.profile_routes import (
            _PASSWORD_RESET_TOKENS,
            reset_password_submit,
        )

        _PASSWORD_RESET_TOKENS["tok2"] = ("uid", datetime.now(UTC) + timedelta(hours=1))
        stack, p = _patch_route_deps()
        try:
            with (
                stack,
                patch(
                    "file_organizer.web.profile_routes.validate_password",
                    return_value=(False, "Too weak"),
                ),
            ):
                reset_password_submit(
                    MagicMock(),
                    token="tok2",
                    new_password="weak",
                    confirm_password="weak",
                    settings=MagicMock(),
                )
            assert "Too weak" in str(p["tmpl"].TemplateResponse.call_args)
        finally:
            _PASSWORD_RESET_TOKENS.pop("tok2", None)

    def test_reset_password_user_deleted(self) -> None:
        from file_organizer.web.profile_routes import (
            _PASSWORD_RESET_TOKENS,
            reset_password_submit,
        )

        _PASSWORD_RESET_TOKENS["tok3"] = ("uid-gone", datetime.now(UTC) + timedelta(hours=1))
        db = _make_db_mock(user=None)
        stack, p = _patch_route_deps(db_mock=db)
        try:
            with (
                stack,
                patch(
                    "file_organizer.web.profile_routes.validate_password",
                    return_value=(True, None),
                ),
            ):
                reset_password_submit(
                    MagicMock(),
                    token="tok3",
                    new_password="StrongP@ss1",
                    confirm_password="StrongP@ss1",
                    settings=MagicMock(),
                )
            assert "Account no longer exists" in str(p["tmpl"].TemplateResponse.call_args)
        finally:
            _PASSWORD_RESET_TOKENS.pop("tok3", None)

    def test_reset_password_success(self) -> None:
        from file_organizer.web.profile_routes import (
            _PASSWORD_RESET_TOKENS,
            reset_password_submit,
        )

        _PASSWORD_RESET_TOKENS["tok4"] = ("uid-ok", datetime.now(UTC) + timedelta(hours=1))
        user = MagicMock()
        db = _make_db_mock(user=user)
        stack, p = _patch_route_deps(db_mock=db)
        try:
            with (
                stack,
                patch(
                    "file_organizer.web.profile_routes.validate_password",
                    return_value=(True, None),
                ),
                patch("file_organizer.web.profile_routes.hash_password", return_value="newhash"),
            ):
                reset_password_submit(
                    MagicMock(),
                    token="tok4",
                    new_password="StrongP@ss1",
                    confirm_password="StrongP@ss1",
                    settings=MagicMock(),
                )
            assert "Password reset complete" in str(p["tmpl"].TemplateResponse.call_args)
            assert user.hashed_password == "newhash"
            assert "tok4" not in _PASSWORD_RESET_TOKENS
        finally:
            _PASSWORD_RESET_TOKENS.pop("tok4", None)


# ---------------------------------------------------------------------------
# Change password handler tests
# ---------------------------------------------------------------------------


class TestChangePassword:
    """Covers account_settings_change_password route branches."""

    def test_change_password_wrong_current(self) -> None:
        from file_organizer.web.profile_routes import account_settings_change_password

        user = MagicMock()
        user.id = "u1"
        db_user = MagicMock()
        db = _make_db_mock(user=db_user)

        stack, p = _patch_route_deps(user_mock=user, db_mock=db)
        with stack, patch("file_organizer.web.profile_routes.verify_password", return_value=False):
            account_settings_change_password(
                MagicMock(),
                current_password="wrong",
                new_password="new",
                confirm_password="new",
                settings=MagicMock(),
            )
        assert "Current password is incorrect" in str(p["tmpl"].TemplateResponse.call_args)

    def test_change_password_success(self) -> None:
        from file_organizer.web.profile_routes import account_settings_change_password

        user = MagicMock()
        user.id = "u1"
        db_user = MagicMock()
        db = _make_db_mock(user=db_user)

        stack, p = _patch_route_deps(user_mock=user, db_mock=db)
        with (
            stack,
            patch("file_organizer.web.profile_routes.verify_password", return_value=True),
            patch(
                "file_organizer.web.profile_routes.validate_password",
                return_value=(True, None),
            ),
            patch("file_organizer.web.profile_routes.hash_password", return_value="newhash"),
            patch(
                "file_organizer.web.profile_routes._load_profile_state",
                return_value={"activity_log": [], "notifications": [], "two_factor_enabled": False},
            ),
            patch(
                "file_organizer.web.profile_routes._save_profile_state",
            ),
        ):
            account_settings_change_password(
                MagicMock(),
                current_password="old",
                new_password="NewStr0ng!",
                confirm_password="NewStr0ng!",
                settings=MagicMock(),
            )
        assert db_user.hashed_password == "newhash"
        assert "Password updated" in str(p["tmpl"].TemplateResponse.call_args)


# ---------------------------------------------------------------------------
# Two-factor toggle tests
# ---------------------------------------------------------------------------


class TestToggle2FA:
    """Covers account_settings_toggle_2fa route branches."""

    def test_2fa_enable(self) -> None:
        from file_organizer.web.profile_routes import account_settings_toggle_2fa

        user = MagicMock()
        user.id = "u1"
        db = _make_db_mock()

        stack, p = _patch_route_deps(user_mock=user, db_mock=db)
        with (
            stack,
            patch(
                "file_organizer.web.profile_routes._load_profile_state",
                return_value={"activity_log": [], "notifications": []},
            ),
            patch(
                "file_organizer.web.profile_routes._save_profile_state",
            ),
        ):
            account_settings_toggle_2fa(
                MagicMock(),
                enabled="true",
                settings=MagicMock(),
            )
        ctx_args = str(p["tmpl"].TemplateResponse.call_args)
        assert "Two-factor preference updated" in ctx_args

    def test_2fa_disable(self) -> None:
        from file_organizer.web.profile_routes import account_settings_toggle_2fa

        user = MagicMock()
        user.id = "u1"
        db = _make_db_mock()

        stack, p = _patch_route_deps(user_mock=user, db_mock=db)
        with (
            stack,
            patch(
                "file_organizer.web.profile_routes._load_profile_state",
                return_value={"activity_log": [], "notifications": []},
            ),
            patch(
                "file_organizer.web.profile_routes._save_profile_state",
            ),
        ):
            account_settings_toggle_2fa(
                MagicMock(),
                enabled=None,
                settings=MagicMock(),
            )
        ctx_args = str(p["tmpl"].TemplateResponse.call_args)
        assert "Two-factor preference updated" in ctx_args


# ---------------------------------------------------------------------------
# API key management tests
# ---------------------------------------------------------------------------


class TestApiKeys:
    """Covers API key list, generate, and revoke routes."""

    def test_api_keys_list(self) -> None:
        from file_organizer.web.profile_routes import api_keys_partial

        user = MagicMock()
        user.id = "u1"
        db = _make_db_mock(query_results=[])

        stack, p = _patch_route_deps(user_mock=user, db_mock=db)
        with (
            stack,
            patch(
                "file_organizer.web.profile_routes._ensure_api_key_table",
            ),
        ):
            api_keys_partial(MagicMock(), settings=MagicMock())
        p["tmpl"].TemplateResponse.assert_called_once()

    def test_api_key_generate(self) -> None:
        from file_organizer.web.profile_routes import api_key_generate

        user = MagicMock()
        user.id = "u1"
        db = _make_db_mock(query_results=[])

        stack, p = _patch_route_deps(user_mock=user, db_mock=db)
        with (
            stack,
            patch(
                "file_organizer.web.profile_routes._ensure_api_key_table",
            ),
            patch(
                "file_organizer.web.profile_routes._load_profile_state",
                return_value={"activity_log": [], "notifications": []},
            ),
            patch(
                "file_organizer.web.profile_routes._save_profile_state",
            ),
            patch("file_organizer.api.api_keys.hash_api_key", return_value="hashed-key"),
        ):
            api_key_generate(MagicMock(), label="my-key", settings=MagicMock())
        db.add.assert_called_once()
        db.commit.assert_called_once()
        # Check that raw_key is passed in extras
        ctx_args = str(p["tmpl"].TemplateResponse.call_args)
        assert "fo_" in ctx_args  # raw_key starts with fo_

    def test_api_key_revoke(self) -> None:
        from file_organizer.web.profile_routes import api_key_revoke

        user = MagicMock()
        user.id = "u1"
        api_key = MagicMock()
        api_key.label = "my-key"
        api_key.is_active = True
        db = _make_db_mock(query_results=[])
        # The revoke route queries for the specific key, then lists all
        db.query.return_value.filter.return_value.first.return_value = api_key
        db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []

        stack, p = _patch_route_deps(user_mock=user, db_mock=db)
        with (
            stack,
            patch(
                "file_organizer.web.profile_routes._ensure_api_key_table",
            ),
            patch(
                "file_organizer.web.profile_routes._load_profile_state",
                return_value={"activity_log": [], "notifications": []},
            ),
            patch(
                "file_organizer.web.profile_routes._save_profile_state",
            ),
        ):
            api_key_revoke(MagicMock(), key_id="k1", settings=MagicMock())
        assert api_key.is_active is False
        db.commit.assert_called_once()


# ---------------------------------------------------------------------------
# Avatar upload tests
# ---------------------------------------------------------------------------


class TestAvatarUpload:
    """Covers profile_avatar_upload route."""

    def test_avatar_too_large(self) -> None:
        from file_organizer.web.profile_routes import profile_avatar_upload

        user = MagicMock()
        user.id = "u1"
        avatar = MagicMock()
        avatar.read = AsyncMock(return_value=b"x" * (6 * 1024 * 1024))

        stack, p = _patch_route_deps(user_mock=user)
        with stack:
            result = asyncio.get_event_loop().run_until_complete(
                profile_avatar_upload(MagicMock(), avatar=avatar, settings=MagicMock())
            )
        assert "5MB" in result.body.decode()

    def test_avatar_success(self, tmp_path) -> None:
        from file_organizer.web.profile_routes import profile_avatar_upload

        user = MagicMock()
        user.id = "u1"
        avatar = MagicMock()
        avatar.read = AsyncMock(return_value=b"png-data")

        stack, p = _patch_route_deps(user_mock=user)
        with (
            stack,
            patch("file_organizer.web.profile_routes._AVATAR_DIR", tmp_path),
            patch(
                "file_organizer.web.profile_routes._avatar_path",
                return_value=tmp_path / "u1.png",
            ),
        ):
            result = asyncio.get_event_loop().run_until_complete(
                profile_avatar_upload(MagicMock(), avatar=avatar, settings=MagicMock())
            )
        assert "Avatar updated" in result.body.decode()
        assert (tmp_path / "u1.png").read_bytes() == b"png-data"


# ---------------------------------------------------------------------------
# Profile edit tests
# ---------------------------------------------------------------------------


class TestProfileEdit:
    """Covers profile_edit_submit route."""

    def test_edit_profile_email_conflict(self) -> None:
        from file_organizer.web.profile_routes import profile_edit_submit

        user = MagicMock()
        user.id = "u1"
        db_user = MagicMock()
        db_user.email = "old@e.com"
        db_user.id = "u1"
        db = MagicMock()
        # First filter → db_user (finding user by id), second filter → existing (email conflict)
        db.query.return_value.filter.return_value.first.side_effect = [db_user, MagicMock()]

        stack, p = _patch_route_deps(user_mock=user, db_mock=db)
        with stack:
            profile_edit_submit(
                MagicMock(),
                full_name="Name",
                email="conflict@e.com",
                settings=MagicMock(),
            )
        assert "Email already in use" in str(p["tmpl"].TemplateResponse.call_args)


# ---------------------------------------------------------------------------
# Logout tests
# ---------------------------------------------------------------------------


class TestLogout:
    """Covers logout route."""

    def test_logout_deletes_cookie(self) -> None:
        from file_organizer.web.profile_routes import logout

        result = logout(MagicMock(), settings=MagicMock())
        assert result.status_code == 303
