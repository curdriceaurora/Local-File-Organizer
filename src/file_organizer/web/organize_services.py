"""Service helpers for the web organization dashboard."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4

from file_organizer.api.exceptions import ApiError
from file_organizer.api.models import OrganizationError, OrganizationResultResponse
from file_organizer.api.utils import is_hidden, resolve_path
from file_organizer.config.methodology import (
    JOHNNY_DECIMAL,
    PARA,
)
from file_organizer.config.methodology import (
    normalize as _normalize_methodology,
)
from file_organizer.core.organizer import FileOrganizer
from file_organizer.core.plan import (
    CollisionAction,
    OrganizationOperationStatus,
    OrganizationPlan,
)
from file_organizer.core.types import OrganizationResult
from file_organizer.web._forms import form_bool

ORGANIZE_DEFAULT_DELAY_MIN = 0
ORGANIZE_MAX_DELAY_MIN = 7 * 24 * 60
ORGANIZE_PLAN_LIMIT = 200

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


def _scan_directory(path: Path, recursive: bool, include_hidden: bool) -> list[Path]:
    """Collect files from *path*, optionally recursing and including hidden items."""
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
    """Tally files by broad type category (text, image, video, etc.)."""
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
        deduplicated_files=result.deduplicated_files,
        processing_time=result.processing_time,
        organized_structure=result.organized_structure,
        errors=[
            OrganizationError(file=file_name, error=error) for file_name, error in result.errors
        ],
    )


def _methodology_preview_bucket(bucket: str, methodology: str) -> str:
    """Return the dashboard preview bucket for a selected methodology."""
    if methodology == PARA:
        para_roots = {"Projects", "Areas", "Resources", "Archive"}
        if bucket in para_roots or any(bucket.startswith(f"{root}/") for root in para_roots):
            return bucket
        return f"Resources/{bucket}"
    if methodology == JOHNNY_DECIMAL:
        if bucket[:2].isdigit() and len(bucket) > 2 and bucket[2] in {" ", "/", "."}:
            return bucket
        return f"30 Operations & Projects/{bucket}"
    return bucket


def _apply_preview_methodology(
    preview: OrganizationResultResponse,
    methodology: str,
) -> OrganizationResultResponse:
    """Apply methodology-specific destination shape to a dry-run preview."""
    if methodology not in {PARA, JOHNNY_DECIMAL}:
        return preview

    organized_structure: dict[str, list[str]] = {}
    for bucket, names in preview.organized_structure.items():
        mapped_bucket = _methodology_preview_bucket(bucket, methodology)
        organized_structure.setdefault(mapped_bucket, []).extend(names)

    return preview.model_copy(update={"organized_structure": organized_structure})


def _build_plan_movements(
    files: list[Path],
    output_dir: Path,
    preview: OrganizationResultResponse,
) -> list[dict[str, str]]:
    """Build a list of planned source-to-destination movements from a dry-run preview."""
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


def _apply_plan_methodology(plan: OrganizationPlan, methodology: str) -> OrganizationPlan:
    """Return a copy of *plan* with methodology-specific destination buckets."""
    if methodology not in {PARA, JOHNNY_DECIMAL}:
        return plan

    remapped = OrganizationPlan.from_dict(plan.to_dict())
    reserved_destinations: set[str] = set()
    output_dir = remapped.output_root

    for operation in remapped.operations:
        mapped_bucket = _methodology_preview_bucket(operation.folder_name, methodology)
        operation.folder_name = mapped_bucket
        base_destination = output_dir / mapped_bucket / operation.file_name
        operation.destination_path = str(base_destination)
        if operation.status == OrganizationOperationStatus.ERROR:
            continue

        if remapped.skip_existing and base_destination.exists():
            operation.status = OrganizationOperationStatus.SKIPPED
            operation.collision_action = CollisionAction.SKIP_EXISTING
            continue

        operation.status = OrganizationOperationStatus.READY
        operation.collision_action = CollisionAction.CREATE
        if str(base_destination) in reserved_destinations or not remapped.skip_existing:
            counter = 1
            planned = base_destination
            stem, suffix = _split_name_suffix(operation.file_name)
            while planned.exists() or str(planned) in reserved_destinations:
                planned = output_dir / mapped_bucket / f"{stem}_{counter}{suffix}"
                counter += 1
            if planned != base_destination:
                operation.destination_path = str(planned)
                operation.file_name = planned.name
                operation.collision_action = CollisionAction.RENAME_WITH_COUNTER

        reserved_destinations.add(operation.destination_path)

    remapped.processed_files = len(remapped.ready_operations)
    remapped.skipped_files = sum(
        1
        for operation in remapped.operations
        if operation.status == OrganizationOperationStatus.SKIPPED
    )
    remapped.failed_files = sum(
        1
        for operation in remapped.operations
        if operation.status == OrganizationOperationStatus.ERROR
    )
    remapped.metadata["methodology"] = methodology
    return remapped


def _split_name_suffix(file_name: str) -> tuple[str, str]:
    """Split a file name into stem and suffix without constructing a Path."""
    stem, dot, suffix = file_name.rpartition(".")
    if not dot or not stem:
        return file_name, ""
    return stem, f".{suffix}"


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


def _get_organize_plan(plan_id: str) -> dict[str, Any] | None:
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


def build_organize_plan(
    *,
    input_dir: str,
    output_dir: str,
    methodology: str,
    recursive: str,
    include_hidden: str,
    skip_existing: str,
    use_hardlinks: str,
    allowed_paths: list[str] | None,
    organizer_factory: Callable[..., FileOrganizer] = FileOrganizer,
) -> dict[str, Any]:
    """Validate scan input, run a dry-run preview, and persist the resulting plan."""
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
    if not safe_input.exists():
        raise ApiError(status_code=404, error="not_found", message="Input directory not found.")

    normalized_methodology = _normalize_methodology(methodology)
    recursive_enabled = form_bool(recursive)
    include_hidden_enabled = form_bool(include_hidden)
    if include_hidden_enabled:
        raise ApiError(
            status_code=400,
            error="include_hidden_not_supported",
            message="Including hidden files is not supported in this dashboard flow yet.",
        )
    skip_existing_enabled = form_bool(skip_existing)
    use_hardlinks_enabled = form_bool(use_hardlinks)

    scan_files = _scan_directory(
        safe_input,
        recursive=recursive_enabled,
        include_hidden=include_hidden_enabled,
    )
    counts = _counts_by_type(scan_files)

    organizer = organizer_factory(dry_run=True, use_hardlinks=use_hardlinks_enabled)
    preview_result = organizer.organize(
        input_path=safe_input,
        output_path=safe_output,
        skip_existing=skip_existing_enabled,
    )
    plan = preview_result.plan
    if not isinstance(plan, OrganizationPlan):
        raise ApiError(
            status_code=500,
            error="plan_unavailable",
            message="Dry-run did not produce an executable organization plan.",
        )
    plan = _apply_plan_methodology(plan, normalized_methodology)
    preview_result.organized_structure = plan.organized_structure()
    preview_result.processed_files = plan.processed_files
    preview_result.skipped_files = plan.skipped_files
    preview = _result_to_response(preview_result)
    return _store_organize_plan(
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
