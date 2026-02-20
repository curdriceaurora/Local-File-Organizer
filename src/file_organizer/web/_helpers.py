"""Shared helpers, constants, and template setup for the web UI."""

from __future__ import annotations

import hashlib
import io
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import Request
from fastapi.templating import Jinja2Templates
from PIL import Image, ImageDraw

from file_organizer.api.config import ApiSettings
from file_organizer.api.exceptions import ApiError
from file_organizer.api.utils import is_hidden, resolve_path
from file_organizer.core.organizer import FileOrganizer

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

NAV_ITEMS = [
    ("Home", "/ui/"),
    ("Files", "/ui/files"),
    ("Organize", "/ui/organize"),
    ("Marketplace", "/ui/marketplace"),
    ("Settings", "/ui/settings"),
    ("Profile", "/ui/profile"),
]

PAGE_SIZE = 48
THUMBNAIL_SIZE = (240, 160)
MAX_LIMIT = 500
MAX_NAV_DEPTH = 12
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
UPLOAD_CHUNK_SIZE = 1024 * 1024
MAX_THUMBNAIL_BYTES = 15 * 1024 * 1024
TEXT_SAMPLE_BYTES = 8192
TEXT_PREVIEW_CHARS = 4000
INVALID_FILENAME_CHARS = set('<>:"/\\|?*')
SAFE_FILENAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._()-]*$")
ALLOWED_VIEWS = {"grid", "list"}
ALLOWED_SORT_BY = {"name", "size", "created", "modified", "type"}
ALLOWED_SORT_ORDER = {"asc", "desc"}
FILENAME_FALLBACK_RE = re.compile(r"[^A-Za-z0-9._-]+")
TRUE_VALUES = {"1", "true", "yes", "on"}

FILE_TYPE_GROUPS = {
    "image": FileOrganizer.IMAGE_EXTENSIONS,
    "video": FileOrganizer.VIDEO_EXTENSIONS,
    "audio": FileOrganizer.AUDIO_EXTENSIONS,
    "text": FileOrganizer.TEXT_EXTENSIONS,
    "cad": FileOrganizer.CAD_EXTENSIONS,
    "pdf": {".pdf"},
}


