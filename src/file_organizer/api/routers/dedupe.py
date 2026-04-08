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
from file_organizer.api.openapi_responses import (
    AUTH_401_RESPONSE,
    INTERNAL_500_RESPONSE,
    api_error_response,
    merge_responses,
    success_response,
    validation_error_response,
)
from file_organizer.api.utils import resolve_path
from file_organizer.services.deduplication import DuplicateDetector
from file_organizer.services.deduplication.detector import ScanOptions

router = APIRouter(
    tags=["dedupe"],
    dependencies=[Depends(get_current_active_user)],
    responses=merge_responses(AUTH_401_RESPONSE, INTERNAL_500_RESPONSE),
)


def _scan_duplicates(
    path: Path, request: DedupeScanRequest
) -> tuple[list[DedupeGroup], dict[str, int]]:
    """Run the duplicate detector against the given root and return grouped results."""
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
    """Build a preview response summarizing what a dedupe run would remove.

    Files are sorted by (modified time, path) so the oldest copy is always
    kept and newer duplicates are removed.  The path tie-breaker ensures
    stable selection when two files share an identical mtime.  This matches
    the CLI behaviour in dedupe_v2.py and is deterministic regardless of
    filesystem iteration order.
    """
    previews: list[DedupePreviewGroup] = []
    for group in groups:
        if not group.files:
            continue
        sorted_files = sorted(group.files, key=lambda f: (f.modified, f.path))
        keep = sorted_files[0].path
        remove = [file.path for file in sorted_files[1:]]
        previews.append(DedupePreviewGroup(hash_value=group.hash_value, keep=keep, remove=remove))
    return previews


@router.post(
    "/dedupe/scan",
    response_model=DedupeScanResponse,
    responses=merge_responses(
        success_response(
            "Scanned for duplicate files.",
            {"path": "/Users/demo/Documents", "duplicates": [], "stats": {"scanned_files": 12}},
        ),
        api_error_response(400, error="invalid_path", message="Path is not a directory"),
        api_error_response(404, error="not_found", message="Path not found"),
        validation_error_response(),
    ),
)
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


@router.post(
    "/dedupe/preview",
    response_model=DedupePreviewResponse,
    responses=merge_responses(
        success_response(
            "Prepared deduplication preview.",
            {"path": "/Users/demo/Documents", "preview": [], "stats": {"scanned_files": 12}},
        ),
        api_error_response(400, error="invalid_path", message="Path is not a directory"),
        api_error_response(404, error="not_found", message="Path not found"),
        validation_error_response(),
    ),
)
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


@router.post(
    "/dedupe/execute",
    response_model=DedupeExecuteResponse,
    responses=merge_responses(
        success_response(
            "Executed deduplication plan.",
            {
                "path": "/Users/demo/Documents",
                "removed": ["/Users/demo/.local/share/file-organizer/trash/report-copy.pdf"],
                "dry_run": False,
                "stats": {"scanned_files": 12},
            },
        ),
        api_error_response(400, error="invalid_path", message="Path is not a directory"),
        api_error_response(404, error="not_found", message="Path not found"),
        validation_error_response(),
    ),
)
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
                    from file_organizer.config.path_manager import get_data_dir

                    trash_dir = get_data_dir() / "trash"
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
