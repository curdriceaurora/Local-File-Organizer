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
from typing import Any, Optional
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from loguru import logger

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_settings
from file_organizer.api.exceptions import ApiError
from file_organizer.api.jobs import create_job, get_job, list_jobs, update_job
from file_organizer.api.models import OrganizationError, OrganizationResultResponse, OrganizeRequest
from file_organizer.api.utils import is_hidden, resolve_path
from file_organizer.core.organizer import FileOrganizer, OrganizationResult
from file_organizer.web._helpers import (
    allowed_roots,
    as_bool,
    build_content_disposition,
    format_timestamp,
    templates,
)

organize_router = APIRouter(tags=["web"])

ORGANIZE_DEFAULT_DELAY_MIN = 0
ORGANIZE_MAX_DELAY_MIN = 7 * 24 * 60
ORGANIZE_EVENT_POLL_SECONDS = 1
ORGANIZE_HISTORY_LIMIT = 50
ORGANIZE_PLAN_LIMIT = 200
ORGANIZE_JOB_TYPE = "organize_web"
JOB_METADATA_PRUNE_THRESHOLD = 256
JOB_METADATA_PRUNE_INTERVAL_SECONDS = 60.0

ORGANIZE_METHODOLOGIES = {
    "johnny_decimal": "Johnny Decimal",
    "para": "PARA",
    "content_based": "Content-Based",
    "date_based": "Date-Based",
}

_ORGANIZE_PLAN_STORE: dict[str, dict[str, Any]] = {}
_ORGANIZE_PLAN_LOCK = Lock()
_SCHEDULED_TIMERS: dict[str, Timer] = {}
_SCHEDULED_TIMERS_LOCK = Lock()
_JOB_METADATA: dict[str, dict[str, Any]] = {}
_JOB_METADATA_LOCK = Lock()
_LAST_JOB_METADATA_PRUNE_MONOTONIC = 0.0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_delay_minutes(value: Optional[str]) -> int:
    """Parse and validate a schedule delay value in minutes.

    Args:
        value: Raw string from the form field.

    Returns:
        Validated delay in minutes.

    Raises:
        ApiError: If the value is not a valid non-negative integer within bounds.
    """
    if value is None or value.strip() == "":
        return ORGANIZE_DEFAULT_DELAY_MIN
    try:
        minutes = int(value)
    except ValueError as exc:
        raise ApiError(
            status_code=400,
            error="invalid_schedule_delay",
            message="Schedule delay must be a whole number of minutes.",
        ) from exc
    if minutes < 0 or minutes > ORGANIZE_MAX_DELAY_MIN:
        raise ApiError(
            status_code=400,
            error="invalid_schedule_delay",
            message=f"Schedule delay must be between 0 and {ORGANIZE_MAX_DELAY_MIN} minutes.",
        )
    return minutes


def _normalize_methodology(value: Optional[str]) -> str:
    """Normalize a methodology string, defaulting to ``content_based``."""
    token = (value or "").strip().lower()
    if token in ORGANIZE_METHODOLOGIES:
        return token
    return "content_based"


def _scan_directory(path: Path, recursive: bool, include_hidden: bool) -> list[Path]:
    """Collect files from *path*, optionally recursing and including hidden items.

    Returns:
        List of file ``Path`` objects found under *path*.
    """
    files: list[Path] = []
    if path.is_file():
        if include_hidden or not is_hidden(path):
            files.append(path)
        return files

    iterator = path.rglob("*") if recursive else path.glob("*")
    for entry in iterator:
        if not entry.is_file():
            continue
        if not include_hidden and is_hidden(entry):
            continue
        files.append(entry)
    return files


def _counts_by_type(files: list[Path]) -> dict[str, int]:
    """Tally files by broad type category (text, image, video, etc.).

    Returns:
        Dict mapping category names to counts.
    """
    counts = {
        "text": 0,
        "image": 0,
        "video": 0,
        "audio": 0,
        "cad": 0,
        "other": 0,
    }
    for path in files:
        suffix = path.suffix.lower()
        if suffix in FileOrganizer.TEXT_EXTENSIONS:
            counts["text"] += 1
        elif suffix in FileOrganizer.IMAGE_EXTENSIONS:
            counts["image"] += 1
        elif suffix in FileOrganizer.VIDEO_EXTENSIONS:
            counts["video"] += 1
        elif suffix in FileOrganizer.AUDIO_EXTENSIONS:
            counts["audio"] += 1
        elif suffix in FileOrganizer.CAD_EXTENSIONS:
            counts["cad"] += 1
        else:
            counts["other"] += 1
    return counts


def _result_to_response(result: OrganizationResult) -> OrganizationResultResponse:
    """Convert an ``OrganizationResult`` to the API response model."""
    return OrganizationResultResponse(
        total_files=result.total_files,
        processed_files=result.processed_files,
        skipped_files=result.skipped_files,
        failed_files=result.failed_files,
        processing_time=result.processing_time,
        organized_structure=result.organized_structure,
        errors=[
            OrganizationError(file=file_name, error=error) for file_name, error in result.errors
        ],
    )


