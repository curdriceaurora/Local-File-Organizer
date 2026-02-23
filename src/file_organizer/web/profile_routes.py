"""Web UI routes for authentication, profile, and collaboration features."""

from __future__ import annotations

import json
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, or_
from sqlalchemy.orm import Session

# Ensure database tables from db_models are registered on Base.metadata.
import file_organizer.api.db_models  # noqa: F401
from file_organizer.api.auth import (
    TokenError,
    create_token_bundle,
    decode_token,
    hash_password,
    is_access_token,
    validate_password,
    verify_password,
)
from file_organizer.api.auth_db import create_session
from file_organizer.api.auth_models import Base, User
from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_settings
from file_organizer.api.repositories.settings_repo import SettingsRepository
from file_organizer.api.repositories.workspace_repo import WorkspaceRepository
from file_organizer.web._helpers import base_context, templates

profile_router = APIRouter(tags=["web"])

_SESSION_COOKIE = "fo_session"
_API_KEY_PREFIX = "fo"
_STATE_KEY = "web_profile_state"
_RESET_TOKEN_TTL_MINUTES = 20
_SETTINGS_DIR = Path.home() / ".config" / "file-organizer"
_AVATAR_DIR = _SETTINGS_DIR / "avatars"
_DEFAULT_ROLES = {"viewer", "editor", "admin"}
_PASSWORD_RESET_TOKENS: dict[str, tuple[str, datetime]] = {}


class UserApiKey(Base):
    """Per-user API key stored in the auth database."""

    __tablename__ = "user_api_keys"

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    label = Column(String, nullable=False)
    key_prefix = Column(String, nullable=False)
    key_hash = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


def _now() -> datetime:
    return datetime.now(UTC)


def _ensure_api_key_table(db_path: str) -> None:
    from file_organizer.api.auth_db import get_engine

    engine = get_engine(db_path)
    UserApiKey.__table__.create(engine, checkfirst=True)


def _get_db(settings: ApiSettings) -> Session:
    return create_session(settings.auth_db_path)


def get_current_web_user(request: Request, settings: ApiSettings) -> Optional[User]:
    """Read session cookie and return the authenticated user when available."""
    if not settings.auth_enabled:
        return None
    token = request.cookies.get(_SESSION_COOKIE)
    if not token:
        return None
    try:
        payload = decode_token(token, settings)
    except TokenError:
        return None
    if not is_access_token(payload):
        return None
    user_id = payload.get("user_id")
    if not isinstance(user_id, str):
        return None

    db = create_session(settings.auth_db_path)
    try:
        return db.query(User).filter(User.id == user_id, User.is_active.is_(True)).first()
    finally:
        db.close()


def _require_web_user(request: Request, settings: ApiSettings) -> User | HTMLResponse:
    user = get_current_web_user(request, settings)
    if user is None:
        return HTMLResponse('<p class="error-text">Not authenticated.</p>')
    return user


def _default_profile_state() -> dict[str, object]:
    return {
        "active_workspace_id": "",
        "team_members": [],
        "shared_folders": [],
        "activity_log": [],
        "notifications": [],
        "two_factor_enabled": False,
    }


def _sanitize_profile_state(raw: object) -> dict[str, object]:
    state = _default_profile_state()
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


def _load_profile_state(db: Session, user_id: str) -> dict[str, object]:
    raw = SettingsRepository.get(db, _STATE_KEY, user_id=user_id)
    if raw is None:
        return _default_profile_state()
    try:
        return _sanitize_profile_state(json.loads(raw))
    except Exception:
        return _default_profile_state()


def _save_profile_state(db: Session, user_id: str, state: dict[str, object]) -> None:
    SettingsRepository.set(db, _STATE_KEY, json.dumps(state), user_id=user_id)


def _append_activity(state: dict[str, object], message: str) -> None:
    log = state.get("activity_log")
    if not isinstance(log, list):
        log = []
        state["activity_log"] = log
    log.insert(
        0,
        {
            "id": secrets.token_hex(4),
            "message": message,
            "timestamp": _now().isoformat(),
        },
    )
    del log[100:]


def _append_notification(state: dict[str, object], message: str) -> None:
    notifications = state.get("notifications")
    if not isinstance(notifications, list):
        notifications = []
        state["notifications"] = notifications
    notifications.insert(
        0,
        {
            "id": secrets.token_hex(4),
            "message": message,
            "created_at": _now().isoformat(),
            "read": False,
        },
    )
    del notifications[100:]


