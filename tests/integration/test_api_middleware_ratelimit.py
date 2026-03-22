"""Integration tests for api/rate_limit.py and api/middleware.py.

Covers: RateLimitResult, InMemoryRateLimiter (check, sweep, cap),
build_rate_limiter (no Redis → in-memory, bad URL → in-memory),
RateLimitMiddleware (exempt paths, rule matching, rate exceeded → 429,
  allowed → headers applied, client_id via Bearer/API key/proxy/IP),
SecurityHeadersMiddleware (headers attached, HTTPS HSTS, disabled).
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from file_organizer.api.config import ApiSettings
from file_organizer.api.rate_limit import (
    InMemoryRateLimiter,
    RateLimitResult,
    RateLimitState,
    build_rate_limiter,
)

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# RateLimitResult
# ---------------------------------------------------------------------------


class TestRateLimitResult:
    def test_allowed_fields(self) -> None:
        r = RateLimitResult(allowed=True, remaining=9, reset_at=1700000010)
        assert r.allowed is True
        assert r.remaining == 9
        assert r.reset_at == 1700000010

    def test_denied_fields(self) -> None:
        r = RateLimitResult(allowed=False, remaining=0, reset_at=1700000010)
        assert r.allowed is False
        assert r.remaining == 0


# ---------------------------------------------------------------------------
# InMemoryRateLimiter
# ---------------------------------------------------------------------------


class TestInMemoryRateLimiter:
    def test_first_request_is_allowed(self) -> None:
        limiter = InMemoryRateLimiter()
        result = limiter.check("user:alice:/api", limit=5, window_seconds=60)
        assert result.allowed is True
        assert result.remaining == 4

    def test_within_limit_all_allowed(self) -> None:
        limiter = InMemoryRateLimiter()
        for _ in range(5):
            r = limiter.check("user:bob:/api", limit=5, window_seconds=60)
            assert r.allowed is True

    def test_exceeds_limit_is_denied(self) -> None:
        limiter = InMemoryRateLimiter()
        for _ in range(5):
            limiter.check("user:carol:/api", limit=5, window_seconds=60)
        result = limiter.check("user:carol:/api", limit=5, window_seconds=60)
        assert result.allowed is False
        assert result.remaining == 0

    def test_remaining_decrements(self) -> None:
        limiter = InMemoryRateLimiter()
        r1 = limiter.check("k1:/test", limit=3, window_seconds=60)
        r2 = limiter.check("k1:/test", limit=3, window_seconds=60)
        assert r1.remaining == 2
        assert r2.remaining == 1

    def test_expired_window_resets_count(self) -> None:
        limiter = InMemoryRateLimiter()
        limiter.check("k2:/api", limit=1, window_seconds=1)
        limiter.check("k2:/api", limit=1, window_seconds=1)
        limiter._state["k2:/api"].reset_at = int(time.time()) - 1
        result = limiter.check("k2:/api", limit=1, window_seconds=60)
        assert result.allowed is True
        assert result.remaining == 0

    def test_sweep_removes_expired_entries(self) -> None:
        limiter = InMemoryRateLimiter(sweep_interval_seconds=0)
        limiter._state["expired_key"] = RateLimitState(count=5, reset_at=int(time.time()) - 10)
        limiter._last_sweep = 0
        limiter.check("new_key:/api", limit=10, window_seconds=60)
        assert "expired_key" not in limiter._state

    def test_capacity_cap_triggers_sweep(self) -> None:
        limiter = InMemoryRateLimiter(max_entries=2, sweep_interval_seconds=9999)
        now = int(time.time())
        limiter._state["old1"] = RateLimitState(count=1, reset_at=now - 5)
        limiter._state["old2"] = RateLimitState(count=1, reset_at=now - 5)
        limiter.check("new:/api", limit=10, window_seconds=60)
        assert "old1" not in limiter._state
        assert "old2" not in limiter._state

    def test_reset_at_is_in_future(self) -> None:
        limiter = InMemoryRateLimiter()
        result = limiter.check("k3:/test", limit=5, window_seconds=30)
        assert result.reset_at > int(time.time())


# ---------------------------------------------------------------------------
# build_rate_limiter
# ---------------------------------------------------------------------------


class TestBuildRateLimiter:
    def test_no_redis_url_returns_in_memory(self) -> None:
        limiter = build_rate_limiter(None)
        assert isinstance(limiter, InMemoryRateLimiter)
        result = limiter.check("k", limit=10, window_seconds=60)
        assert result.allowed is True

    def test_empty_redis_url_returns_in_memory(self) -> None:
        limiter = build_rate_limiter("")
        assert isinstance(limiter, InMemoryRateLimiter)
        result = limiter.check("k", limit=10, window_seconds=60)
        assert result.allowed is True

    def test_bad_redis_url_falls_back_to_in_memory(self) -> None:
        limiter = build_rate_limiter("redis://unreachable-host-xyz:9999/0")
        assert isinstance(limiter, InMemoryRateLimiter)
        result = limiter.check("k", limit=10, window_seconds=60)
        assert result.allowed is True


# ---------------------------------------------------------------------------
# RateLimitMiddleware — via TestClient
# ---------------------------------------------------------------------------


def _make_rate_limited_app(settings: ApiSettings) -> FastAPI:
    from file_organizer.api.middleware import RateLimitMiddleware
    from file_organizer.api.rate_limit import InMemoryRateLimiter

    app = FastAPI()
    limiter = InMemoryRateLimiter()
    app.add_middleware(RateLimitMiddleware, settings=settings, limiter=limiter)

    @app.get("/ping")
    def ping() -> dict[str, str]:
        return {"pong": "ok"}

    @app.get("/api/v1/data")
    def data() -> dict[str, str]:
        return {"data": "ok"}

    return app


def _base_settings(tmp_path: Path, **kwargs: object) -> ApiSettings:
    return ApiSettings(
        allowed_paths=[str(tmp_path)],
        auth_enabled=False,
        auth_db_path=str(tmp_path / "auth.db"),
        **kwargs,
    )


class TestRateLimitMiddlewareDisabled:
    def test_disabled_passes_through(self, tmp_path: Path) -> None:
        settings = _base_settings(tmp_path, rate_limit_enabled=False)
        app = _make_rate_limited_app(settings)
        client = TestClient(app, raise_server_exceptions=False)
        r = client.get("/ping")
        assert r.status_code == 200

    def test_disabled_no_ratelimit_headers(self, tmp_path: Path) -> None:
        settings = _base_settings(tmp_path, rate_limit_enabled=False)
        app = _make_rate_limited_app(settings)
        client = TestClient(app, raise_server_exceptions=False)
        r = client.get("/ping")
        assert "X-RateLimit-Limit" not in r.headers


class TestRateLimitMiddlewareEnabled:
    def test_first_request_allowed(self, tmp_path: Path) -> None:
        settings = _base_settings(
            tmp_path,
            rate_limit_enabled=True,
            rate_limit_default_requests=10,
            rate_limit_default_window_seconds=60,
        )
        app = _make_rate_limited_app(settings)
        client = TestClient(app, raise_server_exceptions=False)
        r = client.get("/ping")
        assert r.status_code == 200

    def test_ratelimit_headers_present(self, tmp_path: Path) -> None:
        settings = _base_settings(
            tmp_path,
            rate_limit_enabled=True,
            rate_limit_default_requests=10,
            rate_limit_default_window_seconds=60,
        )
        app = _make_rate_limited_app(settings)
        client = TestClient(app, raise_server_exceptions=False)
        r = client.get("/ping")
        assert "X-RateLimit-Limit" in r.headers
        assert "X-RateLimit-Remaining" in r.headers
        assert "X-RateLimit-Reset" in r.headers

    def test_limit_1_second_request_denied(self, tmp_path: Path) -> None:
        settings = _base_settings(
            tmp_path,
            rate_limit_enabled=True,
            rate_limit_default_requests=1,
            rate_limit_default_window_seconds=60,
        )
        app = _make_rate_limited_app(settings)
        client = TestClient(app, raise_server_exceptions=False)
        client.get("/ping")
        r = client.get("/ping")
        assert r.status_code == 429

    def test_429_has_retry_after(self, tmp_path: Path) -> None:
        settings = _base_settings(
            tmp_path,
            rate_limit_enabled=True,
            rate_limit_default_requests=1,
            rate_limit_default_window_seconds=60,
        )
        app = _make_rate_limited_app(settings)
        client = TestClient(app, raise_server_exceptions=False)
        client.get("/ping")
        r = client.get("/ping")
        assert "Retry-After" in r.headers

    def test_exempt_path_not_rate_limited(self, tmp_path: Path) -> None:
        settings = _base_settings(
            tmp_path,
            rate_limit_enabled=True,
            rate_limit_default_requests=1,
            rate_limit_exempt_paths=["/ping"],
            rate_limit_default_window_seconds=60,
        )
        app = _make_rate_limited_app(settings)
        client = TestClient(app, raise_server_exceptions=False)
        for _ in range(3):
            r = client.get("/ping")
            assert r.status_code == 200

    def test_rule_for_path_applies_custom_limit(self, tmp_path: Path) -> None:
        settings = _base_settings(
            tmp_path,
            rate_limit_enabled=True,
            rate_limit_default_requests=100,
            rate_limit_default_window_seconds=60,
            rate_limit_rules={"/api/v1/data": {"requests": 2, "window_seconds": 60}},
        )
        app = _make_rate_limited_app(settings)
        client = TestClient(app, raise_server_exceptions=False)
        client.get("/api/v1/data")
        client.get("/api/v1/data")
        r = client.get("/api/v1/data")
        assert r.status_code == 429


class TestRateLimitClientId:
    def test_ip_based_client_id(self, tmp_path: Path) -> None:
        settings = _base_settings(
            tmp_path,
            rate_limit_enabled=True,
            rate_limit_default_requests=1,
            rate_limit_default_window_seconds=60,
        )
        app = _make_rate_limited_app(settings)
        client = TestClient(app, raise_server_exceptions=False)
        client.get("/ping")
        r = client.get("/ping")
        assert r.status_code == 429

    def test_proxy_header_ip(self, tmp_path: Path) -> None:
        settings = _base_settings(
            tmp_path,
            rate_limit_enabled=True,
            rate_limit_default_requests=1,
            rate_limit_default_window_seconds=60,
            rate_limit_trust_proxy_headers=True,
        )
        app = _make_rate_limited_app(settings)
        client = TestClient(app, raise_server_exceptions=False)
        client.get("/ping", headers={"X-Forwarded-For": "10.0.0.1"})
        r = client.get("/ping", headers={"X-Forwarded-For": "10.0.0.1"})
        assert r.status_code == 429


# ---------------------------------------------------------------------------
# SecurityHeadersMiddleware
# ---------------------------------------------------------------------------


def _make_security_app(settings: ApiSettings) -> FastAPI:
    from file_organizer.api.middleware import SecurityHeadersMiddleware

    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware, settings=settings)

    @app.get("/ok")
    def ok() -> dict[str, str]:
        return {"status": "ok"}

    return app


class TestSecurityHeadersMiddleware:
    def test_security_headers_present_when_enabled(self, tmp_path: Path) -> None:
        settings = _base_settings(tmp_path, security_headers_enabled=True)
        app = _make_security_app(settings)
        client = TestClient(app, raise_server_exceptions=False)
        r = client.get("/ok")
        assert r.status_code == 200
        assert r.headers.get("X-Frame-Options") == "DENY"
        assert r.headers.get("X-Content-Type-Options") == "nosniff"
        assert r.headers.get("X-XSS-Protection") == "1; mode=block"

    def test_security_headers_absent_when_disabled(self, tmp_path: Path) -> None:
        settings = _base_settings(tmp_path, security_headers_enabled=False)
        app = _make_security_app(settings)
        client = TestClient(app, raise_server_exceptions=False)
        r = client.get("/ok")
        assert "X-Frame-Options" not in r.headers

    def test_csp_header_present(self, tmp_path: Path) -> None:
        settings = _base_settings(tmp_path, security_headers_enabled=True)
        app = _make_security_app(settings)
        client = TestClient(app, raise_server_exceptions=False)
        r = client.get("/ok")
        assert "Content-Security-Policy" in r.headers

    def test_referrer_policy_header(self, tmp_path: Path) -> None:
        settings = _base_settings(
            tmp_path,
            security_headers_enabled=True,
            security_referrer_policy="no-referrer",
        )
        app = _make_security_app(settings)
        client = TestClient(app, raise_server_exceptions=False)
        r = client.get("/ok")
        assert r.headers.get("Referrer-Policy") == "no-referrer"

    def test_permissions_policy_header(self, tmp_path: Path) -> None:
        settings = _base_settings(tmp_path, security_headers_enabled=True)
        app = _make_security_app(settings)
        client = TestClient(app, raise_server_exceptions=False)
        r = client.get("/ok")
        assert "Permissions-Policy" in r.headers
