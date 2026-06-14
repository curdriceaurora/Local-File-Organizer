"""Hybrid BM25 + vector retriever with Reciprocal Rank Fusion (RRF).

Combines lexical (BM25) and semantic (TF-IDF vector) rankings using
Reciprocal Rank Fusion to produce a single fused ranking.

RRF formula:  score(d) = sum over indices i of  1 / (k + rank_i(d))
where k=60 is the standard smoothing constant (Cormack et al., 2009).

This module also exposes :func:`read_text_safe`, a shared helper used by
both the API router and the CLI to extract text from files for corpus
building.
"""

from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

from loguru import logger

from file_organizer.interfaces.search import RetrieverProtocol
from file_organizer.services.search.bm25_index import BM25Index
from file_organizer.services.search.vector_index import VectorIndex
from file_organizer.utils.safedir import SafeDir, SymlinkRejected

# ---------------------------------------------------------------------------
# Corpus helpers (shared by API router and CLI)
# ---------------------------------------------------------------------------

#: Maximum number of bytes read from each file for corpus building.
CORPUS_TEXT_LIMIT: int = 4096
#: Number of bytes inspected to decide whether a file is binary.
CORPUS_BINARY_PEEK: int = 512


def read_text_safe(
    path: Path,
    limit: int = CORPUS_TEXT_LIMIT,
    *,
    scan_root: Path | None = None,
) -> str:
    """Read up to *limit* bytes from *path* as text, skipping binary files.

    Reads only what is needed: opens the file in binary mode, reads at most
    *limit* bytes, inspects the first :data:`CORPUS_BINARY_PEEK` bytes for
    null bytes (binary sentinel), then decodes.

    The read goes through :class:`file_organizer.utils.safedir.SafeDir` on
    POSIX so a symlink swapped in between corpus enumeration and this content
    read is refused rather than dereferenced (closes the LLM-exfiltration
    vector documented in #264). Windows / non-POSIX platforms fall back to the
    legacy path-based open until the SafeDir Windows port lands.

    When *scan_root* is provided, the read uses
    :meth:`SafeDir.open_anchored_reader` to walk every intermediate path
    component between *scan_root* and *path* with ``O_NOFOLLOW``, so a symlink
    swapped into ANY ancestor directory is detected (closes the nested-ancestor
    TOCTOU window documented in #286/#325). Without *scan_root* the
    parent-rooted ``SafeDir.open_root(path.parent)`` behaviour is retained.

    Args:
        path: File to read.
        limit: Maximum number of bytes to read (may yield fewer characters for
            multi-byte encodings).
        scan_root: The trusted root directory that was walked to discover
            *path*. When provided, component-wise ``O_NOFOLLOW`` validation is
            applied to every directory between *scan_root* and *path*. Passing
            ``None`` (the default) retains the parent-rooted SafeDir behaviour.

    Returns:
        Decoded text content, or an empty string if the file is binary,
        unreadable, or a refused symlink.
    """
    # Defensive clamp: a non-positive limit would make the underlying
    # ``read(n)`` calls read the whole file, bypassing the corpus cap
    # (search-generation-patterns S3). Callers today pass ``CORPUS_TEXT_LIMIT``
    # or smaller, but the guard keeps the API safe against future regressions.
    if limit <= 0:
        return ""
    limit = min(limit, CORPUS_TEXT_LIMIT)
    raw: bytes | None = None
    if sys.platform != "win32":
        if scan_root is not None:
            # Anchored traversal: walks every intermediate component between
            # scan_root and path with O_NOFOLLOW (#286/#325).
            try:
                relative = path.relative_to(scan_root)
                with SafeDir.open_root(scan_root) as root:
                    fd = root.open_anchored_reader(relative)
                    try:
                        fileobj = os.fdopen(fd, "rb", closefd=True)
                    except OSError:
                        os.close(fd)
                        raise
                    with fileobj:
                        raw = fileobj.read(limit)
            except SymlinkRejected as exc:
                logger.warning("Refused to read symlinked file {}: {}", path, exc)
                return ""
            except NotImplementedError:
                # SafeDir's POSIX primitives unavailable; fall through to
                # legacy path-based open below.
                logger.debug("SafeDir unavailable; using legacy reader for {}", path.name)
            except (OSError, ValueError):
                # ValueError covers path.relative_to() when path escapes
                # scan_root, or SafeDir's name-validation rejection.
                return ""
        else:
            try:
                with SafeDir.open_root(path.parent) as safe_dir:
                    fd = safe_dir.open_for_reader(path.name)
                    # fdopen takes ownership only once it returns; explicitly
                    # close the bare fd if fdopen itself raises.
                    try:
                        fileobj = os.fdopen(fd, "rb", closefd=True)
                    except OSError:
                        os.close(fd)
                        raise
                    with fileobj:
                        raw = fileobj.read(limit)
            except SymlinkRejected as exc:
                logger.warning("Refused to read symlinked file {}: {}", path, exc)
                return ""
            except NotImplementedError:
                # SafeDir's POSIX primitives unavailable; fall through to
                # legacy path-based open below.
                logger.debug("SafeDir unavailable; using legacy reader for {}", path.name)
            except (OSError, ValueError):
                # ValueError covers SafeDir's name-validation rejection
                # (filenames with backslash / NUL / path separators).
                return ""
    if raw is None:
        try:
            with path.open("rb") as fh:  # safedir: ok — Windows / NotImplementedError fallback
                raw = fh.read(limit)
        except OSError:
            return ""
    peek_size = min(CORPUS_BINARY_PEEK, len(raw))
    if b"\x00" in raw[:peek_size]:
        return ""  # binary file — skip content extraction
    return raw.decode(errors="replace")