def _workspace_context(db: Session, user_id: str) -> tuple[list[object], str]:
    workspaces = WorkspaceRepository.list_by_owner(db, user_id)
    state = _load_profile_state(db, user_id)
    active_workspace_id = state.get("active_workspace_id")
    active = active_workspace_id if isinstance(active_workspace_id, str) else ""

    workspace_ids = {workspace.id for workspace in workspaces}
    if active and active not in workspace_ids:
        active = ""

    if not active and workspaces:
        active = workspaces[0].id
        state["active_workspace_id"] = active
        _save_profile_state(db, user_id, state)

    return workspaces, active


def _avatar_path(user_id: str) -> Path:
    return _AVATAR_DIR / f"{user_id}.png"


def _cleanup_expired_reset_tokens() -> None:
    now = _now()
    stale = [token for token, (_, expires) in _PASSWORD_RESET_TOKENS.items() if expires <= now]
    for token in stale:
        _PASSWORD_RESET_TOKENS.pop(token, None)


def _make_profile_context(
    request: Request,
    settings: ApiSettings,
    user: Optional[User],
    *,
    extras: Optional[dict[str, object]] = None,
) -> dict[str, object]:
    context_extras: dict[str, object] = {"user": user, "auth_enabled": settings.auth_enabled}
    if extras:
        context_extras.update(extras)
    return base_context(
        request,
        settings,
        active="profile",
        title="Profile",
        extras=context_extras,
    )


@profile_router.get("/profile", response_class=HTMLResponse)
def profile_page(request: Request, settings: ApiSettings = Depends(get_settings)) -> HTMLResponse:
    """Render the user profile page."""
    user = get_current_web_user(request, settings)
    if user is None:
        context = _make_profile_context(request, settings, None)
        return templates.TemplateResponse("profile/index.html", context)

    db = _get_db(settings)
    try:
        workspaces, active_workspace_id = _workspace_context(db, user.id)
        context = _make_profile_context(
            request,
            settings,
            user,
            extras={
                "workspace_options": workspaces,
                "active_workspace_id": active_workspace_id,
                "avatar_url": f"/ui/profile/avatar/{user.id}",
            },
        )
        return templates.TemplateResponse("profile/index.html", context)
    finally:
        db.close()


@profile_router.get("/profile/login", response_class=HTMLResponse)
def login_form(request: Request, settings: ApiSettings = Depends(get_settings)) -> HTMLResponse:
    """Render the login form."""
    context = _make_profile_context(request, settings, None, extras={"error": None})
    return templates.TemplateResponse("profile/login.html", context)


@profile_router.post("/profile/login", response_class=HTMLResponse, response_model=None)
def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    settings: ApiSettings = Depends(get_settings),
) -> HTMLResponse | RedirectResponse:
    """Handle login form submission."""
    db = _get_db(settings)
    try:
        user = db.query(User).filter(or_(User.username == username, User.email == username)).first()
        if user is None or not verify_password(password, user.hashed_password):
            context = _make_profile_context(
                request,
                settings,
                None,
                extras={"error": "Incorrect username or password"},
            )
            return templates.TemplateResponse("profile/login.html", context)

        if not user.is_active:
            context = _make_profile_context(
                request,
                settings,
                None,
                extras={"error": "Account is inactive"},
            )
            return templates.TemplateResponse("profile/login.html", context)

        user.last_login = _now()
        db.commit()

        bundle = create_token_bundle(user.id, user.username, settings)
        response = RedirectResponse(url="/ui/profile", status_code=303)
        response.set_cookie(
            key=_SESSION_COOKIE,
            value=bundle.access_token,
            httponly=True,
            samesite="lax",
            max_age=settings.auth_access_token_minutes * 60,
            path="/",
        )
        return response
    finally:
        db.close()


@profile_router.get("/profile/register", response_class=HTMLResponse)
def register_form(request: Request, settings: ApiSettings = Depends(get_settings)) -> HTMLResponse:
    """Render the registration form."""
    context = _make_profile_context(request, settings, None, extras={"error": None})
    return templates.TemplateResponse("profile/register.html", context)


