"""Web UI routes and template rendering."""
from __future__ import annotations

import asyncio
import csv
import hashlib
import io
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock, Timer
from time import monotonic
from typing import Any, Optional
from urllib.parse import quote, unquote
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.templating import Jinja2Templates
from loguru import logger
from PIL import Image, ImageDraw, UnidentifiedImageError

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_settings
from file_organizer.api.exceptions import ApiError
from file_organizer.api.jobs import create_job, get_job, list_jobs, update_job
from file_organizer.api.models import OrganizationError, OrganizationResultResponse, OrganizeRequest
from file_organizer.api.utils import file_info_from_path, is_hidden, resolve_path
from file_organizer.core.organizer import FileOrganizer, OrganizationResult

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
_TRUE_VALUES = {"1", "true", "yes", "on"}
_ORGANIZE_DEFAULT_DELAY_MIN = 0
_ORGANIZE_MAX_DELAY_MIN = 7 * 24 * 60
_ORGANIZE_EVENT_POLL_SECONDS = 1
_ORGANIZE_HISTORY_LIMIT = 50
_ORGANIZE_PLAN_LIMIT = 200
_ORGANIZE_JOB_TYPE = "organize_web"
_JOB_METADATA_PRUNE_THRESHOLD = 256
_JOB_METADATA_PRUNE_INTERVAL_SECONDS = 60.0
_ORGANIZE_METHODOLOGIES = {
    "johnny_decimal": "Johnny Decimal",
    "para": "PARA",
    "content_based": "Content-Based",
    "date_based": "Date-Based",
}

_FILE_TYPE_GROUPS = {
    "image": FileOrganizer.IMAGE_EXTENSIONS,
    "video": FileOrganizer.VIDEO_EXTENSIONS,
    "audio": FileOrganizer.AUDIO_EXTENSIONS,
    "text": FileOrganizer.TEXT_EXTENSIONS,
    "cad": FileOrganizer.CAD_EXTENSIONS,
    "pdf": {".pdf"},
}

_ORGANIZE_PLAN_STORE: dict[str, dict[str, Any]] = {}
_ORGANIZE_PLAN_LOCK = Lock()
_SCHEDULED_TIMERS: dict[str, Timer] = {}
_SCHEDULED_TIMERS_LOCK = Lock()
_JOB_METADATA: dict[str, dict[str, Any]] = {}
_JOB_METADATA_LOCK = Lock()
_LAST_JOB_METADATA_PRUNE_MONOTONIC = 0.0


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


def _as_bool(value: Optional[str]) -> bool:
    if value is None:
        return False
    return value.strip().lower() in _TRUE_VALUES


def _parse_delay_minutes(value: Optional[str]) -> int:
    if value is None or value.strip() == "":
        return _ORGANIZE_DEFAULT_DELAY_MIN
    try:
        minutes = int(value)
    except ValueError as exc:
        raise ApiError(
            status_code=400,
            error="invalid_schedule_delay",
            message="Schedule delay must be a whole number of minutes.",
        ) from exc
    if minutes < 0 or minutes > _ORGANIZE_MAX_DELAY_MIN:
        raise ApiError(
            status_code=400,
            error="invalid_schedule_delay",
            message=f"Schedule delay must be between 0 and {_ORGANIZE_MAX_DELAY_MIN} minutes.",
        )
    return minutes


def _normalize_methodology(value: Optional[str]) -> str:
    token = (value or "").strip().lower()
    if token in _ORGANIZE_METHODOLOGIES:
        return token
    return "content_based"


def _scan_directory(path: Path, recursive: bool, include_hidden: bool) -> list[Path]:
    files: list[Path] = []
    if path.is_file():
        if include_hidden or not is_hidden(path):
            files.append(path)
        return files

    iterator = path.rglob("*") if recursive else path.glob("*")
    for entry in iterator:
        if not entry.is_file():
            continue
        if not include_hidden and is_hidden(entry):
            continue
        files.append(entry)
    return files


