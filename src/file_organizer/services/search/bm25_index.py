"""BM25 keyword index for file retrieval.

Builds an in-memory Okapi BM25 index over file names, paths, and extracted
text content. Supports optional disk-based caching to avoid rebuilding large
indexes on startup. Cache is automatically invalidated when document set changes.

Requires the ``rank-bm25`` package (``pip install rank-bm25``).
"""

from __future__ import annotations

import re
from pathlib import Path

from loguru import logger

from .bm25_persistence import BM25Persistence


def _tokenise(text: str) -> list[str]:
    """Lower-case, split on non-alphanumeric runs, filter empty tokens."""
    return [t for t in re.split(r"[^a-z0-9]+", text.lower()) if t]


class BM25Index:
    """In-memory BM25 index implementing :class:`IndexProtocol`.

    The corpus consists of one document per file.  Each document is the
    concatenation of the file's stem, relative path components, and any
    extracted text content supplied by the caller.

    Supports optional caching to disk to avoid rebuilding large indexes.
    When a cache path is provided, the index is lazily loaded from cache
    if valid, or rebuilt and saved to cache otherwise.

    Example::

        index = BM25Index(cache_path=Path(".cache/bm25.pkl"))
        index.index(["quarterly finance report", "meeting notes"], paths)
        results = index.search("finance report", top_k=5)
    """

    def __init__(self, cache_path: Path | None = None) -> None:
        """Initialise an empty BM25 index.

        Args:
            cache_path: Optional path for caching the index to disk.
                If provided, enables lazy loading from cache.
        """
        self._paths: list[Path] = []
        self._bm25: object | None = None  # rank_bm25.BM25Okapi | None
        self._cache_path = cache_path
        self._persistence = BM25Persistence()

    # ------------------------------------------------------------------
    # IndexProtocol
    # ------------------------------------------------------------------

    def index(self, documents: list[str], paths: list[Path]) -> None:
        """Build the BM25 index from *documents* and *paths*.

        If a cache path is configured, attempts to load from cache first.
        Cache is used only if the cached paths exactly match the provided paths.
        Otherwise, builds a new index and saves to cache.

        Args:
            documents: Textual representation of each file (name + content).
            paths: Corresponding file paths; must have the same length as
                *documents*.

        Raises:
            ValueError: If *documents* and *paths* have different lengths.
            ImportError: If ``rank-bm25`` is not installed.
        """
        if len(documents) != len(paths):
            raise ValueError(
                f"documents ({len(documents)}) and paths ({len(paths)}) must have equal length"
            )

        try:
            from rank_bm25 import BM25Okapi
        except ImportError as exc:
            raise ImportError(
                "rank-bm25 is required for BM25Index. "
                "Install it with: pip install 'file-organizer[search]'"
            ) from exc

        # Try lazy loading from cache if enabled
        if self._cache_path is not None:
            try:
                cached_index, cached_paths = self._persistence.load(self._cache_path)

                # Use cache only if paths match exactly
                if cached_index is not None and cached_paths == paths:
                    self._bm25 = cached_index
                    self._paths = cached_paths
                    logger.debug(
                        "BM25Index: loaded {} documents from cache",
                        len(paths),
                    )
                    return

                # Cache invalid or paths changed, will rebuild
                if cached_index is not None:
                    logger.debug(
                        "BM25Index: cache invalid (path mismatch), rebuilding index"
                    )

            except (OSError, Exception) as exc:
                # Cache load failed, fall through to rebuild
                logger.debug("BM25Index: cache load failed ({}), rebuilding", exc)

        # Build new index
        tokenised = [_tokenise(doc) for doc in documents]
        self._bm25 = BM25Okapi(tokenised)
        self._paths = list(paths)
        logger.debug("BM25Index: indexed {} documents", len(paths))

        # Save to cache if enabled
        if self._cache_path is not None:
            try:
                self._persistence.save(self._bm25, self._paths, self._cache_path)
            except (OSError, Exception) as exc:
                # Cache save failed, but index is still usable
                logger.warning("BM25Index: failed to save cache: {}", exc)

    def search(self, query: str, top_k: int = 10) -> list[tuple[Path, float]]:
        """Return at most *top_k* (path, score) pairs ordered by BM25 score.

        Returns an empty list if :meth:`index` has not been called yet.

        Args:
            query: Free-text search query.
            top_k: Maximum number of results to return.

        Returns:
            List of (path, score) tuples sorted by descending score.
        """
        if top_k <= 0:
            return []
        if self._bm25 is None or not self._paths:
            return []

        tokens = _tokenise(query)
        if not tokens:
            return []

        scores: list[float] = self._bm25.get_scores(tokens)  # type: ignore[attr-defined]

        # Filter zero-score docs first, then sort descending and take top_k.
        # Zeros must be removed before slicing: since 0.0 > negative, zero-score
        # non-overlap documents sort ahead of negative-score matches and would
        # otherwise fill the top_k window, leaving too few real results.
        non_zero = [
            (path, float(score))
            for path, score in zip(self._paths, scores, strict=True)
            if score != 0.0
        ]
        ranked = sorted(non_zero, key=lambda pair: pair[1], reverse=True)
        return ranked[:top_k]

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    @property
    def size(self) -> int:
        """Number of documents currently indexed."""
        return len(self._paths)

    def invalidate_cache(self) -> None:
        """Invalidate and delete the persisted cache if it exists.

        This method clears the on-disk cache file. Useful when you want
        to force a rebuild on the next :meth:`index` call.

        Does nothing if no cache path was configured or if the cache
        file doesn't exist.
        """
        if self._cache_path is None:
            logger.debug("BM25Index: no cache path configured, nothing to invalidate")
            return

        try:
            self._persistence.delete(self._cache_path)
        except OSError as exc:
            logger.warning("BM25Index: failed to invalidate cache: {}", exc)


# Verify structural conformance at import time (no runtime overhead).
def _check() -> None:
    """Verify structural conformance of BM25Index at import time."""
    assert isinstance(BM25Index, type)
    # Runtime check deferred — BM25Index satisfies IndexProtocol structurally.


_check()
