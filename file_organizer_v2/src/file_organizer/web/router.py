"""Web UI routes and template rendering."""
from __future__ import annotations

import hashlib
import io
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote, unquote

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from PIL import Image, ImageDraw, UnidentifiedImageError

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_settings
from file_organizer.api.exceptions import ApiError
from file_organizer.api.utils import file_info_from_path, is_hidden, resolve_path
from file_organizer.core.organizer import FileOrganizer

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

router = APIRouter(tags=["web"])

_templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

_NAV_ITEMS = [
    ("Home", "/ui/"),
    ("Files", "/ui/files"),
    ("Organize", "/ui/organize"),
    ("Settings", "/ui/settings"),
    ("Profile", "/ui/profile"),
]

_PAGE_SIZE = 48
_THUMBNAIL_SIZE = (240, 160)
_MAX_LIMIT = 500
_MAX_NAV_DEPTH = 12
_MAX_UPLOAD_BYTES = 25 * 1024 * 1024
_UPLOAD_CHUNK_SIZE = 1024 * 1024
_MAX_THUMBNAIL_BYTES = 15 * 1024 * 1024
_TEXT_SAMPLE_BYTES = 8192
_TEXT_PREVIEW_CHARS = 4000
_INVALID_FILENAME_CHARS = set('<>:"/\\|?*')
_SAFE_FILENAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._()-]*$")
_ALLOWED_VIEWS = {"grid", "list"}
_ALLOWED_SORT_BY = {"name", "size", "created", "modified", "type"}
_ALLOWED_SORT_ORDER = {"asc", "desc"}
_FILENAME_FALLBACK_RE = re.compile(r"[^A-Za-z0-9._-]+")

_FILE_TYPE_GROUPS = {
    "image": FileOrganizer.IMAGE_EXTENSIONS,
    "video": FileOrganizer.VIDEO_EXTENSIONS,
    "audio": FileOrganizer.AUDIO_EXTENSIONS,
    "text": FileOrganizer.TEXT_EXTENSIONS,
    "cad": FileOrganizer.CAD_EXTENSIONS,
    "pdf": {".pdf"},
}


