"""Integration tests for services/search modules.

Covers:
- read_text_safe: normal text file, binary file, OSError, custom limit
- _rrf_fuse: basic fusion, deduplication, top_k limit, invalid k
- HybridRetriever: index + retrieve, empty corpus, retrieve before index,
  top_k=0, corpus_size, cleanup, single-document fallback (BM25-only),
  length mismatch raises ValueError, invalid k raises ValueError
- EmbeddingCache: cache miss (compute called), cache hit (compute not called),
  mtime-based invalidation, model-change invalidation, prune orphan rows,
  stats, context manager, file not found
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# read_text_safe
# ---------------------------------------------------------------------------


class TestReadTextSafe:
    def test_reads_text_file_content(self, tmp_path: Path) -> None:
        from file_organizer.services.search.hybrid_retriever import read_text_safe

        f = tmp_path / "notes.txt"
        f.write_text("hello world", encoding="utf-8")
        result = read_text_safe(f)
        assert result == "hello world"

    def test_returns_empty_for_binary_file(self, tmp_path: Path) -> None:
        from file_organizer.services.search.hybrid_retriever import read_text_safe

        f = tmp_path / "data.bin"
        f.write_bytes(b"\x00\x01\x02\x03" * 200)
        result = read_text_safe(f)
        assert result == ""

    def test_returns_empty_for_missing_file(self, tmp_path: Path) -> None:
        from file_organizer.services.search.hybrid_retriever import read_text_safe

        result = read_text_safe(tmp_path / "ghost.txt")
        assert result == ""

    def test_respects_limit_parameter(self, tmp_path: Path) -> None:
        from file_organizer.services.search.hybrid_retriever import read_text_safe

        f = tmp_path / "long.txt"
        f.write_text("A" * 1000, encoding="utf-8")
        result = read_text_safe(f, limit=10)
        assert len(result) == 10

    def test_default_limit_is_4096(self, tmp_path: Path) -> None:
        from file_organizer.services.search.hybrid_retriever import CORPUS_TEXT_LIMIT

        assert CORPUS_TEXT_LIMIT == 4096


# ---------------------------------------------------------------------------
# _rrf_fuse
# ---------------------------------------------------------------------------


class TestRrfFuse:
    def test_basic_fusion_of_two_lists(self) -> None:
        from file_organizer.services.search.hybrid_retriever import _rrf_fuse

        list_a = [(Path("a.txt"), 0.9), (Path("b.txt"), 0.5)]
        list_b = [(Path("b.txt"), 0.8), (Path("a.txt"), 0.4)]
        fused = _rrf_fuse(list_a, list_b, top_k=5)
        assert len(fused) == 2
        paths = [p for p, _ in fused]
        assert Path("a.txt") in paths
        assert Path("b.txt") in paths

    def test_document_in_both_lists_ranks_higher(self) -> None:
        from file_organizer.services.search.hybrid_retriever import _rrf_fuse

        common = Path("common.txt")
        unique = Path("unique.txt")
        list_a = [(common, 0.9), (unique, 0.5)]
        list_b = [(common, 0.8)]
        fused = _rrf_fuse(list_a, list_b, top_k=2)
        assert fused[0][0] == common

    def test_top_k_truncates_results(self) -> None:
        from file_organizer.services.search.hybrid_retriever import _rrf_fuse

        paths = [Path(f"{i}.txt") for i in range(10)]
        list_a = [(p, float(10 - i)) for i, p in enumerate(paths)]
        fused = _rrf_fuse(list_a, top_k=3)
        assert len(fused) == 3

    def test_empty_lists_returns_empty(self) -> None:
        from file_organizer.services.search.hybrid_retriever import _rrf_fuse

        result = _rrf_fuse([], [], top_k=5)
        assert result == []

    def test_invalid_k_raises_value_error(self) -> None:
        from file_organizer.services.search.hybrid_retriever import _rrf_fuse

        with pytest.raises(ValueError, match="k must be positive"):
            _rrf_fuse([(Path("a.txt"), 1.0)], top_k=5, k=0)

    def test_scores_are_floats(self) -> None:
        from file_organizer.services.search.hybrid_retriever import _rrf_fuse

        list_a = [(Path("x.txt"), 0.9)]
        fused = _rrf_fuse(list_a, top_k=1)
        assert all(isinstance(score, float) for _, score in fused)


# ---------------------------------------------------------------------------
# HybridRetriever
# ---------------------------------------------------------------------------


class TestHybridRetriever:
    @pytest.fixture(autouse=True)
    def _require_search_deps(self) -> None:
        pytest.importorskip("rank_bm25")
        pytest.importorskip("sklearn")

    def _make_retriever(self, k: int = 60):
        from file_organizer.services.search.hybrid_retriever import HybridRetriever

        return HybridRetriever(k=k)

    def test_retrieve_before_index_returns_empty(self) -> None:
        r = self._make_retriever()
        assert r.retrieve("anything") == []

    def test_is_initialized_false_before_index(self) -> None:
        r = self._make_retriever()
        assert r.is_initialized is False

    def test_initialize_marks_as_initialized(self) -> None:
        r = self._make_retriever()
        r.initialize()
        assert r.is_initialized is True

    def test_index_and_retrieve_returns_results(self, tmp_path: Path) -> None:
        r = self._make_retriever()
        docs = [
            "quarterly finance report budget analysis",
            "meeting notes project status update",
            "python script data processing pipeline",
        ]
        paths = [tmp_path / "finance.txt", tmp_path / "meeting.txt", tmp_path / "script.py"]
        r.index(docs, paths)
        assert r.is_initialized is True
        results = r.retrieve("finance budget", top_k=2)
        assert len(results) >= 1
        assert all(isinstance(p, Path) and isinstance(s, float) for p, s in results)

    def test_corpus_size_after_index(self, tmp_path: Path) -> None:
        r = self._make_retriever()
        paths = [tmp_path / f"{i}.txt" for i in range(3)]
        r.index(["doc one", "doc two", "doc three"], paths)
        assert r.corpus_size == 3

    def test_top_k_zero_returns_empty(self, tmp_path: Path) -> None:
        r = self._make_retriever()
        paths = [tmp_path / "a.txt"]
        r.index(["some text"], paths)
        assert r.retrieve("some", top_k=0) == []

    def test_empty_corpus_returns_empty(self) -> None:
        r = self._make_retriever()
        r.index([], [])
        assert r.is_initialized is True
        assert r.retrieve("anything", top_k=5) == []

    def test_length_mismatch_raises_value_error(self, tmp_path: Path) -> None:
        r = self._make_retriever()
        with pytest.raises(ValueError, match="equal length"):
            r.index(["doc a", "doc b"], [tmp_path / "a.txt"])

    def test_invalid_k_raises_value_error(self) -> None:
        from file_organizer.services.search.hybrid_retriever import HybridRetriever

        with pytest.raises(ValueError, match="k must be positive"):
            HybridRetriever(k=0)

    def test_cleanup_marks_uninitialized(self, tmp_path: Path) -> None:
        r = self._make_retriever()
        r.index(["doc a"], [tmp_path / "a.txt"])
        assert r.is_initialized is True
        r.cleanup()
        assert r.is_initialized is False

    def test_single_document_bm25_only_fallback(self, tmp_path: Path) -> None:
        r = self._make_retriever()
        paths = [tmp_path / "only.txt"]
        r.index(["the quick brown fox"], paths)
        results = r.retrieve("quick fox", top_k=5)
        assert isinstance(results, list)
        assert all(isinstance(p, Path) and isinstance(s, float) for p, s in results)


# ---------------------------------------------------------------------------
# EmbeddingCache
# ---------------------------------------------------------------------------


class TestEmbeddingCache:
    def _make_cache(self, tmp_path: Path, model: str = "test-model"):
        from file_organizer.services.search.embedding_cache import EmbeddingCache

        db = tmp_path / "test_cache.db"
        return EmbeddingCache(db_path=db, model=model)

    def test_cache_miss_calls_compute(self, tmp_path: Path) -> None:
        cache = self._make_cache(tmp_path)
        f = tmp_path / "doc.txt"
        f.write_text("hello world", encoding="utf-8")

        compute = MagicMock(return_value=np.array([0.1, 0.2, 0.3]))
        result = cache.get_or_compute(f, compute=compute)

        compute.assert_called_once()
        assert isinstance(result, np.ndarray)
        assert result.shape == (3,)
        cache.close()

    def test_cache_hit_does_not_call_compute(self, tmp_path: Path) -> None:
        cache = self._make_cache(tmp_path)
        f = tmp_path / "doc.txt"
        f.write_text("hello world", encoding="utf-8")

        compute = MagicMock(return_value=np.array([0.1, 0.2, 0.3]))
        cache.get_or_compute(f, compute=compute)
        cache.get_or_compute(f, compute=compute)

        compute.assert_called_once()
        cache.close()

    def test_mtime_change_invalidates_cache(self, tmp_path: Path) -> None:
        import os

        cache = self._make_cache(tmp_path)
        f = tmp_path / "doc.txt"
        f.write_text("original content", encoding="utf-8")

        compute = MagicMock(
            side_effect=lambda text: np.array([1.0] if "original" in text else [2.0])
        )
        cache.get_or_compute(f, compute=compute)

        # Update file content then advance mtime by 2 seconds to invalidate cache
        f.write_text("updated content", encoding="utf-8")
        new_mtime = f.stat().st_mtime + 2.0
        os.utime(f, (new_mtime, new_mtime))
        cache.get_or_compute(f, compute=compute)

        assert compute.call_count == 2
        cache.close()

    def test_model_change_invalidates_cache(self, tmp_path: Path) -> None:
        from file_organizer.services.search.embedding_cache import EmbeddingCache

        f = tmp_path / "doc.txt"
        f.write_text("some text", encoding="utf-8")
        db = tmp_path / "shared.db"

        compute_v1 = MagicMock(return_value=np.array([1.0, 0.0]))
        cache_v1 = EmbeddingCache(db_path=db, model="model-v1")
        cache_v1.get_or_compute(f, compute=compute_v1)
        cache_v1.close()

        compute_v2 = MagicMock(return_value=np.array([0.0, 1.0]))
        cache_v2 = EmbeddingCache(db_path=db, model="model-v2")
        cache_v2.get_or_compute(f, compute=compute_v2)
        cache_v2.close()

        compute_v2.assert_called_once()

    def test_prune_removes_orphan_rows(self, tmp_path: Path) -> None:
        cache = self._make_cache(tmp_path)
        f = tmp_path / "soon_gone.txt"
        f.write_text("temporary content", encoding="utf-8")

        compute = MagicMock(return_value=np.array([0.5]))
        cache.get_or_compute(f, compute=compute)

        stats_before = cache.stats()
        assert stats_before["entries"] == 1

        f.unlink()
        pruned = cache.prune()
        assert pruned == 1

        stats_after = cache.stats()
        assert stats_after["entries"] == 0
        cache.close()

    def test_stats_returns_expected_keys(self, tmp_path: Path) -> None:
        cache = self._make_cache(tmp_path)
        stats = cache.stats()
        assert "entries" in stats
        assert "model" in stats
        assert stats["model"] == "test-model"
        assert stats["entries"] == 0
        cache.close()

    def test_db_path_property(self, tmp_path: Path) -> None:
        db = tmp_path / "my.db"
        from file_organizer.services.search.embedding_cache import EmbeddingCache

        cache = EmbeddingCache(db_path=db)
        assert cache.db_path == db
        cache.close()

    def test_context_manager_closes_on_exit(self, tmp_path: Path) -> None:
        from file_organizer.services.search.embedding_cache import EmbeddingCache

        db = tmp_path / "ctx.db"
        with EmbeddingCache(db_path=db) as cache:
            stats = cache.stats()
            assert stats["entries"] == 0

    def test_file_not_found_raises(self, tmp_path: Path) -> None:
        cache = self._make_cache(tmp_path)
        missing = tmp_path / "missing.txt"
        with pytest.raises(FileNotFoundError):
            cache.get_or_compute(missing, compute=lambda text: np.array([0.0]))
        cache.close()