def _counts_by_type(files: list[Path]) -> dict[str, int]:
    counts = {
        "text": 0,
        "image": 0,
        "video": 0,
        "audio": 0,
        "cad": 0,
        "other": 0,
    }
    for path in files:
        suffix = path.suffix.lower()
        if suffix in FileOrganizer.TEXT_EXTENSIONS:
            counts["text"] += 1
        elif suffix in FileOrganizer.IMAGE_EXTENSIONS:
            counts["image"] += 1
        elif suffix in FileOrganizer.VIDEO_EXTENSIONS:
            counts["video"] += 1
        elif suffix in FileOrganizer.AUDIO_EXTENSIONS:
            counts["audio"] += 1
        elif suffix in FileOrganizer.CAD_EXTENSIONS:
            counts["cad"] += 1
        else:
            counts["other"] += 1
    return counts


def _result_to_response(result: OrganizationResult) -> OrganizationResultResponse:
    return OrganizationResultResponse(
        total_files=result.total_files,
        processed_files=result.processed_files,
        skipped_files=result.skipped_files,
        failed_files=result.failed_files,
        processing_time=result.processing_time,
        organized_structure=result.organized_structure,
        errors=[OrganizationError(file=file_name, error=error) for file_name, error in result.errors],
    )


def _build_plan_movements(
    files: list[Path],
    output_dir: Path,
    preview: OrganizationResultResponse,
) -> list[dict[str, str]]:
    source_lookup: dict[str, list[str]] = {}
    for file_path in sorted(files, key=lambda item: item.as_posix().lower()):
        source_lookup.setdefault(file_path.name, []).append(str(file_path))

    movements: list[dict[str, str]] = []
    for bucket, names in sorted(preview.organized_structure.items(), key=lambda item: item[0].lower()):
        for name in sorted(names, key=str.lower):
            sources = source_lookup.get(name, [])
            source_path = sources.pop(0) if sources else name
            destination = output_dir / bucket / name
            movements.append(
                {
                    "file_name": name,
                    "source": source_path,
                    "destination": str(destination),
                    "reason": f"Categorized into {bucket}",
                }
            )
    return movements


def _prune_plan_store() -> None:
    while len(_ORGANIZE_PLAN_STORE) > _ORGANIZE_PLAN_LIMIT:
        oldest_plan_id = next(iter(_ORGANIZE_PLAN_STORE))
        _ORGANIZE_PLAN_STORE.pop(oldest_plan_id, None)


def _store_organize_plan(plan_data: dict[str, Any]) -> dict[str, Any]:
    plan_id = uuid4().hex
    created_at = datetime.now(timezone.utc)
    record = {
        "plan_id": plan_id,
        "created_at": created_at,
        "updated_at": created_at,
        **plan_data,
    }
    with _ORGANIZE_PLAN_LOCK:
        _ORGANIZE_PLAN_STORE[plan_id] = record
        _prune_plan_store()
    return record


def _get_organize_plan(plan_id: str) -> Optional[dict[str, Any]]:
    with _ORGANIZE_PLAN_LOCK:
        plan = _ORGANIZE_PLAN_STORE.get(plan_id)
        if plan is None:
            return None
        plan["updated_at"] = datetime.now(timezone.utc)
        return dict(plan)


def _delete_organize_plan(plan_id: str) -> None:
    with _ORGANIZE_PLAN_LOCK:
        _ORGANIZE_PLAN_STORE.pop(plan_id, None)


def _prune_job_metadata(*, force: bool = False) -> None:
    global _LAST_JOB_METADATA_PRUNE_MONOTONIC
    now = monotonic()
    with _JOB_METADATA_LOCK:
        current_size = len(_JOB_METADATA)
        last_prune = _LAST_JOB_METADATA_PRUNE_MONOTONIC
        should_prune = force or current_size >= _JOB_METADATA_PRUNE_THRESHOLD
        if not should_prune and (now - last_prune) < _JOB_METADATA_PRUNE_INTERVAL_SECONDS:
            return
        tracked_ids = list(_JOB_METADATA.keys())
        _LAST_JOB_METADATA_PRUNE_MONOTONIC = now
    stale_ids = [job_id for job_id in tracked_ids if get_job(job_id) is None]
    if not stale_ids:
        return
    with _JOB_METADATA_LOCK:
        for job_id in stale_ids:
            _JOB_METADATA.pop(job_id, None)


