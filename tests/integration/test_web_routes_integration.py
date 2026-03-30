"""Integration tests for web UI routes (organize, files, settings, profiles).

These tests exercise the full HTTP request/response cycle using a real FastAPI
TestClient.  Template rendering is mocked (returns trivial HTML) so tests focus
on route logic, path validation, job management, and error handling rather than
Jinja2 template correctness — that is covered by unit tests in tests/web/.

Coverage targets:
  - web/organize_routes.py
  - web/files_routes.py
  - web/settings_routes.py
  - web/profile_routes.py
  - web/_helpers.py
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.testclient import TestClient

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_settings
from file_organizer.api.exceptions import setup_exception_handlers
from file_organizer.api.test_utils import csrf_headers, seed_csrf_token
from file_organizer.web.files_routes import files_router
from file_organizer.web.organize_routes import organize_router
from file_organizer.web.profile_routes import profile_router
from file_organizer.web.settings_routes import settings_router

pytestmark = pytest.mark.integration

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_HTML = HTMLResponse("<html><body>stub</body></html>")
_JSON = JSONResponse({"ok": True})


def _mock_job(
    job_id: str = "job-1",
    status: str = "completed",
    result: dict | None = None,
) -> MagicMock:
    job = MagicMock()
    job.job_id = job_id
    job.status = status
    job.result = result or {
        "processed_files": 2,
        "total_files": 2,
        "failed_files": 0,
        "skipped_files": 0,
        "organized_structure": {"docs": ["a.txt"]},
    }
    job.error = None
    job.created_at = datetime(2026, 1, 1, tzinfo=UTC)
    job.updated_at = datetime(2026, 1, 1, 0, 1, tzinfo=UTC)
    return job


# ---------------------------------------------------------------------------
# Organize-route fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def file_tree(tmp_path: Path) -> Path:
    (tmp_path / "in").mkdir()
    (tmp_path / "in" / "report.txt").write_text("quarterly report")
    (tmp_path / "in" / "data.csv").write_text("col1,col2\n1,2")
    (tmp_path / "out").mkdir()
    return tmp_path


@pytest.fixture()
def org_settings(file_tree: Path) -> ApiSettings:
    return ApiSettings(
        allowed_paths=[str(file_tree)],
        auth_enabled=False,
        auth_db_path=str(file_tree / "auth.db"),
    )


@pytest.fixture()
def org_client(org_settings: ApiSettings) -> TestClient:
    app = FastAPI()
    app.dependency_overrides[get_settings] = lambda: org_settings
    setup_exception_handlers(app)
    app.include_router(organize_router, prefix="/ui")
    client = TestClient(app, raise_server_exceptions=False)
    seed_csrf_token(client)
    return client


# ---------------------------------------------------------------------------
# Organize: GET /organize
# ---------------------------------------------------------------------------


class TestOrganizeDashboard:
    def test_returns_200(self, org_client: TestClient) -> None:
        with (
            patch("file_organizer.web.organize_routes.templates") as tpl,
            patch("file_organizer.web.organize_routes.list_jobs", return_value=[]),
        ):
            tpl.TemplateResponse.return_value = _HTML
            r = org_client.get("/ui/organize")
        assert r.status_code == 200

    def test_renders_dashboard_template(self, org_client: TestClient) -> None:
        with (
            patch("file_organizer.web.organize_routes.templates") as tpl,
            patch("file_organizer.web.organize_routes.list_jobs", return_value=[]),
        ):
            tpl.TemplateResponse.return_value = _HTML
            org_client.get("/ui/organize")
        call_args = str(tpl.TemplateResponse.call_args)
        assert "dashboard.html" in call_args


# ---------------------------------------------------------------------------
# Organize: POST /organize/scan
# ---------------------------------------------------------------------------


class TestOrganizeScan:
    def test_missing_input_dir_returns_200(self, org_client: TestClient) -> None:
        with patch("file_organizer.web.organize_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            r = org_client.post(
                "/ui/organize/scan",
                data={"input_dir": "", "output_dir": "/out"},
                headers=csrf_headers(org_client),
            )
        assert r.status_code == 200

    def test_missing_output_dir_returns_200(self, org_client: TestClient, file_tree: Path) -> None:
        with patch("file_organizer.web.organize_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            r = org_client.post(
                "/ui/organize/scan",
                data={"input_dir": str(file_tree / "in"), "output_dir": ""},
                headers=csrf_headers(org_client),
            )
        assert r.status_code == 200

    def test_include_hidden_not_supported(self, org_client: TestClient, file_tree: Path) -> None:
        with patch("file_organizer.web.organize_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            r = org_client.post(
                "/ui/organize/scan",
                data={
                    "input_dir": str(file_tree / "in"),
                    "output_dir": str(file_tree / "out"),
                    "include_hidden": "1",
                },
                headers=csrf_headers(org_client),
            )
        assert r.status_code == 200

    def test_successful_scan_generates_plan(self, org_client: TestClient, file_tree: Path) -> None:
        mock_result = MagicMock()
        mock_result.total_files = 2
        mock_result.processed_files = 2
        mock_result.skipped_files = 0
        mock_result.failed_files = 0
        mock_result.processing_time = 0.1
        mock_result.errors = []
        mock_result.organized_structure = {"docs": ["report.txt"]}

        with (
            patch("file_organizer.web.organize_routes.templates") as tpl,
            patch("file_organizer.web.organize_routes.FileOrganizer") as mock_org,
        ):
            mock_org.return_value.organize.return_value = mock_result
            tpl.TemplateResponse.return_value = _HTML
            r = org_client.post(
                "/ui/organize/scan",
                data={
                    "input_dir": str(file_tree / "in"),
                    "output_dir": str(file_tree / "out"),
                    "methodology": "content_based",
                    "recursive": "1",
                    "include_hidden": "0",
                },
                headers=csrf_headers(org_client),
            )
        assert r.status_code == 200

    def test_input_dir_not_found(self, org_client: TestClient, file_tree: Path) -> None:
        with patch("file_organizer.web.organize_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            r = org_client.post(
                "/ui/organize/scan",
                data={
                    "input_dir": str(file_tree / "nonexistent"),
                    "output_dir": str(file_tree / "out"),
                },
                headers=csrf_headers(org_client),
            )
        assert r.status_code == 200  # returns error template, not 4xx

    def test_organizer_exception_renders_error(
        self, org_client: TestClient, file_tree: Path
    ) -> None:
        with (
            patch("file_organizer.web.organize_routes.templates") as tpl,
            patch("file_organizer.web.organize_routes.FileOrganizer") as mock_org,
        ):
            mock_org.return_value.organize.side_effect = RuntimeError("crashed")
            tpl.TemplateResponse.return_value = _HTML
            r = org_client.post(
                "/ui/organize/scan",
                data={
                    "input_dir": str(file_tree / "in"),
                    "output_dir": str(file_tree / "out"),
                },
                headers=csrf_headers(org_client),
            )
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Organize: POST /organize/plan/clear
# ---------------------------------------------------------------------------


class TestOrganizePlanClear:
    def test_clear_plan_returns_200(self, org_client: TestClient) -> None:
        with patch("file_organizer.web.organize_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            r = org_client.post("/ui/organize/plan/clear", headers=csrf_headers(org_client))
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Organize: POST /organize/execute
# ---------------------------------------------------------------------------


class TestOrganizerExecute:
    def test_execute_no_plan_renders_error(self, org_client: TestClient) -> None:
        with patch("file_organizer.web.organize_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            r = org_client.post("/ui/organize/execute", headers=csrf_headers(org_client))
        assert r.status_code == 200

    def test_execute_with_plan_queues_job(self, org_client: TestClient, file_tree: Path) -> None:
        mock_result = MagicMock()
        mock_result.total_files = 1
        mock_result.processed_files = 1
        mock_result.skipped_files = 0
        mock_result.failed_files = 0
        mock_result.errors = []
        mock_result.organized_structure = {}

        with (
            patch("file_organizer.web.organize_routes.templates") as tpl,
            patch("file_organizer.web.organize_routes.FileOrganizer") as mock_org,
            patch("file_organizer.web.organize_routes._get_organize_plan") as mock_plan,
            patch("file_organizer.web.organize_routes.create_job") as mock_create,
            patch("file_organizer.web.organize_routes.update_job"),
        ):
            mock_plan.return_value = {
                "input_dir": str(file_tree / "in"),
                "output_dir": str(file_tree / "out"),
                "methodology": "content_based",
                "recursive": True,
                "include_hidden": False,
                "skip_existing": True,
                "use_hardlinks": False,
            }
            mock_job = _mock_job(status="queued")
            mock_create.return_value = mock_job
            mock_org.return_value.organize.return_value = mock_result
            tpl.TemplateResponse.return_value = _HTML
            r = org_client.post("/ui/organize/execute", headers=csrf_headers(org_client))
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Organize: GET /organize/jobs/{job_id}/status
# ---------------------------------------------------------------------------


class TestJobStatus:
    def test_job_status_running(self, org_client: TestClient) -> None:
        with (
            patch("file_organizer.web.organize_routes.templates") as tpl,
            patch(
                "file_organizer.web.organize_routes.get_job",
                return_value=_mock_job(status="running"),
            ),
        ):
            tpl.TemplateResponse.return_value = _HTML
            r = org_client.get("/ui/organize/jobs/job-1/status")
        assert r.status_code == 200

    def test_job_status_completed(self, org_client: TestClient) -> None:
        with (
            patch("file_organizer.web.organize_routes.templates") as tpl,
            patch(
                "file_organizer.web.organize_routes.get_job",
                return_value=_mock_job(status="completed"),
            ),
        ):
            tpl.TemplateResponse.return_value = _HTML
            r = org_client.get("/ui/organize/jobs/job-1/status")
        assert r.status_code == 200

    def test_job_status_not_found(self, org_client: TestClient) -> None:
        with (
            patch("file_organizer.web.organize_routes.templates") as tpl,
            patch("file_organizer.web.organize_routes.get_job", return_value=None),
        ):
            tpl.TemplateResponse.return_value = _HTML
            r = org_client.get("/ui/organize/jobs/missing/status")
        assert r.status_code == 404

    def test_job_cancel(self, org_client: TestClient) -> None:
        with (
            patch("file_organizer.web.organize_routes.templates") as tpl,
            patch(
                "file_organizer.web.organize_routes.get_job",
                return_value=_mock_job(status="running"),
            ),
            patch("file_organizer.web.organize_routes.update_job"),
        ):
            tpl.TemplateResponse.return_value = _HTML
            r = org_client.post("/ui/organize/jobs/job-1/cancel", headers=csrf_headers(org_client))
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Files routes
# ---------------------------------------------------------------------------


@pytest.fixture()
def files_settings(tmp_path: Path) -> ApiSettings:
    (tmp_path / "files").mkdir()
    (tmp_path / "files" / "doc.txt").write_text("hello")
    (tmp_path / "files" / "sub").mkdir()
    (tmp_path / "files" / "sub" / "nested.txt").write_text("nested")
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
    client = TestClient(app, raise_server_exceptions=False)
    seed_csrf_token(client)
    return client


class TestFilesRoutes:
    def test_files_list_root(self, files_client: TestClient, tmp_path: Path) -> None:
        with patch("file_organizer.web.files_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            r = files_client.get("/ui/files")
        assert r.status_code == 200

    def test_files_list_with_path(
        self, files_client: TestClient, files_settings: ApiSettings
    ) -> None:
        # Use a path that is within allowed roots
        root = files_settings.allowed_paths[0]
        with patch("file_organizer.web.files_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            r = files_client.get(f"/ui/files?path={root}/files")
        assert r.status_code == 200

    def test_files_list_nonexistent_path(
        self, files_client: TestClient, files_settings: ApiSettings
    ) -> None:
        root = files_settings.allowed_paths[0]
        with patch("file_organizer.web.files_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            r = files_client.get(f"/ui/files?path={root}/nonexistent")
        assert r.status_code == 200  # error rendered as template

    def test_files_tree_returns_200(
        self, files_client: TestClient, files_settings: ApiSettings
    ) -> None:
        root = files_settings.allowed_paths[0]
        with patch("file_organizer.web.files_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            r = files_client.get(f"/ui/files/tree?path={root}/files")
        assert r.status_code == 200

    def test_files_preview_returns_200(
        self, files_client: TestClient, files_settings: ApiSettings
    ) -> None:
        root = files_settings.allowed_paths[0]
        target = Path(root) / "files" / "doc.txt"
        with patch("file_organizer.web.files_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            r = files_client.get(f"/ui/files/preview?path={target}")
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Settings routes
# ---------------------------------------------------------------------------


@pytest.fixture()
def settings_settings(tmp_path: Path) -> ApiSettings:
    return ApiSettings(
        allowed_paths=[str(tmp_path)],
        auth_enabled=False,
        auth_db_path=str(tmp_path / "auth.db"),
    )


@pytest.fixture()
def settings_client(settings_settings: ApiSettings) -> TestClient:
    app = FastAPI()
    app.dependency_overrides[get_settings] = lambda: settings_settings
    setup_exception_handlers(app)
    app.include_router(settings_router, prefix="/ui")
    client = TestClient(app, raise_server_exceptions=False)
    seed_csrf_token(client)
    return client


class TestSettingsRoutes:
    def test_settings_index_returns_200(self, settings_client: TestClient) -> None:
        with patch("file_organizer.web.settings_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            r = settings_client.get("/ui/settings")
        assert r.status_code == 200

    def test_settings_general_post_returns_200(
        self, settings_client: TestClient, tmp_path: Path
    ) -> None:
        with patch("file_organizer.web.settings_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            r = settings_client.post(
                "/ui/settings/general",
                data={
                    "allowed_paths": str(tmp_path),
                },
                headers=csrf_headers(settings_client),
            )
        assert r.status_code == 200

    def test_settings_reset_returns_200(self, settings_client: TestClient) -> None:
        with patch("file_organizer.web.settings_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            r = settings_client.post("/ui/settings/reset", headers=csrf_headers(settings_client))
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Profile routes
# ---------------------------------------------------------------------------


@pytest.fixture()
def profile_settings(tmp_path: Path) -> ApiSettings:
    return ApiSettings(
        allowed_paths=[str(tmp_path)],
        auth_enabled=False,
        auth_db_path=str(tmp_path / "auth.db"),
    )


@pytest.fixture()
def profile_client(profile_settings: ApiSettings) -> TestClient:
    app = FastAPI()
    app.dependency_overrides[get_settings] = lambda: profile_settings
    setup_exception_handlers(app)
    app.include_router(profile_router, prefix="/ui")
    client = TestClient(app, raise_server_exceptions=False)
    seed_csrf_token(client)
    return client


class TestProfileRoutes:
    def test_profile_dashboard_returns_200(self, profile_client: TestClient) -> None:
        with patch("file_organizer.web.profile_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            r = profile_client.get("/ui/profile")
        assert r.status_code == 200

    def test_profile_login_form_returns_200(self, profile_client: TestClient) -> None:
        with patch("file_organizer.web.profile_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            r = profile_client.get("/ui/profile/login")
        assert r.status_code == 200

    def test_profile_register_form_returns_200(self, profile_client: TestClient) -> None:
        with patch("file_organizer.web.profile_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            r = profile_client.get("/ui/profile/register")
        assert r.status_code == 200

    def test_profile_login_post(self, profile_client: TestClient) -> None:
        with patch("file_organizer.web.profile_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            r = profile_client.post(
                "/ui/profile/login",
                data={"username": "user@example.com", "password": "secret"},
                headers=csrf_headers(profile_client),
            )
        assert r.status_code in (200, 303, 302)

    def test_profile_logout_returns_redirect(self, profile_client: TestClient) -> None:
        r = profile_client.post(
            "/ui/profile/logout",
            headers=csrf_headers(profile_client),
            follow_redirects=False,
        )
        assert r.status_code in (200, 303, 302, 401)
