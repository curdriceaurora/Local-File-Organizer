"""Tests for API middleware (middleware.py)."""

from __future__ import annotations

import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from file_organizer.api.middleware import RateLimitMiddleware, SecurityHeadersMiddleware
from file_organizer.api.rate_limit import InMemoryRateLimiter, RateLimitResult
from file_organizer.api.test_utils import build_test_settings


def _make_rate_limited_app(tmp_path, *, limit: int = 1000, enabled: bool = True):
    """Return an app+client with RateLimitMiddleware using a tracking fake limiter."""
    settings = build_test_settings(
        tmp_path,
        auth_overrides={
            "rate_limit_enabled": enabled,
            "rate_limit_default_requests": limit,
            "rate_limit_default_window_seconds": 60,
            "rate_limit_exempt_paths": ["/docs", "/redoc", "/openapi.json"],
        },
    )
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, settings=settings, limiter=InMemoryRateLimiter())

    @app.get("/probe")
    def probe():
        return {"ok": True}

    @app.get("/api/v1/items")
    def items():
        return {"items": []}

    return app, settings


class _FakeLimiter:
    """Fake RateLimiter that records every check() call and always allows."""

    def __init__(self):
        self.calls: list[tuple[str, int, int]] = []

    def check(self, key: str, limit: int, window_seconds: int) -> RateLimitResult:
        self.calls.append((key, limit, window_seconds))
        return RateLimitResult(allowed=True, remaining=limit - 1, reset_at=int(time.time()) + window_seconds)