@profile_router.post("/profile/register", response_class=HTMLResponse, response_model=None)
def register_submit(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    full_name: str = Form(""),
    settings: ApiSettings = Depends(get_settings),
) -> HTMLResponse | RedirectResponse:
    """Handle registration form submission."""
    db = _get_db(settings)
    try:
        valid, reason = validate_password(password, settings)
        if not valid:
            context = _make_profile_context(request, settings, None, extras={"error": reason})
            return templates.TemplateResponse("profile/register.html", context)

        if db.query(User).filter(User.username == username).first():
            context = _make_profile_context(
                request,
                settings,
                None,
                extras={"error": "Username already taken"},
            )
            return templates.TemplateResponse("profile/register.html", context)

        if db.query(User).filter(User.email == email).first():
            context = _make_profile_context(
                request,
                settings,
                None,
                extras={"error": "Email already registered"},
            )
            return templates.TemplateResponse("profile/register.html", context)

        user = User(
            username=username,
            email=email,
            hashed_password=hash_password(password),
            full_name=full_name or None,
        )
        db.add(user)
        db.commit()
        return RedirectResponse(url="/ui/profile/login", status_code=303)
    finally:
        db.close()


@profile_router.get("/profile/forgot-password", response_class=HTMLResponse)
def forgot_password_form(
    request: Request, settings: ApiSettings = Depends(get_settings)
) -> HTMLResponse:
    """Render the forgot-password form."""
    context = _make_profile_context(
        request,
        settings,
        None,
        extras={"error": None, "success": None, "token_preview": None},
    )
    return templates.TemplateResponse("profile/forgot_password.html", context)


@profile_router.post("/profile/forgot-password", response_class=HTMLResponse)
def forgot_password_submit(
    request: Request,
    email: str = Form(...),
    settings: ApiSettings = Depends(get_settings),
) -> HTMLResponse:
    """Handle forgot-password form submission."""
    db = _get_db(settings)
    try:
        user = db.query(User).filter(User.email == email).first()
        token_preview = None
        success = "If an account exists for that email, a reset link has been prepared."
        if user is not None:
            _cleanup_expired_reset_tokens()
            token = secrets.token_urlsafe(24)
            expires = _now() + timedelta(minutes=_RESET_TOKEN_TTL_MINUTES)
            _PASSWORD_RESET_TOKENS[token] = (user.id, expires)
            token_preview = token
        context = _make_profile_context(
            request,
            settings,
            None,
            extras={"error": None, "success": success, "token_preview": token_preview},
        )
        return templates.TemplateResponse("profile/forgot_password.html", context)
    finally:
        db.close()


@profile_router.get("/profile/reset-password", response_class=HTMLResponse)
def reset_password_form(
    request: Request,
    token: str = Query(""),
    settings: ApiSettings = Depends(get_settings),
) -> HTMLResponse:
    """Render the reset-password form."""
    _cleanup_expired_reset_tokens()
    valid = token in _PASSWORD_RESET_TOKENS
    context = _make_profile_context(
        request,
        settings,
        None,
        extras={"token": token, "valid_token": valid, "error": None, "success": None},
    )
    return templates.TemplateResponse("profile/reset_password.html", context)


@profile_router.post("/profile/reset-password", response_class=HTMLResponse)
def reset_password_submit(
    request: Request,
    token: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    settings: ApiSettings = Depends(get_settings),
) -> HTMLResponse:
    """Handle reset-password form submission."""
    _cleanup_expired_reset_tokens()
    reset_info = _PASSWORD_RESET_TOKENS.get(token)
    if reset_info is None:
        context = _make_profile_context(
            request,
            settings,
            None,
            extras={
                "token": token,
                "valid_token": False,
                "error": "Reset token is invalid or expired.",
                "success": None,
            },
        )
        return templates.TemplateResponse("profile/reset_password.html", context)

    if new_password != confirm_password:
        context = _make_profile_context(
            request,
            settings,
            None,
            extras={
                "token": token,
                "valid_token": True,
                "error": "Passwords do not match.",
                "success": None,
            },
        )
        return templates.TemplateResponse("profile/reset_password.html", context)

    valid, reason = validate_password(new_password, settings)
    if not valid:
        context = _make_profile_context(
            request,
            settings,
            None,
            extras={"token": token, "valid_token": True, "error": reason, "success": None},
        )
        return templates.TemplateResponse("profile/reset_password.html", context)

    user_id, _ = reset_info
    db = _get_db(settings)
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if user is None:
            context = _make_profile_context(
                request,
                settings,
                None,
                extras={
                    "token": token,
                    "valid_token": False,
                    "error": "Account no longer exists.",
                    "success": None,
                },
            )
            return templates.TemplateResponse("profile/reset_password.html", context)
        user.hashed_password = hash_password(new_password)
        db.commit()
    finally:
        db.close()

    _PASSWORD_RESET_TOKENS.pop(token, None)
    context = _make_profile_context(
        request,
        settings,
        None,
        extras={
            "token": "",
            "valid_token": False,
            "error": None,
            "success": "Password reset complete. You can now log in.",
        },
    )
    return templates.TemplateResponse("profile/reset_password.html", context)