def _build_plan_movements(
    files: list[Path],
    output_dir: Path,
    preview: OrganizationResultResponse,
) -> list[dict[str, str]]:
    """Build a list of planned source-to-destination movements from a dry-run preview.

    Returns:
        List of dicts with *file_name*, *source*, *destination*, and *reason*.
    """
    source_lookup: dict[str, list[str]] = {}
    for file_path in sorted(files, key=lambda item: item.as_posix().lower()):
        source_lookup.setdefault(file_path.name, []).append(str(file_path))

    movements: list[dict[str, str]] = []
    for bucket, names in sorted(
        preview.organized_structure.items(), key=lambda item: item[0].lower()
    ):
        for name in sorted(names, key=str.lower):
            sources = source_lookup.get(name, [])
            source_path = sources.pop(0) if sources else name
            destination = output_dir / bucket / name
            movements.append(
                {
                    "file_name": name,
                    "source": source_path,
                    "destination": str(destination),
                    "reason": f"Categorized into {bucket}",
                }
            )
    return movements


def _prune_plan_store() -> None:
    """Evict the oldest plans when the in-memory store exceeds its limit."""
    while len(_ORGANIZE_PLAN_STORE) > ORGANIZE_PLAN_LIMIT:
        oldest_plan_id = next(iter(_ORGANIZE_PLAN_STORE))
        _ORGANIZE_PLAN_STORE.pop(oldest_plan_id, None)


def _store_organize_plan(plan_data: dict[str, Any]) -> dict[str, Any]:
    """Persist *plan_data* in the in-memory plan store and return the stored record."""
    plan_id = uuid4().hex
    created_at = datetime.now(UTC)
    record = {
        "plan_id": plan_id,
        "created_at": created_at,
        "updated_at": created_at,
        **plan_data,
    }
    with _ORGANIZE_PLAN_LOCK:
        _ORGANIZE_PLAN_STORE[plan_id] = record
        _prune_plan_store()
    return record


def _get_organize_plan(plan_id: str) -> Optional[dict[str, Any]]:
    """Retrieve a stored plan by *plan_id*, or ``None`` if expired/missing."""
    with _ORGANIZE_PLAN_LOCK:
        plan = _ORGANIZE_PLAN_STORE.get(plan_id)
        if plan is None:
            return None
        plan["updated_at"] = datetime.now(UTC)
        return dict(plan)


def _delete_organize_plan(plan_id: str) -> None:
    """Remove a plan from the in-memory store."""
    with _ORGANIZE_PLAN_LOCK:
        _ORGANIZE_PLAN_STORE.pop(plan_id, None)


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


def _build_job_view(job_id: str) -> Optional[dict[str, Any]]:
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
        "methodology": metadata.get("methodology", "content_based"),
        "methodology_label": ORGANIZE_METHODOLOGIES.get(
            metadata.get("methodology", "content_based"),
            "Content-Based",
        ),
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
    status_filter: Optional[str] = None,
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
        label = job.get("methodology_label", "Content-Based")
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


def _schedule_job(job_id: str, organize_request: OrganizeRequest, delay_minutes: int) -> None:
    """Schedule an organization job to run after *delay_minutes*.

    If *delay_minutes* is zero or negative the job runs immediately.
    """
    delay_seconds = delay_minutes * 60

    def _runner() -> None:
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


def _job_report_payload(job: dict[str, Any]) -> dict[str, Any]:
    """Extract a serializable report payload from a job view dict."""
    return {
        "job_id": job["job_id"],
        "status": job["status"],
        "created_at": job["created_at"],
        "updated_at": job["updated_at"],
        "methodology": job["methodology"],
        "input_dir": job["input_dir"],
        "output_dir": job["output_dir"],
        "dry_run": job["dry_run"],
        "processed_files": job["processed_files"],
        "total_files": job["total_files"],
        "failed_files": job["failed_files"],
        "skipped_files": job["skipped_files"],
        "error": job["error"],
        "result": job["result"],
    }


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
    return templates.TemplateResponse("organize/dashboard.html", context)


