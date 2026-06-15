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

    @pytest.fixture()
    def mock_setup_completed(self):
        """Mock ConfigManager to report setup as completed."""
        with patch("file_organizer.web.router.ConfigManager") as mock_cm:
            mock_cm.return_value.load.return_value.setup_completed = True
            yield mock_cm

    def test_home_returns_200(self, client, mock_setup_completed):
        with patch("file_organizer.web.router.templates") as mock_tpl:
            mock_tpl.TemplateResponse.return_value = HTMLResponse("<html>home</html>")
            response = client.get("/ui/")
        assert response.status_code == 200

    def test_home_uses_index_template(self, client, mock_setup_completed):
        with patch("file_organizer.web.router.templates") as mock_tpl:
            mock_tpl.TemplateResponse.return_value = HTMLResponse("<html></html>")
            client.get("/ui/")
        call_args = mock_tpl.TemplateResponse.call_args
        assert call_args is not None
        assert call_args[0][1] == "index.html"

    def test_home_response_body(self, client, mock_setup_completed):
        with patch("file_organizer.web.router.templates") as mock_tpl:
            mock_tpl.TemplateResponse.return_value = HTMLResponse("<html>home-page</html>")
            response = client.get("/ui/")
        assert "home-page" in response.text

    def test_home_redirects_when_setup_incomplete(self, client):
        with patch("file_organizer.web.router.ConfigManager") as mock_cm:
            mock_cm.return_value.load.return_value.setup_completed = False
            response = client.get("/ui/", follow_redirects=False)
        assert response.status_code == 303
        assert "/ui/setup" in response.headers["location"]


def _mounted_app_paths() -> list[str]:
    """Concrete route paths after mounting the web router as the app does.

    Starlette 1.3 (#1282) no longer surfaces included sub-router paths on a bare
    ``APIRouter.routes`` (it only shows ``/``), so inspecting ``router.routes``
    directly is unreliable. Mount the router into a fresh ``FastAPI`` app at
    ``/ui`` (mirroring the real app) and read the assembled, flattened routes —
    a runtime-faithful assertion of sub-router inclusion.
    """
    app = FastAPI()
    app.include_router(router, prefix="/ui")
    return [route.path for route in app.routes if hasattr(route, "path")]


class TestSubRouterInclusion:
    """Verify that sub-routers are included (and reachable) under ``/ui``.

    Asserts exact base-route membership (not substring) so an unrelated path
    like ``/ui/files-legacy`` can't satisfy the guard (Copilot/CodeRabbit #1283).
    Each sub-router exposes a concrete base route at ``/ui/<name>``.
    """

    def test_files_router_routes_present(self):
        assert "/ui/files" in set(_mounted_app_paths())

    def test_organize_router_routes_present(self):
        assert "/ui/organize" in set(_mounted_app_paths())

    def test_profile_router_routes_present(self):
        assert "/ui/profile" in set(_mounted_app_paths())

    def test_settings_router_routes_present(self):
        assert "/ui/settings" in set(_mounted_app_paths())

    def test_marketplace_router_routes_present(self):
        assert "/ui/marketplace" in set(_mounted_app_paths())
