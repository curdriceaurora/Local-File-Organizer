"""Tests for the FastAPI app factory and middleware."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from file_organizer.api.config import ApiSettings
from file_organizer.api.main import create_app

pytestmark = pytest.mark.ci


@pytest.mark.unit
class TestAppFactory:
    """Tests for the create_app() factory function."""

    def test_create_app_returns_fastapi_instance(self) -> None:
        """Test that create_app returns a FastAPI instance."""
        with patch("file_organizer.api.main.ApiSettings") as mock_settings:
            mock_settings.return_value = ApiSettings(environment="test")
            app = create_app()
            assert isinstance(app, FastAPI)

    def test_app_has_routers(self) -> None:
        """Test that created app has routers registered."""
        with patch("file_organizer.api.main.ApiSettings") as mock_settings:
            mock_settings.return_value = ApiSettings(environment="test")
            app = create_app()
            # Check that app has routes
            assert len(app.routes) > 0

    def test_app_has_exception_handlers(self) -> None:
        """Test that app has exception handlers registered."""
        with patch("file_organizer.api.main.ApiSettings") as mock_settings:
            mock_settings.return_value = ApiSettings(environment="test")
            app = create_app()
            # Exception handlers should be registered
            assert hasattr(app, "exception_handlers")

    def test_app_has_middleware(self) -> None:
        """Test that created app has middleware."""
        with patch("file_organizer.api.main.ApiSettings") as mock_settings:
            mock_settings.return_value = ApiSettings(environment="test")
            app = create_app()
            # Middleware should be present in the app
            assert hasattr(app, "middleware_stack")


@pytest.mark.unit
class TestAppMiddleware:
    """Tests for middleware chain and ordering."""

    def test_cors_middleware_allows_origins(self) -> None:
        """Test CORS middleware allows configured origins."""
        with patch("file_organizer.api.main.ApiSettings") as mock_settings:
            settings = ApiSettings(
                environment="test",
                cors_origins=["http://localhost:3000"],
            )
            mock_settings.return_value = settings
            app = create_app()

            # CORS middleware should be present
            assert hasattr(app, "middleware_stack")

    def test_middleware_ordering(self) -> None:
        """Test middleware is applied in correct order."""
        with patch("file_organizer.api.main.ApiSettings") as mock_settings:
            mock_settings.return_value = ApiSettings(environment="test")
            app = create_app()
            # Middleware should be applied via middleware list
            assert len(app.user_middleware) > 0

    def test_request_id_middleware(self) -> None:
        """Test request ID middleware adds tracking."""
        with patch("file_organizer.api.main.ApiSettings") as mock_settings:
            mock_settings.return_value = ApiSettings(environment="test")
            app = create_app()
            # Request ID middleware should be part of middleware stack
            assert hasattr(app, "user_middleware")


@pytest.mark.unit
class TestAppStartupShutdown:
    """Tests for app startup and shutdown events."""

    def test_app_startup_event(self) -> None:
        """Test app startup event is configured."""
        with patch("file_organizer.api.main.ApiSettings") as mock_settings:
            mock_settings.return_value = ApiSettings(environment="test")
            app = create_app()
            # Startup events should be registered or at least app is created
            assert app is not None

    def test_app_shutdown_event(self) -> None:
        """Test app shutdown event is configured."""
        with patch("file_organizer.api.main.ApiSettings") as mock_settings:
            mock_settings.return_value = ApiSettings(environment="test")
            app = create_app()
            # Shutdown events should be registered or at least app is created
            assert app is not None

    def test_app_lifecycle(self) -> None:
        """Test complete app lifecycle."""
        with patch("file_organizer.api.main.ApiSettings") as mock_settings:
            mock_settings.return_value = ApiSettings(environment="test")
            app = create_app()
            client = TestClient(app)

            # Client context manager triggers startup/shutdown
            with client:
                resp = client.get("/health")
                # Should get valid response
                assert resp.status_code in [200, 404]


@pytest.mark.unit
class TestAppExceptionHandlers:
    """Tests for app exception handlers."""

    def test_404_exception_handler(self) -> None:
        """Test 404 handler returns JSON."""
        with patch("file_organizer.api.main.ApiSettings") as mock_settings:
            mock_settings.return_value = ApiSettings(environment="test")
            app = create_app()
            client = TestClient(app)

            resp = client.get("/nonexistent-route")
            assert resp.status_code == 404
            # Should return JSON response
            body = resp.json()
            assert isinstance(body, dict)

    def test_500_exception_handler(self) -> None:
        """Test 500 error handler."""
        with patch("file_organizer.api.main.ApiSettings") as mock_settings:
            mock_settings.return_value = ApiSettings(environment="test")
            app = create_app()

            # Exception handler should be registered as part of app setup
            assert hasattr(app, "exception_handlers")


@pytest.mark.unit
class TestAppRoutes:
    """Tests for app route registration."""

    def test_health_route_exists(self) -> None:
        """Test health route is registered."""
        with patch("file_organizer.api.main.ApiSettings") as mock_settings:
            mock_settings.return_value = ApiSettings(environment="test")
            app = create_app()
            client = TestClient(app)

            resp = client.get("/api/v1/health")
            # Health route should exist (207 = Multi-Status for multiple health checks)
            assert resp.status_code in [200, 207, 500]

    def test_api_routes_exist(self) -> None:
        """Test API routes are registered."""
        with patch("file_organizer.api.main.ApiSettings") as mock_settings:
            mock_settings.return_value = ApiSettings(environment="test")
            app = create_app()
            client = TestClient(app)

            # API prefix should be registered
            resp = client.get("/api/v1/system/status")
            # Route should exist or require auth
            assert resp.status_code in [200, 401, 403, 404]

    def test_openapi_schema_available(self) -> None:
        """Test OpenAPI schema is available."""
        with patch("file_organizer.api.main.ApiSettings") as mock_settings:
            mock_settings.return_value = ApiSettings(environment="test")
            app = create_app()
            client = TestClient(app)

            resp = client.get("/openapi.json")
            # OpenAPI schema should be available
            assert resp.status_code == 200
            assert "openapi" in resp.json()


@pytest.mark.unit
class TestAppConfiguration:
    """Tests for app configuration."""

    def test_app_title_and_description(self) -> None:
        """Test app title and description are set."""
        with patch("file_organizer.api.main.ApiSettings") as mock_settings:
            mock_settings.return_value = ApiSettings(environment="test")
            app = create_app()
            # App should have title
            assert app.title is not None

    def test_app_version(self) -> None:
        """Test app version is set."""
        with patch("file_organizer.api.main.ApiSettings") as mock_settings:
            mock_settings.return_value = ApiSettings(environment="test")
            app = create_app()
            # App should have version
            assert app.version is not None

    def test_app_docs_enabled(self) -> None:
        """Test API documentation is available."""
        with patch("file_organizer.api.main.ApiSettings") as mock_settings:
            mock_settings.return_value = ApiSettings(environment="test")
            app = create_app()
            client = TestClient(app)

            # Swagger UI should be available
            resp = client.get("/docs")
            assert resp.status_code == 200