@profile_router.get("/profile/avatar/{user_id}")
def profile_avatar(user_id: str) -> Response:
    """Return the avatar image for a user."""
    path = _avatar_path(user_id)
    if not path.exists():
        return HTMLResponse(status_code=404, content="Avatar not found")
    return FileResponse(path, media_type="image/png")


@profile_router.post("/profile/edit-avatar", response_class=HTMLResponse)
async def profile_avatar_upload(
    request: Request,
    avatar: UploadFile = File(...),
    settings: ApiSettings = Depends(get_settings),
) -> HTMLResponse:
    """Handle avatar image upload."""
    user = _require_web_user(request, settings)
    if isinstance(user, HTMLResponse):
        return user

    raw = await avatar.read()
    if len(raw) > 5 * 1024 * 1024:
        return HTMLResponse('<p class="error-text">Avatar file exceeds 5MB limit.</p>')

    _AVATAR_DIR.mkdir(parents=True, exist_ok=True)
    _avatar_path(user.id).write_bytes(raw)
    return HTMLResponse('<p class="success-text">Avatar updated.</p>')


@profile_router.get("/profile/edit", response_class=HTMLResponse)
def profile_edit_partial(
    request: Request, settings: ApiSettings = Depends(get_settings)
) -> HTMLResponse:
    """Render the profile edit partial."""
    user = _require_web_user(request, settings)
    if isinstance(user, HTMLResponse):
        return user

    context = _make_profile_context(
        request,
        settings,
        user,
        extras={"success": None, "error": None, "avatar_url": f"/ui/profile/avatar/{user.id}"},
    )
    return templates.TemplateResponse("profile/_edit.html", context)


@profile_router.post("/profile/edit", response_class=HTMLResponse)
def profile_edit_submit(
    request: Request,
    full_name: str = Form(""),
    email: str = Form(...),
    settings: ApiSettings = Depends(get_settings),
) -> HTMLResponse:
    """Handle profile edit form submission."""
    user = _require_web_user(request, settings)
    if isinstance(user, HTMLResponse):
        return user

    db = _get_db(settings)
    try:
        db_user = db.query(User).filter(User.id == user.id).first()
        if db_user is None:
            return HTMLResponse('<p class="error-text">User not found.</p>')

        if email != db_user.email:
            existing = db.query(User).filter(User.email == email, User.id != db_user.id).first()
            if existing:
                context = _make_profile_context(
                    request,
                    settings,
                    db_user,
                    extras={"success": None, "error": "Email already in use"},
                )
                return templates.TemplateResponse("profile/_edit.html", context)

        db_user.full_name = full_name or None
        db_user.email = email
        db.commit()
        db.refresh(db_user)

        state = _load_profile_state(db, db_user.id)
        _append_activity(state, "Updated profile details.")
        _save_profile_state(db, db_user.id, state)

        context = _make_profile_context(
            request,
            settings,
            db_user,
            extras={"success": "Profile updated", "error": None},
        )
        return templates.TemplateResponse("profile/_edit.html", context)
    finally:
        db.close()


@profile_router.get("/profile/workspaces", response_class=HTMLResponse)
def workspaces_partial(
    request: Request, settings: ApiSettings = Depends(get_settings)
) -> HTMLResponse:
    """Render the workspaces partial."""
    user = _require_web_user(request, settings)
    if isinstance(user, HTMLResponse):
        return user

    db = _get_db(settings)
    try:
        workspaces, active_workspace_id = _workspace_context(db, user.id)
        context = _make_profile_context(
            request,
            settings,
            user,
            extras={"workspaces": workspaces, "active_workspace_id": active_workspace_id},
        )
        return templates.TemplateResponse("profile/_workspaces.html", context)
    finally:
        db.close()