def _rrf_fuse(
    *ranked_lists: list[tuple[Path, float]],
    top_k: int,
    k: int = 60,
) -> list[tuple[Path, float]]:
    """Fuse multiple ranked lists using Reciprocal Rank Fusion.

    Args:
        *ranked_lists: Variable number of (path, score) lists, each sorted
            by descending score.
        top_k: Maximum number of results to return.
        k: RRF smoothing constant (default 60 per Cormack et al. 2009).

    Returns:
        Fused list of (path, rrf_score) tuples sorted by descending score,
        at most *top_k* entries.
    """
    if k <= 0:
        raise ValueError(f"RRF smoothing constant k must be positive, got {k}")
    fused: dict[Path, float] = {}
    for ranked in ranked_lists:
        for rank, (path, _) in enumerate(ranked, start=1):
            fused[path] = fused.get(path, 0.0) + 1.0 / (k + rank)

    sorted_results = sorted(fused.items(), key=lambda item: item[1], reverse=True)
    return [(path, score) for path, score in sorted_results[:top_k]]


class HybridRetriever:
    """RRF-fused hybrid retriever combining BM25 and TF-IDF vector indices.

    Implements :class:`RetrieverProtocol`.  The corpus must be supplied via
    :meth:`index` before calling :meth:`retrieve`.

    Ranking is based on Reciprocal Rank Fusion: results from both indices are
    merged using ``score = sum(1 / (k + rank))`` across all lists.

    Example::

        retriever = HybridRetriever()
        retriever.index(
            ["quarterly finance report", "meeting notes about budget"],
            [Path("finance.txt"), Path("meeting.txt")],
        )
        results = retriever.retrieve("quarterly budget", top_k=5)

    Args:
        bm25: Optional pre-constructed :class:`BM25Index` instance.
        vector: Optional pre-constructed :class:`VectorIndex` instance.
        k: RRF smoothing constant (default 60).
    """

    def __init__(
        self,
        bm25: BM25Index | None = None,
        vector: VectorIndex | None = None,
        k: int = 60,
    ) -> None:
        """Initialise the hybrid retriever."""
        if k <= 0:
            raise ValueError(f"RRF smoothing constant k must be positive, got {k}")
        self._bm25 = bm25 if bm25 is not None else BM25Index()
        self._vector = vector if vector is not None else VectorIndex()
        self._k = k
        self._initialized = False
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # RetrieverProtocol
    # ------------------------------------------------------------------

    @property
    def is_initialized(self) -> bool:
        """True after :meth:`index` or :meth:`initialize` has been called."""
        with self._lock:
            return self._initialized

    def initialize(self) -> None:
        """Mark the retriever as initialised.

        Call :meth:`index` to supply the corpus before calling
        :meth:`retrieve`.  :meth:`initialize` alone does not load any data.
        """
        with self._lock:
            self._initialized = True

    def retrieve(self, query: str, top_k: int = 10) -> list[tuple[Path, float]]:
        """Return at most *top_k* (path, rrf_score) pairs, highest first.

        Fuses BM25 and vector rankings using Reciprocal Rank Fusion.
        Returns an empty list when the corpus has not been indexed yet.

        Args:
            query: Free-text search query.
            top_k: Maximum number of results to return.

        Returns:
            RRF-fused list of (path, score) tuples sorted by descending score.
        """
        if top_k <= 0:
            return []

        with self._lock:
            if not self._initialized:
                logger.warning("HybridRetriever.retrieve called before index(); returning []")
                return []
            bm25 = self._bm25
            vector = self._vector
            k = self._k

        # Fetch more candidates than top_k so RRF has enough material to fuse.
        candidate_k = min(top_k * 4, 200)
        bm25_results = bm25.search(query, top_k=candidate_k)
        vector_results = vector.search(query, top_k=candidate_k)

        if not bm25_results and not vector_results:
            return []

        fused = _rrf_fuse(bm25_results, vector_results, top_k=top_k, k=k)
        logger.debug(
            "HybridRetriever: bm25={}, vector={}, fused={}",
            len(bm25_results),
            len(vector_results),
            len(fused),
        )
        return fused

    def cleanup(self) -> None:
        """Release held resources (no-op for in-memory indices)."""
        with self._lock:
            self._initialized = False

    # ------------------------------------------------------------------
    # Corpus management (not part of RetrieverProtocol)
    # ------------------------------------------------------------------

    def index(self, documents: list[str], paths: list[Path]) -> None:
        """Build both BM25 and vector indices from *documents* and *paths*.

        After this call :attr:`is_initialized` is ``True`` and
        :meth:`retrieve` may be called.

        If the vector index raises ``ValueError`` during build (e.g. corpus too
        small for the TF-IDF vectorizer, or all terms pruned by ``max_df``),
        the retriever falls back to BM25-only mode and logs a warning rather
        than raising.

        Args:
            documents: Textual representation of each file (name + content).
            paths: Corresponding file paths; must have the same length.

        Raises:
            ValueError: If *documents* and *paths* have different lengths.
        """
        if len(documents) != len(paths):
            raise ValueError(
                f"documents ({len(documents)}) and paths ({len(paths)}) must have equal length"
            )
        # Build indices outside the lock (potentially slow), then swap under lock.
        new_bm25 = BM25Index()
        new_vector = VectorIndex()
        if not documents:
            with self._lock:
                self._bm25 = new_bm25
                self._vector = new_vector
                self._initialized = True
            logger.debug("HybridRetriever: indexed 0 documents (empty corpus)")
            return
        new_bm25.index(documents, paths)
        try:
            new_vector.index(documents, paths)
        except ValueError as exc:
            # Corpus may be too small for the TF-IDF vectorizer (e.g. < 2 documents,
            # or max_df pruning removes all terms).  Fall back to BM25-only retrieval.
            logger.warning(
                "HybridRetriever: vector index build failed (falling back to BM25-only): {}",
                exc,
            )
        with self._lock:
            self._bm25 = new_bm25
            self._vector = new_vector
            self._initialized = True
        logger.debug("HybridRetriever: indexed {} documents", len(paths))

    @property
    def corpus_size(self) -> int:
        """Number of documents currently indexed."""
        return self._bm25.size


# Verify structural conformance at import time.
# NOTE: issubclass() cannot be used with RetrieverProtocol because it has a
# property member (is_initialized); isinstance() on an instance is used instead.
# Guarded by ImportError so the module can be imported when optional search
# dependencies (rank-bm25, scikit-learn) are not installed.
try:
    assert isinstance(HybridRetriever(), RetrieverProtocol)
except ImportError:
    pass  # optional deps absent — skip conformance check
