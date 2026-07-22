"""Organization endpoints."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Query, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_current_active_user, get_settings
from file_organizer.api.exceptions import ApiError
from file_organizer.api.jobs import (
    JobState,
    create_job_with_disposition,
    get_job,
    list_jobs,
    update_job,
)
from file_organizer.api.models import (
    JobStatusResponse,
    OrganizationError,
    OrganizationPlanPayload,
    OrganizationResultResponse,
    OrganizeExecuteResponse,
    OrganizeRequest,
    ScanRequest,
    ScanResponse,
)
from file_organizer.api.openapi_responses import (
    AUTH_401_RESPONSE,
    INTERNAL_500_RESPONSE,
    api_error_response,
    detail_error_response,
    merge_responses,
    success_response,
    validation_error_response,
)
from file_organizer.api.utils import resolve_path
from file_organizer.core.errors import DomainError, DomainErrorCode
from file_organizer.core.lifecycle import JobProgress, JobStatus, RecoveryAction
from file_organizer.core.organization_service import OrganizationService
from file_organizer.core.organize_options import OrganizeOptions
from file_organizer.core.organize_options import OrganizeRequest as CoreRequest
from file_organizer.core.organizer import FileOrganizer
from file_organizer.core.plan import OrganizationPlan
from file_organizer.core.types import OrganizationResult

router = APIRouter(
    tags=["organize"],
    dependencies=[Depends(get_current_active_user)],
    responses=merge_responses(AUTH_401_RESPONSE, INTERNAL_500_RESPONSE),
)


def get_organization_service() -> OrganizationService:
    """Provide the canonical application service for HTTP adapter calls."""
    return OrganizationService(organizer_factory=FileOrganizer)


def _result_to_response(result: OrganizationResult) -> OrganizationResultResponse:
    """Map an OrganizationResult dataclass to the HTTP response model."""
    plan = (
        OrganizationPlanPayload(**result.plan.to_dict())
        if isinstance(result.plan, OrganizationPlan)
        else None
    )
    return OrganizationResultResponse(
        total_files=result.total_files,
        processed_files=result.processed_files,
        skipped_files=result.skipped_files,
        failed_files=result.failed_files,
        deduplicated_files=result.deduplicated_files,
        processing_time=result.processing_time,
        organized_structure=result.organized_structure,
        errors=[OrganizationError(file=err[0], error=err[1]) for err in result.errors],
        plan=plan,
        transaction_id=result.transaction_id,
    )


def _job_to_response(job: JobState) -> JobStatusResponse:
    """Map canonical job state to its stable HTTP representation."""
    result = OrganizationResultResponse(**job.result) if job.result is not None else None
    return JobStatusResponse(
        job_id=job.job_id,
        status=job.status,
        created_at=job.created_at,
        updated_at=job.updated_at,
        result=result,
        error=job.error,
        error_code=job.error_code.value if job.error_code is not None else None,
        error_retryable=job.error_retryable,
        error_details=job.error_details,
        revision=job.revision,
        scheduled_for=job.scheduled_for,
        progress={
            "total": job.progress.total,
            "completed": job.progress.completed,
            "failed": job.progress.failed,
            "skipped": job.progress.skipped,
            "percent": job.progress.percent,
        },
        transaction_id=job.transaction_id,
        recovery_action=job.recovery_action,
    )


def _load_request_plan(request: OrganizeRequest) -> OrganizationPlan | None:
    """Deserialize an optional executable plan from the request."""
    if request.plan is None:
        return None
    try:
        return OrganizationPlan.from_dict(request.plan.model_dump())
    except (KeyError, TypeError, ValueError) as exc:
        raise DomainError(
            DomainErrorCode.INVALID_REQUEST,
            f"Invalid organization plan: {exc}",
        ) from exc


def _core_request(
    request: OrganizeRequest,
    input_path: Path,
    output_path: Path,
    plan: OrganizationPlan | None = None,
) -> CoreRequest:
    """Map a validated HTTP payload into the transport-neutral request."""
    return CoreRequest(input_path, output_path, request.to_domain_options(plan))


def _execute_request(
    service: OrganizationService,
    request: OrganizeRequest,
    input_path: Path,
    output_path: Path,
) -> OrganizationResult:
    """Execute or preview one HTTP request through canonical service methods."""
    plan = _load_request_plan(request)
    core_request = _core_request(request, input_path, output_path, plan)
    if request.dry_run:
        if plan is not None:
            raise DomainError(
                DomainErrorCode.INVALID_REQUEST,
                "A reviewed plan cannot be combined with dry_run; submit it for execution.",
            )
        return service.preview(core_request)
    return service.execute(core_request, plan)


def _run_organize_job(
    job_id: str,
    request: OrganizeRequest,
    input_path: Path,
    output_path: Path,
    service: OrganizationService | None = None,
) -> None:
    """Run a background organization job with validated paths."""
    service = service or get_organization_service()
    update_job(job_id, status="running")
    try:
        result = _execute_request(service, request, input_path, output_path)
        response = _result_to_response(result).model_dump()
        progress = JobProgress(
            total=result.total_files,
            completed=result.processed_files,
            failed=result.failed_files,
            skipped=result.skipped_files + result.deduplicated_files,
        )
        status = JobStatus.PARTIAL if result.failed_files else JobStatus.COMPLETED
        update_job(
            job_id,
            status=status,
            result=response,
            progress=progress,
            transaction_id=result.transaction_id,
            recovery_action=(RecoveryAction.ROLLBACK if result.transaction_id else None),
        )
    except DomainError as exc:
        update_job(
            job_id,
            status=JobStatus.FAILED,
            error=exc.message,
            error_code=exc.code,
            error_retryable=exc.retryable,
            error_details=exc.details,
        )
    except Exception as exc:
        update_job(job_id, status="failed", error=str(exc))


@router.post(
    "/organize/scan",
    response_model=ScanResponse,
    responses=merge_responses(
        success_response(
            "Scanned the input directory.",
            {
                "input_dir": "/Users/demo/Downloads",
                "total_files": 3,
                "counts": {"text": 1, "image": 1, "video": 0, "audio": 0, "cad": 0, "other": 1},
            },
        ),
        api_error_response(404, error="not_found", message="Input path not found"),
        validation_error_response(),
    ),
)
def scan_directory(
    request: ScanRequest,
    settings: ApiSettings = Depends(get_settings),
    service: OrganizationService = Depends(get_organization_service),
) -> ScanResponse:
    """Scan a directory and return file counts by type."""
    path = resolve_path(request.input_dir, settings.allowed_paths)
    if not path.exists():
        raise ApiError(status_code=404, error="not_found", message="Input path not found")

    scan = service.scan(
        CoreRequest(
            path,
            path,
            OrganizeOptions(
                recursive=request.recursive,
                include_hidden=request.include_hidden,
            ),
        )
    )
    return ScanResponse(
        input_dir=str(scan.input_path),
        total_files=scan.total_files,
        counts=scan.counts,
    )


@router.post(
    "/organize/preview",
    response_model=OrganizationResultResponse,
    responses=merge_responses(
        success_response(
            "Generated an organization preview.",
            {
                "total_files": 3,
                "processed_files": 3,
                "skipped_files": 0,
                "failed_files": 0,
                "deduplicated_files": 0,
                "processing_time": 1.24,
                "organized_structure": {"Documents": ["report.pdf"], "Images": ["photo.jpg"]},
                "errors": [],
            },
        ),
        api_error_response(404, error="not_found", message="Input path not found"),
        validation_error_response(),
    ),
)
def preview_organization(
    request: OrganizeRequest,
    settings: ApiSettings = Depends(get_settings),
    service: OrganizationService = Depends(get_organization_service),
) -> OrganizationResultResponse:
    """Preview organization results without moving files."""
    path = resolve_path(request.input_dir, settings.allowed_paths)
    output = resolve_path(request.output_dir, settings.allowed_paths)
    if not path.exists():
        raise ApiError(status_code=404, error="not_found", message="Input path not found")

    safe_request = request.model_copy(
        update={"input_dir": str(path), "output_dir": str(output), "dry_run": True}
    )
    return _result_to_response(_execute_request(service, safe_request, path, output))


@router.post(
    "/organize/execute",
    response_model=OrganizeExecuteResponse,
    responses=merge_responses(
        success_response(
            "Queued or completed an organization run.",
            {"status": "queued", "job_id": "job_123", "result": None, "error": None},
        ),
        api_error_response(404, error="not_found", message="Input path not found"),
        validation_error_response(),
    ),
)
def execute_organization(
    request: OrganizeRequest,
    background_tasks: BackgroundTasks,
    settings: ApiSettings = Depends(get_settings),
    service: OrganizationService = Depends(get_organization_service),
) -> OrganizeExecuteResponse:
    """Execute file organization, optionally in the background."""
    path = resolve_path(request.input_dir, settings.allowed_paths)
    output = resolve_path(request.output_dir, settings.allowed_paths)
    if not path.exists():
        raise ApiError(status_code=404, error="not_found", message="Input path not found")

    safe_request = request.model_copy(
        update={"input_dir": str(path), "output_dir": str(output)},
    )
    if request.run_in_background:
        job, created = create_job_with_disposition(
            "organize",
            idempotency_key=request.idempotency_key,
        )
        if created:
            background_tasks.add_task(
                _run_organize_job,
                job.job_id,
                safe_request,
                path,
                output,
                service,
            )
        return OrganizeExecuteResponse(status="queued", job_id=job.job_id)

    if request.idempotency_key is not None:
        raise DomainError(
            DomainErrorCode.INVALID_REQUEST,
            "idempotency_key requires run_in_background=true.",
        )

    result = _execute_request(service, safe_request, path, output)
    return OrganizeExecuteResponse(
        status="completed",
        result=_result_to_response(result),
    )


@router.get(
    "/organize/status/{job_id}",
    response_model=JobStatusResponse,
    responses=merge_responses(
        success_response(
            "Returned background job status.",
            {
                "job_id": "job_123",
                "status": "completed",
                "created_at": "2026-04-05T14:10:00Z",
                "updated_at": "2026-04-05T14:11:00Z",
                "result": None,
                "error": None,
            },
        ),
        api_error_response(404, error="not_found", message="Job not found"),
    ),
)
def get_job_status(job_id: str) -> JobStatusResponse:
    """Retrieve the status of an organization job."""
    job = get_job(job_id)
    if not job:
        raise ApiError(status_code=404, error="not_found", message="Job not found")
    return _job_to_response(job)


class JobMutationRequest(BaseModel):
    """Compare-and-swap guard for job lifecycle mutations."""

    expected_revision: int | None = None


@router.get(
    "/organize/jobs",
    response_model=list[JobStatusResponse],
    responses=validation_error_response(),
)
def get_job_history(
    status: JobStatus | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
) -> list[JobStatusResponse]:
    """List recent organization jobs, newest first."""
    statuses = {status} if status is not None else None
    return [
        _job_to_response(job)
        for job in list_jobs(job_type="organize", statuses=statuses, limit=limit)
    ]


@router.post(
    "/organize/jobs/{job_id}/cancel",
    response_model=JobStatusResponse,
    responses=merge_responses(
        api_error_response(404, error="not_found", message="Job not found"),
        api_error_response(409, error="invalid_job_transition", message="Job cannot be cancelled"),
        validation_error_response(),
    ),
)
def cancel_organization_job(
    job_id: str,
    request: JobMutationRequest,
) -> JobStatusResponse:
    """Cancel a queued or scheduled organization job."""
    job = get_job(job_id)
    if job is None:
        raise ApiError(status_code=404, error="not_found", message="Job not found")
    updated = update_job(
        job_id,
        status=JobStatus.CANCELLED,
        expected_revision=request.expected_revision,
    )
    assert updated is not None
    return _job_to_response(updated)


@router.post(
    "/organize/jobs/{job_id}/rollback",
    response_model=JobStatusResponse,
    responses=merge_responses(
        api_error_response(400, error="invalid_request", message="Job has no transaction"),
        api_error_response(404, error="not_found", message="Job not found"),
        api_error_response(
            409, error="invalid_job_transition", message="Job cannot be rolled back"
        ),
        validation_error_response(),
    ),
)
def rollback_organization_job(
    job_id: str,
    request: JobMutationRequest,
) -> JobStatusResponse:
    """Rollback a completed organization job's transaction."""
    job = get_job(job_id)
    if job is None:
        raise ApiError(status_code=404, error="not_found", message="Job not found")
    if not job.transaction_id:
        raise DomainError(
            DomainErrorCode.INVALID_REQUEST,
            "Job does not have a transaction that can be rolled back.",
            details={"job_id": job_id},
        )

    rolling_back = update_job(
        job_id,
        status=JobStatus.ROLLING_BACK,
        expected_revision=request.expected_revision,
    )
    assert rolling_back is not None

    from file_organizer.undo.undo_manager import UndoManager

    try:
        success = UndoManager().undo_transaction(job.transaction_id)
    except Exception as exc:
        update_job(
            job_id,
            status=JobStatus.RECOVERY_REQUIRED,
            error="Rollback failed.",
            error_code=DomainErrorCode.RECOVERY_REQUIRED,
            recovery_action=RecoveryAction.MANUAL,
        )
        raise DomainError(
            DomainErrorCode.RECOVERY_REQUIRED,
            "Rollback failed and requires manual recovery.",
            details={"job_id": job_id, "transaction_id": job.transaction_id},
        ) from exc
    updated = update_job(
        job_id,
        status=(JobStatus.ROLLED_BACK if success else JobStatus.RECOVERY_REQUIRED),
        error=(None if success else "Rollback did not complete."),
        error_code=(None if success else DomainErrorCode.RECOVERY_REQUIRED),
        recovery_action=(RecoveryAction.NONE if success else RecoveryAction.MANUAL),
    )
    assert updated is not None
    return _job_to_response(updated)


