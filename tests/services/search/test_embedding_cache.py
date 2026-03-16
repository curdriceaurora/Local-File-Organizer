"""Unit tests for EmbeddingCache."""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest

from file_organizer.interfaces.search import EmbeddingCacheProtocol
from file_organizer.services.search.embedding_cache import EmbeddingCache

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _dummy_compute(text: str) -> np.ndarray:
    """Deterministic fake embedding: mean byte value repeated 4 times."""
    val = float(sum(text.encode()) % 256) / 255.0
    return np.array([val, val, val, val], dtype=np.float32)


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestEmbeddingCacheProtocol:
    def test_implements_protocol(self, tmp_path: Path) -> None:
        cache = EmbeddingCache(tmp_path / "cache.db")
        assert isinstance(cache, EmbeddingCacheProtocol)
        cache.close()


# ---------------------------------------------------------------------------
# Basic get_or_compute
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetOrCompute:
    def test_computes_on_miss(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.txt"
        f.write_text("hello world")
        cache = EmbeddingCache(tmp_path / "cache.db")
        result = cache.get_or_compute(f, compute=_dummy_compute)
        assert isinstance(result, np.ndarray)
        assert result.shape == (4,)
        cache.close()

    def test_returns_same_value_on_hit(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.txt"
        f.write_text("hello world")
        cache = EmbeddingCache(tmp_path / "cache.db")
        first = cache.get_or_compute(f, compute=_dummy_compute)
        second = cache.get_or_compute(f, compute=_dummy_compute)
        np.testing.assert_array_equal(first, second)
        cache.close()

    def test_hit_does_not_call_compute_again(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.txt"
        f.write_text("hello")
        call_count = {"n": 0}

        def counting_compute(text: str) -> np.ndarray:
            call_count["n"] += 1
            return _dummy_compute(text)

        cache = EmbeddingCache(tmp_path / "cache.db")
        cache.get_or_compute(f, compute=counting_compute)
        cache.get_or_compute(f, compute=counting_compute)
        assert call_count["n"] == 1, "compute should only be called once on cache hit"
        cache.close()

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        cache = EmbeddingCache(tmp_path / "cache.db")
        with pytest.raises(FileNotFoundError):
            cache.get_or_compute(tmp_path / "nonexistent.txt", compute=_dummy_compute)
        cache.close()


# ---------------------------------------------------------------------------
# Staleness / invalidation
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestStaleness:
    def test_recomputes_on_mtime_change(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.txt"
        f.write_text("version 1")
        cache = EmbeddingCache(tmp_path / "cache.db")
        first = cache.get_or_compute(f, compute=_dummy_compute)

        # Modify content and force a guaranteed mtime bump via os.utime
        f.write_text("version 2 different content entirely")
        new_mtime = f.stat().st_mtime + 2.0
        os.utime(f, (new_mtime, new_mtime))

        second = cache.get_or_compute(f, compute=_dummy_compute)
        # Content changed → different embedding
        assert not np.array_equal(first, second), "Stale entry should be recomputed"
        cache.close()

    def test_recomputes_on_model_change(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.txt"
        f.write_text("same content")
        call_count = {"n": 0}

        def counting_compute(text: str) -> np.ndarray:
            call_count["n"] += 1
            return _dummy_compute(text)

        cache_a = EmbeddingCache(tmp_path / "cache.db", model="model_a")
        cache_a.get_or_compute(f, compute=counting_compute)
        cache_a.close()

        # Different model identifier → stale
        cache_b = EmbeddingCache(tmp_path / "cache.db", model="model_b")
        cache_b.get_or_compute(f, compute=counting_compute)
        cache_b.close()

        assert call_count["n"] == 2, "Should recompute when model changes"


# ---------------------------------------------------------------------------
# Pruning
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPrune:
    def test_prune_removes_deleted_files(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.txt"
        f.write_text("temporary file")
        cache = EmbeddingCache(tmp_path / "cache.db")
        cache.get_or_compute(f, compute=_dummy_compute)

        f.unlink()  # Delete the file
        deleted = cache.prune()
        assert deleted == 1
        cache.close()

    def test_prune_keeps_existing_files(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.txt"
        f.write_text("persisted")
        cache = EmbeddingCache(tmp_path / "cache.db")
        cache.get_or_compute(f, compute=_dummy_compute)
        deleted = cache.prune()
        assert deleted == 0
        cache.close()

    def test_prune_returns_zero_on_empty_cache(self, tmp_path: Path) -> None:
        cache = EmbeddingCache(tmp_path / "cache.db")
        assert cache.prune() == 0
        cache.close()


# ---------------------------------------------------------------------------
# Persistence across instances
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPersistence:
    def test_cache_survives_restart(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.txt"
        f.write_text("persisted content")
        db = tmp_path / "cache.db"
        call_count = {"n": 0}

        def counting_compute(text: str) -> np.ndarray:
            call_count["n"] += 1
            return _dummy_compute(text)

        # First "session"
        cache1 = EmbeddingCache(db)
        cache1.get_or_compute(f, compute=counting_compute)
        cache1.close()

        # Second "session" — same DB, should hit cache
        cache2 = EmbeddingCache(db)
        cache2.get_or_compute(f, compute=counting_compute)
        cache2.close()

        assert call_count["n"] == 1, "compute should be called once across sessions"

    def test_stats_reports_entry_count(self, tmp_path: Path) -> None:
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("alpha")
        f2.write_text("beta")
        cache = EmbeddingCache(tmp_path / "cache.db")
        cache.get_or_compute(f1, compute=_dummy_compute)
        cache.get_or_compute(f2, compute=_dummy_compute)
        stats = cache.stats()
        assert stats["entries"] == 2
        cache.close()


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestContextManager:
    def test_context_manager_closes(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.txt"
        f.write_text("cm test")
        with EmbeddingCache(tmp_path / "cache.db") as cache:
            result = cache.get_or_compute(f, compute=_dummy_compute)
        assert result is not None  # no exception
