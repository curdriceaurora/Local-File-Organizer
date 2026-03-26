"""Search endpoints."""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from file_organizer.api.cache import CacheBackend, InMemoryCache
from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_settings
from file_organizer.api.models import SearchResult
from file_organizer.api.utils import is_hidden, resolve_path

logger = logging.getLogger(__name__)

router = APIRouter(tags=["search"])

_MAX_TRAVERSAL = 10_000
_MAX_SEMANTIC = 2_000
_MAX_LIMIT = 1000
_CACHE_TTL_SECONDS = 300  # 5 minutes

# Global cache instance for search results
_search_cache: CacheBackend = InMemoryCache()


class _ScoringTiers:
    """Relevance scoring tiers for file search results."""

    EXACT_MATCH = 1.0  # Exact filename or stem match
    STEM_CONTAINS = 0.7  # Query appears in filename stem (not extension)
    EXTENSION_MATCH = 0.5  # Exact file extension match
    PATH_CONTAINS = 0.3  # Query appears anywhere in file path
    NO_MATCH = 0.0


def _generate_cache_key(
    query: str,
    file_type: str | None,
    search_roots: list[Path],
    semantic: bool,
    offset: int | None,
    limit: int | None,
) -> str:
    """Generate a cache key for search results.

    Creates a deterministic hash from search parameters to use as cache key.
    """
    params = {
        "q": query,
        "type": file_type,
        "roots": [str(root) for root in search_roots],
        "semantic": semantic,
        "offset": offset,
        "limit": limit,
    }
    # Create deterministic JSON string and hash it
    params_json = json.dumps(params, sort_keys=True)
    hash_digest = hashlib.sha256(params_json.encode()).hexdigest()
    return f"search:{hash_digest[:16]}"


def _relative_path(fp: Path, roots: list[Path]) -> str:
    """Return *fp* relative to the first matching root, or absolute as fallback."""
    for root in roots:
        try:
            return str(fp.relative_to(root))
        except ValueError:
            continue
    return str(fp)


def _load_cached_results(cache_key: str) -> list[SearchResult] | None:
    """Return cached search results if present and valid."""
    cached_result = _search_cache.get(cache_key)
    if not cached_result:
        return None

    try:
        cached_data = json.loads(cached_result)
        return [SearchResult(**item) for item in cached_data]
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("Failed to deserialize cached search result: %s", exc, exc_info=True)
        return None


def _store_cached_results(cache_key: str, results: list[SearchResult]) -> None:
    """Store search results in the response cache."""
    _search_cache.set(
        cache_key,
        json.dumps([item.model_dump() for item in results]),
        ttl_seconds=_CACHE_TTL_SECONDS,
    )


def _paginate_results(
    results: list[SearchResult],
    offset: int | None,
    limit: int | None,
) -> list[SearchResult]:
    """Return a stable slice of results using the legacy offset/limit contract."""
    skip = offset or 0
    if limit is None:
        return results[skip:]
    return results[skip : skip + limit]


def _semantic_search_with_cache(
    cache_key: str,
    search_roots: list[Path],
    query: str,
    file_type: str | None,
    offset: int | None,
    limit: int | None,
) -> list[SearchResult]:
    """Run semantic search and cache the paginated results."""
    skip = max(0, offset or 0)
    if skip >= _MAX_SEMANTIC:
        return []

    if limit is not None:
        top_k = min(skip + limit, _MAX_SEMANTIC)
        results = _semantic_search(search_roots, query, file_type, top_k=top_k)
    else:
        results = _semantic_search(search_roots, query, file_type, top_k=_MAX_SEMANTIC)

    paged_results = _paginate_results(results, offset, limit)
    _store_cached_results(cache_key, paged_results)
    return paged_results


