"""Tests for the /health REST endpoint (issue #558).

The endpoint must act as the authoritative readiness probe for the Tauri
sidecar: it must respond quickly (< 500 ms), carry all required fields, and
return the correct HTTP status code based on Ollama availability.
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from file_organizer.api.routers.health import router
from file_organizer.version import __version__

pytestmark = [pytest.mark.unit, pytest.mark.ci]

# ---------------------------------------------------------------------------
# Test fixtures / helpers
# ---------------------------------------------------------------------------

_PATCH_TARGET = "file_organizer.api.service_facade.ServiceFacade.health_check"


def _build_client() -> TestClient:
    """Return a TestClient wrapping a minimal app with only the health router."""
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _mock_health(ollama: bool) -> dict[str, object]:
    """Return a mock health_check payload.

    Mirrors the real ``ServiceFacade.health_check`` behaviour: ``status`` is
    ``"ok"`` when Ollama is reachable, ``"degraded"`` otherwise.
    """
    return {
        "status": "ok" if ollama else "degraded",
        "version": __version__,
        "ollama": ollama,
    }


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------


class TestHealthEndpoint:
    """Tests for GET /health."""

    def test_happy_path_ollama_reachable_returns_200(self) -> None:
        """When Ollama is reachable, status='ok' and HTTP 200 is returned."""
        client = _build_client()
        with patch(_PATCH_TARGET, new_callable=AsyncMock, return_value=_mock_health(ollama=True)):
            resp = client.get("/health")

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["ollama"] is True

    def test_degraded_ollama_unreachable_returns_207(self) -> None:
        """When Ollama is unreachable, status='degraded' and HTTP 207 is returned."""
        client = _build_client()
        with patch(_PATCH_TARGET, new_callable=AsyncMock, return_value=_mock_health(ollama=False)):
            resp = client.get("/health")

        assert resp.status_code == 207
        body = resp.json()
        assert body["status"] == "degraded"
        assert body["ollama"] is False

    def test_response_shape_contains_all_required_fields(self) -> None:
        """GET /health must include status, version, ollama, and uptime fields."""
        client = _build_client()
        with patch(_PATCH_TARGET, new_callable=AsyncMock, return_value=_mock_health(ollama=True)):
            resp = client.get("/health")

        body = resp.json()
        assert "status" in body, "Missing 'status' field"
        assert "version" in body, "Missing 'version' field"
        assert "ollama" in body, "Missing 'ollama' field"
        assert "uptime" in body, "Missing 'uptime' field"

    def test_response_time_under_500ms(self) -> None:
        """GET /health must respond in under 500 ms even when Ollama is unreachable."""
        client = _build_client()
        with patch(_PATCH_TARGET, new_callable=AsyncMock, return_value=_mock_health(ollama=False)):
            start = time.monotonic()
            resp = client.get("/health")
            elapsed = time.monotonic() - start

        assert resp.status_code in (200, 207)
        assert elapsed < 0.5, f"Response took {elapsed:.3f}s, expected < 0.5s"

    def test_uptime_field_is_positive_float(self) -> None:
        """The uptime field must be a non-negative float representing seconds since startup."""
        client = _build_client()
        with patch(_PATCH_TARGET, new_callable=AsyncMock, return_value=_mock_health(ollama=True)):
            resp = client.get("/health")

        body = resp.json()
        uptime = body["uptime"]
        assert isinstance(uptime, float), f"uptime should be float, got {type(uptime)}"
        assert uptime >= 0.0, f"uptime should be non-negative, got {uptime}"

    def test_version_matches_package_version(self) -> None:
        """The version field in the health response must match the installed package version."""
        client = _build_client()
        with patch(_PATCH_TARGET, new_callable=AsyncMock, return_value=_mock_health(ollama=True)):
            resp = client.get("/health")

        body = resp.json()
        assert body["version"] == __version__
        assert isinstance(body["version"], str)
