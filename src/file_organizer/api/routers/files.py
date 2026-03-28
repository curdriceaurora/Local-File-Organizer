"""File operation endpoints."""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_current_active_user, get_settings
from file_organizer.api.exceptions import ApiError
from file_organizer.api.models import (
    DeleteFileRequest,
    DeleteFileResponse,
    FileContentResponse,
    FileInfo,
    FileListResponse,
    MoveFileRequest,
    MoveFileResponse,
)
from file_organizer.api.utils import file_info_from_path, is_hidden, resolve_path
from file_organizer.core.organizer import FileOrganizer

logger = logging.getLogger(__name__)

router = APIRouter(tags=["files"], dependencies=[Depends(get_current_active_user)])

_FILE_TYPE_GROUPS = {
    "text": FileOrganizer.TEXT_EXTENSIONS,
    "image": FileOrganizer.IMAGE_EXTENSIONS,
    "video": FileOrganizer.VIDEO_EXTENSIONS,
    "audio": FileOrganizer.AUDIO_EXTENSIONS,
    "cad": FileOrganizer.CAD_EXTENSIONS,
}


def _parse_file_types(file_type: str | None) -> set[str] | None:
    if not file_type:
        return None
    types: set[str] = set()
    for part in file_type.split(","):
        token = part.strip().lower()
        if not token:
            continue
        if token in _FILE_TYPE_GROUPS:
            types.update(_FILE_TYPE_GROUPS[token])
        else:
            ext = token if token.startswith(".") else f".{token}"
            types.add(ext)
    return types or None


def _collect_files(path: Path, recursive: bool, include_hidden: bool) -> list[Path]:
    files: list[Path] = []
    if path.is_file():
        if include_hidden or not is_hidden(path):
            files.append(path)
        return files

    if recursive:
        iterator = path.rglob("*")
    else:
        iterator = path.glob("*")

    for entry in iterator:
        try:
            if entry.is_symlink():
                continue
            if not entry.is_file():
                continue
            if not include_hidden and is_hidden(entry):
                continue
        except (OSError, PermissionError):
            logger.debug("Skipping entry %s: filesystem error", entry, exc_info=True)
            continue
        files.append(entry)
    return files