def _set_job_metadata(job_id: str, data: dict[str, Any]) -> None:
    with _JOB_METADATA_LOCK:
        _JOB_METADATA[job_id] = data
    _prune_job_metadata()


def _get_job_metadata(job_id: str) -> dict[str, Any]:
    with _JOB_METADATA_LOCK:
        return dict(_JOB_METADATA.get(job_id, {}))


def _status_progress(status: str) -> int:
    if status == "queued":
        return 5
    if status == "running":
        return 65
    if status in {"completed", "failed"}:
        return 100
    return 0


def _build_job_view(job_id: str) -> Optional[dict[str, Any]]:
    job = get_job(job_id)
    if job is None:
        return None

    metadata = _get_job_metadata(job_id)
    result = job.result or {}
    schedule_delay_minutes = int(metadata.get("schedule_delay_minutes", 0) or 0)
    scheduled_for = str(metadata.get("scheduled_for", ""))
    is_scheduled = job.status == "queued" and bool(scheduled_for) and schedule_delay_minutes > 0
    processed_files = int(result.get("processed_files", 0) or 0)
    total_files = int(result.get("total_files", 0) or 0)
    failed_files = int(result.get("failed_files", 0) or 0)
    skipped_files = int(result.get("skipped_files", 0) or 0)
    progress = _status_progress(job.status)

    if total_files > 0 and job.status == "completed":
        progress = 100
    elif total_files > 0 and job.status == "running":
        progress = max(progress, int((processed_files / max(total_files, 1)) * 100))

    return {
        "job_id": job.job_id,
        "status": job.status,
        "progress_percent": max(0, min(progress, 100)),
        "created_at": _format_timestamp(job.created_at),
        "updated_at": _format_timestamp(job.updated_at),
        "error": job.error,
        "processed_files": processed_files,
        "total_files": total_files,
        "failed_files": failed_files,
        "skipped_files": skipped_files,
        "result": result,
        "methodology": metadata.get("methodology", "content_based"),
        "methodology_label": _ORGANIZE_METHODOLOGIES.get(
            metadata.get("methodology", "content_based"),
            "Content-Based",
        ),
        "input_dir": metadata.get("input_dir", ""),
        "output_dir": metadata.get("output_dir", ""),
        "dry_run": bool(metadata.get("dry_run", False)),
        "schedule_delay_minutes": schedule_delay_minutes,
        "scheduled_for": scheduled_for,
        "can_cancel": is_scheduled,
        "can_rollback": job.status == "completed" and not bool(metadata.get("dry_run", False)),
        "is_terminal": job.status in {"completed", "failed"},
    }


def _list_organize_jobs(
    *,
    status_filter: Optional[str] = None,
    limit: int = _ORGANIZE_HISTORY_LIMIT,
) -> list[dict[str, Any]]:
    jobs = list_jobs(job_type=_ORGANIZE_JOB_TYPE, limit=limit)
    rows: list[dict[str, Any]] = []
    for job in jobs:
        if status_filter and status_filter != "all" and job.status != status_filter:
            continue
        view = _build_job_view(job.job_id)
        if view is not None:
            rows.append(view)
    return rows


def _build_organize_stats() -> dict[str, Any]:
    jobs = _list_organize_jobs(limit=500)
    total_jobs = len(jobs)
    completed_jobs = sum(1 for job in jobs if job["status"] == "completed")
    failed_jobs = sum(1 for job in jobs if job["status"] == "failed")
    active_jobs = sum(1 for job in jobs if job["status"] in {"queued", "running"})
    total_files = sum(int(job["processed_files"]) for job in jobs if job["status"] == "completed")
    success_rate = 0.0
    if total_jobs:
        success_rate = (completed_jobs / total_jobs) * 100.0

    methodology_counts: dict[str, int] = {}
    for job in jobs:
        label = job.get("methodology_label", "Content-Based")
        methodology_counts[label] = methodology_counts.get(label, 0) + 1

    return {
        "total_jobs": total_jobs,
        "completed_jobs": completed_jobs,
        "failed_jobs": failed_jobs,
        "active_jobs": active_jobs,
        "total_files": total_files,
        "success_rate": success_rate,
        "methodology_counts": methodology_counts,
    }


