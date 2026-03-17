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

from pathlib import Path

from loguru import logger

from file_organizer.interfaces.search import RetrieverProtocol
from file_organizer.services.search.bm25_index import BM25Index
from file_organizer.services.search.vector_index import VectorIndex

# ---------------------------------------------------------------------------
# Corpus helpers (shared by API router and CLI)
# ---------------------------------------------------------------------------

#: Maximum number of bytes read from each file for corpus building.
CORPUS_TEXT_LIMIT: int = 4096
#: Number of bytes inspected to decide whether a file is binary.
CORPUS_BINARY_PEEK: int = 512


def read_text_safe(path: Path, limit: int = CORPUS_TEXT_LIMIT) -> str:
    """Read up to *limit* bytes from *path* as text, skipping binary files.

    Reads only what is needed: opens the file in binary mode, reads at most
    *limit* bytes, inspects the first :data:`CORPUS_BINARY_PEEK` bytes for
    null bytes (binary sentinel), then decodes.

    Args:
        path: File to read.
        limit: Maximum number of bytes to read (may yield fewer characters for
            multi-byte encodings).

    Returns:
        Decoded text content, or an empty string if the file is binary or
        unreadable.
    """
    try:
        with path.open("rb") as fh:
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
        self._bm25 = bm25 if bm25 is not None else BM25Index()
        self._vector = vector if vector is not None else VectorIndex()
        self._k = k
        self._initialized = False

    # ------------------------------------------------------------------
    # RetrieverProtocol
    # ------------------------------------------------------------------

    @property
    def is_initialized(self) -> bool:
        """True after :meth:`index` or :meth:`initialize` has been called."""
        return self._initialized

    def initialize(self) -> None:
        """Mark the retriever as initialised.

        Call :meth:`index` to supply the corpus before calling
        :meth:`retrieve`.  :meth:`initialize` alone does not load any data.
        """
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
        if not self._initialized:
            logger.warning("HybridRetriever.retrieve called before index(); returning []")
            return []

        # Fetch more candidates than top_k so RRF has enough material to fuse.
        candidate_k = min(top_k * 4, 200)
        bm25_results = self._bm25.search(query, top_k=candidate_k)
        vector_results = self._vector.search(query, top_k=candidate_k)

        if not bm25_results and not vector_results:
            return []

        fused = _rrf_fuse(bm25_results, vector_results, top_k=top_k, k=self._k)
        logger.debug(
            "HybridRetriever: bm25={}, vector={}, fused={}",
            len(bm25_results),
            len(vector_results),
            len(fused),
        )
        return fused

    def cleanup(self) -> None:
        """Release held resources (no-op for in-memory indices)."""
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
        if not documents:
            self._bm25 = BM25Index()
            self._vector = VectorIndex()
            self._initialized = True
            logger.debug("HybridRetriever: indexed 0 documents (empty corpus)")
            return
        self._bm25.index(documents, paths)
        try:
            self._vector.index(documents, paths)
        except ValueError as exc:
            # Corpus may be too small for the TF-IDF vectorizer (e.g. < 2 documents,
            # or max_df pruning removes all terms).  Fall back to BM25-only retrieval.
            logger.warning(
                "HybridRetriever: vector index build failed (falling back to BM25-only): {}",
                exc,
            )
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
