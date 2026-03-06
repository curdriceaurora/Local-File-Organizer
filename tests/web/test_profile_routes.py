"""Unit tests for web profile_routes helpers and route handlers.

Tests internal helpers (_default_profile_state, _sanitize_profile_state,
_append_activity, _append_notification, _avatar_path,
_cleanup_expired_reset_tokens, get_current_web_user, _require_web_user,
_make_profile_context, _workspace_context) and key route handlers.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.api.config import ApiSettings

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def settings():
    """Return a mocked ApiSettings."""
    s = MagicMock(spec=ApiSettings)
    s.allowed_paths = ["/tmp/test"]
    s.db_url = "sqlite://"
    s.auth_enabled = True
    s.auth_db_path = ":memory:"
    return s


@pytest.fixture()
def fake_user():
    """Return a minimal mock User object."""
    user = MagicMock()
    user.id = "user-1"
    user.email = "test@example.com"
    user.display_name = "Test User"
    user.role = "admin"
    user.is_active = True
    user.created_at = datetime(2025, 1, 1, tzinfo=UTC)
    return user


# ---------------------------------------------------------------------------
# _default_profile_state
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDefaultProfileState:
    """Test the _default_profile_state helper."""

    def test_returns_expected_keys(self):
        from file_organizer.web.profile_routes import _default_profile_state

        state = _default_profile_state()
        assert isinstance(state, dict)
        assert "active_workspace_id" in state
        assert "team_members" in state
        assert "shared_folders" in state
        assert "activity_log" in state
        assert "notifications" in state
        assert "two_factor_enabled" in state

    def test_defaults_are_sensible(self):
        from file_organizer.web.profile_routes import _default_profile_state

        state = _default_profile_state()
        assert state["active_workspace_id"] == ""
        assert isinstance(state["activity_log"], list)
        assert isinstance(state["notifications"], list)
        assert state["two_factor_enabled"] is False


# ---------------------------------------------------------------------------
# _sanitize_profile_state
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSanitizeProfileState:
    """Test _sanitize_profile_state normalisation."""

    def test_none_input(self):
        from file_organizer.web.profile_routes import _sanitize_profile_state

        result = _sanitize_profile_state(None)
        assert isinstance(result, dict)
        assert "active_workspace_id" in result

    def test_empty_dict(self):
        from file_organizer.web.profile_routes import _sanitize_profile_state

        result = _sanitize_profile_state({})
        assert "active_workspace_id" in result

    def test_preserves_valid_keys(self):
        from file_organizer.web.profile_routes import _sanitize_profile_state

        raw = {
            "active_workspace_id": "ws-42",
            "two_factor_enabled": True,
            "activity_log": [{"id": "a", "message": "hi", "timestamp": "t"}],
        }
        result = _sanitize_profile_state(raw)
        assert result["active_workspace_id"] == "ws-42"
        assert result["two_factor_enabled"] is True
        assert len(result["activity_log"]) == 1

    def test_activity_log_non_list(self):
        from file_organizer.web.profile_routes import _sanitize_profile_state

        raw = {"activity_log": "not a list"}
        result = _sanitize_profile_state(raw)
        assert isinstance(result["activity_log"], list)
        # Falls back to default empty list
        assert result["activity_log"] == []

    def test_notifications_non_list(self):
        from file_organizer.web.profile_routes import _sanitize_profile_state

        raw = {"notifications": 42}
        result = _sanitize_profile_state(raw)
        assert isinstance(result["notifications"], list)
        assert result["notifications"] == []

    def test_non_string_workspace_id_ignored(self):
        from file_organizer.web.profile_routes import _sanitize_profile_state

        raw = {"active_workspace_id": 123}
        result = _sanitize_profile_state(raw)
        assert result["active_workspace_id"] == ""

    def test_non_bool_two_factor_ignored(self):
        from file_organizer.web.profile_routes import _sanitize_profile_state

        raw = {"two_factor_enabled": "yes"}
        result = _sanitize_profile_state(raw)
        assert result["two_factor_enabled"] is False

    def test_string_input(self):
        from file_organizer.web.profile_routes import _sanitize_profile_state

        result = _sanitize_profile_state("bogus")
        assert isinstance(result, dict)
        assert "notifications" in result


# ---------------------------------------------------------------------------
# _append_activity / _append_notification
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAppendActivity:
    """Test the _append_activity helper."""

    def test_appends_entry(self):
        from file_organizer.web.profile_routes import _append_activity

        state: dict[str, object] = {"activity_log": []}
        _append_activity(state, "Did something")
        log = state["activity_log"]
        assert isinstance(log, list)
        assert len(log) == 1
        assert log[0]["message"] == "Did something"
        assert "timestamp" in log[0]
        assert "id" in log[0]

    def test_caps_at_limit(self):
        from file_organizer.web.profile_routes import _append_activity

        state: dict[str, object] = {
            "activity_log": [
                {"id": str(i), "message": f"Item {i}", "timestamp": ""} for i in range(120)
            ]
        }
        _append_activity(state, "new entry")
        log = state["activity_log"]
        assert isinstance(log, list)
        # Capped at 100 after insert
        assert len(log) <= 101

    def test_creates_list_when_not_list(self):
        from file_organizer.web.profile_routes import _append_activity

        state: dict[str, object] = {"activity_log": "bad"}
        _append_activity(state, "fixed")
        log = state["activity_log"]
        assert isinstance(log, list)
        assert len(log) == 1


@pytest.mark.unit
class TestAppendNotification:
    """Test the _append_notification helper."""

    def test_appends_notification(self):
        from file_organizer.web.profile_routes import _append_notification

        state: dict[str, object] = {"notifications": []}
        _append_notification(state, "Alert!")
        notifs = state["notifications"]
        assert isinstance(notifs, list)
        assert len(notifs) == 1
        assert notifs[0]["message"] == "Alert!"
        assert "created_at" in notifs[0]
        assert notifs[0]["read"] is False

    def test_creates_list_when_not_list(self):
        from file_organizer.web.profile_routes import _append_notification

        state: dict[str, object] = {"notifications": None}
        _append_notification(state, "Info message")
        notifs = state["notifications"]
        assert isinstance(notifs, list)
        assert len(notifs) == 1

    def test_caps_at_limit(self):
        from file_organizer.web.profile_routes import _append_notification

        state: dict[str, object] = {
            "notifications": [
                {"id": str(i), "message": "x", "created_at": "", "read": False} for i in range(120)
            ]
        }
        _append_notification(state, "new")
        notifs = state["notifications"]
        assert isinstance(notifs, list)
        assert len(notifs) <= 101


# ---------------------------------------------------------------------------
# _avatar_path
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAvatarPath:
    """Test _avatar_path returns a Path under the avatar directory."""

    def test_returns_path_for_user_id(self):
        from file_organizer.web.profile_routes import _avatar_path

        result = _avatar_path("user-123")
        assert isinstance(result, Path)
        assert "user-123" in str(result)
        assert "avatars" in str(result)

    def test_extension_is_png(self):
        from file_organizer.web.profile_routes import _avatar_path

        result = _avatar_path("abc")
        assert result.suffix == ".png"


# ---------------------------------------------------------------------------
# _cleanup_expired_reset_tokens
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCleanupExpiredResetTokens:
    """Test the _cleanup_expired_reset_tokens helper."""

    def test_removes_expired_tokens(self):
        from file_organizer.web.profile_routes import (
            _PASSWORD_RESET_TOKENS,
            _cleanup_expired_reset_tokens,
        )

        # Insert an expired token
        expired_time = datetime.now(UTC) - timedelta(hours=1)
        token_value = secrets.token_urlsafe(16)
        _PASSWORD_RESET_TOKENS[token_value] = ("user@test.com", expired_time)

        _cleanup_expired_reset_tokens()

        assert token_value not in _PASSWORD_RESET_TOKENS

    def test_keeps_valid_tokens(self):
        from file_organizer.web.profile_routes import (
            _PASSWORD_RESET_TOKENS,
            _cleanup_expired_reset_tokens,
        )

        future_time = datetime.now(UTC) + timedelta(hours=1)
        token_value = secrets.token_urlsafe(16)
        _PASSWORD_RESET_TOKENS[token_value] = ("valid@test.com", future_time)

        _cleanup_expired_reset_tokens()

        assert token_value in _PASSWORD_RESET_TOKENS
        # Clean up
        _PASSWORD_RESET_TOKENS.pop(token_value, None)


# ---------------------------------------------------------------------------
# get_current_web_user
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetCurrentWebUser:
    """Test the get_current_web_user dependency."""

    def test_no_cookie(self, settings):
        from file_organizer.web.profile_routes import get_current_web_user

        request = MagicMock()
        request.cookies = {}
        result = get_current_web_user(request, settings)
        assert result is None

    def test_auth_disabled(self, settings):
        from file_organizer.web.profile_routes import get_current_web_user

        settings.auth_enabled = False
        request = MagicMock()
        request.cookies = {"fo_session": "some-token"}
        result = get_current_web_user(request, settings)
        assert result is None

    def test_invalid_token(self, settings):
        from file_organizer.web.profile_routes import TokenError, get_current_web_user

        request = MagicMock()
        request.cookies = {"fo_session": "invalid-token"}

        with patch(
            "file_organizer.web.profile_routes.decode_token",
            side_effect=TokenError("bad token"),
        ):
            result = get_current_web_user(request, settings)
        assert result is None

    def test_valid_token_user_found(self, settings, fake_user):
        from file_organizer.web.profile_routes import get_current_web_user

        request = MagicMock()
        request.cookies = {"fo_session": "valid-token"}

        mock_payload = {"user_id": "user-1"}
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = fake_user

        with (
            patch("file_organizer.web.profile_routes.decode_token", return_value=mock_payload),
            patch("file_organizer.web.profile_routes.is_access_token", return_value=True),
            patch("file_organizer.web.profile_routes.create_session", return_value=mock_db),
        ):
            result = get_current_web_user(request, settings)
        assert result is not None
        assert result.id == "user-1"
        mock_db.close.assert_called_once()

    def test_valid_token_user_not_found(self, settings):
        from file_organizer.web.profile_routes import get_current_web_user

        request = MagicMock()
        request.cookies = {"fo_session": "valid-token"}

        mock_payload = {"user_id": "missing-user"}
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with (
            patch("file_organizer.web.profile_routes.decode_token", return_value=mock_payload),
            patch("file_organizer.web.profile_routes.is_access_token", return_value=True),
            patch("file_organizer.web.profile_routes.create_session", return_value=mock_db),
        ):
            result = get_current_web_user(request, settings)
        assert result is None
        mock_db.close.assert_called_once()

    def test_token_not_access_token(self, settings):
        from file_organizer.web.profile_routes import get_current_web_user

        request = MagicMock()
        request.cookies = {"fo_session": "refresh-token"}

        mock_payload = {"user_id": "user-1"}
        with (
            patch("file_organizer.web.profile_routes.decode_token", return_value=mock_payload),
            patch("file_organizer.web.profile_routes.is_access_token", return_value=False),
        ):
            result = get_current_web_user(request, settings)
        assert result is None

    def test_missing_user_id_in_payload(self, settings):
        from file_organizer.web.profile_routes import get_current_web_user

        request = MagicMock()
        request.cookies = {"fo_session": "some-token"}

        mock_payload = {"scope": "full"}  # no user_id key
        with (
            patch("file_organizer.web.profile_routes.decode_token", return_value=mock_payload),
            patch("file_organizer.web.profile_routes.is_access_token", return_value=True),
        ):
            result = get_current_web_user(request, settings)
        assert result is None


# ---------------------------------------------------------------------------
# _require_web_user
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRequireWebUser:
    """Test the _require_web_user helper."""

    def test_returns_user_when_authenticated(self, settings, fake_user):
        from file_organizer.web.profile_routes import _require_web_user

        request = MagicMock()
        with patch(
            "file_organizer.web.profile_routes.get_current_web_user",
            return_value=fake_user,
        ):
            result = _require_web_user(request, settings)
        assert result == fake_user

    def test_returns_html_response_when_not_authenticated(self, settings):
        from fastapi.responses import HTMLResponse

        from file_organizer.web.profile_routes import _require_web_user

        request = MagicMock()
        with patch(
            "file_organizer.web.profile_routes.get_current_web_user",
            return_value=None,
        ):
            result = _require_web_user(request, settings)
        assert isinstance(result, HTMLResponse)


# ---------------------------------------------------------------------------
# _workspace_context
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestWorkspaceContext:
    """Test the _workspace_context helper."""

    def test_returns_tuple_with_workspaces(self):
        from file_organizer.web.profile_routes import _workspace_context

        mock_db = MagicMock()
        with (
            patch(
                "file_organizer.web.profile_routes.WorkspaceRepository.list_by_owner",
                return_value=[],
            ),
            patch(
                "file_organizer.web.profile_routes._load_profile_state",
                return_value={"active_workspace_id": ""},
            ),
        ):
            result = _workspace_context(mock_db, "user-1")
        assert isinstance(result, tuple)
        assert len(result) == 2
        workspaces, active_id = result
        assert workspaces == []
        assert isinstance(active_id, str)

    def test_selects_first_workspace_when_no_active(self):
        from file_organizer.web.profile_routes import _workspace_context

        mock_ws = MagicMock()
        mock_ws.id = "ws-1"
        mock_db = MagicMock()

        with (
            patch(
                "file_organizer.web.profile_routes.WorkspaceRepository.list_by_owner",
                return_value=[mock_ws],
            ),
            patch(
                "file_organizer.web.profile_routes._load_profile_state",
                return_value={"active_workspace_id": ""},
            ),
            patch(
                "file_organizer.web.profile_routes._save_profile_state",
            ),
        ):
            workspaces, active_id = _workspace_context(mock_db, "user-1")
        assert active_id == "ws-1"
        assert workspaces == [mock_ws]


# ---------------------------------------------------------------------------
# _make_profile_context
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMakeProfileContext:
    """Test the _make_profile_context helper."""

    def test_with_user(self, settings, fake_user):
        from file_organizer.web.profile_routes import _make_profile_context

        request = MagicMock()

        with patch(
            "file_organizer.web.profile_routes.base_context",
            return_value={"request": request, "user": fake_user, "auth_enabled": True},
        ):
            ctx = _make_profile_context(request, settings, fake_user)
        assert isinstance(ctx, dict)
        assert ctx["user"] == fake_user

    def test_with_no_user(self, settings):
        from file_organizer.web.profile_routes import _make_profile_context

        request = MagicMock()

        with patch(
            "file_organizer.web.profile_routes.base_context",
            return_value={"request": request, "user": None, "auth_enabled": True},
        ):
            ctx = _make_profile_context(request, settings, None)
        assert isinstance(ctx, dict)
        assert ctx.get("user") is None

    def test_extras_merged(self, settings, fake_user):
        from file_organizer.web.profile_routes import _make_profile_context

        request = MagicMock()

        with patch(
            "file_organizer.web.profile_routes.base_context",
            return_value={
                "request": request,
                "user": fake_user,
                "auth_enabled": True,
                "custom": 42,
            },
        ):
            ctx = _make_profile_context(request, settings, fake_user, extras={"custom": 42})
        assert ctx.get("custom") == 42


# ---------------------------------------------------------------------------
# UserApiKey model
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestUserApiKeyModel:
    """Test the UserApiKey SQLAlchemy model declaration."""

    def test_table_name(self):
        from file_organizer.web.profile_routes import UserApiKey

        assert UserApiKey.__tablename__ == "user_api_keys"

    def test_has_expected_columns(self):
        from file_organizer.web.profile_routes import UserApiKey

        col_names = [c.name for c in UserApiKey.__table__.columns]
        assert "id" in col_names
        assert "user_id" in col_names
        assert "key_hash" in col_names
        assert "label" in col_names


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestModuleConstants:
    """Verify module-level constants are sensible."""

    def test_session_cookie_name(self):
        from file_organizer.web.profile_routes import _SESSION_COOKIE

        assert _SESSION_COOKIE == "fo_session"

    def test_default_roles(self):
        from file_organizer.web.profile_routes import _DEFAULT_ROLES

        assert "admin" in _DEFAULT_ROLES
        assert "viewer" in _DEFAULT_ROLES
        assert "editor" in _DEFAULT_ROLES

    def test_reset_token_ttl(self):
        from file_organizer.web.profile_routes import _RESET_TOKEN_TTL_MINUTES

        assert _RESET_TOKEN_TTL_MINUTES > 0
