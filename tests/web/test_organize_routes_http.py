"""HTTP-level tests for the organize_routes web endpoints.

Tests route handlers via TestClient at the HTTP transport layer, mocking
template rendering, job management, and the FileOrganizer.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from starlette.testclient import TestClient

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_settings
from file_organizer.api.exceptions import setup_exception_handlers
from file_organizer.web.organize_routes import organize_router

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tree(tmp_path):
    """Create a sample directory for organize tests."""
    (tmp_path / "input").mkdir()
    (tmp_path / "input" / "doc.txt").write_text("hello")
    (tmp_path / "output").mkdir()
    return tmp_path


@pytest.fixture()
def settings(tree):
    """Return ApiSettings pointing at the temp tree."""
    return ApiSettings(
        allowed_paths=[str(tree)],
        auth_enabled=False,
        auth_db_path=str(tree / "auth.db"),
    )


@pytest.fixture()
def client(settings):
    """Create a TestClient with the organize router mounted."""
    app = FastAPI()
    app.dependency_overrides[get_settings] = lambda: settings
    setup_exception_handlers(app)
    app.include_router(organize_router, prefix="/ui")
    return TestClient(app, raise_server_exceptions=False)


def _mock_job(
    job_id="test-job-1",
    status="completed",
    error=None,
):
    """Create a mock job object."""
    job = MagicMock()
    job.job_id = job_id
    job.status = status
    job.result = {
        "processed_files": 5,
        "total_files": 5,
        "failed_files": 0,
        "skipped_files": 0,
        "organized_structure": {},
    }
    job.created_at = datetime(2025, 6, 1, tzinfo=UTC)
    job.updated_at = datetime(2025, 6, 1, 0, 5, tzinfo=UTC)
    job.error = error
    return job


# ---------------------------------------------------------------------------
# GET /organize (dashboard)
# ---------------------------------------------------------------------------


class TestOrganizeDashboard:
    """Test GET /ui/organize endpoint."""

    def test_returns_200(self, client):
        with (
            patch("file_organizer.web.organize_routes.templates") as mock_tpl,
            patch("file_organizer.web.organize_routes.list_jobs", return_value=[]),
        ):
            mock_tpl.TemplateResponse.return_value = HTMLResponse("<html>dashboard</html>")
            response = client.get("/ui/organize")
        assert response.status_code == 200

    def test_uses_dashboard_template(self, client):
        with (
            patch("file_organizer.web.organize_routes.templates") as mock_tpl,
            patch("file_organizer.web.organize_routes.list_jobs", return_value=[]),
        ):
            mock_tpl.TemplateResponse.return_value = HTMLResponse("<html></html>")
            client.get("/ui/organize")
        assert "organize/dashboard.html" in str(mock_tpl.TemplateResponse.call_args)


# ---------------------------------------------------------------------------
# POST /organize/scan
# ---------------------------------------------------------------------------


class TestOrganizeScan:
    """Test POST /ui/organize/scan endpoint."""

    def test_missing_input_dir(self, client):
        with patch("file_organizer.web.organize_routes.templates") as mock_tpl:
            mock_tpl.TemplateResponse.return_value = HTMLResponse("<div>error</div>")
            response = client.post(
                "/ui/organize/scan",
                data={"input_dir": "", "output_dir": "/out"},
            )
        assert response.status_code == 200

    def test_missing_output_dir(self, client, tree):
        with patch("file_organizer.web.organize_routes.templates") as mock_tpl:
            mock_tpl.TemplateResponse.return_value = HTMLResponse("<div>error</div>")
            response = client.post(
                "/ui/organize/scan",
                data={"input_dir": str(tree / "input"), "output_dir": ""},
            )
        assert response.status_code == 200

    def test_successful_scan(self, client, tree):
        mock_result = MagicMock()
        mock_result.total_files = 1
        mock_result.processed_files = 1
        mock_result.skipped_files = 0
        mock_result.failed_files = 0
        mock_result.processing_time = 0.5
        mock_result.organized_structure = {"documents": ["doc.txt"]}
        mock_result.errors = []

        with (
            patch("file_organizer.web.organize_routes.templates") as mock_tpl,
            patch("file_organizer.web.organize_routes.FileOrganizer") as mock_org_cls,
        ):
            mock_org_cls.return_value.organize.return_value = mock_result
            mock_tpl.TemplateResponse.return_value = HTMLResponse("<div>plan</div>")
            response = client.post(
                "/ui/organize/scan",
                data={
                    "input_dir": str(tree / "input"),
                    "output_dir": str(tree / "output"),
                    "methodology": "content_based",
                },
            )
        assert response.status_code == 200
        assert "organize/_plan.html" in str(mock_tpl.TemplateResponse.call_args)


# ---------------------------------------------------------------------------
# POST /organize/execute
# ---------------------------------------------------------------------------


class TestOrganizeExecute:
    """Test POST /ui/organize/execute endpoint."""

    def test_missing_plan_id(self, client):
        with patch("file_organizer.web.organize_routes.templates") as mock_tpl:
            mock_tpl.TemplateResponse.return_value = HTMLResponse("<div>error</div>")
            response = client.post(
                "/ui/organize/execute",
                data={"plan_id": "", "dry_run": "0"},
            )
        assert response.status_code == 200

    def test_plan_not_found(self, client):
        with (
            patch("file_organizer.web.organize_routes.templates") as mock_tpl,
            patch(
                "file_organizer.web.organize_routes._get_organize_plan",
                return_value=None,
            ),
        ):
            mock_tpl.TemplateResponse.return_value = HTMLResponse("<div>error</div>")
            response = client.post(
                "/ui/organize/execute",
                data={"plan_id": "nonexistent", "dry_run": "0"},
            )
        assert response.status_code == 200

    def test_successful_execute(self, client, tree):
        plan = {
            "plan_id": "test-plan",
            "input_dir": str(tree / "input"),
            "output_dir": str(tree / "output"),
            "methodology": "content_based",
            "skip_existing": True,
            "use_hardlinks": True,
        }
        mock_job = _mock_job(status="queued")

        with (
            patch("file_organizer.web.organize_routes.templates") as mock_tpl,
            patch(
                "file_organizer.web.organize_routes._get_organize_plan",
                return_value=plan,
            ),
            patch(
                "file_organizer.web.organize_routes.create_job",
                return_value=mock_job,
            ),
            patch("file_organizer.web.organize_routes._set_job_metadata"),
            patch("file_organizer.web.organize_routes._run_organize_job"),
            patch("file_organizer.web.organize_routes.get_job", return_value=mock_job),
            patch(
                "file_organizer.web.organize_routes._get_job_metadata",
                return_value={
                    "methodology": "content_based",
                    "input_dir": str(tree / "input"),
                    "output_dir": str(tree / "output"),
                    "dry_run": False,
                },
            ),
        ):
            mock_tpl.TemplateResponse.return_value = HTMLResponse("<div>job</div>")
            response = client.post(
                "/ui/organize/execute",
                data={"plan_id": "test-plan", "dry_run": "0"},
            )
        assert response.status_code == 200
        trigger = json.loads(response.headers["HX-Trigger"])
        assert trigger == {"refreshHistory": True, "refreshStats": True}


# ---------------------------------------------------------------------------
# GET /organize/jobs/{job_id}/status
# ---------------------------------------------------------------------------


class TestOrganizeJobStatus:
    """Test GET /ui/organize/jobs/{job_id}/status endpoint."""

    def test_html_status(self, client):
        mock_job = _mock_job()
        with (
            patch("file_organizer.web.organize_routes.templates") as mock_tpl,
            patch(
                "file_organizer.web.organize_routes.get_job",
                return_value=mock_job,
            ),
            patch(
                "file_organizer.web.organize_routes._get_job_metadata",
                return_value={},
            ),
        ):
            mock_tpl.TemplateResponse.return_value = HTMLResponse("<div>status</div>")
            response = client.get("/ui/organize/jobs/test-job-1/status")
        assert response.status_code == 200

    def test_json_status(self, client):
        mock_job = _mock_job()
        with (
            patch(
                "file_organizer.web.organize_routes.get_job",
                return_value=mock_job,
            ),
            patch(
                "file_organizer.web.organize_routes._get_job_metadata",
                return_value={},
            ),
        ):
            response = client.get("/ui/organize/jobs/test-job-1/status?format=json")
        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == "test-job-1"
        assert data["status"] == "completed"

    def test_not_found(self, client):
        with patch(
            "file_organizer.web.organize_routes.get_job",
            return_value=None,
        ):
            response = client.get("/ui/organize/jobs/missing/status")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# POST /organize/jobs/{job_id}/cancel
# ---------------------------------------------------------------------------


class TestOrganizeJobCancel:
    """Test POST /ui/organize/jobs/{job_id}/cancel endpoint."""

    def test_cancel_existing(self, client):
        mock_job = _mock_job(status="queued")
        with (
            patch("file_organizer.web.organize_routes.templates") as mock_tpl,
            patch(
                "file_organizer.web.organize_routes.get_job",
                return_value=mock_job,
            ),
            patch(
                "file_organizer.web.organize_routes._get_job_metadata",
                return_value={
                    "schedule_delay_minutes": 30,
                    "scheduled_for": "2025-06-01T01:00:00Z",
                },
            ),
            patch(
                "file_organizer.web.organize_routes._cancel_scheduled_job",
                return_value=True,
            ),
        ):
            mock_tpl.TemplateResponse.return_value = HTMLResponse("<div>cancelled</div>")
            response = client.post("/ui/organize/jobs/test-job-1/cancel")
        assert response.status_code == 200

    def test_cancel_not_found(self, client):
        with patch(
            "file_organizer.web.organize_routes.get_job",
            return_value=None,
        ):
            response = client.post("/ui/organize/jobs/missing/cancel")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# POST /organize/jobs/{job_id}/rollback
# ---------------------------------------------------------------------------


class TestOrganizeJobRollback:
    """Test POST /ui/organize/jobs/{job_id}/rollback endpoint."""

    def test_rollback_completed_job(self, client):
        mock_job = _mock_job(status="completed")
        with (
            patch("file_organizer.web.organize_routes.templates") as mock_tpl,
            patch(
                "file_organizer.web.organize_routes.get_job",
                return_value=mock_job,
            ),
            patch(
                "file_organizer.web.organize_routes._get_job_metadata",
                return_value={"dry_run": False, "methodology": "para"},
            ),
            patch("file_organizer.undo.undo_manager.UndoManager") as mock_undo_cls,
        ):
            mock_undo_cls.return_value.undo_last_operation.return_value = True
            mock_tpl.TemplateResponse.return_value = HTMLResponse("<div>rolled back</div>")
            response = client.post("/ui/organize/jobs/test-job-1/rollback")
        assert response.status_code == 200
        trigger = json.loads(response.headers["HX-Trigger"])
        assert trigger == {"refreshHistory": True, "refreshStats": True}

    def test_rollback_not_found(self, client):
        with patch(
            "file_organizer.web.organize_routes.get_job",
            return_value=None,
        ):
            response = client.post("/ui/organize/jobs/missing/rollback")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# GET /organize/history
# ---------------------------------------------------------------------------


class TestOrganizeHistory:
    """Test GET /ui/organize/history endpoint."""

    def test_empty_history(self, client):
        with (
            patch("file_organizer.web.organize_routes.templates") as mock_tpl,
            patch(
                "file_organizer.web.organize_routes.list_jobs",
                return_value=[],
            ),
        ):
            mock_tpl.TemplateResponse.return_value = HTMLResponse("<div>empty</div>")
            response = client.get("/ui/organize/history")
        assert response.status_code == 200
        assert "organize/_history.html" in str(mock_tpl.TemplateResponse.call_args)

    def test_status_filter(self, client):
        with (
            patch("file_organizer.web.organize_routes.templates") as mock_tpl,
            patch(
                "file_organizer.web.organize_routes.list_jobs",
                return_value=[],
            ),
        ):
            mock_tpl.TemplateResponse.return_value = HTMLResponse("<div></div>")
            response = client.get("/ui/organize/history?status_filter=completed")
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# GET /organize/stats
# ---------------------------------------------------------------------------


class TestOrganizeStats:
    """Test GET /ui/organize/stats endpoint."""

    def test_returns_200(self, client):
        with (
            patch("file_organizer.web.organize_routes.templates") as mock_tpl,
            patch(
                "file_organizer.web.organize_routes.list_jobs",
                return_value=[],
            ),
        ):
            mock_tpl.TemplateResponse.return_value = HTMLResponse("<div>stats</div>")
            response = client.get("/ui/organize/stats")
        assert response.status_code == 200
        assert "organize/_stats.html" in str(mock_tpl.TemplateResponse.call_args)


# ---------------------------------------------------------------------------
# GET /organize/report/{job_id}
# ---------------------------------------------------------------------------


class TestOrganizeReport:
    """Test GET /ui/organize/report/{job_id} endpoint."""

    def _mock_with_metadata(self):
        """Return patch context for a mock job with metadata."""
        mock_job = _mock_job()
        return (
            patch(
                "file_organizer.web.organize_routes.get_job",
                return_value=mock_job,
            ),
            patch(
                "file_organizer.web.organize_routes._get_job_metadata",
                return_value={
                    "methodology": "para",
                    "input_dir": "/in",
                    "output_dir": "/out",
                    "dry_run": False,
                },
            ),
        )

    def test_json_report(self, client):
        p1, p2 = self._mock_with_metadata()
        with p1, p2:
            response = client.get("/ui/organize/report/test-job-1?format=json")
        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == "test-job-1"

    def test_txt_report(self, client):
        p1, p2 = self._mock_with_metadata()
        with p1, p2:
            response = client.get("/ui/organize/report/test-job-1?format=txt")
        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]
        assert "Job ID: test-job-1" in response.text

    def test_csv_report(self, client):
        p1, p2 = self._mock_with_metadata()
        with p1, p2:
            response = client.get("/ui/organize/report/test-job-1?format=csv")
        assert response.status_code == 200
        assert "text/csv" in response.headers["content-type"]

    def test_report_not_found(self, client):
        with patch(
            "file_organizer.web.organize_routes.get_job",
            return_value=None,
        ):
            response = client.get("/ui/organize/report/missing")
        assert response.status_code == 404
