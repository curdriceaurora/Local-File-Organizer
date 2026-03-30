"""Tests for CSRF protection middleware."""

from __future__ import annotations

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.testclient import TestClient

from file_organizer.web.csrf import (
    CSRF_COOKIE_NAME,
    CSRF_FORM_FIELD,
    CSRF_HEADER_NAME,
    CSRFMiddleware,
    generate_csrf_token,
    validate_csrf_token,
)

pytestmark = [pytest.mark.unit, pytest.mark.ci]

# ---------------------------------------------------------------------------
# Token generation / validation unit tests
# ---------------------------------------------------------------------------


class TestGenerateCSRFToken:
    """Tests for the generate_csrf_token function."""

    def test_returns_hex_string(self) -> None:
        token = generate_csrf_token()
        # Should be a hex string of 64 chars (32 bytes)
        assert len(token) == 64
        int(token, 16)  # raises ValueError if not valid hex

    def test_returns_different_tokens(self) -> None:
        t1 = generate_csrf_token()
        t2 = generate_csrf_token()
        assert t1 != t2

    def test_token_has_sufficient_length(self) -> None:
        token = generate_csrf_token()
        # 32 bytes = 64 hex chars
        assert len(token) >= 64


class TestValidateCSRFToken:
    """Tests for the validate_csrf_token function."""

    def test_matching_tokens_pass(self) -> None:
        token = generate_csrf_token()
        assert validate_csrf_token(cookie_token=token, submitted_token=token) is True

    def test_mismatched_tokens_fail(self) -> None:
        t1 = generate_csrf_token()
        t2 = generate_csrf_token()
        assert validate_csrf_token(cookie_token=t1, submitted_token=t2) is False

    def test_none_cookie_fails(self) -> None:
        assert validate_csrf_token(cookie_token=None, submitted_token="abc") is False

    def test_none_submitted_fails(self) -> None:
        assert validate_csrf_token(cookie_token="abc", submitted_token=None) is False

    def test_both_none_fails(self) -> None:
        assert validate_csrf_token(cookie_token=None, submitted_token=None) is False

    def test_empty_strings_fail(self) -> None:
        assert validate_csrf_token(cookie_token="", submitted_token="") is False

    def test_non_ascii_token_returns_false(self) -> None:
        assert validate_csrf_token(cookie_token="café", submitted_token="café") is False

    def test_uses_constant_time_comparison(self) -> None:
        """Validate that comparison is timing-safe (uses hmac.compare_digest)."""
        # We can't directly test timing, but we verify the function works
        # correctly for equal/unequal cases. The implementation uses
        # hmac.compare_digest which is constant-time.
        token = generate_csrf_token()
        assert validate_csrf_token(cookie_token=token, submitted_token=token) is True
        assert validate_csrf_token(cookie_token=token, submitted_token=token + "x") is False


# ---------------------------------------------------------------------------
# Middleware integration tests
# ---------------------------------------------------------------------------


def _make_app(exempt_paths: list[str] | None = None) -> FastAPI:
    """Create a minimal FastAPI app with CSRF middleware for testing."""
    app = FastAPI()
    app.add_middleware(CSRFMiddleware, exempt_paths=exempt_paths or [])

    @app.get("/form")
    async def get_form(request: Request) -> HTMLResponse:
        token = request.state.csrf_token
        return HTMLResponse(f'<input name="{CSRF_FORM_FIELD}" value="{token}">')

    @app.post("/submit")
    async def post_submit() -> JSONResponse:
        return JSONResponse({"ok": True})

    @app.post("/exempt")
    async def exempt_endpoint() -> JSONResponse:
        return JSONResponse({"ok": True})

    @app.post("/api/session/refresh")
    async def exempt_prefix_endpoint() -> JSONResponse:
        return JSONResponse({"ok": True})

    return app


