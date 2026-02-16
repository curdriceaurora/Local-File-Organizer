"""Browser extension token and configuration utilities."""
from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Any


@dataclass(frozen=True)
class BrowserTokenRecord:
    """Issued browser token metadata."""

    token: str
    extension_id: str
    created_at: datetime
    expires_at: datetime


class BrowserExtensionManager:
    """In-memory token issuer/validator for browser extension API access."""

    def __init__(self, *, allowed_origins: list[str], token_ttl_seconds: int = 3600) -> None:
        self._allowed_origins = list(dict.fromkeys(allowed_origins))
        self._token_ttl_seconds = token_ttl_seconds
        self._tokens: dict[str, BrowserTokenRecord] = {}
        self._lock = RLock()

    def get_config(self) -> dict[str, Any]:
        """Return browser-extension bootstrap configuration."""
        return {
            "allowed_origins": list(self._allowed_origins),
            "token_ttl_seconds": self._token_ttl_seconds,
        }

    def issue_token(self, extension_id: str) -> BrowserTokenRecord:
        """Issue a short-lived token for extension clients."""
        now = datetime.now(timezone.utc)
        token = secrets.token_urlsafe(32)
        record = BrowserTokenRecord(
            token=token,
            extension_id=extension_id,
            created_at=now,
            expires_at=now + timedelta(seconds=self._token_ttl_seconds),
        )
        with self._lock:
            self._prune_expired_locked(now)
            self._tokens[token] = record
        return record

    def verify_token(self, token: str) -> bool:
        """Validate token existence and expiry state."""
        now = datetime.now(timezone.utc)
        with self._lock:
            self._prune_expired_locked(now)
            record = self._tokens.get(token)
            if record is None:
                return False
            return True

    def _prune_expired_locked(self, now: datetime) -> None:
        """Remove expired tokens while holding the manager lock."""
        expired = [token for token, record in self._tokens.items() if record.expires_at <= now]
        for token in expired:
            self._tokens.pop(token, None)