@profile_router.post("/profile/workspaces/create", response_class=HTMLResponse)
def workspace_create(
    request: Request,
    name: str = Form(...),
    root_path: str = Form(...),
    description: str = Form(""),
    settings: ApiSettings = Depends(get_settings),
) -> HTMLResponse:
    """Handle workspace creation."""
    user = _require_web_user(request, settings)
    if isinstance(user, HTMLResponse):
        return user

    db = _get_db(settings)
    try:
        WorkspaceRepository.create(
            db,
            name=name.strip(),
            owner_id=user.id,
            root_path=root_path.strip(),
            description=description.strip() or None,
        )
        state = _load_profile_state(db, user.id)
        _append_activity(state, f"Created workspace '{name.strip()}'.")
        _append_notification(state, f"Workspace '{name.strip()}' was created.")
        _save_profile_state(db, user.id, state)
        db.commit()
        return workspaces_partial(request, settings)
    finally:
        db.close()


@profile_router.post("/profile/workspaces/switch", response_class=HTMLResponse)
def workspace_switch(
    request: Request,
    workspace_id: str = Form(...),
    settings: ApiSettings = Depends(get_settings),
) -> HTMLResponse:
    """Handle workspace switch."""
    user = _require_web_user(request, settings)
    if isinstance(user, HTMLResponse):
        return user

    db = _get_db(settings)
    try:
        workspace = WorkspaceRepository.get_by_id(db, workspace_id)
        if workspace is not None and workspace.owner_id == user.id:
            state = _load_profile_state(db, user.id)
            state["active_workspace_id"] = workspace_id
            _append_activity(state, f"Switched to workspace '{workspace.name}'.")
            _save_profile_state(db, user.id, state)
            db.commit()
        return workspaces_partial(request, settings)
    finally:
        db.close()


@profile_router.get("/profile/team", response_class=HTMLResponse)
def team_partial(request: Request, settings: ApiSettings = Depends(get_settings)) -> HTMLResponse:
    """Render the team management partial."""
    user = _require_web_user(request, settings)
    if isinstance(user, HTMLResponse):
        return user

    db = _get_db(settings)
    try:
        state = _load_profile_state(db, user.id)
        context = _make_profile_context(
            request,
            settings,
            user,
            extras={"team_members": state["team_members"]},
        )
        return templates.TemplateResponse("profile/_team.html", context)
    finally:
        db.close()


@profile_router.post("/profile/team/invite", response_class=HTMLResponse)
def team_invite(
    request: Request,
    email: str = Form(...),
    role: str = Form("viewer"),
    settings: ApiSettings = Depends(get_settings),
) -> HTMLResponse:
    """Send a team invitation."""
    user = _require_web_user(request, settings)
    if isinstance(user, HTMLResponse):
        return user

    normalized_role = role if role in _DEFAULT_ROLES else "viewer"
    db = _get_db(settings)
    try:
        state = _load_profile_state(db, user.id)
        team = state.get("team_members")
        if not isinstance(team, list):
            team = []
            state["team_members"] = team
        team.append(
            {
                "id": secrets.token_hex(4),
                "email": email.strip().lower(),
                "role": normalized_role,
                "status": "invited",
            }
        )
        _append_activity(state, f"Invited {email.strip().lower()} as {normalized_role}.")
        _append_notification(state, f"Invitation created for {email.strip().lower()}.")
        _save_profile_state(db, user.id, state)
        db.commit()
        return team_partial(request, settings)
    finally:
        db.close()


@profile_router.post("/profile/team/role", response_class=HTMLResponse)
def team_update_role(
    request: Request,
    member_id: str = Form(...),
    role: str = Form("viewer"),
    settings: ApiSettings = Depends(get_settings),
) -> HTMLResponse:
    """Update a team member's role."""
    user = _require_web_user(request, settings)
    if isinstance(user, HTMLResponse):
        return user

    normalized_role = role if role in _DEFAULT_ROLES else "viewer"
    db = _get_db(settings)
    try:
        state = _load_profile_state(db, user.id)
        team = state.get("team_members")
        if isinstance(team, list):
            for member in team:
                if isinstance(member, dict) and member.get("id") == member_id:
                    member["role"] = normalized_role
                    member["status"] = "active"
                    _append_activity(
                        state,
                        f"Updated role for {member.get('email', 'member')} to {normalized_role}.",
                    )
                    break
        _save_profile_state(db, user.id, state)
        db.commit()
        return team_partial(request, settings)
    finally:
        db.close()


