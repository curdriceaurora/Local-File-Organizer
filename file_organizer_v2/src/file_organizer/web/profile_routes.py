"""Web UI routes for user profile, authentication, and API key management."""
from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String
from sqlalchemy.orm import Session

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
from file_organizer.web._helpers import base_context, templates

profile_router = APIRouter(tags=["web"])

_SESSION_COOKIE = "fo_session"


# ---------------------------------------------------------------------------
# Per-user API key model (stored in the same auth DB)
# ---------------------------------------------------------------------------

_API_KEY_PREFIX = "fo"


class UserApiKey(Base):
    """Per-user API key stored in the auth database."""

    __tablename__ = "user_api_keys"

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    label = Column(String, nullable=False)
    key_prefix = Column(String, nullable=False)
    key_hash = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


def _ensure_api_key_table(db_path: str) -> None:
    """Ensure the user_api_keys table exists."""
    from file_organizer.api.auth_db import get_engine

    engine = get_engine(db_path)
    UserApiKey.__table__.create(engine, checkfirst=True)


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------


def get_current_web_user(request: Request, settings: ApiSettings) -> Optional[User]:
    """Read the session cookie and return the authenticated User, or None."""
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
        user = db.query(User).filter(User.id == user_id, User.is_active.is_(True)).first()
    finally:
        db.close()
    return user


def _get_db(settings: ApiSettings) -> Session:
    """Create a new database session."""
    return create_session(settings.auth_db_path)


# ---------------------------------------------------------------------------
# Profile page (auth-aware)
# ---------------------------------------------------------------------------


@profile_router.get("/profile", response_class=HTMLResponse)
def profile_page(request: Request, settings: ApiSettings = Depends(get_settings)) -> HTMLResponse:
    """Main profile page - shows login if unauthenticated, profile if authenticated."""
    user = get_current_web_user(request, settings)
    context = base_context(
        request,
        settings,
        active="profile",
        title="Profile",
        extras={"user": user, "auth_enabled": settings.auth_enabled},
    )
    return templates.TemplateResponse("profile/index.html", context)


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------


@profile_router.get("/profile/login", response_class=HTMLResponse)
def login_form(request: Request, settings: ApiSettings = Depends(get_settings)) -> HTMLResponse:
    """Render the login form partial."""
    context = base_context(
        request,
        settings,
        active="profile",
        title="Login",
        extras={"error": None},
    )
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
        user = db.query(User).filter(User.username == username).first()
        if user is None or not verify_password(password, user.hashed_password):
            context = base_context(
                request,
                settings,
                active="profile",
                title="Login",
                extras={"error": "Incorrect username or password"},
            )
            return templates.TemplateResponse("profile/login.html", context)

        if not user.is_active:
            context = base_context(
                request,
                settings,
                active="profile",
                title="Login",
                extras={"error": "Account is inactive"},
            )
            return templates.TemplateResponse("profile/login.html", context)

        user.last_login = datetime.now(timezone.utc)
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


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


