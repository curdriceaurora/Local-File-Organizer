"""Shared helpers for API routers."""
from __future__ import annotations

import mimetypes
import os
from datetime import datetime, timezone
from pathlib import Path

from file_organizer.api.exceptions import ApiError
from file_organizer.api.models import FileInfo


def resolve_path(path_value: str, allowed_paths: list[str] | None = None) -> Path:
    """Expand and normalize a filesystem path."""
    resolved = Path(path_value).expanduser()
    resolved_str = os.path.realpath(resolved)
    if allowed_paths is None:
        return Path(resolved_str)

    roots = [os.path.realpath(Path(root).expanduser()) for root in allowed_paths]
    if not roots:
        raise ApiError(
            status_code=403,
            error="path_not_allowed",
            message="No allowed paths configured for this API instance.",
        )
    try:
        allowed = any(os.path.commonpath([resolved_str, root]) == root for root in roots)
    except ValueError:
        allowed = False
    if not allowed:
        raise ApiError(
            status_code=403,
            error="path_not_allowed",
            message="Path is outside allowed roots.",
        )

    return Path(resolved_str)


def is_hidden(path: Path) -> bool:
    """Return True if any part of the path is hidden."""
    return any(part.startswith(".") for part in path.parts)


def file_info_from_path(path: Path) -> FileInfo:
    try:
        stat = path.stat()
    except (OSError, PermissionError) as exc:
        raise ApiError(
            status_code=403,
            error="file_access_error",
            message=f"Unable to access file metadata for {path}",
        ) from exc
    mime_type, _ = mimetypes.guess_type(path.as_posix())
    return FileInfo(
        path=str(path),
        name=path.name,
        size=stat.st_size,
        created=datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc),
        modified=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
        file_type=path.suffix.lower() or "",
        mime_type=mime_type,
    )
