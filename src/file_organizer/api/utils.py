"""Shared helpers for API routers."""

from __future__ import annotations

import mimetypes
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional

from file_organizer.api.exceptions import ApiError
from file_organizer.api.models import FileInfo


def resolve_path(path_value: str, allowed_paths: Optional[list[str]] = None) -> Path:
    """Expand and normalize a filesystem path, then enforce allowed-root policy.

    Uses ``Path.resolve()`` + ``Path.is_relative_to()`` to evaluate containment,
    which correctly handles symlinks, ``..`` sequences, and Windows drive-qualified
    paths — unlike a bare ``str.startswith`` or ``os.path.commonpath`` comparison.
    """
    # Path is validated against allowed roots below.
    resolved = Path(path_value).expanduser().resolve()  # codeql[py/path-injection]
    if not allowed_paths:
        raise ApiError(
            status_code=403,
            error="path_not_allowed",
            message="No allowed paths configured for this API instance.",
        )

    # Allowed roots are configuration-controlled.
    # codeql[py/path-injection]
    roots = [Path(root).expanduser().resolve() for root in allowed_paths]
    if not roots:
        raise ApiError(
            status_code=403,
            error="path_not_allowed",
            message="No allowed paths configured for this API instance.",
        )
    try:
        allowed = any(resolved == root or resolved.is_relative_to(root) for root in roots)
    except ValueError:
        allowed = False
    if not allowed:
        raise ApiError(
            status_code=403,
            error="path_not_allowed",
            message="Path is outside allowed roots.",
        )

    return resolved


def is_hidden(path: Path) -> bool:
    """Return True if any part of the path is hidden."""
    return any(part.startswith(".") for part in path.parts)


def file_info_from_path(path: Path) -> FileInfo:
    """Build FileInfo from a filesystem path, raising ApiError on failure."""
    try:
        stat = path.stat()
    except OSError as exc:
        if isinstance(exc, FileNotFoundError):
            raise ApiError(
                status_code=404,
                error="file_not_found",
                message=f"File not found: {path}",
            ) from exc
        if isinstance(exc, PermissionError):
            raise ApiError(
                status_code=403,
                error="file_access_error",
                message=f"Permission denied for {path}",
            ) from exc
        raise ApiError(
            status_code=500,
            error="file_access_error",
            message=f"Unable to access file metadata for {path}",
        ) from exc
    mime_type, _ = mimetypes.guess_type(path.as_posix())
    # Cross-platform creation time: st_birthtime (macOS), st_ctime (Windows),
    # st_mtime fallback (Linux — st_ctime is inode-change time, not creation).
    if hasattr(stat, "st_birthtime"):
        creation_ref = stat.st_birthtime
    elif os.name == "nt":
        creation_ref = stat.st_ctime
    else:
        creation_ref = stat.st_mtime
    return FileInfo(
        path=str(path),
        name=path.name,
        size=stat.st_size,
        created=datetime.fromtimestamp(creation_ref, tz=UTC),
        modified=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
        file_type=path.suffix.lower() or "",
        mime_type=mime_type,
    )
