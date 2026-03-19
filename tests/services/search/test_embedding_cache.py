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


@pytest.mark.ci
@pytest.mark.unit
class TestEmbeddingCacheProtocol:
    def test_implements_protocol(self, tmp_path: Path) -> None:
        cache = EmbeddingCache(tmp_path / "cache.db")
        assert isinstance(cache, EmbeddingCacheProtocol)
        cache.close()


# ---------------------------------------------------------------------------
# Basic get_or_compute
# ---------------------------------------------------------------------------


@pytest.mark.ci
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

    def test_file_deleted_between_stat_and_read_raises(self, tmp_path: Path) -> None:
        """FileNotFoundError propagated when file vanishes after stat() but before read_text()."""
        from unittest.mock import patch

        f = tmp_path / "vanishing.txt"
        f.write_text("hello")
        cache = EmbeddingCache(tmp_path / "cache.db")

        original_stat = f.stat()

        def _raise_on_read_text(*args: object, **kwargs: object) -> str:
            raise FileNotFoundError(f"File not found: {f}")

        with patch.object(type(f), "read_text", _raise_on_read_text):
            with pytest.raises(FileNotFoundError):
                cache.get_or_compute(f, compute=_dummy_compute)
        cache.close()
        _ = original_stat  # suppress unused variable warning

    def test_oserror_on_stat_raises(self, tmp_path: Path) -> None:
        """OSError from stat() is re-raised as OSError."""
        from unittest.mock import patch

        f = tmp_path / "inaccessible.txt"
        f.write_text("data")
        cache = EmbeddingCache(tmp_path / "cache.db")

        with patch.object(type(f), "stat", side_effect=OSError("permission denied")):
            with pytest.raises(OSError):
                cache.get_or_compute(f, compute=_dummy_compute)
        cache.close()


# ---------------------------------------------------------------------------
# Staleness / invalidation
# ---------------------------------------------------------------------------


@pytest.mark.ci
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


@pytest.mark.ci
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


@pytest.mark.ci
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


@pytest.mark.ci
@pytest.mark.unit
class TestTOCTOU:
    """Verify TOCTOU race-condition fix: no pre-existence check."""

    def test_nonexistent_file_raises_immediately(self, tmp_path: Path) -> None:
        cache = EmbeddingCache(tmp_path / "cache.db")
        missing = tmp_path / "no_such_file.txt"
        with pytest.raises(FileNotFoundError, match="File not found"):
            cache.get_or_compute(missing, compute=_dummy_compute)
        cache.close()

    def test_file_deleted_between_stat_and_read(self, tmp_path: Path) -> None:
        """Simulate file disappearing after stat succeeds."""
        f = tmp_path / "ephemeral.txt"
        f.write_text("here now")
        cache = EmbeddingCache(tmp_path / "cache.db")

        original_read_text = Path.read_text

        def _delete_then_read(self_path: Path, *args: object, **kwargs: object) -> str:
            if self_path == f:
                f.unlink()  # delete file before reading
            return original_read_text(self_path, *args, **kwargs)  # type: ignore[arg-type]

        import unittest.mock

        with unittest.mock.patch.object(Path, "read_text", _delete_then_read):
            with pytest.raises((FileNotFoundError, OSError)):
                cache.get_or_compute(f, compute=_dummy_compute)
        cache.close()


@pytest.mark.ci
@pytest.mark.unit
class TestBatchedPrune:
    """Verify prune uses batched iteration."""

    def test_prune_handles_many_entries(self, tmp_path: Path) -> None:
        cache = EmbeddingCache(tmp_path / "cache.db")
        # Insert 1200 entries directly, exceeding the batch_size=500 threshold
        n_total = 1200
        n_delete = 600
        for i in range(n_total):
            f = tmp_path / f"file_{i}.txt"
            f.write_text(f"content {i}")
            cache.get_or_compute(f, compute=_dummy_compute)

        # Delete 600 of the files
        for i in range(n_delete):
            (tmp_path / f"file_{i}.txt").unlink()

        pruned = cache.prune()
        assert pruned == n_delete
        assert cache.stats()["entries"] == n_total - n_delete
        cache.close()


@pytest.mark.ci
@pytest.mark.unit
class TestExceptionPaths:
    """Verify all exception-handling paths are covered."""

    def test_get_or_compute_stat_permission_error(self, tmp_path: Path) -> None:
        """Test OSError when path.stat() fails."""
        f = tmp_path / "restricted.txt"
        f.write_text("secret")
        cache = EmbeddingCache(tmp_path / "cache.db")

        import unittest.mock

        original_stat = Path.stat

        def _raise_on_stat(self_path: Path) -> object:
            if self_path == f:
                raise OSError("Permission denied")
            return original_stat(self_path)

        with unittest.mock.patch.object(Path, "stat", _raise_on_stat):
            with pytest.raises(OSError, match=r"Cannot access.*Permission denied"):
                cache.get_or_compute(f, compute=_dummy_compute)
        cache.close()

    def test_get_or_compute_read_permission_error(self, tmp_path: Path) -> None:
        """Test OSError when path.read_text() fails."""
        f = tmp_path / "readable_stat.txt"
        f.write_text("content")
        cache = EmbeddingCache(tmp_path / "cache.db")

        import unittest.mock

        original_read = Path.read_text

        def _raise_on_read(self_path: Path, *args: object, **kwargs: object) -> str:
            if self_path == f:
                raise OSError("Permission denied on read")
            return original_read(self_path, *args, **kwargs)  # type: ignore[arg-type]

        with unittest.mock.patch.object(Path, "read_text", _raise_on_read):
            with pytest.raises(OSError, match=r"Cannot read.*Permission denied on read"):
                cache.get_or_compute(f, compute=_dummy_compute)
        cache.close()

    def test_prune_batching_logic(self, tmp_path: Path) -> None:
        """Verify batched iteration in prune (tests loop continuation)."""
        cache = EmbeddingCache(tmp_path / "cache.db")
        # Insert more than batch_size (500) entries
        for i in range(520):
            f = tmp_path / f"file_{i:03d}.txt"
            f.write_text(f"content {i}")
            cache.get_or_compute(f, compute=_dummy_compute)

        # Delete all files
        for i in range(520):
            (tmp_path / f"file_{i:03d}.txt").unlink()

        # Prune should iterate through multiple batches
        pruned = cache.prune()
        assert pruned == 520
        assert cache.stats()["entries"] == 0
        cache.close()


@pytest.mark.ci
@pytest.mark.unit
class TestContextManager:
    def test_context_manager_closes(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.txt"
        f.write_text("cm test")
        with EmbeddingCache(tmp_path / "cache.db") as cache:
            result = cache.get_or_compute(f, compute=_dummy_compute)
        assert result is not None  # no exception
