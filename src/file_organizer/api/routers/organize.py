"""Organization endpoints."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_current_active_user, get_settings
from file_organizer.api.exceptions import ApiError
from file_organizer.api.jobs import create_job, get_job, update_job
from file_organizer.api.models import (
    JobStatusResponse,
    OrganizationError,
    OrganizationResultResponse,
    OrganizeExecuteResponse,
    OrganizeRequest,
    ScanRequest,
    ScanResponse,
)
from file_organizer.api.utils import is_hidden, resolve_path
from file_organizer.core.organizer import FileOrganizer, OrganizationResult

router = APIRouter(tags=["organize"], dependencies=[Depends(get_current_active_user)])


def _scan_directory(path: Path, recursive: bool, include_hidden: bool) -> list[Path]:
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
    counts = {
        "text": 0,
        "image": 0,
        "video": 0,
        "audio": 0,
        "cad": 0,
        "other": 0,
    }
    for path in files:
        ext = path.suffix.lower()
        if ext in FileOrganizer.TEXT_EXTENSIONS:
            counts["text"] += 1
        elif ext in FileOrganizer.IMAGE_EXTENSIONS:
            counts["image"] += 1
        elif ext in FileOrganizer.VIDEO_EXTENSIONS:
            counts["video"] += 1
        elif ext in FileOrganizer.AUDIO_EXTENSIONS:
            counts["audio"] += 1
        elif ext in FileOrganizer.CAD_EXTENSIONS:
            counts["cad"] += 1
        else:
            counts["other"] += 1
    return counts


def _result_to_response(result: OrganizationResult) -> OrganizationResultResponse:
    return OrganizationResultResponse(
        total_files=result.total_files,
        processed_files=result.processed_files,
        skipped_files=result.skipped_files,
        failed_files=result.failed_files,
        processing_time=result.processing_time,
        organized_structure=result.organized_structure,
        errors=[OrganizationError(file=err[0], error=err[1]) for err in result.errors],
    )


def _run_organize_job(job_id: str, request: OrganizeRequest) -> None:
    """Run a background organization job with validated paths."""
    update_job(job_id, status="running")
    try:
        organizer = FileOrganizer(
            dry_run=request.dry_run,
            use_hardlinks=request.use_hardlinks,
        )
        result = organizer.organize(
            input_path=request.input_dir,
            output_path=request.output_dir,
            skip_existing=request.skip_existing,
        )
        response = _result_to_response(result).model_dump()
        update_job(job_id, status="completed", result=response)
    except Exception as exc:
        update_job(job_id, status="failed", error=str(exc))


@router.post("/organize/scan", response_model=ScanResponse)
def scan_directory(
    request: ScanRequest,
    settings: ApiSettings = Depends(get_settings),
) -> ScanResponse:
    """Scan a directory and return file counts by type."""
    path = resolve_path(request.input_dir, settings.allowed_paths)
    if not path.exists():
        raise ApiError(status_code=404, error="not_found", message="Input path not found")

    files = _scan_directory(path, request.recursive, request.include_hidden)
    counts = _counts_by_type(files)
    return ScanResponse(
        input_dir=str(path),
        total_files=len(files),
        counts=counts,
    )


@router.post("/organize/preview", response_model=OrganizationResultResponse)
def preview_organization(
    request: OrganizeRequest,
    settings: ApiSettings = Depends(get_settings),
) -> OrganizationResultResponse:
    """Preview organization results without moving files."""
    path = resolve_path(request.input_dir, settings.allowed_paths)
    output = resolve_path(request.output_dir, settings.allowed_paths)
    if not path.exists():
        raise ApiError(status_code=404, error="not_found", message="Input path not found")

    organizer = FileOrganizer(dry_run=True, use_hardlinks=request.use_hardlinks)
    result = organizer.organize(
        input_path=path,
        output_path=output,
        skip_existing=request.skip_existing,
    )
    return _result_to_response(result)


@router.post("/organize/execute", response_model=OrganizeExecuteResponse)
def execute_organization(
    request: OrganizeRequest,
    background_tasks: BackgroundTasks,
    settings: ApiSettings = Depends(get_settings),
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
        job = create_job("organize")
        background_tasks.add_task(_run_organize_job, job.job_id, safe_request)
        return OrganizeExecuteResponse(status="queued", job_id=job.job_id)

    try:
        organizer = FileOrganizer(
            dry_run=request.dry_run,
            use_hardlinks=request.use_hardlinks,
        )
        result = organizer.organize(
            input_path=path,
            output_path=output,
            skip_existing=safe_request.skip_existing,
        )
        return OrganizeExecuteResponse(
            status="completed",
            result=_result_to_response(result),
        )
    except Exception as exc:
        return OrganizeExecuteResponse(status="failed", error=str(exc))


@router.get("/organize/status/{job_id}", response_model=JobStatusResponse)
def get_job_status(job_id: str) -> JobStatusResponse:
    """Retrieve the status of an organization job."""
    job = get_job(job_id)
    if not job:
        raise ApiError(status_code=404, error="not_found", message="Job not found")
    result = OrganizationResultResponse(**job.result) if job.result is not None else None
    return JobStatusResponse(
        job_id=job.job_id,
        status=job.status,
        created_at=job.created_at,
        updated_at=job.updated_at,
        result=result,
        error=job.error,
    )


class SimpleOrganizeRequest(BaseModel):
    """Simple single-file organization request."""

    filename: str
    folder_suggestion: str | None = None


class SimpleOrganizeResponse(BaseModel):
    """Response from simple organize endpoint."""

    filename: str
    folder_name: str
    confidence: float


@router.post("/organize", response_model=None)
async def organize_file(
    file: UploadFile | None = File(None),
    request: SimpleOrganizeRequest | None = None,
    settings: ApiSettings = Depends(get_settings),
) -> SimpleOrganizeResponse | JSONResponse:
    """Organize a single file with naming and folder suggestions.

    Accepts either file upload (multipart/form-data) or JSON request body.
    """
    import os

    # Get filename from file upload or request body
    if file:
        filename = file.filename or "unknown"
    elif request:
        filename = request.filename
    else:
        return JSONResponse(
            status_code=400,
            content={"detail": "Either file upload or request body must be provided"},
        )

    # Simple logic: extract base name and suggest folder
    base_name = os.path.basename(filename)
    name_parts = os.path.splitext(base_name)

    # Simple category detection
    ext = name_parts[1].lower()
    if ext in [".txt", ".md", ".pdf", ".doc", ".docx"]:
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
