"""Degraded categorization path for images that timed out in the vision model (#406).

When ``VisionProcessor`` exceeds the dispatcher's per-file timeout (#396),
the abandoned thread leaves the file uncategorized. Rather than counting
it as a hard failure, we run a metadata-only fallback that synthesizes a
folder + filename from:

1. **EXIF metadata** — ``DateTime`` and ``Model`` tags via Pillow's
   ``Image.getexif()``. Yields ``Images/<Year>/<Month>/`` placements that
   match a typical date-based photo layout.
2. **Filename pattern recognition** — well-known patterns such as
   ``Screenshot YYYY-MM-DD …`` or ``IMG_YYYYMMDD_HHMMSS.jpg`` lock the
   file to ``Images/Screenshots/<Year>/`` and ``Images/Photos/<Year>/<Month>/``.
3. **Generic bucket** — anything that matches neither lands in
   ``Images/Untagged/``.

The result carries a ``source`` marker that the summary uses to surface a
"categorized via fallback" count, distinct from the success and failure
totals. Fallback placements are intentionally low-confidence (the vision
model never saw the image) and should be reviewed before any destructive
rename / move.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from loguru import logger

# Folder name returned when neither EXIF nor filename gave a usable hint.
_UNTAGGED_FOLDER = "Images/Untagged"


FallbackSource = Literal["fallback_exif", "fallback_filename"]


@dataclass(frozen=True)
class FallbackResult:
    """Folder + filename + provenance from the degraded image path."""

    folder: str
    filename: str
    source: FallbackSource


# ----------------------------------------------------------------------
# Filename heuristics — checked in order, first match wins.
# Each entry: (compiled regex, builder taking the match → FallbackResult)
# ----------------------------------------------------------------------

# "Screenshot 2026-05-22 at 14.03.07.png"
_SCREENSHOT_PATTERN = re.compile(
    r"^Screenshot\s+(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})",
    re.IGNORECASE,
)

# "IMG_20260522_140307.jpg" or "VID_20260522_140307.mp4"
_IMG_DATESTAMP_PATTERN = re.compile(
    r"^(?:IMG|VID|PXL|DSC)_(?P<year>\d{4})(?P<month>\d{2})(?P<day>\d{2})",
    re.IGNORECASE,
)


def _from_filename(path: Path) -> FallbackResult | None:
    """Try filename-based categorization. Returns None if no pattern matched."""
    name = path.name
    if (m := _SCREENSHOT_PATTERN.match(name)) is not None:
        year = m.group("year")
        return FallbackResult(
            folder=f"Images/Screenshots/{year}",
            filename=path.stem,
            source="fallback_filename",
        )
    if (m := _IMG_DATESTAMP_PATTERN.match(name)) is not None:
        year = m.group("year")
        month = m.group("month")
        return FallbackResult(
            folder=f"Images/Photos/{year}/{month}",
            filename=path.stem,
            source="fallback_filename",
        )
    return None


def _from_exif(path: Path) -> FallbackResult | None:
    """Try EXIF-based categorization. Returns None if Pillow / EXIF unavailable."""
    try:
        from PIL import ExifTags, Image
    except ImportError:
        return None

    try:
        with Image.open(path) as img:
            exif = img.getexif()
    except Exception:
        # Truncated image, format Pillow doesn't recognise, permission error, …
        return None

    if not exif:
        return None

    # Map numeric tag IDs to names so we can ask by name.
    tag_by_name: dict[str, int] = {v: k for k, v in ExifTags.TAGS.items()}
    date_tag_id = tag_by_name.get("DateTimeOriginal") or tag_by_name.get("DateTime")
    if date_tag_id is None:  # pragma: no cover — Pillow's TAGS always has these
        return None
    raw = exif.get(date_tag_id)
    if not raw:
        return None

    # EXIF date format: "YYYY:MM:DD HH:MM:SS". The standard doesn't carry
    # a timezone, so a naive datetime is the honest representation; we
    # only ever read .year / .month off it, never use it as an absolute
    # instant. Suppress ruff DTZ007 — the warning's tzinfo recommendation
    # would invent a timezone we don't actually have.
    try:
        dt = datetime.strptime(str(raw), "%Y:%m:%d %H:%M:%S")  # noqa: DTZ007
    except ValueError:
        return None

    return FallbackResult(
        folder=f"Images/Photos/{dt.year:04d}/{dt.month:02d}",
        filename=path.stem,
        source="fallback_exif",
    )


def compute_fallback(file_path: Path) -> FallbackResult:
    """Synthesize a folder + filename for an image that timed out in vision (#406).

    Resolution order:
      1. EXIF DateTime / DateTimeOriginal → ``Images/Photos/<Year>/<Month>/``
      2. Filename pattern (``Screenshot YYYY-MM-DD`` / ``IMG_YYYYMMDD_HHMMSS``)
      3. ``Images/Untagged/`` with the file's stem as the filename

    Always returns a result — the caller never has to handle ``None``.

    Args:
        file_path: Path to the image whose vision inference timed out.

    Returns:
        A ``FallbackResult`` carrying the folder, filename, and the
        ``source`` marker (``"fallback_exif"`` or ``"fallback_filename"``).
        Generic-bucket placements are reported as ``"fallback_filename"``
        because the filename — not the (empty) EXIF — is what dictated them.
    """
    if (exif_result := _from_exif(file_path)) is not None:
        logger.debug(
            "Fallback categorization for {}: source=fallback_exif → {}",
            file_path.name,
            exif_result.folder,
        )
        return exif_result

    if (filename_result := _from_filename(file_path)) is not None:
        logger.debug(
            "Fallback categorization for {}: source=fallback_filename → {}",
            file_path.name,
            filename_result.folder,
        )
        return filename_result

    logger.debug(
        "Fallback categorization for {}: source=fallback_filename → {} (untagged)",
        file_path.name,
        _UNTAGGED_FOLDER,
    )
    return FallbackResult(
        folder=_UNTAGGED_FOLDER,
        filename=file_path.stem,
        source="fallback_filename",
    )
