"""Filesystem action helpers for copilot rules."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from file_organizer._compat import StrEnum
from file_organizer.utils.atomic_io import fsync_directory


class ConflictStrategy(StrEnum):
    """How rule actions handle an occupied destination path."""

    RENAME_NEW = "rename_new"
    SKIP = "skip"
    OVERWRITE = "overwrite"


@dataclass(frozen=True)
class LinkResult:
    """Result of creating a filesystem link."""

    source: Path
    destination: Path
    skipped: bool = False
    reason: str = ""


def resolve_conflict(path: Path, strategy: ConflictStrategy) -> Path | None:
    """Resolve an occupied destination path according to *strategy*."""
    if not path.exists() and not path.is_symlink():
        return path
    if strategy == ConflictStrategy.SKIP:
        return None
    if strategy == ConflictStrategy.OVERWRITE:
        if path.is_dir() and not path.is_symlink():
            raise IsADirectoryError(f"Cannot overwrite directory: {path}")
        path.unlink()
        return path

    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    counter = 1
    while True:
        candidate = parent / f"{stem}_{counter}{suffix}"
        if not candidate.exists() and not candidate.is_symlink():
            return candidate
        counter += 1


def copy_file(source: Path, destination: Path, strategy: ConflictStrategy) -> LinkResult:
    """Copy *source* to *destination* using the shared conflict strategy."""
    resolved = resolve_conflict(destination, strategy)
    if resolved is None:
        return LinkResult(source=source, destination=destination, skipped=True, reason="exists")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, resolved)
    fsync_directory(resolved)
    return LinkResult(source=source, destination=resolved)


def apply_hardlink(source: Path, destination: Path, strategy: ConflictStrategy) -> LinkResult:
    """Create a hardlink from *source* to *destination*."""
    resolved = resolve_conflict(destination, strategy)
    if resolved is None:
        return LinkResult(source=source, destination=destination, skipped=True, reason="exists")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    os.link(source, resolved)
    fsync_directory(resolved)
    return LinkResult(source=source, destination=resolved)


def apply_symlink(source: Path, destination: Path, strategy: ConflictStrategy) -> LinkResult:
    """Create a symlink from *destination* pointing at *source*."""
    resolved = resolve_conflict(destination, strategy)
    if resolved is None:
        return LinkResult(source=source, destination=destination, skipped=True, reason="exists")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.symlink_to(source)
    fsync_directory(resolved)
    return LinkResult(source=source, destination=resolved)