@profile_router.get("/profile/shared", response_class=HTMLResponse)
def shared_partial(request: Request, settings: ApiSettings = Depends(get_settings)) -> HTMLResponse:
    """Render the shared folders partial."""
    user = _require_web_user(request, settings)
    if isinstance(user, HTMLResponse):
        return user

    db = _get_db(settings)
    try:
        state = _load_profile_state(db, user.id)
        context = _make_profile_context(
            request,
            settings,
            user,
            extras={"shared_folders": state["shared_folders"]},
        )
        return templates.TemplateResponse("profile/_shared.html", context)
    finally:
        db.close()


@profile_router.post("/profile/shared/add", response_class=HTMLResponse)
def shared_add(
    request: Request,
    folder_path: str = Form(...),
    permission: str = Form("view"),
    settings: ApiSettings = Depends(get_settings),
) -> HTMLResponse:
    """Add a shared folder."""
    user = _require_web_user(request, settings)
    if isinstance(user, HTMLResponse):
        return user

    normalized_permission = permission if permission in {"view", "edit", "admin"} else "view"
    db = _get_db(settings)
    try:
        state = _load_profile_state(db, user.id)
        shared = state.get("shared_folders")
        if not isinstance(shared, list):
            shared = []
            state["shared_folders"] = shared
        shared.append(
            {
                "id": secrets.token_hex(4),
                "path": folder_path.strip(),
                "permission": normalized_permission,
            }
        )
        _append_activity(
            state, f"Shared folder '{folder_path.strip()}' as {normalized_permission}."
        )
        _save_profile_state(db, user.id, state)
        db.commit()
        return shared_partial(request, settings)
    finally:
        db.close()


@profile_router.post("/profile/shared/remove", response_class=HTMLResponse)
def shared_remove(
    request: Request,
    folder_id: str = Form(...),
    settings: ApiSettings = Depends(get_settings),
) -> HTMLResponse:
    """Remove a shared folder."""
    user = _require_web_user(request, settings)
    if isinstance(user, HTMLResponse):
        return user

    db = _get_db(settings)
    try:
        state = _load_profile_state(db, user.id)
        shared = state.get("shared_folders")
        if isinstance(shared, list):
            state["shared_folders"] = [
                folder
                for folder in shared
                if not (isinstance(folder, dict) and folder.get("id") == folder_id)
            ]
            _append_activity(state, "Removed a shared folder entry.")
        _save_profile_state(db, user.id, state)
        db.commit()
        return shared_partial(request, settings)
    finally:
        db.close()


@profile_router.get("/profile/activity", response_class=HTMLResponse)
def activity_partial(
    request: Request, settings: ApiSettings = Depends(get_settings)
) -> HTMLResponse:
    """Render the activity log partial."""
    user = _require_web_user(request, settings)
    if isinstance(user, HTMLResponse):
        return user

    db = _get_db(settings)
    try:
        state = _load_profile_state(db, user.id)
        context = _make_profile_context(
            request,
            settings,
            user,
            extras={"activity_log": state["activity_log"]},
        )
        return templates.TemplateResponse("profile/_activity.html", context)
    finally:
        db.close()


@profile_router.get("/profile/notifications", response_class=HTMLResponse)
def notifications_partial(
    request: Request, settings: ApiSettings = Depends(get_settings)
) -> HTMLResponse:
    """Render the notifications partial."""
    user = _require_web_user(request, settings)
    if isinstance(user, HTMLResponse):
        return user

    db = _get_db(settings)
    try:
        state = _load_profile_state(db, user.id)
        context = _make_profile_context(
            request,
            settings,
            user,
            extras={"notifications": state["notifications"]},
        )
        return templates.TemplateResponse("profile/_notifications.html", context)
    finally:
        db.close()


