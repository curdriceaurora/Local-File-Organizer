"""
Tests for QueryCache.

Tests verify caching behaviour, TTL expiration, LRU eviction, table-based
invalidation, and thread safety.
"""

from __future__ import annotations

import threading
import time

import pytest

from file_organizer.optimization.query_cache import CachedResult, QueryCache

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def cache() -> QueryCache:
    """Create a cache with sensible test defaults."""
    return QueryCache(max_size=10, ttl_seconds=5.0)


@pytest.fixture()
def small_cache() -> QueryCache:
    """Create a tiny cache for eviction testing."""
    return QueryCache(max_size=3, ttl_seconds=60.0)


# ---------------------------------------------------------------------------
# Tests — Basic Get / Put
# ---------------------------------------------------------------------------


class TestBasicOperations:
    """Tests for get() and put()."""

    def test_put_and_get(self, cache: QueryCache) -> None:
        """A stored result can be retrieved."""
        cache.put("q1", [1, 2, 3])
        result = cache.get("q1")
        assert result is not None
        assert result.data == [1, 2, 3]

    def test_get_nonexistent_returns_none(self, cache: QueryCache) -> None:
        """Getting a key that was never stored returns None."""
        assert cache.get("missing") is None

    def test_hit_count_increments(self, cache: QueryCache) -> None:
        """Each successful get() increments hit_count."""
        cache.put("q1", "data")
        cache.get("q1")
        cache.get("q1")
        result = cache.get("q1")
        assert result is not None
        assert result.hit_count == 3

    def test_put_overwrites_existing(self, cache: QueryCache) -> None:
        """Storing with the same key replaces the old entry."""
        cache.put("q1", "old")
        cache.put("q1", "new")
        result = cache.get("q1")
        assert result is not None
        assert result.data == "new"
        assert result.hit_count == 1  # 1 from the get() call above.

    def test_size_property(self, cache: QueryCache) -> None:
        """size reflects the number of cached entries."""
        assert cache.size == 0
        cache.put("a", 1)
        cache.put("b", 2)
        assert cache.size == 2


# ---------------------------------------------------------------------------
# Tests — TTL Expiration
# ---------------------------------------------------------------------------


class TestTTLExpiration:
    """Tests for time-to-live based expiry."""

    def test_expired_entry_returns_none(self) -> None:
        """Entries past their TTL are not returned."""
        short_cache = QueryCache(max_size=10, ttl_seconds=0.1)
        short_cache.put("q1", "data")
        time.sleep(0.2)
        assert short_cache.get("q1") is None

    def test_not_yet_expired(self) -> None:
        """Entries within TTL are still returned."""
        cache = QueryCache(max_size=10, ttl_seconds=10.0)
        cache.put("q1", "data")
        result = cache.get("q1")
        assert result is not None
        assert result.data == "data"

    def test_expired_entry_is_removed(self) -> None:
        """Expired entries are removed on access."""
        short_cache = QueryCache(max_size=10, ttl_seconds=0.1)
        short_cache.put("q1", "data")
        assert short_cache.size == 1
        time.sleep(0.2)
        short_cache.get("q1")  # Should remove expired entry.
        assert short_cache.size == 0


# ---------------------------------------------------------------------------
# Tests — LRU Eviction
# ---------------------------------------------------------------------------


class TestLRUEviction:
    """Tests for least-recently-used eviction."""

    def test_evicts_lru_when_full(self, small_cache: QueryCache) -> None:
        """Oldest entry is evicted when max_size is reached."""
        small_cache.put("a", 1)
        small_cache.put("b", 2)
        small_cache.put("c", 3)
        # Cache is full (size=3). Adding a 4th should evict "a".
        small_cache.put("d", 4)
        assert small_cache.get("a") is None
        assert small_cache.get("d") is not None
        assert small_cache.size == 3

    def test_access_promotes_entry(self, small_cache: QueryCache) -> None:
        """Accessing an entry makes it most-recently-used."""
        small_cache.put("a", 1)
        small_cache.put("b", 2)
        small_cache.put("c", 3)
        # Access "a" to promote it.
        small_cache.get("a")
        # Now "b" is the LRU entry. Adding "d" should evict "b".
        small_cache.put("d", 4)
        assert small_cache.get("b") is None
        assert small_cache.get("a") is not None


# ---------------------------------------------------------------------------
# Tests — Table Invalidation
# ---------------------------------------------------------------------------


