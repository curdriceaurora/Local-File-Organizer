"""Authentication endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from file_organizer.api.auth import (
    TokenError,
    create_token_bundle,
    decode_token,
    hash_password,
    is_refresh_token,
    validate_password,
    verify_password,
)
from file_organizer.api.auth_models import User
from file_organizer.api.auth_rate_limit import LoginRateLimiter
from file_organizer.api.auth_store import TokenStore
from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import (
    get_current_active_user,
    get_db,
    get_login_rate_limiter,
    get_settings,
    get_token_store,
    oauth2_scheme,
)
from file_organizer.api.models import (
    TokenRefreshRequest,
    TokenResponse,
    TokenRevokeRequest,
    UserCreateRequest,
    UserResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])

_LOCALHOSTS = {"127.0.0.1", "::1", "localhost"}


def _rate_limit_key(request: Request, username: str) -> str:
    client_host = request.client.host if request.client else "unknown"
    user_key = username.strip().lower() if username else "unknown"
    return f"{client_host}:{user_key}"


def _is_local_request(request: Request) -> bool:
    if request.client is None:
        return False
    return request.client.host in _LOCALHOSTS


def _access_ttl_seconds(settings: ApiSettings, payload: dict) -> int:
    exp = payload.get("exp")
    if not isinstance(exp, (int, float)):
        return settings.auth_access_token_minutes * 60
    now = datetime.now(UTC).timestamp()
    ttl = int(exp - now)
    return max(ttl, 0)


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register_user(
    request: UserCreateRequest,
    http_request: Request,
    db: Session = Depends(get_db),
    settings: ApiSettings = Depends(get_settings),
) -> UserResponse:
    valid, reason = validate_password(request.password, settings)
    if not valid:
        raise HTTPException(status_code=400, detail=reason)

    existing_user = db.query(User).filter(User.username == request.username).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Username already taken")

    existing_email = db.query(User).filter(User.email == request.email).first()
    if existing_email:
        raise HTTPException(status_code=400, detail="Email already registered")

    is_first_user = db.query(User).count() == 0
    is_admin = False
    if is_first_user and settings.auth_bootstrap_admin:
        if not settings.auth_bootstrap_admin_local_only or _is_local_request(http_request):
            is_admin = True
    user = User(
        username=request.username,
        email=request.email,
        hashed_password=hash_password(request.password),
        full_name=request.full_name,
        is_admin=is_admin,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
    token_store: TokenStore = Depends(get_token_store),
    settings: ApiSettings = Depends(get_settings),
    rate_limiter: LoginRateLimiter = Depends(get_login_rate_limiter),
) -> TokenResponse:
    rate_limit_key = _rate_limit_key(request, form_data.username)
    if settings.auth_login_rate_limit_enabled:
        blocked, retry_after = rate_limiter.is_blocked(rate_limit_key)
        if blocked:
            headers = {"Retry-After": str(retry_after)} if retry_after else None
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many login attempts. Try again later.",
                headers=headers,
            )

    user = db.query(User).filter(User.username == form_data.username).first()
    if user is None or not verify_password(form_data.password, user.hashed_password):
        if settings.auth_login_rate_limit_enabled:
            rate_limiter.record_failure(rate_limit_key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        if settings.auth_login_rate_limit_enabled:
            rate_limiter.record_failure(rate_limit_key)
        raise HTTPException(status_code=400, detail="Inactive user")

    if settings.auth_login_rate_limit_enabled:
        rate_limiter.reset(rate_limit_key)

    user.last_login = datetime.now(UTC)
    db.commit()

    token_bundle = create_token_bundle(user.id, user.username, settings)
    refresh_ttl = max(
        int((token_bundle.refresh_expires_at - datetime.now(UTC)).total_seconds()),
        1,
    )
    token_store.store_refresh(token_bundle.refresh_jti, user.id, refresh_ttl)
    return TokenResponse(
        access_token=token_bundle.access_token,
        refresh_token=token_bundle.refresh_token,
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh(
    request: TokenRefreshRequest,
    db: Session = Depends(get_db),
    token_store: TokenStore = Depends(get_token_store),
    settings: ApiSettings = Depends(get_settings),
) -> TokenResponse:
    try:
        payload = decode_token(request.refresh_token, settings)
    except TokenError as exc:
        raise HTTPException(status_code=401, detail="Invalid refresh token") from exc

    if not is_refresh_token(payload):
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    refresh_jti = payload.get("jti")
    if not isinstance(refresh_jti, str) or not token_store.is_refresh_active(refresh_jti):
        raise HTTPException(status_code=401, detail="Refresh token revoked")

    user_id = payload.get("user_id")
    if not isinstance(user_id, str):
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    user = db.query(User).filter(User.id == user_id).first()
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User not active")

    token_store.revoke_refresh(refresh_jti)
    token_bundle = create_token_bundle(user.id, user.username, settings)
    refresh_ttl = max(
        int((token_bundle.refresh_expires_at - datetime.now(UTC)).total_seconds()),
        1,
    )
    token_store.store_refresh(token_bundle.refresh_jti, user.id, refresh_ttl)

    return TokenResponse(
        access_token=token_bundle.access_token,
        refresh_token=token_bundle.refresh_token,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: TokenRevokeRequest,
    current_user: User = Depends(get_current_active_user),
    token: Optional[str] = Depends(oauth2_scheme),
    token_store: TokenStore = Depends(get_token_store),
    settings: ApiSettings = Depends(get_settings),
) -> None:
    if not settings.auth_enabled:
        return None

    if not token:
        raise HTTPException(status_code=401, detail="Missing access token")
    try:
        access_payload = decode_token(token, settings)
    except TokenError as exc:
        raise HTTPException(status_code=401, detail="Invalid access token") from exc

    access_jti = access_payload.get("jti")
    if isinstance(access_jti, str):
        ttl = _access_ttl_seconds(settings, access_payload)
        if ttl > 0:
            token_store.revoke_access(access_jti, ttl)

    try:
        refresh_payload = decode_token(request.refresh_token, settings)
    except TokenError as exc:
        raise HTTPException(status_code=401, detail="Invalid refresh token") from exc

    if not is_refresh_token(refresh_payload):
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    refresh_jti = refresh_payload.get("jti")
    refresh_user = refresh_payload.get("user_id")
    if not isinstance(refresh_jti, str) or refresh_user != current_user.id:
        raise HTTPException(status_code=401, detail="Refresh token invalid for user")

    token_store.revoke_refresh(refresh_jti)
    return None


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_active_user)) -> UserResponse:
    return current_user
