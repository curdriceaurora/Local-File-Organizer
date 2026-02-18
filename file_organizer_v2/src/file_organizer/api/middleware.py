"""Middleware setup for the API layer."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from file_organizer.api.api_keys import api_key_identifier
from file_organizer.api.auth import decode_token, is_access_token
from file_organizer.api.config import ApiSettings
from file_organizer.api.rate_limit import RateLimiter, RateLimitResult, build_rate_limiter


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Apply rate limiting based on endpoint and client identity."""

    def __init__(self, app: FastAPI, settings: ApiSettings, limiter: RateLimiter) -> None:
        super().__init__(app)
        self._settings = settings
        self._limiter = limiter
        self._rule_prefixes = sorted(settings.rate_limit_rules.keys(), key=len, reverse=True)

    def _is_exempt(self, path: str) -> bool:
        for exempt in self._settings.rate_limit_exempt_paths:
            normalized = exempt.rstrip("/") if exempt != "/" else exempt
            if path == normalized:
                return True
            if normalized != "/" and path.startswith(f"{normalized}/"):
                return True
        return False

    def _rule_for_path(self, path: str) -> Optional[dict[str, int]]:
        rules = self._settings.rate_limit_rules
        for rule_path in self._rule_prefixes:
            if path.startswith(rule_path):
                return rules[rule_path]
        return None

    def _client_id(self, request: Request) -> str:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1]
            try:
                payload = decode_token(token, self._settings)
            except Exception:
                payload = None
            if payload and is_access_token(payload):
                user_id = payload.get("user_id")
                if isinstance(user_id, str):
                    return f"user:{user_id}"

        api_key = request.headers.get(self._settings.api_key_header)
        if api_key and self._settings.api_key_enabled:
            key_id = api_key_identifier(api_key, self._settings.api_key_hashes)
            if key_id:
                request.state.api_key_identifier = key_id
                return f"key:{key_id}"

        client_ip = request.client.host if request.client else "unknown"
        if self._settings.rate_limit_trust_proxy_headers:
            forwarded = request.headers.get("X-Forwarded-For")
            if forwarded:
                client_ip = forwarded.split(",")[0].strip()
        return f"ip:{client_ip}"

    def _apply_headers(self, response: Response, result: RateLimitResult, limit: int) -> None:
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(result.remaining)
        response.headers["X-RateLimit-Reset"] = str(result.reset_at)

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if not self._settings.rate_limit_enabled or request.scope.get("type") != "http":
            return await call_next(request)

        path = request.url.path
        if self._is_exempt(path):
            return await call_next(request)

        rule = self._rule_for_path(path)
        limit = self._settings.rate_limit_default_requests
        window = self._settings.rate_limit_default_window_seconds
        if rule:
            limit = rule.get("requests", limit)
            window = rule.get("window_seconds", window)

        key = f"{self._client_id(request)}:{path}"
        result = self._limiter.check(key, limit, window)
        if not result.allowed:
            retry_after = max(result.reset_at - int(time.time()), 0)
            response: Response = JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Try again later."},
            )
            response.headers["Retry-After"] = str(retry_after)
            self._apply_headers(response, result, limit)
            return response

        response = await call_next(request)
        self._apply_headers(response, result, limit)
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach security headers to API responses."""

    def __init__(self, app: FastAPI, settings: ApiSettings) -> None:
        super().__init__(app)
        self._settings = settings

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = await call_next(request)
        if not self._settings.security_headers_enabled:
            return response

        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-XSS-Protection", "1; mode=block")
        response.headers.setdefault("Referrer-Policy", self._settings.security_referrer_policy)
        response.headers.setdefault(
            "Permissions-Policy",
            "geolocation=(), microphone=(), camera=(), payment=()",
        )
        response.headers.setdefault("Content-Security-Policy", self._settings.security_csp)

        if request.url.scheme == "https" and self._settings.security_hsts_seconds > 0:
            hsts = f"max-age={self._settings.security_hsts_seconds}"
            if self._settings.security_hsts_subdomains:
                hsts += "; includeSubDomains"
            response.headers.setdefault("Strict-Transport-Security", hsts)

        return response


def setup_middleware(app: FastAPI, settings: ApiSettings) -> None:
    """Configure middleware on the FastAPI app."""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=settings.cors_allow_methods,
        allow_headers=settings.cors_allow_headers,
    )
    app.add_middleware(
        RateLimitMiddleware,
        settings=settings,
        limiter=build_rate_limiter(settings.auth_redis_url),
    )
    app.add_middleware(SecurityHeadersMiddleware, settings=settings)
