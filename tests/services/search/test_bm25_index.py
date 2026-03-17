"""Unit tests for BM25Index."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from file_organizer.interfaces.search import IndexProtocol
from file_organizer.services.search.bm25_index import BM25Index, _tokenise

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_paths(n: int) -> list[Path]:
    tmp = Path(tempfile.gettempdir())
    return [tmp / f"file_{i}.txt" for i in range(n)]


# ---------------------------------------------------------------------------
# Tokeniser
# ---------------------------------------------------------------------------


@pytest.mark.ci
@pytest.mark.unit
class TestTokenise:
    def test_lowercases(self) -> None:
        assert _tokenise("Hello World") == ["hello", "world"]

    def test_splits_on_non_alphanumeric(self) -> None:
        assert _tokenise("foo-bar_baz.txt") == ["foo", "bar", "baz", "txt"]

    def test_preserves_digits(self) -> None:
        tokens = _tokenise("report_2023_q3")
        assert "2023" in tokens
        assert "q3" in tokens

    def test_empty_string_returns_empty(self) -> None:
        assert _tokenise("") == []

    def test_filters_empty_tokens(self) -> None:
        assert _tokenise("  ") == []


# ---------------------------------------------------------------------------
# BM25Index protocol conformance
# ---------------------------------------------------------------------------


@pytest.mark.ci
@pytest.mark.unit
class TestBM25IndexProtocol:
    def test_implements_index_protocol(self) -> None:
        assert isinstance(BM25Index(), IndexProtocol)


# ---------------------------------------------------------------------------
# BM25Index behaviour
# ---------------------------------------------------------------------------


@pytest.mark.ci
@pytest.mark.unit
class TestBM25Index:
    def test_search_before_index_returns_empty(self) -> None:
        idx = BM25Index()
        assert idx.search("anything") == []

    def test_search_top_k_zero_returns_empty(self) -> None:
        idx = BM25Index()
        idx.index(
            ["finance budget report", "legal contract", "recipe baking", "travel japan"],
            _make_paths(4),
        )
        assert idx.search("finance", top_k=0) == []

    def test_search_top_k_negative_returns_empty(self) -> None:
        idx = BM25Index()
        idx.index(
            ["finance budget report", "legal contract", "recipe baking", "travel japan"],
            _make_paths(4),
        )
        assert idx.search("finance", top_k=-1) == []

    def test_size_zero_before_index(self) -> None:
        assert BM25Index().size == 0

    def test_index_sets_size(self) -> None:
        idx = BM25Index()
        docs = ["finance budget report", "recipe cookie chocolate"]
        idx.index(docs, _make_paths(2))
        assert idx.size == 2

    def test_mismatched_lengths_raises(self) -> None:
        idx = BM25Index()
        with pytest.raises(ValueError, match="equal length"):
            idx.index(["doc"], _make_paths(2))

    def test_relevant_document_ranked_first(self) -> None:
        paths = _make_paths(3)
        idx = BM25Index()
        idx.index(
            [
                "quarterly budget finance report",
                "chocolate chip cookie recipe",
                "travel itinerary japan",
            ],
            paths,
        )
        results = idx.search("budget finance")
        assert results, "Expected at least one result"
        assert results[0][0] == paths[0], "Finance doc should rank first for budget query"

    def test_scores_are_positive(self) -> None:
        idx = BM25Index()
        idx.index(
            [
                "machine learning python neural network",
                "legal contract software agreement",
                "recipe baking chocolate cookie",
                "finance budget quarterly report",
            ],
            _make_paths(4),
        )
        results = idx.search("machine learning python")
        assert results, "Expected at least one match for overlapping query terms"
        assert all(score > 0 for _, score in results)

    def test_top_k_limits_results(self) -> None:
        docs = [f"document about topic {i}" for i in range(20)]
        idx = BM25Index()
        idx.index(docs, _make_paths(20))
        results = idx.search("document topic", top_k=5)
        assert len(results) == 5, "All 20 docs match the query; expected exactly top_k=5 results"

    def test_empty_query_returns_empty(self) -> None:
        idx = BM25Index()
        idx.index(["finance report"], _make_paths(1))
        assert idx.search("") == []

    def test_zero_score_results_excluded(self) -> None:
        idx = BM25Index()
        idx.index(["finance budget"], _make_paths(1))
        # Query with no overlap should yield no results
        results = idx.search("xyzzy nonsense zork")
        assert results == []

    def test_re_index_replaces_previous(self) -> None:
        idx = BM25Index()
        idx.index(["first corpus alpha", "first corpus beta"], _make_paths(2))
        assert idx.size == 2
        # Re-index with different paths — old corpus must be gone
        # Use 3+ docs: rank-bm25 needs N>2 to produce positive IDF scores
        tmp = Path(tempfile.gettempdir())
        new_paths = [tmp / "new_a.txt", tmp / "new_b.txt", tmp / "new_c.txt"]
        idx.index(
            ["finance budget report", "legal contract agreement", "recipe baking chocolate"],
            new_paths,
        )
        assert idx.size == 3
        # Old paths must not appear in results; new corpus must be reachable
        results = idx.search("finance budget")
        assert results, "Expected results from re-indexed corpus"
        returned_paths = [p for p, _ in results]
        old_paths = _make_paths(2)
        assert old_paths[0] not in returned_paths
        assert old_paths[1] not in returned_paths
        assert new_paths[0] in returned_paths
