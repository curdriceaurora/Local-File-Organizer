"""HTTP-level tests for the web router (``/ui/``) and sub-router inclusion.

Verifies that the home page route responds and that the expected sub-routers
are included in the main web router.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from starlette.testclient import TestClient

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_settings
from file_organizer.web.router import router

pytestmark = [pytest.mark.unit]

_HTML_OK = HTMLResponse("<html>ok</html>")


@pytest.fixture()
def settings(tmp_path):
    """Return a minimal ApiSettings pointing at a temp directory."""
    return ApiSettings(
        allowed_paths=[str(tmp_path)],
        auth_enabled=False,
        auth_db_path=str(tmp_path / "auth.db"),
    )


@pytest.fixture()
def client(settings):
    """Create a TestClient using a minimal FastAPI app with the web router."""
    app = FastAPI()
    app.dependency_overrides[get_settings] = lambda: settings
    app.include_router(router, prefix="/ui")
    return TestClient(app, raise_server_exceptions=False)


class TestHomeRoute:
    """Test the GET / (home) route."""

    def test_home_returns_200(self, client):
        with patch("file_organizer.web.router.templates") as mock_tpl:
            mock_tpl.TemplateResponse.return_value = HTMLResponse("<html>home</html>")
            response = client.get("/ui/")
        assert response.status_code == 200

    def test_home_uses_index_template(self, client):
        with patch("file_organizer.web.router.templates") as mock_tpl:
            mock_tpl.TemplateResponse.return_value = HTMLResponse("<html></html>")
            client.get("/ui/")
        call_args = mock_tpl.TemplateResponse.call_args
        assert call_args is not None
        assert "index.html" in str(call_args)

    def test_home_response_body(self, client):
        with patch("file_organizer.web.router.templates") as mock_tpl:
            mock_tpl.TemplateResponse.return_value = HTMLResponse("<html>home-page</html>")
            response = client.get("/ui/")
        assert "home-page" in response.text


class TestSubRouterInclusion:
    """Verify that sub-routers are included in the main router."""

    def test_files_router_routes_present(self):
        paths = [r.path for r in router.routes]
        assert "/files" in paths or any("/files" in p for p in paths)

    def test_organize_router_routes_present(self):
        paths = [r.path for r in router.routes]
        assert "/organize" in paths or any("/organize" in p for p in paths)

    def test_profile_router_routes_present(self):
        paths = [r.path for r in router.routes]
        assert "/profile" in paths or any("/profile" in p for p in paths)

    def test_settings_router_routes_present(self):
        paths = [r.path for r in router.routes]
        assert any("settings" in str(p) for p in paths)

    def test_marketplace_router_routes_present(self):
        paths = [r.path for r in router.routes]
        assert any("marketplace" in str(p) for p in paths)
