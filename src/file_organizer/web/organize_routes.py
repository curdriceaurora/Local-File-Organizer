"""Web UI routes for the organization dashboard, jobs, and reports."""

from __future__ import annotations

import asyncio
import csv
import io
import json
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock, Timer
from time import monotonic
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from loguru import logger

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_settings
from file_organizer.api.exceptions import ApiError
from file_organizer.api.jobs import create_job, get_job, list_jobs, update_job
from file_organizer.api.models import OrganizeRequest
from file_organizer.api.utils import resolve_path
from file_organizer.config.methodology import DEFAULT as _DEFAULT_METHODOLOGY
from file_organizer.config.methodology import LABELS as ORGANIZE_METHODOLOGIES
from file_organizer.config.methodology import normalize as _normalize_methodology
from file_organizer.core.organizer import FileOrganizer
from file_organizer.core.plan import OrganizationPlan
from file_organizer.core.types import OrganizationResult
from file_organizer.web._forms import form_bool
from file_organizer.web._helpers import (
    allowed_roots,
    build_content_disposition,
    format_timestamp,
    templates,
)
from file_organizer.web.organize_services import (
    _ORGANIZE_PLAN_STORE,
    ORGANIZE_DEFAULT_DELAY_MIN,
    ORGANIZE_MAX_DELAY_MIN,
    ORGANIZE_PLAN_LIMIT,
    _build_plan_movements,
    _counts_by_type,
    _delete_organize_plan,
    _get_organize_plan,
    _job_report_payload,
    _parse_delay_minutes,
    _result_to_response,
    _scan_directory,
    _store_organize_plan,
    build_organize_plan,
)

organize_router = APIRouter(tags=["web"])

__all__ = [
    "ORGANIZE_DEFAULT_DELAY_MIN",
    "ORGANIZE_EVENT_POLL_SECONDS",
    "ORGANIZE_HISTORY_LIMIT",
    "ORGANIZE_JOB_TYPE",
    "ORGANIZE_MAX_DELAY_MIN",
    "ORGANIZE_METHODOLOGIES",
    "ORGANIZE_PLAN_LIMIT",
    "_ORGANIZE_PLAN_STORE",
    "_build_job_view",
    "_build_organize_stats",
    "_build_plan_movements",
    "_cancel_scheduled_job",
    "_counts_by_type",
    "_delete_organize_plan",
    "_get_job_metadata",
    "_get_organize_plan",
    "_job_report_payload",
    "_list_organize_jobs",
    "_normalize_methodology",
    "_parse_delay_minutes",
    "_prune_job_metadata",
    "_result_to_response",
    "_run_organize_job",
    "_scan_directory",
    "_schedule_job",
    "_set_job_metadata",
    "_status_progress",
    "_store_organize_plan",
    "organize_router",
]

ORGANIZE_EVENT_POLL_SECONDS = 1
ORGANIZE_HISTORY_LIMIT = 50
ORGANIZE_JOB_TYPE = "organize_web"
JOB_METADATA_PRUNE_THRESHOLD = 256
JOB_METADATA_PRUNE_INTERVAL_SECONDS = 60.0

_SCHEDULED_TIMERS: dict[str, Timer] = {}
_SCHEDULED_TIMERS_LOCK = Lock()
_JOB_METADATA: dict[str, dict[str, Any]] = {}
_JOB_METADATA_LOCK = Lock()
_LAST_JOB_METADATA_PRUNE_MONOTONIC = 0.0


def _prune_job_metadata(*, force: bool = False) -> None:
    """Remove metadata for jobs that no longer exist in the job store."""
    global _LAST_JOB_METADATA_PRUNE_MONOTONIC
    now = monotonic()
    with _JOB_METADATA_LOCK:
        current_size = len(_JOB_METADATA)
        last_prune = _LAST_JOB_METADATA_PRUNE_MONOTONIC
        should_prune = force or current_size >= JOB_METADATA_PRUNE_THRESHOLD
        if not should_prune and (now - last_prune) < JOB_METADATA_PRUNE_INTERVAL_SECONDS:
            return
        tracked_ids = list(_JOB_METADATA.keys())
        _LAST_JOB_METADATA_PRUNE_MONOTONIC = now
    stale_ids = [job_id for job_id in tracked_ids if get_job(job_id) is None]
    if not stale_ids:
        return
    with _JOB_METADATA_LOCK:
        for job_id in stale_ids:
            _JOB_METADATA.pop(job_id, None)


