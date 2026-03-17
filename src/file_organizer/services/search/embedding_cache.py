"""SQLite-backed persistent embedding cache.

Stores numpy embedding vectors keyed by absolute file path.  Entries are
automatically invalidated when a file's mtime changes and orphan rows are
pruned when the file no longer exists.

.. note::

   File paths are stored as **absolute paths** in the SQLite database.
   If the database file is shared or leaked it reveals the directory
   structure of the host machine.

Schema::

    CREATE TABLE IF NOT EXISTS embeddings (
        file_path  TEXT    PRIMARY KEY,
        embedding  BLOB    NOT NULL,
        model      TEXT    NOT NULL,
        mtime      REAL    NOT NULL,
        updated_at TEXT    NOT NULL
    )
"""

from __future__ import annotations

import io
import sqlite3
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from loguru import logger

from file_organizer.interfaces.search import EmbeddingCacheProtocol

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS embeddings (
    file_path  TEXT PRIMARY KEY,
    embedding  BLOB NOT NULL,
    model      TEXT NOT NULL,
    mtime      REAL NOT NULL,
    updated_at TEXT NOT NULL
)
"""


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _array_to_blob(arr: np.ndarray) -> bytes:
    buf = io.BytesIO()
    np.save(buf, arr, allow_pickle=False)
    return buf.getvalue()


def _blob_to_array(blob: bytes) -> np.ndarray:
    return np.load(io.BytesIO(blob), allow_pickle=False)


class EmbeddingCache:
    """SQLite-backed embedding cache implementing :class:`EmbeddingCacheProtocol`.

    Thread-safety: a :class:`threading.Lock` serializes all write operations
    (INSERT/UPDATE and prune deletes) on the shared SQLite connection.  The
    underlying file is opened in WAL mode so concurrent readers do not block
    writers, but callers must not share one ``EmbeddingCache`` instance across
    processes.

    Example::

        cache = EmbeddingCache(Path("~/.cache/fo/embeddings.db").expanduser())
        embedding = cache.get_or_compute(
            path,
            compute=lambda text: embedder.transform(text),
        )
    """

    def __init__(self, db_path: Path, model: str = "tfidf") -> None:
        """Open (or create) the SQLite cache at *db_path*.

        Orphan rows (entries whose file no longer exists) are pruned
        automatically on open.

        Args:
            db_path: Path to the SQLite database file.  Parent directory
                must exist.
            model: Identifier for the embedding model.  Stored in the
                ``model`` column; used to detect when the model changes.
        """
        self._db_path = db_path
        self._model = model
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(_CREATE_TABLE)
        self._conn.commit()
        pruned = self.prune()
        if pruned:
            logger.debug("EmbeddingCache pruned {} orphan rows on open", pruned)
        logger.debug("EmbeddingCache opened at {}", db_path)

    # ------------------------------------------------------------------
    # EmbeddingCacheProtocol
    # ------------------------------------------------------------------

    def get_or_compute(
        self,
        path: Path,
        /,
        compute: Callable[[str], np.ndarray],
    ) -> np.ndarray:
        """Return a cached embedding for *path*, computing it if necessary.

        The cache entry is invalidated when:
        - The file's mtime has changed since the entry was written.
        - The stored model identifier differs from ``self._model``.
        - The file does not exist (raises :exc:`FileNotFoundError`).

        .. note::

           Callers **must** validate *path* against allowed directories
           before calling this method.  The cache does not enforce path
           containment.

        Args:
            path: Absolute path to the file.
            compute: Callable that accepts the file's text content and
                returns a numpy array embedding.

        Returns:
            numpy array embedding for the file.

        Raises:
            FileNotFoundError: If *path* does not exist.
            OSError: If *path* cannot be read.
        """
        try:
            current_mtime = path.stat().st_mtime
        except FileNotFoundError:
            raise FileNotFoundError(f"File not found: {path}") from None
        except OSError as exc:
            raise OSError(f"Cannot access {path}: {exc}") from exc

        key = str(path.resolve())

        row = self._conn.execute(
            "SELECT embedding, model, mtime FROM embeddings WHERE file_path = ?",
            (key,),
        ).fetchone()

        if row is not None:
            blob, stored_model, stored_mtime = row
            if stored_model == self._model and abs(stored_mtime - current_mtime) < 1e-3:
                logger.debug("EmbeddingCache hit: {}", path.name)
                return _blob_to_array(blob)
            logger.debug("EmbeddingCache stale (mtime or model changed): {}", path.name)

        # Cache miss or stale — compute fresh embedding
        try:
            text = path.read_text(errors="replace")
        except FileNotFoundError:
            raise FileNotFoundError(f"File not found: {path}") from None
        except OSError as exc:
            raise OSError(f"Cannot read {path}: {exc}") from exc
        embedding = compute(text)

        blob = _array_to_blob(embedding)
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO embeddings (file_path, embedding, model, mtime, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(file_path) DO UPDATE SET
                    embedding  = excluded.embedding,
                    model      = excluded.model,
                    mtime      = excluded.mtime,
                    updated_at = excluded.updated_at
                """,
                (key, blob, self._model, current_mtime, _now_iso()),
            )
            self._conn.commit()
        logger.debug("EmbeddingCache stored: {}", path.name)
        return embedding

    def prune(self) -> int:
        """Remove rows whose file no longer exists on disk.

        Iterates in batches to avoid loading the entire table into memory.

        Returns:
            Number of rows deleted.
        """
        stale: list[str] = []
        batch_size = 500
        offset = 0
        while True:
            rows = self._conn.execute(
                "SELECT file_path FROM embeddings ORDER BY file_path LIMIT ? OFFSET ?",
                (batch_size, offset),
            ).fetchall()
            if not rows:
                break
            stale.extend(row[0] for row in rows if not Path(row[0]).exists())
            offset += batch_size
        if stale:
            with self._lock:
                self._conn.executemany(
                    "DELETE FROM embeddings WHERE file_path = ?",
                    [(p,) for p in stale],
                )
                self._conn.commit()
            logger.debug("EmbeddingCache pruned {} orphan rows", len(stale))
        return len(stale)

    def close(self) -> None:
        """Flush pending writes and close the SQLite connection."""
        try:
            self._conn.commit()
            self._conn.close()
        except sqlite3.Error as exc:  # best-effort cleanup; errors on close are non-actionable
            logger.debug("EmbeddingCache: error during close (ignored): {}", exc)

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    @property
    def db_path(self) -> Path:
        """Path to the underlying SQLite file."""
        return self._db_path

    def stats(self) -> dict[str, Any]:
        """Return basic cache statistics."""
        row = self._conn.execute(
            "SELECT COUNT(*) FROM embeddings WHERE model = ?",
            (self._model,),
        ).fetchone()
        entries = int(row[0]) if row is not None else 0
        return {"entries": entries, "model": self._model}

    def __enter__(self) -> EmbeddingCache:
        """Return self for use as a context manager."""
        return self

    def __exit__(self, *_: object) -> None:
        """Close the cache on context manager exit."""
        self.close()


# Verify structural conformance at import time.
assert issubclass(EmbeddingCache, EmbeddingCacheProtocol)