class TestCSRFMiddleware:
    """Integration tests for CSRFMiddleware."""

    @pytest.fixture()
    def app(self) -> FastAPI:
        return _make_app(exempt_paths=["/exempt"])

    @pytest.fixture()
    def client(self, app: FastAPI) -> TestClient:
        return TestClient(app)

    def test_get_sets_csrf_cookie(self, client: TestClient) -> None:
        response = client.get("/form")
        assert response.status_code == 200
        assert CSRF_COOKIE_NAME in response.cookies

    def test_get_injects_token_into_request_state(self, client: TestClient) -> None:
        response = client.get("/form")
        assert response.status_code == 200
        token = response.cookies[CSRF_COOKIE_NAME]
        assert f'name="{CSRF_FORM_FIELD}"' in response.text
        assert f'value="{token}"' in response.text

    def test_post_without_token_returns_403(self, client: TestClient) -> None:
        response = client.post("/submit")
        assert response.status_code == 403

    def test_post_with_valid_form_token_succeeds(self, client: TestClient) -> None:
        # First GET to obtain the CSRF cookie
        get_resp = client.get("/form")
        token = get_resp.cookies[CSRF_COOKIE_NAME]

        # POST with matching form field
        response = client.post("/submit", data={CSRF_FORM_FIELD: token})
        assert response.status_code == 200

    def test_post_with_valid_header_token_succeeds(self, client: TestClient) -> None:
        # First GET to obtain the CSRF cookie
        get_resp = client.get("/form")
        token = get_resp.cookies[CSRF_COOKIE_NAME]

        # POST with matching header
        response = client.post("/submit", headers={CSRF_HEADER_NAME: token})
        assert response.status_code == 200

    def test_post_with_wrong_token_returns_403(self, client: TestClient) -> None:
        # First GET to obtain the CSRF cookie
        get_resp = client.get("/form")
        assert CSRF_COOKIE_NAME in get_resp.cookies

        # POST with a different token
        response = client.post("/submit", data={CSRF_FORM_FIELD: "wrong-token"})
        assert response.status_code == 403

    def test_post_with_valid_multipart_token_succeeds(self, client: TestClient) -> None:
        get_resp = client.get("/form")
        token = get_resp.cookies[CSRF_COOKIE_NAME]

        # Multipart POST with CSRF token as a form field
        response = client.post(
            "/submit",
            data={CSRF_FORM_FIELD: token},
            files={"file": ("test.txt", b"data")},
        )
        assert response.status_code == 200

    def test_post_with_wrong_multipart_token_returns_403(self, client: TestClient) -> None:
        get_resp = client.get("/form")
        assert CSRF_COOKIE_NAME in get_resp.cookies

        response = client.post(
            "/submit",
            data={CSRF_FORM_FIELD: "wrong-token"},
            files={"file": ("test.txt", b"data")},
        )
        assert response.status_code == 403

    def test_exempt_path_bypasses_csrf(self, client: TestClient) -> None:
        response = client.post("/exempt")
        assert response.status_code == 200

    def test_exempt_prefix_with_trailing_slash_bypasses_csrf(self) -> None:
        app = _make_app(exempt_paths=["/api/"])
        client = TestClient(app)

        response = client.post("/api/session/refresh")

        assert response.status_code == 200

    def test_cookie_is_httponly(self, client: TestClient) -> None:
        response = client.get("/form")
        cookie_header = response.headers.get("set-cookie", "")
        assert "httponly" in cookie_header.lower()

    def test_cookie_is_samesite_strict(self, client: TestClient) -> None:
        response = client.get("/form")
        cookie_header = response.headers.get("set-cookie", "")
        assert "samesite=strict" in cookie_header.lower()

    def test_reuses_existing_cookie_on_get(self, client: TestClient) -> None:
        # First GET sets the cookie
        resp1 = client.get("/form")
        token1 = resp1.cookies[CSRF_COOKIE_NAME]

        # Second GET with existing cookie should reuse it
        resp2 = client.get("/form")
        # The token in the rendered page should match
        assert token1 in resp2.text