def _run_organize_job(job_id: str, organize_request: OrganizeRequest) -> None:
    update_job(job_id, status="running", error=None)
    try:
        organizer = FileOrganizer(
            dry_run=organize_request.dry_run,
            use_hardlinks=organize_request.use_hardlinks,
        )
        result = organizer.organize(
            input_path=organize_request.input_dir,
            output_path=organize_request.output_dir,
            skip_existing=organize_request.skip_existing,
        )
        response = _result_to_response(result).model_dump()
        update_job(job_id, status="completed", result=response, error=None)
    except Exception as exc:
        update_job(job_id, status="failed", error=str(exc))


def _schedule_job(job_id: str, organize_request: OrganizeRequest, delay_minutes: int) -> None:
    delay_seconds = delay_minutes * 60

    def _runner() -> None:
        with _SCHEDULED_TIMERS_LOCK:
            _SCHEDULED_TIMERS.pop(job_id, None)
        _run_organize_job(job_id, organize_request)

    if delay_seconds <= 0:
        _runner()
        return

    timer = Timer(delay_seconds, _runner)
    timer.daemon = True
    with _SCHEDULED_TIMERS_LOCK:
        _SCHEDULED_TIMERS[job_id] = timer
    timer.start()


def _cancel_scheduled_job(job_id: str) -> bool:
    with _SCHEDULED_TIMERS_LOCK:
        timer = _SCHEDULED_TIMERS.pop(job_id, None)
    if timer is None:
        return False
    timer.cancel()
    update_job(job_id, status="failed", error="Cancelled before execution.")
    return True


def _job_report_payload(job: dict[str, Any]) -> dict[str, Any]:
    return {
        "job_id": job["job_id"],
        "status": job["status"],
        "created_at": job["created_at"],
        "updated_at": job["updated_at"],
        "methodology": job["methodology"],
        "input_dir": job["input_dir"],
        "output_dir": job["output_dir"],
        "dry_run": job["dry_run"],
        "processed_files": job["processed_files"],
        "total_files": job["total_files"],
        "failed_files": job["failed_files"],
        "skipped_files": job["skipped_files"],
        "error": job["error"],
        "result": job["result"],
    }


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
    roots = _allowed_roots(settings)
    default_input = str(roots[0]) if roots else ""
    default_output = str(roots[0] / "organized") if roots else ""
    stats = _build_organize_stats()
    context = _base_context(
        request,
        settings,
        active="organize",
        title="Organize",
        extras={
            "allowed_roots": [str(root) for root in roots],
            "default_input_dir": default_input,
            "default_output_dir": default_output,
            "methodology_options": _ORGANIZE_METHODOLOGIES,
            "stats": stats,
        },
    )
    return _templates.TemplateResponse("organize/dashboard.html", context)


