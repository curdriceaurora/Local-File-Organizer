"""Unit tests for BM25Index."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

pytest.importorskip("rank_bm25")

from file_organizer.interfaces.search import IndexProtocol
from file_organizer.services.search.bm25_index import BM25Index, _tokenise

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_paths(n: int) -> list[Path]:
    """Return a list of n unique temporary Path objects for test fixtures."""
    tmp = Path(tempfile.gettempdir())
    return [tmp / f"file_{i}.txt" for i in range(n)]


# ---------------------------------------------------------------------------
# Tokeniser
# ---------------------------------------------------------------------------


@pytest.mark.ci
@pytest.mark.unit
class TestTokenise:
    """Tests for the _tokenise helper."""

    def test_lowercases(self) -> None:
        """Tokens are converted to lowercase."""
        assert _tokenise("Hello World") == ["hello", "world"]

    def test_splits_on_non_alphanumeric(self) -> None:
        """Non-alphanumeric characters act as token delimiters."""
        assert _tokenise("foo-bar_baz.txt") == ["foo", "bar", "baz", "txt"]

    def test_preserves_digits(self) -> None:
        """Numeric tokens are preserved."""
        tokens = _tokenise("report_2023_q3")
        assert "2023" in tokens
        assert "q3" in tokens

    def test_empty_string_returns_empty(self) -> None:
        """Empty input yields an empty token list."""
        assert _tokenise("") == []

    def test_filters_empty_tokens(self) -> None:
        """Whitespace-only input yields an empty token list."""
        assert _tokenise("  ") == []


# ---------------------------------------------------------------------------
# BM25Index protocol conformance
# ---------------------------------------------------------------------------


@pytest.mark.ci
@pytest.mark.unit
class TestBM25IndexProtocol:
    """Protocol conformance tests for BM25Index."""

    def test_implements_index_protocol(self) -> None:
        """BM25Index satisfies the IndexProtocol runtime-checkable interface."""
        assert isinstance(BM25Index(), IndexProtocol)


# ---------------------------------------------------------------------------
# BM25Index behaviour
# ---------------------------------------------------------------------------


@pytest.mark.ci
@pytest.mark.unit
class TestBM25Index:
    """Functional tests for BM25Index search and indexing behaviour."""

    def test_search_before_index_returns_empty(self) -> None:
        """Searching an uninitialised index returns an empty list."""
        idx = BM25Index()
        assert idx.search("anything") == []

    def test_search_top_k_zero_returns_empty(self) -> None:
        """top_k=0 returns an empty result list."""
        idx = BM25Index()
        idx.index(
            ["finance budget report", "legal contract", "recipe baking", "travel japan"],
            _make_paths(4),
        )
        assert idx.search("finance", top_k=0) == []

    def test_search_top_k_negative_returns_empty(self) -> None:
        """Negative top_k returns an empty result list."""
        idx = BM25Index()
        idx.index(
            ["finance budget report", "legal contract", "recipe baking", "travel japan"],
            _make_paths(4),
        )
        assert idx.search("finance", top_k=-1) == []

    def test_size_zero_before_index(self) -> None:
        """size is 0 before any documents are indexed."""
        assert BM25Index().size == 0

    def test_index_sets_size(self) -> None:
        """size equals the number of indexed documents."""
        idx = BM25Index()
        docs = ["finance budget report", "recipe cookie chocolate"]
        idx.index(docs, _make_paths(2))
        assert idx.size == 2

    def test_mismatched_lengths_raises(self) -> None:
        """Mismatched docs/paths lengths raise ValueError."""
        idx = BM25Index()
        with pytest.raises(ValueError, match="equal length"):
            idx.index(["doc"], _make_paths(2))

    def test_relevant_document_ranked_first(self) -> None:
        """The most relevant document appears at rank 0."""
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
        """Matching results have positive BM25 scores."""
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
        """Results are capped at top_k even when more documents match."""
        docs = [f"document about topic {i}" for i in range(20)]
        idx = BM25Index()
        idx.index(docs, _make_paths(20))
        results = idx.search("document topic", top_k=5)
        assert len(results) == 5, "All 20 docs match the query; expected exactly top_k=5 results"

    def test_empty_query_returns_empty(self) -> None:
        """An empty query string returns no results."""
        idx = BM25Index()
        idx.index(["finance report"], _make_paths(1))
        assert idx.search("") == []

    def test_zero_score_results_excluded(self) -> None:
        """Documents with zero BM25 score (no term overlap) are excluded from results."""
        idx = BM25Index()
        idx.index(["finance budget"], _make_paths(1))
        # Query with no overlap should yield no results
        results = idx.search("xyzzy nonsense zork")
        assert results == []

    def test_single_doc_matching_query_returned(self) -> None:
        """Single-doc corpus with a matching query must return that document despite negative BM25 IDF."""
        # With a 1-doc corpus every term has df=N=1, so BM25 IDF is negative.
        # The result must still be returned (score != 0.0, not score > 0).
        idx = BM25Index()
        paths = _make_paths(1)
        idx.index(["finance quarterly report"], paths)
        results = idx.search("finance")
        assert len(results) == 1, "single-doc corpus with matching query must return the document"
        assert results[0][0] == paths[0]

    def test_re_index_replaces_previous(self) -> None:
        """Re-indexing with new documents completely replaces the previous corpus."""
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


# ---------------------------------------------------------------------------
# BM25Index incremental updates
# ---------------------------------------------------------------------------


@pytest.mark.ci
@pytest.mark.unit
class TestBM25IndexIncrementalUpdates:
    """Tests for incremental document add/update/remove operations."""

    def test_add_document_increases_size(self) -> None:
        """Adding a document increases the index size by 1."""
        idx = BM25Index()
        paths = _make_paths(3)
        idx.index(
            ["finance budget report", "legal contract agreement", "recipe baking chocolate"],
            paths,
        )
        assert idx.size == 3
        # Add a new document
        new_path = Path(tempfile.gettempdir()) / "new_doc.txt"
        idx.add_document("machine learning neural network", new_path)
        assert idx.size == 4

    def test_add_document_searchable(self) -> None:
        """Added documents are immediately searchable."""
        idx = BM25Index()
        paths = _make_paths(3)
        idx.index(
            ["finance budget report", "legal contract agreement", "recipe baking chocolate"],
            paths,
        )
        # Add a new document
        new_path = Path(tempfile.gettempdir()) / "ml_doc.txt"
        idx.add_document("machine learning python tensorflow", new_path)
        # Search should find the new document
        results = idx.search("machine learning")
        assert results, "Expected to find newly added document"
        returned_paths = [p for p, _ in results]
        assert new_path in returned_paths

    def test_remove_document_decreases_size(self) -> None:
        """Removing a document decreases the index size by 1."""
        idx = BM25Index()
        paths = _make_paths(3)
        idx.index(
            ["finance budget report", "legal contract agreement", "recipe baking chocolate"],
            paths,
        )
        assert idx.size == 3
        # Remove a document
        idx.remove_document(paths[1])
        assert idx.size == 2

    def test_remove_document_not_searchable(self) -> None:
        """Removed documents no longer appear in search results."""
        idx = BM25Index()
        paths = _make_paths(3)
        idx.index(
            ["finance budget report", "legal contract agreement", "recipe baking chocolate"],
            paths,
        )
        # Remove the legal document
        idx.remove_document(paths[1])
        # Search for contract should not return the removed document
        results = idx.search("legal contract")
        returned_paths = [p for p, _ in results]
        assert paths[1] not in returned_paths

    def test_remove_nonexistent_document_raises(self) -> None:
        """Attempting to remove a document that doesn't exist raises ValueError."""
        idx = BM25Index()
        paths = _make_paths(2)
        idx.index(["finance report", "legal contract"], paths)
        nonexistent_path = Path(tempfile.gettempdir()) / "nonexistent.txt"
        with pytest.raises(ValueError, match="not found in index"):
            idx.remove_document(nonexistent_path)

    def test_update_document_maintains_size(self) -> None:
        """Updating a document maintains the same index size."""
        idx = BM25Index()
        paths = _make_paths(3)
        idx.index(
            ["finance budget report", "legal contract agreement", "recipe baking chocolate"],
            paths,
        )
        assert idx.size == 3
        # Update a document
        idx.update_document(paths[0], "quarterly earnings financial statement")
        assert idx.size == 3

    def test_update_document_changes_search_results(self) -> None:
        """Updating a document reflects in search results."""
        idx = BM25Index()
        paths = _make_paths(3)
        idx.index(
            ["finance budget report", "legal contract agreement", "recipe baking chocolate"],
            paths,
        )
        # Update first document with completely different content
        idx.update_document(paths[0], "machine learning artificial intelligence")
        # Old terms should not match as strongly
        finance_results = idx.search("finance budget")
        assert all(path != paths[0] for path, _ in finance_results)
        # New terms should match
        ml_results = idx.search("machine learning")
        assert ml_results, "Expected updated document to match new content"
        ml_paths = [p for p, _ in ml_results]
        assert paths[0] in ml_paths, "Updated document should appear for new query terms"

    def test_update_nonexistent_document_raises(self) -> None:
        """Attempting to update a document that doesn't exist raises ValueError."""
        idx = BM25Index()
        paths = _make_paths(2)
        idx.index(["finance report", "legal contract"], paths)
        nonexistent_path = Path(tempfile.gettempdir()) / "nonexistent.txt"
        with pytest.raises(ValueError, match="not found in index"):
            idx.update_document(nonexistent_path, "new content")

    def test_incremental_update(self) -> None:
        """Combined test: add, update, and remove documents."""
        idx = BM25Index()
        paths = _make_paths(3)
        idx.index(
            ["finance budget report", "legal contract agreement", "recipe baking chocolate"],
            paths,
        )
        assert idx.size == 3

        # Add a new document
        new_path = Path(tempfile.gettempdir()) / "ml_doc.txt"
        idx.add_document("machine learning python", new_path)
        assert idx.size == 4

        # Update an existing document
        idx.update_document(paths[1], "software license agreement open source")
        assert idx.size == 4

        # Remove a document
        idx.remove_document(paths[2])
        assert idx.size == 3

        # Verify search results reflect all changes
        ml_results = idx.search("machine learning")
        assert any(p == new_path for p, _ in ml_results), "Added document should be searchable"

        software_results = idx.search("software license")
        assert any(p == paths[1] for p, _ in software_results), (
            "Updated document should match new content"
        )

        recipe_results = idx.search("recipe baking")
        assert not any(p == paths[2] for p, _ in recipe_results), (
            "Removed document should not appear"
        )

    def test_incremental_updates_invalidate_cache(self) -> None:
        """Incremental updates invalidate and rebuild the cache."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "test_cache.pkl"
            idx = BM25Index(cache_path=cache_path)
            paths = _make_paths(3)
            idx.index(
                ["finance budget report", "legal contract agreement", "recipe baking chocolate"],
                paths,
            )
            # Cache should be created
            assert cache_path.exists()

            # Add a document - cache should be rebuilt
            new_path = Path(tempfile.gettempdir()) / "new_doc.txt"
            idx.add_document("machine learning", new_path)
            # Cache should still exist and be valid
            assert cache_path.exists()

            # Create a new index instance with the same cache
            idx2 = BM25Index(cache_path=cache_path)
            assert idx2.size == 4
            results = idx2.search("machine learning")
            assert any(p == new_path for p, _ in results)

    def test_cache_rebuilds_when_documents_change_without_path_change(self) -> None:
        """Cache is rejected when the document payload changes for the same paths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "test_cache.pkl"
            idx = BM25Index(cache_path=cache_path)
            paths = _make_paths(3)
            idx.index(
                ["finance budget report", "legal contract agreement", "recipe baking chocolate"],
                paths,
            )

            idx2 = BM25Index(cache_path=cache_path)
            idx2.index(
                ["machine learning report", "legal contract agreement", "recipe baking chocolate"],
                paths,
            )

            results = idx2.search("machine learning")
            assert any(p == paths[0] for p, _ in results)


