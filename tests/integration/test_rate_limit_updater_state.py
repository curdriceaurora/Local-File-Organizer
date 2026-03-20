"""Integration tests for API rate limiter and updater state.

Covers:
  - api/rate_limit.py      — InMemoryRateLimiter, RateLimitResult, build_rate_limiter
  - updater/state.py       — UpdateState, UpdateStateStore
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from file_organizer.api.rate_limit import (
    InMemoryRateLimiter,
    RateLimitResult,
    RateLimitState,
    build_rate_limiter,
)
from file_organizer.updater.state import UpdateState, UpdateStateStore

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# RateLimitResult
# ---------------------------------------------------------------------------


class TestRateLimitResult:
    def test_created(self) -> None:
        r = RateLimitResult(allowed=True, remaining=10, reset_at=1000)
        assert r is not None

    def test_fields(self) -> None:
        r = RateLimitResult(allowed=False, remaining=0, reset_at=1234)
        assert r.allowed is False
        assert r.remaining == 0
        assert r.reset_at == 1234


# ---------------------------------------------------------------------------
# RateLimitState
# ---------------------------------------------------------------------------


class TestApiRateLimitState:
    def test_created(self) -> None:
        import time

        s = RateLimitState(count=1, reset_at=int(time.time()) + 60)
        assert s.count == 1


# ---------------------------------------------------------------------------
# InMemoryRateLimiter
# ---------------------------------------------------------------------------


class TestInMemoryRateLimiter:
    def test_created(self) -> None:
        limiter = InMemoryRateLimiter()
        assert limiter is not None

    def test_first_request_allowed(self) -> None:
        limiter = InMemoryRateLimiter()
        result = limiter.check("user1", limit=10, window_seconds=60)
        assert result.allowed is True

    def test_remaining_decrements(self) -> None:
        limiter = InMemoryRateLimiter()
        r1 = limiter.check("user1", limit=5, window_seconds=60)
        r2 = limiter.check("user1", limit=5, window_seconds=60)
        assert r2.remaining < r1.remaining

    def test_blocked_after_limit(self) -> None:
        limiter = InMemoryRateLimiter()
        for _ in range(3):
            limiter.check("user1", limit=3, window_seconds=60)
        result = limiter.check("user1", limit=3, window_seconds=60)
        assert result.allowed is False

    def test_different_keys_independent(self) -> None:
        limiter = InMemoryRateLimiter()
        for _ in range(3):
            limiter.check("userA", limit=3, window_seconds=60)
        r_a = limiter.check("userA", limit=3, window_seconds=60)
        r_b = limiter.check("userB", limit=3, window_seconds=60)
        assert r_a.allowed is False
        assert r_b.allowed is True

    def test_returns_rate_limit_result(self) -> None:
        limiter = InMemoryRateLimiter()
        result = limiter.check("key", limit=5, window_seconds=60)
        assert isinstance(result, RateLimitResult)

    def test_reset_at_positive(self) -> None:
        import time

        limiter = InMemoryRateLimiter()
        result = limiter.check("key", limit=5, window_seconds=60)
        assert result.reset_at > int(time.time())

    def test_sweep_clears_expired_entries(self) -> None:
        limiter = InMemoryRateLimiter(sweep_interval_seconds=0)
        limiter.check("key", limit=5, window_seconds=1)
        result = limiter.check("key", limit=5, window_seconds=60)
        assert result.allowed is True


# ---------------------------------------------------------------------------
# build_rate_limiter
# ---------------------------------------------------------------------------


class TestBuildRateLimiter:
    def test_no_redis_url_returns_in_memory(self) -> None:
        limiter = build_rate_limiter(None)
        assert isinstance(limiter, InMemoryRateLimiter)

    def test_empty_redis_url_returns_in_memory(self) -> None:
        limiter = build_rate_limiter("")
        assert isinstance(limiter, InMemoryRateLimiter)

    def test_invalid_redis_url_falls_back_to_in_memory(self) -> None:
        limiter = build_rate_limiter("redis://nonexistent-host:9999/0")
        assert isinstance(limiter, InMemoryRateLimiter)


# ---------------------------------------------------------------------------
# UpdateState
# ---------------------------------------------------------------------------


class TestUpdateState:
    def test_created(self) -> None:
        state = UpdateState()
        assert state is not None

    def test_last_checked_at_empty_returns_none(self) -> None:
        state = UpdateState()
        assert state.last_checked_at() is None

    def test_last_checked_at_valid_iso(self) -> None:
        ts = datetime.now(UTC).isoformat()
        state = UpdateState(last_checked=ts)
        result = state.last_checked_at()
        assert result is not None
        assert isinstance(result, datetime)

    def test_last_checked_at_invalid_returns_none(self) -> None:
        state = UpdateState(last_checked="not-a-date")
        assert state.last_checked_at() is None

    def test_due_no_interval_returns_true(self) -> None:
        state = UpdateState()
        assert state.due(0) is True

    def test_due_never_checked_returns_true(self) -> None:
        state = UpdateState()
        assert state.due(24) is True

    def test_due_recently_checked_returns_false(self) -> None:
        now = datetime.now(UTC)
        state = UpdateState(last_checked=now.isoformat())
        assert state.due(24, now=now) is False

    def test_due_old_check_returns_true(self) -> None:
        old = datetime.now(UTC) - timedelta(hours=25)
        state = UpdateState(last_checked=old.isoformat())
        assert state.due(24) is True


# ---------------------------------------------------------------------------
# UpdateStateStore
# ---------------------------------------------------------------------------


class TestUpdateStateStore:
    def test_created(self, tmp_path: Path) -> None:
        store = UpdateStateStore(state_path=tmp_path / "state.json")
        assert store is not None

    def test_state_path_property(self, tmp_path: Path) -> None:
        p = tmp_path / "state.json"
        store = UpdateStateStore(state_path=p)
        assert store.state_path == p

    def test_load_missing_returns_default(self, tmp_path: Path) -> None:
        store = UpdateStateStore(state_path=tmp_path / "missing.json")
        state = store.load()
        assert isinstance(state, UpdateState)
        assert state.last_checked == ""

    def test_save_and_load(self, tmp_path: Path) -> None:
        store = UpdateStateStore(state_path=tmp_path / "state.json")
        now_ts = datetime.now(UTC).isoformat()
        original = UpdateState(last_checked=now_ts, last_version="1.2.3")
        store.save(original)
        loaded = store.load()
        assert loaded.last_version == "1.2.3"

    def test_load_corrupt_returns_default(self, tmp_path: Path) -> None:
        p = tmp_path / "state.json"
        p.write_text("not json", encoding="utf-8")
        store = UpdateStateStore(state_path=p)
        state = store.load()
        assert state.last_checked == ""

    def test_load_non_dict_returns_default(self, tmp_path: Path) -> None:
        p = tmp_path / "state.json"
        p.write_text("[1, 2, 3]", encoding="utf-8")
        store = UpdateStateStore(state_path=p)
        state = store.load()
        assert state.last_checked == ""

    def test_record_check_saves_state(self, tmp_path: Path) -> None:
        store = UpdateStateStore(state_path=tmp_path / "state.json")
        now = datetime.now(UTC)
        state = store.record_check("2.0.0", now=now)
        assert state.last_version == "2.0.0"

    def test_record_check_persists(self, tmp_path: Path) -> None:
        store = UpdateStateStore(state_path=tmp_path / "state.json")
        store.record_check("1.5.0")
        loaded = store.load()
        assert loaded.last_version == "1.5.0"

    def test_save_creates_parent_dirs(self, tmp_path: Path) -> None:
        deep_path = tmp_path / "nested" / "dir" / "state.json"
        store = UpdateStateStore(state_path=deep_path)
        store.save(UpdateState(last_version="1.0.0"))
        assert deep_path.exists()
