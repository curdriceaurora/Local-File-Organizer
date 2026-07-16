"""Focused tests for profile state helper logic."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from file_organizer.web import profile_state

pytestmark = [pytest.mark.unit, pytest.mark.ci]


def test_append_activity_uses_injected_clock_and_caps_log() -> None:
    state: dict[str, object] = {
        "activity_log": [
            {"id": str(index), "message": "old", "timestamp": ""} for index in range(100)
        ]
    }

    profile_state.append_activity(
        state,
        "new",
        id_factory=lambda: "activity-id",
        clock=lambda: datetime(2026, 1, 2, 3, 4, tzinfo=UTC),
    )

    log = state["activity_log"]
    assert isinstance(log, list)
    assert len(log) == 100
    assert log[0] == {
        "id": "activity-id",
        "message": "new",
        "timestamp": "2026-01-02T03:04:00+00:00",
    }


def test_invite_team_member_normalizes_input_and_records_notification() -> None:
    state = profile_state.default_profile_state()

    profile_state.invite_team_member(
        state,
        " Person@Example.COM ",
        "owner",
        id_factory=lambda: "member-id",
    )

    assert state["team_members"] == [
        {
            "id": "member-id",
            "email": "person@example.com",
            "role": "viewer",
            "status": "invited",
        }
    ]
    notifications = state["notifications"]
    assert isinstance(notifications, list)
    assert notifications[0]["message"] == "Invitation created for person@example.com."


def test_update_team_member_role_only_changes_matching_member() -> None:
    state = {
        "team_members": [
            {"id": "one", "email": "one@example.com", "role": "viewer"},
            {"id": "two", "email": "two@example.com", "role": "viewer"},
        ],
        "activity_log": [],
    }

    profile_state.update_team_member_role(state, "two", "admin")

    team = state["team_members"]
    assert isinstance(team, list)
    assert team[0]["role"] == "viewer"
    assert team[1]["role"] == "admin"
    assert team[1]["status"] == "active"
    activity = state["activity_log"]
    assert isinstance(activity, list)
    assert "Updated role for two@example.com to admin." == activity[0]["message"]


def test_shared_folder_helpers_normalize_and_remove_entries(tmp_path) -> None:
    state = profile_state.default_profile_state()
    shared_dir = tmp_path / "shared"

    profile_state.add_shared_folder(
        state,
        f" {shared_dir} ",
        "delete",
        id_factory=lambda: "folder-id",
    )
    profile_state.remove_shared_folder(state, "folder-id")

    assert state["shared_folders"] == []
    activity = state["activity_log"]
    assert isinstance(activity, list)
    assert activity[0]["message"] == "Removed a shared folder entry."
    assert activity[1]["message"] == f"Shared folder '{shared_dir}' as view."


def test_remove_shared_folder_ignores_missing_id_without_activity() -> None:
    state = {
        "shared_folders": [{"id": "folder-id", "path": "/safe", "permission": "view"}],
        "activity_log": [],
    }

    profile_state.remove_shared_folder(state, "missing")

    assert state["shared_folders"] == [{"id": "folder-id", "path": "/safe", "permission": "view"}]
    assert state["activity_log"] == []


def test_mark_notification_read_ignores_non_matching_entries() -> None:
    state = {
        "notifications": [
            {"id": "one", "read": False},
            {"id": "two", "read": False},
        ]
    }

    profile_state.mark_notification_read(state, "two")

    notifications = state["notifications"]
    assert isinstance(notifications, list)
    assert notifications[0]["read"] is False
    assert notifications[1]["read"] is True


def test_load_profile_state_falls_back_when_json_is_invalid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = MagicMock()
    monkeypatch.setattr(profile_state.SettingsRepository, "get", lambda *_args, **_kwargs: "{")

    result = profile_state.load_profile_state(db, "user-id")

    assert result == profile_state.default_profile_state()


def test_load_profile_state_propagates_unexpected_sanitizer_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = MagicMock()
    monkeypatch.setattr(profile_state.SettingsRepository, "get", lambda *_args, **_kwargs: "{}")

    def broken(_raw: object) -> dict[str, object]:
        raise RuntimeError("sanitizer bug")

    monkeypatch.setattr(profile_state, "sanitize_profile_state", broken)

    with pytest.raises(RuntimeError, match="sanitizer bug"):
        profile_state.load_profile_state(db, "user-id")
