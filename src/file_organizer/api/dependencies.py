"""Dependency providers for the API layer."""

from __future__ import annotations

import os
from collections.abc import Generator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import lru_cache

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from file_organizer.api.api_keys import api_key_identifier
from file_organizer.api.auth import decode_token, is_access_token
from file_organizer.api.auth_db import create_session
from file_organizer.api.auth_models import User
from file_organizer.api.auth_rate_limit import LoginRateLimiter, build_login_rate_limiter
from file_organizer.api.auth_store import TokenStore, build_token_store
from file_organizer.api.config import ApiSettings, load_settings
from file_organizer.config.manager import ConfigManager


@lru_cache
def get_settings() -> ApiSettings:
    """Return API settings for request handlers."""
    return load_settings()


@lru_cache
def get_config_manager() -> ConfigManager:
    """Return a config manager, optionally overridden by FO_CONFIG_DIR."""
    config_dir = os.environ.get("FO_CONFIG_DIR")
    return ConfigManager(config_dir=config_dir)


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


@dataclass(frozen=True)
class AnonymousUser:
    """Anonymous user identity used when auth is disabled."""

    id: str = "anonymous"
    username: str = "anonymous"
    email: str = "anonymous@example.com"
    full_name: str | None = None
    is_active: bool = True
    is_admin: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_login: datetime | None = None


@dataclass(frozen=True)
class ApiKeyIdentity:
    """API key-based user identity."""

    id: str
    username: str
    email: str = "api-key@example.com"
    full_name: str | None = None
    is_active: bool = True
    is_admin: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_login: datetime | None = None
    auth_type: str = "api_key"


UserLike = User | AnonymousUser | ApiKeyIdentity


def get_db(settings: ApiSettings = Depends(get_settings)) -> Generator[Session, None, None]:
    """Yield a database session for auth data."""
    session = create_session(settings.auth_db_path)
    try:
        yield session
    finally:
        session.close()


@lru_cache
def _token_store_cached(redis_url: str | None) -> TokenStore:
    return build_token_store(redis_url)


def get_token_store(settings: ApiSettings = Depends(get_settings)) -> TokenStore:
    """Return the token store for the current settings."""
    return _token_store_cached(settings.auth_redis_url)


@lru_cache
def _login_rate_limiter_cached(
    redis_url: str | None,
    max_attempts: int,
    window_seconds: int,
) -> LoginRateLimiter:
    return build_login_rate_limiter(redis_url, max_attempts, window_seconds)


def get_login_rate_limiter(settings: ApiSettings = Depends(get_settings)) -> LoginRateLimiter:
    """Return the login rate limiter for the current settings."""
    return _login_rate_limiter_cached(
        settings.auth_redis_url,
        settings.auth_login_max_attempts,
        settings.auth_login_window_seconds,
    )


def get_current_user(
    request: Request,
    token: str | None = Depends(oauth2_scheme),
    settings: ApiSettings = Depends(get_settings),
    db: Session = Depends(get_db),
    token_store: TokenStore = Depends(get_token_store),
) -> UserLike:
    """Resolve and return the current authenticated user."""
    if not settings.auth_enabled:
        return AnonymousUser()
    if not token:
        api_key = request.headers.get(settings.api_key_header)
        if settings.api_key_enabled and api_key:
            key_id = getattr(request.state, "api_key_identifier", None)
            if not key_id:
                key_id = api_key_identifier(api_key, settings.api_key_hashes)
            if key_id:
                return ApiKeyIdentity(
                    id=f"api-key:{key_id}",
                    username=f"api-key-{key_id}",
                    is_admin=settings.api_key_admin,
                )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_token(token, settings)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    if not is_access_token(payload):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    jti = payload.get("jti")
    if isinstance(jti, str) and token_store.is_access_revoked(jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("user_id")
    if not isinstance(user_id, str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def get_current_active_user(
    user: UserLike = Depends(get_current_user),
    settings: ApiSettings = Depends(get_settings),
) -> UserLike:
    """Return the current user, raising 400 if inactive."""
    if not settings.auth_enabled:
        return user
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return user


def require_admin_user(
    user: UserLike = Depends(get_current_active_user),
    settings: ApiSettings = Depends(get_settings),
) -> UserLike:
    """Return the current user, raising 403 if not an admin."""
    if not settings.auth_enabled:
        return user
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return user
