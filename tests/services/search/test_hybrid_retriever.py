"""Unit tests for HybridRetriever and _rrf_fuse."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import ANY, MagicMock

import pytest

from file_organizer.interfaces.search import RetrieverProtocol
from file_organizer.services.search.hybrid_retriever import HybridRetriever, _rrf_fuse

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_paths(n: int) -> list[Path]:
    tmp = Path(tempfile.gettempdir())
    return [tmp / f"doc_{i}.txt" for i in range(n)]


def _make_retriever_with_corpus(
    docs: list[str],
    paths: list[Path],
) -> HybridRetriever:
    r = HybridRetriever()
    r.index(docs, paths)
    return r


# ---------------------------------------------------------------------------
# _rrf_fuse unit tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRrfFuse:
    def test_empty_lists(self) -> None:
        result = _rrf_fuse([], [], top_k=5)
        assert result == []

    def test_single_list(self) -> None:
        paths = _make_paths(3)
        ranked = [(paths[0], 1.0), (paths[1], 0.5), (paths[2], 0.1)]
        result = _rrf_fuse(ranked, top_k=3)
        # Rank 1 gets highest RRF score
        assert result[0][0] == paths[0]
        assert result[1][0] == paths[1]
        assert result[2][0] == paths[2]

    def test_two_lists_agreement_boosts_score(self) -> None:
        """A path ranked high in both lists should outscore one ranked high in only one."""
        paths = _make_paths(4)
        # Both lists agree that paths[0] is #1
        list_a = [(paths[0], 1.0), (paths[1], 0.5)]
        list_b = [(paths[0], 0.9), (paths[2], 0.3)]
        result = _rrf_fuse(list_a, list_b, top_k=4)
        # paths[0] appears in both lists at rank 1 → highest fused score
        assert result[0][0] == paths[0]

    def test_top_k_limits_output(self) -> None:
        paths = _make_paths(10)
        ranked = [(p, float(10 - i)) for i, p in enumerate(paths)]
        result = _rrf_fuse(ranked, top_k=3)
        assert len(result) == 3

    def test_scores_are_positive(self) -> None:
        paths = _make_paths(3)
        ranked = [(p, 1.0) for p in paths]
        result = _rrf_fuse(ranked, top_k=3)
        assert all(score > 0 for _, score in result)

    def test_custom_k_parameter(self) -> None:
        paths = _make_paths(2)
        ranked = [(paths[0], 1.0), (paths[1], 0.5)]
        # k=1 → scores are 1/(1+rank); k=100 → scores are 1/(100+rank)
        result_small_k = _rrf_fuse(ranked, top_k=2, k=1)
        result_large_k = _rrf_fuse(ranked, top_k=2, k=100)
        # Ordering must be the same regardless of k
        assert result_small_k[0][0] == result_large_k[0][0]
        # But absolute scores differ
        assert result_small_k[0][1] > result_large_k[0][1]

    def test_fuse_deduplicates_paths(self) -> None:
        """A path appearing in multiple lists should appear only once in output."""
        paths = _make_paths(2)
        list_a = [(paths[0], 1.0)]
        list_b = [(paths[0], 0.8)]
        result = _rrf_fuse(list_a, list_b, top_k=5)
        result_paths = [p for p, _ in result]
        assert result_paths.count(paths[0]) == 1


# ---------------------------------------------------------------------------
# HybridRetriever unit tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestHybridRetrieverInit:
    def test_not_initialized_before_index(self) -> None:
        r = HybridRetriever()
        assert r.is_initialized is False

    def test_corpus_size_zero_before_index(self) -> None:
        r = HybridRetriever()
        assert r.corpus_size == 0

    def test_satisfies_retriever_protocol(self) -> None:
        # RetrieverProtocol has a property member (is_initialized), so
        # issubclass() raises TypeError; use isinstance() on an instance instead.
        assert isinstance(HybridRetriever(), RetrieverProtocol)

    def test_initialize_marks_as_initialized(self) -> None:
        r = HybridRetriever()
        r.initialize()
        assert r.is_initialized is True

    def test_cleanup_resets_initialized(self) -> None:
        r = HybridRetriever()
        r.initialize()
        r.cleanup()
        assert r.is_initialized is False

    def test_custom_bm25_and_vector_injected(self) -> None:
        from file_organizer.services.search.bm25_index import BM25Index
        from file_organizer.services.search.vector_index import VectorIndex

        bm25 = BM25Index()
        vector = VectorIndex()
        r = HybridRetriever(bm25=bm25, vector=vector)
        assert r._bm25 is bm25
        assert r._vector is vector


@pytest.mark.unit
class TestHybridRetrieverIndex:
    def test_index_sets_initialized(self) -> None:
        paths = _make_paths(3)
        r = HybridRetriever()
        r.index(
            ["quarterly finance report", "project planning document", "research analysis"],
            paths,
        )
        assert r.is_initialized is True

    def test_index_updates_corpus_size(self) -> None:
        paths = _make_paths(5)
        r = HybridRetriever()
        r.index(
            [
                "quarterly finance report",
                "project planning schedule",
                "research analysis document",
                "meeting notes agenda",
                "budget forecast spreadsheet",
            ],
            paths,
        )
        assert r.corpus_size == 5

    def test_index_mismatched_lengths_raises(self) -> None:
        r = HybridRetriever()
        with pytest.raises(ValueError, match="equal length"):
            r.index(["one", "two"], _make_paths(3))

    def test_index_empty_corpus(self) -> None:
        r = HybridRetriever()
        r.index([], [])
        # BM25Index and VectorIndex both handle empty corpora gracefully
        assert r.is_initialized is True


@pytest.mark.unit
class TestHybridRetrieverRetrieve:
    def test_retrieve_before_index_returns_empty(self) -> None:
        r = HybridRetriever()
        results = r.retrieve("anything")
        assert results == []

    def test_retrieve_returns_list_of_tuples(self) -> None:
        paths = _make_paths(3)
        docs = ["finance quarterly report", "meeting notes agenda", "budget planning"]
        r = _make_retriever_with_corpus(docs, paths)
        results = r.retrieve("quarterly report")
        assert isinstance(results, list)
        assert len(results) > 0, "query 'quarterly report' should match at least one document"
        for item in results:
            assert isinstance(item, tuple)
            assert len(item) == 2
            assert isinstance(item[0], Path)
            assert isinstance(item[1], float)
            assert item[0] in paths, "returned path must be from the indexed corpus"

    def test_retrieve_top_k_limits_output(self) -> None:
        paths = _make_paths(10)
        docs = [
            "quarterly finance report",
            "project planning document",
            "research analysis report",
            "meeting notes agenda",
            "budget forecast spreadsheet",
            "marketing campaign proposal",
            "technical specification document",
            "annual performance review",
            "product roadmap planning",
            "customer feedback analysis",
        ]
        r = _make_retriever_with_corpus(docs, paths)
        results = r.retrieve("finance report", top_k=3)
        assert len(results) == 3

    def test_retrieve_scores_are_positive(self) -> None:
        paths = _make_paths(5)
        docs = [
            "quarterly finance analysis",
            "project management planning",
            "financial budget forecast",
            "technical documentation review",
            "marketing strategy proposal",
        ]
        r = _make_retriever_with_corpus(docs, paths)
        results = r.retrieve("finance")
        assert all(score > 0 for _, score in results)

    def test_retrieve_sorted_descending(self) -> None:
        paths = _make_paths(5)
        docs = [
            "quarterly report",
            "quarterly finance report",
            "quarterly finance budget report",
            "technical specification",
            "marketing proposal",
        ]
        r = _make_retriever_with_corpus(docs, paths)
        results = r.retrieve("quarterly finance budget")
        scores = [s for _, s in results]
        assert scores == sorted(scores, reverse=True)

    def test_retrieve_empty_query_bm25_returns_empty(self) -> None:
        """An empty query string causes BM25 to return no results (no tokens to score)."""
        from unittest.mock import MagicMock

        bm25_mock = MagicMock()
        vector_mock = MagicMock()
        bm25_mock.search.return_value = []
        vector_mock.search.return_value = []
        bm25_mock.size = 3

        r = HybridRetriever(bm25=bm25_mock, vector=vector_mock)
        r.initialize()
        results = r.retrieve("")
        assert results == []


@pytest.mark.unit
class TestHybridRetrieverMocked:
    """Tests that verify RRF fusion without depending on real BM25/vector."""

    def test_rrf_fusion_uses_both_indices(self) -> None:
        """Verify HybridRetriever calls both indices and fuses their results."""
        bm25_mock = MagicMock()
        vector_mock = MagicMock()

        paths = _make_paths(3)
        bm25_mock.search.return_value = [(paths[0], 1.0), (paths[1], 0.5)]
        vector_mock.search.return_value = [(paths[1], 0.9), (paths[2], 0.3)]
        bm25_mock.size = 3
        vector_mock.size = 3

        r = HybridRetriever(bm25=bm25_mock, vector=vector_mock)
        r.initialize()

        results = r.retrieve("test query", top_k=5)

        bm25_mock.search.assert_called_once_with("test query", top_k=ANY)
        vector_mock.search.assert_called_once_with("test query", top_k=ANY)

        # paths[1] is in both lists — should appear exactly once in output
        result_paths = [p for p, _ in results]
        assert result_paths.count(paths[1]) == 1

    def test_index_calls_both_subindices(self) -> None:
        """index() must delegate to both BM25Index and VectorIndex."""
        bm25_mock = MagicMock()
        vector_mock = MagicMock()
        bm25_mock.size = 2

        r = HybridRetriever(bm25=bm25_mock, vector=vector_mock)
        docs = ["doc a", "doc b"]
        paths = _make_paths(2)
        r.index(docs, paths)

        bm25_mock.index.assert_called_once_with(docs, paths)
        vector_mock.index.assert_called_once_with(docs, paths)
        assert r.is_initialized is True

    def test_retrieve_falls_back_gracefully_when_both_empty(self) -> None:
        """If both indices return no results, retrieve() returns []."""
        bm25_mock = MagicMock()
        vector_mock = MagicMock()
        bm25_mock.search.return_value = []
        vector_mock.search.return_value = []
        bm25_mock.size = 0

        r = HybridRetriever(bm25=bm25_mock, vector=vector_mock)
        r.initialize()
        assert r.retrieve("anything") == []
