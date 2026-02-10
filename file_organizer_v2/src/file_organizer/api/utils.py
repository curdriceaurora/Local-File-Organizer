"""Shared helpers for API routers."""
from __future__ import annotations

import mimetypes
from datetime import datetime
from pathlib import Path

from file_organizer.api.exceptions import ApiError
from file_organizer.api.models import FileInfo


def resolve_path(path_value: str, allowed_paths: list[str] | None = None) -> Path:
    """Expand and normalize a filesystem path."""
    resolved = Path(path_value).expanduser().resolve(strict=False)
    if allowed_paths is None:
        return resolved

    roots = [Path(root).expanduser().resolve(strict=False) for root in allowed_paths]
    if not roots:
        raise ApiError(
            status_code=403,
            error="path_not_allowed",
            message="No allowed paths configured for this API instance.",
        )
    if not any(resolved == root or root in resolved.parents for root in roots):
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
    stat = path.stat()
    mime_type, _ = mimetypes.guess_type(path.as_posix())
    return FileInfo(
        path=str(path),
        name=path.name,
        size=stat.st_size,
        created=datetime.fromtimestamp(stat.st_ctime),
        modified=datetime.fromtimestamp(stat.st_mtime),
        file_type=path.suffix.lower() or "",
        mime_type=mime_type,
    )
