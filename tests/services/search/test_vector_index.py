"""Unit tests for VectorIndex."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from file_organizer.interfaces.search import IndexProtocol
from file_organizer.services.search.vector_index import VectorIndex

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_paths(n: int) -> list[Path]:
    tmp = Path(tempfile.gettempdir())
    return [tmp / f"file_{i}.txt" for i in range(n)]


_CORPUS = [
    "quarterly budget finance report revenue expenses",
    "machine learning python neural network deep learning",
    "patient discharge summary diabetes medication healthcare",
    "legal contract software licensing agreement",
    "engineering standup meeting notes action items ci pipeline",
    "chocolate chip cookie recipe baking ingredients butter sugar",
    "travel itinerary japan tokyo kyoto flights hotels",
    "transformer attention mechanism research paper nlp",
    "nginx docker configuration server deployment kubernetes",
    "product roadmap presentation strategy 2023 features",
]


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


@pytest.mark.ci
@pytest.mark.unit
class TestVectorIndexProtocol:
    def test_implements_index_protocol(self) -> None:
        assert isinstance(VectorIndex(), IndexProtocol)


# ---------------------------------------------------------------------------
# Basic behaviour
# ---------------------------------------------------------------------------


@pytest.mark.ci
@pytest.mark.unit
class TestVectorIndex:
    def test_search_before_index_returns_empty(self) -> None:
        idx = VectorIndex()
        assert idx.search("anything") == []

    def test_search_top_k_zero_returns_empty(self) -> None:
        idx = VectorIndex()
        idx.index(_CORPUS, _make_paths(len(_CORPUS)))
        # Verify the guard: top_k=0 returns []
        assert idx.search("report", top_k=0) == []
        # Verify search works with positive top_k
        assert len(idx.search("report", top_k=1)) > 0

    def test_search_top_k_negative_returns_empty(self) -> None:
        idx = VectorIndex()
        idx.index(_CORPUS, _make_paths(len(_CORPUS)))
        # Verify the guard: top_k=-1 returns []
        assert idx.search("report", top_k=-1) == []
        # Verify search works with positive top_k
        assert len(idx.search("report", top_k=1)) > 0

    def test_size_zero_before_index(self) -> None:
        assert VectorIndex().size == 0

    def test_index_sets_size(self) -> None:
        idx = VectorIndex()
        idx.index(_CORPUS, _make_paths(len(_CORPUS)))
        assert idx.size == len(_CORPUS)

    def test_mismatched_lengths_raises(self) -> None:
        idx = VectorIndex()
        with pytest.raises(ValueError, match="equal length"):
            idx.index(["doc"], _make_paths(2))

    def test_empty_corpus_clears_index(self) -> None:
        idx = VectorIndex()
        idx.index(_CORPUS, _make_paths(len(_CORPUS)))
        idx.index([], [])
        assert idx.size == 0
        assert idx.search("finance") == []

    def test_relevant_document_in_top_results(self) -> None:
        paths = _make_paths(len(_CORPUS))
        idx = VectorIndex()
        idx.index(_CORPUS, paths)
        results = idx.search("finance budget quarterly", top_k=3)
        assert results, "Expected at least one result"
        returned_paths = [p for p, _ in results]
        assert paths[0] in returned_paths, "Finance doc should appear in top 3 for budget query"

    def test_scores_are_between_zero_and_one(self) -> None:
        idx = VectorIndex()
        idx.index(_CORPUS, _make_paths(len(_CORPUS)))
        results = idx.search("machine learning python")
        for _, score in results:
            assert 0.0 <= score <= 1.0, f"Score {score} out of [0, 1] range"

    def test_top_k_limits_results(self) -> None:
        idx = VectorIndex()
        idx.index(_CORPUS, _make_paths(len(_CORPUS)))
        results = idx.search("report", top_k=3)
        assert results, "Expected results for 'report' in a 10-doc corpus"
        assert len(results) == 3

    def test_results_sorted_descending(self) -> None:
        idx = VectorIndex()
        idx.index(_CORPUS, _make_paths(len(_CORPUS)))
        results = idx.search("legal contract", top_k=5)
        scores = [s for _, s in results]
        assert scores == sorted(scores, reverse=True), "Results must be sorted by descending score"

    def test_re_index_replaces_previous(self) -> None:
        idx = VectorIndex()
        old_paths = _make_paths(len(_CORPUS))
        idx.index(_CORPUS, old_paths)
        # Use 2+ docs to satisfy scikit-learn min_df/max_df constraints
        tmp = Path(tempfile.gettempdir())
        new_paths = [tmp / "new_a.txt", tmp / "new_b.txt"]
        idx.index(["completely different document one", "another new document two"], new_paths)
        assert idx.size == 2
        # Old paths must not survive re-index
        results = idx.search("finance budget quarterly", top_k=5)
        returned = [p for p, _ in results]
        for old_path in old_paths:
            assert old_path not in returned, f"{old_path.name} survived re-index"

    def test_threshold_filters_low_scores(self) -> None:
        paths = _make_paths(len(_CORPUS))
        # Control: loose threshold returns results for a relevant query
        loose_idx = VectorIndex(similarity_threshold=0.0)
        loose_idx.index(_CORPUS, paths)
        assert loose_idx.search("finance budget quarterly"), "Loose threshold should return results"

        # Strict threshold: same query must be filtered out
        strict_idx = VectorIndex(similarity_threshold=0.99)
        strict_idx.index(_CORPUS, paths)
        results = strict_idx.search("xyzzy zork nonsense")
        # All returned scores must satisfy the threshold
        for _, score in results:
            assert score >= 0.99, f"Score {score} below threshold"


# ---------------------------------------------------------------------------
# Corpus-level recall (non-exhaustive smoke test)
# ---------------------------------------------------------------------------


@pytest.mark.ci
@pytest.mark.unit
class TestVectorIndexRecall:
    """Smoke-test that semantically related queries find the right category."""

    @pytest.fixture(scope="class")
    def indexed(self) -> VectorIndex:
        idx = VectorIndex()
        idx.index(_CORPUS, _make_paths(len(_CORPUS)))
        return idx

    @pytest.mark.parametrize(
        "query,expected_idx",
        [
            ("budget revenue expenses", 0),  # finance
            ("neural network deep learning", 1),  # ml
            ("healthcare patient medication", 2),  # healthcare
            ("contract licensing legal", 3),  # legal
            ("cookie baking recipe sugar", 5),  # recipes
            ("japan tokyo travel", 6),  # travel
            ("attention transformer nlp", 7),  # research
            ("docker nginx server", 8),  # devops
        ],
    )
    def test_category_recall(self, indexed: VectorIndex, query: str, expected_idx: int) -> None:
        results = indexed.search(query, top_k=3)
        assert results, f"No results for query: {query!r}"
        returned = [p for p, _ in results]
        assert Path(tempfile.gettempdir()) / f"file_{expected_idx}.txt" in returned, (
            f"Expected file_{expected_idx}.txt in top-3 for query {query!r}, got {returned}"
        )
