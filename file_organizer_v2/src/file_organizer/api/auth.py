"""Authentication helpers for JWT and password hashing."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from jose import JWTError, jwt
from passlib.context import CryptContext

from file_organizer.api.config import ApiSettings

_ACCESS_TOKEN_TYPE = "access"
_REFRESH_TOKEN_TYPE = "refresh"

_PWD_CONTEXT = CryptContext(schemes=["bcrypt"], deprecated="auto")


class TokenError(Exception):
    """Raised when a JWT token is invalid."""


@dataclass(frozen=True)
class TokenBundle:
    access_token: str
    refresh_token: str
    access_jti: str
    refresh_jti: str
    access_expires_at: datetime
    refresh_expires_at: datetime


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return _PWD_CONTEXT.verify(plain_password, hashed_password)


def hash_password(password: str) -> str:
    return _PWD_CONTEXT.hash(password)


_COMMON_PASSWORDS: frozenset[str] = frozenset({
    "password", "password1", "password12", "password123",
    "passw0rd", "p@ssword", "p@ssw0rd",
    "admin", "admin123", "admin1234",
    "letmein", "welcome1", "monkey123",
    "qwerty123", "abc123456",
    "iloveyou1", "sunshine1",
})


def validate_password(password: str, settings: ApiSettings) -> tuple[bool, str]:
    """Validate password strength based on API settings."""
    if len(password) < settings.auth_password_min_length:
        return (
            False,
            f"Password must be at least {settings.auth_password_min_length} characters long",
        )
    if settings.auth_password_require_letter and not any(ch.isalpha() for ch in password):
        return False, "Password must include at least one letter"
    if settings.auth_password_require_number and not any(ch.isdigit() for ch in password):
        return False, "Password must include at least one number"
    if settings.auth_password_require_uppercase and not any(ch.isupper() for ch in password):
        return False, "Password must include at least one uppercase letter"
    if settings.auth_password_require_special and not any(
        ch in '!"#$%&\'()*+,-./:;<=>?@[\\]^_`{|}~' for ch in password
    ):
        return False, "Password must include at least one special character"
    if password.lower() in _COMMON_PASSWORDS:
        return False, "Password is too common, please choose a more unique password"
    return True, ""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _build_token(
    payload: dict[str, Any],
    token_type: str,
    expires_delta: timedelta,
    settings: ApiSettings,
) -> tuple[str, str, datetime]:
    issued_at = _now()
    expires_at = issued_at + expires_delta
    jti = str(uuid4())
    claims = {
        **payload,
        "type": token_type,
        "jti": jti,
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    token = jwt.encode(claims, settings.auth_jwt_secret.get_secret_value(), algorithm=settings.auth_jwt_algorithm)
    return token, jti, expires_at


def create_token_bundle(user_id: str, username: str, settings: ApiSettings) -> TokenBundle:
    payload = {"sub": username, "user_id": user_id}
    access_token, access_jti, access_exp = _build_token(
        payload,
        _ACCESS_TOKEN_TYPE,
        timedelta(minutes=settings.auth_access_token_minutes),
        settings,
    )
    refresh_token, refresh_jti, refresh_exp = _build_token(
        payload,
        _REFRESH_TOKEN_TYPE,
        timedelta(days=settings.auth_refresh_token_days),
        settings,
    )
    return TokenBundle(
        access_token=access_token,
        refresh_token=refresh_token,
        access_jti=access_jti,
        refresh_jti=refresh_jti,
        access_expires_at=access_exp,
        refresh_expires_at=refresh_exp,
    )


def decode_token(token: str, settings: ApiSettings) -> dict[str, Any]:
    try:
        return jwt.decode(token, settings.auth_jwt_secret.get_secret_value(), algorithms=[settings.auth_jwt_algorithm])
    except JWTError as exc:
        raise TokenError("Invalid token") from exc


def is_access_token(payload: dict[str, Any]) -> bool:
    return payload.get("type") == _ACCESS_TOKEN_TYPE


def is_refresh_token(payload: dict[str, Any]) -> bool:
    return payload.get("type") == _REFRESH_TOKEN_TYPE
