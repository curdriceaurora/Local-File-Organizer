"""API tests for file operations."""

from __future__ import annotations

from pathlib import Path

import pytest

from file_organizer.api.test_utils import create_auth_client

pytestmark = pytest.mark.ci


def test_list_and_info_and_content(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    sample = data_dir / "sample.txt"
    sample.write_text("hello api")
    client, headers, _ = create_auth_client(tmp_path, [str(data_dir)])

    resp = client.get("/api/v1/files", params={"path": str(data_dir)}, headers=headers)
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["total"] == 1
    assert payload["items"][0]["name"] == "sample.txt"

    info = client.get("/api/v1/files/info", params={"path": str(sample)}, headers=headers)
    assert info.status_code == 200
    assert info.json()["name"] == "sample.txt"

    content = client.get(
        "/api/v1/files/content",
        params={"path": str(sample)},
        headers=headers,
    )
    assert content.status_code == 200
    assert "hello api" in content.json()["content"]


def test_move_and_delete(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    source = data_dir / "source.txt"
    source.write_text("move me")
    dest = data_dir / "nested" / "dest.txt"

    client, headers, _ = create_auth_client(tmp_path, [str(data_dir)])
    move_resp = client.post(
        "/api/v1/files/move",
        json={
            "source": str(source),
            "destination": str(dest),
            "overwrite": False,
            "dry_run": False,
        },
        headers=headers,
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
        headers=headers,
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

    client, headers, _ = create_auth_client(tmp_path, [str(allowed_root)])
    resp = client.get("/api/v1/files/info", params={"path": str(outside)}, headers=headers)
    assert resp.status_code == 403
    assert resp.json()["error"] == "path_not_allowed"


def test_error_responses(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    client, headers, _ = create_auth_client(tmp_path, [str(data_dir)])

    missing = data_dir / "missing.txt"
    resp = client.get("/api/v1/files", params={"path": str(missing)}, headers=headers)
    assert resp.status_code == 404

    resp = client.get("/api/v1/files/info", params={"path": str(data_dir)}, headers=headers)
    assert resp.status_code == 400

    source = data_dir / "source.txt"
    source.write_text("data")
    dest = data_dir / "dest.txt"
    dest.write_text("exists")
    move_resp = client.post(
        "/api/v1/files/move",
        json={
            "source": str(source),
            "destination": str(dest),
            "overwrite": False,
            "dry_run": False,
        },
        headers=headers,
    )
    assert move_resp.status_code == 409

    dir_dest = data_dir / "dir-dest"
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
        headers=headers,
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
        headers=headers,
    )
    assert delete_resp.status_code == 404