def _compute_score(file_path: Path, query: str) -> float:
    """Score a file path against a search query.

    Scoring tiers:
    - 1.0 (EXACT_MATCH): Exact filename or stem match
    - 0.7 (STEM_CONTAINS): Query appears in filename stem (not extension)
    - 0.5 (EXTENSION_MATCH): Exact file extension match
    - 0.3 (PATH_CONTAINS): Query appears anywhere in file path
    - 0.0 (NO_MATCH): No match found

    Note: Changed from checking full filename to stem only in tier-2.
    This prevents queries matching both the stem and extension from
    scoring higher than extension-only matches.
    """
    q_lower = query.lower()
    name_lower = file_path.name.lower()
    stem_lower = file_path.stem.lower()
    suffix_lower = file_path.suffix.lower().lstrip(".")

    if name_lower == q_lower or stem_lower == q_lower:
        return _ScoringTiers.EXACT_MATCH
    if q_lower in stem_lower:
        return _ScoringTiers.STEM_CONTAINS
    # Handle extension match: normalize both sides (strip leading dots)
    # This allows queries like "pdf" or ".pdf" to match extension ".pdf"
    q_suffix = q_lower.lstrip(".")
    if q_suffix and q_suffix == suffix_lower:
        return _ScoringTiers.EXTENSION_MATCH
    if q_lower in str(file_path).lower():
        return _ScoringTiers.PATH_CONTAINS
    return _ScoringTiers.NO_MATCH