def _set_job_metadata(job_id: str, data: dict[str, Any]) -> None:
    """Store supplementary metadata for *job_id*."""
    with _JOB_METADATA_LOCK:
        _JOB_METADATA[job_id] = data
    _prune_job_metadata()


def _get_job_metadata(job_id: str) -> dict[str, Any]:
    """Return a copy of the stored metadata for *job_id* (empty dict if absent)."""
    with _JOB_METADATA_LOCK:
        return dict(_JOB_METADATA.get(job_id, {}))


def _status_progress(status: str) -> int:
    """Map a job status string to an approximate progress percentage."""
    if status == "queued":
        return 5
    if status == "running":
        return 65
    if status in {"completed", "failed"}:
        return 100
    return 0


def _build_job_view(job_id: str) -> dict[str, Any] | None:
    """Build a rich view dict for a job, merging job state with metadata.

    Returns:
        Job view dict suitable for templates, or ``None`` if the job is missing.
    """
    job = get_job(job_id)
    if job is None:
        return None

    metadata = _get_job_metadata(job_id)
    result = job.result or {}
    schedule_delay_minutes = int(metadata.get("schedule_delay_minutes", 0) or 0)
    scheduled_for = str(metadata.get("scheduled_for", ""))
    is_scheduled = job.status == "queued" and bool(scheduled_for) and schedule_delay_minutes > 0
    processed_files = int(result.get("processed_files", 0) or 0)
    total_files = int(result.get("total_files", 0) or 0)
    failed_files = int(result.get("failed_files", 0) or 0)
    skipped_files = int(result.get("skipped_files", 0) or 0)
    progress = _status_progress(job.status)

    if total_files > 0 and job.status == "completed":
        progress = 100
    elif total_files > 0 and job.status == "running":
        progress = max(progress, int((processed_files / max(total_files, 1)) * 100))

    methodology = _normalize_methodology(metadata.get("methodology"))

    return {
        "job_id": job.job_id,
        "status": job.status,
        "progress_percent": max(0, min(progress, 100)),
        "created_at": format_timestamp(job.created_at),
        "updated_at": format_timestamp(job.updated_at),
        "error": job.error,
        "processed_files": processed_files,
        "total_files": total_files,
        "failed_files": failed_files,
        "skipped_files": skipped_files,
        "result": result,
        "methodology": methodology,
        "methodology_label": ORGANIZE_METHODOLOGIES[methodology],
        "input_dir": metadata.get("input_dir", ""),
        "output_dir": metadata.get("output_dir", ""),
        "dry_run": bool(metadata.get("dry_run", False)),
        "schedule_delay_minutes": schedule_delay_minutes,
        "scheduled_for": scheduled_for,
        "can_cancel": is_scheduled,
        "can_rollback": job.status == "completed" and not bool(metadata.get("dry_run", False)),
        "is_terminal": job.status in {"completed", "failed"},
    }


def _list_organize_jobs(
    *,
    status_filter: str | None = None,
    limit: int = ORGANIZE_HISTORY_LIMIT,
) -> list[dict[str, Any]]:
    """List recent organize jobs, optionally filtered by status.

    Returns:
        List of job view dicts.
    """
    jobs = list_jobs(job_type=ORGANIZE_JOB_TYPE, limit=limit)
    rows: list[dict[str, Any]] = []
    for job in jobs:
        if status_filter and status_filter != "all" and job.status != status_filter:
            continue
        view = _build_job_view(job.job_id)
        if view is not None:
            rows.append(view)
    return rows


