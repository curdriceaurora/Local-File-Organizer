"""File operations for the web UI.

Handles file browsing, filtering, sorting, and tree navigation.
Extracted from ``files_routes.py`` to separate file operations logic
from route handling.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import Request

from file_organizer.api.config import ApiSettings
from file_organizer.api.exceptions import ApiError
from file_organizer.api.utils import file_info_from_path, is_hidden
from file_organizer.web._helpers import (
    clamp_limit,
    detect_kind,
    format_bytes,
    format_timestamp,
    has_children,
    parse_file_type_filter,
    path_id,
    resolve_selected_path,
    select_root_for_path,
    validate_depth,
)


def build_breadcrumbs(path: Path, roots: list[Path]) -> list[dict[str, str]]:
    """Build navigation breadcrumbs from *path* back to its closest allowed root.

    Args:
        path: Absolute directory path to create breadcrumbs for.
        roots: Allowed root directories.

    Returns:
        Ordered list of breadcrumb dicts with *label*, *path*, and *path_param*.
    """
    root_match = select_root_for_path(path, roots)
    crumbs: list[dict[str, str]] = []
    label = root_match.name or root_match.as_posix()
    crumbs.append(
        {
            "label": label,
            "path": str(root_match),
            "path_param": quote(str(root_match)),
        }
    )
    try:
        parts = path.relative_to(root_match).parts
    except ValueError:
        parts = ()
    current = root_match
    for part in parts:
        current = current / part
        crumbs.append(
            {
                "label": part,
                "path": str(current),
                "path_param": quote(str(current)),
            }
        )
    return crumbs


def list_tree_nodes(path: Path, include_hidden: bool) -> list[dict[str, Any]]:
    """List immediate child directories of *path* as sidebar tree nodes.

    Args:
        path: Directory to list children of.
        include_hidden: Whether to include hidden directories.

    Returns:
        List of node dicts suitable for the sidebar tree template.
    """
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
    """Collect, filter, and sort directory entries for the file browser.

    Args:
        path: Directory to scan.
        query: Optional name substring filter.
        file_type: Optional file-type filter (e.g. ``"image"``).
        sort_by: Column to sort by (``name``, ``size``, ``created``, etc.).
        sort_order: ``"asc"`` or ``"desc"``.
        include_hidden: Whether to include hidden entries.
        limit: Maximum number of entries to return.

    Returns:
        Tuple of ``(entries, total)`` where *entries* is the page slice.
    """
    entries: list[dict[str, Any]] = []
    try:
        children = list(path.iterdir())
    except OSError:
        return entries, 0

    query_token = query.lower() if query else None
    allowed_types = parse_file_type_filter(file_type)

    directories = [p for p in children if p.is_dir()]
    files = [p for p in children if p.is_file()]

    directories = [p for p in directories if include_hidden or not is_hidden(p)]
    files = [p for p in files if include_hidden or not is_hidden(p)]

    if query_token:
        directories = [p for p in directories if query_token in p.name.lower()]
        files = [p for p in files if query_token in p.name.lower()]

    if allowed_types is not None:
        files = [p for p in files if p.suffix.lower() in allowed_types]

    directories.sort(key=lambda p: p.name.lower())

    file_stats: dict[Path, os.stat_result | None] = {}
    if sort_by in {"size", "created", "modified"}:
        for entry in files:
            try:
                file_stats[entry] = entry.stat()
            except OSError:
                file_stats[entry] = None

    reverse = sort_order == "desc"
    if sort_by == "name":
        files.sort(key=lambda p: p.name.lower(), reverse=reverse)
    elif sort_by == "size":
        files.sort(
            key=lambda p: (s := file_stats.get(p)) and s.st_size or 0,
            reverse=reverse,
        )
    elif sort_by == "created":
        # Cross-platform: st_birthtime (macOS), st_ctime (Windows), st_mtime (Linux)
        def _creation_key(p: Path) -> float:
            """Get file creation timestamp with platform-specific fallbacks.

            Returns the file's creation timestamp when available. On platforms
            without st_birthtime support (e.g., Linux), falls back to the
            modification timestamp (st_mtime).

            Args:
                p: File path to get creation time for.

            Returns:
                Creation timestamp (or modification time as fallback), or 0.0
                if stat information is unavailable.
            """
            s = file_stats.get(p)
            if s is None:
                return 0.0
            if hasattr(s, "st_birthtime"):
                return s.st_birthtime
            if os.name == "nt":
                return s.st_ctime
            return s.st_mtime

        files.sort(key=_creation_key, reverse=reverse)
    elif sort_by == "type":
        files.sort(key=lambda p: p.suffix.lower(), reverse=reverse)
    else:
        files.sort(
            key=lambda p: (s := file_stats.get(p)) and s.st_mtime or 0,
            reverse=reverse,
        )

    total = len(directories) + len(files)
    if limit <= 0:
        return entries, total

    dir_limit = min(limit, len(directories))
    selected_dirs = directories[:dir_limit]
    remaining = max(limit - dir_limit, 0)
    selected_files = files[:remaining] if remaining else []

    for entry in selected_dirs:
        try:
            stat = entry.stat()
            modified = datetime.fromtimestamp(stat.st_mtime, tz=UTC)
        except OSError:
            modified = datetime.now(UTC)
        entries.append(
            {
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
        )

    for entry in selected_files:
        info = file_info_from_path(entry)
        kind = detect_kind(entry)
        thumbnail_url = None
        if kind in {"image", "pdf", "video"}:
            thumbnail_url = f"/ui/files/thumbnail?path={quote(info.path)}&kind={kind}"
        entries.append(
            {
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
        )

    return entries, total


def build_file_results_context(
    request: Request,
    settings: ApiSettings,
    *,
    path: str | None,
    view: str,
    query: str | None,
    file_type: str | None,
    sort_by: str,
    sort_order: str,
    limit: int,
    page_size: int,
) -> dict[str, Any]:
    """Assemble the full template context for file-browser result views.

    Args:
        request: FastAPI request object.
        settings: Application settings with allowed paths.
        path: Optional path to browse.
        view: View mode (``grid`` or ``list``).
        query: Optional search query.
        file_type: Optional file type filter.
        sort_by: Sort column name.
        sort_order: Sort direction (``asc`` or ``desc``).
        limit: Number of entries to show.
        page_size: Default page size for pagination.

    Returns:
        Dict suitable for passing directly to a Jinja template.
    """
    from file_organizer.web._helpers import allowed_roots

    limit = clamp_limit(limit)
    roots = allowed_roots(settings)
    error_message: str | None = None
    entries: list[dict[str, Any]] = []
    total = 0
    current_path: Path | None = None

    try:
        current_path = resolve_selected_path(path, settings)
    except ApiError as exc:
        error_message = exc.message

    if current_path is None:
        if error_message is None:
            error_message = "No allowed paths configured. Add FO_API_ALLOWED_PATHS."
    else:
        try:
            validate_depth(current_path, roots)
            entries, total = collect_entries(
                current_path,
                query=query,
                file_type=file_type,
                sort_by=sort_by,
                sort_order=sort_order,
                include_hidden=False,
                limit=limit,
            )
        except ApiError as exc:
            error_message = exc.message
            entries = []
            total = 0

    limit = max(1, min(limit, total)) if total else limit
    paged_entries = entries
    breadcrumbs: list[dict[str, str]] = []
    if current_path is not None:
        breadcrumbs = build_breadcrumbs(current_path, roots)

    view = view if view in {"grid", "list"} else "grid"
    next_limit = min(limit + page_size, total) if total else limit

    return {
        "current_path": str(current_path) if current_path else "",
        "current_path_param": quote(str(current_path)) if current_path else "",
        "breadcrumbs": breadcrumbs,
        "entries": paged_entries,
        "view": view,
        "query": query or "",
        "file_type": file_type or "all",
        "sort_by": sort_by,
        "sort_order": sort_order,
        "limit": limit,
        "next_limit": next_limit,
        "has_more": next_limit > limit,
        "error_message": error_message,
        "roots": [str(root) for root in roots],
        "page_size": page_size,
        "request": request,
    }