@pytest.mark.unit
class TestRateLimitMiddleware:
    """Tests for RateLimitMiddleware."""

    def test_allows_request_within_limit(self, tmp_path):
        app, _ = _make_rate_limited_app(tmp_path, limit=10)
        client = TestClient(app, raise_server_exceptions=True)
        response = client.get("/probe")
        assert response.status_code == 200

    def test_rate_limit_headers_present(self, tmp_path):
        app, _ = _make_rate_limited_app(tmp_path, limit=10)
        client = TestClient(app)
        response = client.get("/probe")
        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers
        assert "X-RateLimit-Reset" in response.headers

    def test_blocks_when_limit_exceeded(self, tmp_path):
        app, _ = _make_rate_limited_app(tmp_path, limit=1)
        client = TestClient(app)
        # First request uses the single allowed slot
        client.get("/probe")
        # Second request should be blocked
        response = client.get("/probe")
        assert response.status_code == 429
        assert "Retry-After" in response.headers

    def test_exempt_path_bypasses_limiter(self, tmp_path):
        settings = build_test_settings(
            tmp_path,
            auth_overrides={
                "rate_limit_enabled": True,
                "rate_limit_default_requests": 1,
                "rate_limit_default_window_seconds": 60,
                "rate_limit_exempt_paths": ["/exempt"],
            },
        )
        fake = _FakeLimiter()
        app = FastAPI()
        app.add_middleware(RateLimitMiddleware, settings=settings, limiter=fake)

        @app.get("/exempt")
        def exempt_route():
            return {}

        client = TestClient(app)
        client.get("/exempt")
        # The limiter should NOT have been called for the exempt path
        assert all("/exempt" not in key for key, _, _ in fake.calls)

    def test_rate_limit_disabled_bypasses_limiter(self, tmp_path):
        settings = build_test_settings(
            tmp_path,
            auth_overrides={"rate_limit_enabled": False},
        )
        fake = _FakeLimiter()
        app = FastAPI()
        app.add_middleware(RateLimitMiddleware, settings=settings, limiter=fake)

        @app.get("/probe")
        def probe():
            return {}

        client = TestClient(app)
        client.get("/probe")
        assert fake.calls == []

    def test_rate_limit_key_format(self, tmp_path):
        """S-3: Verify the key passed to the limiter uses the '{client_id}:{path}' format."""
        settings = build_test_settings(
            tmp_path,
            auth_overrides={
                "rate_limit_enabled": True,
                "rate_limit_default_requests": 100,
                "rate_limit_default_window_seconds": 60,
                "rate_limit_exempt_paths": [],
            },
        )
        fake = _FakeLimiter()
        app = FastAPI()
        app.add_middleware(RateLimitMiddleware, settings=settings, limiter=fake)

        @app.get("/api/v1/items")
        def items():
            return {}

        client = TestClient(app)
        client.get("/api/v1/items")

        assert len(fake.calls) == 1
        key, _, _ = fake.calls[0]
        # Key must follow the "{client_id}:{path}" pattern defined in middleware.py:99
        # client_id prefix is one of: "ip:", "user:", "key:"
        assert ":" in key, f"Key must contain ':' separator, got {key!r}"
        colon_idx = key.rfind(":/api/v1/items")
        assert colon_idx != -1, (
            f"Key must end with ':<path>', i.e. contain ':/api/v1/items'. Got {key!r}"
        )
        # Verify the prefix portion matches a recognised client-id prefix pattern
        client_id = key[: colon_idx + 1]  # includes the ':' from client_id
        assert client_id.startswith(("ip:", "user:", "key:")), (
            f"client_id prefix must be ip:, user:, or key:. Got {client_id!r}"
        )

    def test_different_paths_use_different_keys(self, tmp_path):
        """Requests to different paths produce different rate-limit keys."""
        settings = build_test_settings(
            tmp_path,
            auth_overrides={
                "rate_limit_enabled": True,
                "rate_limit_default_requests": 100,
                "rate_limit_default_window_seconds": 60,
                "rate_limit_exempt_paths": [],
            },
        )
        fake = _FakeLimiter()
        app = FastAPI()
        app.add_middleware(RateLimitMiddleware, settings=settings, limiter=fake)

        @app.get("/path-a")
        def path_a():
            return {}

        @app.get("/path-b")
        def path_b():
            return {}

        client = TestClient(app)
        client.get("/path-a")
        client.get("/path-b")

        assert len(fake.calls) == 2
        keys = [c[0] for c in fake.calls]
        assert keys[0] != keys[1]

    def test_per_path_rule_overrides_default(self, tmp_path):
        settings = build_test_settings(
            tmp_path,
            auth_overrides={
                "rate_limit_enabled": True,
                "rate_limit_default_requests": 100,
                "rate_limit_default_window_seconds": 60,
                "rate_limit_exempt_paths": [],
                "rate_limit_rules": {"/strict": {"requests": 2, "window_seconds": 30}},
            },
        )
        fake = _FakeLimiter()
        app = FastAPI()
        app.add_middleware(RateLimitMiddleware, settings=settings, limiter=fake)

        @app.get("/strict")
        def strict():
            return {}

        client = TestClient(app)
        client.get("/strict")

        assert len(fake.calls) == 1
        _, limit, window = fake.calls[0]
        assert limit == 2
        assert window == 30


@pytest.mark.unit
class TestSecurityHeadersMiddleware:
    """Tests for SecurityHeadersMiddleware."""

    def _make_app(self, tmp_path, *, enabled: bool = True):
        settings = build_test_settings(
            tmp_path,
            auth_overrides={"security_headers_enabled": enabled},
        )
        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware, settings=settings)

        @app.get("/probe")
        def probe():
            return {}

        return TestClient(app)

    def test_security_headers_added_when_enabled(self, tmp_path):
        client = self._make_app(tmp_path, enabled=True)
        response = client.get("/probe")
        assert response.headers.get("X-Frame-Options") == "DENY"
        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("X-XSS-Protection") == "1; mode=block"

    def test_security_headers_absent_when_disabled(self, tmp_path):
        client = self._make_app(tmp_path, enabled=False)
        response = client.get("/probe")
        assert "X-Frame-Options" not in response.headers

    def test_referrer_policy_header(self, tmp_path):
        client = self._make_app(tmp_path, enabled=True)
        response = client.get("/probe")
        assert "Referrer-Policy" in response.headers

    def test_content_security_policy_header(self, tmp_path):
        client = self._make_app(tmp_path, enabled=True)
        response = client.get("/probe")
        assert "Content-Security-Policy" in response.headers
