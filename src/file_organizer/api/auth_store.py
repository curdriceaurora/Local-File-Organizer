"""Token storage for authentication sessions."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional, Protocol

from loguru import logger
from redis import Redis


class TokenStore(Protocol):
    """Protocol for token storage backends."""

    def store_refresh(self, jti: str, user_id: str, ttl_seconds: int) -> None:
        """Store a refresh token identifier with TTL."""
        ...

    def is_refresh_active(self, jti: str) -> bool:
        """Return True if the refresh token is active."""
        ...

    def revoke_refresh(self, jti: str) -> None:
        """Revoke a refresh token identifier."""
        ...

    def revoke_access(self, jti: str, ttl_seconds: int) -> None:
        """Mark an access token as revoked for the remaining TTL."""
        ...

    def is_access_revoked(self, jti: str) -> bool:
        """Return True if the access token has been revoked."""
        ...


class InMemoryTokenStore:
    """Simple in-memory token store for testing or local fallback."""

    def __init__(self) -> None:
        """Initialize InMemoryTokenStore with empty refresh and revoked buckets."""
        self._refresh: dict[str, float] = {}
        self._revoked: dict[str, float] = {}

    def _is_active(self, bucket: dict[str, float], jti: str) -> bool:
        expires_at = bucket.get(jti)
        if expires_at is None:
            return False
        if expires_at <= time.time():
            bucket.pop(jti, None)
            return False
        return True

    def store_refresh(self, jti: str, user_id: str, ttl_seconds: int) -> None:
        """Store a refresh token with the given TTL."""
        self._refresh[jti] = time.time() + ttl_seconds

    def is_refresh_active(self, jti: str) -> bool:
        """Return True if the refresh token is active."""
        return self._is_active(self._refresh, jti)

    def revoke_refresh(self, jti: str) -> None:
        """Revoke a refresh token by JTI."""
        self._refresh.pop(jti, None)

    def revoke_access(self, jti: str, ttl_seconds: int) -> None:
        """Mark an access token as revoked for the remaining TTL."""
        self._revoked[jti] = time.time() + ttl_seconds

    def is_access_revoked(self, jti: str) -> bool:
        """Return True if the access token has been revoked."""
        return self._is_active(self._revoked, jti)


@dataclass(frozen=True)
class RedisTokenStore:
    """Redis-backed token store for production use."""

    redis: Redis
    refresh_prefix: str = "auth:refresh:"
    revoked_prefix: str = "auth:revoked:"

    def _refresh_key(self, jti: str) -> str:
        return f"{self.refresh_prefix}{jti}"

    def _revoked_key(self, jti: str) -> str:
        return f"{self.revoked_prefix}{jti}"

    def store_refresh(self, jti: str, user_id: str, ttl_seconds: int) -> None:
        """Store a refresh token with the given TTL in Redis."""
        self.redis.setex(self._refresh_key(jti), ttl_seconds, user_id)

    def is_refresh_active(self, jti: str) -> bool:
        """Return True if the refresh token is active in Redis."""
        return self.redis.exists(self._refresh_key(jti)) == 1

    def revoke_refresh(self, jti: str) -> None:
        """Revoke a refresh token in Redis."""
        self.redis.delete(self._refresh_key(jti))

    def revoke_access(self, jti: str, ttl_seconds: int) -> None:
        """Mark an access token as revoked in Redis."""
        self.redis.setex(self._revoked_key(jti), ttl_seconds, "1")

    def is_access_revoked(self, jti: str) -> bool:
        """Return True if the access token has been revoked in Redis."""
        return self.redis.exists(self._revoked_key(jti)) == 1


def build_token_store(redis_url: Optional[str]) -> TokenStore:
    """Create a token store, preferring Redis when configured."""
    if not redis_url:
        return InMemoryTokenStore()
    try:
        client = Redis.from_url(redis_url, decode_responses=True)
        client.ping()
        return RedisTokenStore(client)
    except Exception as exc:
        logger.warning("Auth redis unavailable, using in-memory token store: {}", exc)
        return InMemoryTokenStore()
