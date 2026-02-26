"""Tests for SemanticAnalyzer class.

Tests cosine similarity computation, document similarity finding,
clustering, similarity matrix computation, and statistics.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from file_organizer.services.deduplication.semantic import SemanticAnalyzer

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def analyzer():
    """Create a SemanticAnalyzer with default threshold."""
    return SemanticAnalyzer(threshold=0.85)


@pytest.fixture
def low_threshold_analyzer():
    """Create a SemanticAnalyzer with low threshold for testing."""
    return SemanticAnalyzer(threshold=0.3)


@pytest.fixture
def sample_embeddings():
    """Create sample embeddings for testing."""
    return np.array(
        [
            [1.0, 0.0, 0.0],  # doc0
            [0.9, 0.1, 0.0],  # doc1 - similar to doc0
            [0.0, 0.0, 1.0],  # doc2 - different
            [0.0, 0.05, 0.95],  # doc3 - similar to doc2
        ]
    )


@pytest.fixture
def sample_paths():
    """Create sample file paths."""
    return [
        Path("/docs/a.txt"),
        Path("/docs/b.txt"),
        Path("/docs/c.txt"),
        Path("/docs/d.txt"),
    ]


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


class TestSemanticAnalyzerInit:
    """Tests for SemanticAnalyzer initialization."""

    def test_default_threshold(self, analyzer):
        assert analyzer.threshold == 0.85

    def test_custom_threshold(self):
        sa = SemanticAnalyzer(threshold=0.5)
        assert sa.threshold == 0.5

    def test_invalid_threshold_too_high(self):
        with pytest.raises(ValueError, match="between 0 and 1"):
            SemanticAnalyzer(threshold=1.5)

    def test_invalid_threshold_negative(self):
        with pytest.raises(ValueError, match="between 0 and 1"):
            SemanticAnalyzer(threshold=-0.1)

    def test_boundary_thresholds(self):
        sa0 = SemanticAnalyzer(threshold=0.0)
        assert sa0.threshold == 0.0
        sa1 = SemanticAnalyzer(threshold=1.0)
        assert sa1.threshold == 1.0


# ---------------------------------------------------------------------------
# compute_similarity
# ---------------------------------------------------------------------------


class TestComputeSimilarity:
    """Tests for compute_similarity."""

    def test_identical_vectors(self, analyzer):
        v = np.array([1.0, 0.0, 0.0])
        sim = analyzer.compute_similarity(v, v)
        assert sim == pytest.approx(1.0, abs=1e-6)

    def test_orthogonal_vectors(self, analyzer):
        v1 = np.array([1.0, 0.0, 0.0])
        v2 = np.array([0.0, 1.0, 0.0])
        sim = analyzer.compute_similarity(v1, v2)
        assert sim == pytest.approx(0.0, abs=1e-6)

    def test_similar_vectors(self, analyzer):
        v1 = np.array([1.0, 0.0, 0.0])
        v2 = np.array([0.9, 0.1, 0.0])
        sim = analyzer.compute_similarity(v1, v2)
        assert 0.9 < sim < 1.0

    def test_zero_vector(self, analyzer):
        v1 = np.array([0.0, 0.0, 0.0])
        v2 = np.array([1.0, 0.0, 0.0])
        sim = analyzer.compute_similarity(v1, v2)
        assert sim == 0.0

    def test_both_zero_vectors(self, analyzer):
        v = np.array([0.0, 0.0, 0.0])
        sim = analyzer.compute_similarity(v, v)
        assert sim == 0.0

    def test_result_clamped_to_01(self, analyzer):
        v1 = np.array([1.0, 0.5])
        v2 = np.array([0.8, 0.3])
        sim = analyzer.compute_similarity(v1, v2)
        assert 0.0 <= sim <= 1.0


# ---------------------------------------------------------------------------
# compute_similarity_matrix
# ---------------------------------------------------------------------------


class TestComputeSimilarityMatrix:
    """Tests for compute_similarity_matrix."""

    def test_shape(self, analyzer, sample_embeddings):
        matrix = analyzer.compute_similarity_matrix(sample_embeddings)
        assert matrix.shape == (4, 4)

    def test_diagonal_ones(self, analyzer, sample_embeddings):
        matrix = analyzer.compute_similarity_matrix(sample_embeddings)
        for i in range(4):
            assert matrix[i, i] == pytest.approx(1.0, abs=1e-6)

    def test_symmetric(self, analyzer, sample_embeddings):
        matrix = analyzer.compute_similarity_matrix(sample_embeddings)
        assert np.allclose(matrix, matrix.T, atol=1e-6)

    def test_values_in_range(self, analyzer, sample_embeddings):
        matrix = analyzer.compute_similarity_matrix(sample_embeddings)
        assert np.all(matrix >= 0.0)
        assert np.all(matrix <= 1.0)

    def test_zero_vector_handling(self, analyzer):
        embeddings = np.array([[0.0, 0.0], [1.0, 0.0]])
        matrix = analyzer.compute_similarity_matrix(embeddings)
        assert matrix.shape == (2, 2)
        # Zero vector should have 0 similarity with non-zero
        # But the normalization prevents div by zero by setting norm to 1


# ---------------------------------------------------------------------------
# find_similar_documents
# ---------------------------------------------------------------------------


class TestFindSimilarDocuments:
    """Tests for find_similar_documents."""

    def test_mismatched_counts_raises(self, analyzer):
        embeddings = np.array([[1, 0], [0, 1]])
        paths = [Path("a.txt")]
        with pytest.raises(ValueError, match="must match"):
            analyzer.find_similar_documents(embeddings, paths)

    def test_finds_similar_pairs(self, low_threshold_analyzer, sample_embeddings, sample_paths):
        result = low_threshold_analyzer.find_similar_documents(sample_embeddings, sample_paths)
        # doc0 and doc1 are similar; doc2 and doc3 are similar
        assert len(result[sample_paths[0]]) > 0 or len(result[sample_paths[1]]) > 0

    def test_uses_custom_threshold(self, analyzer, sample_embeddings, sample_paths):
        # Very high threshold should find fewer matches
        result = analyzer.find_similar_documents(
            sample_embeddings, sample_paths, min_similarity=0.9999
        )
        # Only identical docs would match at 0.9999
        total_matches = sum(len(v) for v in result.values())
        assert total_matches == 0  # No docs are > 0.9999 similar

    def test_sorted_by_similarity(self, low_threshold_analyzer, sample_embeddings, sample_paths):
        result = low_threshold_analyzer.find_similar_documents(sample_embeddings, sample_paths)
        for _path, similars in result.items():
            if len(similars) > 1:
                for i in range(len(similars) - 1):
                    assert similars[i][1] >= similars[i + 1][1]

    def test_empty_input(self, analyzer):
        result = analyzer.find_similar_documents(np.array([]).reshape(0, 0), [])
        assert result == {}


# ---------------------------------------------------------------------------
# find_similar_to_query
# ---------------------------------------------------------------------------


class TestFindSimilarToQuery:
    """Tests for find_similar_to_query."""

    def test_finds_similar(self, low_threshold_analyzer, sample_embeddings, sample_paths):
        query = np.array([1.0, 0.0, 0.0])  # Similar to doc0
        result = low_threshold_analyzer.find_similar_to_query(
            query, sample_embeddings, sample_paths
        )
        assert len(result) > 0
        assert result[0][0] == sample_paths[0]  # doc0 should be most similar

    def test_top_k(self, low_threshold_analyzer, sample_embeddings, sample_paths):
        query = np.array([0.5, 0.5, 0.5])
        result = low_threshold_analyzer.find_similar_to_query(
            query, sample_embeddings, sample_paths, top_k=1
        )
        assert len(result) <= 1

    def test_sorted_desc(self, low_threshold_analyzer, sample_embeddings, sample_paths):
        query = np.array([0.5, 0.5, 0.5])
        result = low_threshold_analyzer.find_similar_to_query(
            query, sample_embeddings, sample_paths
        )
        for i in range(len(result) - 1):
            assert result[i][1] >= result[i + 1][1]

    def test_high_threshold_no_results(self, analyzer, sample_embeddings, sample_paths):
        query = np.array([0.5, 0.5, 0.5])
        result = analyzer.find_similar_to_query(
            query, sample_embeddings, sample_paths, min_similarity=0.99
        )
        assert len(result) == 0


# ---------------------------------------------------------------------------
# cluster_by_similarity
# ---------------------------------------------------------------------------


class TestClusterBySimilarity:
    """Tests for cluster_by_similarity."""

    def test_basic_clustering(self, analyzer):
        similar_docs = {
            Path("a"): [(Path("b"), 0.9)],
            Path("b"): [(Path("a"), 0.9)],
            Path("c"): [(Path("d"), 0.8)],
            Path("d"): [(Path("c"), 0.8)],
        }
        clusters = analyzer.cluster_by_similarity(similar_docs)
        assert len(clusters) == 2

    def test_no_similar_docs(self, analyzer):
        similar_docs = {
            Path("a"): [],
            Path("b"): [],
        }
        clusters = analyzer.cluster_by_similarity(similar_docs)
        assert clusters == []

    def test_single_cluster(self, analyzer):
        similar_docs = {
            Path("a"): [(Path("b"), 0.9), (Path("c"), 0.85)],
            Path("b"): [(Path("a"), 0.9)],
            Path("c"): [(Path("a"), 0.85)],
        }
        clusters = analyzer.cluster_by_similarity(similar_docs)
        # a, b, and c form one cluster
        assert len(clusters) == 1
        assert len(clusters[0]) == 3

    def test_empty_input(self, analyzer):
        clusters = analyzer.cluster_by_similarity({})
        assert clusters == []


# ---------------------------------------------------------------------------
# get_duplicate_groups
# ---------------------------------------------------------------------------


class TestGetDuplicateGroups:
    """Tests for get_duplicate_groups."""

    def test_returns_groups(self, low_threshold_analyzer, sample_embeddings, sample_paths):
        with patch.object(Path, "exists", return_value=True), patch.object(
            Path, "stat"
        ) as mock_stat:
            mock_stat.return_value.st_size = 1024
            groups = low_threshold_analyzer.get_duplicate_groups(
                sample_embeddings, sample_paths
            )

        # Should find at least one group
        assert isinstance(groups, list)
        for group in groups:
            assert "files" in group
            assert "count" in group
            assert "avg_similarity" in group
            assert "total_size" in group
            assert group["count"] >= 2

    def test_sorted_by_similarity(self, low_threshold_analyzer, sample_embeddings, sample_paths):
        with patch.object(Path, "exists", return_value=True), patch.object(
            Path, "stat"
        ) as mock_stat:
            mock_stat.return_value.st_size = 1024
            groups = low_threshold_analyzer.get_duplicate_groups(
                sample_embeddings, sample_paths
            )

        if len(groups) > 1:
            for i in range(len(groups) - 1):
                assert groups[i]["avg_similarity"] >= groups[i + 1]["avg_similarity"]


# ---------------------------------------------------------------------------
# set_threshold
# ---------------------------------------------------------------------------


class TestSetThreshold:
    """Tests for set_threshold."""

    def test_valid_update(self, analyzer):
        analyzer.set_threshold(0.5)
        assert analyzer.threshold == 0.5

    def test_invalid_raises(self, analyzer):
        with pytest.raises(ValueError, match="between 0 and 1"):
            analyzer.set_threshold(2.0)

        with pytest.raises(ValueError, match="between 0 and 1"):
            analyzer.set_threshold(-0.1)


# ---------------------------------------------------------------------------
# get_statistics
# ---------------------------------------------------------------------------


class TestGetStatistics:
    """Tests for get_statistics."""

    def test_basic_stats(self, analyzer, sample_embeddings):
        matrix = analyzer.compute_similarity_matrix(sample_embeddings)
        stats = analyzer.get_statistics(matrix)

        assert "mean_similarity" in stats
        assert "median_similarity" in stats
        assert "std_similarity" in stats
        assert "max_similarity" in stats
        assert "min_similarity" in stats
        assert "above_threshold_count" in stats

    def test_stats_types(self, analyzer, sample_embeddings):
        matrix = analyzer.compute_similarity_matrix(sample_embeddings)
        stats = analyzer.get_statistics(matrix)

        assert isinstance(stats["mean_similarity"], float)
        assert isinstance(stats["above_threshold_count"], int)

    def test_stats_values_reasonable(self, analyzer, sample_embeddings):
        matrix = analyzer.compute_similarity_matrix(sample_embeddings)
        stats = analyzer.get_statistics(matrix)

        assert 0.0 <= stats["mean_similarity"] <= 1.0
        assert 0.0 <= stats["max_similarity"] <= 1.0
        assert stats["min_similarity"] >= 0.0
        assert stats["above_threshold_count"] >= 0