class SimpleOrganizeRequest(BaseModel):
    """Simple single-file organization request."""

    filename: str
    folder_suggestion: str | None = None


class SimpleOrganizeResponse(BaseModel):
    """Response from simple organize endpoint."""

    filename: str
    folder_name: str
    confidence: float


@router.post(
    "/organize",
    response_model=None,
    responses=merge_responses(
        success_response(
            "Generated a simple organization suggestion.",
            {"filename": "report_organized.pdf", "folder_name": "Documents", "confidence": 0.85},
        ),
        detail_error_response(400, detail="Either file upload or request body must be provided"),
    ),
)
async def organize_file(
    http_request: Request,
    file: UploadFile | None = File(None),
    settings: ApiSettings = Depends(get_settings),
) -> SimpleOrganizeResponse | JSONResponse:
    """Organize a single file with naming and folder suggestions.

    Accepts either file upload (multipart/form-data) or JSON request body.
    """
    import os

    # Get filename from file upload or request body
    organize_request: SimpleOrganizeRequest | None = None
    if file:
        filename = file.filename or "unknown"
    else:
        try:
            organize_request = SimpleOrganizeRequest.model_validate(await http_request.json())
        except (ValueError, TypeError):
            return JSONResponse(
                status_code=400,
                content={
                    "error": "invalid_request",
                    "message": "Either file upload or request body must be provided",
                },
            )
        filename = organize_request.filename

    # Simple logic: extract base name and suggest folder
    base_name = os.path.basename(filename)
    name_parts = os.path.splitext(base_name)

    # Simple category detection
    ext = name_parts[1].lower()
    if organize_request is not None and organize_request.folder_suggestion:
        folder = organize_request.folder_suggestion
    elif ext in [".txt", ".md", ".pdf", ".doc", ".docx"]:
        folder = "Documents"
    elif ext in [".jpg", ".png", ".gif", ".bmp"]:
        folder = "Images"
    elif ext in [".mp4", ".avi", ".mkv"]:
        folder = "Videos"
    elif ext in [".mp3", ".wav", ".flac"]:
        folder = "Audio"
    else:
        folder = "Other"

    organized_name = f"{name_parts[0]}_organized{name_parts[1]}"

    return SimpleOrganizeResponse(
        filename=organized_name,
        folder_name=folder,
        confidence=0.85,
    )