class TestInvalidation:
    """Tests for invalidate() and clear()."""

    def test_invalidate_removes_matching(self, cache: QueryCache) -> None:
        """Entries tagged with a table are removed on invalidation."""
        cache.put("q1", "data1", tables={"users"})
        cache.put("q2", "data2", tables={"users", "orders"})
        cache.put("q3", "data3", tables={"orders"})

        removed = cache.invalidate("users")
        assert removed == 2
        assert cache.get("q1") is None
        assert cache.get("q2") is None
        assert cache.get("q3") is not None

    def test_invalidate_nonexistent_table(self, cache: QueryCache) -> None:
        """Invalidating a table with no entries returns 0."""
        cache.put("q1", "data", tables={"users"})
        removed = cache.invalidate("nonexistent")
        assert removed == 0
        assert cache.size == 1

    def test_clear_removes_all(self, cache: QueryCache) -> None:
        """clear() empties the entire cache."""
        cache.put("a", 1)
        cache.put("b", 2)
        cache.put("c", 3)
        cache.clear()
        assert cache.size == 0
        assert cache.get("a") is None


# ---------------------------------------------------------------------------
# Tests — Hit Rate
# ---------------------------------------------------------------------------


class TestHitRate:
    """Tests for hit_rate property."""

    def test_no_lookups_returns_zero(self, cache: QueryCache) -> None:
        """Hit rate is 0.0 when no lookups have been made."""
        assert cache.hit_rate == 0.0

    def test_all_hits(self, cache: QueryCache) -> None:
        """Hit rate is 1.0 when all lookups are hits."""
        cache.put("q1", "data")
        cache.get("q1")
        cache.get("q1")
        assert cache.hit_rate == 1.0

    def test_mixed_hits_misses(self, cache: QueryCache) -> None:
        """Hit rate reflects the ratio of hits to total lookups."""
        cache.put("q1", "data")
        cache.get("q1")  # hit
        cache.get("miss")  # miss
        assert 0.4 < cache.hit_rate < 0.6  # ~0.5


# ---------------------------------------------------------------------------
# Tests — make_hash
# ---------------------------------------------------------------------------


class TestMakeHash:
    """Tests for the static make_hash() helper."""

    def test_deterministic(self) -> None:
        """Same input always produces the same hash."""
        h1 = QueryCache.make_hash("SELECT 1", (42,))
        h2 = QueryCache.make_hash("SELECT 1", (42,))
        assert h1 == h2

    def test_different_queries_different_hash(self) -> None:
        """Different queries produce different hashes."""
        h1 = QueryCache.make_hash("SELECT 1")
        h2 = QueryCache.make_hash("SELECT 2")
        assert h1 != h2

    def test_different_params_different_hash(self) -> None:
        """Same query with different params produces different hashes."""
        h1 = QueryCache.make_hash("SELECT ?", (1,))
        h2 = QueryCache.make_hash("SELECT ?", (2,))
        assert h1 != h2

    def test_hash_is_hex_string(self) -> None:
        """Hash output is a hex-encoded string."""
        h = QueryCache.make_hash("SELECT 1")
        assert isinstance(h, str)
        assert len(h) == 64  # SHA-256 hex digest.
        int(h, 16)  # Should not raise.


# ---------------------------------------------------------------------------
# Tests — Thread Safety
# ---------------------------------------------------------------------------


class TestCacheThreadSafety:
    """Tests for concurrent access."""

    def test_concurrent_puts_and_gets(self) -> None:
        """Multiple threads can put and get without errors."""
        cache = QueryCache(max_size=100, ttl_seconds=10.0)
        errors: list[str] = []

        def writer(tid: int) -> None:
            try:
                for i in range(20):
                    cache.put(f"t{tid}-q{i}", f"data-{tid}-{i}")
            except Exception as exc:
                errors.append(str(exc))

        def reader(tid: int) -> None:
            try:
                for i in range(20):
                    cache.get(f"t{tid}-q{i}")
            except Exception as exc:
                errors.append(str(exc))

        threads: list[threading.Thread] = []
        for tid in range(5):
            threads.append(threading.Thread(target=writer, args=(tid,)))
            threads.append(threading.Thread(target=reader, args=(tid,)))

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert errors == []


# ---------------------------------------------------------------------------
# Tests — Validation
# ---------------------------------------------------------------------------


class TestValidation:
    """Tests for constructor validation."""

    def test_invalid_max_size(self) -> None:
        """max_size < 1 raises ValueError."""
        with pytest.raises(ValueError, match="max_size"):
            QueryCache(max_size=0)

    def test_invalid_ttl(self) -> None:
        """ttl_seconds <= 0 raises ValueError."""
        with pytest.raises(ValueError, match="ttl_seconds"):
            QueryCache(ttl_seconds=0)

    def test_cached_result_fields(self) -> None:
        """CachedResult dataclass fields are accessible."""
        cr = CachedResult(data=[1], timestamp=1000.0, hit_count=5, tables={"t"})
        assert cr.data == [1]
        assert cr.timestamp == 1000.0
        assert cr.hit_count == 5
        assert cr.tables == {"t"}
