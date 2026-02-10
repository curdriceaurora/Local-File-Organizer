"""API tests for file operations."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_settings
from file_organizer.api.main import create_app

pytestmark = pytest.mark.ci


def _client() -> TestClient:
    settings = ApiSettings(environment="test", enable_docs=False)
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


def test_list_and_info_and_content(tmp_path: Path) -> None:
    sample = tmp_path / "sample.txt"
    sample.write_text("hello api")
    client = _client()

    resp = client.get("/api/v1/files", params={"path": str(tmp_path)})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["total"] == 1
    assert payload["items"][0]["name"] == "sample.txt"

    info = client.get("/api/v1/files/info", params={"path": str(sample)})
    assert info.status_code == 200
    assert info.json()["name"] == "sample.txt"

    content = client.get("/api/v1/files/content", params={"path": str(sample)})
    assert content.status_code == 200
    assert "hello api" in content.json()["content"]


def test_move_and_delete(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("move me")
    dest = tmp_path / "nested" / "dest.txt"

    client = _client()
    move_resp = client.post(
        "/api/v1/files/move",
        json={
            "source": str(source),
            "destination": str(dest),
            "overwrite": False,
            "dry_run": False,
        },
    )
    assert move_resp.status_code == 200
    assert dest.exists()

    delete_resp = client.request(
        "DELETE",
        "/api/v1/files",
        json={
            "path": str(dest),
            "permanent": True,
            "dry_run": False,
        },
    )
    assert delete_resp.status_code == 200
    assert not dest.exists()
