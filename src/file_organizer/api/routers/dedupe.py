"""Deduplication endpoints."""

from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, Depends

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_current_active_user, get_settings
from file_organizer.api.exceptions import ApiError
from file_organizer.api.models import (
    DedupeExecuteRequest,
    DedupeExecuteResponse,
    DedupeFileInfo,
    DedupeGroup,
    DedupePreviewGroup,
    DedupePreviewResponse,
    DedupeScanRequest,
    DedupeScanResponse,
)
from file_organizer.api.utils import resolve_path
from file_organizer.services.deduplication import DuplicateDetector
from file_organizer.services.deduplication.detector import ScanOptions

router = APIRouter(tags=["dedupe"], dependencies=[Depends(get_current_active_user)])


def _scan_duplicates(
    path: Path, request: DedupeScanRequest
) -> tuple[list[DedupeGroup], dict[str, int]]:
    detector = DuplicateDetector()
    options = ScanOptions(
        algorithm=request.algorithm,
        recursive=request.recursive,
        min_file_size=request.min_file_size,
        max_file_size=request.max_file_size,
        file_patterns=request.include_patterns,
        exclude_patterns=request.exclude_patterns,
    )
    index = detector.scan_directory(path, options)
    duplicates = index.get_duplicates()

    groups: list[DedupeGroup] = []
    for hash_value, group in duplicates.items():
        files = [
            DedupeFileInfo(
                path=str(file.path),
                size=file.size,
                modified=file.modified_time,
                accessed=file.accessed_time,
            )
            for file in group.files
        ]
        groups.append(
            DedupeGroup(
                hash_value=hash_value,
                files=files,
                total_size=group.total_size,
                wasted_space=group.wasted_space,
            )
        )

    return groups, index.get_statistics()


def _preview(groups: list[DedupeGroup]) -> list[DedupePreviewGroup]:
    previews: list[DedupePreviewGroup] = []
    for group in groups:
        if not group.files:
            continue
        keep = group.files[0].path
        remove = [file.path for file in group.files[1:]]
        previews.append(DedupePreviewGroup(hash_value=group.hash_value, keep=keep, remove=remove))
    return previews


@router.post("/dedupe/scan", response_model=DedupeScanResponse)
def scan_duplicates(
    request: DedupeScanRequest,
    settings: ApiSettings = Depends(get_settings),
) -> DedupeScanResponse:
    """Scan a directory for duplicate files and return groups."""
    path = resolve_path(request.path, settings.allowed_paths)
    if not path.exists():
        raise ApiError(status_code=404, error="not_found", message="Path not found")
    if not path.is_dir():
        raise ApiError(status_code=400, error="invalid_path", message="Path is not a directory")

    groups, stats = _scan_duplicates(path, request)
    return DedupeScanResponse(path=str(path), duplicates=groups, stats=stats)


@router.post("/dedupe/preview", response_model=DedupePreviewResponse)
def preview_duplicates(
    request: DedupeScanRequest,
    settings: ApiSettings = Depends(get_settings),
) -> DedupePreviewResponse:
    """Preview which duplicates would be kept and removed."""
    path = resolve_path(request.path, settings.allowed_paths)
    if not path.exists():
        raise ApiError(status_code=404, error="not_found", message="Path not found")
    if not path.is_dir():
        raise ApiError(status_code=400, error="invalid_path", message="Path is not a directory")

    groups, stats = _scan_duplicates(path, request)
    preview = _preview(groups)
    return DedupePreviewResponse(path=str(path), preview=preview, stats=stats)


@router.post("/dedupe/execute", response_model=DedupeExecuteResponse)
def execute_deduplication(
    request: DedupeExecuteRequest,
    settings: ApiSettings = Depends(get_settings),
) -> DedupeExecuteResponse:
    """Remove duplicate files, optionally moving them to trash."""
    path = resolve_path(request.path, settings.allowed_paths)
    if not path.exists():
        raise ApiError(status_code=404, error="not_found", message="Path not found")
    if not path.is_dir():
        raise ApiError(status_code=400, error="invalid_path", message="Path is not a directory")

    scan_request = DedupeScanRequest(
        path=request.path,
        recursive=request.recursive,
        algorithm=request.algorithm,
        min_file_size=request.min_file_size,
        max_file_size=request.max_file_size,
        include_patterns=request.include_patterns,
        exclude_patterns=request.exclude_patterns,
    )
    groups, stats = _scan_duplicates(path, scan_request)
    preview = _preview(groups)

    removed: list[str] = []
    if not request.dry_run:
        for group in preview:
            for file_path in group.remove:
                target = resolve_path(file_path, settings.allowed_paths)
                if not target.exists():
                    continue
                if request.trash:
                    trash_dir = Path.home() / ".config" / "file-organizer" / "trash"
                    trash_dir.mkdir(parents=True, exist_ok=True)
                    destination = trash_dir / target.name
                    counter = 1
                    while destination.exists():
                        destination = trash_dir / f"{target.stem}-{counter}{target.suffix}"
                        counter += 1
                    shutil.move(str(target), str(destination))
                    removed.append(str(destination))
                else:
                    target.unlink()
                    removed.append(str(target))
    else:
        for group in preview:
            removed.extend(group.remove)

    return DedupeExecuteResponse(
        path=str(path),
        removed=removed,
        dry_run=request.dry_run,
        stats=stats,
    )
