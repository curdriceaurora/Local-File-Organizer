"""Search endpoints."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_settings
from file_organizer.api.utils import is_hidden, resolve_path

logger = logging.getLogger(__name__)

router = APIRouter(tags=["search"])

_MAX_TRAVERSAL = 10_000


class SearchResult(BaseModel):
    """Single search result."""

    filename: str
    path: str
    score: float
    type: Optional[str] = None
    size: Optional[int] = None
    created: Optional[str] = None


def _compute_score(file_path: Path, query: str) -> float:
    """Score a file path against a search query.

    Returns 1.0 for exact filename match, 0.7 for filename contains,
    0.3 for path contains.
    """
    q_lower = query.lower()
    name_lower = file_path.name.lower()
    stem_lower = file_path.stem.lower()

    if name_lower == q_lower or stem_lower == q_lower:
        return 1.0
    if q_lower in name_lower:
        return 0.7
    if q_lower in str(file_path).lower():
        return 0.3
    return 0.0


def _collect_matching_files(
    root: Path,
    query: str,
    file_type: Optional[str],
    max_files: int = _MAX_TRAVERSAL,
) -> Iterator[Path]:
    """Yield files under *root* whose name or path matches *query*."""
    q_lower = query.lower()
    ext_filter = None
    if file_type:
        ext_filter = file_type.lower() if file_type.startswith(".") else f".{file_type.lower()}"

    traversed = 0
    try:
        for entry in root.rglob("*"):
            traversed += 1
            if traversed > max_files:
                break
            if not entry.is_file():
                continue
            if is_hidden(entry):
                continue
            if ext_filter and entry.suffix.lower() != ext_filter:
                continue
            # Check if query matches name or path
            if q_lower in entry.name.lower() or q_lower in str(entry).lower():
                yield entry
    except PermissionError:
        logger.debug("Permission denied traversing %s", root)


@router.get("/search", response_model=None)
def search(
    q: Optional[str] = Query(None, description="Search query"),
    type: Optional[str] = None,
    limit: Optional[int] = None,
    offset: Optional[int] = None,
    path: Optional[str] = None,
    settings: ApiSettings = Depends(get_settings),
) -> list[SearchResult] | JSONResponse:
    """Search for files by query.

    Supports filtering, pagination, and relevance scoring.
    """
    if q is None or q == "":
        return JSONResponse(
            status_code=400,
            content={"detail": "Query parameter 'q' is required"},
        )

    # Determine search roots
    if path:
        search_roots = [resolve_path(path, settings.allowed_paths)]
    else:
        search_roots = [Path(p) for p in settings.allowed_paths]

    results: list[SearchResult] = []
    for root in search_roots:
        if not root.exists() or not root.is_dir():
            continue
        for fp in _collect_matching_files(root, q, type):
            try:
                stat = fp.stat()
            except OSError:
                continue
            score = _compute_score(fp, q)
            if hasattr(stat, "st_birthtime"):
                creation_ts = stat.st_birthtime
            else:
                creation_ts = stat.st_mtime
            results.append(
                SearchResult(
                    filename=fp.name,
                    path=str(fp),
                    score=score,
                    type=fp.suffix.lower().lstrip(".") or "unknown",
                    size=stat.st_size,
                    created=datetime.fromtimestamp(creation_ts, tz=UTC).isoformat(),
                )
            )

    # Sort by score descending
    results.sort(key=lambda r: r.score, reverse=True)

    # Apply pagination
    skip = offset or 0
    if limit:
        results = results[skip : skip + limit]
    else:
        results = results[skip:]

    return results