@profile_router.post("/profile/notifications/mark-read", response_class=HTMLResponse)
def notification_mark_read(
    request: Request,
    notification_id: str = Form(...),
    settings: ApiSettings = Depends(get_settings),
) -> HTMLResponse:
    """Mark a notification as read."""
    user = _require_web_user(request, settings)
    if isinstance(user, HTMLResponse):
        return user

    db = _get_db(settings)
    try:
        state = _load_profile_state(db, user.id)
        notifications = state.get("notifications")
        if isinstance(notifications, list):
            for item in notifications:
                if isinstance(item, dict) and item.get("id") == notification_id:
                    item["read"] = True
                    break
        _save_profile_state(db, user.id, state)
        db.commit()
        return notifications_partial(request, settings)
    finally:
        db.close()


@profile_router.get("/profile/account-settings", response_class=HTMLResponse)
def account_settings_partial(
    request: Request, settings: ApiSettings = Depends(get_settings)
) -> HTMLResponse:
    """Render the account settings partial."""
    user = _require_web_user(request, settings)
    if isinstance(user, HTMLResponse):
        return user

    db = _get_db(settings)
    try:
        state = _load_profile_state(db, user.id)
        context = _make_profile_context(
            request,
            settings,
            user,
            extras={
                "two_factor_enabled": bool(state.get("two_factor_enabled")),
                "success": None,
                "error": None,
            },
        )
        return templates.TemplateResponse("profile/_account_settings.html", context)
    finally:
        db.close()


@profile_router.post("/profile/account-settings/password", response_class=HTMLResponse)
def account_settings_change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    settings: ApiSettings = Depends(get_settings),
) -> HTMLResponse:
    """Handle change-password form submission."""
    user = _require_web_user(request, settings)
    if isinstance(user, HTMLResponse):
        return user

    db = _get_db(settings)
    try:
        db_user = db.query(User).filter(User.id == user.id).first()
        if db_user is None:
            return HTMLResponse('<p class="error-text">User not found.</p>')
        if not verify_password(current_password, db_user.hashed_password):
            context = _make_profile_context(
                request,
                settings,
                db_user,
                extras={
                    "two_factor_enabled": False,
                    "success": None,
                    "error": "Current password is incorrect.",
                },
            )
            return templates.TemplateResponse("profile/_account_settings.html", context)
        if new_password != confirm_password:
            context = _make_profile_context(
                request,
                settings,
                db_user,
                extras={
                    "two_factor_enabled": False,
                    "success": None,
                    "error": "New password and confirmation do not match.",
                },
            )
            return templates.TemplateResponse("profile/_account_settings.html", context)
        valid, reason = validate_password(new_password, settings)
        if not valid:
            context = _make_profile_context(
                request,
                settings,
                db_user,
                extras={"two_factor_enabled": False, "success": None, "error": reason},
            )
            return templates.TemplateResponse("profile/_account_settings.html", context)

        db_user.hashed_password = hash_password(new_password)
        state = _load_profile_state(db, db_user.id)
        _append_activity(state, "Changed account password.")
        _append_notification(state, "Your password was changed.")
        _save_profile_state(db, db_user.id, state)
        db.commit()
        context = _make_profile_context(
            request,
            settings,
            db_user,
            extras={
                "two_factor_enabled": bool(state.get("two_factor_enabled")),
                "success": "Password updated.",
                "error": None,
            },
        )
        return templates.TemplateResponse("profile/_account_settings.html", context)
    finally:
        db.close()


@profile_router.post("/profile/account-settings/2fa", response_class=HTMLResponse)
def account_settings_toggle_2fa(
    request: Request,
    enabled: Optional[str] = Form(None),
    settings: ApiSettings = Depends(get_settings),
) -> HTMLResponse:
    """Toggle two-factor authentication."""
    user = _require_web_user(request, settings)
    if isinstance(user, HTMLResponse):
        return user

    toggle = enabled is not None and enabled.strip().lower() in {"1", "true", "yes", "on"}
    db = _get_db(settings)
    try:
        state = _load_profile_state(db, user.id)
        state["two_factor_enabled"] = toggle
        _append_activity(
            state, f"Set two-factor authentication to {'enabled' if toggle else 'disabled'}."
        )
        _save_profile_state(db, user.id, state)
        db.commit()
        context = _make_profile_context(
            request,
            settings,
            user,
            extras={
                "two_factor_enabled": toggle,
                "success": "Two-factor preference updated.",
                "error": None,
            },
        )
        return templates.TemplateResponse("profile/_account_settings.html", context)
    finally:
        db.close()


