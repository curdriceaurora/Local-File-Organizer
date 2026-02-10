"""API tests for system endpoints."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from file_organizer.api.test_utils import create_auth_client

pytestmark = pytest.mark.ci


def _client(
    tmp_path: Path,
    allowed_paths: list[str] | None = None,
    admin: bool = False,
) -> tuple[TestClient, dict[str, str]]:
    client, headers, _ = create_auth_client(
        tmp_path,
        allowed_paths=allowed_paths or [],
        admin=admin,
    )
    return client, headers


def test_system_status(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    client, headers = _client(tmp_path, [str(data_dir)])
    resp = client.get("/api/v1/system/status", params={"path": str(data_dir)}, headers=headers)
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["environment"] == "test"
    assert payload["disk_total"] >= payload["disk_used"]


def test_system_config_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_dir = tmp_path / "config"
    monkeypatch.setenv("FO_CONFIG_DIR", str(config_dir))

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    client, headers = _client(tmp_path, [str(data_dir)], admin=True)
    resp = client.get("/api/v1/system/config", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["profile"] == "default"

    update = client.patch(
        "/api/v1/system/config",
        json={"profile": "default", "default_methodology": "para"},
        headers=headers,
    )
    assert update.status_code == 200
    assert update.json()["config"]["default_methodology"] == "para"


def test_system_config_requires_admin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_dir = tmp_path / "config"
    monkeypatch.setenv("FO_CONFIG_DIR", str(config_dir))

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    client, headers = _client(tmp_path, [str(data_dir)], admin=False)
    update = client.patch(
        "/api/v1/system/config",
        json={"profile": "default", "default_methodology": "para"},
        headers=headers,
    )
    assert update.status_code == 403


def test_system_stats(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "sample.txt").write_text("stats")
    client, headers = _client(tmp_path, [str(data_dir)])
    resp = client.get("/api/v1/system/stats", params={"path": str(data_dir)}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["file_count"] == 1
