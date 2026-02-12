"""Tests for the web UI routing and template rendering."""
from __future__ import annotations

import base64
import importlib
import re
import time
from pathlib import Path
from typing import Optional

from fastapi.testclient import TestClient

from file_organizer.api.main import create_app
from file_organizer.api.test_utils import build_test_settings
from file_organizer.core.organizer import OrganizationResult

_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8"
    "/w8AAn8B9p4n9QAAAABJRU5ErkJggg=="
)


def _build_client(tmp_path: Path, allowed_root: Optional[Path] = None) -> TestClient:
    allowed_paths = [str(allowed_root)] if allowed_root else []
    settings = build_test_settings(
        tmp_path,
        allowed_paths=allowed_paths,
        auth_overrides={"auth_enabled": False},
    )
    app = create_app(settings)
    return TestClient(app)


class DummyOrganizer:
    """Fast deterministic organizer used by web dashboard tests."""

    TEXT_EXTENSIONS = {".txt", ".md"}
    IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}
    VIDEO_EXTENSIONS = {".mp4"}
    AUDIO_EXTENSIONS = {".mp3"}
    CAD_EXTENSIONS = {".dxf", ".dwg"}

    def __init__(self, *args, **kwargs) -> None:
        self.dry_run = bool(kwargs.get("dry_run", False))

    def organize(
        self,
        input_path: str | Path,
        output_path: str | Path,
        skip_existing: bool = True,
    ) -> OrganizationResult:
        source = Path(input_path)
        files = sorted(path for path in source.rglob("*") if path.is_file() and not path.name.startswith("."))
        text_files = [path.name for path in files if path.suffix.lower() == ".txt"]
        image_files = [path.name for path in files if path.suffix.lower() in {".png", ".jpg", ".jpeg"}]
        other_files = [
            path.name
            for path in files
            if path.name not in set(text_files) and path.name not in set(image_files)
        ]
        structure: dict[str, list[str]] = {
            "Text": text_files,
            "Images": image_files,
            "Other": other_files,
        }
        return OrganizationResult(
            total_files=len(files),
            processed_files=len(files),
            skipped_files=0,
            failed_files=0,
            processing_time=0.01,
            organized_structure=structure,
            errors=[],
        )


def _extract_attr(html: str, attr_name: str) -> str:
    match = re.search(rf'{attr_name}=\"([a-fA-F0-9]+)\"', html)
    assert match is not None
    return match.group(1)


def _extract_input_value(html: str, input_name: str) -> str:
    match = re.search(rf'name=\"{re.escape(input_name)}\"[^>]*value=\"([^\"]+)\"', html)
    assert match is not None
    return match.group(1)


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


def test_file_browser_endpoints(tmp_path: Path) -> None:
    root = tmp_path / "library"
    root.mkdir()
    (root / "Photos").mkdir()
    (root / "note.txt").write_text("hello", encoding="utf-8")
    (root / "preview.png").write_bytes(_PNG_BYTES)
    (root / "report.pdf").write_bytes(b"%PDF-1.4\n%")

    client = _build_client(tmp_path, allowed_root=root)

    tree = client.get("/ui/files/tree")
    assert tree.status_code == 200
    assert root.name in tree.text

    listing = client.get("/ui/files/list", params={"path": str(root)})
    assert listing.status_code == 200
    assert "note.txt" in listing.text

    page = client.get("/ui/files", params={"path": str(root)})
    assert page.status_code == 200
    assert "data-file-browser" in page.text

    thumb = client.get(
        "/ui/files/thumbnail",
        params={"path": str(root / "preview.png"), "kind": "image"},
    )
    assert thumb.status_code == 200

    preview = client.get("/ui/files/preview", params={"path": str(root / "note.txt")})
    assert preview.status_code == 200
    assert "note.txt" in preview.text

    upload = client.post(
        "/ui/files/upload",
        data={"path": str(root)},
        files={"files": ("upload.txt", b"data")},
    )
    assert upload.status_code == 200
    assert (root / "upload.txt").exists()