@router.post("/organize/scan", response_class=HTMLResponse)
def organize_scan(
    request: Request,
    settings: ApiSettings = Depends(get_settings),
    input_dir: str = Form(""),
    output_dir: str = Form(""),
    methodology: str = Form("content_based"),
    recursive: str = Form("1"),
    include_hidden: str = Form("0"),
    skip_existing: str = Form("1"),
    use_hardlinks: str = Form("1"),
) -> HTMLResponse:
    error_message: Optional[str] = None
    info_message: Optional[str] = None
    plan: Optional[dict[str, Any]] = None

    try:
        if not input_dir.strip():
            raise ApiError(
                status_code=400,
                error="missing_input_dir",
                message="Input directory is required.",
            )
        if not output_dir.strip():
            raise ApiError(
                status_code=400,
                error="missing_output_dir",
                message="Output directory is required.",
            )

        safe_input = resolve_path(input_dir, settings.allowed_paths)
        safe_output = resolve_path(output_dir, settings.allowed_paths)
        if not safe_input.exists():
            raise ApiError(status_code=404, error="not_found", message="Input directory not found.")

        normalized_methodology = _normalize_methodology(methodology)
        recursive_enabled = _as_bool(recursive)
        include_hidden_enabled = _as_bool(include_hidden)
        if include_hidden_enabled:
            raise ApiError(
                status_code=400,
                error="include_hidden_not_supported",
                message="Including hidden files is not supported in this dashboard flow yet.",
            )
        skip_existing_enabled = _as_bool(skip_existing)
        use_hardlinks_enabled = _as_bool(use_hardlinks)

        scan_files = _scan_directory(
            safe_input,
            recursive=recursive_enabled,
            include_hidden=include_hidden_enabled,
        )
        counts = _counts_by_type(scan_files)

        organizer = FileOrganizer(dry_run=True, use_hardlinks=use_hardlinks_enabled)
        preview_result = organizer.organize(
            input_path=safe_input,
            output_path=safe_output,
            skip_existing=skip_existing_enabled,
        )
        preview = _result_to_response(preview_result)
        plan = _store_organize_plan(
            {
                "input_dir": str(safe_input),
                "output_dir": str(safe_output),
                "methodology": normalized_methodology,
                "recursive": recursive_enabled,
                "include_hidden": include_hidden_enabled,
                "skip_existing": skip_existing_enabled,
                "use_hardlinks": use_hardlinks_enabled,
                "scan_counts": counts,
                "scan_total_files": len(scan_files),
                "preview": preview.model_dump(),
                "movements": _build_plan_movements(scan_files, safe_output, preview),
            }
        )
        info_message = "Plan generated. Review movements and execute when ready."
    except ApiError as exc:
        error_message = exc.message
    except Exception:
        logger.exception("Failed to generate organize plan")
        error_message = "Failed to generate plan."

    return _templates.TemplateResponse(
        "organize/_plan.html",
        {
            "request": request,
            "plan": plan,
            "error_message": error_message,
            "info_message": info_message,
            "methodology_options": _ORGANIZE_METHODOLOGIES,
        },
    )


@router.post("/organize/plan/clear", response_class=HTMLResponse)
def organize_clear_plan(
    request: Request,
    plan_id: str = Form(""),
) -> HTMLResponse:
    if plan_id:
        _delete_organize_plan(plan_id)
    return _templates.TemplateResponse(
        "organize/_plan.html",
        {
            "request": request,
            "plan": None,
            "info_message": "Plan dismissed.",
            "error_message": None,
            "methodology_options": _ORGANIZE_METHODOLOGIES,
        },
    )


@router.post("/organize/execute", response_class=HTMLResponse)
def organize_execute(
    request: Request,
    background_tasks: BackgroundTasks,
    settings: ApiSettings = Depends(get_settings),
    plan_id: str = Form(""),
    dry_run: str = Form("0"),
    schedule_delay_minutes: str = Form(str(_ORGANIZE_DEFAULT_DELAY_MIN)),
) -> HTMLResponse:
    info_message: Optional[str] = None
    error_message: Optional[str] = None
    job_view: Optional[dict[str, Any]] = None
    response: Optional[HTMLResponse] = None

    try:
        if not plan_id.strip():
            raise ApiError(status_code=400, error="missing_plan_id", message="Plan id is required.")
        plan = _get_organize_plan(plan_id)
        if plan is None:
            raise ApiError(status_code=404, error="plan_not_found", message="Organization plan not found.")

        delay_minutes = _parse_delay_minutes(schedule_delay_minutes)
        dry_run_enabled = _as_bool(dry_run)
        safe_input = resolve_path(plan["input_dir"], settings.allowed_paths)
        safe_output = resolve_path(plan["output_dir"], settings.allowed_paths)

        organize_request = OrganizeRequest(
            input_dir=str(safe_input),
            output_dir=str(safe_output),
            skip_existing=bool(plan.get("skip_existing", True)),
            dry_run=dry_run_enabled,
            use_hardlinks=bool(plan.get("use_hardlinks", True)),
            run_in_background=True,
        )

        job = create_job(_ORGANIZE_JOB_TYPE)
        scheduled_for = ""
        if delay_minutes > 0:
            scheduled_at = datetime.now(timezone.utc).timestamp() + (delay_minutes * 60)
            scheduled_for = _format_timestamp(
                datetime.fromtimestamp(scheduled_at, tz=timezone.utc)
            )
        _set_job_metadata(
            job.job_id,
            {
                "plan_id": plan_id,
                "input_dir": organize_request.input_dir,
                "output_dir": organize_request.output_dir,
                "methodology": str(plan.get("methodology", "content_based")),
                "dry_run": organize_request.dry_run,
                "schedule_delay_minutes": delay_minutes,
                "scheduled_for": scheduled_for,
            },
        )

        if delay_minutes > 0:
            _schedule_job(job.job_id, organize_request, delay_minutes)
            info_message = f"Job scheduled to start in {delay_minutes} minute(s)."
        else:
            background_tasks.add_task(_run_organize_job, job.job_id, organize_request)
            info_message = "Organization job queued."

        job_view = _build_job_view(job.job_id)
        if job_view is None:
            raise ApiError(status_code=500, error="job_error", message="Failed to queue job.")
    except ApiError as exc:
        error_message = exc.message
    except Exception:
        logger.exception("Failed to queue organize job")
        error_message = "Failed to queue job."

    response = _templates.TemplateResponse(
        "organize/_job_status.html",
        {
            "request": request,
            "job": job_view,
            "info_message": info_message,
            "error_message": error_message,
            "rollback_message": None,
        },
    )
    response.headers["HX-Trigger"] = json.dumps({"refreshHistory": True, "refreshStats": True})
    return response


