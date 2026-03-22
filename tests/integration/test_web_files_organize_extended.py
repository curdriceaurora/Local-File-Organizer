"""Extended integration tests for web/files_routes.py and web/organize_routes.py.

Covers: files_browser (with path/filter params), files_list partial, files_tree
(no path / with path / error path), files_thumbnail (all kind variants), files_raw
(inline / download), files_preview (text / error), files_upload (success / hidden
file / empty / no-path), organize_history, organize_stats, organize_report
(json/txt/csv), organize_job_rollback, organize_stats_events header.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.testclient import TestClient

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_settings
from file_organizer.api.exceptions import setup_exception_handlers
from file_organizer.web.files_routes import files_router
from file_organizer.web.organize_routes import organize_router

pytestmark = pytest.mark.integration

_HTML = HTMLResponse("<html><body>stub</body></html>")
_JSON = JSONResponse({"ok": True})


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _mock_job(
    job_id: str = "job-1",
    status: str = "completed",
    result: dict | None = None,
    error: str | None = None,
) -> MagicMock:
    from datetime import UTC, datetime

    job = MagicMock()
    job.job_id = job_id
    job.status = status
    job.error = error
    job.result = result or {
        "processed_files": 2,
        "total_files": 2,
        "failed_files": 0,
        "skipped_files": 0,
        "organized_structure": {},
    }
    job.created_at = datetime(2026, 1, 1, tzinfo=UTC)
    job.updated_at = datetime(2026, 1, 1, 0, 1, tzinfo=UTC)
    return job


# ---------------------------------------------------------------------------
# Files fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def files_settings(tmp_path: Path) -> ApiSettings:
    d = tmp_path / "files"
    d.mkdir()
    (d / "readme.txt").write_text("hello world content for preview")
    (d / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    (d / "data.csv").write_text("a,b\n1,2")
    sub = d / "subdir"
    sub.mkdir()
    (sub / "nested.txt").write_text("nested")
    return ApiSettings(
        allowed_paths=[str(tmp_path)],
        auth_enabled=False,
        auth_db_path=str(tmp_path / "auth.db"),
    )


@pytest.fixture()
def files_client(files_settings: ApiSettings) -> TestClient:
    app = FastAPI()
    app.dependency_overrides[get_settings] = lambda: files_settings
    setup_exception_handlers(app)
    app.include_router(files_router, prefix="/ui")
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Files routes — browser
# ---------------------------------------------------------------------------


class TestFilesBrowser:
    def test_files_browser_returns_200(self, files_client: TestClient) -> None:
        with patch("file_organizer.web.files_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            r = files_client.get("/ui/files")
        assert r.status_code == 200

    def test_files_browser_with_path(
        self, files_client: TestClient, files_settings: ApiSettings
    ) -> None:
        root = files_settings.allowed_paths[0]
        with patch("file_organizer.web.files_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            r = files_client.get(f"/ui/files?path={root}/files")
        assert r.status_code == 200

    def test_files_browser_with_query(
        self, files_client: TestClient, files_settings: ApiSettings
    ) -> None:
        root = files_settings.allowed_paths[0]
        with patch("file_organizer.web.files_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            r = files_client.get(f"/ui/files?path={root}/files&q=readme")
        assert r.status_code == 200

    def test_files_browser_list_view(
        self, files_client: TestClient, files_settings: ApiSettings
    ) -> None:
        root = files_settings.allowed_paths[0]
        with patch("file_organizer.web.files_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            r = files_client.get(f"/ui/files?path={root}/files&view=list")
        assert r.status_code == 200

    def test_files_browser_sort_by_size(
        self, files_client: TestClient, files_settings: ApiSettings
    ) -> None:
        root = files_settings.allowed_paths[0]
        with patch("file_organizer.web.files_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            r = files_client.get(f"/ui/files?path={root}/files&sort_by=size&sort_order=desc")
        assert r.status_code == 200

    def test_files_browser_type_filter(
        self, files_client: TestClient, files_settings: ApiSettings
    ) -> None:
        root = files_settings.allowed_paths[0]
        with patch("file_organizer.web.files_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            r = files_client.get(f"/ui/files?path={root}/files&type=image")
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Files routes — list partial
# ---------------------------------------------------------------------------


class TestFilesList:
    def test_files_list_returns_200(
        self, files_client: TestClient, files_settings: ApiSettings
    ) -> None:
        root = files_settings.allowed_paths[0]
        with patch("file_organizer.web.files_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            r = files_client.get(f"/ui/files/list?path={root}/files")
        assert r.status_code == 200

    def test_files_list_nonexistent_path(
        self, files_client: TestClient, files_settings: ApiSettings
    ) -> None:
        root = files_settings.allowed_paths[0]
        with patch("file_organizer.web.files_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            r = files_client.get(f"/ui/files/list?path={root}/nonexistent")
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Files routes — tree partial
# ---------------------------------------------------------------------------


class TestFilesTree:
    def test_files_tree_no_path_returns_200(self, files_client: TestClient) -> None:
        with patch("file_organizer.web.files_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            r = files_client.get("/ui/files/tree")
        assert r.status_code == 200

    def test_files_tree_with_valid_path(
        self, files_client: TestClient, files_settings: ApiSettings
    ) -> None:
        root = files_settings.allowed_paths[0]
        with patch("file_organizer.web.files_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            r = files_client.get(f"/ui/files/tree?path={root}/files")
        assert r.status_code == 200

    def test_files_tree_invalid_path_returns_200(
        self, files_client: TestClient, files_settings: ApiSettings
    ) -> None:
        root = files_settings.allowed_paths[0]
        with patch("file_organizer.web.files_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            r = files_client.get(f"/ui/files/tree?path={root}/gone")
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Files routes — thumbnail
# ---------------------------------------------------------------------------


class TestFilesThumbnail:
    def test_thumbnail_not_found_returns_404(
        self, files_client: TestClient, files_settings: ApiSettings
    ) -> None:
        root = files_settings.allowed_paths[0]
        r = files_client.get(f"/ui/files/thumbnail?path={root}/files/missing.jpg&kind=image")
        assert r.status_code == 404

    def test_thumbnail_image_kind_returns_png(
        self, files_client: TestClient, files_settings: ApiSettings
    ) -> None:
        root = files_settings.allowed_paths[0]
        r = files_client.get(f"/ui/files/thumbnail?path={root}/files/image.png&kind=image")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("image/png")

    def test_thumbnail_pdf_kind_returns_png(
        self, files_client: TestClient, files_settings: ApiSettings
    ) -> None:
        root = files_settings.allowed_paths[0]
        target = f"{root}/files/readme.txt"
        r = files_client.get(f"/ui/files/thumbnail?path={target}&kind=pdf")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("image/png")

    def test_thumbnail_video_kind_returns_png(
        self, files_client: TestClient, files_settings: ApiSettings
    ) -> None:
        root = files_settings.allowed_paths[0]
        target = f"{root}/files/readme.txt"
        r = files_client.get(f"/ui/files/thumbnail?path={target}&kind=video")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("image/png")

    def test_thumbnail_file_kind_returns_png(
        self, files_client: TestClient, files_settings: ApiSettings
    ) -> None:
        root = files_settings.allowed_paths[0]
        target = f"{root}/files/data.csv"
        r = files_client.get(f"/ui/files/thumbnail?path={target}&kind=file")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("image/png")


# ---------------------------------------------------------------------------
# Files routes — raw
# ---------------------------------------------------------------------------


class TestFilesRaw:
    def test_files_raw_inline(self, files_client: TestClient, files_settings: ApiSettings) -> None:
        root = files_settings.allowed_paths[0]
        r = files_client.get(f"/ui/files/raw?path={root}/files/readme.txt")
        assert r.status_code == 200

    def test_files_raw_download(
        self, files_client: TestClient, files_settings: ApiSettings
    ) -> None:
        root = files_settings.allowed_paths[0]
        r = files_client.get(f"/ui/files/raw?path={root}/files/readme.txt&download=1")
        assert r.status_code == 200
        assert "Content-Disposition" in r.headers

    def test_files_raw_not_found(
        self, files_client: TestClient, files_settings: ApiSettings
    ) -> None:
        root = files_settings.allowed_paths[0]
        r = files_client.get(f"/ui/files/raw?path={root}/files/ghost.txt")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Files routes — preview
# ---------------------------------------------------------------------------


class TestFilesPreview:
    def test_files_preview_text_returns_200(
        self, files_client: TestClient, files_settings: ApiSettings
    ) -> None:
        root = files_settings.allowed_paths[0]
        with patch("file_organizer.web.files_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            r = files_client.get(f"/ui/files/preview?path={root}/files/readme.txt")
        assert r.status_code == 200

    def test_files_preview_not_found_returns_200(
        self, files_client: TestClient, files_settings: ApiSettings
    ) -> None:
        root = files_settings.allowed_paths[0]
        with patch("file_organizer.web.files_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            r = files_client.get(f"/ui/files/preview?path={root}/files/missing.txt")
        assert r.status_code == 200

    def test_files_preview_image_returns_200(
        self, files_client: TestClient, files_settings: ApiSettings
    ) -> None:
        root = files_settings.allowed_paths[0]
        with patch("file_organizer.web.files_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            r = files_client.get(f"/ui/files/preview?path={root}/files/image.png")
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Files routes — upload
# ---------------------------------------------------------------------------


class TestFilesUpload:
    def test_upload_success(self, files_client: TestClient, files_settings: ApiSettings) -> None:
        root = files_settings.allowed_paths[0]
        with patch("file_organizer.web.files_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            r = files_client.post(
                "/ui/files/upload",
                data={"path": f"{root}/files"},
                files={"files": ("upload.txt", b"file content", "text/plain")},
            )
        assert r.status_code == 200

    def test_upload_hidden_file_rejected(
        self, files_client: TestClient, files_settings: ApiSettings
    ) -> None:
        root = files_settings.allowed_paths[0]
        target_dir = Path(root) / "files"
        with patch("file_organizer.web.files_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            r = files_client.post(
                "/ui/files/upload",
                data={"path": str(target_dir)},
                files={"files": (".hidden", b"x", "text/plain")},
            )
        assert r.status_code == 200
        assert not (target_dir / ".hidden").exists()

    def test_upload_no_files_returns_200(
        self, files_client: TestClient, files_settings: ApiSettings
    ) -> None:
        root = files_settings.allowed_paths[0]
        with patch("file_organizer.web.files_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            r = files_client.post(
                "/ui/files/upload",
                data={"path": f"{root}/files"},
            )
        assert r.status_code == 200

    def test_upload_no_path_returns_200(
        self, files_client: TestClient, files_settings: ApiSettings
    ) -> None:
        with patch("file_organizer.web.files_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            r = files_client.post(
                "/ui/files/upload",
                data={"path": ""},
            )
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Organize routes — fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def org_settings(tmp_path: Path) -> ApiSettings:
    (tmp_path / "in").mkdir()
    (tmp_path / "out").mkdir()
    return ApiSettings(
        allowed_paths=[str(tmp_path)],
        auth_enabled=False,
        auth_db_path=str(tmp_path / "auth.db"),
    )


@pytest.fixture()
def org_client(org_settings: ApiSettings) -> TestClient:
    app = FastAPI()
    app.dependency_overrides[get_settings] = lambda: org_settings
    setup_exception_handlers(app)
    app.include_router(organize_router, prefix="/ui")
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Organize routes — history / stats
# ---------------------------------------------------------------------------


class TestOrganizeHistoryAndStats:
    def test_organize_history_returns_200(self, org_client: TestClient) -> None:
        with patch("file_organizer.web.organize_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            r = org_client.get("/ui/organize/history")
        assert r.status_code == 200

    def test_organize_history_with_filter(self, org_client: TestClient) -> None:
        with patch("file_organizer.web.organize_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            r = org_client.get("/ui/organize/history?status_filter=completed")
        assert r.status_code == 200

    def test_organize_stats_returns_200(self, org_client: TestClient) -> None:
        with patch("file_organizer.web.organize_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            r = org_client.get("/ui/organize/stats")
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Organize routes — report
# ---------------------------------------------------------------------------


class TestOrganizeReport:
    def test_report_not_found_returns_404(self, org_client: TestClient) -> None:
        r = org_client.get("/ui/organize/report/missing-job-xyz")
        assert r.status_code == 404

    def test_report_json_returns_200(self, org_client: TestClient) -> None:
        with patch(
            "file_organizer.web.organize_routes._build_job_view",
            return_value={
                "job_id": "j1",
                "status": "completed",
                "methodology": "PARA",
                "input_dir": "/mock/in",
                "output_dir": "/mock/out",
                "dry_run": False,
                "processed_files": 1,
                "total_files": 1,
                "failed_files": 0,
                "skipped_files": 0,
                "error": None,
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:01:00Z",
                "organized_structure": {},
            },
        ):
            with patch("file_organizer.web.organize_routes._job_report_payload") as rp:
                rp.return_value = {
                    "job_id": "j1",
                    "status": "completed",
                    "methodology": "PARA",
                    "input_dir": "/mock/in",
                    "output_dir": "/mock/out",
                    "dry_run": False,
                    "processed_files": 1,
                    "total_files": 1,
                    "failed_files": 0,
                    "skipped_files": 0,
                    "error": None,
                    "created_at": "2026-01-01T00:00:00Z",
                    "updated_at": "2026-01-01T00:01:00Z",
                    "result": {"organized_structure": {}},
                }
                r = org_client.get("/ui/organize/report/j1?format=json")
        assert r.status_code == 200

    def test_report_txt_returns_200(self, org_client: TestClient) -> None:
        payload = {
            "job_id": "j2",
            "status": "completed",
            "methodology": "PARA",
            "input_dir": "/in",
            "output_dir": "/out",
            "dry_run": False,
            "processed_files": 2,
            "total_files": 2,
            "failed_files": 0,
            "skipped_files": 0,
            "error": None,
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:01:00Z",
            "organized_structure": {},
        }
        with (
            patch("file_organizer.web.organize_routes._build_job_view", return_value=payload),
            patch("file_organizer.web.organize_routes._job_report_payload", return_value=payload),
        ):
            r = org_client.get("/ui/organize/report/j2?format=txt")
        assert r.status_code == 200
        assert "text/plain" in r.headers["content-type"]

    def test_report_csv_returns_200(self, org_client: TestClient) -> None:
        payload = {
            "job_id": "j3",
            "status": "completed",
            "methodology": "PARA",
            "input_dir": "/in",
            "output_dir": "/out",
            "dry_run": False,
            "processed_files": 0,
            "total_files": 0,
            "failed_files": 0,
            "skipped_files": 0,
            "error": None,
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:01:00Z",
            "organized_structure": {},
        }
        with (
            patch("file_organizer.web.organize_routes._build_job_view", return_value=payload),
            patch("file_organizer.web.organize_routes._job_report_payload", return_value=payload),
        ):
            r = org_client.get("/ui/organize/report/j3?format=csv")
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Organize routes — rollback
# ---------------------------------------------------------------------------


class TestOrganizeRollback:
    def test_rollback_not_found_returns_404(self, org_client: TestClient) -> None:
        with (
            patch("file_organizer.web.organize_routes.templates") as tpl,
            patch("file_organizer.web.organize_routes.get_job", return_value=None),
        ):
            tpl.TemplateResponse.return_value = _HTML
            r = org_client.post("/ui/organize/jobs/missing-job/rollback")
        assert r.status_code == 404

    def test_rollback_completed_job_returns_200(self, org_client: TestClient) -> None:
        with (
            patch("file_organizer.web.organize_routes.templates") as tpl,
            patch(
                "file_organizer.web.organize_routes.get_job",
                return_value=_mock_job(status="completed"),
            ),
        ):
            tpl.TemplateResponse.return_value = _HTML
            r = org_client.post("/ui/organize/jobs/job-1/rollback")
        assert r.status_code == 200
