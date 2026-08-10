"""File operations for the web UI.

Handles file browsing, filtering, sorting, and tree navigation.
Extracted from ``files_routes.py`` to separate file operations logic
from route handling.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote

from fastapi import Request
from PIL import Image, UnidentifiedImageError

from file_organizer.api.config import ApiSettings
from file_organizer.api.exceptions import ApiError
from file_organizer.api.utils import file_info_from_path, resolve_path
from file_organizer.core.path_guard import TraversalBudget
from file_organizer.web._helpers import (
    MAX_DIRECTORY_ENTRIES,
    MAX_THUMBNAIL_BYTES,
    TEXT_PREVIEW_CHARS,
    THUMBNAIL_SIZE,
    allowed_roots,
    clamp_limit,
    detect_kind,
    format_bytes,
    format_timestamp,
    has_children,
    is_probably_text,
    path_id,
    render_image_thumbnail,
    render_placeholder_thumbnail,
    resolve_selected_path,
    select_root_for_path,
    validate_depth,
)
from file_organizer.web.file_listing import (
    _creation_sort_key,
    _dir_entry,
    _file_entry,
    _filter_children,
    _sort_files,
    collect_entries,
    list_tree_nodes,
)
from file_organizer.web.file_listing import (
    normalized_extension as _normalized_extension,
)
from file_organizer.web.file_uploads import (
    process_file_uploads,
)
from file_organizer.web.file_uploads import (
    save_upload as _save_upload,
)
from file_organizer.web.file_uploads import (
    write_upload_chunks as _write_upload_chunks,
)

__all__ = [
    "_creation_sort_key",
    "_dir_entry",
    "_file_entry",
    "_filter_children",
    "_normalized_extension",
    "_save_upload",
    "_sort_files",
    "_write_upload_chunks",
    "build_breadcrumbs",
    "build_file_results_context",
    "build_preview_context",
    "build_tree_context",
    "collect_entries",
    "generate_thumbnail",
    "list_tree_nodes",
    "process_file_uploads",
]


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
    listing_budget = TraversalBudget(limit=MAX_DIRECTORY_ENTRIES)

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
                budget=listing_budget,
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
        "listing_truncated": listing_budget.exhausted,
        "directory_entry_limit": f"{MAX_DIRECTORY_ENTRIES:,}",
        "roots": [str(root) for root in roots],
        "page_size": page_size,
        "request": request,
    }


def build_tree_context(
    path: str | None,
    settings: ApiSettings,
    depth: int,
    active: str | None,
) -> dict[str, Any]:
    """Build context for sidebar tree nodes.

    Args:
        path: Directory to expand in the tree (None for roots).
        settings: Application settings with allowed paths.
        depth: Current nesting depth for indentation.
        active: Currently selected path for highlighting.

    Returns:
        Dict with nodes, depth, active_path, active_path_param, and error_message.
    """
    roots = allowed_roots(settings)
    active_path = unquote(active) if active else ""
    active_path_param = quote(active_path) if active_path else ""
    nodes: list[dict[str, Any]] = []
    error_message: str | None = None
    tree_budget = TraversalBudget(limit=MAX_DIRECTORY_ENTRIES)

    if path:
        try:
            current = resolve_path(path, settings.allowed_paths)
            validate_depth(current, roots)
            nodes = list_tree_nodes(current, include_hidden=False, budget=tree_budget)
        except ApiError as exc:
            error_message = exc.message
    else:
        for root in roots:
            nodes.append(
                {
                    "id": path_id(root),
                    "name": root.name or root.as_posix(),
                    "path": str(root),
                    "path_param": quote(str(root)),
                    "has_children": has_children(root, budget=tree_budget),
                    "is_root": True,
                }
            )

    if not nodes and not path:
        error_message = "No allowed paths configured. Add FO_API_ALLOWED_PATHS."

    return {
        "nodes": nodes,
        "depth": depth,
        "active_path": active_path,
        "active_path_param": active_path_param,
        "error_message": error_message,
        "tree_truncated": tree_budget.exhausted,
        "directory_entry_limit": f"{MAX_DIRECTORY_ENTRIES:,}",
    }


def generate_thumbnail(path: str, kind: str, settings: ApiSettings) -> bytes:
    """Generate a thumbnail image for a file.

    Args:
        path: Absolute file path.
        kind: File kind hint (``image``, ``pdf``, ``video``, or ``file``).
        settings: Application settings with allowed paths.

    Returns:
        PNG image bytes.

    Raises:
        ApiError: If the file is not found.
    """
    target = resolve_path(path, settings.allowed_paths)
    if not target.exists() or not target.is_file():
        raise ApiError(status_code=404, error="not_found", message="File not found")

    if kind == "image":
        try:
            stat = target.stat()
        except OSError:
            return render_placeholder_thumbnail("IMG", THUMBNAIL_SIZE)

        if stat.st_size > MAX_THUMBNAIL_BYTES:
            return render_placeholder_thumbnail("IMG", THUMBNAIL_SIZE)

        try:
            return render_image_thumbnail(target)
        except (OSError, UnidentifiedImageError, Image.DecompressionBombError):
            return render_placeholder_thumbnail("IMG", THUMBNAIL_SIZE)
    elif kind == "pdf":
        return render_placeholder_thumbnail("PDF", THUMBNAIL_SIZE)
    elif kind == "video":
        return render_placeholder_thumbnail("VID", THUMBNAIL_SIZE)
    else:
        return render_placeholder_thumbnail("FILE", THUMBNAIL_SIZE)


def build_preview_context(path: str, settings: ApiSettings) -> dict[str, Any]:
    """Build context for file preview panel.

    Args:
        path: Absolute file path to preview.
        settings: Application settings with allowed paths.

    Returns:
        Dict with preview information including kind, text, URLs, and metadata.
    """
    error_message: str | None = None
    preview_kind = "file"
    preview_text: str | None = None
    download_url = ""
    raw_url = ""
    size_display = ""
    modified_display = ""
    info = None

    try:
        target = resolve_path(path, settings.allowed_paths)
        if not target.exists() or not target.is_file():
            raise ApiError(status_code=404, error="not_found", message="File not found")

        info = file_info_from_path(target)
        preview_kind = detect_kind(target)
        raw_url = f"/ui/files/raw?path={quote(info.path)}"
        download_url = f"/ui/files/raw?path={quote(info.path)}&download=1"
        size_display = format_bytes(info.size)
        modified_display = format_timestamp(info.modified)

        if preview_kind == "text" and is_probably_text(target):
            try:
                preview_text = target.read_text(encoding="utf-8", errors="replace")[
                    :TEXT_PREVIEW_CHARS
                ]
            except OSError:
                preview_text = "Preview not available."
        elif preview_kind == "text":
            preview_kind = "file"
    except ApiError as exc:
        error_message = exc.message

    return {
        "info": info,
        "preview_kind": preview_kind,
        "preview_text": preview_text,
        "raw_url": raw_url,
        "download_url": download_url,
        "size_display": size_display,
        "modified_display": modified_display,
        "error_message": error_message,
    }
