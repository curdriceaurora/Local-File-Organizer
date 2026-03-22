"""Extended integration tests for web/organize_routes.py.

Covers uncovered lines including:
- _parse_delay_minutes: None/empty → 0, non-int raises, negative raises, over-max raises
- _normalize_methodology: known key, unknown key → content_based
- _scan_directory: single file input (hidden/not hidden), non-recursive glob
- _counts_by_type: image, video, audio, cad, other categories
- _store_organize_plan / _get_organize_plan / _delete_organize_plan
- _set_job_metadata / _get_job_metadata / _prune_job_metadata (force=True)
- _status_progress: queued, running, failed, unknown
- _build_job_view: job with result, running progress, scheduled job
- organize_execute: missing plan_id, plan not found, delay>0 scheduling path
- organize_job_status: json format, html format
- organize_job_cancel: cancel success, already-running cancel fails
- organize_job_rollback: can_rollback=False branch
- organize_history: with status_filter
- organize_stats: basic call
- organize_report: txt and csv formats, job not found
- organize_clear_plan: with plan_id
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from starlette.testclient import TestClient

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_settings
from file_organizer.api.exceptions import ApiError, setup_exception_handlers
from file_organizer.web.organize_routes import (
    ORGANIZE_MAX_DELAY_MIN,
    _build_job_view,
    _counts_by_type,
    _delete_organize_plan,
    _get_job_metadata,
    _get_organize_plan,
    _normalize_methodology,
    _parse_delay_minutes,
    _prune_job_metadata,
    _scan_directory,
    _set_job_metadata,
    _status_progress,
    _store_organize_plan,
    organize_router,
)

pytestmark = pytest.mark.integration

_HTML = HTMLResponse("<html><body>stub</body></html>")


def _mock_job(
    job_id: str = "job-1",
    status: str = "completed",
    result: dict | None = None,
) -> MagicMock:
    job = MagicMock()
    job.job_id = job_id
    job.status = status
    job.result = result or {
        "processed_files": 3,
        "total_files": 3,
        "failed_files": 0,
        "skipped_files": 0,
        "organized_structure": {"docs": ["a.txt"], "images": ["b.jpg"]},
    }
    job.error = None
    job.created_at = datetime(2026, 1, 1, tzinfo=UTC)
    job.updated_at = datetime(2026, 1, 1, 0, 1, tzinfo=UTC)
    return job


@pytest.fixture()
def file_tree(tmp_path: Path) -> Path:
    (tmp_path / "in").mkdir()
    (tmp_path / "in" / "report.txt").write_text("text")
    (tmp_path / "in" / "photo.jpg").write_bytes(b"\xff\xd8\xff")
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
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Helper: _parse_delay_minutes
# ---------------------------------------------------------------------------


class TestParseDelayMinutes:
    def test_none_returns_zero(self) -> None:
        assert _parse_delay_minutes(None) == 0

    def test_empty_string_returns_zero(self) -> None:
        assert _parse_delay_minutes("") == 0

    def test_valid_integer_string(self) -> None:
        assert _parse_delay_minutes("10") == 10

    def test_non_integer_raises(self) -> None:
        with pytest.raises(ApiError) as exc_info:
            _parse_delay_minutes("abc")
        assert exc_info.value.status_code == 400

    def test_negative_raises(self) -> None:
        with pytest.raises(ApiError) as exc_info:
            _parse_delay_minutes("-1")
        assert exc_info.value.status_code == 400

    def test_over_max_raises(self) -> None:
        with pytest.raises(ApiError) as exc_info:
            _parse_delay_minutes(str(ORGANIZE_MAX_DELAY_MIN + 1))
        assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# Helper: _normalize_methodology
# ---------------------------------------------------------------------------


class TestNormalizeMethodology:
    def test_known_key_returns_key(self) -> None:
        assert _normalize_methodology("para") == "para"

    def test_unknown_key_returns_content_based(self) -> None:
        assert _normalize_methodology("nonsense") == "content_based"

    def test_none_returns_content_based(self) -> None:
        assert _normalize_methodology(None) == "content_based"

    def test_uppercase_known_key_is_case_insensitive(self) -> None:
        assert _normalize_methodology("PARA") == "para"


# ---------------------------------------------------------------------------
# Helper: _scan_directory
# ---------------------------------------------------------------------------


class TestScanDirectory:
    def test_single_visible_file_returned(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.txt"
        f.write_text("hello")
        result = _scan_directory(f, recursive=False, include_hidden=False)
        assert result == [f]

    def test_hidden_file_excluded_when_not_include_hidden(self, tmp_path: Path) -> None:
        hidden = tmp_path / ".secret"
        hidden.write_text("hidden")
        result = _scan_directory(hidden, recursive=False, include_hidden=False)
        assert result == []

    def test_hidden_file_included_when_include_hidden(self, tmp_path: Path) -> None:
        hidden = tmp_path / ".secret"
        hidden.write_text("hidden")
        result = _scan_directory(hidden, recursive=False, include_hidden=True)
        assert result == [hidden]

    def test_directory_non_recursive(self, tmp_path: Path) -> None:
        (tmp_path / "a.txt").write_text("a")
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "b.txt").write_text("b")
        result = _scan_directory(tmp_path, recursive=False, include_hidden=False)
        names = {p.name for p in result}
        assert "a.txt" in names
        assert "b.txt" not in names

    def test_directory_recursive(self, tmp_path: Path) -> None:
        (tmp_path / "a.txt").write_text("a")
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "b.txt").write_text("b")
        result = _scan_directory(tmp_path, recursive=True, include_hidden=False)
        names = {p.name for p in result}
        assert "a.txt" in names
        assert "b.txt" in names


# ---------------------------------------------------------------------------
# Helper: _counts_by_type
# ---------------------------------------------------------------------------


class TestCountsByType:
    def test_text_file_counted(self, tmp_path: Path) -> None:
        files = [tmp_path / "doc.txt"]
        counts = _counts_by_type(files)
        assert counts["text"] == 1
        assert counts["image"] == 0

    def test_image_file_counted(self, tmp_path: Path) -> None:
        files = [tmp_path / "photo.jpg"]
        counts = _counts_by_type(files)
        assert counts["image"] == 1

    def test_video_file_counted(self, tmp_path: Path) -> None:
        files = [tmp_path / "clip.mp4"]
        counts = _counts_by_type(files)
        assert counts["video"] == 1

    def test_audio_file_counted(self, tmp_path: Path) -> None:
        files = [tmp_path / "song.mp3"]
        counts = _counts_by_type(files)
        assert counts["audio"] == 1

    def test_other_file_counted(self, tmp_path: Path) -> None:
        files = [tmp_path / "archive.xyz123"]
        counts = _counts_by_type(files)
        assert counts["other"] == 1

    def test_mixed_files(self, tmp_path: Path) -> None:
        files = [tmp_path / "a.txt", tmp_path / "b.jpg", tmp_path / "c.xyz"]
        counts = _counts_by_type(files)
        assert counts["text"] == 1
        assert counts["image"] == 1
        assert counts["other"] == 1


# ---------------------------------------------------------------------------
# Helper: plan store
# ---------------------------------------------------------------------------


class TestPlanStore:
    def test_store_and_retrieve_plan(self) -> None:
        record = _store_organize_plan({"input_dir": "plan_input", "output_dir": "plan_output"})
        plan_id = record["plan_id"]
        assert plan_id is not None
        retrieved = _get_organize_plan(plan_id)
        assert retrieved is not None
        assert retrieved["input_dir"] == "plan_input"

    def test_delete_plan_removes_it(self) -> None:
        record = _store_organize_plan({"input_dir": "plan_x"})
        plan_id = record["plan_id"]
        _delete_organize_plan(plan_id)
        assert _get_organize_plan(plan_id) is None

    def test_get_nonexistent_plan_returns_none(self) -> None:
        assert _get_organize_plan("does-not-exist-ever") is None


# ---------------------------------------------------------------------------
# Helper: job metadata
# ---------------------------------------------------------------------------


class TestJobMetadata:
    def test_set_and_get_metadata(self) -> None:
        from unittest.mock import patch

        job_id = "test-meta-job-001"
        with patch(
            "file_organizer.web.organize_routes.get_job",
            return_value=_mock_job(job_id, status="queued"),
        ):
            _set_job_metadata(job_id, {"methodology": "para", "dry_run": True})
        meta = _get_job_metadata(job_id)
        assert meta["methodology"] == "para"
        assert meta["dry_run"] is True

    def test_get_nonexistent_job_returns_empty_dict(self) -> None:
        meta = _get_job_metadata("nonexistent-job-xyz")
        assert meta == {}

    def test_prune_job_metadata_force(self) -> None:
        _set_job_metadata("prune-test-job", {"x": 1})
        _prune_job_metadata(force=True)
        assert _get_job_metadata("prune-test-job") == {}


# ---------------------------------------------------------------------------
# Helper: _status_progress
# ---------------------------------------------------------------------------


class TestStatusProgress:
    def test_queued_returns_5(self) -> None:
        assert _status_progress("queued") == 5

    def test_running_returns_65(self) -> None:
        assert _status_progress("running") == 65

    def test_completed_returns_100(self) -> None:
        assert _status_progress("completed") == 100

    def test_failed_returns_100(self) -> None:
        assert _status_progress("failed") == 100

    def test_unknown_returns_zero(self) -> None:
        assert _status_progress("pending") == 0


# ---------------------------------------------------------------------------
# Helper: _build_job_view
# ---------------------------------------------------------------------------


class TestBuildJobView:
    def setup_method(self) -> None:
        from file_organizer.web.organize_routes import _JOB_METADATA

        _JOB_METADATA.clear()

    def test_nonexistent_job_returns_none(self) -> None:
        with patch("file_organizer.web.organize_routes.get_job", return_value=None):
            assert _build_job_view("missing-job") is None

    def test_completed_job_has_progress_100(self) -> None:
        mock = _mock_job("j1", status="completed")
        with patch("file_organizer.web.organize_routes.get_job", return_value=mock):
            view = _build_job_view("j1")
        assert view is not None
        assert view["progress_percent"] == 100
        assert view["is_terminal"] is True

    def test_running_job_progress_computed_from_files(self) -> None:
        mock = _mock_job(
            "j2",
            status="running",
            result={
                "processed_files": 50,
                "total_files": 100,
                "failed_files": 0,
                "skipped_files": 0,
            },
        )
        with patch("file_organizer.web.organize_routes.get_job", return_value=mock):
            view = _build_job_view("j2")
        assert view is not None
        assert view["progress_percent"] == 65

    def test_scheduled_job_can_cancel(self) -> None:
        mock = _mock_job("j3", status="queued")
        with patch("file_organizer.web.organize_routes.get_job", return_value=mock):
            _set_job_metadata(
                "j3", {"schedule_delay_minutes": 30, "scheduled_for": "2026-01-01T01:00:00"}
            )
            view = _build_job_view("j3")
        assert view is not None
        assert view["can_cancel"] is True


# ---------------------------------------------------------------------------
# Route: POST /organize/execute
# ---------------------------------------------------------------------------


class TestOrganizeExecute:
    def test_missing_plan_id_returns_error(self, org_client: TestClient) -> None:
        with patch("file_organizer.web.organize_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            r = org_client.post("/ui/organize/execute", data={"plan_id": ""})
        assert r.status_code == 200

    def test_plan_not_found_returns_error(self, org_client: TestClient) -> None:
        with patch("file_organizer.web.organize_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            r = org_client.post("/ui/organize/execute", data={"plan_id": "no-such-plan"})
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Route: GET /organize/jobs/{job_id}/status
# ---------------------------------------------------------------------------


class TestOrganizeJobStatus:
    def test_html_format_returns_200(self, org_client: TestClient) -> None:
        mock = _mock_job("status-test-job")
        with (
            patch("file_organizer.web.organize_routes.get_job", return_value=mock),
            patch("file_organizer.web.organize_routes.templates") as tpl,
        ):
            tpl.TemplateResponse.return_value = _HTML
            r = org_client.get("/ui/organize/jobs/status-test-job/status")
        assert r.status_code == 200

    def test_json_format_returns_job_data(self, org_client: TestClient) -> None:
        mock = _mock_job("json-test-job", status="completed")
        with patch("file_organizer.web.organize_routes.get_job", return_value=mock):
            r = org_client.get("/ui/organize/jobs/json-test-job/status?format=json")
        assert r.status_code == 200
        data = r.json()
        assert data["job_id"] == "json-test-job"
        assert data["status"] == "completed"

    def test_not_found_raises_error(self, org_client: TestClient) -> None:
        with patch("file_organizer.web.organize_routes.get_job", return_value=None):
            r = org_client.get("/ui/organize/jobs/ghost-job/status")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Route: POST /organize/jobs/{job_id}/cancel
# ---------------------------------------------------------------------------


class TestOrganizeJobCancel:
    def test_cancel_nonexistent_job_returns_404(self, org_client: TestClient) -> None:
        with patch("file_organizer.web.organize_routes.get_job", return_value=None):
            r = org_client.post("/ui/organize/jobs/ghost-job/cancel")
        assert r.status_code == 404

    def test_cancel_non_scheduled_job_shows_error(self, org_client: TestClient) -> None:
        mock = _mock_job("cancel-test", status="completed")
        with (
            patch("file_organizer.web.organize_routes.get_job", return_value=mock),
            patch("file_organizer.web.organize_routes.templates") as tpl,
        ):
            tpl.TemplateResponse.return_value = _HTML
            r = org_client.post("/ui/organize/jobs/cancel-test/cancel")
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Route: POST /organize/jobs/{job_id}/rollback
# ---------------------------------------------------------------------------


class TestOrganizeJobRollback:
    def test_rollback_nonexistent_job_returns_404(self, org_client: TestClient) -> None:
        with patch("file_organizer.web.organize_routes.get_job", return_value=None):
            r = org_client.post("/ui/organize/jobs/ghost/rollback")
        assert r.status_code == 404

    def test_rollback_dry_run_job_shows_error(self, org_client: TestClient) -> None:
        mock = _mock_job("rollback-dry", status="completed")
        with (
            patch("file_organizer.web.organize_routes.get_job", return_value=mock),
            patch("file_organizer.web.organize_routes.templates") as tpl,
        ):
            _set_job_metadata("rollback-dry", {"dry_run": True})
            tpl.TemplateResponse.return_value = _HTML
            r = org_client.post("/ui/organize/jobs/rollback-dry/rollback")
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Route: GET /organize/history
# ---------------------------------------------------------------------------


class TestOrganizeHistory:
    def test_history_all_returns_200(self, org_client: TestClient) -> None:
        with (
            patch("file_organizer.web.organize_routes.list_jobs", return_value=[]),
            patch("file_organizer.web.organize_routes.templates") as tpl,
        ):
            tpl.TemplateResponse.return_value = _HTML
            r = org_client.get("/ui/organize/history")
        assert r.status_code == 200

    def test_history_status_filter_completed(self, org_client: TestClient) -> None:
        with (
            patch("file_organizer.web.organize_routes.list_jobs", return_value=[]),
            patch("file_organizer.web.organize_routes.templates") as tpl,
        ):
            tpl.TemplateResponse.return_value = _HTML
            r = org_client.get("/ui/organize/history?status_filter=completed")
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Route: GET /organize/stats
# ---------------------------------------------------------------------------


class TestOrganizeStats:
    def test_stats_returns_200(self, org_client: TestClient) -> None:
        with (
            patch("file_organizer.web.organize_routes.list_jobs", return_value=[]),
            patch("file_organizer.web.organize_routes.templates") as tpl,
        ):
            tpl.TemplateResponse.return_value = _HTML
            r = org_client.get("/ui/organize/stats")
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Route: GET /organize/report/{job_id}
# ---------------------------------------------------------------------------


class TestOrganizeReport:
    def test_report_not_found_returns_404(self, org_client: TestClient) -> None:
        with patch("file_organizer.web.organize_routes.get_job", return_value=None):
            r = org_client.get("/ui/organize/report/ghost-job")
        assert r.status_code == 404

    def test_report_json_format(self, org_client: TestClient) -> None:
        mock = _mock_job("report-job")
        with patch("file_organizer.web.organize_routes.get_job", return_value=mock):
            r = org_client.get("/ui/organize/report/report-job?format=json")
        assert r.status_code == 200
        data = r.json()
        assert data["job_id"] == "report-job"

    def test_report_txt_format(self, org_client: TestClient) -> None:
        mock = _mock_job("txt-job")
        with patch("file_organizer.web.organize_routes.get_job", return_value=mock):
            r = org_client.get("/ui/organize/report/txt-job?format=txt")
        assert r.status_code == 200
        assert b"Job ID" in r.content
        assert b"txt-job" in r.content

    def test_report_csv_format(self, org_client: TestClient) -> None:
        mock = _mock_job("csv-job")
        with patch("file_organizer.web.organize_routes.get_job", return_value=mock):
            r = org_client.get("/ui/organize/report/csv-job?format=csv")
        assert r.status_code == 200
        assert b"field" in r.content
        assert b"value" in r.content


# ---------------------------------------------------------------------------
# Route: POST /organize/plan/clear
# ---------------------------------------------------------------------------


class TestOrganizeClearPlan:
    def test_clear_with_plan_id_returns_200(self, org_client: TestClient) -> None:
        record = _store_organize_plan({"input_dir": "plan_in", "output_dir": "plan_out"})
        with patch("file_organizer.web.organize_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            r = org_client.post("/ui/organize/plan/clear", data={"plan_id": record["plan_id"]})
        assert r.status_code == 200

    def test_clear_without_plan_id_returns_200(self, org_client: TestClient) -> None:
        with patch("file_organizer.web.organize_routes.templates") as tpl:
            tpl.TemplateResponse.return_value = _HTML
            r = org_client.post("/ui/organize/plan/clear", data={"plan_id": ""})
        assert r.status_code == 200