@organize_router.post("/organize/scan", response_class=HTMLResponse)
def organize_scan(
    request: Request,
    settings: ApiSettings = Depends(get_settings),
    input_dir: str = Form(""),
    output_dir: str = Form(""),
    methodology: str = Form("content_based"),
    recursive: str = Form("1"),
    include_hidden: str = Form("0"),
    skip_existing: str = Form("1"),
    use_hardlinks: str = Form("1"),
) -> HTMLResponse:
    """Scan the input directory and generate a dry-run organization plan.

    Returns:
        HTMX partial showing the generated plan or an error message.
    """
    error_message: Optional[str] = None
    info_message: Optional[str] = None
    plan: Optional[dict[str, Any]] = None

    try:
        if not input_dir.strip():
            raise ApiError(
                status_code=400,
                error="missing_input_dir",
                message="Input directory is required.",
            )
        if not output_dir.strip():
            raise ApiError(
                status_code=400,
                error="missing_output_dir",
                message="Output directory is required.",
            )

        safe_input = resolve_path(input_dir, settings.allowed_paths)
        safe_output = resolve_path(output_dir, settings.allowed_paths)
        if not safe_input.exists():
            raise ApiError(status_code=404, error="not_found", message="Input directory not found.")

        normalized_methodology = _normalize_methodology(methodology)
        recursive_enabled = as_bool(recursive)
        include_hidden_enabled = as_bool(include_hidden)
        if include_hidden_enabled:
            raise ApiError(
                status_code=400,
                error="include_hidden_not_supported",
                message="Including hidden files is not supported in this dashboard flow yet.",
            )
        skip_existing_enabled = as_bool(skip_existing)
        use_hardlinks_enabled = as_bool(use_hardlinks)

        scan_files = _scan_directory(
            safe_input,
            recursive=recursive_enabled,
            include_hidden=include_hidden_enabled,
        )
        counts = _counts_by_type(scan_files)

        organizer = FileOrganizer(dry_run=True, use_hardlinks=use_hardlinks_enabled)
        preview_result = organizer.organize(
            input_path=safe_input,
            output_path=safe_output,
            skip_existing=skip_existing_enabled,
        )
        preview = _result_to_response(preview_result)
        plan = _store_organize_plan(
            {
                "input_dir": str(safe_input),
                "output_dir": str(safe_output),
                "methodology": normalized_methodology,
                "recursive": recursive_enabled,
                "include_hidden": include_hidden_enabled,
                "skip_existing": skip_existing_enabled,
                "use_hardlinks": use_hardlinks_enabled,
                "scan_counts": counts,
                "scan_total_files": len(scan_files),
                "preview": preview.model_dump(),
                "movements": _build_plan_movements(scan_files, safe_output, preview),
            }
        )
        info_message = "Plan generated. Review movements and execute when ready."
    except ApiError as exc:
        error_message = exc.message
    except Exception:
        logger.exception("Failed to generate organize plan")
        error_message = "Failed to generate plan."

    return templates.TemplateResponse(
        "organize/_plan.html",
        {
            "request": request,
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
        "organize/_plan.html",
        {
            "request": request,
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
    info_message: Optional[str] = None
    error_message: Optional[str] = None
    job_view: Optional[dict[str, Any]] = None
    response: Optional[HTMLResponse] = None

    try:
        if not plan_id.strip():
            raise ApiError(status_code=400, error="missing_plan_id", message="Plan id is required.")
        plan = _get_organize_plan(plan_id)
        if plan is None:
            raise ApiError(
                status_code=404, error="plan_not_found", message="Organization plan not found."
            )

        delay_minutes = _parse_delay_minutes(schedule_delay_minutes)
        dry_run_enabled = as_bool(dry_run)
        safe_input = resolve_path(plan["input_dir"], settings.allowed_paths)
        safe_output = resolve_path(plan["output_dir"], settings.allowed_paths)

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
                "methodology": str(plan.get("methodology", "content_based")),
                "dry_run": organize_request.dry_run,
                "schedule_delay_minutes": delay_minutes,
                "scheduled_for": scheduled_for,
            },
        )

        if delay_minutes > 0:
            _schedule_job(job.job_id, organize_request, delay_minutes)
            info_message = f"Job scheduled to start in {delay_minutes} minute(s)."
        else:
            background_tasks.add_task(_run_organize_job, job.job_id, organize_request)
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
        "organize/_job_status.html",
        {
            "request": request,
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
        "organize/_job_status.html",
        {
            "request": request,
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


@organize_router.post("/organize/jobs/{job_id}/cancel", response_class=HTMLResponse)
def organize_job_cancel(request: Request, job_id: str) -> HTMLResponse:
    """Cancel a scheduled organization job.

    Returns:
        Updated job status partial.
    """
    job = _build_job_view(job_id)
    if job is None:
        raise ApiError(status_code=404, error="not_found", message="Job not found.")

    info_message: Optional[str] = None
    error_message: Optional[str] = None
    if _cancel_scheduled_job(job_id):
        info_message = "Scheduled job cancelled."
    else:
        error_message = "Only scheduled jobs can be cancelled."
    refreshed_job = _build_job_view(job_id)
    return templates.TemplateResponse(
        "organize/_job_status.html",
        {
            "request": request,
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

    rollback_message: Optional[str] = None
    error_message: Optional[str] = None
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
        "organize/_job_status.html",
        {
            "request": request,
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
        "organize/_history.html",
        {
            "request": request,
            "rows": rows,
            "status_filter": status_filter,
            "limit": limit,
        },
    )


@organize_router.get("/organize/stats", response_class=HTMLResponse)
def organize_stats(request: Request) -> HTMLResponse:
    """Return an HTMX partial with aggregate organization statistics."""
    return templates.TemplateResponse(
        "organize/_stats.html",
        {
            "request": request,
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
