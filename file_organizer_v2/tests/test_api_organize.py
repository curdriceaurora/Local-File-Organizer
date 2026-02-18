"""API tests for organize endpoints."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from file_organizer.api.test_utils import create_auth_client
from file_organizer.core.organizer import OrganizationResult

pytestmark = pytest.mark.ci


class DummyOrganizer:
    def __init__(self, *args, **kwargs) -> None:
        pass

    def organize(
        self, input_path: str | Path, output_path: str | Path, skip_existing: bool = True
    ) -> OrganizationResult:
        return OrganizationResult(
            total_files=1,
            processed_files=1,
            skipped_files=0,
            failed_files=0,
            processing_time=0.01,
            organized_structure={"test": ["sample.txt"]},
            errors=[],
        )


def _client(
    tmp_path: Path,
    allowed_paths: list[str] | None = None,
) -> tuple[TestClient, dict[str, str]]:
    client, headers, _ = create_auth_client(
        tmp_path,
        allowed_paths=allowed_paths or [str(Path.home())],
    )
    return client, headers


def test_scan_endpoint(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "sample.txt").write_text("hello")
    client, headers = _client(tmp_path, [str(data_dir)])

    resp = client.post(
        "/api/v1/organize/scan",
        json={"input_dir": str(data_dir), "recursive": False, "include_hidden": False},
        headers=headers,
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["total_files"] == 1
    assert payload["counts"]["text"] == 1


def test_preview_and_execute(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import file_organizer.api.routers.organize as organize_router

    monkeypatch.setattr(organize_router, "FileOrganizer", DummyOrganizer)
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    client, headers = _client(tmp_path, [str(data_dir)])

    request = {
        "input_dir": str(data_dir),
        "output_dir": str(data_dir / "out"),
        "skip_existing": True,
        "dry_run": True,
        "use_hardlinks": True,
        "run_in_background": False,
    }

    preview = client.post("/api/v1/organize/preview", json=request, headers=headers)
    assert preview.status_code == 200
    assert preview.json()["processed_files"] == 1

    execute = client.post("/api/v1/organize/execute", json=request, headers=headers)
    assert execute.status_code == 200
    assert execute.json()["status"] == "completed"
