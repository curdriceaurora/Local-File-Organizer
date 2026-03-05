"""Coverage tests for file_organizer.web.profile_routes — route handler branches."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

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