def _build_organize_stats() -> dict[str, Any]:
    """Compute aggregate statistics across all organize jobs.

    Returns:
        Dict with totals, success rate, and methodology breakdowns.
    """
    jobs = _list_organize_jobs(limit=500)
    total_jobs = len(jobs)
    completed_jobs = sum(1 for job in jobs if job["status"] == "completed")
    failed_jobs = sum(1 for job in jobs if job["status"] == "failed")
    active_jobs = sum(1 for job in jobs if job["status"] in {"queued", "running"})
    total_files = sum(int(job["processed_files"]) for job in jobs if job["status"] == "completed")
    success_rate = 0.0
    if total_jobs:
        success_rate = (completed_jobs / total_jobs) * 100.0

    methodology_counts: dict[str, int] = {}
    for job in jobs:
        label = job.get("methodology_label", ORGANIZE_METHODOLOGIES[_DEFAULT_METHODOLOGY])
        methodology_counts[label] = methodology_counts.get(label, 0) + 1

    return {
        "total_jobs": total_jobs,
        "completed_jobs": completed_jobs,
        "failed_jobs": failed_jobs,
        "active_jobs": active_jobs,
        "total_files": total_files,
        "success_rate": success_rate,
        "methodology_counts": methodology_counts,
    }


def _run_organize_job(job_id: str, organize_request: OrganizeRequest) -> None:
    """Execute an organization job synchronously, updating job state on completion."""
    update_job(job_id, status="running", error=None)
    try:
        organizer = FileOrganizer(
            dry_run=organize_request.dry_run,
            use_hardlinks=organize_request.use_hardlinks,
        )
        result = organizer.organize(
            input_path=organize_request.input_dir,
            output_path=organize_request.output_dir,
            skip_existing=organize_request.skip_existing,
        )
        response = _result_to_response(result).model_dump()
        update_job(job_id, status="completed", result=response, error=None)
    except Exception as exc:
        update_job(job_id, status="failed", error=str(exc))


def _result_from_plan_preview(plan: OrganizationPlan) -> OrganizationResult:
    """Build an OrganizationResult for a dry-run execution of a stored plan."""
    return OrganizationResult(
        total_files=plan.total_files,
        processed_files=plan.processed_files,
        skipped_files=plan.skipped_files,
        failed_files=plan.failed_files,
        deduplicated_files=plan.deduplicated_files,
        organized_structure=plan.organized_structure(),
        errors=plan.errors,
        plan=plan,
    )


def _run_organize_plan_job(job_id: str, plan_data: dict[str, Any], *, dry_run: bool) -> None:
    """Execute a stored executable organization plan."""
    update_job(job_id, status="running", error=None)
    try:
        plan = OrganizationPlan.from_dict(plan_data)
        if dry_run:
            result = _result_from_plan_preview(plan)
        else:
            organizer = FileOrganizer(dry_run=False, use_hardlinks=plan.use_hardlinks)
            result = organizer.execute_plan(plan)
        response = _result_to_response(result).model_dump()
        update_job(job_id, status="completed", result=response, error=None)
    except Exception as exc:
        update_job(job_id, status="failed", error=str(exc))


def _schedule_job(job_id: str, organize_request: OrganizeRequest, delay_minutes: int) -> None:
    """Schedule an organization job to run after *delay_minutes*.

    If *delay_minutes* is zero or negative the job runs immediately.
    """
    delay_seconds = delay_minutes * 60

    def _runner() -> None:
        """Execute the scheduled organization job."""
        with _SCHEDULED_TIMERS_LOCK:
            _SCHEDULED_TIMERS.pop(job_id, None)
        _run_organize_job(job_id, organize_request)

    if delay_seconds <= 0:
        _runner()
        return

    timer = Timer(delay_seconds, _runner)
    timer.daemon = True
    with _SCHEDULED_TIMERS_LOCK:
        _SCHEDULED_TIMERS[job_id] = timer
    timer.start()


def _schedule_plan_job(
    job_id: str,
    plan_data: dict[str, Any],
    delay_minutes: int,
    *,
    dry_run: bool,
) -> None:
    """Schedule execution of a stored organization plan."""
    delay_seconds = delay_minutes * 60

    def _runner() -> None:
        """Execute the scheduled plan job."""
        with _SCHEDULED_TIMERS_LOCK:
            _SCHEDULED_TIMERS.pop(job_id, None)
        _run_organize_plan_job(job_id, plan_data, dry_run=dry_run)

    if delay_seconds <= 0:
        _runner()
        return

    timer = Timer(delay_seconds, _runner)
    timer.daemon = True
    with _SCHEDULED_TIMERS_LOCK:
        _SCHEDULED_TIMERS[job_id] = timer
    timer.start()


