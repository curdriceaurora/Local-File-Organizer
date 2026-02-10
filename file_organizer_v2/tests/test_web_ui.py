"""Tests for the web UI routing and template rendering."""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from file_organizer.api.main import create_app
from file_organizer.api.test_utils import build_test_settings


def _build_client(tmp_path: Path) -> TestClient:
    settings = build_test_settings(tmp_path, auth_overrides={"auth_enabled": False})
    app = create_app(settings)
    return TestClient(app)


def test_ui_routes_render(tmp_path: Path) -> None:
    client = _build_client(tmp_path)
    response = client.get("/ui/")
    assert response.status_code == 200
    assert "hx-boost" in response.text

    for path in ("/ui/files", "/ui/organize", "/ui/settings", "/ui/profile"):
        page = client.get(path)
        assert page.status_code == 200


def test_ui_static_assets(tmp_path: Path) -> None:
    client = _build_client(tmp_path)
    css = client.get("/static/css/styles.css")
    assert css.status_code == 200
    htmx = client.get("/static/js/htmx.min.js")
    assert htmx.status_code == 200
