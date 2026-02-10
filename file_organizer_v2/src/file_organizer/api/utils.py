"""Shared helpers for API routers."""
from __future__ import annotations

import mimetypes
from datetime import datetime
from pathlib import Path

from file_organizer.api.models import FileInfo


def resolve_path(path_value: str) -> Path:
    """Expand and normalize a filesystem path."""
    return Path(path_value).expanduser()


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
