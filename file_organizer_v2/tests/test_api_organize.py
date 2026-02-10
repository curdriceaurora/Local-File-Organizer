"""API tests for organize endpoints."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_settings
from file_organizer.api.main import create_app
from file_organizer.core.organizer import OrganizationResult

pytestmark = pytest.mark.ci


class DummyOrganizer:
    def __init__(self, *args, **kwargs) -> None:
        pass

    def organize(self, input_path: str | Path, output_path: str | Path, skip_existing: bool = True) -> OrganizationResult:
        return OrganizationResult(
            total_files=1,
            processed_files=1,
            skipped_files=0,
            failed_files=0,
            processing_time=0.01,
            organized_structure={"test": ["sample.txt"]},
            errors=[],
        )


def _client(allowed_paths: list[str] | None = None) -> TestClient:
    settings = ApiSettings(
        environment="test",
        enable_docs=False,
        allowed_paths=allowed_paths or [str(Path.home())],
    )
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


def test_scan_endpoint(tmp_path: Path) -> None:
    (tmp_path / "sample.txt").write_text("hello")
    client = _client([str(tmp_path)])

    resp = client.post(
        "/api/v1/organize/scan",
        json={"input_dir": str(tmp_path), "recursive": False, "include_hidden": False},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["total_files"] == 1
    assert payload["counts"]["text"] == 1


def test_preview_and_execute(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import file_organizer.api.routers.organize as organize_router

    monkeypatch.setattr(organize_router, "FileOrganizer", DummyOrganizer)
    client = _client([str(tmp_path)])

    request = {
        "input_dir": str(tmp_path),
        "output_dir": str(tmp_path / "out"),
        "skip_existing": True,
        "dry_run": True,
        "use_hardlinks": True,
        "run_in_background": False,
    }

    preview = client.post("/api/v1/organize/preview", json=request)
    assert preview.status_code == 200
    assert preview.json()["processed_files"] == 1

    execute = client.post("/api/v1/organize/execute", json=request)
    assert execute.status_code == 200
    assert execute.json()["status"] == "completed"
