"""Directory listing helpers for the web file browser."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from file_organizer.api.utils import file_info_from_path, is_hidden
from file_organizer.utils.file_times import creation_timestamp
from file_organizer.web._helpers import (
    detect_kind,
    format_bytes,
    format_timestamp,
    has_children,
    parse_file_type_filter,
    path_id,
)


def normalized_extension(path: Path) -> str:
    """Return a normalized extension, preserving supported compound archives."""
    suffixes = [suffix.lower() for suffix in path.suffixes]
    if len(suffixes) >= 2:
        compound = "".join(suffixes[-2:])
        if compound in {".tar.gz", ".tar.bz2"}:
            return compound
    return suffixes[-1] if suffixes else ""


def list_tree_nodes(path: Path, include_hidden: bool) -> list[dict[str, Any]]:
    """List immediate child directories of *path* as sidebar tree nodes."""
    nodes: list[dict[str, Any]] = []
    try:
        entries = sorted(
            [p for p in path.iterdir() if p.is_dir()],
            key=lambda p: p.name.lower(),
        )
    except OSError:
        return nodes
    for entry in entries:
        if not include_hidden and is_hidden(entry):
            continue
        nodes.append(
            {
                "id": path_id(entry),
                "name": entry.name,
                "path": str(entry),
                "path_param": quote(str(entry)),
                "has_children": has_children(entry),
            }
        )
    return nodes


def collect_entries(
    path: Path,
    *,
    query: str | None,
    file_type: str | None,
    sort_by: str,
    sort_order: str,
    include_hidden: bool,
    limit: int,
) -> tuple[list[dict[str, Any]], int]:
    """Collect, filter, and sort directory entries for the file browser."""
    try:
        children = list(path.iterdir())
    except OSError:
        return [], 0

    query_token = query.lower() if query else None
    allowed_types = parse_file_type_filter(file_type)

    directories, files = _filter_children(
        children,
        query_token=query_token,
        include_hidden=include_hidden,
        allowed_types=allowed_types,
    )
    directories.sort(key=lambda p: p.name.lower(), reverse=sort_order == "desc")

    file_stats: dict[Path, os.stat_result | None] = {}
    if sort_by in {"size", "created", "modified"}:
        for entry in files:
            try:
                file_stats[entry] = entry.stat()
            except OSError:
                file_stats[entry] = None

    _sort_files(files, sort_by, sort_order, file_stats)

    total = len(directories) + len(files)
    if limit <= 0:
        return [], total

    dir_limit = min(limit, len(directories))
    remaining = max(limit - dir_limit, 0)

    entries: list[dict[str, Any]] = [_dir_entry(d) for d in directories[:dir_limit]]
    entries.extend(_file_entry(f) for f in files[:remaining])

    return entries, total


def _filter_children(
    children: list[Path],
    *,
    query_token: str | None,
    include_hidden: bool,
    allowed_types: set[str] | None,
) -> tuple[list[Path], list[Path]]:
    """Split and filter children into directories and files."""
    directories = [p for p in children if p.is_dir()]
    files = [p for p in children if p.is_file()]

    if not include_hidden:
        directories = [p for p in directories if not is_hidden(p)]
        files = [p for p in files if not is_hidden(p)]

    if query_token:
        directories = [p for p in directories if query_token in p.name.lower()]
        files = [p for p in files if query_token in p.name.lower()]

    if allowed_types is not None:
        files = [p for p in files if normalized_extension(p) in allowed_types]

    return directories, files


def _sort_files(
    files: list[Path],
    sort_by: str,
    sort_order: str,
    file_stats: dict[Path, os.stat_result | None],
) -> None:
    """Sort files in-place according to the requested column and order."""
    reverse = sort_order == "desc"

    if sort_by == "name":
        files.sort(key=lambda p: p.name.lower(), reverse=reverse)
    elif sort_by == "size":
        files.sort(key=lambda p: _file_size_sort_key(file_stats.get(p)), reverse=reverse)
    elif sort_by == "created":
        files.sort(key=lambda p: _creation_sort_key(file_stats.get(p)), reverse=reverse)
    elif sort_by == "type":
        files.sort(key=lambda p: normalized_extension(p), reverse=reverse)
    else:
        files.sort(key=lambda p: _modified_sort_key(file_stats.get(p)), reverse=reverse)


def _file_size_sort_key(stat: os.stat_result | None) -> int:
    """Return file size for sorting, defaulting missing stats to 0."""
    return stat.st_size if stat is not None else 0


def _modified_sort_key(stat: os.stat_result | None) -> float:
    """Return modified timestamp for sorting, defaulting missing stats to 0."""
    return stat.st_mtime if stat is not None else 0.0


def _creation_sort_key(s: os.stat_result | None) -> float:
    """Return a file creation timestamp for sorting, with platform fallbacks."""
    if s is None:
        return 0.0
    return creation_timestamp(s)


def _dir_entry(entry: Path) -> dict[str, Any]:
    """Build a directory entry dict for the file browser."""
    try:
        stat = entry.stat()
        modified = datetime.fromtimestamp(stat.st_mtime, tz=UTC)
    except OSError:
        modified = datetime.now(UTC)
    return {
        "name": entry.name,
        "path": str(entry),
        "path_param": quote(str(entry)),
        "is_dir": True,
        "kind": "folder",
        "size_display": "-",
        "modified_display": format_timestamp(modified),
        "thumbnail_url": None,
        "meta": "Folder",
    }


def _file_entry(entry: Path) -> dict[str, Any]:
    """Build a file entry dict for the file browser."""
    info = file_info_from_path(entry)
    kind = detect_kind(entry)
    thumbnail_url = None
    if kind in {"image", "pdf", "video"}:
        thumbnail_url = f"/ui/files/thumbnail?path={quote(info.path)}&kind={kind}"
    return {
        "name": info.name,
        "path": info.path,
        "path_param": quote(info.path),
        "is_dir": False,
        "kind": kind,
        "size_display": format_bytes(info.size),
        "modified_display": format_timestamp(info.modified),
        "thumbnail_url": thumbnail_url,
        "meta": f"{info.file_type or 'file'}",
    }