def _cancel_scheduled_job(job_id: str) -> bool:
    """Cancel a scheduled job timer if it exists.

    Returns:
        ``True`` if the job was successfully cancelled, ``False`` otherwise.
    """
    with _SCHEDULED_TIMERS_LOCK:
        timer = _SCHEDULED_TIMERS.pop(job_id, None)
    if timer is None:
        return False
    timer.cancel()
    update_job(job_id, status="failed", error="Cancelled before execution.")
    return True


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------


@organize_router.get("/organize", response_class=HTMLResponse)
def organize_dashboard(
    request: Request, settings: ApiSettings = Depends(get_settings)
) -> HTMLResponse:
    """Render the organization dashboard with defaults and aggregate stats.

    Returns:
        Full HTML page for the organize dashboard.
    """
    from file_organizer.web._helpers import base_context

    roots = allowed_roots(settings)
    default_input = str(roots[0]) if roots else ""
    default_output = str(roots[0] / "organized") if roots else ""
    stats = _build_organize_stats()
    context = base_context(
        request,
        settings,
        active="organize",
        title="Organize",
        extras={
            "allowed_roots": [str(root) for root in roots],
            "default_input_dir": default_input,
            "default_output_dir": default_output,
            "methodology_options": ORGANIZE_METHODOLOGIES,
            "stats": stats,
        },
    )
    return templates.TemplateResponse(request, "organize/dashboard.html", context)


@organize_router.post("/organize/scan", response_class=HTMLResponse)
def organize_scan(
    request: Request,
    settings: ApiSettings = Depends(get_settings),
    input_dir: str = Form(""),
    output_dir: str = Form(""),
    methodology: str = Form(_DEFAULT_METHODOLOGY),
    recursive: str = Form("1"),
    include_hidden: str = Form("0"),
    skip_existing: str = Form("1"),
    use_hardlinks: str = Form("1"),
) -> HTMLResponse:
    """Scan the input directory and generate a dry-run organization plan.

    Returns:
        HTMX partial showing the generated plan or an error message.
    """
    error_message: str | None = None
    info_message: str | None = None
    plan: dict[str, Any] | None = None

    try:
        plan = build_organize_plan(
            input_dir=input_dir,
            output_dir=output_dir,
            methodology=methodology,
            recursive=recursive,
            include_hidden=include_hidden,
            skip_existing=skip_existing,
            use_hardlinks=use_hardlinks,
            allowed_paths=settings.allowed_paths,
            organizer_factory=FileOrganizer,
        )
        info_message = "Plan generated. Review movements and execute when ready."
    except ApiError as exc:
        error_message = exc.message
    except Exception:
        logger.exception("Failed to generate organize plan")
        error_message = "Failed to generate plan."

    return templates.TemplateResponse(
        request,
        "organize/_plan.html",
        {
            "plan": plan,
            "error_message": error_message,
            "info_message": info_message,
            "methodology_options": ORGANIZE_METHODOLOGIES,
        },
    )


@organize_router.post("/organize/plan/clear", response_class=HTMLResponse)
def organize_clear_plan(
    request: Request,
    plan_id: str = Form(""),
) -> HTMLResponse:
    """Dismiss a previously generated organization plan.

    Returns:
        Empty plan partial with a dismissal confirmation.
    """
    if plan_id:
        _delete_organize_plan(plan_id)
    return templates.TemplateResponse(
        request,
        "organize/_plan.html",
        {
            "plan": None,
            "info_message": "Plan dismissed.",
            "error_message": None,
            "methodology_options": ORGANIZE_METHODOLOGIES,
        },
    )


