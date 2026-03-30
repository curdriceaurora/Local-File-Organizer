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
from urllib.parse import quote, unquote

from fastapi import Request, UploadFile
from PIL import Image, UnidentifiedImageError

from file_organizer.api.config import ApiSettings
from file_organizer.api.exceptions import ApiError
from file_organizer.api.utils import file_info_from_path, is_hidden, resolve_path
from file_organizer.web._helpers import (
    MAX_THUMBNAIL_BYTES,
    MAX_UPLOAD_BYTES,
    TEXT_PREVIEW_CHARS,
    THUMBNAIL_SIZE,
    UPLOAD_CHUNK_SIZE,
    allowed_roots,
    clamp_limit,
    detect_kind,
    format_bytes,
    format_timestamp,
    has_children,
    is_probably_text,
    parse_file_type_filter,
    path_id,
    render_image_thumbnail,
    render_placeholder_thumbnail,
    resolve_selected_path,
    sanitize_upload_name,
    select_root_for_path,
    validate_depth,
)


def _normalized_extension(path: Path) -> str:
    """Return a normalized extension, preserving supported compound archives."""
    suffixes = [suffix.lower() for suffix in path.suffixes]
    if len(suffixes) >= 2:
        compound = "".join(suffixes[-2:])
        if compound in {".tar.gz", ".tar.bz2"}:
            return compound
    return suffixes[-1] if suffixes else ""


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
        files = [p for p in files if _normalized_extension(p) in allowed_types]

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
        files.sort(
            key=lambda p: s.st_size if (s := file_stats.get(p)) else 0,
            reverse=reverse,
        )
    elif sort_by == "created":
        files.sort(key=lambda p: _creation_sort_key(file_stats.get(p)), reverse=reverse)
    elif sort_by == "type":
        files.sort(key=lambda p: _normalized_extension(p), reverse=reverse)
    else:
        files.sort(
            key=lambda p: s.st_mtime if (s := file_stats.get(p)) else 0,
            reverse=reverse,
        )


def _creation_sort_key(s: os.stat_result | None) -> float:
    """Return a file creation timestamp for sorting, with platform fallbacks."""
    if s is None:
        return 0.0
    if hasattr(s, "st_birthtime"):
        return s.st_birthtime
    if os.name == "nt":
        return s.st_ctime
    return s.st_mtime


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
    directories.sort(key=lambda p: p.name.lower())

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

    if path:
        try:
            current = resolve_path(path, settings.allowed_paths)
            validate_depth(current, roots)
            nodes = list_tree_nodes(current, include_hidden=False)
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
                    "has_children": has_children(root),
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


def _save_upload(upload: UploadFile, target_dir: Path, allow_hidden: bool) -> str | None:
    """Validate and save a single upload file.

    Args:
        upload: The uploaded file.
        target_dir: Destination directory.
        allow_hidden: Whether hidden files are allowed.

    Returns:
        An error message string if the upload failed, empty string if skipped
        (no filename), or ``None`` on success.
    """
    from file_organizer.web.file_validators import (
        validate_file_not_exists,
        validate_upload_filename,
    )

    if not upload.filename:
        return ""  # skipped — no filename, not an error but not saved

    try:
        validate_upload_filename(upload.filename, allow_hidden=allow_hidden)
    except ApiError as exc:
        return exc.message

    safe_name = sanitize_upload_name(upload.filename)
    if safe_name is None:
        return f"Rejected {upload.filename}: invalid filename."

    destination = target_dir / safe_name
    try:
        validate_file_not_exists(destination, safe_name)
    except ApiError as exc:
        return exc.message

    try:
        _write_upload_chunks(upload, destination, safe_name)
    except ApiError as exc:
        destination.unlink(missing_ok=True)
        return exc.message
    except OSError:
        destination.unlink(missing_ok=True)
        return f"Failed to save {safe_name}."

    return None


def _write_upload_chunks(upload: UploadFile, destination: Path, safe_name: str) -> None:
    """Stream upload chunks to disk, enforcing size limit."""
    from file_organizer.web.file_validators import validate_file_size

    total_bytes = 0
    with destination.open("wb") as handle:
        while True:
            chunk = upload.file.read(UPLOAD_CHUNK_SIZE)
            if not chunk:
                break
            total_bytes += len(chunk)
            try:
                validate_file_size(total_bytes, MAX_UPLOAD_BYTES)
            except ApiError:
                raise ApiError(
                    status_code=400,
                    error="file_too_large",
                    message=f"{safe_name} exceeds upload size limit.",
                ) from None
            handle.write(chunk)


def process_file_uploads(
    files: list[UploadFile],
    target_dir: Path,
    allow_hidden: bool = False,
) -> tuple[int, list[str]]:
    """Process multiple file uploads to a target directory.

    Args:
        files: List of uploaded files to process.
        target_dir: Directory to save files to.
        allow_hidden: Whether to allow hidden files.

    Returns:
        Tuple of (saved_count, error_messages).
    """
    saved = 0
    errors: list[str] = []

    for upload in files:
        try:
            error = _save_upload(upload, target_dir, allow_hidden)
        finally:
            if upload.file:
                upload.file.close()

        if error is None:
            saved += 1
        elif upload.filename:
            errors.append(error)

    return saved, errors