@profile_router.get("/profile/api-keys", response_class=HTMLResponse)
def api_keys_partial(
    request: Request, settings: ApiSettings = Depends(get_settings)
) -> HTMLResponse:
    """Render the API keys partial."""
    user = _require_web_user(request, settings)
    if isinstance(user, HTMLResponse):
        return user
    _ensure_api_key_table(settings.auth_db_path)
    db = _get_db(settings)
    try:
        keys = (
            db.query(UserApiKey)
            .filter(UserApiKey.user_id == user.id, UserApiKey.is_active.is_(True))
            .order_by(UserApiKey.created_at.desc())
            .all()
        )
        context = _make_profile_context(
            request,
            settings,
            user,
            extras={"api_keys": keys, "new_key": None},
        )
        return templates.TemplateResponse("profile/_api_keys.html", context)
    finally:
        db.close()


@profile_router.post("/profile/api-keys/generate", response_class=HTMLResponse)
def api_key_generate(
    request: Request,
    label: str = Form("default"),
    settings: ApiSettings = Depends(get_settings),
) -> HTMLResponse:
    """Generate a new API key."""
    user = _require_web_user(request, settings)
    if isinstance(user, HTMLResponse):
        return user
    _ensure_api_key_table(settings.auth_db_path)
    db = _get_db(settings)
    try:
        from file_organizer.api.api_keys import hash_api_key

        key_id = secrets.token_hex(4)
        raw_token = secrets.token_urlsafe(32)
        raw_key = f"{_API_KEY_PREFIX}_{key_id}_{raw_token}"
        hashed = hash_api_key(raw_key)

        api_key = UserApiKey(
            id=key_id,
            user_id=user.id,
            label=label.strip() or "default",
            key_prefix=f"{_API_KEY_PREFIX}_{key_id}_",
            key_hash=hashed,
        )
        db.add(api_key)

        state = _load_profile_state(db, user.id)
        _append_activity(state, f"Generated API key '{label.strip() or 'default'}'.")
        _append_notification(state, "A new API key was generated.")
        _save_profile_state(db, user.id, state)
        db.commit()

        keys = (
            db.query(UserApiKey)
            .filter(UserApiKey.user_id == user.id, UserApiKey.is_active.is_(True))
            .order_by(UserApiKey.created_at.desc())
            .all()
        )
        context = _make_profile_context(
            request,
            settings,
            user,
            extras={"api_keys": keys, "new_key": raw_key},
        )
        return templates.TemplateResponse("profile/_api_keys.html", context)
    finally:
        db.close()


@profile_router.post("/profile/api-keys/revoke", response_class=HTMLResponse)
def api_key_revoke(
    request: Request,
    key_id: str = Form(...),
    settings: ApiSettings = Depends(get_settings),
) -> HTMLResponse:
    """Revoke an API key."""
    user = _require_web_user(request, settings)
    if isinstance(user, HTMLResponse):
        return user
    _ensure_api_key_table(settings.auth_db_path)
    db = _get_db(settings)
    try:
        api_key = (
            db.query(UserApiKey)
            .filter(
                UserApiKey.id == key_id,
                UserApiKey.user_id == user.id,
                UserApiKey.is_active.is_(True),
            )
            .first()
        )
        if api_key is not None:
            api_key.is_active = False
            state = _load_profile_state(db, user.id)
            _append_activity(state, f"Revoked API key '{api_key.label}'.")
            _append_notification(state, f"API key '{api_key.label}' was revoked.")
            _save_profile_state(db, user.id, state)
            db.commit()

        keys = (
            db.query(UserApiKey)
            .filter(UserApiKey.user_id == user.id, UserApiKey.is_active.is_(True))
            .order_by(UserApiKey.created_at.desc())
            .all()
        )
        context = _make_profile_context(
            request,
            settings,
            user,
            extras={"api_keys": keys, "new_key": None},
        )
        return templates.TemplateResponse("profile/_api_keys.html", context)
    finally:
        db.close()


@profile_router.post("/profile/logout")
def logout(request: Request, settings: ApiSettings = Depends(get_settings)) -> RedirectResponse:
    """Log the current user out and redirect."""
    _ = (request, settings)
    response = RedirectResponse(url="/ui/profile", status_code=303)
    response.delete_cookie(key=_SESSION_COOKIE, path="/")
    return response
