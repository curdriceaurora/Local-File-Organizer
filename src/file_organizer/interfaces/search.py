"""Protocol definitions for search and retrieval contracts.

Defines structural interfaces for BM25/vector indices, hybrid retrievers,
and embedding caches used by the hybrid search pipeline.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class IndexProtocol(Protocol):
    """Structural contract for keyword or semantic indices.

    Implementations must support building/updating an index from a corpus
    and returning ranked results for a query.
    """

    def index(self, documents: list[str], paths: list[Path]) -> None:
        """Build or update the index from *documents*.

        *documents* and *paths* must have the same length: each document is
        the textual representation of the file at the corresponding path.
        """
        ...

    def search(self, query: str, top_k: int = 10) -> list[tuple[Path, float]]:
        """Return at most *top_k* results as (path, score) pairs, highest first.

        Scores are index-specific and need not be normalised to [0, 1].
        """
        ...


@runtime_checkable
class RetrieverProtocol(Protocol):
    """Structural contract for retrieval systems (BM25, vector, hybrid).

    Follows the same initialize / retrieve / cleanup lifecycle as model
    protocols so it can be managed by :class:`ModelManager`.
    """

    @property
    def is_initialized(self) -> bool:
        """Return ``True`` after :meth:`initialize` has completed."""
        ...

    def initialize(self) -> None:
        """Prepare the retriever (load indices, models, caches, etc.)."""
        ...

    def retrieve(self, query: str, top_k: int = 10) -> list[tuple[Path, float]]:
        """Return at most *top_k* ranked (path, score) pairs, highest first."""
        ...

    def cleanup(self) -> None:
        """Release all held resources (models, file handles, DB connections)."""
        ...


@runtime_checkable
class EmbeddingCacheProtocol(Protocol):
    """Structural contract for persistent embedding caches.

    Implementations must detect stale entries (file mtime changed) and
    prune orphan rows (file deleted) transparently.
    """

    def get_or_compute(
        self,
        path: Path,
        /,
        compute: Any,  # Callable[[str], np.ndarray] — typed loosely to avoid numpy import
    ) -> Any:  # np.ndarray
        """Return a cached embedding for *path*, or compute and cache it.

        *path* is positional-only to prevent callers from passing it as a
        keyword argument.

        The *compute* callable receives the file's text content and must
        return a numpy array.  Implementations are responsible for reading
        the file, checking mtime, and persisting the result.
        """
        ...

    def prune(self) -> int:
        """Remove orphan rows for files that no longer exist.

        Returns the number of rows deleted.
        """
        ...

    def close(self) -> None:
        """Flush any pending writes and close the underlying store."""
        ...
