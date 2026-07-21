"""Coverage tests for file_organizer.web.organize_routes — route handler branches."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.api.exceptions import ApiError
from file_organizer.core.plan import OrganizationPlan, build_plan_from_processed
from file_organizer.core.types import OrganizationResult
from file_organizer.services.text_processor import ProcessedFile

pytestmark = [pytest.mark.unit, pytest.mark.ci, pytest.mark.integration]


def _plan_for_routes(tmp_path: Path) -> OrganizationPlan:
    source = tmp_path / "input" / "notes.txt"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("hello")
    return build_plan_from_processed(
        input_path=source.parent,
        output_path=tmp_path / "output",
        processed=[
            ProcessedFile(
                file_path=source,
                description="Categorized into docs",
                folder_name="docs",
                filename=source.stem,
            )
        ],
        skip_existing=True,
        use_hardlinks=False,
        total_files=1,
        skipped_files=0,
        deduplicated_files=0,
    )


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

    def test_execute_rejects_path_mismatch(self, tmp_path, mock_templates) -> None:
        from file_organizer.web.organize_routes import organize_execute

        plan = _plan_for_routes(tmp_path)
        request = MagicMock()
        background = MagicMock()
        settings = MagicMock()
        settings.allowed_paths = [str(tmp_path)]
        stored_plan = {
            "input_dir": str(tmp_path / "different-input"),
            "output_dir": plan.output_path,
            "skip_existing": True,
            "use_hardlinks": False,
            "methodology": "none",
            "executable_plan": plan.to_dict(),
        }

        with patch(
            "file_organizer.web.organize_routes._get_organize_plan", return_value=stored_plan
        ):
            organize_execute(
                request,
                background,
                settings,
                plan_id="plan-1",
                dry_run="0",
                schedule_delay_minutes="0",
            )

        context = mock_templates.TemplateResponse.call_args.args[2]
        assert (
            context["error_message"] == "Stored plan paths do not match the requested safe paths."
        )
        background.add_task.assert_not_called()

    def test_execute_rejects_plan_without_executable_operations(
        self, tmp_path, mock_templates
    ) -> None:
        from file_organizer.web.organize_routes import organize_execute

        request = MagicMock()
        background = MagicMock()
        settings = MagicMock()
        settings.allowed_paths = [str(tmp_path)]
        stored_plan = {
            "input_dir": str(tmp_path / "input"),
            "output_dir": str(tmp_path / "output"),
            "skip_existing": True,
            "use_hardlinks": False,
            "methodology": "none",
            "executable_plan": None,
        }

        with patch(
            "file_organizer.web.organize_routes._get_organize_plan", return_value=stored_plan
        ):
            organize_execute(
                request,
                background,
                settings,
                plan_id="plan-1",
                dry_run="0",
                schedule_delay_minutes="0",
            )

        context = mock_templates.TemplateResponse.call_args.args[2]
        assert context["error_message"] == "Stored plan does not contain executable operations."
        background.add_task.assert_not_called()

    def test_execute_queues_immediate_job_from_stored_plan(self, tmp_path, mock_templates) -> None:
        from file_organizer.web.organize_routes import organize_execute

        plan = _plan_for_routes(tmp_path)
        request = MagicMock()
        background = MagicMock()
        settings = MagicMock()
        settings.allowed_paths = [str(tmp_path)]
        stored_plan = {
            "input_dir": plan.input_path,
            "output_dir": plan.output_path,
            "skip_existing": True,
            "use_hardlinks": False,
            "methodology": "none",
            "executable_plan": plan.to_dict(),
        }

        with patch(
            "file_organizer.web.organize_routes._get_organize_plan", return_value=stored_plan
        ):
            organize_execute(
                request,
                background,
                settings,
                plan_id="plan-1",
                dry_run="0",
                schedule_delay_minutes="0",
            )

        context = mock_templates.TemplateResponse.call_args.args[2]
        assert context["error_message"] is None
        assert context["info_message"] == "Organization job queued."
        assert context["job"] is not None
        background.add_task.assert_called_once()
        # The queued task consumes the exact reviewed executable plan.
        queued_plan = background.add_task.call_args.args[2]
        assert queued_plan["plan_id"] == plan.plan_id

    def test_execute_schedules_delayed_job_from_stored_plan(self, tmp_path, mock_templates) -> None:
        from file_organizer.web.organize_routes import organize_execute

        plan = _plan_for_routes(tmp_path)
        request = MagicMock()
        background = MagicMock()
        settings = MagicMock()
        settings.allowed_paths = [str(tmp_path)]
        stored_plan = {
            "input_dir": plan.input_path,
            "output_dir": plan.output_path,
            "skip_existing": True,
            "use_hardlinks": False,
            "methodology": "none",
            "executable_plan": plan.to_dict(),
        }

        with (
            patch(
                "file_organizer.web.organize_routes._get_organize_plan", return_value=stored_plan
            ),
            patch("file_organizer.web.organize_routes._schedule_plan_job") as schedule,
        ):
            organize_execute(
                request,
                background,
                settings,
                plan_id="plan-1",
                dry_run="0",
                schedule_delay_minutes="5",
            )

        context = mock_templates.TemplateResponse.call_args.args[2]
        assert context["error_message"] is None
        assert context["info_message"] == "Job scheduled to start in 5 minute(s)."
        schedule.assert_called_once()
        background.add_task.assert_not_called()


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
            "transaction_id": "txn-1",
        }
        request = MagicMock()
        mock_manager = MagicMock()
        mock_manager.undo_transaction.return_value = True
        with (
            patch("file_organizer.web.organize_routes._build_job_view", return_value=job_view),
            patch("file_organizer.undo.undo_manager.UndoManager", return_value=mock_manager),
        ):
            organize_job_rollback(request, "j1")
        mock_manager.undo_transaction.assert_called_once_with("txn-1")
        mock_templates.TemplateResponse.assert_called_once()

    def test_rollback_exception(self, mock_templates) -> None:
        from file_organizer.web.organize_routes import organize_job_rollback

        job_view = {
            "job_id": "j1",
            "status": "completed",
            "can_rollback": True,
            "transaction_id": "txn-1",
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


class TestRunOrganizePlanJob:
    """Covers executable-plan job execution."""

    def test_result_from_plan_preview(self, tmp_path) -> None:
        from file_organizer.web.organize_routes import _result_from_plan_preview

        plan = _plan_for_routes(tmp_path)

        result = _result_from_plan_preview(plan)

        assert result.total_files == plan.total_files
        assert result.processed_files == plan.processed_files
        assert result.organized_structure == {"docs": ["notes.txt"]}
        assert result.plan == plan

    def test_run_dry_run_uses_stored_plan_preview(self, tmp_path) -> None:
        from file_organizer.web.organize_routes import _run_organize_plan_job

        plan = _plan_for_routes(tmp_path)

        with patch("file_organizer.web.organize_routes.update_job") as mock_update:
            _run_organize_plan_job("j1", plan.to_dict(), dry_run=True)

        assert mock_update.call_args_list[-1].kwargs["status"] == "completed"
        assert mock_update.call_args_list[-1].kwargs["result"]["processed_files"] == 1

    def test_run_executes_stored_plan(self, tmp_path) -> None:
        from file_organizer.web.organize_routes import _run_organize_plan_job

        plan = _plan_for_routes(tmp_path)
        result = OrganizationResult(
            total_files=1,
            processed_files=1,
            organized_structure={"docs": ["notes.txt"]},
            plan=plan,
        )
        organizer = MagicMock()
        organizer.execute_plan.return_value = result

        with (
            patch("file_organizer.web.organize_routes.update_job") as mock_update,
            patch("file_organizer.web.organize_routes.FileOrganizer", return_value=organizer),
        ):
            _run_organize_plan_job("j1", plan.to_dict(), dry_run=False)

        organizer.execute_plan.assert_called_once()
        assert mock_update.call_args_list[-1].kwargs["status"] == "completed"

    def test_run_reports_invalid_plan_failure(self) -> None:
        from file_organizer.web.organize_routes import _run_organize_plan_job

        with patch("file_organizer.web.organize_routes.update_job") as mock_update:
            _run_organize_plan_job("j1", {"operations": []}, dry_run=True)

        assert mock_update.call_args_list[-1].kwargs["status"] == "failed"
        assert mock_update.call_args_list[-1].kwargs["error"]


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


class TestSchedulePlanJob:
    """Covers _schedule_plan_job."""

    def test_schedule_immediate(self, tmp_path) -> None:
        from file_organizer.web.organize_routes import _schedule_plan_job

        plan = _plan_for_routes(tmp_path)

        with patch("file_organizer.web.organize_routes._run_organize_plan_job") as mock_run:
            _schedule_plan_job("j1", plan.to_dict(), delay_minutes=0, dry_run=True)

        mock_run.assert_called_once_with("j1", plan.to_dict(), dry_run=True)

    def test_schedule_delayed(self, tmp_path) -> None:
        from file_organizer.web.organize_routes import (
            _SCHEDULED_TIMERS,
            _schedule_plan_job,
        )

        plan = _plan_for_routes(tmp_path)

        _schedule_plan_job("j-plan-delayed", plan.to_dict(), delay_minutes=1, dry_run=True)
        assert "j-plan-delayed" in _SCHEDULED_TIMERS
        timer = _SCHEDULED_TIMERS.pop("j-plan-delayed")
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
