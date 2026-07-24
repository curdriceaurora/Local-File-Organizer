"""Service helpers for the web organization dashboard."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from threading import Lock
from typing import Any, cast
from uuid import uuid4

from file_organizer.api.exceptions import ApiError
from file_organizer.api.models import OrganizationError, OrganizationResultResponse
from file_organizer.api.utils import resolve_path
from file_organizer.config.methodology import (
    normalize as _normalize_methodology,
)
from file_organizer.core.organization_service import OrganizationService
from file_organizer.core.organize_options import ModelProvider, OrganizeOptions, OrganizeRequest
from file_organizer.core.organizer import FileOrganizer
from file_organizer.core.plan import OrganizationPlan
from file_organizer.core.types import OrganizationResult
from file_organizer.web._forms import form_bool

ORGANIZE_DEFAULT_DELAY_MIN = 0
ORGANIZE_MAX_DELAY_MIN = 7 * 24 * 60
ORGANIZE_PLAN_LIMIT = 200
ORGANIZE_PLAN_TTL_SECONDS = 3600

_ORGANIZE_PLAN_STORE: dict[str, dict[str, Any]] = {}
_ORGANIZE_PLAN_LOCK = Lock()


def _parse_delay_minutes(value: str | None) -> int:
    """Parse and validate a schedule delay value in minutes."""
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


def _result_to_response(result: OrganizationResult) -> OrganizationResultResponse:
    """Convert an ``OrganizationResult`` to the API response model."""
    return OrganizationResultResponse(
        total_files=result.total_files,
        processed_files=result.processed_files,
        skipped_files=result.skipped_files,
        failed_files=result.failed_files,
        deduplicated_files=result.deduplicated_files,
        processing_time=result.processing_time,
        organized_structure=result.organized_structure,
        errors=[
            OrganizationError(file=file_name, error=error) for file_name, error in result.errors
        ],
        transaction_id=result.transaction_id,
    )


def _prune_plan_store() -> None:
    """Evict expired plans, then oldest entries when the store still exceeds its limit."""
    now = datetime.now(UTC)
    expired = [
        plan_id
        for plan_id, record in _ORGANIZE_PLAN_STORE.items()
        if (now - record.get("created_at", now)).total_seconds() > ORGANIZE_PLAN_TTL_SECONDS
    ]
    for plan_id in expired:
        _ORGANIZE_PLAN_STORE.pop(plan_id, None)
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


def _get_organize_plan(plan_id: str) -> dict[str, Any] | None:
    """Retrieve a stored plan by *plan_id*, or ``None`` if expired/missing."""
    with _ORGANIZE_PLAN_LOCK:
        plan = _ORGANIZE_PLAN_STORE.get(plan_id)
        if plan is None:
            return None
        now = datetime.now(UTC)
        if (now - plan["created_at"]).total_seconds() > ORGANIZE_PLAN_TTL_SECONDS:
            _ORGANIZE_PLAN_STORE.pop(plan_id, None)
            return None
        plan["updated_at"] = now
        return dict(plan)


def _delete_organize_plan(plan_id: str) -> None:
    """Remove a plan from the in-memory store."""
    with _ORGANIZE_PLAN_LOCK:
        _ORGANIZE_PLAN_STORE.pop(plan_id, None)


def _optional_int(value: str | None, field_name: str) -> int | None:
    """Parse an optional integer form value into the canonical option shape."""
    if value is None or not value.strip():
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise ApiError(
            status_code=400,
            error="invalid_organization_options",
            message=f"{field_name} must be a whole number.",
        ) from exc


def _optional_float(value: str | None, field_name: str) -> float | None:
    """Parse an optional numeric form value into the canonical option shape."""
    if value is None or not value.strip():
        return None
    try:
        return float(value)
    except ValueError as exc:
        raise ApiError(
            status_code=400,
            error="invalid_organization_options",
            message=f"{field_name} must be a number.",
        ) from exc


def parse_organize_options(
    *,
    methodology: str,
    recursive: str,
    include_hidden: str,
    skip_existing: str,
    transfer_mode: str,
    use_hardlinks: str,
    enable_vision: str,
    transcribe_audio: str,
    max_transcribe_seconds: str,
    whisper_model: str,
    parallel_workers: str,
    prefetch_depth: str,
    text_model: str,
    vision_model: str,
    text_provider: str = "",
    vision_provider: str = "",
) -> OrganizeOptions:
    """Map Web form values into the complete canonical organization contract."""
    normalized_methodology = _normalize_methodology(methodology, default="")
    if not normalized_methodology:
        raise ApiError(
            status_code=400,
            error="invalid_organization_options",
            message="Methodology must be none, para, or jd.",
        )
    resolved_transfer_mode = transfer_mode.strip()
    if not resolved_transfer_mode:
        resolved_transfer_mode = "hardlink" if form_bool(use_hardlinks) else "copy"
    parsed_prefetch_depth = _optional_int(prefetch_depth, "Prefetch depth")
    try:
        return OrganizeOptions(
            recursive=form_bool(recursive),
            include_hidden=form_bool(include_hidden),
            skip_existing=form_bool(skip_existing),
            transfer_mode=resolved_transfer_mode,
            methodology=normalized_methodology,
            enable_vision=form_bool(enable_vision),
            transcribe_audio=form_bool(transcribe_audio),
            max_transcribe_seconds=_optional_float(
                max_transcribe_seconds, "Maximum transcription seconds"
            ),
            whisper_model=whisper_model.strip(),
            parallel_workers=_optional_int(parallel_workers, "Parallel workers"),
            prefetch_depth=2 if parsed_prefetch_depth is None else parsed_prefetch_depth,
            text_model=text_model.strip() or None,
            vision_model=vision_model.strip() or None,
            text_provider=(
                cast(ModelProvider, text_provider.strip()) if text_provider.strip() else None
            ),
            vision_provider=(
                cast(ModelProvider, vision_provider.strip()) if vision_provider.strip() else None
            ),
        )
    except ValueError as exc:
        raise ApiError(
            status_code=400,
            error="invalid_organization_options",
            message=str(exc),
        ) from exc


def build_organize_plan(
    *,
    input_dir: str,
    output_dir: str,
    allowed_paths: list[str] | None,
    options: OrganizeOptions | None = None,
    organization_service: OrganizationService | None = None,
    methodology: str = "none",
    recursive: str = "1",
    include_hidden: str = "0",
    skip_existing: str = "1",
    use_hardlinks: str = "1",
    organizer_factory: Callable[..., FileOrganizer] | None = None,
) -> dict[str, Any]:
    """Validate paths and persist a scan/preview produced by the canonical service."""
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

    safe_input = resolve_path(input_dir, allowed_paths)
    safe_output = resolve_path(output_dir, allowed_paths)
    if options is None:
        options = parse_organize_options(
            methodology=methodology,
            recursive=recursive,
            include_hidden=include_hidden,
            skip_existing=skip_existing,
            transfer_mode="",
            use_hardlinks=use_hardlinks,
            enable_vision="1",
            transcribe_audio="0",
            max_transcribe_seconds="600",
            whisper_model="tiny",
            parallel_workers="",
            prefetch_depth="2",
            text_model="",
            vision_model="",
            text_provider="",
            vision_provider="",
        )
    if organization_service is None:
        organization_service = OrganizationService(
            organizer_factory=organizer_factory or FileOrganizer,
        )

    organization_request = OrganizeRequest(safe_input, safe_output, options)
    scan = organization_service.scan(organization_request)
    preview_result = organization_service.preview(organization_request)
    plan = preview_result.plan
    if not isinstance(plan, OrganizationPlan):
        raise ApiError(
            status_code=500,
            error="plan_unavailable",
            message="Dry-run did not produce an executable organization plan.",
        )
    preview_result.organized_structure = plan.organized_structure()
    preview_result.processed_files = plan.processed_files
    preview_result.skipped_files = plan.skipped_files
    preview = _result_to_response(preview_result)
    return _store_organize_plan(
        {
            "input_dir": str(safe_input),
            "output_dir": str(safe_output),
            "methodology": plan.options.effective_methodology.value,
            "recursive": plan.options.recursive,
            "include_hidden": plan.options.include_hidden,
            "skip_existing": plan.options.skip_existing,
            "use_hardlinks": plan.options.use_hardlinks,
            "transfer_mode": plan.options.effective_transfer_mode.value,
            "options": plan.options.to_dict(),
            "scan_files": [str(path) for path in scan.files],
            "scan_counts": scan.counts,
            "scan_total_files": scan.total_files,
            "preview": preview.model_dump(),
            "movements": plan.movements(),
            "executable_plan": plan.to_dict(),
        }
    )


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
