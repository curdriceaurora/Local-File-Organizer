"""API tests for file operations."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import pytest
from fastapi.testclient import TestClient

from file_organizer.api.config import ApiSettings
from file_organizer.api.main import create_app

pytestmark = pytest.mark.ci


def _client(allowed_paths: Optional[list[str]] = None) -> TestClient:
    settings = ApiSettings(
        environment="test",
        enable_docs=False,
        allowed_paths=allowed_paths or [],
    )
    app = create_app(settings)
    return TestClient(app)


def test_list_and_info_and_content(tmp_path: Path) -> None:
    sample = tmp_path / "sample.txt"
    sample.write_text("hello api")
    client = _client([str(tmp_path)])

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

    client = _client([str(tmp_path)])
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


def test_path_not_allowed(tmp_path: Path) -> None:
    allowed_root = tmp_path / "allowed"
    allowed_root.mkdir()
    disallowed_root = tmp_path / "disallowed"
    disallowed_root.mkdir()
    outside = disallowed_root / "outside.txt"
    outside.write_text("nope")

    client = _client([str(allowed_root)])
    resp = client.get("/api/v1/files/info", params={"path": str(outside)})
    assert resp.status_code == 403
    assert resp.json()["error"] == "path_not_allowed"


def test_error_responses(tmp_path: Path) -> None:
    client = _client([str(tmp_path)])

    missing = tmp_path / "missing.txt"
    resp = client.get("/api/v1/files", params={"path": str(missing)})
    assert resp.status_code == 404

    resp = client.get("/api/v1/files/info", params={"path": str(tmp_path)})
    assert resp.status_code == 400

    source = tmp_path / "source.txt"
    source.write_text("data")
    dest = tmp_path / "dest.txt"
    dest.write_text("exists")
    move_resp = client.post(
        "/api/v1/files/move",
        json={
            "source": str(source),
            "destination": str(dest),
            "overwrite": False,
            "dry_run": False,
        },
    )
    assert move_resp.status_code == 409

    dir_dest = tmp_path / "dir-dest"
    dir_dest.mkdir()
    overwrite_resp = client.post(
        "/api/v1/files/move",
        json={
            "source": str(source),
            "destination": str(dir_dest),
            "overwrite": True,
            "allow_directory_overwrite": False,
            "dry_run": False,
        },
    )
    assert overwrite_resp.status_code == 400

    delete_resp = client.request(
        "DELETE",
        "/api/v1/files",
        json={
            "path": str(missing),
            "permanent": True,
            "dry_run": False,
        },
    )
    assert delete_resp.status_code == 404