# ---------------------------------------------------------------------------
# BM25Index cache error handling
# ---------------------------------------------------------------------------


@pytest.mark.ci
@pytest.mark.unit
class TestBM25IndexCacheErrorHandling:
    """Tests for cache load/save error paths."""

    def test_cache_load_oserror_falls_through_to_rebuild(self) -> None:
        """OSError during cache load triggers index rebuild instead of failure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "bad_cache.pkl"
            # Write invalid binary data to simulate corrupt cache
            cache_path.write_bytes(b"\x00\x01\x02\x03")

            idx = BM25Index(cache_path=cache_path)
            paths = _make_paths(3)
            docs = [
                "finance budget report",
                "legal contract agreement",
                "recipe baking chocolate",
            ]
            idx.index(docs, paths)

            # Index should work despite corrupt cache
            assert idx.size == 3
            results = idx.search("finance budget")
            assert results, "Expected results after rebuild from corrupt cache"

    def test_cache_save_oserror_does_not_prevent_index_use(self) -> None:
        """OSError during cache save is logged but index remains usable."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "cache.pkl"
            idx = BM25Index(cache_path=cache_path)
            paths = _make_paths(3)
            docs = [
                "finance budget report",
                "legal contract agreement",
                "recipe baking chocolate",
            ]

            with patch.object(idx._persistence, "save", side_effect=OSError("disk full")):
                idx.index(docs, paths)

            assert idx.size == 3
            results = idx.search("finance")
            assert results, "Index should be usable despite cache save failure"

    def test_cache_path_none_skips_caching(self) -> None:
        """No caching operations when cache_path is None."""
        idx = BM25Index(cache_path=None)
        paths = _make_paths(3)
        docs = [
            "finance budget report",
            "legal contract agreement",
            "recipe baking chocolate",
        ]
        idx.index(docs, paths)

        assert idx.size == 3
        results = idx.search("finance")
        assert results, "Expected search results without caching"

    def test_cache_load_returns_mismatched_paths_triggers_rebuild(self) -> None:
        """When cached paths don't match provided paths, index is rebuilt."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "cache.pkl"
            old_paths = _make_paths(2)
            old_docs = ["old doc one", "old doc two"]

            # Build and cache with old paths
            idx1 = BM25Index(cache_path=cache_path)
            idx1.index(old_docs, old_paths)
            assert cache_path.exists()

            # Load with different paths -- cache should be invalidated
            new_paths = [Path(tempfile.gettempdir()) / "new_a.txt"]
            new_docs = ["completely new document about science"]

            idx2 = BM25Index(cache_path=cache_path)
            idx2.index(new_docs, new_paths)
            assert idx2.size == 1


# ---------------------------------------------------------------------------
# BM25Index incremental updates with cache
# ---------------------------------------------------------------------------


@pytest.mark.ci
@pytest.mark.unit
class TestBM25IndexIncrementalUpdatesCacheEdges:
    """Tests for add_document, remove_document, update_document cache interactions."""

    def test_add_document_updates_cache(self) -> None:
        """add_document saves updated index to cache file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "cache.pkl"
            idx = BM25Index(cache_path=cache_path)
            paths = _make_paths(3)
            idx.index(
                ["finance budget", "legal contract", "recipe chocolate"],
                paths,
            )
            import os

            # Set mtime to a known past value so we can detect cache update
            past_time = cache_path.stat().st_mtime - 10
            os.utime(cache_path, (past_time, past_time))
            mtime_before = cache_path.stat().st_mtime

            new_path = Path(tempfile.gettempdir()) / "added.txt"
            idx.add_document("machine learning neural", new_path)

            assert idx.size == 4
            # Cache should be updated (mtime changed from the past value we set)
            assert cache_path.stat().st_mtime > mtime_before

    def test_remove_document_updates_cache(self) -> None:
        """remove_document saves updated index to cache file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "cache.pkl"
            idx = BM25Index(cache_path=cache_path)
            paths = _make_paths(3)
            idx.index(
                ["finance budget", "legal contract", "recipe chocolate"],
                paths,
            )
            assert idx.size == 3

            idx.remove_document(paths[1])
            assert idx.size == 2
            assert cache_path.exists()

    def test_remove_all_documents_sets_bm25_none(self) -> None:
        """Removing all documents sets internal BM25 index to None."""
        idx = BM25Index()
        paths = _make_paths(1)
        idx.index(["finance budget report"], paths)
        assert idx.size == 1

        idx.remove_document(paths[0])
        assert idx.size == 0
        # Search on empty index returns empty
        assert idx.search("finance") == []

    def test_update_document_updates_cache(self) -> None:
        """update_document saves updated index to cache file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "cache.pkl"
            idx = BM25Index(cache_path=cache_path)
            paths = _make_paths(3)
            idx.index(
                ["finance budget", "legal contract", "recipe chocolate"],
                paths,
            )

            idx.update_document(paths[0], "completely new content about art")
            assert idx.size == 3

            # Verify the update is searchable
            results = idx.search("art")
            returned_paths = [p for p, _ in results]
            assert paths[0] in returned_paths

    def test_update_cache_skipped_when_no_cache_path(self) -> None:
        """_update_cache does nothing when cache_path is None."""
        idx = BM25Index(cache_path=None)
        paths = _make_paths(3)
        idx.index(
            ["finance budget", "legal contract", "recipe chocolate"],
            paths,
        )

        # These should all succeed without error
        new_path = Path(tempfile.gettempdir()) / "new.txt"
        idx.add_document("new doc", new_path)
        idx.update_document(paths[0], "updated content")
        idx.remove_document(paths[1])
        assert idx.size == 3


