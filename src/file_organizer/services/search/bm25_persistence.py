"""BM25 index persistence layer.

Provides disk-based persistence for BM25Okapi indexes using pickle serialization.
Allows saving and loading of fitted indexes to avoid rebuilding on each startup
for large document collections.
"""

from __future__ import annotations

import pickle
from pathlib import Path

from loguru import logger


class BM25Persistence:
    """Handles serialization and deserialization of BM25 indexes.

    Uses pickle to persist BM25Okapi instances and their associated metadata
    to disk, enabling faster startup times for large document collections.

    Example::

        persistence = BM25Persistence()
        persistence.save(bm25_index, paths, cache_path)
        loaded_index, loaded_paths = persistence.load(cache_path)
    """

    def save(
        self,
        bm25_index: object,
        paths: list[Path],
        cache_path: Path,
    ) -> None:
        """Save a BM25 index and its paths to disk.

        Args:
            bm25_index: The fitted BM25Okapi instance to persist.
            paths: List of file paths corresponding to indexed documents.
            cache_path: Path where the serialized index will be saved.

        Raises:
            OSError: If the file cannot be written.
            pickle.PicklingError: If the index cannot be serialized.
        """
        if bm25_index is None:
            logger.warning("Cannot save None BM25 index")
            return

        try:
            # Ensure parent directory exists
            cache_path.parent.mkdir(parents=True, exist_ok=True)

            # Save both the index and paths together
            data = {
                "bm25_index": bm25_index,
                "paths": paths,
            }

            with open(cache_path, "wb") as f:
                pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)

            logger.info(
                "Saved BM25 index with {} documents to {}",
                len(paths),
                cache_path,
            )

        except (OSError, pickle.PicklingError) as exc:
            logger.error("Failed to save BM25 index to {}: {}", cache_path, exc)
            raise

    def load(self, cache_path: Path) -> tuple[object | None, list[Path]]:
        """Load a BM25 index and its paths from disk.

        Args:
            cache_path: Path to the serialized index file.

        Returns:
            A tuple of (bm25_index, paths). Returns (None, []) if the file
            does not exist or cannot be loaded.

        Raises:
            OSError: If the file cannot be read.
            pickle.UnpicklingError: If the file cannot be deserialized.
        """
        if not cache_path.exists():
            logger.debug("BM25 cache file does not exist: {}", cache_path)
            return None, []

        try:
            with open(cache_path, "rb") as f:
                data = pickle.load(f)

            # Validate loaded data structure
            if not isinstance(data, dict):
                logger.warning("Invalid BM25 cache format: expected dict, got {}", type(data).__name__)
                return None, []

            bm25_index = data.get("bm25_index")
            paths = data.get("paths", [])

            if not isinstance(paths, list):
                logger.warning("Invalid paths format in BM25 cache: expected list, got {}", type(paths).__name__)
                return None, []

            logger.info(
                "Loaded BM25 index with {} documents from {}",
                len(paths),
                cache_path,
            )

            return bm25_index, paths

        except (OSError, pickle.UnpicklingError) as exc:
            logger.error("Failed to load BM25 index from {}: {}", cache_path, exc)
            raise

    def delete(self, cache_path: Path) -> None:
        """Delete a persisted BM25 index file.

        Args:
            cache_path: Path to the serialized index file to delete.
        """
        if not cache_path.exists():
            logger.debug("BM25 cache file does not exist, nothing to delete: {}", cache_path)
            return

        try:
            cache_path.unlink()
            logger.info("Deleted BM25 cache file: {}", cache_path)

        except OSError as exc:
            logger.error("Failed to delete BM25 cache file {}: {}", cache_path, exc)
            raise

    def is_valid(self, cache_path: Path) -> bool:
        """Check if a persisted index file exists and is valid.

        Args:
            cache_path: Path to the serialized index file.

        Returns:
            True if the file exists and contains valid data, False otherwise.
        """
        if not cache_path.exists():
            return False

        try:
            with open(cache_path, "rb") as f:
                data = pickle.load(f)

            # Basic validation: check structure
            if not isinstance(data, dict):
                return False

            if "bm25_index" not in data or "paths" not in data:
                return False

            if not isinstance(data["paths"], list):
                return False

            return True

        except (OSError, pickle.UnpicklingError, EOFError):
            return False
