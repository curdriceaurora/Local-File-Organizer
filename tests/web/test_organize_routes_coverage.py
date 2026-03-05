"""Coverage tests for file_organizer.web.organize_routes — route handler branches."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from file_organizer.api.exceptions import ApiError

pytestmark = pytest.mark.unit


@pytest.fixture()
def mock_templates():
    response = MagicMock()
    response.headers = {}
    with patch("file_organizer.web.organize_routes.templates") as tmpl:
        tmpl.TemplateResponse.return_value = response
        yield tmpl


class TestOrganizeDashboardRoute:
    """Covers organize_dashboard handler."""

    def test_dashboard(self, tmp_path, mock_templates) -> None:
        from file_organizer.web.organize_routes import organize_dashboard

        settings = MagicMock()
        request = MagicMock()
        with (
            patch("file_organizer.web._helpers.base_context", return_value={"request": request}),
            patch("file_organizer.web.organize_routes.allowed_roots", return_value=[tmp_path]),
            patch(
                "file_organizer.web.organize_routes._build_organize_stats",
                return_value={"total_jobs": 0},
            ),
        ):
            organize_dashboard(request, settings)
        mock_templates.TemplateResponse.assert_called_once()


class TestOrganizeScanRoute:
    """Covers organize_scan handler."""

    def test_scan_missing_input(self, mock_templates) -> None:
        from file_organizer.web.organize_routes import organize_scan

        request = MagicMock()
        settings = MagicMock()
        organize_scan(
            request, settings, input_dir="", output_dir="/out", methodology="content_based"
        )
        mock_templates.TemplateResponse.assert_called_once()

    def test_scan_missing_output(self, mock_templates) -> None:
        from file_organizer.web.organize_routes import organize_scan

        request = MagicMock()
        settings = MagicMock()
        organize_scan(
            request, settings, input_dir="/in", output_dir="", methodology="content_based"
        )
        mock_templates.TemplateResponse.assert_called_once()


class TestOrganizeClearPlanRoute:
    """Covers organize_clear_plan handler."""

    def test_clear_plan(self, mock_templates) -> None:
        from file_organizer.web.organize_routes import organize_clear_plan

        request = MagicMock()
        with patch("file_organizer.web.organize_routes._delete_organize_plan"):
            organize_clear_plan(request, plan_id="test-id")
        mock_templates.TemplateResponse.assert_called_once()

    def test_clear_plan_empty_id(self, mock_templates) -> None:
        from file_organizer.web.organize_routes import organize_clear_plan

        organize_clear_plan(MagicMock(), plan_id="")
        mock_templates.TemplateResponse.assert_called_once()


class TestOrganizeExecuteRoute:
    """Covers organize_execute handler."""

    def test_execute_missing_plan_id(self, mock_templates) -> None:
        from file_organizer.web.organize_routes import organize_execute

        request = MagicMock()
        background = MagicMock()
        settings = MagicMock()
        organize_execute(
            request,
            background,
            settings,
            plan_id="",
            dry_run="0",
            schedule_delay_minutes="0",
        )
        # Should have error
        mock_templates.TemplateResponse.assert_called_once()

    def test_execute_plan_not_found(self, mock_templates) -> None:
        from file_organizer.web.organize_routes import organize_execute

        request = MagicMock()
        background = MagicMock()
        settings = MagicMock()
        with patch("file_organizer.web.organize_routes._get_organize_plan", return_value=None):
            organize_execute(
                request,
                background,
                settings,
                plan_id="missing",
                dry_run="0",
                schedule_delay_minutes="0",
            )
        mock_templates.TemplateResponse.assert_called_once()


class TestOrganizeJobStatusRoute:
    """Covers organize_job_status handler."""

    def test_status_html(self, mock_templates) -> None:
        from file_organizer.web.organize_routes import organize_job_status

        job_view = {
            "job_id": "j1",
            "status": "completed",
            "is_terminal": True,
            "progress_percent": 100,
        }
        request = MagicMock()
        with patch("file_organizer.web.organize_routes._build_job_view", return_value=job_view):
            organize_job_status(request, "j1", format="html")
        mock_templates.TemplateResponse.assert_called_once()

    def test_status_json(self) -> None:
        from file_organizer.web.organize_routes import organize_job_status

        job_view = {
            "job_id": "j1",
            "status": "completed",
            "is_terminal": True,
            "progress_percent": 100,
        }
        request = MagicMock()
        with patch("file_organizer.web.organize_routes._build_job_view", return_value=job_view):
            resp = organize_job_status(request, "j1", format="json")
        assert resp.status_code == 200

    def test_status_not_found(self) -> None:
        from file_organizer.web.organize_routes import organize_job_status

        request = MagicMock()
        with (
            patch("file_organizer.web.organize_routes._build_job_view", return_value=None),
            pytest.raises(ApiError) as exc_info,
        ):
            organize_job_status(request, "missing", format="html")
        assert exc_info.value.status_code == 404


class TestOrganizeJobCancelRoute:
    """Covers organize_job_cancel handler."""

    def test_cancel_success(self, mock_templates) -> None:
        from file_organizer.web.organize_routes import organize_job_cancel

        job_view = {"job_id": "j1", "status": "queued", "can_cancel": True}
        request = MagicMock()
        with (
            patch("file_organizer.web.organize_routes._build_job_view", return_value=job_view),
            patch("file_organizer.web.organize_routes._cancel_scheduled_job", return_value=True),
        ):
            organize_job_cancel(request, "j1")
        mock_templates.TemplateResponse.assert_called_once()

    def test_cancel_not_scheduled(self, mock_templates) -> None:
        from file_organizer.web.organize_routes import organize_job_cancel

        job_view = {"job_id": "j1", "status": "running", "can_cancel": False}
        request = MagicMock()
        with (
            patch("file_organizer.web.organize_routes._build_job_view", return_value=job_view),
            patch("file_organizer.web.organize_routes._cancel_scheduled_job", return_value=False),
        ):
            organize_job_cancel(request, "j1")
        mock_templates.TemplateResponse.assert_called_once()

    def test_cancel_not_found(self) -> None:
        from file_organizer.web.organize_routes import organize_job_cancel

        request = MagicMock()
        with (
            patch("file_organizer.web.organize_routes._build_job_view", return_value=None),
            pytest.raises(ApiError),
        ):
            organize_job_cancel(request, "missing")


class TestOrganizeJobRollbackRoute:
    """Covers organize_job_rollback handler."""

    def test_rollback_not_allowed(self, mock_templates) -> None:
        from file_organizer.web.organize_routes import organize_job_rollback

        job_view = {
            "job_id": "j1",
            "status": "running",
            "can_rollback": False,
        }
        request = MagicMock()
        with patch("file_organizer.web.organize_routes._build_job_view", return_value=job_view):
            organize_job_rollback(request, "j1")
        mock_templates.TemplateResponse.assert_called_once()

    def test_rollback_success(self, mock_templates) -> None:
        from file_organizer.web.organize_routes import organize_job_rollback

        job_view = {
            "job_id": "j1",
            "status": "completed",
            "can_rollback": True,
        }
        request = MagicMock()
        mock_manager = MagicMock()
        mock_manager.undo_last_operation.return_value = True
        with (
            patch("file_organizer.web.organize_routes._build_job_view", return_value=job_view),
            patch("file_organizer.undo.undo_manager.UndoManager", return_value=mock_manager),
        ):
            organize_job_rollback(request, "j1")
        mock_templates.TemplateResponse.assert_called_once()

    def test_rollback_exception(self, mock_templates) -> None:
        from file_organizer.web.organize_routes import organize_job_rollback

        job_view = {
            "job_id": "j1",
            "status": "completed",
            "can_rollback": True,
        }
        request = MagicMock()
        with (
            patch("file_organizer.web.organize_routes._build_job_view", return_value=job_view),
            patch(
                "file_organizer.undo.undo_manager.UndoManager",
                side_effect=RuntimeError("undo failed"),
            ),
        ):
            organize_job_rollback(request, "j1")
        mock_templates.TemplateResponse.assert_called_once()


class TestOrganizeHistoryRoute:
    """Covers organize_history handler."""

    def test_history(self, mock_templates) -> None:
        from file_organizer.web.organize_routes import organize_history

        request = MagicMock()
        with patch("file_organizer.web.organize_routes._list_organize_jobs", return_value=[]):
            organize_history(request, status_filter="all", limit=50)
        mock_templates.TemplateResponse.assert_called_once()


class TestOrganizeStatsRoute:
    """Covers organize_stats handler."""

    def test_stats(self, mock_templates) -> None:
        from file_organizer.web.organize_routes import organize_stats

        request = MagicMock()
        with patch(
            "file_organizer.web.organize_routes._build_organize_stats",
            return_value={"total_jobs": 0},
        ):
            organize_stats(request)
        mock_templates.TemplateResponse.assert_called_once()


class TestOrganizeReportRoute:
    """Covers organize_report handler."""

    def test_report_json(self) -> None:
        from file_organizer.web.organize_routes import organize_report

        job_view = {
            "job_id": "j1",
            "status": "completed",
            "created_at": "2025-01-01",
            "updated_at": "2025-01-02",
            "methodology": "para",
            "input_dir": "/in",
            "output_dir": "/out",
            "dry_run": False,
            "processed_files": 10,
            "total_files": 12,
            "failed_files": 2,
            "skipped_files": 0,
            "error": None,
            "result": {"organized_structure": {}},
        }
        with patch("file_organizer.web.organize_routes._build_job_view", return_value=job_view):
            resp = organize_report("j1", format="json")
        assert resp.status_code == 200

    def test_report_txt(self) -> None:
        from file_organizer.web.organize_routes import organize_report

        job_view = {
            "job_id": "j1",
            "status": "completed",
            "created_at": "2025-01-01",
            "updated_at": "2025-01-02",
            "methodology": "para",
            "input_dir": "/in",
            "output_dir": "/out",
            "dry_run": False,
            "processed_files": 10,
            "total_files": 12,
            "failed_files": 2,
            "skipped_files": 0,
            "error": None,
            "result": {"organized_structure": {}},
        }
        with patch("file_organizer.web.organize_routes._build_job_view", return_value=job_view):
            resp = organize_report("j1", format="txt")
        assert resp.media_type == "text/plain"

    def test_report_csv(self) -> None:
        from file_organizer.web.organize_routes import organize_report

        job_view = {
            "job_id": "j1",
            "status": "completed",
            "created_at": "2025-01-01",
            "updated_at": "2025-01-02",
            "methodology": "para",
            "input_dir": "/in",
            "output_dir": "/out",
            "dry_run": False,
            "processed_files": 10,
            "total_files": 12,
            "failed_files": 2,
            "skipped_files": 0,
            "error": None,
            "result": {"organized_structure": {"docs": ["a.txt", "b.pdf"]}},
        }
        with patch("file_organizer.web.organize_routes._build_job_view", return_value=job_view):
            resp = organize_report("j1", format="csv")
        assert resp.media_type == "text/csv"

    def test_report_not_found(self) -> None:
        from file_organizer.web.organize_routes import organize_report

        with (
            patch("file_organizer.web.organize_routes._build_job_view", return_value=None),
            pytest.raises(ApiError),
        ):
            organize_report("missing", format="json")


class TestRunOrganizeJob:
    """Covers _run_organize_job."""

    def test_run_success(self) -> None:
        from file_organizer.web.organize_routes import _run_organize_job

        mock_organizer = MagicMock()
        mock_result = MagicMock()
        mock_result.errors = []
        mock_organizer.organize.return_value = mock_result

        request = MagicMock()
        request.dry_run = False
        request.use_hardlinks = False
        request.input_dir = "/in"
        request.output_dir = "/out"
        request.skip_existing = True

        with (
            patch("file_organizer.web.organize_routes.update_job"),
            patch("file_organizer.web.organize_routes.FileOrganizer", return_value=mock_organizer),
        ):
            _run_organize_job("j1", request)

    def test_run_failure(self) -> None:
        from file_organizer.web.organize_routes import _run_organize_job

        request = MagicMock()
        request.dry_run = False
        request.use_hardlinks = False

        with (
            patch("file_organizer.web.organize_routes.update_job"),
            patch(
                "file_organizer.web.organize_routes.FileOrganizer", side_effect=RuntimeError("boom")
            ),
        ):
            _run_organize_job("j1", request)


class TestScheduleJob:
    """Covers _schedule_job."""

    def test_schedule_immediate(self) -> None:
        from file_organizer.web.organize_routes import _schedule_job

        request = MagicMock()
        request.dry_run = False
        request.use_hardlinks = False

        with (
            patch("file_organizer.web.organize_routes.update_job"),
            patch("file_organizer.web.organize_routes.FileOrganizer", return_value=MagicMock()),
        ):
            _schedule_job("j1", request, delay_minutes=0)

    def test_schedule_delayed(self) -> None:
        from file_organizer.web.organize_routes import (
            _SCHEDULED_TIMERS,
            _schedule_job,
        )

        request = MagicMock()
        _schedule_job("j-delayed", request, delay_minutes=1)
        assert "j-delayed" in _SCHEDULED_TIMERS
        # Clean up
        timer = _SCHEDULED_TIMERS.pop("j-delayed")
        timer.cancel()


class TestBuildPlanMovements:
    """Covers _build_plan_movements."""

    def test_movements(self, tmp_path) -> None:
        from file_organizer.web.organize_routes import _build_plan_movements

        files = [tmp_path / "a.txt", tmp_path / "b.pdf"]
        preview = MagicMock()
        preview.organized_structure = {"docs": ["a.txt"], "media": ["b.pdf"]}
        output_dir = tmp_path / "output"

        movements = _build_plan_movements(files, output_dir, preview)
        assert len(movements) == 2
        assert movements[0]["file_name"] in ("a.txt", "b.pdf")