# ---------------------------------------------------------------------------
# BM25Index invalidate_cache
# ---------------------------------------------------------------------------


@pytest.mark.ci
@pytest.mark.unit
class TestBM25IndexInvalidateCache:
    """Tests for invalidate_cache method."""

    def test_invalidate_cache_deletes_file(self) -> None:
        """invalidate_cache removes the cache file from disk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "cache.pkl"
            idx = BM25Index(cache_path=cache_path)
            paths = _make_paths(3)
            idx.index(
                ["finance budget", "legal contract", "recipe chocolate"],
                paths,
            )
            assert cache_path.exists()

            idx.invalidate_cache()
            assert not cache_path.exists()

    def test_invalidate_cache_no_cache_path_is_noop(self) -> None:
        """invalidate_cache does nothing when no cache_path is configured."""
        idx = BM25Index(cache_path=None)
        # Should not raise
        idx.invalidate_cache()

    def test_invalidate_cache_nonexistent_file_is_noop(self) -> None:
        """invalidate_cache does nothing when cache file does not exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "nonexistent.pkl"
            idx = BM25Index(cache_path=cache_path)
            # Should not raise
            idx.invalidate_cache()
            assert not cache_path.exists()

    def test_invalidate_then_reindex_rebuilds(self) -> None:
        """After invalidation, next index() call rebuilds the cache."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "cache.pkl"
            paths = _make_paths(3)
            docs = ["finance budget", "legal contract", "recipe chocolate"]

            idx = BM25Index(cache_path=cache_path)
            idx.index(docs, paths)
            assert cache_path.exists()

            idx.invalidate_cache()
            assert not cache_path.exists()

            # Re-index should rebuild and re-cache
            idx2 = BM25Index(cache_path=cache_path)
            idx2.index(docs, paths)
            assert cache_path.exists()
            assert idx2.size == 3
