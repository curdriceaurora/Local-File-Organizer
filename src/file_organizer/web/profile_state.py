"""Profile state persistence and mutation helpers for the web profile UI."""

from __future__ import annotations

import json
import secrets
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from file_organizer.api.repositories.settings_repo import SettingsRepository

STATE_KEY = "web_profile_state"
DEFAULT_ROLES = {"viewer", "editor", "admin"}


def now_utc() -> datetime:
    """Return the current UTC datetime."""
    return datetime.now(UTC)


def default_profile_state() -> dict[str, object]:
    """Return the initial empty profile state dict."""
    return {
        "active_workspace_id": "",
        "team_members": [],
        "shared_folders": [],
        "activity_log": [],
        "notifications": [],
        "two_factor_enabled": False,
    }


def sanitize_profile_state(raw: object) -> dict[str, object]:
    """Normalize raw profile state data, filling in missing keys with defaults."""
    state = default_profile_state()
    if not isinstance(raw, dict):
        return state

    if isinstance(raw.get("active_workspace_id"), str):
        state["active_workspace_id"] = raw["active_workspace_id"]

    for key in ("team_members", "shared_folders", "activity_log", "notifications"):
        value = raw.get(key)
        if isinstance(value, list):
            state[key] = value

    two_factor = raw.get("two_factor_enabled")
    if isinstance(two_factor, bool):
        state["two_factor_enabled"] = two_factor
    return state


def load_profile_state(db: Session, user_id: str) -> dict[str, object]:
    """Load the profile state for *user_id* from the settings repository."""
    raw = SettingsRepository.get(db, STATE_KEY, user_id=user_id)
    if raw is None:
        return default_profile_state()
    try:
        return sanitize_profile_state(json.loads(raw))
    except Exception:
        return default_profile_state()


def save_profile_state(db: Session, user_id: str, state: dict[str, object]) -> None:
    """Persist the profile *state* dict for *user_id*."""
    SettingsRepository.set(db, STATE_KEY, json.dumps(state), user_id=user_id)


def append_activity(
    state: dict[str, object],
    message: str,
    *,
    id_factory: Callable[[], str] | None = None,
    clock: Callable[[], datetime] = now_utc,
) -> None:
    """Add a timestamped activity entry to the profile state."""
    log = state.get("activity_log")
    if not isinstance(log, list):
        log = []
        state["activity_log"] = log
    log.insert(
        0,
        {
            "id": id_factory() if id_factory else secrets.token_hex(4),
            "message": message,
            "timestamp": clock().isoformat(),
        },
    )
    del log[100:]


def append_notification(
    state: dict[str, object],
    message: str,
    *,
    id_factory: Callable[[], str] | None = None,
    clock: Callable[[], datetime] = now_utc,
) -> None:
    """Add a timestamped notification to the profile state."""
    notifications = state.get("notifications")
    if not isinstance(notifications, list):
        notifications = []
        state["notifications"] = notifications
    notifications.insert(
        0,
        {
            "id": id_factory() if id_factory else secrets.token_hex(4),
            "message": message,
            "created_at": clock().isoformat(),
            "read": False,
        },
    )
    del notifications[100:]


def normalize_role(role: str) -> str:
    """Return a supported team role, defaulting to viewer."""
    return role if role in DEFAULT_ROLES else "viewer"


def normalize_permission(permission: str) -> str:
    """Return a supported shared-folder permission, defaulting to view."""
    return permission if permission in {"view", "edit", "admin"} else "view"


def invite_team_member(
    state: dict[str, object],
    email: str,
    role: str,
    *,
    id_factory: Callable[[], str] | None = None,
) -> None:
    """Add an invited team member and record profile activity."""
    normalized_email = email.strip().lower()
    normalized_role = normalize_role(role)
    team = state.get("team_members")
    if not isinstance(team, list):
        team = []
        state["team_members"] = team
    team.append(
        {
            "id": id_factory() if id_factory else secrets.token_hex(4),
            "email": normalized_email,
            "role": normalized_role,
            "status": "invited",
        }
    )
    append_activity(state, f"Invited {normalized_email} as {normalized_role}.")
    append_notification(state, f"Invitation created for {normalized_email}.")


def update_team_member_role(state: dict[str, object], member_id: str, role: str) -> None:
    """Update an existing team member's role when present."""
    normalized_role = normalize_role(role)
    team = state.get("team_members")
    if not isinstance(team, list):
        return
    for member in team:
        if isinstance(member, dict) and member.get("id") == member_id:
            member["role"] = normalized_role
            member["status"] = "active"
            append_activity(
                state,
                f"Updated role for {member.get('email', 'member')} to {normalized_role}.",
            )
            break


def add_shared_folder(
    state: dict[str, object],
    folder_path: str,
    permission: str,
    *,
    id_factory: Callable[[], str] | None = None,
) -> None:
    """Add a shared folder entry and record profile activity."""
    normalized_path = folder_path.strip()
    normalized_permission = normalize_permission(permission)
    shared = state.get("shared_folders")
    if not isinstance(shared, list):
        shared = []
        state["shared_folders"] = shared
    shared.append(
        {
            "id": id_factory() if id_factory else secrets.token_hex(4),
            "path": normalized_path,
            "permission": normalized_permission,
        }
    )
    append_activity(state, f"Shared folder '{normalized_path}' as {normalized_permission}.")


def remove_shared_folder(state: dict[str, object], folder_id: str) -> None:
    """Remove a shared folder entry by id and record profile activity."""
    shared = state.get("shared_folders")
    if not isinstance(shared, list):
        return
    state["shared_folders"] = [
        folder
        for folder in shared
        if not (isinstance(folder, dict) and folder.get("id") == folder_id)
    ]
    append_activity(state, "Removed a shared folder entry.")


def mark_notification_read(state: dict[str, object], notification_id: str) -> None:
    """Mark one notification as read when present."""
    notifications = state.get("notifications")
    if not isinstance(notifications, list):
        return
    for item in notifications:
        if isinstance(item, dict) and item.get("id") == notification_id:
            item["read"] = True
            break


def set_two_factor_enabled(state: dict[str, object], enabled: bool) -> None:
    """Persist the 2FA preference in state and record profile activity."""
    state["two_factor_enabled"] = enabled
    append_activity(
        state, f"Set two-factor authentication to {'enabled' if enabled else 'disabled'}."
    )