@router.get("/organize/jobs/{job_id}/status", response_class=HTMLResponse)
def organize_job_status(
    request: Request,
    job_id: str,
    format: str = Query("html", pattern="^(html|json)$"),
) -> Response:
    job = _build_job_view(job_id)
    if job is None:
        raise ApiError(status_code=404, error="not_found", message="Job not found.")
    if format == "json":
        return JSONResponse(content=job)
    return _templates.TemplateResponse(
        "organize/_job_status.html",
        {
            "request": request,
            "job": job,
            "info_message": None,
            "error_message": None,
            "rollback_message": None,
        },
    )


@router.get("/organize/jobs/{job_id}/events")
async def organize_job_events(job_id: str) -> StreamingResponse:
    if _build_job_view(job_id) is None:
        raise ApiError(status_code=404, error="not_found", message="Job not found.")

    async def _event_generator() -> Any:
        last_payload = ""
        while True:
            job = _build_job_view(job_id)
            if job is None:
                payload = {"job_id": job_id, "status": "missing"}
                data = json.dumps(payload)
                yield f"event: status\ndata: {data}\n\n"
                break

            data = json.dumps(job)
            if data != last_payload:
                yield f"event: status\ndata: {data}\n\n"
                last_payload = data
            else:
                yield ": keep-alive\n\n"
            if job["is_terminal"]:
                yield f"event: complete\ndata: {data}\n\n"
                break
            await asyncio.sleep(_ORGANIZE_EVENT_POLL_SECONDS)

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/organize/jobs/{job_id}/cancel", response_class=HTMLResponse)
def organize_job_cancel(request: Request, job_id: str) -> HTMLResponse:
    job = _build_job_view(job_id)
    if job is None:
        raise ApiError(status_code=404, error="not_found", message="Job not found.")

    info_message: Optional[str] = None
    error_message: Optional[str] = None
    if _cancel_scheduled_job(job_id):
        info_message = "Scheduled job cancelled."
    else:
        error_message = "Only scheduled jobs can be cancelled."
    refreshed_job = _build_job_view(job_id)
    return _templates.TemplateResponse(
        "organize/_job_status.html",
        {
            "request": request,
            "job": refreshed_job,
            "info_message": info_message,
            "error_message": error_message,
            "rollback_message": None,
        },
    )


