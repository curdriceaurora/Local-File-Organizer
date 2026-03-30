"""CSRF protection middleware for the web UI.

Implements the double-submit cookie pattern: a random token is stored in an
httpOnly cookie and must be submitted back in either a form field or a custom
header on every state-changing request (POST/PUT/PATCH/DELETE).

API routes (``/api/``) are exempt because they use Bearer-token auth, which is
not vulnerable to CSRF.
"""

from __future__ import annotations

import hmac
import secrets
from collections.abc import Sequence

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

CSRF_COOKIE_NAME = "_csrf_token"
CSRF_FORM_FIELD = "csrf_token"
CSRF_HEADER_NAME = "x-csrf-token"

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})
_TOKEN_BYTES = 32


def generate_csrf_token() -> str:
    """Generate a cryptographically random CSRF token."""
    return secrets.token_hex(_TOKEN_BYTES)


def validate_csrf_token(*, cookie_token: str | None, submitted_token: str | None) -> bool:
    """Validate that the submitted token matches the cookie token.

    Uses constant-time comparison to prevent timing attacks.
    """
    if not cookie_token or not submitted_token:
        return False
    # hmac.compare_digest raises TypeError on non-ASCII str; our tokens are
    # hex strings, so reject anything that isn't ASCII before comparing.
    if not cookie_token.isascii() or not submitted_token.isascii():
        return False
    return hmac.compare_digest(cookie_token, submitted_token)


class CSRFMiddleware(BaseHTTPMiddleware):
    """Double-submit cookie CSRF middleware.

    Parameters
    ----------
    app:
        The ASGI application.
    exempt_paths:
        URL path prefixes that skip CSRF validation (e.g. ``["/api/"]``).
    """

    def __init__(
        self,
        app: object,
        exempt_paths: Sequence[str] = (),
    ) -> None:
        """Initialise the middleware with optional exempt path prefixes."""
        super().__init__(app)  # type: ignore[arg-type]
        self._exempt_prefixes = tuple(exempt_paths)

    def _is_exempt(self, path: str) -> bool:
        """Return True if path matches an exempt route exactly or by path-segment prefix."""
        for prefix in self._exempt_prefixes:
            if prefix.endswith("/"):
                if path.startswith(prefix):
                    return True
            elif path == prefix or path.startswith(f"{prefix}/"):
                return True
        return False

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Enforce CSRF on state-changing methods for non-exempt paths."""
        # Always make a token available on request.state for templates.
        cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
        if not cookie_token:
            cookie_token = generate_csrf_token()
        request.state.csrf_token = cookie_token

        # Safe methods and exempt paths skip validation.
        if request.method in _SAFE_METHODS or self._is_exempt(request.url.path):
            response = await call_next(request)
            # Set cookie on every response so the token is always available.
            response.set_cookie(
                CSRF_COOKIE_NAME,
                cookie_token,
                httponly=True,
                samesite="strict",
                path="/",
            )
            return response

        # State-changing method: validate token.
        submitted: str | None = None

        # Check header first (preferred for JS-driven forms / fetch).
        submitted = request.headers.get(CSRF_HEADER_NAME)

        # Fall back to form field.
        if not submitted:
            content_type = request.headers.get("content-type", "")
            if (
                "application/x-www-form-urlencoded" in content_type
                or "multipart/form-data" in content_type
            ):
                form = await request.form()
                submitted = form.get(CSRF_FORM_FIELD)  # type: ignore[assignment]

        if not validate_csrf_token(cookie_token=cookie_token, submitted_token=submitted):
            return JSONResponse(
                {"detail": "CSRF token missing or invalid"},
                status_code=403,
            )

        response = await call_next(request)
        response.set_cookie(
            CSRF_COOKIE_NAME,
            cookie_token,
            httponly=True,
            samesite="strict",
            path="/",
        )
        return response
