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
            mock_cm.return_value.load.return_value.setup_deferred = False
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
            mock_cm.return_value.load.return_value.setup_deferred = False
            response = client.get("/ui/", follow_redirects=False)
        assert response.status_code == 303
        assert "/ui/setup" in response.headers["location"]

    def test_home_renders_when_setup_deferred(self, client):
        with (
            patch("file_organizer.web.router.ConfigManager") as mock_cm,
            patch("file_organizer.web.router.templates") as mock_tpl,
        ):
            mock_cm.return_value.load.return_value.setup_completed = False
            mock_cm.return_value.load.return_value.setup_deferred = True
            mock_tpl.TemplateResponse.return_value = HTMLResponse("<html>home</html>")
            response = client.get("/ui/", follow_redirects=False)

        assert response.status_code == 200
        context = mock_tpl.TemplateResponse.call_args[0][2]
        assert context["setup_deferred"] is True

    def test_defer_setup_marks_deferred_and_redirects(self, client):
        with patch("file_organizer.web.setup_routes.ConfigManager") as mock_cm:
            config = mock_cm.return_value.load.return_value
            config.setup_completed = True
            config.setup_deferred = False
            config.profile_name = "default"
            response = client.post("/ui/setup/defer", follow_redirects=False)

        assert response.status_code == 303
        assert response.headers["location"] == "/ui/"
        assert config.setup_completed is False
        assert config.setup_deferred is True
        mock_cm.return_value.save.assert_called_once_with(config, "default", force=True)


class TestSubRouterInclusion:
    """Verify that sub-routers are included (and reachable) under ``/ui``.

    Asserts each sub-router's concrete base route at ``/ui/<name>`` is reachable
    by issuing a real request through a mounted ``TestClient`` — the same runtime
    mechanism ``TestHomeRoute`` uses (and which passes in CI). A registered route
    responds (here ``200``); an *unincluded* sub-router would yield ``404``.

    This replaces the earlier ``app.routes`` introspection, which was fragile
    across FastAPI/Starlette versions (included sub-router paths are not reliably
    surfaced on a flattened ``app.routes`` under Starlette 1.3+, #1282) and broke
    nondeterministically under xdist. Targeting the *exact* base path keeps the
    guard precise: an unrelated path like ``/ui/files-legacy`` still 404s, so it
    can't satisfy the check (Copilot/CodeRabbit #1283).
    """

    @pytest.mark.parametrize(
        "base_path",
        ["/ui/files", "/ui/organize", "/ui/profile", "/ui/settings", "/ui/marketplace"],
    )
    def test_sub_router_base_route_reachable(self, client, base_path, tmp_path, monkeypatch):
        # ``/ui/marketplace`` instantiates ``MarketplaceService``, which creates
        # its home dir and writes ``metadata.json`` under ``FO_MARKETPLACE_HOME``
        # (defaulting to the real user config dir). Redirect it into ``tmp_path``
        # so this route-inclusion check stays hermetic and doesn't 500 on
        # read-only config homes.
        monkeypatch.setenv("FO_MARKETPLACE_HOME", str(tmp_path / "marketplace"))
        status = client.get(base_path).status_code
        # Require a success/redirect status (not merely "not 404"): a registered
        # but broken route returning 500/503 should fail this reachability guard,
        # while a missing sub-router (404) still fails as before.
        assert 200 <= status < 400, (
            f"{base_path} returned unexpected status {status} — expected a reachable "
            f"GET route under /ui (404 => sub-router not included; 5xx => route broken)"
        )