@router.post("/organize/jobs/{job_id}/rollback", response_class=HTMLResponse)
def organize_job_rollback(request: Request, job_id: str) -> HTMLResponse:
    job = _build_job_view(job_id)
    if job is None:
        raise ApiError(status_code=404, error="not_found", message="Job not found.")

    rollback_message: Optional[str] = None
    error_message: Optional[str] = None
    if not job["can_rollback"]:
        error_message = "Rollback is only available for completed non-dry-run jobs."
    else:
        try:
            from file_organizer.undo.undo_manager import UndoManager

            manager = UndoManager()
            success = manager.undo_last_operation()
            rollback_message = (
                "Rollback completed for the latest tracked operation."
                if success
                else "No rollback candidates were available."
            )
        except Exception:
            logger.exception("Rollback execution failed for job {}", job_id)
            error_message = "Rollback failed."

    refreshed_job = _build_job_view(job_id)
    response = _templates.TemplateResponse(
        "organize/_job_status.html",
        {
            "request": request,
            "job": refreshed_job,
            "info_message": None,
            "error_message": error_message,
            "rollback_message": rollback_message,
        },
    )
    response.headers["HX-Trigger"] = json.dumps({"refreshHistory": True, "refreshStats": True})
    return response


@router.get("/organize/history", response_class=HTMLResponse)
def organize_history(
    request: Request,
    status_filter: str = Query("all", pattern="^(all|queued|running|completed|failed)$"),
    limit: int = Query(_ORGANIZE_HISTORY_LIMIT, ge=1, le=200),
) -> HTMLResponse:
    rows = _list_organize_jobs(status_filter=status_filter, limit=limit)
    return _templates.TemplateResponse(
        "organize/_history.html",
        {
            "request": request,
            "rows": rows,
            "status_filter": status_filter,
            "limit": limit,
        },
    )


@router.get("/organize/stats", response_class=HTMLResponse)
def organize_stats(request: Request) -> HTMLResponse:
    return _templates.TemplateResponse(
        "organize/_stats.html",
        {
            "request": request,
            "stats": _build_organize_stats(),
        },
    )


@router.get("/organize/report/{job_id}")
def organize_report(job_id: str, format: str = Query("json", pattern="^(json|csv|txt)$")) -> Response:
    job = _build_job_view(job_id)
    if job is None:
        raise ApiError(status_code=404, error="not_found", message="Job not found.")
    payload = _job_report_payload(job)
    if format == "json":
        return JSONResponse(content=payload)
    if format == "txt":
        lines = [
            f"Job ID: {payload['job_id']}",
            f"Status: {payload['status']}",
            f"Methodology: {payload['methodology']}",
            f"Input: {payload['input_dir']}",
            f"Output: {payload['output_dir']}",
            f"Dry run: {payload['dry_run']}",
            f"Processed: {payload['processed_files']} / {payload['total_files']}",
            f"Failed: {payload['failed_files']}",
            f"Skipped: {payload['skipped_files']}",
            f"Error: {payload['error'] or 'None'}",
        ]
        return Response(
            content="\n".join(lines),
            media_type="text/plain",
            headers={
                "Content-Disposition": _build_content_disposition(f"organization-{job_id}.txt"),
            },
        )

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["field", "value"])
    for key in (
        "job_id",
        "status",
        "methodology",
        "input_dir",
        "output_dir",
        "dry_run",
        "processed_files",
        "total_files",
        "failed_files",
        "skipped_files",
        "error",
    ):
        writer.writerow([key, payload.get(key, "")])
    buffer.write("\n")
    writer.writerow(["bucket", "files"])
    result = payload.get("result") or {}
    structure = result.get("organized_structure") or {}
    for bucket, files in structure.items():
        writer.writerow([bucket, ", ".join(files)])
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": _build_content_disposition(f"organization-{job_id}.csv"),
        },
    )


@router.get("/settings", response_class=HTMLResponse)
def settings(request: Request, settings_obj: ApiSettings = Depends(get_settings)) -> HTMLResponse:
    context = _base_context(request, settings_obj, active="settings", title="Settings")
    return _templates.TemplateResponse("settings/index.html", context)


@router.get("/profile", response_class=HTMLResponse)
def profile(request: Request, settings: ApiSettings = Depends(get_settings)) -> HTMLResponse:
    context = _base_context(request, settings, active="profile", title="Profile")
    return _templates.TemplateResponse("profile/index.html", context)