def test_upload_rejects_hidden_files(tmp_path: Path) -> None:
    root = tmp_path / "library"
    root.mkdir()

    client = _build_client(tmp_path, allowed_root=root)
    response = client.post(
        "/ui/files/upload",
        data={"path": str(root)},
        files={"files": (".secret", b"data")},
    )
    assert response.status_code == 200
    assert "hidden files are not allowed" in response.text.lower()
    assert not (root / ".secret").exists()


def test_organize_dashboard_end_to_end(monkeypatch, tmp_path: Path) -> None:
    organize_mod = importlib.import_module("file_organizer.web.organize_routes")

    monkeypatch.setattr(organize_mod, "FileOrganizer", DummyOrganizer)
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "note.txt").write_text("hello", encoding="utf-8")
    (root / "photo.png").write_bytes(_PNG_BYTES)
    (root / "misc.bin").write_bytes(b"abc")

    client = _build_client(tmp_path, allowed_root=root)

    page = client.get("/ui/organize")
    assert page.status_code == 200
    assert "Organization dashboard" in page.text

    scan = client.post(
        "/ui/organize/scan",
        data={
            "input_dir": str(root),
            "output_dir": str(root / "organized"),
            "methodology": "para",
            "recursive": "1",
            "include_hidden": "0",
            "skip_existing": "1",
            "use_hardlinks": "1",
        },
    )
    assert scan.status_code == 200
    assert "Plan summary" in scan.text
    assert "Approve and execute" in scan.text
    plan_id = _extract_input_value(scan.text, "plan_id")

    execute = client.post(
        "/ui/organize/execute",
        data={
            "plan_id": plan_id,
            "dry_run": "0",
            "schedule_delay_minutes": "0",
        },
    )
    assert execute.status_code == 200
    job_id = _extract_attr(execute.text, "data-job-id")

    status_payload = {}
    for _ in range(10):
        status = client.get(f"/ui/organize/jobs/{job_id}/status", params={"format": "json"})
        assert status.status_code == 200
        status_payload = status.json()
        if status_payload["status"] in {"completed", "failed"}:
            break
        time.sleep(0.01)
    assert status_payload["status"] == "completed"
    assert status_payload["processed_files"] == 3

    history = client.get("/ui/organize/history")
    assert history.status_code == 200
    assert job_id[:12] in history.text

    stats = client.get("/ui/organize/stats")
    assert stats.status_code == 200
    assert "Total jobs" in stats.text
    assert "Success rate" in stats.text

    json_report = client.get(f"/ui/organize/report/{job_id}", params={"format": "json"})
    assert json_report.status_code == 200
    assert json_report.json()["job_id"] == job_id

    csv_report = client.get(f"/ui/organize/report/{job_id}", params={"format": "csv"})
    assert csv_report.status_code == 200
    assert "text/csv" in csv_report.headers["content-type"]
    assert "job_id" in csv_report.text


def test_organize_scan_blocks_outside_allowed_root(monkeypatch, tmp_path: Path) -> None:
    organize_mod = importlib.import_module("file_organizer.web.organize_routes")

    monkeypatch.setattr(organize_mod, "FileOrganizer", DummyOrganizer)
    root = tmp_path / "allowed"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()

    client = _build_client(tmp_path, allowed_root=root)
    scan = client.post(
        "/ui/organize/scan",
        data={
            "input_dir": str(outside),
            "output_dir": str(root / "organized"),
            "methodology": "content_based",
        },
    )
    assert scan.status_code == 200
    assert "outside allowed roots" in scan.text.lower()


