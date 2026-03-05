"""Tests for API middleware (security headers and rate limiting)."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI
from starlette.testclient import TestClient

from file_organizer.api.config import ApiSettings
from file_organizer.api.middleware import RateLimitMiddleware, SecurityHeadersMiddleware
from file_organizer.api.rate_limit import RateLimitResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_settings(**overrides: Any) -> ApiSettings:
    """Create an ApiSettings with test-friendly defaults."""
    defaults: dict[str, Any] = {
        "auth_enabled": False,
        "environment": "test",
    }
    defaults.update(overrides)
    return ApiSettings(**defaults)


@dataclass
class _FakeLimiterConfig:
    allowed: bool = True
    remaining: int = 99
    reset_at: int = 0


class _FakeLimiter:
    """Minimal rate limiter that returns a pre-configured result."""

    def __init__(self, cfg: _FakeLimiterConfig | None = None) -> None:
        self._cfg = cfg or _FakeLimiterConfig()
        self.calls: list[tuple[str, int, int]] = []

    def check(self, key: str, limit: int, window_seconds: int) -> RateLimitResult:
        self.calls.append((key, limit, window_seconds))
        return RateLimitResult(
            allowed=self._cfg.allowed,
            remaining=self._cfg.remaining,
            reset_at=self._cfg.reset_at or (int(time.time()) + window_seconds),
        )


def _build_app(
    settings: ApiSettings | None = None,
    limiter: _FakeLimiter | None = None,
    *,
    include_rate_limit: bool = False,
    include_security: bool = True,
) -> FastAPI:
    """Build a minimal FastAPI app with the requested middleware."""
    app = FastAPI()

    @app.get("/test")
    async def _test_endpoint() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/docs")
    async def _docs_endpoint() -> dict[str, str]:
        return {"docs": "yes"}

    @app.get("/health")
    async def _health_endpoint() -> dict[str, str]:
        return {"health": "ok"}

    settings = settings or _make_settings()

    if include_rate_limit:
        app.add_middleware(
            RateLimitMiddleware,
            settings=settings,
            limiter=limiter or _FakeLimiter(),
        )

    if include_security:
        app.add_middleware(SecurityHeadersMiddleware, settings=settings)

    return app


# ---------------------------------------------------------------------------
# SecurityHeadersMiddleware tests
# ---------------------------------------------------------------------------


class TestSecurityHeadersMiddleware:
    """Tests for the SecurityHeadersMiddleware class."""

    def test_security_headers_present_when_enabled(self) -> None:
        settings = _make_settings(security_headers_enabled=True)
        app = _build_app(settings=settings)
        client = TestClient(app)

        response = client.get("/test")

        assert response.status_code == 200
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-XSS-Protection"] == "1; mode=block"
        assert response.headers["Referrer-Policy"] == settings.security_referrer_policy
        assert "Permissions-Policy" in response.headers
        assert "Content-Security-Policy" in response.headers

    def test_no_security_headers_when_disabled(self) -> None:
        settings = _make_settings(security_headers_enabled=False)
        app = _build_app(settings=settings)
        client = TestClient(app)

        response = client.get("/test")

        assert response.status_code == 200
        assert "X-Frame-Options" not in response.headers
        assert "X-Content-Type-Options" not in response.headers
        assert "X-XSS-Protection" not in response.headers

    def test_custom_referrer_policy(self) -> None:
        settings = _make_settings(security_referrer_policy="no-referrer")
        app = _build_app(settings=settings)
        client = TestClient(app)

        response = client.get("/test")

        assert response.headers["Referrer-Policy"] == "no-referrer"

    def test_custom_csp(self) -> None:
        custom_csp = "default-src 'none'"
        settings = _make_settings(security_csp=custom_csp)
        app = _build_app(settings=settings)
        client = TestClient(app)

        response = client.get("/test")

        assert response.headers["Content-Security-Policy"] == custom_csp

    def test_hsts_not_present_for_http(self) -> None:
        """HSTS header should not appear for plain HTTP requests."""
        settings = _make_settings(
            security_headers_enabled=True,
            security_hsts_seconds=31536000,
        )
        app = _build_app(settings=settings)
        # TestClient uses http:// by default
        client = TestClient(app, base_url="http://testserver")

        response = client.get("/test")

        assert response.status_code == 200
        assert "Strict-Transport-Security" not in response.headers

    def test_hsts_present_for_https(self) -> None:
        """HSTS header should appear for HTTPS requests."""
        settings = _make_settings(
            security_headers_enabled=True,
            security_hsts_seconds=31536000,
            security_hsts_subdomains=True,
        )
        app = _build_app(settings=settings)
        client = TestClient(app, base_url="https://testserver")

        response = client.get("/test")

        assert response.status_code == 200
        hsts_value = response.headers.get("Strict-Transport-Security", "")
        assert "max-age=31536000" in hsts_value
        assert "includeSubDomains" in hsts_value

    def test_hsts_without_subdomains(self) -> None:
        settings = _make_settings(
            security_headers_enabled=True,
            security_hsts_seconds=31536000,
            security_hsts_subdomains=False,
        )
        app = _build_app(settings=settings)
        client = TestClient(app, base_url="https://testserver")

        response = client.get("/test")

        hsts_value = response.headers.get("Strict-Transport-Security", "")
        assert "max-age=31536000" in hsts_value
        assert "includeSubDomains" not in hsts_value

    def test_hsts_zero_seconds_no_header(self) -> None:
        settings = _make_settings(
            security_headers_enabled=True,
            security_hsts_seconds=0,
        )
        app = _build_app(settings=settings)
        client = TestClient(app, base_url="https://testserver")

        response = client.get("/test")

        assert "Strict-Transport-Security" not in response.headers


# ---------------------------------------------------------------------------
# RateLimitMiddleware tests
# ---------------------------------------------------------------------------


class TestRateLimitMiddleware:
    """Tests for the RateLimitMiddleware class."""

    def test_normal_request_passes_with_headers(self) -> None:
        limiter = _FakeLimiter(_FakeLimiterConfig(allowed=True, remaining=99))
        settings = _make_settings(rate_limit_enabled=True)
        app = _build_app(settings=settings, limiter=limiter, include_rate_limit=True)
        client = TestClient(app)

        response = client.get("/test")

        assert response.status_code == 200
        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers
        assert "X-RateLimit-Reset" in response.headers
        assert response.headers["X-RateLimit-Remaining"] == "99"

    def test_rate_limit_exceeded_returns_429(self) -> None:
        reset_at = int(time.time()) + 60
        limiter = _FakeLimiter(_FakeLimiterConfig(allowed=False, remaining=0, reset_at=reset_at))
        settings = _make_settings(rate_limit_enabled=True)
        app = _build_app(settings=settings, limiter=limiter, include_rate_limit=True)
        client = TestClient(app)

        response = client.get("/test")

        assert response.status_code == 429
        assert "Retry-After" in response.headers
        body = response.json()
        assert "Rate limit exceeded" in body["detail"]

    def test_rate_limit_disabled_skips_check(self) -> None:
        limiter = _FakeLimiter()
        settings = _make_settings(rate_limit_enabled=False)
        app = _build_app(settings=settings, limiter=limiter, include_rate_limit=True)
        client = TestClient(app)

        response = client.get("/test")

        assert response.status_code == 200
        # Limiter should not have been called
        assert len(limiter.calls) == 0
        # No rate limit headers expected
        assert "X-RateLimit-Limit" not in response.headers

    def test_exempt_path_bypasses_rate_limiting(self) -> None:
        limiter = _FakeLimiter()
        settings = _make_settings(
            rate_limit_enabled=True,
            rate_limit_exempt_paths=["/docs", "/health"],
        )
        app = _build_app(
            settings=settings,
            limiter=limiter,
            include_rate_limit=True,
            include_security=False,
        )
        client = TestClient(app)

        response = client.get("/docs")

        assert response.status_code == 200
        assert len(limiter.calls) == 0

    def test_non_exempt_path_is_rate_limited(self) -> None:
        limiter = _FakeLimiter()
        settings = _make_settings(
            rate_limit_enabled=True,
            rate_limit_exempt_paths=["/docs"],
        )
        app = _build_app(
            settings=settings,
            limiter=limiter,
            include_rate_limit=True,
            include_security=False,
        )
        client = TestClient(app)

        response = client.get("/test")

        assert response.status_code == 200
        assert len(limiter.calls) == 1

    def test_custom_rule_overrides_defaults(self) -> None:
        limiter = _FakeLimiter(_FakeLimiterConfig(allowed=True, remaining=4))
        settings = _make_settings(
            rate_limit_enabled=True,
            rate_limit_default_requests=1000,
            rate_limit_rules={"/test": {"requests": 5, "window_seconds": 30}},
        )
        app = _build_app(
            settings=settings,
            limiter=limiter,
            include_rate_limit=True,
            include_security=False,
        )
        client = TestClient(app)

        response = client.get("/test")

        assert response.status_code == 200
        # The limiter should have been called with the custom limit
        assert len(limiter.calls) == 1
        _key, limit, window = limiter.calls[0]
        assert limit == 5
        assert window == 30

    def test_rate_limit_key_format(self) -> None:
        """Rate limit key must follow the '{client_id}:{path}' format (middleware.py:99)."""
        limiter = _FakeLimiter()
        settings = _make_settings(rate_limit_enabled=True)
        app = _build_app(
            settings=settings,
            limiter=limiter,
            include_rate_limit=True,
            include_security=False,
        )
        client = TestClient(app)

        client.get("/test")

        assert len(limiter.calls) == 1
        key, _limit, _window = limiter.calls[0]
        # Unauthenticated requests use "ip:{address}" as the client identifier
        assert key.startswith("ip:")
        assert key.endswith(":/test")

    def test_rate_limit_headers_values(self) -> None:
        reset_ts = int(time.time()) + 120
        limiter = _FakeLimiter(_FakeLimiterConfig(allowed=True, remaining=42, reset_at=reset_ts))
        settings = _make_settings(
            rate_limit_enabled=True,
            rate_limit_default_requests=100,
        )
        app = _build_app(
            settings=settings,
            limiter=limiter,
            include_rate_limit=True,
            include_security=False,
        )
        client = TestClient(app)

        response = client.get("/test")

        assert response.headers["X-RateLimit-Limit"] == "100"
        assert response.headers["X-RateLimit-Remaining"] == "42"
        assert response.headers["X-RateLimit-Reset"] == str(reset_ts)