@profile_router.get("/profile/register", response_class=HTMLResponse)
def register_form(request: Request, settings: ApiSettings = Depends(get_settings)) -> HTMLResponse:
    """Render the registration form partial."""
    context = base_context(
        request,
        settings,
        active="profile",
        title="Register",
        extras={"error": None},
    )
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
            context = base_context(
                request,
                settings,
                active="profile",
                title="Register",
                extras={"error": reason},
            )
            return templates.TemplateResponse("profile/register.html", context)

        if db.query(User).filter(User.username == username).first():
            context = base_context(
                request,
                settings,
                active="profile",
                title="Register",
                extras={"error": "Username already taken"},
            )
            return templates.TemplateResponse("profile/register.html", context)

        if db.query(User).filter(User.email == email).first():
            context = base_context(
                request,
                settings,
                active="profile",
                title="Register",
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


# ---------------------------------------------------------------------------
# Profile edit
# ---------------------------------------------------------------------------


@profile_router.get("/profile/edit", response_class=HTMLResponse)
def profile_edit_partial(
    request: Request,
    settings: ApiSettings = Depends(get_settings),
) -> HTMLResponse:
    """Render the profile edit partial (HTMX)."""
    user = get_current_web_user(request, settings)
    if user is None:
        return HTMLResponse('<p class="error-text">Not authenticated.</p>')
    context = base_context(
        request,
        settings,
        active="profile",
        title="Edit Profile",
        extras={"user": user, "success": None, "error": None},
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
    user = get_current_web_user(request, settings)
    if user is None:
        return HTMLResponse('<p class="error-text">Not authenticated.</p>')
    db = _get_db(settings)
    try:
        db_user = db.query(User).filter(User.id == user.id).first()
        if db_user is None:
            return HTMLResponse('<p class="error-text">User not found.</p>')

        # Check email uniqueness if changed
        if email != db_user.email:
            existing = db.query(User).filter(User.email == email, User.id != db_user.id).first()
            if existing:
                context = base_context(
                    request,
                    settings,
                    active="profile",
                    title="Edit Profile",
                    extras={"user": db_user, "success": None, "error": "Email already in use"},
                )
                return templates.TemplateResponse("profile/_edit.html", context)

        db_user.full_name = full_name or None
        db_user.email = email
        db.commit()
        db.refresh(db_user)

        context = base_context(
            request,
            settings,
            active="profile",
            title="Edit Profile",
            extras={"user": db_user, "success": "Profile updated", "error": None},
        )
        return templates.TemplateResponse("profile/_edit.html", context)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# API key management
# ---------------------------------------------------------------------------


@profile_router.get("/profile/api-keys", response_class=HTMLResponse)
def api_keys_partial(
    request: Request,
    settings: ApiSettings = Depends(get_settings),
) -> HTMLResponse:
    """Render the API key management partial (HTMX)."""
    user = get_current_web_user(request, settings)
    if user is None:
        return HTMLResponse('<p class="error-text">Not authenticated.</p>')
    _ensure_api_key_table(settings.auth_db_path)
    db = _get_db(settings)
    try:
        keys = (
            db.query(UserApiKey)
            .filter(UserApiKey.user_id == user.id, UserApiKey.is_active.is_(True))
            .order_by(UserApiKey.created_at.desc())
            .all()
        )
        context = base_context(
            request,
            settings,
            active="profile",
            title="API Keys",
            extras={"user": user, "api_keys": keys, "new_key": None},
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
    """Generate a new API key for the current user."""
    user = get_current_web_user(request, settings)
    if user is None:
        return HTMLResponse('<p class="error-text">Not authenticated.</p>')
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
            label=label,
            key_prefix=f"{_API_KEY_PREFIX}_{key_id}_",
            key_hash=hashed,
        )
        db.add(api_key)
        db.commit()

        keys = (
            db.query(UserApiKey)
            .filter(UserApiKey.user_id == user.id, UserApiKey.is_active.is_(True))
            .order_by(UserApiKey.created_at.desc())
            .all()
        )
        context = base_context(
            request,
            settings,
            active="profile",
            title="API Keys",
            extras={"user": user, "api_keys": keys, "new_key": raw_key},
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
    user = get_current_web_user(request, settings)
    if user is None:
        return HTMLResponse('<p class="error-text">Not authenticated.</p>')
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
            db.commit()

        keys = (
            db.query(UserApiKey)
            .filter(UserApiKey.user_id == user.id, UserApiKey.is_active.is_(True))
            .order_by(UserApiKey.created_at.desc())
            .all()
        )
        context = base_context(
            request,
            settings,
            active="profile",
            title="API Keys",
            extras={"user": user, "api_keys": keys, "new_key": None},
        )
        return templates.TemplateResponse("profile/_api_keys.html", context)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------


@profile_router.post("/profile/logout")
def logout(request: Request, settings: ApiSettings = Depends(get_settings)) -> RedirectResponse:
    """Clear session cookie and redirect to profile page."""
    response = RedirectResponse(url="/ui/profile", status_code=303)
    response.delete_cookie(key=_SESSION_COOKIE, path="/")
    return response