def test_organize_scan_rejects_include_hidden(monkeypatch, tmp_path: Path) -> None:
    organize_mod = importlib.import_module("file_organizer.web.organize_routes")

    monkeypatch.setattr(organize_mod, "FileOrganizer", DummyOrganizer)
    root = tmp_path / "allowed"
    root.mkdir()
    (root / ".secret.txt").write_text("hidden", encoding="utf-8")

    client = _build_client(tmp_path, allowed_root=root)
    scan = client.post(
        "/ui/organize/scan",
        data={
            "input_dir": str(root),
            "output_dir": str(root / "organized"),
            "methodology": "content_based",
            "include_hidden": "1",
        },
    )
    assert scan.status_code == 200
    assert "not supported" in scan.text.lower()


def test_organize_schedule_and_cancel(monkeypatch, tmp_path: Path) -> None:
    organize_mod = importlib.import_module("file_organizer.web.organize_routes")

    monkeypatch.setattr(organize_mod, "FileOrganizer", DummyOrganizer)
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "note.txt").write_text("hello", encoding="utf-8")

    client = _build_client(tmp_path, allowed_root=root)

    scan = client.post(
        "/ui/organize/scan",
        data={
            "input_dir": str(root),
            "output_dir": str(root / "organized"),
            "methodology": "johnny_decimal",
        },
    )
    assert scan.status_code == 200
    plan_id = _extract_input_value(scan.text, "plan_id")

    execute = client.post(
        "/ui/organize/execute",
        data={
            "plan_id": plan_id,
            "dry_run": "0",
            "schedule_delay_minutes": "1",
        },
    )
    assert execute.status_code == 200
    assert "scheduled to start" in execute.text.lower()
    assert "Cancel scheduled job" in execute.text
    job_id = _extract_attr(execute.text, "data-job-id")

    cancel = client.post(f"/ui/organize/jobs/{job_id}/cancel")
    assert cancel.status_code == 200
    assert "cancelled" in cancel.text.lower()


def test_organize_events_emit_keepalive_until_complete(monkeypatch, tmp_path: Path) -> None:
    organize_mod = importlib.import_module("file_organizer.web.organize_routes")

    class FakeJob:
        def __init__(self, job_id: str) -> None:
            self.job_id = job_id

    calls = {"count": 0}

    def fake_build_job_view(job_id: str) -> dict[str, object]:
        calls["count"] += 1
        if calls["count"] < 4:
            return {"job_id": job_id, "status": "running", "is_terminal": False}
        return {"job_id": job_id, "status": "completed", "is_terminal": True}

    monkeypatch.setattr(organize_mod, "_build_job_view", fake_build_job_view)
    monkeypatch.setattr(organize_mod, "ORGANIZE_EVENT_POLL_SECONDS", 0.001)
    monkeypatch.setattr(
        organize_mod,
        "list_jobs",
        lambda *, job_type=None, statuses=None, limit=100: [FakeJob("job-1")],
    )

    client = _build_client(tmp_path)
    payload = ""
    with client.stream("GET", "/ui/organize/jobs/job-1/events") as response:
        assert response.status_code == 200
        for chunk in response.iter_text():
            payload += chunk
            if "event: complete" in payload:
                break

    assert "event: status" in payload
    assert ": keep-alive" in payload
    assert "event: complete" in payload


def test_job_metadata_prunes_stale_entries(monkeypatch, tmp_path: Path) -> None:
    organize_mod = importlib.import_module("file_organizer.web.organize_routes")

    class FakeJob:
        def __init__(self, job_id: str) -> None:
            self.job_id = job_id

    monkeypatch.setattr(organize_mod, "get_job", lambda job_id: FakeJob(job_id) if job_id == "keep" else None)
    monkeypatch.setattr(organize_mod, "JOB_METADATA_PRUNE_INTERVAL_SECONDS", 0.0)

    organize_mod._JOB_METADATA.clear()
    organize_mod._LAST_JOB_METADATA_PRUNE_MONOTONIC = 0.0
    organize_mod._set_job_metadata("stale", {"value": 1})
    organize_mod._set_job_metadata("keep", {"value": 2})

    assert "keep" in organize_mod._JOB_METADATA
    assert "stale" not in organize_mod._JOB_METADATA
    organize_mod._JOB_METADATA.clear()
