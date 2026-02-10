"""API tests for system endpoints."""
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


def test_system_status(tmp_path: Path) -> None:
    client = _client([str(tmp_path)])
    resp = client.get("/api/v1/system/status", params={"path": str(tmp_path)})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["environment"] == "test"
    assert payload["disk_total"] >= payload["disk_used"]


def test_system_config_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_dir = tmp_path / "config"
    monkeypatch.setenv("FO_CONFIG_DIR", str(config_dir))

    client = _client([str(tmp_path)])
    resp = client.get("/api/v1/system/config")
    assert resp.status_code == 200
    assert resp.json()["profile"] == "default"

    update = client.patch(
        "/api/v1/system/config",
        json={"profile": "default", "default_methodology": "para"},
    )
    assert update.status_code == 200
    assert update.json()["config"]["default_methodology"] == "para"


def test_system_stats(tmp_path: Path) -> None:
    (tmp_path / "sample.txt").write_text("stats")
    client = _client([str(tmp_path)])
    resp = client.get("/api/v1/system/stats", params={"path": str(tmp_path)})
    assert resp.status_code == 200
    assert resp.json()["file_count"] == 1
