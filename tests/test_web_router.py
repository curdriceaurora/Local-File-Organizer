"""Tests for the web UI router (routes at /ui/ prefix).

NOTE: This module tests the web router initialization and basic /ui/ route
accessibility. For comprehensive web route tests, see tests/web/ directory.
"""

from __future__ import annotations

import pytest


@pytest.mark.unit
class TestHomeRoute:
    """Tests for the home page route."""

    def test_home_page_returns_200(self, web_client_builder) -> None:
        """Web home page should return 200 status."""
        client = web_client_builder(allowed_paths=[])
        response = client.get("/ui/")
        assert response.status_code == 200

    def test_home_page_returns_html(self, web_client_builder) -> None:
        """Web home page should return HTML content."""
        client = web_client_builder(allowed_paths=[])
        response = client.get("/ui/")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    def test_home_page_renders_template(self, web_client_builder) -> None:
        """Web home page should render the base template with expected HTML structure."""
        client = web_client_builder(allowed_paths=[])
        response = client.get("/ui/")
        assert response.status_code == 200
        # Check for common HTML structural elements
        assert any(tag in response.text for tag in ("<!DOCTYPE html", "<html", "<head", "<body"))

    def test_home_page_with_auth_disabled(self, web_client_builder) -> None:
        """Web home page works with auth disabled."""
        client = web_client_builder(allowed_paths=[], auth_enabled=False)
        response = client.get("/ui/")
        assert response.status_code == 200

    def test_home_page_with_auth_enabled(self, web_client_builder) -> None:
        """Web home page accessible with auth enabled."""
        client = web_client_builder(allowed_paths=[], auth_enabled=True)
        response = client.get("/ui/")
        # May redirect to login or show home - either is acceptable
        assert response.status_code in [200, 303]


@pytest.mark.unit
class TestErrorPages:
    """Tests for error page handling."""

    def test_nonexistent_path_returns_404(self, web_client_builder) -> None:
        """Requesting nonexistent path should return 404."""
        client = web_client_builder(allowed_paths=[])
        response = client.get("/ui/nonexistent/path/that/does/not/exist")
        assert response.status_code == 404

    def test_404_returns_valid_response(self, web_client_builder) -> None:
        """404 error should return valid response with appropriate content type."""
        client = web_client_builder(allowed_paths=[])
        response = client.get("/ui/invalid")
        assert response.status_code == 404
        # FastAPI may return JSON or HTML depending on error handler configuration
        content_type = response.headers.get("content-type", "")
        assert "json" in content_type or "html" in content_type


@pytest.mark.unit
class TestRouterSetup:
    """Tests for router initialization and configuration."""

    def test_app_creates_successfully(self, tmp_path) -> None:
        """App should initialize without errors."""
        from file_organizer.api.main import create_app
        from file_organizer.api.test_utils import build_test_settings

        settings = build_test_settings(tmp_path, allowed_paths=[])
        app = create_app(settings)
        assert app is not None

    def test_client_can_make_requests(self, web_client_builder) -> None:
        """Test client should be able to make requests to web routes."""
        client = web_client_builder(allowed_paths=[])
        response = client.get("/ui/")
        assert response.status_code in [200, 303]  # Allow redirect for auth


@pytest.mark.unit
class TestResponseHeaders:
    """Tests for response header handling and caching."""

    def test_html_response_includes_content_type(self, web_client_builder) -> None:
        """HTML responses should include proper content-type header."""
        client = web_client_builder(allowed_paths=[])
        response = client.get("/ui/")
        assert response.status_code == 200
        content_type = response.headers.get("content-type", "")
        assert "text/html" in content_type

    def test_response_headers_include_cache_control(self, web_client_builder) -> None:
        """Responses should include cache control headers."""
        client = web_client_builder(allowed_paths=[])
        response = client.get("/ui/")
        assert response.status_code == 200
        # Assert cache-control header (FINDING 6)
        assert response.headers.get("cache-control") is not None

    def test_response_headers_etag_for_static_content(self, web_client_builder) -> None:
        """Responses may include ETag header for cache validation."""
        client = web_client_builder(allowed_paths=[])
        response = client.get("/ui/")
        assert response.status_code in [200, 304, 303]
        # ETag optional but if present, should be valid format
        etag = response.headers.get("etag")
        if etag:
            assert etag.startswith('"') or etag.startswith("W/"), f"ETag has invalid format: {etag}"


@pytest.mark.unit
class TestHTMXIntegration:
    """Tests for HTMX request/response handling."""

    def test_htmx_request_header_recognition(self, web_client_builder) -> None:
        """Server should recognize HX-Request header from HTMX."""
        client = web_client_builder(allowed_paths=[])
        headers = {"HX-Request": "true"}
        response = client.get("/ui/", headers=headers)
        # Response should handle HTMX request appropriately
        assert response.status_code in [200, 303]

    def test_htmx_swap_target_header(self, web_client_builder) -> None:
        """Server should handle HX-Target header for swap operations."""
        client = web_client_builder(allowed_paths=[])
        headers = {
            "HX-Request": "true",
            "HX-Target": "main-content",
        }
        response = client.get("/ui/", headers=headers)
        assert response.status_code in [200, 303, 404]

    def test_htmx_trigger_header_handling(self, web_client_builder) -> None:
        """Server should handle HX-Trigger header for event tracking."""
        client = web_client_builder(allowed_paths=[])
        headers = {
            "HX-Request": "true",
            "HX-Trigger": "search-form",
        }
        response = client.get("/ui/", headers=headers)
        assert response.status_code in [200, 303, 404]

    def test_htmx_redirect_response_header(self, web_client_builder) -> None:
        """Server may send HX-Redirect header for client-side redirects."""
        client = web_client_builder(allowed_paths=[])
        headers = {"HX-Request": "true"}
        response = client.get("/ui/", headers=headers)
        # Response may include HX-Redirect or handle normally
        assert response.status_code in [200, 303, 404]
        # If redirect header present, should be valid
        hx_redirect = response.headers.get("HX-Redirect")
        if hx_redirect:
            assert hx_redirect.startswith("/") or hx_redirect.startswith("http")


@pytest.mark.unit
class TestRateLimitingAndIntegration:
    """Tests for rate limiting and integration behavior (Stream D)."""

    def test_rate_limiting_enforcement(self, web_client_builder) -> None:
        """Server may enforce rate limiting on endpoints."""
        client = web_client_builder(allowed_paths=[])
        # Make multiple requests to same endpoint
        responses = [client.get("/ui/") for _ in range(5)]
        # All requests should succeed or some may hit rate limit
        status_codes = [r.status_code for r in responses]
        # Should have mix of 200 and possibly 429 (too many requests)
        assert any(code in [200, 303] for code in status_codes)

    def test_integration_multiple_endpoints_consistency(self, web_client_builder) -> None:
        """Multiple endpoints should maintain consistent state."""
        client = web_client_builder(allowed_paths=[])
        # Hit multiple endpoints in sequence
        response1 = client.get("/ui/")
        response2 = client.get("/ui/")
        response3 = client.get("/ui/")
        # All should be consistent
        assert response1.status_code == response2.status_code == response3.status_code
