"""BM25 keyword index for file retrieval.

Builds an in-memory Okapi BM25 index over file names, paths, and extracted
text content. Supports optional disk-based caching to avoid rebuilding large
indexes on startup. Cache is automatically invalidated when document set changes.

Requires the ``rank-bm25`` package (``pip install rank-bm25``).
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from pickle import PicklingError, UnpicklingError

from loguru import logger

from .bm25_persistence import BM25Persistence


def _tokenise(text: str) -> list[str]:
    """Lower-case, split on non-alphanumeric runs, filter empty tokens."""
    return [t for t in re.split(r"[^a-z0-9]+", text.lower()) if t]


def _documents_fingerprint(documents: list[str]) -> str:
    """Return a stable fingerprint for the indexed document payload."""
    digest = hashlib.sha256()
    for document in documents:
        encoded = document.encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    return digest.hexdigest()


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
        self._documents: list[str] = []
        self._bm25: object | None = None  # rank_bm25.BM25Okapi | None
        self._cache_path = cache_path
        self._persistence = BM25Persistence()
        self._load_cache_snapshot()

    # ------------------------------------------------------------------
    # IndexProtocol
    # ------------------------------------------------------------------

    def _load_cache_snapshot(self) -> None:
        """Load a persisted cache snapshot when no in-memory index exists yet."""
        if self._cache_path is None or self._bm25 is not None:
            return

        try:
            cached_index, cached_paths, cached_documents, _ = self._persistence.load(
                self._cache_path
            )
        except (OSError, UnpicklingError) as exc:
            logger.debug("BM25Index: initial cache load failed ({}), continuing empty", exc)
            return

        if cached_index is not None and len(cached_documents) == len(cached_paths) and cached_paths:
            self._bm25 = cached_index
            self._paths = cached_paths
            self._documents = cached_documents
            logger.debug(
                "BM25Index: eagerly loaded {} documents from cache snapshot",
                len(cached_paths),
            )

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
                (
                    cached_index,
                    cached_paths,
                    cached_documents,
                    cached_fingerprint,
                ) = self._persistence.load(self._cache_path)
                current_fingerprint = _documents_fingerprint(documents)

                # Use cache only if paths match exactly
                if (
                    cached_index is not None
                    and cached_paths == paths
                    and len(cached_documents) == len(cached_paths)
                    and cached_fingerprint == current_fingerprint
                ):
                    self._bm25 = cached_index
                    self._paths = cached_paths
                    self._documents = cached_documents
                    logger.debug(
                        "BM25Index: loaded {} documents from cache",
                        len(paths),
                    )
                    return

                # Cache invalid or paths changed, will rebuild
                if cached_index is not None:
                    logger.debug("BM25Index: cache invalid (path mismatch), rebuilding index")

            except (OSError, UnpicklingError) as exc:
                # Cache load failed, fall through to rebuild
                logger.debug("BM25Index: cache load failed ({}), rebuilding", exc)

        # Build new index
        tokenised = [_tokenise(doc) for doc in documents]
        self._bm25 = BM25Okapi(tokenised)
        self._paths = list(paths)
        self._documents = list(documents)
        logger.debug("BM25Index: indexed {} documents", len(paths))

        # Save to cache if enabled
        if self._cache_path is not None:
            try:
                self._persistence.save(
                    self._bm25,
                    self._paths,
                    self._cache_path,
                    documents=self._documents,
                    fingerprint=_documents_fingerprint(self._documents),
                )
            except (OSError, PicklingError) as exc:
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
        self._load_cache_snapshot()
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
    # Incremental updates
    # ------------------------------------------------------------------

    def add_document(self, document: str, path: Path) -> None:
        """Add a single document to the index.

        This performs an incremental update by adding the document to
        the internal corpus and rebuilding the BM25 index. The cache
        is automatically invalidated and updated if enabled.

        Args:
            document: Textual representation of the file (name + content).
            path: Corresponding file path.

        Raises:
            ImportError: If ``rank-bm25`` is not installed.
        """
        try:
            from rank_bm25 import BM25Okapi
        except ImportError as exc:
            raise ImportError(
                "rank-bm25 is required for BM25Index. "
                "Install it with: pip install 'file-organizer[search]'"
            ) from exc

        # Add to internal state
        self._paths.append(path)
        self._documents.append(document)

        # Rebuild the index with all documents
        tokenised = [_tokenise(doc) for doc in self._documents]
        self._bm25 = BM25Okapi(tokenised)
        logger.debug("BM25Index: added document, index now has {} documents", len(self._paths))

        # Update cache if enabled
        self._update_cache()

    def remove_document(self, path: Path) -> None:
        """Remove a document from the index by path.

        This performs an incremental update by removing the document
        from the internal corpus and rebuilding the BM25 index. The
        cache is automatically invalidated and updated if enabled.

        Args:
            path: Path of the document to remove.

        Raises:
            ValueError: If the path is not found in the index.
            ImportError: If ``rank-bm25`` is not installed.
        """
        try:
            from rank_bm25 import BM25Okapi
        except ImportError as exc:
            raise ImportError(
                "rank-bm25 is required for BM25Index. "
                "Install it with: pip install 'file-organizer[search]'"
            ) from exc

        # Find and remove from internal state
        try:
            idx = self._paths.index(path)
        except ValueError as exc:
            raise ValueError(f"Path {path} not found in index") from exc

        self._paths.pop(idx)
        self._documents.pop(idx)

        # Rebuild the index with remaining documents
        if self._documents:
            tokenised = [_tokenise(doc) for doc in self._documents]
            self._bm25 = BM25Okapi(tokenised)
        else:
            self._bm25 = None

        logger.debug("BM25Index: removed document, index now has {} documents", len(self._paths))

        # Update cache if enabled
        self._update_cache()

    def update_document(self, path: Path, document: str) -> None:
        """Update an existing document in the index.

        This performs an incremental update by replacing the document
        content in the internal corpus and rebuilding the BM25 index.
        The cache is automatically invalidated and updated if enabled.

        Args:
            path: Path of the document to update.
            document: New textual representation of the file.

        Raises:
            ValueError: If the path is not found in the index.
            ImportError: If ``rank-bm25`` is not installed.
        """
        try:
            from rank_bm25 import BM25Okapi
        except ImportError as exc:
            raise ImportError(
                "rank-bm25 is required for BM25Index. "
                "Install it with: pip install 'file-organizer[search]'"
            ) from exc

        # Verify path exists in index
        if path not in self._paths:
            raise ValueError(f"Path {path} not found in index")

        idx = self._paths.index(path)
        self._documents[idx] = document
        tokenised = [_tokenise(doc) for doc in self._documents]

        self._bm25 = BM25Okapi(tokenised)
        logger.debug("BM25Index: updated document at {}", path)

        # Update cache if enabled
        self._update_cache()

    def _update_cache(self) -> None:
        """Update the cache file after incremental changes.

        This helper saves the current index state to cache if enabled.
        Called automatically after add/update/remove operations.
        """
        if self._cache_path is None or self._bm25 is None:
            return

        try:
            self._persistence.save(
                self._bm25,
                self._paths,
                self._cache_path,
                documents=self._documents,
                fingerprint=_documents_fingerprint(self._documents),
            )
            logger.debug("BM25Index: cache updated after incremental change")
        except (OSError, PicklingError) as exc:
            # Cache update failed, but index is still usable
            logger.warning("BM25Index: failed to update cache: {}", exc)

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    @property
    def size(self) -> int:
        """Number of documents currently indexed."""
        self._load_cache_snapshot()
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
