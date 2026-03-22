"""Integration tests for api/routers/health.py and api/routers/analyze.py.

Covers: GET /health with ok/degraded/error/unknown status, shape check;
        POST /analyze with no body, content text, file upload,
        ImportError → 503, generic exception → 500.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_settings
from file_organizer.api.exceptions import setup_exception_handlers
from file_organizer.api.routers.health import router as health_router

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def base_settings(tmp_path: Path) -> ApiSettings:
    return ApiSettings(
        allowed_paths=[str(tmp_path)],
        auth_enabled=False,
        auth_db_path=str(tmp_path / "auth.db"),
    )


@pytest.fixture()
def health_client(base_settings: ApiSettings) -> TestClient:
    app = FastAPI()
    app.dependency_overrides[get_settings] = lambda: base_settings
    setup_exception_handlers(app)
    app.include_router(health_router)
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------


_FACADE_PATH = "file_organizer.api.service_facade.ServiceFacade"


class TestHealthEndpoint:
    def _mock_facade(self, status: str) -> dict[str, object]:
        return {
            "status": status,
            "version": "1.0.0",
            "provider": "ollama",
            "ollama": status == "ok",
        }

    def test_health_ok_returns_200(self, health_client: TestClient) -> None:
        with patch(_FACADE_PATH) as mock_cls:
            mock_facade = MagicMock()
            mock_facade.health_check = AsyncMock(return_value=self._mock_facade("ok"))
            mock_cls.return_value = mock_facade
            r = health_client.get("/health")
        assert r.status_code == 200

    def test_health_ok_response_shape(self, health_client: TestClient) -> None:
        with patch(_FACADE_PATH) as mock_cls:
            mock_facade = MagicMock()
            mock_facade.health_check = AsyncMock(return_value=self._mock_facade("ok"))
            mock_cls.return_value = mock_facade
            r = health_client.get("/health")
        body = r.json()
        assert "status" in body
        assert "readiness" in body
        assert "uptime" in body

    def test_health_degraded_returns_207(self, health_client: TestClient) -> None:
        with patch(_FACADE_PATH) as mock_cls:
            mock_facade = MagicMock()
            mock_facade.health_check = AsyncMock(return_value=self._mock_facade("degraded"))
            mock_cls.return_value = mock_facade
            r = health_client.get("/health")
        assert r.status_code == 207
        assert r.json()["readiness"] == "starting"

    def test_health_error_returns_503(self, health_client: TestClient) -> None:
        with patch(_FACADE_PATH) as mock_cls:
            mock_facade = MagicMock()
            mock_facade.health_check = AsyncMock(return_value=self._mock_facade("error"))
            mock_cls.return_value = mock_facade
            r = health_client.get("/health")
        assert r.status_code == 503
        assert r.json()["readiness"] == "unhealthy"

    def test_health_unknown_status_ready(self, health_client: TestClient) -> None:
        with patch(_FACADE_PATH) as mock_cls:
            mock_facade = MagicMock()
            mock_facade.health_check = AsyncMock(return_value=self._mock_facade("unknown"))
            mock_cls.return_value = mock_facade
            r = health_client.get("/health")
        assert r.status_code == 200
        assert r.json()["readiness"] == "ready"

    def test_health_facade_exception_returns_503(self, health_client: TestClient) -> None:
        with patch(_FACADE_PATH) as mock_cls:
            mock_facade = MagicMock()
            mock_facade.health_check = AsyncMock(side_effect=RuntimeError("facade down"))
            mock_cls.return_value = mock_facade
            r = health_client.get("/health")
        assert r.status_code == 503

    def test_health_uptime_is_positive(self, health_client: TestClient) -> None:
        with patch(_FACADE_PATH) as mock_cls:
            mock_facade = MagicMock()
            mock_facade.health_check = AsyncMock(return_value=self._mock_facade("ok"))
            mock_cls.return_value = mock_facade
            r = health_client.get("/health")
        assert 0 <= r.json()["uptime"] < 300


# ---------------------------------------------------------------------------
# POST /analyze
# ---------------------------------------------------------------------------


@pytest.fixture()
def analyze_client(base_settings: ApiSettings) -> TestClient:
    from file_organizer.api.routers.analyze import router as analyze_router

    app = FastAPI()
    app.dependency_overrides[get_settings] = lambda: base_settings
    setup_exception_handlers(app)
    app.include_router(analyze_router)
    return TestClient(app, raise_server_exceptions=False)


def _patch_analyze_model(
    category: str = "Documents",
    description: str = "A text document",
    confidence: float = 0.85,
) -> tuple[object, ...]:
    """Return a stack of patches that bypass the real Ollama model."""
    return (
        patch("file_organizer.api.routers.analyze.get_text_model", return_value=MagicMock()),
        patch(
            "file_organizer.api.routers.analyze.generate_category",
            return_value=category,
        ),
        patch(
            "file_organizer.api.routers.analyze.generate_description",
            return_value=description,
        ),
        patch(
            "file_organizer.api.routers.analyze.calculate_confidence",
            return_value=confidence,
        ),
    )


class TestAnalyzeEndpoint:
    def test_no_content_no_file_returns_400(self, analyze_client: TestClient) -> None:
        r = analyze_client.post("/analyze")
        assert r.status_code == 400

    def test_content_returns_200(self, analyze_client: TestClient) -> None:
        p1, p2, p3, p4 = _patch_analyze_model()
        with p1, p2, p3, p4:
            r = analyze_client.post("/analyze", params={"content": "hello world document"})
        assert r.status_code == 200

    def test_response_has_required_fields(self, analyze_client: TestClient) -> None:
        p1, p2, p3, p4 = _patch_analyze_model()
        with p1, p2, p3, p4:
            r = analyze_client.post("/analyze", params={"content": "sample text"})
        body = r.json()
        assert "description" in body
        assert "category" in body
        assert "confidence" in body

    def test_response_values_match_mocked_model(self, analyze_client: TestClient) -> None:
        p1, p2, p3, p4 = _patch_analyze_model(
            category="Photos", description="A photo", confidence=0.9
        )
        with p1, p2, p3, p4:
            r = analyze_client.post("/analyze", params={"content": "image data"})
        body = r.json()
        assert body["category"] == "Photos"
        assert body["description"] == "A photo"
        assert body["confidence"] == pytest.approx(0.9)

    def test_file_upload_returns_200(self, analyze_client: TestClient) -> None:
        p1, p2, p3, p4 = _patch_analyze_model()
        with p1, p2, p3, p4:
            r = analyze_client.post(
                "/analyze",
                files={"file": ("doc.txt", BytesIO(b"file content here"), "text/plain")},
            )
        assert r.status_code == 200

    def test_import_error_returns_503(self, analyze_client: TestClient) -> None:
        with patch(
            "file_organizer.api.routers.analyze.get_text_model",
            side_effect=ImportError("ollama not found"),
        ):
            r = analyze_client.post("/analyze", params={"content": "text"})
        assert r.status_code == 503

    def test_generic_exception_returns_500(self, analyze_client: TestClient) -> None:
        with patch(
            "file_organizer.api.routers.analyze.get_text_model",
            side_effect=RuntimeError("model crashed"),
        ):
            r = analyze_client.post("/analyze", params={"content": "text"})
        assert r.status_code == 500
