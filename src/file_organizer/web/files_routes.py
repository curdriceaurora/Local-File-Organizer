"""Web UI routes for file browsing, preview, upload, and thumbnails."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
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
from file_organizer.web.file_operations import (
    build_breadcrumbs,
    build_file_results_context,
    collect_entries,
    list_tree_nodes,
)
from file_organizer.web.file_validators import (
    validate_file_not_exists,
    validate_file_size,
    validate_upload_filename,
    validate_upload_path,
)

files_router = APIRouter(tags=["web"])


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------


@files_router.get("/files", response_class=HTMLResponse)
def files_browser(
    request: Request,
    settings: ApiSettings = Depends(get_settings),
    path: str | None = Query(None),
    view: str = Query("grid", pattern="^(grid|list)$"),
    q: str | None = Query(None),
    file_type: str | None = Query(None, alias="type"),
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
    results = build_file_results_context(
        request,
        settings,
        path=path,
        view=view,
        query=q,
        file_type=file_type,
        sort_by=sort_by,
        sort_order=sort_order,
        limit=limit,
        page_size=PAGE_SIZE,
    )
    context.update(results)
    context["active_path"] = results.get("current_path", "")
    context["active_path_param"] = results.get("current_path_param", "")
    return templates.TemplateResponse(request, "files/browser.html", context)


@files_router.get("/files/list", response_class=HTMLResponse)
def files_list(
    request: Request,
    settings: ApiSettings = Depends(get_settings),
    path: str | None = Query(None),
    view: str = Query("grid", pattern="^(grid|list)$"),
    q: str | None = Query(None),
    file_type: str | None = Query(None, alias="type"),
    sort_by: str = Query("name", pattern="^(name|size|created|modified|type)$"),
    sort_order: str = Query("asc", pattern="^(asc|desc)$"),
    limit: int = Query(PAGE_SIZE, ge=1, le=500),
) -> HTMLResponse:
    """Return an HTMX partial with file-browser results (grid or list view).

    Returns:
        HTML fragment of the file results panel.
    """
    context = build_file_results_context(
        request,
        settings,
        path=path,
        view=view,
        query=q,
        file_type=file_type,
        sort_by=sort_by,
        sort_order=sort_order,
        limit=limit,
        page_size=PAGE_SIZE,
    )
    return templates.TemplateResponse(request, "files/_results.html", context)


@files_router.get("/files/tree", response_class=HTMLResponse)
def files_tree(
    request: Request,
    settings: ApiSettings = Depends(get_settings),
    path: str | None = Query(None),
    depth: int = Query(0, ge=0, le=MAX_NAV_DEPTH),
    active: str | None = Query(None),
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
            nodes = list_tree_nodes(current, include_hidden=False)
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
    info_message: str | None = None
    error_message: str | None = None
    errors: list[str] = []

    try:
        target_dir = resolve_selected_path(path or None, settings)
        if target_dir is None:
            raise ApiError(status_code=403, error="path_not_allowed", message="No upload path")
        validate_upload_path(target_dir)

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

            try:
                validate_upload_filename(upload.filename, allow_hidden=False)
            except ApiError as exc:
                errors.append(exc.message)
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
            try:
                validate_file_not_exists(destination, safe_name)
            except ApiError as exc:
                errors.append(exc.message)
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
                        try:
                            validate_file_size(total_bytes, MAX_UPLOAD_BYTES)
                        except ApiError:
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

    context = build_file_results_context(
        request,
        settings,
        path=path or None,
        view=view,
        query=q or None,
        file_type=file_type if file_type != "all" else None,
        sort_by=sort_by,
        sort_order=sort_order,
        limit=limit,
        page_size=PAGE_SIZE,
    )
    context["info_message"] = info_message
    context["error_message"] = error_message or context.get("error_message")
    return templates.TemplateResponse(request, "files/_results.html", context)
