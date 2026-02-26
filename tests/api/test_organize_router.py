"""Tests for the organize API router."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_current_active_user, get_settings
from file_organizer.api.exceptions import setup_exception_handlers
from file_organizer.api.routers.organize import router
from file_organizer.core.organizer import OrganizationResult


def _build_app(tmp_path: Path) -> tuple[FastAPI, TestClient, ApiSettings]:
    """Create a minimal FastAPI app with the organize router."""
    settings = ApiSettings(
        environment="test",
        auth_enabled=False,
        allowed_paths=[str(tmp_path)],
        auth_jwt_secret="test-secret",
        rate_limit_enabled=False,
    )
    app = FastAPI()
    setup_exception_handlers(app)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_current_active_user] = lambda: MagicMock(
        is_active=True, is_admin=True
    )
    app.include_router(router, prefix="/api/v1")
    client = TestClient(app)
    return app, client, settings


def _make_result(**overrides) -> OrganizationResult:
    """Build an OrganizationResult with sensible defaults."""
    defaults = {
        "total_files": 3,
        "processed_files": 2,
        "skipped_files": 1,
        "failed_files": 0,
        "processing_time": 1.5,
        "organized_structure": {"Documents": ["a.txt", "b.md"]},
        "errors": [],
    }
    defaults.update(overrides)
    return OrganizationResult(**defaults)


# ---------------------------------------------------------------------------
# scan_directory endpoint
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestScanDirectory:
    """Tests for POST /api/v1/organize/scan."""

    def test_scan_directory_success(self, tmp_path: Path) -> None:
        (tmp_path / "doc.txt").write_text("text")
        (tmp_path / "pic.jpg").write_bytes(b"\xff\xd8")
        _, client, _ = _build_app(tmp_path)

        resp = client.post(
            "/api/v1/organize/scan",
            json={"input_dir": str(tmp_path)},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_files"] == 2
        assert "text" in body["counts"]
        assert "image" in body["counts"]

    def test_scan_directory_not_found(self, tmp_path: Path) -> None:
        _, client, _ = _build_app(tmp_path)

        resp = client.post(
            "/api/v1/organize/scan",
            json={"input_dir": str(tmp_path / "missing")},
        )
        assert resp.status_code == 404

    def test_scan_recursive(self, tmp_path: Path) -> None:
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "deep.txt").write_text("deep")
        (tmp_path / "top.txt").write_text("top")
        _, client, _ = _build_app(tmp_path)

        resp = client.post(
            "/api/v1/organize/scan",
            json={"input_dir": str(tmp_path), "recursive": True},
        )
        assert resp.status_code == 200
        assert resp.json()["total_files"] == 2

    def test_scan_non_recursive(self, tmp_path: Path) -> None:
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "deep.txt").write_text("deep")
        (tmp_path / "top.txt").write_text("top")
        _, client, _ = _build_app(tmp_path)

        resp = client.post(
            "/api/v1/organize/scan",
            json={"input_dir": str(tmp_path), "recursive": False},
        )
        assert resp.status_code == 200
        assert resp.json()["total_files"] == 1

    def test_scan_hidden_files(self, tmp_path: Path) -> None:
        (tmp_path / ".hidden").write_text("hidden")
        (tmp_path / "visible.txt").write_text("visible")
        _, client, _ = _build_app(tmp_path)

        # Without include_hidden
        resp = client.post(
            "/api/v1/organize/scan",
            json={"input_dir": str(tmp_path), "include_hidden": False},
        )
        assert resp.json()["total_files"] == 1

        # With include_hidden
        resp = client.post(
            "/api/v1/organize/scan",
            json={"input_dir": str(tmp_path), "include_hidden": True},
        )
        assert resp.json()["total_files"] == 2

    def test_scan_single_file_path(self, tmp_path: Path) -> None:
        f = tmp_path / "solo.txt"
        f.write_text("solo")
        _, client, _ = _build_app(tmp_path)

        resp = client.post(
            "/api/v1/organize/scan",
            json={"input_dir": str(f)},
        )
        assert resp.status_code == 200
        assert resp.json()["total_files"] == 1

    def test_scan_counts_by_type(self, tmp_path: Path) -> None:
        (tmp_path / "a.txt").write_text("text")
        (tmp_path / "b.jpg").write_bytes(b"\xff\xd8")
        (tmp_path / "c.mp4").write_bytes(b"\x00")
        (tmp_path / "d.mp3").write_bytes(b"\x00")
        (tmp_path / "e.dxf").write_bytes(b"\x00")
        (tmp_path / "f.unknown").write_bytes(b"\x00")
        _, client, _ = _build_app(tmp_path)

        resp = client.post(
            "/api/v1/organize/scan",
            json={"input_dir": str(tmp_path)},
        )
        counts = resp.json()["counts"]
        assert counts["text"] >= 1
        assert counts["image"] >= 1
        assert counts["video"] >= 1
        assert counts["audio"] >= 1
        assert counts["cad"] >= 1
        assert counts["other"] >= 1


# ---------------------------------------------------------------------------
# preview_organization endpoint
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPreviewOrganization:
    """Tests for POST /api/v1/organize/preview."""

    @patch("file_organizer.api.routers.organize.FileOrganizer")
    def test_preview_success(self, mock_organizer_cls, tmp_path: Path) -> None:
        (tmp_path / "input").mkdir()
        (tmp_path / "output").mkdir()
        mock_instance = MagicMock()
        mock_instance.organize.return_value = _make_result()
        mock_organizer_cls.return_value = mock_instance
        _, client, _ = _build_app(tmp_path)

        resp = client.post(
            "/api/v1/organize/preview",
            json={
                "input_dir": str(tmp_path / "input"),
                "output_dir": str(tmp_path / "output"),
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_files"] == 3
        assert body["processed_files"] == 2
        # Preview always uses dry_run=True
        mock_organizer_cls.assert_called_once_with(dry_run=True, use_hardlinks=True)

    def test_preview_input_not_found(self, tmp_path: Path) -> None:
        (tmp_path / "output").mkdir()
        _, client, _ = _build_app(tmp_path)

        resp = client.post(
            "/api/v1/organize/preview",
            json={
                "input_dir": str(tmp_path / "missing"),
                "output_dir": str(tmp_path / "output"),
            },
        )
        assert resp.status_code == 404

    @patch("file_organizer.api.routers.organize.FileOrganizer")
    def test_preview_with_errors(self, mock_organizer_cls, tmp_path: Path) -> None:
        (tmp_path / "input").mkdir()
        (tmp_path / "output").mkdir()
        mock_instance = MagicMock()
        mock_instance.organize.return_value = _make_result(
            failed_files=1,
            errors=[("bad.txt", "Permission denied")],
        )
        mock_organizer_cls.return_value = mock_instance
        _, client, _ = _build_app(tmp_path)

        resp = client.post(
            "/api/v1/organize/preview",
            json={
                "input_dir": str(tmp_path / "input"),
                "output_dir": str(tmp_path / "output"),
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["failed_files"] == 1
        assert len(body["errors"]) == 1
        assert body["errors"][0]["file"] == "bad.txt"


# ---------------------------------------------------------------------------
# execute_organization endpoint
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExecuteOrganization:
    """Tests for POST /api/v1/organize/execute."""

    @patch("file_organizer.api.routers.organize.FileOrganizer")
    def test_execute_sync_success(self, mock_organizer_cls, tmp_path: Path) -> None:
        (tmp_path / "input").mkdir()
        (tmp_path / "output").mkdir()
        mock_instance = MagicMock()
        mock_instance.organize.return_value = _make_result()
        mock_organizer_cls.return_value = mock_instance
        _, client, _ = _build_app(tmp_path)

        resp = client.post(
            "/api/v1/organize/execute",
            json={
                "input_dir": str(tmp_path / "input"),
                "output_dir": str(tmp_path / "output"),
                "run_in_background": False,
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "completed"
        assert body["result"]["total_files"] == 3

    @patch("file_organizer.api.routers.organize.FileOrganizer")
    def test_execute_sync_failure(self, mock_organizer_cls, tmp_path: Path) -> None:
        (tmp_path / "input").mkdir()
        (tmp_path / "output").mkdir()
        mock_instance = MagicMock()
        mock_instance.organize.side_effect = RuntimeError("disk full")
        mock_organizer_cls.return_value = mock_instance
        _, client, _ = _build_app(tmp_path)

        resp = client.post(
            "/api/v1/organize/execute",
            json={
                "input_dir": str(tmp_path / "input"),
                "output_dir": str(tmp_path / "output"),
                "run_in_background": False,
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "failed"
        assert "disk full" in body["error"]

    @patch("file_organizer.api.routers.organize.create_job")
    def test_execute_background(self, mock_create_job, tmp_path: Path) -> None:
        (tmp_path / "input").mkdir()
        (tmp_path / "output").mkdir()
        mock_job = MagicMock()
        mock_job.job_id = "test-job-123"
        mock_create_job.return_value = mock_job
        _, client, _ = _build_app(tmp_path)

        resp = client.post(
            "/api/v1/organize/execute",
            json={
                "input_dir": str(tmp_path / "input"),
                "output_dir": str(tmp_path / "output"),
                "run_in_background": True,
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "queued"
        assert body["job_id"] == "test-job-123"

    def test_execute_input_not_found(self, tmp_path: Path) -> None:
        (tmp_path / "output").mkdir()
        _, client, _ = _build_app(tmp_path)

        resp = client.post(
            "/api/v1/organize/execute",
            json={
                "input_dir": str(tmp_path / "missing"),
                "output_dir": str(tmp_path / "output"),
                "run_in_background": False,
            },
        )
        assert resp.status_code == 404

    @patch("file_organizer.api.routers.organize.FileOrganizer")
    def test_execute_sync_with_dry_run(self, mock_organizer_cls, tmp_path: Path) -> None:
        (tmp_path / "input").mkdir()
        (tmp_path / "output").mkdir()
        mock_instance = MagicMock()
        mock_instance.organize.return_value = _make_result()
        mock_organizer_cls.return_value = mock_instance
        _, client, _ = _build_app(tmp_path)

        resp = client.post(
            "/api/v1/organize/execute",
            json={
                "input_dir": str(tmp_path / "input"),
                "output_dir": str(tmp_path / "output"),
                "run_in_background": False,
                "dry_run": True,
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "completed"
        mock_organizer_cls.assert_called_once_with(dry_run=True, use_hardlinks=True)

    @patch("file_organizer.api.routers.organize.FileOrganizer")
    def test_execute_sync_with_hardlinks_disabled(
        self, mock_organizer_cls, tmp_path: Path
    ) -> None:
        (tmp_path / "input").mkdir()
        (tmp_path / "output").mkdir()
        mock_instance = MagicMock()
        mock_instance.organize.return_value = _make_result()
        mock_organizer_cls.return_value = mock_instance
        _, client, _ = _build_app(tmp_path)

        resp = client.post(
            "/api/v1/organize/execute",
            json={
                "input_dir": str(tmp_path / "input"),
                "output_dir": str(tmp_path / "output"),
                "run_in_background": False,
                "use_hardlinks": False,
            },
        )
        assert resp.status_code == 200
        mock_organizer_cls.assert_called_once_with(dry_run=False, use_hardlinks=False)


# ---------------------------------------------------------------------------
# get_job_status endpoint
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetJobStatus:
    """Tests for GET /api/v1/organize/status/{job_id}."""

    @patch("file_organizer.api.routers.organize.get_job")
    def test_job_found(self, mock_get_job, tmp_path: Path) -> None:
        from datetime import UTC, datetime

        mock_job = MagicMock()
        mock_job.job_id = "job-1"
        mock_job.status = "completed"
        mock_job.created_at = datetime(2025, 1, 1, tzinfo=UTC)
        mock_job.updated_at = datetime(2025, 1, 1, tzinfo=UTC)
        mock_job.result = {
            "total_files": 5,
            "processed_files": 5,
            "skipped_files": 0,
            "failed_files": 0,
            "processing_time": 2.0,
            "organized_structure": {},
            "errors": [],
        }
        mock_job.error = None
        mock_get_job.return_value = mock_job
        _, client, _ = _build_app(tmp_path)

        resp = client.get("/api/v1/organize/status/job-1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["job_id"] == "job-1"
        assert body["status"] == "completed"
        assert body["result"]["total_files"] == 5

    @patch("file_organizer.api.routers.organize.get_job")
    def test_job_not_found(self, mock_get_job, tmp_path: Path) -> None:
        mock_get_job.return_value = None
        _, client, _ = _build_app(tmp_path)

        resp = client.get("/api/v1/organize/status/nonexistent")
        assert resp.status_code == 404

    @patch("file_organizer.api.routers.organize.get_job")
    def test_job_no_result(self, mock_get_job, tmp_path: Path) -> None:
        from datetime import UTC, datetime

        mock_job = MagicMock()
        mock_job.job_id = "job-2"
        mock_job.status = "running"
        mock_job.created_at = datetime(2025, 1, 1, tzinfo=UTC)
        mock_job.updated_at = datetime(2025, 1, 1, tzinfo=UTC)
        mock_job.result = None
        mock_job.error = None
        mock_get_job.return_value = mock_job
        _, client, _ = _build_app(tmp_path)

        resp = client.get("/api/v1/organize/status/job-2")
        assert resp.status_code == 200
        body = resp.json()
        assert body["result"] is None

    @patch("file_organizer.api.routers.organize.get_job")
    def test_job_failed_with_error(self, mock_get_job, tmp_path: Path) -> None:
        from datetime import UTC, datetime

        mock_job = MagicMock()
        mock_job.job_id = "job-3"
        mock_job.status = "failed"
        mock_job.created_at = datetime(2025, 1, 1, tzinfo=UTC)
        mock_job.updated_at = datetime(2025, 1, 1, tzinfo=UTC)
        mock_job.result = None
        mock_job.error = "Something went wrong"
        mock_get_job.return_value = mock_job
        _, client, _ = _build_app(tmp_path)

        resp = client.get("/api/v1/organize/status/job-3")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "failed"
        assert body["error"] == "Something went wrong"


# ---------------------------------------------------------------------------
# simple organize endpoint (POST /api/v1/organize)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSimpleOrganize:
    """Tests for POST /api/v1/organize."""

    def test_organize_with_file_upload(self, tmp_path: Path) -> None:
        _, client, _ = _build_app(tmp_path)

        resp = client.post(
            "/api/v1/organize",
            files={"file": ("report.pdf", b"pdf content", "application/pdf")},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["folder_name"] == "Documents"
        assert "organized" in body["filename"]
        assert body["confidence"] == 0.85

    def test_organize_image_file(self, tmp_path: Path) -> None:
        _, client, _ = _build_app(tmp_path)

        resp = client.post(
            "/api/v1/organize",
            files={"file": ("photo.jpg", b"\xff\xd8\xff", "image/jpeg")},
        )
        assert resp.status_code == 200
        assert resp.json()["folder_name"] == "Images"

    def test_organize_video_file(self, tmp_path: Path) -> None:
        _, client, _ = _build_app(tmp_path)

        resp = client.post(
            "/api/v1/organize",
            files={"file": ("clip.mp4", b"\x00\x00", "video/mp4")},
        )
        assert resp.status_code == 200
        assert resp.json()["folder_name"] == "Videos"

    def test_organize_audio_file(self, tmp_path: Path) -> None:
        _, client, _ = _build_app(tmp_path)

        resp = client.post(
            "/api/v1/organize",
            files={"file": ("song.mp3", b"\xff\xfb", "audio/mpeg")},
        )
        assert resp.status_code == 200
        assert resp.json()["folder_name"] == "Audio"

    def test_organize_unknown_extension(self, tmp_path: Path) -> None:
        _, client, _ = _build_app(tmp_path)

        resp = client.post(
            "/api/v1/organize",
            files={"file": ("data.xyz", b"data", "application/octet-stream")},
        )
        assert resp.status_code == 200
        assert resp.json()["folder_name"] == "Other"

    def test_organize_no_input_returns_error(self, tmp_path: Path) -> None:
        """When neither file nor request body is provided, returns 400 JSONResponse."""
        _, client, _ = _build_app(tmp_path)

        resp = client.post("/api/v1/organize")
        # The endpoint returns JSONResponse(status_code=400, ...) when no input
        assert resp.status_code in (400, 422)

    def test_organize_txt_extension(self, tmp_path: Path) -> None:
        _, client, _ = _build_app(tmp_path)

        resp = client.post(
            "/api/v1/organize",
            files={"file": ("notes.txt", b"my notes", "text/plain")},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["folder_name"] == "Documents"
        assert body["filename"] == "notes_organized.txt"

    def test_organize_md_extension(self, tmp_path: Path) -> None:
        _, client, _ = _build_app(tmp_path)

        resp = client.post(
            "/api/v1/organize",
            files={"file": ("readme.md", b"# Readme", "text/markdown")},
        )
        assert resp.status_code == 200
        assert resp.json()["folder_name"] == "Documents"

    def test_organize_gif_extension(self, tmp_path: Path) -> None:
        _, client, _ = _build_app(tmp_path)

        resp = client.post(
            "/api/v1/organize",
            files={"file": ("meme.gif", b"GIF89a", "image/gif")},
        )
        assert resp.status_code == 200
        assert resp.json()["folder_name"] == "Images"

    def test_organize_wav_extension(self, tmp_path: Path) -> None:
        _, client, _ = _build_app(tmp_path)

        resp = client.post(
            "/api/v1/organize",
            files={"file": ("sound.wav", b"RIFF", "audio/wav")},
        )
        assert resp.status_code == 200
        assert resp.json()["folder_name"] == "Audio"


# ---------------------------------------------------------------------------
# _run_organize_job helper
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRunOrganizeJob:
    """Tests for _run_organize_job background function."""

    @patch("file_organizer.api.routers.organize.update_job")
    @patch("file_organizer.api.routers.organize.FileOrganizer")
    def test_successful_job(self, mock_organizer_cls, mock_update_job) -> None:
        from file_organizer.api.models import OrganizeRequest
        from file_organizer.api.routers.organize import _run_organize_job

        mock_instance = MagicMock()
        mock_instance.organize.return_value = _make_result()
        mock_organizer_cls.return_value = mock_instance

        request = OrganizeRequest(
            input_dir="/fake/input",
            output_dir="/fake/output",
            dry_run=False,
        )
        _run_organize_job("job-abc", request)

        # First call sets status to running
        mock_update_job.assert_any_call("job-abc", status="running")
        # Last call sets status to completed with result
        last_call = mock_update_job.call_args_list[-1]
        assert last_call[1]["status"] == "completed"
        assert "result" in last_call[1]

    @patch("file_organizer.api.routers.organize.update_job")
    @patch("file_organizer.api.routers.organize.FileOrganizer")
    def test_failed_job(self, mock_organizer_cls, mock_update_job) -> None:
        from file_organizer.api.models import OrganizeRequest
        from file_organizer.api.routers.organize import _run_organize_job

        mock_instance = MagicMock()
        mock_instance.organize.side_effect = RuntimeError("boom")
        mock_organizer_cls.return_value = mock_instance

        request = OrganizeRequest(
            input_dir="/fake/input",
            output_dir="/fake/output",
            dry_run=False,
        )
        _run_organize_job("job-xyz", request)

        mock_update_job.assert_any_call("job-xyz", status="running")
        last_call = mock_update_job.call_args_list[-1]
        assert last_call[1]["status"] == "failed"
        assert "boom" in last_call[1]["error"]


# ---------------------------------------------------------------------------
# _scan_directory and _counts_by_type helpers
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestScanDirectoryHelper:
    """Tests for _scan_directory helper function."""

    def test_scan_file_path(self, tmp_path: Path) -> None:
        from file_organizer.api.routers.organize import _scan_directory

        f = tmp_path / "file.txt"
        f.write_text("hello")
        result = _scan_directory(f, recursive=True, include_hidden=False)
        assert len(result) == 1

    def test_scan_hidden_file_excluded(self, tmp_path: Path) -> None:
        from file_organizer.api.routers.organize import _scan_directory

        f = tmp_path / ".hidden"
        f.write_text("hidden")
        result = _scan_directory(f, recursive=False, include_hidden=False)
        assert len(result) == 0

    def test_scan_hidden_file_included(self, tmp_path: Path) -> None:
        from file_organizer.api.routers.organize import _scan_directory

        f = tmp_path / ".hidden"
        f.write_text("hidden")
        result = _scan_directory(f, recursive=False, include_hidden=True)
        assert len(result) == 1


@pytest.mark.unit
class TestCountsByType:
    """Tests for _counts_by_type helper function."""

    def test_empty_list(self) -> None:
        from file_organizer.api.routers.organize import _counts_by_type

        counts = _counts_by_type([])
        assert counts["text"] == 0
        assert counts["other"] == 0

    def test_mixed_types(self, tmp_path: Path) -> None:
        from file_organizer.api.routers.organize import _counts_by_type

        files = [
            tmp_path / "a.txt",
            tmp_path / "b.jpg",
            tmp_path / "c.unknown",
        ]
        counts = _counts_by_type(files)
        assert counts["text"] == 1
        assert counts["image"] == 1
        assert counts["other"] == 1


@pytest.mark.unit
class TestResultToResponse:
    """Tests for _result_to_response helper function."""

    def test_basic_conversion(self) -> None:
        from file_organizer.api.routers.organize import _result_to_response

        result = _make_result(errors=[("fail.txt", "bad encoding")])
        resp = _result_to_response(result)
        assert resp.total_files == 3
        assert len(resp.errors) == 1
        assert resp.errors[0].file == "fail.txt"
        assert resp.errors[0].error == "bad encoding"
