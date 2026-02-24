"""In-memory query result cache with TTL-based expiration.

This module provides a thread-safe, LRU-style cache for query results.  It
supports per-table invalidation so that write operations can selectively
clear stale entries without flushing the entire cache.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class CachedResult:
    """A cached query result with metadata.

    Attributes:
        data: The cached result data.
        timestamp: Unix timestamp when the entry was created.
        hit_count: Number of times this entry has been served from cache.
        tables: Set of table names this result depends on (used for
            targeted invalidation).
    """

    data: Any
    timestamp: float
    hit_count: int = 0
    tables: set[str] = field(default_factory=set)


class QueryCache:
    """Thread-safe LRU query cache with time-to-live expiration.

    Stores query results keyed by a caller-provided hash string.  Entries
    expire after ``ttl_seconds`` and the cache evicts least-recently-used
    entries once ``max_size`` is reached.

    Args:
        max_size: Maximum number of entries the cache may hold.
        ttl_seconds: Time-to-live for each entry in seconds.

    Example:
        >>> cache = QueryCache(max_size=500, ttl_seconds=30)
        >>> cache.put("abc123", [{"id": 1}], tables={"users"})
        >>> result = cache.get("abc123")
        >>> if result is not None:
        ...     print(result.data)
        >>> cache.invalidate("users")
    """

    def __init__(self, max_size: int = 1000, ttl_seconds: float = 60.0) -> None:
        """Create a query cache with the given capacity and TTL."""
        if max_size < 1:
            raise ValueError("max_size must be >= 1")
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be > 0")

        self._max_size = max_size
        self._ttl = ttl_seconds
        self._cache: OrderedDict[str, CachedResult] = OrderedDict()
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

        logger.info("QueryCache initialised: max_size=%d, ttl=%.1fs", max_size, ttl_seconds)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, query_hash: str) -> CachedResult | None:
        """Retrieve a cached result by query hash.

        Returns ``None`` if the entry does not exist or has expired.
        Accessing an entry promotes it to the most-recently-used position.

        Args:
            query_hash: Unique hash identifying the query.

        Returns:
            The ``CachedResult`` if found and valid, otherwise ``None``.
        """
        with self._lock:
            entry = self._cache.get(query_hash)
            if entry is None:
                self._misses += 1
                return None

            # Check TTL.
            if self._is_expired(entry):
                del self._cache[query_hash]
                self._misses += 1
                logger.debug("Cache miss (expired): %s", query_hash)
                return None

            # Promote to most-recently-used.
            self._cache.move_to_end(query_hash)
            entry.hit_count += 1
            self._hits += 1
            logger.debug("Cache hit: %s (hits=%d)", query_hash, entry.hit_count)
            return entry

    def put(
        self,
        query_hash: str,
        result: Any,
        *,
        tables: set[str] | None = None,
    ) -> None:
        """Store a query result in the cache.

        If the cache is at capacity the least-recently-used entry is evicted.

        Args:
            query_hash: Unique hash identifying the query.
            result: The data to cache.
            tables: Optional set of table names this result depends on,
                enabling targeted invalidation via :meth:`invalidate`.
        """
        with self._lock:
            # If key already exists, remove it so we can re-insert at end.
            if query_hash in self._cache:
                del self._cache[query_hash]

            # Evict LRU entries if at capacity.
            while len(self._cache) >= self._max_size:
                evicted_key, _ = self._cache.popitem(last=False)
                logger.debug("Evicted LRU entry: %s", evicted_key)

            self._cache[query_hash] = CachedResult(
                data=result,
                timestamp=time.time(),
                hit_count=0,
                tables=tables or set(),
            )
            logger.debug("Cached result: %s (tables=%s)", query_hash, tables)

    def invalidate(self, table_name: str) -> int:
        """Invalidate all cached entries that depend on a given table.

        This should be called after write operations (INSERT, UPDATE, DELETE)
        to ensure stale data is not served.

        Args:
            table_name: The table whose dependent cache entries should be
                removed.

        Returns:
            Number of entries invalidated.
        """
        with self._lock:
            to_remove = [key for key, entry in self._cache.items() if table_name in entry.tables]
            for key in to_remove:
                del self._cache[key]

        if to_remove:
            logger.info(
                "Invalidated %d entries for table '%s'",
                len(to_remove),
                table_name,
            )
        return len(to_remove)

    def clear(self) -> None:
        """Remove all entries from the cache."""
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            self._hits = 0
            self._misses = 0
        logger.info("Cache cleared: %d entries removed", count)

    @property
    def size(self) -> int:
        """Return the current number of entries in the cache."""
        with self._lock:
            return len(self._cache)

    @property
    def hit_rate(self) -> float:
        """Return the cache hit rate as a float between 0.0 and 1.0.

        Returns 0.0 if no lookups have been performed.
        """
        with self._lock:
            total = self._hits + self._misses
            if total == 0:
                return 0.0
            return self._hits / total

    # ------------------------------------------------------------------
    # Static helpers
    # ------------------------------------------------------------------

    @staticmethod
    def make_hash(query: str, params: tuple[object, ...] = ()) -> str:
        """Create a deterministic hash for a query + parameters.

        This is a convenience method so callers don't have to invent their
        own hashing scheme.

        Args:
            query: The SQL query string.
            params: Bind parameters for the query.

        Returns:
            A hex-encoded SHA-256 hash string.
        """
        content = f"{query}|{params!r}"
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _is_expired(self, entry: CachedResult) -> bool:
        """Check whether *entry* has exceeded its TTL."""
        return (time.time() - entry.timestamp) > self._ttl