@router.get("/files", response_model=FileListResponse)
def list_files(
    path: str = Query(None, description="Directory or file path"),
    recursive: bool = Query(False),
    include_hidden: bool = Query(False),
    file_type: str | None = Query(None, description="Comma-separated extensions or groups"),
    sort_by: str = Query("name", pattern="^(name|size|created|modified)$"),
    sort_order: str = Query("asc", pattern="^(asc|desc)$"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    settings: ApiSettings = Depends(get_settings),
) -> FileListResponse:
    """List files in a directory with optional filtering and sorting."""
    # Use home directory if path not provided
    if path is None:
        path = str(Path.home())
    target = resolve_path(path, settings.allowed_paths)
    if not target.exists():
        raise ApiError(status_code=404, error="not_found", message="Path does not exist")

    allowed_types = _parse_file_types(file_type)
    files = _collect_files(target, recursive, include_hidden)
    if allowed_types is not None:
        files = [f for f in files if f.suffix.lower() in allowed_types]

    reverse = sort_order == "desc"
    if sort_by == "name":
        files.sort(key=lambda p: p.name.lower(), reverse=reverse)
    elif sort_by == "size":
        files.sort(key=lambda p: p.stat().st_size, reverse=reverse)
    elif sort_by == "created":
        # Cross-platform: st_birthtime (macOS), st_ctime (Windows), st_mtime (Linux)
        def _creation_key(p: Path) -> float:
            s = p.stat()
            if hasattr(s, "st_birthtime"):
                return s.st_birthtime
            if os.name == "nt":
                return s.st_ctime
            return s.st_mtime

        files.sort(key=_creation_key, reverse=reverse)
    else:
        files.sort(key=lambda p: p.stat().st_mtime, reverse=reverse)

    total = len(files)
    paged = files[skip : skip + limit]
    items = [file_info_from_path(f) for f in paged]

    return FileListResponse(items=items, total=total, skip=skip, limit=limit)


@router.get("/files/info", response_model=FileInfo)
def get_file_info(
    path: str = Query(...),
    settings: ApiSettings = Depends(get_settings),
) -> FileInfo:
    """Return metadata for a single file."""
    target = resolve_path(path, settings.allowed_paths)
    if not target.exists():
        raise ApiError(status_code=404, error="not_found", message="File not found")
    if not target.is_file():
        raise ApiError(status_code=400, error="invalid_path", message="Path is not a file")
    return file_info_from_path(target)


@router.get("/files/content", response_model=FileContentResponse)
def read_file_content(
    path: str = Query(...),
    max_bytes: int = Query(200_000, ge=1, le=5_000_000),
    encoding: str = Query("utf-8"),
    settings: ApiSettings = Depends(get_settings),
) -> FileContentResponse:
    """Return the text content of a file, optionally truncated."""
    target = resolve_path(path, settings.allowed_paths)
    if not target.exists():
        raise ApiError(status_code=404, error="not_found", message="File not found")
    if not target.is_file():
        raise ApiError(status_code=400, error="invalid_path", message="Path is not a file")

    with target.open("rb") as handle:
        data = handle.read(max_bytes + 1)
    truncated = len(data) > max_bytes
    if truncated:
        data = data[:max_bytes]

    content = data.decode(encoding, errors="replace")
    info = file_info_from_path(target)
    return FileContentResponse(
        path=info.path,
        content=content,
        encoding=encoding,
        truncated=truncated,
        size=info.size,
        mime_type=info.mime_type,
    )


@router.get("/files/{file_id}")
def get_file_by_id(
    file_id: str,
    settings: ApiSettings = Depends(get_settings),
) -> FileInfo:
    """Get file details by ID."""
    if not file_id or file_id.strip() == "":
        raise ApiError(status_code=422, error="invalid_id", message="File ID cannot be empty")
    # Validate file_id has no path traversal characters (defense-in-depth)
    if any(sep in file_id for sep in ("/", "\\")) or ".." in file_id:
        raise ApiError(status_code=400, error="invalid_id", message="File ID has an invalid format")
    # Simple mock: treat file_id as a path or name
    # In a real implementation, this would look up the file by ID
    target = resolve_path(file_id, settings.allowed_paths)
    if not target.exists():
        raise ApiError(status_code=404, error="not_found", message="File not found")
    return file_info_from_path(target)


@router.post("/files/move", response_model=MoveFileResponse)
def move_file(
    request: MoveFileRequest,
    settings: ApiSettings = Depends(get_settings),
) -> MoveFileResponse:
    """Move or rename a file."""
    source = resolve_path(request.source, settings.allowed_paths)
    destination = resolve_path(request.destination, settings.allowed_paths)

    if not source.exists():
        raise ApiError(status_code=404, error="not_found", message="Source not found")

    if destination.exists() and not request.overwrite:
        raise ApiError(status_code=409, error="conflict", message="Destination exists")

    if request.dry_run:
        return MoveFileResponse(
            source=str(source),
            destination=str(destination),
            moved=False,
            dry_run=True,
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and request.overwrite:
        if destination.is_dir() and not request.allow_directory_overwrite:
            raise ApiError(
                status_code=400,
                error="invalid_request",
                message="Directory overwrite requires allow_directory_overwrite=true.",
            )
        if destination.is_dir():
            shutil.rmtree(destination)
        else:
            destination.unlink()

    shutil.move(str(source), str(destination))
    return MoveFileResponse(
        source=str(source),
        destination=str(destination),
        moved=True,
        dry_run=False,
    )


def _trash_target(path: Path) -> Path:
    from file_organizer.config.path_manager import get_data_dir

    trash_dir = get_data_dir() / "trash"
    trash_dir.mkdir(parents=True, exist_ok=True)
    candidate = trash_dir / path.name
    if not candidate.exists():
        return candidate
    stem = path.stem
    suffix = path.suffix
    for counter in range(1, 1001):
        candidate = trash_dir / f"{stem}-{counter}{suffix}"
        if not candidate.exists():
            return candidate
    return trash_dir / f"{stem}-{uuid4().hex}{suffix}"


@router.delete("/files", response_model=DeleteFileResponse)
def delete_file(
    request: DeleteFileRequest,
    settings: ApiSettings = Depends(get_settings),
) -> DeleteFileResponse:
    """Delete or trash a file."""
    target = resolve_path(request.path, settings.allowed_paths)
    if not target.exists():
        raise ApiError(status_code=404, error="not_found", message="File not found")

    if request.dry_run:
        return DeleteFileResponse(path=str(target), deleted=False, dry_run=True)

    trashed_path: str | None = None
    if request.permanent:
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
    else:
        destination = _trash_target(target)
        shutil.move(str(target), str(destination))
        trashed_path = str(destination)

    return DeleteFileResponse(
        path=str(target),
        deleted=True,
        dry_run=False,
        trashed_path=trashed_path,
    )


@router.delete("/files/{file_id}", response_model=DeleteFileResponse)
def delete_file_by_id(
    file_id: str,
    permanent: bool = Query(False),
    settings: ApiSettings = Depends(get_settings),
) -> DeleteFileResponse:
    """Delete a file by ID."""
    if not file_id or file_id.strip() == "":
        raise ApiError(status_code=422, error="invalid_id", message="File ID cannot be empty")
    # Validate file_id has no path traversal characters (defense-in-depth)
    if any(sep in file_id for sep in ("/", "\\")) or ".." in file_id:
        raise ApiError(status_code=400, error="invalid_id", message="File ID has an invalid format")

    # Simple mock: treat file_id as a path (validated against allowed paths)
    target = resolve_path(file_id, settings.allowed_paths)
    if not target.exists():
        raise ApiError(status_code=404, error="not_found", message="File not found")

    trashed_path: str | None = None
    if permanent:
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
    else:
        destination = _trash_target(target)
        shutil.move(str(target), str(destination))
        trashed_path = str(destination)

    return DeleteFileResponse(
        path=str(target),
        deleted=True,
        dry_run=False,
        trashed_path=trashed_path,
    )


class FileUploadResponse(BaseModel):
    """Response from file upload endpoint."""

    file_id: str
    filename: str
    size: int


@router.post("/files/upload", response_model=None)
async def upload_files(
    files: list[UploadFile] | None = File(None),
    file: UploadFile | None = File(None),
) -> FileUploadResponse | list[FileUploadResponse] | JSONResponse:
    """Upload one or more files.

    Accepts either a single file or multiple files.
    """
    # Handle both single file and multiple files
    if files:
        # Multiple files
        upload_list = files
    elif file:
        # Single file
        upload_list = [file]
    else:
        return JSONResponse(
            status_code=400,
            content={"detail": "At least one file must be provided"},
        )

    responses = []
    for uploaded_file in upload_list:
        content = await uploaded_file.read()
        response = FileUploadResponse(
            file_id=str(uuid4()),
            filename=uploaded_file.filename or "unknown",
            size=len(content),
        )
        responses.append(response)

    # Return single response if only one file, list if multiple
    if len(responses) == 1:
        return responses[0]
    return responses