def base_context(
    request: Request,
    settings: ApiSettings,
    *,
    active: str,
    title: str,
    extras: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Build the base Jinja2 template context."""
    context: dict[str, Any] = {
        "request": request,
        "app_name": settings.app_name,
        "version": settings.version,
        "active": active,
        "page_title": title,
        "nav_items": NAV_ITEMS,
        "year": datetime.now(UTC).year,
    }
    if extras:
        context.update(extras)
    return context


def allowed_roots(settings: ApiSettings) -> list[Path]:
    """Return resolved allowed root paths from settings."""
    roots: list[Path] = []
    for root in settings.allowed_paths or []:
        try:
            resolved = resolve_path(root, settings.allowed_paths)
        except ApiError:
            continue
        if resolved not in roots:
            roots.append(resolved)
    return roots


def resolve_selected_path(path_value: Optional[str], settings: ApiSettings) -> Optional[Path]:
    """Resolve a user-provided path, falling back to the first allowed root."""
    if path_value:
        return resolve_path(path_value, settings.allowed_paths)
    roots = allowed_roots(settings)
    if roots:
        return roots[0]
    return None


def format_bytes(size_bytes: int) -> str:
    """Format byte count as a human-readable string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    units = ["KB", "MB", "GB", "TB"]
    size = float(size_bytes)
    for unit in units:
        size /= 1024.0
        if size < 1024.0:
            return f"{size:.1f} {unit}"
    return f"{size:.1f} PB"


def format_timestamp(timestamp: datetime) -> str:
    """Format a datetime for display."""
    return timestamp.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")


def parse_file_type_filter(file_type: Optional[str]) -> Optional[set[str]]:
    """Parse a file-type filter string into a set of extensions."""
    if not file_type or file_type == "all":
        return None
    token = file_type.lower()
    if token in FILE_TYPE_GROUPS:
        return set(FILE_TYPE_GROUPS[token])
    if token.startswith("."):
        return {token}
    return {f".{token}"}


def detect_kind(path: Path) -> str:
    """Detect the broad kind of a file based on its extension."""
    suffix = path.suffix.lower()
    if suffix in FILE_TYPE_GROUPS["image"]:
        return "image"
    if suffix == ".pdf":
        return "pdf"
    if suffix in FILE_TYPE_GROUPS["video"]:
        return "video"
    if suffix in FILE_TYPE_GROUPS["audio"]:
        return "audio"
    if suffix in FILE_TYPE_GROUPS["text"]:
        return "text"
    if suffix in FILE_TYPE_GROUPS["cad"]:
        return "cad"
    return "file"


def path_id(path: Path) -> str:
    """Return a short hash identifier for a path."""
    digest = hashlib.sha1(str(path).encode("utf-8")).hexdigest()
    return digest[:10]


def select_root_for_path(path: Path, roots: list[Path]) -> Path:
    """Select the best-matching root for a given path."""
    root_match: Optional[Path] = None
    for root in roots:
        try:
            path.relative_to(root)
        except ValueError:
            continue
        if root_match is None or len(str(root)) > len(str(root_match)):
            root_match = root
    return root_match or path


def validate_depth(path: Path, roots: list[Path]) -> None:
    """Raise ApiError when path exceeds the maximum navigation depth."""
    root_match = select_root_for_path(path, roots)
    try:
        depth = len(path.relative_to(root_match).parts)
    except ValueError:
        depth = 0
    if depth > MAX_NAV_DEPTH:
        raise ApiError(
            status_code=400,
            error="path_too_deep",
            message="Selected path is too deep for the file browser.",
        )


def has_children(path: Path) -> bool:
    """Check whether a directory contains visible subdirectories."""
    try:
        for entry in path.iterdir():
            if entry.is_dir() and not is_hidden(entry):
                return True
    except OSError:
        return False
    return False


def is_probably_text(path: Path) -> bool:
    """Heuristic to detect whether a file is likely text."""
    try:
        with path.open("rb") as handle:
            sample = handle.read(TEXT_SAMPLE_BYTES)
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


def sanitize_upload_name(name: str) -> Optional[str]:
    """Sanitize an upload filename, returning None when unsafe."""
    safe_name = Path(name).name.strip()
    if not safe_name or safe_name in {".", ".."}:
        return None
    if safe_name.startswith("."):
        return None
    if len(safe_name) > 255:
        return None
    if any(char in INVALID_FILENAME_CHARS for char in safe_name):
        return None
    if not SAFE_FILENAME_RE.match(safe_name):
        return None
    return safe_name


def normalize_view(view: str) -> str:
    """Normalize a view parameter to a valid value."""
    return view if view in ALLOWED_VIEWS else "grid"


def normalize_sort_by(sort_by: str) -> str:
    """Normalize a sort-by parameter to a valid value."""
    return sort_by if sort_by in ALLOWED_SORT_BY else "name"


def normalize_sort_order(sort_order: str) -> str:
    """Normalize a sort-order parameter to a valid value."""
    return sort_order if sort_order in ALLOWED_SORT_ORDER else "asc"


def clamp_limit(limit: int) -> int:
    """Clamp a pagination limit to valid bounds."""
    return max(1, min(limit, MAX_LIMIT))


def build_content_disposition(filename: str) -> str:
    """Build a Content-Disposition header value for a download."""
    from urllib.parse import quote

    safe_name = filename.replace("\r", "").replace("\n", "").replace('"', "_")
    fallback = FILENAME_FALLBACK_RE.sub("_", safe_name).strip("._")
    if not fallback:
        fallback = "download"
    encoded = quote(filename)
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{encoded}"


def as_bool(value: Optional[str]) -> bool:
    """Interpret a form value as a boolean."""
    if value is None:
        return False
    return value.strip().lower() in TRUE_VALUES


def render_placeholder_thumbnail(label: str, size: tuple[int, int]) -> bytes:
    """Render a labeled placeholder thumbnail image as PNG bytes."""
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


def render_image_thumbnail(path: Path) -> bytes:
    """Render a scaled thumbnail of an image file as PNG bytes."""
    with Image.open(path) as image_file:
        image = image_file.convert("RGB")
        image.thumbnail(THUMBNAIL_SIZE)
        canvas = Image.new("RGB", THUMBNAIL_SIZE, (235, 240, 245))
        offset = (
            (THUMBNAIL_SIZE[0] - image.width) // 2,
            (THUMBNAIL_SIZE[1] - image.height) // 2,
        )
        canvas.paste(image, offset)
        buffer = io.BytesIO()
        canvas.save(buffer, format="PNG")
        return buffer.getvalue()