def _base_context(
    request: Request,
    settings: ApiSettings,
    *,
    active: str,
    title: str,
    extras: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    context: dict[str, Any] = {
        "request": request,
        "app_name": settings.app_name,
        "version": settings.version,
        "active": active,
        "page_title": title,
        "nav_items": _NAV_ITEMS,
        "year": datetime.now(timezone.utc).year,
    }
    if extras:
        context.update(extras)
    return context


def _allowed_roots(settings: ApiSettings) -> list[Path]:
    roots: list[Path] = []
    for root in settings.allowed_paths or []:
        try:
            resolved = resolve_path(root, settings.allowed_paths)
        except ApiError:
            continue
        if resolved not in roots:
            roots.append(resolved)
    return roots


def _resolve_selected_path(path_value: Optional[str], settings: ApiSettings) -> Optional[Path]:
    if path_value:
        return resolve_path(path_value, settings.allowed_paths)
    roots = _allowed_roots(settings)
    if roots:
        return roots[0]
    return None


def _format_bytes(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    units = ["KB", "MB", "GB", "TB"]
    size = float(size_bytes)
    for unit in units:
        size /= 1024.0
        if size < 1024.0:
            return f"{size:.1f} {unit}"
    return f"{size:.1f} PB"


def _format_timestamp(timestamp: datetime) -> str:
    return timestamp.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _parse_file_type_filter(file_type: Optional[str]) -> Optional[set[str]]:
    if not file_type or file_type == "all":
        return None
    token = file_type.lower()
    if token in _FILE_TYPE_GROUPS:
        return set(_FILE_TYPE_GROUPS[token])
    if token.startswith("."):
        return {token}
    return {f".{token}"}


def _detect_kind(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in _FILE_TYPE_GROUPS["image"]:
        return "image"
    if suffix == ".pdf":
        return "pdf"
    if suffix in _FILE_TYPE_GROUPS["video"]:
        return "video"
    if suffix in _FILE_TYPE_GROUPS["audio"]:
        return "audio"
    if suffix in _FILE_TYPE_GROUPS["text"]:
        return "text"
    if suffix in _FILE_TYPE_GROUPS["cad"]:
        return "cad"
    return "file"


def _path_id(path: Path) -> str:
    digest = hashlib.sha1(str(path).encode("utf-8")).hexdigest()
    return digest[:10]


def _build_breadcrumbs(path: Path, roots: list[Path]) -> list[dict[str, str]]:
    root_match = _select_root_for_path(path, roots)
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


def _has_children(path: Path) -> bool:
    try:
        for entry in path.iterdir():
            if entry.is_dir() and not is_hidden(entry):
                return True
    except OSError:
        return False
    return False


def _select_root_for_path(path: Path, roots: list[Path]) -> Path:
    root_match: Optional[Path] = None
    for root in roots:
        try:
            path.relative_to(root)
        except ValueError:
            continue
        if root_match is None or len(str(root)) > len(str(root_match)):
            root_match = root
    return root_match or path


def _validate_depth(path: Path, roots: list[Path]) -> None:
    root_match = _select_root_for_path(path, roots)
    try:
        depth = len(path.relative_to(root_match).parts)
    except ValueError:
        depth = 0
    if depth > _MAX_NAV_DEPTH:
        raise ApiError(
            status_code=400,
            error="path_too_deep",
            message="Selected path is too deep for the file browser.",
        )


def _is_probably_text(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            sample = handle.read(_TEXT_SAMPLE_BYTES)
    except OSError:
        return False
    if not sample:
        return True
    if b"\x00" in sample:
        return False
    try:
        sample.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def _sanitize_upload_name(name: str) -> Optional[str]:
    safe_name = Path(name).name.strip()
    if not safe_name or safe_name in {".", ".."}:
        return None
    if safe_name.startswith("."):
        return None
    if len(safe_name) > 255:
        return None
    if any(char in _INVALID_FILENAME_CHARS for char in safe_name):
        return None
    if not _SAFE_FILENAME_RE.match(safe_name):
        return None
    return safe_name


def _normalize_view(view: str) -> str:
    return view if view in _ALLOWED_VIEWS else "grid"


def _normalize_sort_by(sort_by: str) -> str:
    return sort_by if sort_by in _ALLOWED_SORT_BY else "name"


def _normalize_sort_order(sort_order: str) -> str:
    return sort_order if sort_order in _ALLOWED_SORT_ORDER else "asc"


def _clamp_limit(limit: int) -> int:
    return max(1, min(limit, _MAX_LIMIT))


def _build_content_disposition(filename: str) -> str:
    safe_name = filename.replace("\r", "").replace("\n", "").replace('"', "_")
    fallback = _FILENAME_FALLBACK_RE.sub("_", safe_name).strip("._")
    if not fallback:
        fallback = "download"
    encoded = quote(filename)
    return f'attachment; filename="{fallback}"; filename*=UTF-8\'\'{encoded}'


def _list_tree_nodes(path: Path, include_hidden: bool) -> list[dict[str, Any]]:
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
                "id": _path_id(entry),
                "name": entry.name,
                "path": str(entry),
                "path_param": quote(str(entry)),
                "has_children": _has_children(entry),
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
    entries: list[dict[str, Any]] = []
    try:
        children = list(path.iterdir())
    except OSError:
        return entries, 0

    query_token = query.lower() if query else None
    allowed_types = _parse_file_type_filter(file_type)

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
            key=lambda p: (file_stats.get(p).st_size if file_stats.get(p) is not None else 0),
            reverse=reverse,
        )
    elif sort_by == "created":
        files.sort(
            key=lambda p: (file_stats.get(p).st_ctime if file_stats.get(p) is not None else 0),
            reverse=reverse,
        )
    elif sort_by == "type":
        files.sort(key=lambda p: p.suffix.lower(), reverse=reverse)
    else:
        files.sort(
            key=lambda p: (file_stats.get(p).st_mtime if file_stats.get(p) is not None else 0),
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
            modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
        except OSError:
            modified = datetime.now(timezone.utc)
        entries.append(
            {
                "name": entry.name,
                "path": str(entry),
                "path_param": quote(str(entry)),
                "is_dir": True,
                "kind": "folder",
                "size_display": "-",
                "modified_display": _format_timestamp(modified),
                "thumbnail_url": None,
                "meta": "Folder",
            }
        )

    for entry in selected_files:
        info = file_info_from_path(entry)
        kind = _detect_kind(entry)
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
                "size_display": _format_bytes(info.size),
                "modified_display": _format_timestamp(info.modified),
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
    limit = _clamp_limit(limit)
    roots = _allowed_roots(settings)
    error_message: Optional[str] = None
    entries: list[dict[str, Any]] = []
    total = 0
    current_path: Optional[Path] = None

    try:
        current_path = _resolve_selected_path(path, settings)
    except ApiError as exc:
        error_message = exc.message

    if current_path is None:
        if error_message is None:
            error_message = "No allowed paths configured. Add FO_API_ALLOWED_PATHS."
    else:
        try:
            _validate_depth(current_path, roots)
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
    next_limit = min(limit + _PAGE_SIZE, total) if total else limit

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
        "page_size": _PAGE_SIZE,
        "request": request,
    }


def _render_placeholder_thumbnail(label: str, size: tuple[int, int]) -> bytes:
    background = Image.new("RGB", size, (235, 240, 245))
    draw = ImageDraw.Draw(background)
    text = label.upper()
    bbox = draw.textbbox((0, 0), text)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    draw.text(
        ((size[0] - text_width) / 2, (size[1] - text_height) / 2),
        text,
        fill=(80, 90, 110),
    )
    buffer = io.BytesIO()
    background.save(buffer, format="PNG")
    return buffer.getvalue()


def _render_image_thumbnail(path: Path) -> bytes:
    with Image.open(path) as image_file:
        image = image_file.convert("RGB")
        image.thumbnail(_THUMBNAIL_SIZE)
        canvas = Image.new("RGB", _THUMBNAIL_SIZE, (235, 240, 245))
        offset = (
            (_THUMBNAIL_SIZE[0] - image.width) // 2,
            (_THUMBNAIL_SIZE[1] - image.height) // 2,
        )
        canvas.paste(image, offset)
        buffer = io.BytesIO()
        canvas.save(buffer, format="PNG")
        return buffer.getvalue()


@router.get("/", response_class=HTMLResponse)
def home(request: Request, settings: ApiSettings = Depends(get_settings)) -> HTMLResponse:
    context = _base_context(request, settings, active="home", title="Home")
    return _templates.TemplateResponse("index.html", context)


@router.get("/files", response_class=HTMLResponse)
def files_browser(
    request: Request,
    settings: ApiSettings = Depends(get_settings),
    path: Optional[str] = Query(None),
    view: str = Query("grid", pattern="^(grid|list)$"),
    q: Optional[str] = Query(None),
    file_type: Optional[str] = Query(None, alias="type"),
    sort_by: str = Query("name", pattern="^(name|size|created|modified|type)$"),
    sort_order: str = Query("asc", pattern="^(asc|desc)$"),
    limit: int = Query(_PAGE_SIZE, ge=1, le=500),
) -> HTMLResponse:
    context = _base_context(request, settings, active="files", title="Files")
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
    return _templates.TemplateResponse("files/browser.html", context)


@router.get("/files/list", response_class=HTMLResponse)
def files_list(
    request: Request,
    settings: ApiSettings = Depends(get_settings),
    path: Optional[str] = Query(None),
    view: str = Query("grid", pattern="^(grid|list)$"),
    q: Optional[str] = Query(None),
    file_type: Optional[str] = Query(None, alias="type"),
    sort_by: str = Query("name", pattern="^(name|size|created|modified|type)$"),
    sort_order: str = Query("asc", pattern="^(asc|desc)$"),
    limit: int = Query(_PAGE_SIZE, ge=1, le=500),
) -> HTMLResponse:
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
    return _templates.TemplateResponse("files/_results.html", context)


@router.get("/files/tree", response_class=HTMLResponse)
def files_tree(
    request: Request,
    settings: ApiSettings = Depends(get_settings),
    path: Optional[str] = Query(None),
    depth: int = Query(0, ge=0, le=_MAX_NAV_DEPTH),
    active: Optional[str] = Query(None),
) -> HTMLResponse:
    roots = _allowed_roots(settings)
    active_path = unquote(active) if active else ""
    active_path_param = quote(active_path) if active_path else ""
    nodes: list[dict[str, Any]] = []

    if path:
        try:
            current = resolve_path(path, settings.allowed_paths)
            _validate_depth(current, roots)
            nodes = _list_tree_nodes(current, include_hidden=False)
        except ApiError as exc:
            return _templates.TemplateResponse(
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
                    "id": _path_id(root),
                    "name": root.name or root.as_posix(),
                    "path": str(root),
                    "path_param": quote(str(root)),
                    "has_children": _has_children(root),
                    "is_root": True,
                }
            )

    error_message = None
    if not nodes and not path:
        error_message = "No allowed paths configured. Add FO_API_ALLOWED_PATHS."

    return _templates.TemplateResponse(
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


@router.get("/files/thumbnail")
def files_thumbnail(
    settings: ApiSettings = Depends(get_settings),
    path: str = Query(...),
    kind: str = Query("file"),
) -> Response:
    target = resolve_path(path, settings.allowed_paths)
    if not target.exists() or not target.is_file():
        raise ApiError(status_code=404, error="not_found", message="File not found")

    if kind == "image":
        try:
            stat = target.stat()
        except OSError:
            data = _render_placeholder_thumbnail("IMG", _THUMBNAIL_SIZE)
        else:
            if stat.st_size > _MAX_THUMBNAIL_BYTES:
                data = _render_placeholder_thumbnail("IMG", _THUMBNAIL_SIZE)
            else:
                try:
                    data = _render_image_thumbnail(target)
                except (OSError, UnidentifiedImageError, Image.DecompressionBombError):
                    data = _render_placeholder_thumbnail("IMG", _THUMBNAIL_SIZE)
    elif kind == "pdf":
        data = _render_placeholder_thumbnail("PDF", _THUMBNAIL_SIZE)
    elif kind == "video":
        data = _render_placeholder_thumbnail("VID", _THUMBNAIL_SIZE)
    else:
        data = _render_placeholder_thumbnail("FILE", _THUMBNAIL_SIZE)

    return Response(content=data, media_type="image/png")


@router.get("/files/raw")
def files_raw(
    settings: ApiSettings = Depends(get_settings),
    path: str = Query(...),
    download: bool = Query(False),
) -> FileResponse:
    target = resolve_path(path, settings.allowed_paths)
    if not target.exists() or not target.is_file():
        raise ApiError(status_code=404, error="not_found", message="File not found")
    headers = {"X-Content-Type-Options": "nosniff"}
    if download:
        headers["Content-Disposition"] = _build_content_disposition(target.name)
    return FileResponse(target, headers=headers)


@router.get("/files/preview", response_class=HTMLResponse)
def files_preview(
    request: Request,
    settings: ApiSettings = Depends(get_settings),
    path: str = Query(...),
) -> HTMLResponse:
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
        preview_kind = _detect_kind(target)
        raw_url = f"/ui/files/raw?path={quote(info.path)}"
        download_url = f"/ui/files/raw?path={quote(info.path)}&download=1"
        size_display = _format_bytes(info.size)
        modified_display = _format_timestamp(info.modified)
        if preview_kind == "text" and _is_probably_text(target):
            try:
                preview_text = target.read_text(encoding="utf-8", errors="replace")[:_TEXT_PREVIEW_CHARS]
            except OSError:
                preview_text = "Preview not available."
        elif preview_kind == "text":
            preview_kind = "file"
    except ApiError as exc:
        error_message = exc.message

    return _templates.TemplateResponse(
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


@router.post("/files/upload", response_class=HTMLResponse)
def files_upload(
    request: Request,
    settings: ApiSettings = Depends(get_settings),
    path: str = Form(""),
    view: str = Form("grid"),
    q: str = Form(""),
    file_type: str = Form("all"),
    sort_by: str = Form("name"),
    sort_order: str = Form("asc"),
    limit: int = Form(_PAGE_SIZE),
    files: list[UploadFile] = File(default=[]),
) -> HTMLResponse:
    info_message: Optional[str] = None
    error_message: Optional[str] = None
    errors: list[str] = []

    try:
        target_dir = _resolve_selected_path(path or None, settings)
        if target_dir is None:
            raise ApiError(status_code=403, error="path_not_allowed", message="No upload path")
        if not target_dir.exists() or not target_dir.is_dir():
            raise ApiError(status_code=400, error="invalid_path", message="Invalid upload path")

        if not files:
            raise ApiError(status_code=400, error="missing_files", message="No files selected")

        view = _normalize_view(view)
        sort_by = _normalize_sort_by(sort_by)
        sort_order = _normalize_sort_order(sort_order)
        limit = _clamp_limit(limit)

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
            safe_name = _sanitize_upload_name(upload.filename)
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
                        chunk = upload.file.read(_UPLOAD_CHUNK_SIZE)
                        if not chunk:
                            break
                        total_bytes += len(chunk)
                        if total_bytes > _MAX_UPLOAD_BYTES:
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
    return _templates.TemplateResponse("files/_results.html", context)


@router.get("/organize", response_class=HTMLResponse)
def organize_dashboard(request: Request, settings: ApiSettings = Depends(get_settings)) -> HTMLResponse:
    context = _base_context(request, settings, active="organize", title="Organize")
    return _templates.TemplateResponse("organize/dashboard.html", context)


@router.get("/settings", response_class=HTMLResponse)
def settings(request: Request, settings_obj: ApiSettings = Depends(get_settings)) -> HTMLResponse:
    context = _base_context(request, settings_obj, active="settings", title="Settings")
    return _templates.TemplateResponse("settings/index.html", context)


@router.get("/profile", response_class=HTMLResponse)
def profile(request: Request, settings: ApiSettings = Depends(get_settings)) -> HTMLResponse:
    context = _base_context(request, settings, active="profile", title="Profile")
    return _templates.TemplateResponse("profile/index.html", context)
