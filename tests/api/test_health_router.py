"""Tests for the health check API router."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_settings
from file_organizer.api.exceptions import setup_exception_handlers
from file_organizer.api.routers.health import router


def _build_app() -> tuple[FastAPI, TestClient]:
    """Create a FastAPI app with health router."""
    from file_organizer.api.routers.health import reset_startup_time

    reset_startup_time()
    settings = ApiSettings(environment="test")
    app = FastAPI()
    setup_exception_handlers(app)
    app.dependency_overrides[get_settings] = lambda: settings
    app.include_router(router, prefix="/api/v1")
    client = TestClient(app)
    return app, client


# ---------------------------------------------------------------------------
# health endpoint
# ---------------------------------------------------------------------------


@pytest.mark.ci
@pytest.mark.unit
class TestHealthEndpoint:
    """Tests for GET /api/v1/health."""

    def test_health_ok(self) -> None:
        """Test health check with status ok."""
        _, client = _build_app()

        with patch("file_organizer.api.service_facade.ServiceFacade") as mock_facade_class:
            mock_facade = AsyncMock()
            mock_facade_class.return_value = mock_facade
            mock_facade.health_check.return_value = {
                "status": "ok",
                "version": "2.0.0",
                "ollama": True,
            }

            resp = client.get("/api/v1/health")
            assert resp.status_code == 200
            body = resp.json()
            assert body["status"] == "ok"
            assert body["readiness"] == "ready"
            assert body["version"] == "2.0.0"
            assert body["ollama"] is True
            assert "uptime" in body
            assert 0 <= body["uptime"] < 5  # Should be small for unit test startup

    def test_health_degraded(self) -> None:
        """Test health check with degraded status."""
        _, client = _build_app()

        with patch("file_organizer.api.service_facade.ServiceFacade") as mock_facade_class:
            mock_facade = AsyncMock()
            mock_facade_class.return_value = mock_facade
            mock_facade.health_check.return_value = {
                "status": "degraded",
                "version": "2.0.0",
                "ollama": False,
            }

            resp = client.get("/api/v1/health")
            assert resp.status_code == 207
            body = resp.json()
            assert body["status"] == "degraded"
            assert body["readiness"] == "starting"
            assert body["ollama"] is False

    def test_health_llama_cpp_unknown_maps_to_ready(self) -> None:
        """llama_cpp provider should surface unknown status as ready readiness."""
        _, client = _build_app()

        with patch("file_organizer.api.service_facade.ServiceFacade") as mock_facade_class:
            mock_facade = AsyncMock()
            mock_facade_class.return_value = mock_facade
            mock_facade.health_check.return_value = {
                "status": "unknown",
                "version": "2.0.0",
                "provider": "llama_cpp",
                "ollama": False,
            }

            resp = client.get("/api/v1/health")
            assert resp.status_code == 200
            body = resp.json()
            assert body["status"] == "unknown"
            assert body["readiness"] == "ready"
            assert body["provider"] == "llama_cpp"
            assert body["ollama"] is False

    def test_health_mlx_unknown_maps_to_ready(self) -> None:
        """mlx provider should surface unknown status as ready readiness."""
        _, client = _build_app()

        with patch("file_organizer.api.service_facade.ServiceFacade") as mock_facade_class:
            mock_facade = AsyncMock()
            mock_facade_class.return_value = mock_facade
            mock_facade.health_check.return_value = {
                "status": "unknown",
                "version": "2.0.0",
                "provider": "mlx",
                "ollama": False,
            }

            resp = client.get("/api/v1/health")
            assert resp.status_code == 200
            body = resp.json()
            assert body["status"] == "unknown"
            assert body["readiness"] == "ready"
            assert body["provider"] == "mlx"
            assert body["ollama"] is False

    def test_health_error(self) -> None:
        """Test health check with error status."""
        _, client = _build_app()

        with patch("file_organizer.api.service_facade.ServiceFacade") as mock_facade_class:
            mock_facade = AsyncMock()
            mock_facade_class.return_value = mock_facade
            mock_facade.health_check.return_value = {
                "status": "error",
                "version": "",
                "ollama": False,
            }

            resp = client.get("/api/v1/health")
            assert resp.status_code == 503
            body = resp.json()
            assert body["status"] == "error"
            assert body["readiness"] == "unhealthy"

    def test_health_exception_handling(self) -> None:
        """Test health check handles exceptions gracefully."""
        _, client = _build_app()

        with patch("file_organizer.api.service_facade.ServiceFacade") as mock_facade_class:
            mock_facade = AsyncMock()
            mock_facade_class.return_value = mock_facade
            mock_facade.health_check.side_effect = RuntimeError("Service unavailable")

            resp = client.get("/api/v1/health")
            assert resp.status_code == 503
            body = resp.json()
            assert body["status"] == "error"
            assert body["readiness"] == "unhealthy"
            assert body["version"] == ""

    def test_health_response_schema(self) -> None:
        """Test health response has correct schema."""
        _, client = _build_app()

        with patch("file_organizer.api.service_facade.ServiceFacade") as mock_facade_class:
            mock_facade = AsyncMock()
            mock_facade_class.return_value = mock_facade
            mock_facade.health_check.return_value = {
                "status": "ok",
                "version": "2.0.0",
                "ollama": True,
            }

            resp = client.get("/api/v1/health")
            assert resp.status_code == 200
            body = resp.json()

            # Verify schema
            assert isinstance(body["status"], str)
            assert isinstance(body["readiness"], str)
            assert isinstance(body["version"], str)
            assert isinstance(body["ollama"], bool)
            assert isinstance(body["uptime"], (int, float))

    def test_health_status_readiness_mapping(self) -> None:
        """Test status to readiness mapping is correct."""
        _, client = _build_app()

        test_cases = [
            ("ok", 200, "ready"),
            ("degraded", 207, "starting"),
            ("unknown", 200, "ready"),
            ("error", 503, "unhealthy"),
        ]

        for status, expected_code, expected_readiness in test_cases:
            with patch("file_organizer.api.service_facade.ServiceFacade") as mock_facade_class:
                mock_facade = AsyncMock()
                mock_facade_class.return_value = mock_facade
                mock_facade.health_check.return_value = {
                    "status": status,
                    "version": "2.0.0",
                    "ollama": True,
                }

                resp = client.get("/api/v1/health")
                assert resp.status_code == expected_code
                body = resp.json()
                assert body["status"] == status
                assert body["readiness"] == expected_readiness

    def test_health_missing_payload_fields(self) -> None:
        """Test health check handles missing payload fields."""
        _, client = _build_app()

        with patch("file_organizer.api.service_facade.ServiceFacade") as mock_facade_class:
            mock_facade = AsyncMock()
            mock_facade_class.return_value = mock_facade
            # Return minimal payload
            mock_facade.health_check.return_value = {
                "status": "ok",
            }

            resp = client.get("/api/v1/health")
            assert resp.status_code == 200
            body = resp.json()
            assert body["status"] == "ok"
            assert body["version"] == ""
            assert body["ollama"] is False
            assert 0 <= body["uptime"] < 5  # Should be small for unit test startup

    def test_health_uptime_increases(self) -> None:
        """Test that uptime increases over time."""
        _, client = _build_app()

        with patch("file_organizer.api.service_facade.ServiceFacade") as mock_facade_class:
            mock_facade = AsyncMock()
            mock_facade_class.return_value = mock_facade
            mock_facade.health_check.return_value = {
                "status": "ok",
                "version": "2.0.0",
                "ollama": True,
            }

            resp1 = client.get("/api/v1/health")
            uptime1 = resp1.json()["uptime"]

            resp2 = client.get("/api/v1/health")
            uptime2 = resp2.json()["uptime"]

            # Uptime should be non-decreasing (time.time() advances monotonically)
            assert uptime2 >= uptime1

    def test_reset_startup_time_updates_module_state(self) -> None:
        """reset_startup_time() resets the module-level _startup_time."""
        from file_organizer.api.routers import health

        # Force a stale timestamp, then verify reset overwrites it
        old = health._startup_time
        health._startup_time = old - 100.0  # artificially stale
        health.reset_startup_time()
        assert health._startup_time >= old  # at least as recent as before