@organize_router.post("/organize/execute", response_class=HTMLResponse)
def organize_execute(
    request: Request,
    background_tasks: BackgroundTasks,
    settings: ApiSettings = Depends(get_settings),
    plan_id: str = Form(""),
    dry_run: str = Form("0"),
    schedule_delay_minutes: str = Form(str(ORGANIZE_DEFAULT_DELAY_MIN)),
) -> HTMLResponse:
    """Execute or schedule an organization plan as a background job.

    Returns:
        Job status HTMX partial with progress information.
    """
    info_message: str | None = None
    error_message: str | None = None
    job_view: dict[str, Any] | None = None
    response: HTMLResponse | None = None

    try:
        if not plan_id.strip():
            raise ApiError(status_code=400, error="missing_plan_id", message="Plan id is required.")
        plan = _get_organize_plan(plan_id)
        if plan is None:
            raise ApiError(
                status_code=404, error="plan_not_found", message="Organization plan not found."
            )

        delay_minutes = _parse_delay_minutes(schedule_delay_minutes)
        dry_run_enabled = form_bool(dry_run)
        safe_input = resolve_path(plan["input_dir"], settings.allowed_paths)
        safe_output = resolve_path(plan["output_dir"], settings.allowed_paths)
        executable_plan_data = plan.get("executable_plan")
        if not isinstance(executable_plan_data, dict):
            raise ApiError(
                status_code=400,
                error="plan_not_executable",
                message="Stored plan does not contain executable operations.",
            )
        executable_plan = OrganizationPlan.from_dict(executable_plan_data)
        if Path(executable_plan.input_path).resolve(strict=False) != safe_input.resolve(
            strict=False
        ) or Path(executable_plan.output_path).resolve(strict=False) != safe_output.resolve(
            strict=False
        ):
            raise ApiError(
                status_code=400,
                error="plan_path_mismatch",
                message="Stored plan paths do not match the requested safe paths.",
            )

        organize_request = OrganizeRequest(
            input_dir=str(safe_input),
            output_dir=str(safe_output),
            skip_existing=bool(plan.get("skip_existing", True)),
            dry_run=dry_run_enabled,
            use_hardlinks=bool(plan.get("use_hardlinks", True)),
            run_in_background=True,
        )

        job = create_job(ORGANIZE_JOB_TYPE)
        scheduled_for = ""
        if delay_minutes > 0:
            scheduled_at = datetime.now(UTC).timestamp() + (delay_minutes * 60)
            scheduled_for = format_timestamp(datetime.fromtimestamp(scheduled_at, tz=UTC))
        _set_job_metadata(
            job.job_id,
            {
                "plan_id": plan_id,
                "input_dir": organize_request.input_dir,
                "output_dir": organize_request.output_dir,
                "methodology": _normalize_methodology(plan.get("methodology")),
                "dry_run": organize_request.dry_run,
                "schedule_delay_minutes": delay_minutes,
                "scheduled_for": scheduled_for,
                "executable_plan_id": executable_plan.plan_id,
            },
        )

        if delay_minutes > 0:
            _schedule_plan_job(
                job.job_id,
                executable_plan.to_dict(),
                delay_minutes,
                dry_run=dry_run_enabled,
            )
            info_message = f"Job scheduled to start in {delay_minutes} minute(s)."
        else:
            background_tasks.add_task(
                _run_organize_plan_job,
                job.job_id,
                executable_plan.to_dict(),
                dry_run=dry_run_enabled,
            )
            info_message = "Organization job queued."

        job_view = _build_job_view(job.job_id)
        if job_view is None:
            raise ApiError(status_code=500, error="job_error", message="Failed to queue job.")
    except ApiError as exc:
        error_message = exc.message
    except Exception:
        logger.exception("Failed to queue organize job")
        error_message = "Failed to queue job."

    response = templates.TemplateResponse(
        request,
        "organize/_job_status.html",
        {
            "job": job_view,
            "info_message": info_message,
            "error_message": error_message,
            "rollback_message": None,
        },
    )
    response.headers["HX-Trigger"] = json.dumps({"refreshHistory": True, "refreshStats": True})
    return response


@organize_router.get("/organize/jobs/{job_id}/status", response_class=HTMLResponse)
def organize_job_status(
    request: Request,
    job_id: str,
    format: str = Query("html", pattern="^(html|json)$"),
) -> Response:
    """Return the current status of an organization job.

    Args:
        request: Incoming FastAPI request.
        job_id: Unique job identifier.
        format: Response format (``html`` or ``json``).

    Returns:
        Job status as an HTML partial or JSON payload.
    """
    job = _build_job_view(job_id)
    if job is None:
        raise ApiError(status_code=404, error="not_found", message="Job not found.")
    if format == "json":
        return JSONResponse(content=job)
    return templates.TemplateResponse(
        request,
        "organize/_job_status.html",
        {
            "job": job,
            "info_message": None,
            "error_message": None,
            "rollback_message": None,
        },
    )


