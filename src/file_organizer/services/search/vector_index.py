"""Vector similarity index wrapping DocumentEmbedder and SemanticAnalyzer.

Reuses the TF-IDF vectorization and cosine-similarity infrastructure from
``services/deduplication/`` rather than re-implementing it.  When an Ollama
embedding model is available the index can be upgraded to use semantic
embeddings (``nomic-embed-text`` or similar); it falls back gracefully to
TF-IDF when Ollama is unreachable.

This module deliberately does NOT import Ollama at module load time so that
the class remains usable in environments without a running Ollama instance.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from loguru import logger

from file_organizer.services.deduplication.embedder import DocumentEmbedder
from file_organizer.services.deduplication.semantic import SemanticAnalyzer


class VectorIndex:
    """TF-IDF vector index implementing :class:`IndexProtocol`.

    Wraps :class:`DocumentEmbedder` (vectorization) and
    :class:`SemanticAnalyzer` (cosine similarity search) from the
    deduplication layer to provide ranked retrieval.

    Example::

        idx = VectorIndex()
        idx.index(["quarterly report contents …", "meeting notes …"], paths)
        results = idx.search("financial summary", top_k=5)
    """

    def __init__(self, similarity_threshold: float = 0.0) -> None:
        """Initialise the vector index.

        Args:
            similarity_threshold: Minimum cosine similarity for a result to
                be returned.  Defaults to ``0.0`` (return all results with
                any non-zero similarity; zero-similarity results are always
                excluded as they indicate out-of-vocabulary queries).
        """
        self._embedder = DocumentEmbedder()
        self._analyzer = SemanticAnalyzer(threshold=max(similarity_threshold, 0.0))
        self._paths: list[Path] = []
        self._matrix: np.ndarray | None = None  # shape (n_docs, n_features)

    # ------------------------------------------------------------------
    # IndexProtocol
    # ------------------------------------------------------------------

    def index(self, documents: list[str], paths: list[Path]) -> None:
        """Build the TF-IDF index from *documents* and *paths*.

        Args:
            documents: Text content for each file (name + body).
            paths: Corresponding file paths; must have the same length.

        Raises:
            ValueError: If *documents* and *paths* have different lengths or
                the document list is empty.
        """
        if len(documents) != len(paths):
            raise ValueError(
                f"documents ({len(documents)}) and paths ({len(paths)}) must have equal length"
            )
        if not documents:
            self._paths = []
            self._matrix = None
            return

        self._matrix = self._embedder.fit_transform(documents)
        self._paths = list(paths)
        logger.debug("VectorIndex: indexed {} documents", len(paths))

    def search(self, query: str, top_k: int = 10) -> list[tuple[Path, float]]:
        """Return at most *top_k* (path, cosine-similarity) pairs.

        Returns an empty list if :meth:`index` has not been called or the
        corpus is empty.

        Args:
            query: Free-text search query.
            top_k: Maximum number of results to return.

        Returns:
            List of (path, score) tuples sorted by descending similarity,
            filtered to scores above ``similarity_threshold``.
        """
        if top_k <= 0:
            return []
        if self._matrix is None or not self._paths:
            return []

        try:
            query_vec = self._embedder.transform(query)
        except ValueError as exc:
            logger.warning("VectorIndex: failed to embed query: {}", exc)
            return []

        return self._analyzer.find_similar_to_query(
            query_embedding=query_vec,
            document_embeddings=self._matrix,
            paths=self._paths,
            top_k=top_k,
            min_similarity=self._analyzer.threshold,
        )

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    @property
    def size(self) -> int:
        """Number of documents currently indexed."""
        return len(self._paths)
