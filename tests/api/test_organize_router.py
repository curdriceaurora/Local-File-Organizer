"""Tests for the organize API router."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_current_active_user, get_settings
from file_organizer.api.exceptions import setup_exception_handlers
from file_organizer.api.routers import organize as organize_router_module
from file_organizer.api.routers.organize import get_organization_service, router
from file_organizer.core.organization_service import OrganizationService
from file_organizer.core.organize_options import OrganizeOptions
from file_organizer.core.organizer import OrganizationResult
from file_organizer.core.plan import build_plan_from_processed
from file_organizer.models.base import ModelConfig, ModelType
from file_organizer.services.text_processor import ProcessedFile

# Route-level TestClient tests: counted for the integration coverage gate as
# well, so the plan preview/execute API paths added for #1504 keep
# api/routers/organize.py above its integration floor.
pytestmark = pytest.mark.ci


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
    app.dependency_overrides[get_organization_service] = lambda: OrganizationService(
        text_model_config=ModelConfig("test-model:latest", ModelType.TEXT),
        vision_model_config=ModelConfig("vis:3b", ModelType.VISION),
        organizer_factory=organize_router_module.FileOrganizer,
    )
    app.include_router(router, prefix="/api/v1")
    client = TestClient(app, raise_server_exceptions=False)
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


def _make_plan(tmp_path: Path, *, use_hardlinks: bool = False):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir(exist_ok=True)
    output_dir.mkdir(exist_ok=True)
    source = input_dir / "report.txt"
    source.write_text("hello")
    return build_plan_from_processed(
        input_path=input_dir,
        output_path=output_dir,
        processed=[
            ProcessedFile(
                file_path=source,
                description="Categorized into Documents",
                folder_name="Documents",
                filename="report",
            )
        ],
        skip_existing=True,
        use_hardlinks=use_hardlinks,
        total_files=1,
        skipped_files=0,
        deduplicated_files=0,
        options=OrganizeOptions(
            use_hardlinks=use_hardlinks,
            text_model="test-model:latest",
            vision_model="vis:3b",
            text_provider="ollama",
            vision_provider="ollama",
        ),
    )


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
        # Preview goes through the canonical service with resolved options.
        call = mock_organizer_cls.call_args
        assert call.kwargs["dry_run"] is True
        assert call.kwargs["organize_options"].use_hardlinks is True

    @patch("file_organizer.api.routers.organize.FileOrganizer")
    def test_preview_preserves_every_canonical_option(
        self, mock_organizer_cls, tmp_path: Path
    ) -> None:
        (tmp_path / "input").mkdir()
        (tmp_path / "output").mkdir()
        mock_instance = MagicMock()
        mock_instance.organize.return_value = _make_result()
        mock_organizer_cls.return_value = mock_instance
        _, client, _ = _build_app(tmp_path)
        options = {
            "recursive": False,
            "include_hidden": True,
            "skip_existing": False,
            "transfer_mode": "copy",
            "methodology": "para",
            "enable_vision": False,
            "transcribe_audio": True,
            "max_transcribe_seconds": 42.5,
            "whisper_model": "base",
            "parallel_workers": 3,
            "prefetch_depth": 4,
            "text_model": "text-custom",
            "vision_model": "vision-custom",
            "text_provider": "openai",
            "vision_provider": "openai",
        }

        response = client.post(
            "/api/v1/organize/preview",
            json={
                "input_dir": str(tmp_path / "input"),
                "output_dir": str(tmp_path / "output"),
                "options": options,
            },
        )

        assert response.status_code == 200
        assert mock_organizer_cls.call_args.kwargs["organize_options"].to_dict() == options

    def test_canonical_options_reject_conflicting_legacy_alias(self, tmp_path: Path) -> None:
        (tmp_path / "input").mkdir()
        (tmp_path / "output").mkdir()
        _, client, _ = _build_app(tmp_path)

        response = client.post(
            "/api/v1/organize/preview",
            json={
                "input_dir": str(tmp_path / "input"),
                "output_dir": str(tmp_path / "output"),
                "options": {"transfer_mode": "copy"},
                "use_hardlinks": True,
            },
        )

        assert response.status_code == 422
        assert response.json()["error"] == "validation_error"

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

    @patch("file_organizer.api.routers.organize.FileOrganizer")
    def test_preview_includes_executable_plan_when_available(
        self, mock_organizer_cls, tmp_path: Path
    ) -> None:
        plan = _make_plan(tmp_path)
        mock_instance = MagicMock()
        mock_instance.organize.return_value = _make_result(
            total_files=1,
            processed_files=1,
            skipped_files=0,
            organized_structure=plan.organized_structure(),
            plan=plan,
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
        assert body["plan"]["plan_id"] == plan.plan_id
        assert body["plan"]["operations"][0]["destination_path"] == str(
            tmp_path / "output" / "Documents" / "report.txt"
        )


# ---------------------------------------------------------------------------
# execute_organization endpoint
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExecuteOrganization:
    """Tests for POST /api/v1/organize/execute."""

    @patch("file_organizer.api.routers.organize.FileOrganizer")
    def test_execute_sync_success(self, mock_organizer_cls, tmp_path: Path) -> None:
        plan = _make_plan(tmp_path, use_hardlinks=True)
        mock_instance = MagicMock()
        mock_instance.organize.return_value = _make_result(plan=plan)
        mock_instance.execute_plan.return_value = _make_result(plan=plan)
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
        assert resp.status_code == 500
        body = resp.json()
        assert body == {
            "error": "internal_server_error",
            "message": "Unexpected server error.",
        }

    @patch("file_organizer.api.routers.organize.create_job_with_disposition")
    def test_execute_background(self, mock_create_job, tmp_path: Path) -> None:
        (tmp_path / "input").mkdir()
        (tmp_path / "output").mkdir()
        mock_job = MagicMock()
        mock_job.job_id = "test-job-123"
        mock_create_job.return_value = (mock_job, True)
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

    @patch("file_organizer.api.routers.organize._run_organize_job")
    def test_execute_background_idempotency_runs_once(self, mock_run_job, tmp_path: Path) -> None:
        (tmp_path / "input").mkdir()
        (tmp_path / "output").mkdir()
        _, client, _ = _build_app(tmp_path)
        payload = {
            "input_dir": str(tmp_path / "input"),
            "output_dir": str(tmp_path / "output"),
            "run_in_background": True,
            "idempotency_key": "same-request",
        }

        first = client.post("/api/v1/organize/execute", json=payload)
        second = client.post("/api/v1/organize/execute", json=payload)

        assert first.status_code == second.status_code == 200
        assert first.json()["job_id"] == second.json()["job_id"]
        mock_run_job.assert_called_once()

    def test_sync_execute_rejects_idempotency_key(self, tmp_path: Path) -> None:
        (tmp_path / "input").mkdir()
        (tmp_path / "output").mkdir()
        _, client, _ = _build_app(tmp_path)

        response = client.post(
            "/api/v1/organize/execute",
            json={
                "input_dir": str(tmp_path / "input"),
                "output_dir": str(tmp_path / "output"),
                "run_in_background": False,
                "idempotency_key": "sync-request",
            },
        )

        assert response.status_code == 400
        assert response.json()["error"] == "invalid_request"

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
        call = mock_organizer_cls.call_args
        assert call.kwargs["dry_run"] is True
        assert call.kwargs["organize_options"].use_hardlinks is True

    @patch("file_organizer.api.routers.organize.FileOrganizer")
    def test_execute_sync_with_hardlinks_disabled(self, mock_organizer_cls, tmp_path: Path) -> None:
        plan = _make_plan(tmp_path, use_hardlinks=False)
        mock_instance = MagicMock()
        mock_instance.organize.return_value = _make_result(plan=plan)
        mock_instance.execute_plan.return_value = _make_result(plan=plan)
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
        call = mock_organizer_cls.call_args
        assert call.kwargs["dry_run"] is False
        assert call.kwargs["organize_options"].use_hardlinks is False

    @patch("file_organizer.api.routers.organize.FileOrganizer")
    def test_execute_sync_uses_submitted_plan(self, mock_organizer_cls, tmp_path: Path) -> None:
        plan = _make_plan(tmp_path)
        mock_instance = MagicMock()
        mock_instance.execute_plan.return_value = _make_result(
            total_files=1,
            processed_files=1,
            skipped_files=0,
            organized_structure=plan.organized_structure(),
            plan=plan,
        )
        mock_organizer_cls.return_value = mock_instance
        _, client, _ = _build_app(tmp_path)

        resp = client.post(
            "/api/v1/organize/execute",
            json={
                "input_dir": str(tmp_path / "input"),
                "output_dir": str(tmp_path / "output"),
                "run_in_background": False,
                "plan": plan.to_dict(),
            },
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "completed"
        executed_plan = mock_instance.execute_plan.call_args.args[0]
        assert executed_plan.plan_id == plan.plan_id
        mock_instance.organize.assert_not_called()

    @patch("file_organizer.api.routers.organize.FileOrganizer")
    def test_execute_accepts_preview_response_plan(
        self, mock_organizer_cls, tmp_path: Path
    ) -> None:
        plan = _make_plan(tmp_path)
        mock_instance = MagicMock()
        mock_instance.organize.return_value = _make_result(
            total_files=1,
            processed_files=1,
            skipped_files=0,
            organized_structure=plan.organized_structure(),
            plan=plan,
        )
        mock_instance.execute_plan.return_value = _make_result(
            total_files=1,
            processed_files=1,
            skipped_files=0,
            organized_structure=plan.organized_structure(),
            plan=plan,
        )
        mock_organizer_cls.return_value = mock_instance
        _, client, _ = _build_app(tmp_path)

        preview = client.post(
            "/api/v1/organize/preview",
            json={
                "input_dir": str(tmp_path / "input"),
                "output_dir": str(tmp_path / "output"),
            },
        )
        assert preview.status_code == 200

        resp = client.post(
            "/api/v1/organize/execute",
            json={
                "input_dir": str(tmp_path / "input"),
                "output_dir": str(tmp_path / "output"),
                "run_in_background": False,
                "plan": preview.json()["plan"],
            },
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "completed"
        assert body["result"]["organized_structure"] == {"Documents": ["report.txt"]}
        executed_plan = mock_instance.execute_plan.call_args.args[0]
        assert executed_plan.plan_id == plan.plan_id

    @patch("file_organizer.api.routers.organize.FileOrganizer")
    def test_execute_rejects_plan_with_mismatched_roots(
        self, mock_organizer_cls, tmp_path: Path
    ) -> None:
        plan = _make_plan(tmp_path)
        data = plan.to_dict()
        data["input_path"] = str(tmp_path / "other-input")
        _, client, _ = _build_app(tmp_path)

        resp = client.post(
            "/api/v1/organize/execute",
            json={
                "input_dir": str(tmp_path / "input"),
                "output_dir": str(tmp_path / "output"),
                "run_in_background": False,
                "plan": data,
            },
        )

        assert resp.status_code == 409
        body = resp.json()
        assert body["error"] == "plan_mismatch"
        assert "roots do not match" in body["message"]
        mock_organizer_cls.assert_not_called()


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
        mock_job.error_code = None
        mock_job.error_retryable = False
        mock_job.error_details = None
        mock_job.revision = 1
        mock_job.scheduled_for = None
        mock_job.progress.total = 5
        mock_job.progress.completed = 5
        mock_job.progress.failed = 0
        mock_job.progress.skipped = 0
        mock_job.progress.percent = 100.0
        mock_job.transaction_id = "txn-1"
        mock_job.recovery_action = "none"
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
        mock_job.error_code = None
        mock_job.error_retryable = False
        mock_job.error_details = None
        mock_job.revision = 1
        mock_job.scheduled_for = None
        mock_job.progress.total = 5
        mock_job.progress.completed = 2
        mock_job.progress.failed = 0
        mock_job.progress.skipped = 0
        mock_job.progress.percent = 40.0
        mock_job.transaction_id = None
        mock_job.recovery_action = "none"
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
        mock_job.error_code.value = "execution_failed"
        mock_job.error_retryable = True
        mock_job.error_details = {"phase": "execution"}
        mock_job.revision = 2
        mock_job.scheduled_for = None
        mock_job.progress.total = 1
        mock_job.progress.completed = 0
        mock_job.progress.failed = 1
        mock_job.progress.skipped = 0
        mock_job.progress.percent = 100.0
        mock_job.transaction_id = None
        mock_job.recovery_action = "retry"
        mock_get_job.return_value = mock_job
        _, client, _ = _build_app(tmp_path)

        resp = client.get("/api/v1/organize/status/job-3")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "failed"
        assert body["error"] == "Something went wrong"


@pytest.mark.unit
class TestJobLifecycleEndpoints:
    """Tests for job history, cancellation, and rollback endpoints."""

    def test_job_history_lists_organization_jobs(self, tmp_path: Path) -> None:
        from file_organizer.api.jobs import create_job

        job = create_job("organize")
        _, client, _ = _build_app(tmp_path)

        response = client.get("/api/v1/organize/jobs?limit=10")

        assert response.status_code == 200
        assert job.job_id in {row["job_id"] for row in response.json()}

    def test_cancel_job_uses_revision_guard(self, tmp_path: Path) -> None:
        from file_organizer.api.jobs import create_job

        job = create_job("organize")
        _, client, _ = _build_app(tmp_path)

        response = client.post(
            f"/api/v1/organize/jobs/{job.job_id}/cancel",
            json={"expected_revision": job.revision},
        )

        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"
        assert response.json()["revision"] == job.revision + 1

    def test_cancel_job_rejects_stale_revision(self, tmp_path: Path) -> None:
        from file_organizer.api.jobs import create_job

        job = create_job("organize")
        _, client, _ = _build_app(tmp_path)

        response = client.post(
            f"/api/v1/organize/jobs/{job.job_id}/cancel",
            json={"expected_revision": job.revision + 1},
        )

        assert response.status_code == 409
        assert response.json()["error"] == "stale_job_revision"

    def test_cancel_job_returns_404_when_job_disappears_during_update(self, tmp_path: Path) -> None:
        with (
            patch.object(organize_router_module, "get_job", return_value=MagicMock()),
            patch.object(organize_router_module, "update_job", return_value=None),
        ):
            _, client, _ = _build_app(tmp_path)

            response = client.post(
                "/api/v1/organize/jobs/disappeared/cancel",
                json={"expected_revision": None},
            )

        assert response.status_code == 404
        assert response.json() == {"error": "not_found", "message": "Job not found"}

    def test_rollback_job_returns_404_when_job_disappears_before_rollback(
        self, tmp_path: Path
    ) -> None:
        job = MagicMock(transaction_id="txn-123")
        with (
            patch.object(organize_router_module, "get_job", return_value=job),
            patch.object(organize_router_module, "update_job", return_value=None),
            patch("file_organizer.undo.undo_manager.UndoManager") as undo_manager,
        ):
            _, client, _ = _build_app(tmp_path)

            response = client.post(
                "/api/v1/organize/jobs/disappeared/rollback",
                json={"expected_revision": None},
            )

        assert response.status_code == 404
        assert response.json() == {"error": "not_found", "message": "Job not found"}
        undo_manager.assert_not_called()

    def test_rollback_job_returns_404_when_job_disappears_after_rollback(
        self, tmp_path: Path
    ) -> None:
        job = MagicMock(transaction_id="txn-123")
        with (
            patch.object(organize_router_module, "get_job", return_value=job),
            patch.object(
                organize_router_module,
                "update_job",
                side_effect=[MagicMock(), None],
            ),
            patch("file_organizer.undo.undo_manager.UndoManager") as undo_manager,
        ):
            undo_manager.return_value.undo_transaction.return_value = True
            _, client, _ = _build_app(tmp_path)

            response = client.post(
                "/api/v1/organize/jobs/disappeared/rollback",
                json={"expected_revision": None},
            )

        assert response.status_code == 404
        assert response.json() == {"error": "not_found", "message": "Job not found"}

    @patch("file_organizer.undo.undo_manager.UndoManager")
    def test_rollback_job_transitions_to_rolled_back(
        self, mock_undo_manager, tmp_path: Path
    ) -> None:
        from file_organizer.api.jobs import create_job, update_job

        job = create_job("organize")
        completed = update_job(
            job.job_id,
            status="completed",
            transaction_id="txn-123",
        )
        assert completed is not None
        mock_undo_manager.return_value.undo_transaction.return_value = True
        _, client, _ = _build_app(tmp_path)

        response = client.post(
            f"/api/v1/organize/jobs/{job.job_id}/rollback",
            json={"expected_revision": completed.revision},
        )

        assert response.status_code == 200
        assert response.json()["status"] == "rolled_back"
        mock_undo_manager.return_value.undo_transaction.assert_called_once_with("txn-123")


# ---------------------------------------------------------------------------
# simple organize endpoint (POST /api/v1/organize)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSimpleOrganize:
    """Tests for POST /api/v1/organize."""

    def test_organize_with_json_request(self, tmp_path: Path) -> None:
        _, client, _ = _build_app(tmp_path)

        response = client.post(
            "/api/v1/organize",
            json={"filename": "notes.txt", "folder_suggestion": "Writing"},
        )

        assert response.status_code == 200
        assert response.json()["folder_name"] == "Writing"

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
            dry_run=True,
        )
        _run_organize_job(
            "job-abc",
            request,
            Path("fake") / "input",
            Path("fake") / "output",
        )

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
        _run_organize_job(
            "job-xyz",
            request,
            Path("fake") / "input",
            Path("fake") / "output",
        )

        mock_update_job.assert_any_call("job-xyz", status="running")
        last_call = mock_update_job.call_args_list[-1]
        assert last_call[1]["status"] == "failed"
        assert "boom" in last_call[1]["error"]


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
