"""API tests for deduplication endpoints."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_settings
from file_organizer.api.main import create_app

pytestmark = pytest.mark.ci


def _client(allowed_paths: list[str] | None = None) -> TestClient:
    settings = ApiSettings(
        environment="test",
        enable_docs=False,
        allowed_paths=allowed_paths or [str(Path.home())],
    )
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


def test_dedupe_scan_and_preview(tmp_path: Path) -> None:
    file_a = tmp_path / "a.txt"
    file_b = tmp_path / "b.txt"
    file_a.write_text("duplicate")
    file_b.write_text("duplicate")

    client = _client([str(tmp_path)])
    payload = {
        "path": str(tmp_path),
        "recursive": False,
        "algorithm": "sha256",
    }

    scan = client.post("/api/v1/dedupe/scan", json=payload)
    assert scan.status_code == 200
    assert len(scan.json()["duplicates"]) >= 1

    preview = client.post("/api/v1/dedupe/preview", json=payload)
    assert preview.status_code == 200
    assert len(preview.json()["preview"]) >= 1


def test_dedupe_execute_dry_run(tmp_path: Path) -> None:
    file_a = tmp_path / "a.txt"
    file_b = tmp_path / "b.txt"
    file_a.write_text("duplicate")
    file_b.write_text("duplicate")

    client = _client([str(tmp_path)])
    payload = {
        "path": str(tmp_path),
        "recursive": False,
        "algorithm": "sha256",
        "dry_run": True,
        "trash": True,
    }

    execute = client.post("/api/v1/dedupe/execute", json=payload)
    assert execute.status_code == 200
    assert execute.json()["dry_run"] is True