@organize_router.get("/organize/jobs/{job_id}/events")
async def organize_job_events(job_id: str) -> StreamingResponse:
    """Stream server-sent events for real-time job progress updates.

    Args:
        job_id: Unique job identifier.

    Returns:
        SSE stream that terminates when the job reaches a terminal state.
    """
    if _build_job_view(job_id) is None:
        raise ApiError(status_code=404, error="not_found", message="Job not found.")

    async def _event_generator() -> Any:
        """Generate server-sent events for job status updates.

        Yields:
            SSE formatted event strings for job status and completion.
        """
        last_payload = ""
        while True:
            job = _build_job_view(job_id)
            if job is None:
                payload = {"job_id": job_id, "status": "missing"}
                data = json.dumps(payload)
                yield f"event: status\ndata: {data}\n\n"
                break

            data = json.dumps(job)
            if data != last_payload:
                yield f"event: status\ndata: {data}\n\n"
                last_payload = data
            else:
                yield ": keep-alive\n\n"
            if job["is_terminal"]:
                yield f"event: complete\ndata: {data}\n\n"
                break
            await asyncio.sleep(ORGANIZE_EVENT_POLL_SECONDS)

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@organize_router.get("/organize/stats/events")
async def organize_stats_events(request: Request) -> StreamingResponse:
    """Stream server-sent events for aggregate statistics updates.

    Emits events whenever job statistics change (active jobs, total jobs,
    files organized, success rate).

    Returns:
        SSE stream with periodic statistics updates.
    """

    async def _event_generator() -> Any:
        """Generate server-sent events for statistics updates.

        Yields:
            SSE formatted event strings with job statistics.
        """
        last_payload = ""
        while True:
            if await request.is_disconnected():
                break
            stats = _build_organize_stats()
            data = json.dumps(stats, sort_keys=True)
            if data != last_payload:
                yield f"event: stats\ndata: {data}\n\n"
                last_payload = data
            else:
                yield ": keep-alive\n\n"
            await asyncio.sleep(ORGANIZE_EVENT_POLL_SECONDS)

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@organize_router.get("/organize/history/events")
async def organize_history_events(
    request: Request,
    status_filter: str = Query("all", pattern="^(all|queued|running|completed|failed)$"),
    limit: int = Query(50, ge=1, le=200),
) -> StreamingResponse:
    """Stream server-sent events for job history updates.

    Emits events whenever the job history changes (new jobs, status changes).

    Args:
        request: Incoming FastAPI request.
        status_filter: Filter history by status (all, queued, running, completed, failed).
        limit: Maximum number of history records to include (1-200).

    Returns:
        SSE stream with periodic history updates.
    """

    async def _event_generator() -> Any:
        """Generate server-sent events for history updates.

        Yields:
            SSE formatted event strings with job history.
        """
        last_payload = ""
        while True:
            if await request.is_disconnected():
                break
            rows = _list_organize_jobs(status_filter=status_filter, limit=limit)
            data = json.dumps(rows, sort_keys=True)
            if data != last_payload:
                yield f"event: history\ndata: {data}\n\n"
                last_payload = data
            else:
                yield ": keep-alive\n\n"
            await asyncio.sleep(ORGANIZE_EVENT_POLL_SECONDS)

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@organize_router.post("/organize/jobs/{job_id}/cancel", response_class=HTMLResponse)
def organize_job_cancel(request: Request, job_id: str) -> HTMLResponse:
    """Cancel a scheduled organization job.

    Returns:
        Updated job status partial.
    """
    job = _build_job_view(job_id)
    if job is None:
        raise ApiError(status_code=404, error="not_found", message="Job not found.")

    info_message: str | None = None
    error_message: str | None = None
    if _cancel_scheduled_job(job_id):
        info_message = "Scheduled job cancelled."
    else:
        error_message = "Only scheduled jobs can be cancelled."
    refreshed_job = _build_job_view(job_id)
    return templates.TemplateResponse(
        request,
        "organize/_job_status.html",
        {
            "job": refreshed_job,
            "info_message": info_message,
            "error_message": error_message,
            "rollback_message": None,
        },
    )