def _collect_matching_files(
    root: Path,
    query: str,
    file_type: str | None,
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
            # Skip symlinks to prevent traversing into hidden/protected directories
            if entry.is_symlink():
                continue
            if not entry.is_file():
                continue
            if is_hidden(entry):
                continue
            if ext_filter and entry.suffix.lower() != ext_filter:
                continue
            # Check if query matches name or path
            try:
                rel = entry.relative_to(root)
            except ValueError:
                rel = entry
            if q_lower in entry.name.lower() or q_lower in str(rel).lower():
                yield entry
    except PermissionError:
        logger.debug("Permission denied traversing %s", root)


def _build_semantic_corpus(
    roots: list[Path],
    max_files: int = _MAX_SEMANTIC,
) -> tuple[list[str], list[Path]]:
    """Walk *roots* and build a text corpus for semantic indexing.

    Each document is the concatenation of the file stem, relative path parts,
    and up to :data:`_SEMANTIC_TEXT_LIMIT` characters of extracted text.

    Args:
        roots: Directory roots to traverse.
        max_files: Hard upper bound on files traversed across all roots.

    Returns:
        ``(documents, paths)`` lists of equal length, ready for
        :meth:`HybridRetriever.index`.
    """
    from file_organizer.services.search.hybrid_retriever import (
        read_text_safe,
    )  # lazy — optional dep

    documents: list[str] = []
    paths: list[Path] = []
    total = 0
    done = False

    for root in roots:
        if done or not root.exists() or not root.is_dir():
            continue
        try:
            for entry in root.rglob("*"):
                total += 1
                if total > max_files:
                    done = True
                    break
                try:
                    rel_entry = entry.relative_to(root)
                except ValueError:
                    rel_entry = entry
                if entry.is_symlink() or not entry.is_file() or is_hidden(rel_entry):
                    continue
                text = read_text_safe(entry)
                doc = f"{entry.stem} {' '.join(rel_entry.parts)} {text}".strip()
                documents.append(doc)
                paths.append(entry)
        except PermissionError:
            logger.debug("Permission denied traversing %s", root)

    return documents, paths


def _semantic_search(
    roots: list[Path],
    query: str,
    file_type: str | None,
    top_k: int,
) -> list[SearchResult]:
    """Run hybrid BM25+vector retrieval over *roots* for *query*.

    Args:
        roots: Directories to index.
        query: Search query.
        file_type: Optional file extension filter (e.g. ``"pdf"``).
        top_k: Maximum results to return.

    Returns:
        List of :class:`SearchResult` sorted by descending RRF score.
    """
    from file_organizer.services.search.hybrid_retriever import (
        HybridRetriever,
    )  # lazy — optional dep

    documents, paths = _build_semantic_corpus(roots)
    if not paths:
        return []

    retriever = HybridRetriever()
    try:
        retriever.index(documents, paths)
    except ValueError as exc:  # pragma: no cover — defensive; index() rarely raises ValueError
        logger.warning("Semantic index build failed: %s", exc, exc_info=True)
        return []

    # When filtering by type, overfetch the full semantic budget so that
    # post-filter slicing can fill top_k results even if mixed-type hits dominate.
    fetch_k = _MAX_SEMANTIC if file_type else min(top_k * 2, _MAX_SEMANTIC)
    raw_results = retriever.retrieve(query, top_k=fetch_k)

    ext_filter: str | None = None
    if file_type:
        ext_filter = file_type.lower() if file_type.startswith(".") else f".{file_type.lower()}"

    results: list[SearchResult] = []
    for fp, score in raw_results:
        if ext_filter and fp.suffix.lower() != ext_filter:
            continue
        try:
            stat = fp.stat()
        except OSError:
            continue
        creation_ts = getattr(stat, "st_birthtime", stat.st_mtime)
        created_str = datetime.fromtimestamp(creation_ts, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        results.append(
            SearchResult(
                filename=fp.name,
                path=_relative_path(fp, roots),
                score=round(score, 6),
                type=fp.suffix.lower().lstrip(".") or "unknown",
                size=stat.st_size,
                created=created_str,
            )
        )
        if len(results) >= top_k:
            break

    return results


@router.get("/search", response_model=list[SearchResult])
def search(
    q: str | None = Query(None, description="Search query"),
    file_type: str | None = Query(None, alias="type"),
    limit: int | None = None,
    offset: int | None = None,
    path: str | None = None,
    semantic: bool = Query(False, description="Use hybrid BM25+vector semantic search"),
    settings: ApiSettings = Depends(get_settings),
) -> list[SearchResult] | JSONResponse:
    """Search for files by query.

    Supports filtering, pagination, relevance scoring, and result caching.

    When ``semantic=true`` the search uses hybrid BM25+vector retrieval
    (Reciprocal Rank Fusion) instead of the default keyword scan.  The
    existing ``semantic=false`` path is unchanged.

    Authentication is enforced at the middleware layer
    (see ``file_organizer.api.middleware``), not per-route.
    """
    if q is None or q == "":
        return JSONResponse(
            status_code=400,
            content={"detail": "Query parameter 'q' is required"},
        )

    # Clamp limit to a safe upper bound to prevent unbounded allocations.
    effective_limit: int | None = None
    if limit is not None and limit > 0:
        effective_limit = min(limit, _MAX_LIMIT)

    # Determine search roots (normalize paths for consistency)
    if path:
        search_roots = [resolve_path(path, settings.allowed_paths)]
    else:
        # Normalize allowed_paths to ensure consistent path representation.
        # Allowed roots are configuration-controlled, not request-driven.
        search_roots = [  # codeql[py/path-injection]
            Path(p).resolve() for p in settings.allowed_paths
        ]

    cache_key = _generate_cache_key(q, file_type, search_roots, semantic, offset, effective_limit)
    cached_results = _load_cached_results(cache_key)
    if cached_results is not None:
        return cached_results

    # ------------------------------------------------------------------
    # Semantic path — hybrid BM25 + vector retrieval
    # ------------------------------------------------------------------
    if semantic:
        try:
            return _semantic_search_with_cache(
                cache_key,
                search_roots,
                q,
                file_type,
                offset,
                effective_limit,
            )
        except ImportError:
            return JSONResponse(
                status_code=503,
                content={
                    "detail": (
                        "Semantic search is not available: search dependencies not installed. "
                        "Install with: pip install 'file-organizer[search]'"
                    )
                },
            )

    # ------------------------------------------------------------------
    # Default keyword path — unchanged response shape, with cached results
    # ------------------------------------------------------------------
    results: list[SearchResult] = []
    total_traversed = 0

    for root in search_roots:
        if not root.exists() or not root.is_dir():
            continue
        # Adjust remaining quota for this root (global limit across all roots)
        remaining = _MAX_TRAVERSAL - total_traversed
        if remaining <= 0:
            break
        for fp in _collect_matching_files(root, q, file_type, max_files=remaining):
            total_traversed += 1
            try:
                stat = fp.stat()
            except OSError:
                continue
            score = _compute_score(fp, q)
            if hasattr(stat, "st_birthtime"):
                creation_ts = stat.st_birthtime
            else:
                creation_ts = stat.st_mtime
            created_dt = datetime.fromtimestamp(creation_ts, tz=UTC)
            # Format as ISO 8601 with Z suffix for UTC
            created_str = created_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            results.append(
                SearchResult(
                    filename=fp.name,
                    path=_relative_path(fp, search_roots),
                    score=score,
                    type=fp.suffix.lower().lstrip(".") or "unknown",
                    size=stat.st_size,
                    created=created_str,
                )
            )

    # Sort by score descending, then by filename for deterministic pagination
    results.sort(key=lambda r: (-r.score, r.filename))

    paged_results = _paginate_results(results, offset, effective_limit)
    _store_cached_results(cache_key, paged_results)

    return paged_results
