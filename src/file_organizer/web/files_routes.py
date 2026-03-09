"""Web UI routes for file browsing, preview, upload, and thumbnails."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote, unquote

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response
from PIL import Image, UnidentifiedImageError

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_settings
from file_organizer.api.exceptions import ApiError
from file_organizer.api.utils import file_info_from_path, is_hidden, resolve_path
from file_organizer.web._helpers import (
    MAX_NAV_DEPTH,
    MAX_THUMBNAIL_BYTES,
    MAX_UPLOAD_BYTES,
    PAGE_SIZE,
    TEXT_PREVIEW_CHARS,
    THUMBNAIL_SIZE,
    UPLOAD_CHUNK_SIZE,
    allowed_roots,
    build_content_disposition,
    clamp_limit,
    detect_kind,
    format_bytes,
    format_timestamp,
    has_children,
    is_probably_text,
    normalize_sort_by,
    normalize_sort_order,
    normalize_view,
    parse_file_type_filter,
    path_id,
    render_image_thumbnail,
    render_placeholder_thumbnail,
    resolve_selected_path,
    sanitize_upload_name,
    select_root_for_path,
    templates,
    validate_depth,
)

files_router = APIRouter(tags=["web"])


def _build_breadcrumbs(path: Path, roots: list[Path]) -> list[dict[str, str]]:
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


def _list_tree_nodes(path: Path, include_hidden: bool) -> list[dict[str, Any]]:
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


def _collect_entries(
    path: Path,
    *,
    query: Optional[str],
    file_type: Optional[str],
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

    file_stats: dict[Path, Optional[os.stat_result]] = {}
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


def _build_file_results_context(
    request: Request,
    settings: ApiSettings,
    *,
    path: Optional[str],
    view: str,
    query: Optional[str],
    file_type: Optional[str],
    sort_by: str,
    sort_order: str,
    limit: int,
) -> dict[str, Any]:
    """Assemble the full template context for file-browser result views.

    Returns:
        Dict suitable for passing directly to a Jinja template.
    """
    limit = clamp_limit(limit)
    roots = allowed_roots(settings)
    error_message: Optional[str] = None
    entries: list[dict[str, Any]] = []
    total = 0
    current_path: Optional[Path] = None

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
            entries, total = _collect_entries(
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
        breadcrumbs = _build_breadcrumbs(current_path, roots)

    view = view if view in {"grid", "list"} else "grid"
    next_limit = min(limit + PAGE_SIZE, total) if total else limit

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
        "page_size": PAGE_SIZE,
        "request": request,
    }


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------


@files_router.get("/files", response_class=HTMLResponse)
def files_browser(
    request: Request,
    settings: ApiSettings = Depends(get_settings),
    path: Optional[str] = Query(None),
    view: str = Query("grid", pattern="^(grid|list)$"),
    q: Optional[str] = Query(None),
    file_type: Optional[str] = Query(None, alias="type"),
    sort_by: str = Query("name", pattern="^(name|size|created|modified|type)$"),
    sort_order: str = Query("asc", pattern="^(asc|desc)$"),
    limit: int = Query(PAGE_SIZE, ge=1, le=500),
) -> HTMLResponse:
    """Render the full-page file browser with sidebar tree and file grid/list.

    Returns:
        Full HTML page for the file browser.
    """
    from file_organizer.web._helpers import base_context

    context = base_context(request, settings, active="files", title="Files")
    results = _build_file_results_context(
        request,
        settings,
        path=path,
        view=view,
        query=q,
        file_type=file_type,
        sort_by=sort_by,
        sort_order=sort_order,
        limit=limit,
    )
    context.update(results)
    context["active_path"] = results.get("current_path", "")
    context["active_path_param"] = results.get("current_path_param", "")
    return templates.TemplateResponse(request, "files/browser.html", context)


@files_router.get("/files/list", response_class=HTMLResponse)
def files_list(
    request: Request,
    settings: ApiSettings = Depends(get_settings),
    path: Optional[str] = Query(None),
    view: str = Query("grid", pattern="^(grid|list)$"),
    q: Optional[str] = Query(None),
    file_type: Optional[str] = Query(None, alias="type"),
    sort_by: str = Query("name", pattern="^(name|size|created|modified|type)$"),
    sort_order: str = Query("asc", pattern="^(asc|desc)$"),
    limit: int = Query(PAGE_SIZE, ge=1, le=500),
) -> HTMLResponse:
    """Return an HTMX partial with file-browser results (grid or list view).

    Returns:
        HTML fragment of the file results panel.
    """
    context = _build_file_results_context(
        request,
        settings,
        path=path,
        view=view,
        query=q,
        file_type=file_type,
        sort_by=sort_by,
        sort_order=sort_order,
        limit=limit,
    )
    return templates.TemplateResponse(request, "files/_results.html", context)


@files_router.get("/files/tree", response_class=HTMLResponse)
def files_tree(
    request: Request,
    settings: ApiSettings = Depends(get_settings),
    path: Optional[str] = Query(None),
    depth: int = Query(0, ge=0, le=MAX_NAV_DEPTH),
    active: Optional[str] = Query(None),
) -> HTMLResponse:
    """Return an HTMX partial with sidebar tree nodes for the given path.

    Args:
        request: Incoming FastAPI request.
        settings: Application settings with allowed paths.
        path: Directory to expand in the tree.
        depth: Current nesting depth for indentation.
        active: Currently selected path, used for highlighting.

    Returns:
        HTML fragment of tree nodes.
    """
    roots = allowed_roots(settings)
    active_path = unquote(active) if active else ""
    active_path_param = quote(active_path) if active_path else ""
    nodes: list[dict[str, Any]] = []

    if path:
        try:
            current = resolve_path(path, settings.allowed_paths)
            validate_depth(current, roots)
            nodes = _list_tree_nodes(current, include_hidden=False)
        except ApiError as exc:
            return templates.TemplateResponse(
                request,
                "files/_tree.html",
                {
                    "request": request,
                    "nodes": [],
                    "depth": depth,
                    "active_path": active_path,
                    "active_path_param": active_path_param,
                    "error_message": exc.message,
                },
            )
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

    error_message = None
    if not nodes and not path:
        error_message = "No allowed paths configured. Add FO_API_ALLOWED_PATHS."

    return templates.TemplateResponse(
        request,
        "files/_tree.html",
        {
            "request": request,
            "nodes": nodes,
            "depth": depth,
            "active_path": active_path,
            "active_path_param": active_path_param,
            "error_message": error_message,
        },
    )


@files_router.get("/files/thumbnail")
def files_thumbnail(
    settings: ApiSettings = Depends(get_settings),
    path: str = Query(...),
    kind: str = Query("file"),
) -> Response:
    """Generate a small PNG thumbnail for an image, PDF, or video file.

    Args:
        settings: Application settings with allowed paths.
        path: Absolute file path.
        kind: File kind hint (``image``, ``pdf``, ``video``, or ``file``).

    Returns:
        PNG image response.
    """
    target = resolve_path(path, settings.allowed_paths)
    if not target.exists() or not target.is_file():
        raise ApiError(status_code=404, error="not_found", message="File not found")

    if kind == "image":
        try:
            stat = target.stat()
        except OSError:
            data = render_placeholder_thumbnail("IMG", THUMBNAIL_SIZE)
        else:
            if stat.st_size > MAX_THUMBNAIL_BYTES:
                data = render_placeholder_thumbnail("IMG", THUMBNAIL_SIZE)
            else:
                try:
                    data = render_image_thumbnail(target)
                except (OSError, UnidentifiedImageError, Image.DecompressionBombError):
                    data = render_placeholder_thumbnail("IMG", THUMBNAIL_SIZE)
    elif kind == "pdf":
        data = render_placeholder_thumbnail("PDF", THUMBNAIL_SIZE)
    elif kind == "video":
        data = render_placeholder_thumbnail("VID", THUMBNAIL_SIZE)
    else:
        data = render_placeholder_thumbnail("FILE", THUMBNAIL_SIZE)

    return Response(content=data, media_type="image/png")


@files_router.get("/files/raw")
def files_raw(
    settings: ApiSettings = Depends(get_settings),
    path: str = Query(...),
    download: bool = Query(False),
) -> FileResponse:
    """Serve a raw file for inline viewing or as a download attachment.

    Args:
        settings: Application settings with allowed paths.
        path: Absolute file path.
        download: When true, set Content-Disposition to attachment.

    Returns:
        The raw file response.
    """
    target = resolve_path(path, settings.allowed_paths)
    if not target.exists() or not target.is_file():
        raise ApiError(status_code=404, error="not_found", message="File not found")
    headers = {"X-Content-Type-Options": "nosniff"}
    if download:
        headers["Content-Disposition"] = build_content_disposition(target.name)
    return FileResponse(target, headers=headers)


@files_router.get("/files/preview", response_class=HTMLResponse)
def files_preview(
    request: Request,
    settings: ApiSettings = Depends(get_settings),
    path: str = Query(...),
) -> HTMLResponse:
    """Return an HTMX partial with a file preview panel.

    Supports inline text preview, image thumbnails, and download links.

    Returns:
        HTML fragment for the preview sidebar.
    """
    error_message: Optional[str] = None
    preview_kind = "file"
    preview_text: Optional[str] = None
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

    return templates.TemplateResponse(
        request,
        "files/_preview.html",
        {
            "request": request,
            "info": info,
            "preview_kind": preview_kind,
            "preview_text": preview_text,
            "raw_url": raw_url,
            "download_url": download_url,
            "size_display": size_display,
            "modified_display": modified_display,
            "error_message": error_message,
        },
    )


@files_router.post("/files/upload", response_class=HTMLResponse)
def files_upload(
    request: Request,
    settings: ApiSettings = Depends(get_settings),
    path: str = Form(""),
    view: str = Form("grid"),
    q: str = Form(""),
    file_type: str = Form("all"),
    sort_by: str = Form("name"),
    sort_order: str = Form("asc"),
    limit: int = Form(PAGE_SIZE),
    files: list[UploadFile] = File(default=[]),
) -> HTMLResponse:
    """Handle multi-file upload to a target directory and refresh the listing.

    Returns:
        Updated file results HTML fragment with upload status messages.
    """
    info_message: Optional[str] = None
    error_message: Optional[str] = None
    errors: list[str] = []

    try:
        target_dir = resolve_selected_path(path or None, settings)
        if target_dir is None:
            raise ApiError(status_code=403, error="path_not_allowed", message="No upload path")
        if not target_dir.exists() or not target_dir.is_dir():
            raise ApiError(status_code=400, error="invalid_path", message="Invalid upload path")

        if not files:
            raise ApiError(status_code=400, error="missing_files", message="No files selected")

        view = normalize_view(view)
        sort_by = normalize_sort_by(sort_by)
        sort_order = normalize_sort_order(sort_order)
        limit = clamp_limit(limit)

        saved = 0
        for upload in files:
            if not upload.filename:
                continue
            raw_name = Path(upload.filename).name.strip()
            if raw_name.startswith("."):
                errors.append(f"Rejected {raw_name}: hidden files are not allowed.")
                if upload.file:
                    upload.file.close()
                continue
            safe_name = sanitize_upload_name(upload.filename)
            if safe_name is None:
                errors.append(f"Rejected {upload.filename}: invalid filename.")
                if upload.file:
                    upload.file.close()
                continue
            destination = target_dir / safe_name
            if destination.exists():
                errors.append(f"Skipped {safe_name}: file already exists.")
                if upload.file:
                    upload.file.close()
                continue

            total_bytes = 0
            try:
                with destination.open("wb") as handle:
                    while True:
                        chunk = upload.file.read(UPLOAD_CHUNK_SIZE)
                        if not chunk:
                            break
                        total_bytes += len(chunk)
                        if total_bytes > MAX_UPLOAD_BYTES:
                            raise ApiError(
                                status_code=400,
                                error="file_too_large",
                                message=f"{safe_name} exceeds upload size limit.",
                            )
                        handle.write(chunk)
            except ApiError as exc:
                if destination.exists():
                    destination.unlink(missing_ok=True)
                errors.append(exc.message)
                if upload.file:
                    upload.file.close()
                continue
            except OSError:
                if destination.exists():
                    destination.unlink(missing_ok=True)
                errors.append(f"Failed to save {safe_name}.")
                if upload.file:
                    upload.file.close()
                continue
            if upload.file:
                upload.file.close()
            saved += 1
        if saved:
            info_message = f"Uploaded {saved} file(s)."
        if errors:
            error_message = " ".join(errors)
    except ApiError as exc:
        error_message = exc.message

    context = _build_file_results_context(
        request,
        settings,
        path=path or None,
        view=view,
        query=q or None,
        file_type=file_type if file_type != "all" else None,
        sort_by=sort_by,
        sort_order=sort_order,
        limit=limit,
    )
    context["info_message"] = info_message
    context["error_message"] = error_message or context.get("error_message")
    return templates.TemplateResponse(request, "files/_results.html", context)
