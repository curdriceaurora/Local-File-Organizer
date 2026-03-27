"""Web UI routes for file browsing, preview, upload, and thumbnails."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_settings
from file_organizer.api.exceptions import ApiError
from file_organizer.api.utils import resolve_path
from file_organizer.web._helpers import (
    MAX_NAV_DEPTH,
    PAGE_SIZE,
    build_content_disposition,
    clamp_limit,
    normalize_sort_by,
    normalize_sort_order,
    normalize_view,
    resolve_selected_path,
    templates,
)
from file_organizer.web.file_operations import (
    build_file_results_context,
    build_preview_context,
    build_tree_context,
    generate_thumbnail,
    process_file_uploads,
)
from file_organizer.web.file_validators import validate_upload_path

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
    context = build_tree_context(path, settings, depth, active)
    context["request"] = request
    return templates.TemplateResponse(request, "files/_tree.html", context)


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
    data = generate_thumbnail(path, kind, settings)
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
    context = build_preview_context(path, settings)
    context["request"] = request
    return templates.TemplateResponse(request, "files/_preview.html", context)


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

        saved, errors = process_file_uploads(files, target_dir, allow_hidden=False)

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