@organize_router.post("/organize/jobs/{job_id}/rollback", response_class=HTMLResponse)
def organize_job_rollback(request: Request, job_id: str) -> HTMLResponse:
    """Rollback a completed organization job using the undo manager.

    Returns:
        Updated job status partial with rollback result.
    """
    job = _build_job_view(job_id)
    if job is None:
        raise ApiError(status_code=404, error="not_found", message="Job not found.")

    rollback_message: str | None = None
    error_message: str | None = None
    if not job["can_rollback"]:
        error_message = "Rollback is only available for completed non-dry-run jobs."
    else:
        try:
            from file_organizer.undo.undo_manager import UndoManager

            manager = UndoManager()
            success = manager.undo_last_operation()
            rollback_message = (
                "Rollback completed for the latest tracked operation."
                if success
                else "No rollback candidates were available."
            )
        except Exception:
            logger.exception("Rollback execution failed for job {}", job_id)
            error_message = "Rollback failed."

    refreshed_job = _build_job_view(job_id)
    response = templates.TemplateResponse(
        request,
        "organize/_job_status.html",
        {
            "job": refreshed_job,
            "info_message": None,
            "error_message": error_message,
            "rollback_message": rollback_message,
        },
    )
    response.headers["HX-Trigger"] = json.dumps({"refreshHistory": True, "refreshStats": True})
    return response


@organize_router.get("/organize/history", response_class=HTMLResponse)
def organize_history(
    request: Request,
    status_filter: str = Query("all", pattern="^(all|queued|running|completed|failed)$"),
    limit: int = Query(ORGANIZE_HISTORY_LIMIT, ge=1, le=200),
) -> HTMLResponse:
    """Return an HTMX partial listing recent organization jobs.

    Returns:
        HTML fragment with the job history table.
    """
    rows = _list_organize_jobs(status_filter=status_filter, limit=limit)
    return templates.TemplateResponse(
        request,
        "organize/_history.html",
        {
            "rows": rows,
            "status_filter": status_filter,
            "limit": limit,
        },
    )


@organize_router.get("/organize/stats", response_class=HTMLResponse)
def organize_stats(request: Request) -> HTMLResponse:
    """Return an HTMX partial with aggregate organization statistics."""
    return templates.TemplateResponse(
        request,
        "organize/_stats.html",
        {
            "stats": _build_organize_stats(),
        },
    )


@organize_router.get("/organize/report/{job_id}")
def organize_report(
    job_id: str, format: str = Query("json", pattern="^(json|csv|txt)$")
) -> Response:
    """Download a job report in JSON, CSV, or plain-text format.

    Args:
        job_id: Unique job identifier.
        format: Output format (``json``, ``csv``, or ``txt``).

    Returns:
        Formatted report response.
    """
    job = _build_job_view(job_id)
    if job is None:
        raise ApiError(status_code=404, error="not_found", message="Job not found.")
    payload = _job_report_payload(job)
    if format == "json":
        return JSONResponse(content=payload)
    if format == "txt":
        lines = [
            f"Job ID: {payload['job_id']}",
            f"Status: {payload['status']}",
            f"Methodology: {payload['methodology']}",
            f"Input: {payload['input_dir']}",
            f"Output: {payload['output_dir']}",
            f"Dry run: {payload['dry_run']}",
            f"Processed: {payload['processed_files']} / {payload['total_files']}",
            f"Failed: {payload['failed_files']}",
            f"Skipped: {payload['skipped_files']}",
            f"Error: {payload['error'] or 'None'}",
        ]
        return Response(
            content="\n".join(lines),
            media_type="text/plain",
            headers={
                "Content-Disposition": build_content_disposition(f"organization-{job_id}.txt"),
            },
        )

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["field", "value"])
    for key in (
        "job_id",
        "status",
        "methodology",
        "input_dir",
        "output_dir",
        "dry_run",
        "processed_files",
        "total_files",
        "failed_files",
        "skipped_files",
        "error",
    ):
        writer.writerow([key, payload.get(key, "")])
    buffer.write("\n")
    writer.writerow(["bucket", "files"])
    result = payload.get("result") or {}
    structure = result.get("organized_structure") or {}
    for bucket, files in structure.items():
        writer.writerow([bucket, ", ".join(files)])
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": build_content_disposition(f"organization-{job_id}.csv"),
        },
    )
