"""Tests for DocumentEmbedder class.

Tests TF-IDF vectorization, fit/transform, caching, model save/load,
and feature extraction. scikit-learn is mocked where needed.
"""

from __future__ import annotations

import hashlib
import pickle
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_vectorizer():
    """Create a mock TfidfVectorizer."""
    vectorizer = MagicMock()
    vectorizer.vocabulary_ = {"hello": 0, "world": 1, "python": 2}

    # fit_transform returns a sparse matrix mock
    mock_sparse = MagicMock()
    mock_sparse.toarray.return_value = np.array([[0.5, 0.3, 0.0], [0.0, 0.4, 0.6]])
    vectorizer.fit_transform.return_value = mock_sparse

    # transform returns a sparse matrix mock
    mock_transform = MagicMock()
    mock_transform.toarray.return_value = np.array([[0.1, 0.2, 0.3]])
    vectorizer.transform.return_value = mock_transform

    # get_feature_names_out
    vectorizer.get_feature_names_out.return_value = np.array(["hello", "world", "python"])

    return vectorizer


@pytest.fixture
def embedder(mock_vectorizer):
    """Create a DocumentEmbedder with mocked sklearn."""
    mock_tfidf_cls = MagicMock(return_value=mock_vectorizer)

    with patch.dict(
        "sys.modules",
        {
            "sklearn": MagicMock(),
            "sklearn.feature_extraction": MagicMock(),
            "sklearn.feature_extraction.text": MagicMock(),
        },
    ):
        with patch("sklearn.feature_extraction.text.TfidfVectorizer", mock_tfidf_cls):
            from file_organizer.services.deduplication.embedder import DocumentEmbedder

            emb = DocumentEmbedder(max_features=100, ngram_range=(1, 2))
            emb.vectorizer = mock_vectorizer
            return emb


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDocumentEmbedderInit:
    """Tests for DocumentEmbedder initialization."""

    def test_attributes_set(self, embedder):
        assert embedder.max_features == 100
        assert embedder.ngram_range == (1, 2)
        assert embedder.is_fitted is False
        assert embedder.embedding_cache == {}

    def test_sklearn_import_error(self):
        """Raises ImportError when sklearn not available."""
        with patch.dict(
            "sys.modules",
            {
                "sklearn": None,
                "sklearn.feature_extraction": None,
                "sklearn.feature_extraction.text": None,
            },
        ):
            with pytest.raises(ImportError, match="scikit-learn"):
                # Force reimport
                import importlib

                import file_organizer.services.deduplication.embedder as mod

                importlib.reload(mod)
                mod.DocumentEmbedder()

    def test_cache_path_not_set(self, embedder):
        assert embedder.cache_path is None


# ---------------------------------------------------------------------------
# fit_transform
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFitTransform:
    """Tests for fit_transform."""

    def test_empty_documents(self, embedder):
        result = embedder.fit_transform([])
        assert len(result) == 0

    def test_returns_dense_array(self, embedder):
        result = embedder.fit_transform(["hello world", "python code"])
        assert isinstance(result, np.ndarray)
        assert result.shape == (2, 3)

    def test_sets_is_fitted(self, embedder):
        embedder.fit_transform(["doc1", "doc2"])
        assert embedder.is_fitted is True

    def test_calls_vectorizer_fit_transform(self, embedder, mock_vectorizer):
        embedder.fit_transform(["doc1", "doc2"])
        mock_vectorizer.fit_transform.assert_called_once_with(["doc1", "doc2"])

    def test_error_propagates(self, embedder, mock_vectorizer):
        mock_vectorizer.fit_transform.side_effect = RuntimeError("sklearn error")
        with pytest.raises(RuntimeError, match="sklearn error"):
            embedder.fit_transform(["doc"])


# ---------------------------------------------------------------------------
# transform (single document)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestTransform:
    """Tests for transform."""

    def test_not_fitted_raises(self, embedder):
        with pytest.raises(RuntimeError, match="not fitted"):
            embedder.transform("some text")

    def test_returns_embedding(self, embedder, mock_vectorizer):
        embedder.is_fitted = True
        result = embedder.transform("hello world")
        assert isinstance(result, np.ndarray)

    def test_caches_result(self, embedder, mock_vectorizer):
        embedder.is_fitted = True
        embedder.transform("hello world")
        # Second call should use cache
        embedder.transform("hello world")
        # transform should only be called once (second time from cache)
        assert mock_vectorizer.transform.call_count == 1

    def test_cache_key_is_hash(self, embedder):
        doc = "test document"
        doc_hash = hashlib.sha256(doc.encode()).hexdigest()
        result = embedder._hash_document(doc)
        assert result == doc_hash


# ---------------------------------------------------------------------------
# transform_batch
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestTransformBatch:
    """Tests for transform_batch."""

    def test_not_fitted_raises(self, embedder):
        with pytest.raises(RuntimeError, match="not fitted"):
            embedder.transform_batch(["doc1", "doc2"])

    def test_returns_matrix(self, embedder, mock_vectorizer):
        embedder.is_fitted = True
        mock_sparse = MagicMock()
        mock_sparse.toarray.return_value = np.array([[0.1, 0.2], [0.3, 0.4]])
        mock_vectorizer.transform.return_value = mock_sparse

        result = embedder.transform_batch(["doc1", "doc2"])
        assert isinstance(result, np.ndarray)


# ---------------------------------------------------------------------------
# get_feature_names / get_vocabulary
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFeatureAccess:
    """Tests for get_feature_names and get_vocabulary."""

    def test_get_feature_names_not_fitted(self, embedder):
        with pytest.raises(RuntimeError, match="not fitted"):
            embedder.get_feature_names()

    def test_get_feature_names(self, embedder, mock_vectorizer):
        embedder.is_fitted = True
        result = embedder.get_feature_names()
        assert result == ["hello", "world", "python"]

    def test_get_feature_names_fallback_old_api(self, embedder, mock_vectorizer):
        embedder.is_fitted = True
        mock_vectorizer.get_feature_names_out.side_effect = AttributeError
        mock_vectorizer.get_feature_names.return_value = ["a", "b"]
        result = embedder.get_feature_names()
        assert result == ["a", "b"]

    def test_get_vocabulary_not_fitted(self, embedder):
        with pytest.raises(RuntimeError, match="not fitted"):
            embedder.get_vocabulary()

    def test_get_vocabulary(self, embedder, mock_vectorizer):
        embedder.is_fitted = True
        vocab = embedder.get_vocabulary()
        assert vocab == {"hello": 0, "world": 1, "python": 2}


# ---------------------------------------------------------------------------
# get_top_terms
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetTopTerms:
    """Tests for get_top_terms."""

    def test_not_fitted_raises(self, embedder):
        with pytest.raises(RuntimeError, match="not fitted"):
            embedder.get_top_terms(np.array([0.1, 0.2, 0.3]))

    def test_returns_sorted_terms(self, embedder, mock_vectorizer):
        embedder.is_fitted = True
        embedding = np.array([0.5, 0.1, 0.8])
        top = embedder.get_top_terms(embedding, top_n=2)
        assert len(top) == 2
        # Highest weight first
        assert top[0][1] >= top[1][1]

    def test_skips_zero_weights(self, embedder, mock_vectorizer):
        embedder.is_fitted = True
        embedding = np.array([0.5, 0.0, 0.3])
        top = embedder.get_top_terms(embedding, top_n=5)
        # Should only return non-zero terms
        assert all(weight > 0 for _, weight in top)


# ---------------------------------------------------------------------------
# save_model / load_model
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestModelPersistence:
    """Tests for save_model and load_model."""

    def test_save_not_fitted(self, embedder, tmp_path):
        """Saving unfitted model logs warning and returns."""
        p = tmp_path / "model.pkl"
        embedder.save_model(p)
        assert not p.exists()

    def test_save_and_load(self, embedder, mock_vectorizer, tmp_path):
        embedder.is_fitted = True
        p = tmp_path / "model.pkl"

        # MagicMock can't be pickled, so mock pickle operations
        sentinel = object()
        with patch("file_organizer.services.deduplication.embedder.pickle.dump") as mock_dump:
            embedder.save_model(p)
            # save_model opens the file and calls pickle.dump
            mock_dump.assert_called_once()

        # Write a real pickle file so load_model can read it
        with open(p, "wb") as f:
            pickle.dump(sentinel, f)

        embedder.is_fitted = False
        embedder.load_model(p)
        assert embedder.is_fitted is True

    def test_load_nonexistent_raises(self, embedder):
        with pytest.raises((FileNotFoundError, OSError, ValueError)):
            embedder.load_model(Path("/nonexistent/model.pkl"))


# ---------------------------------------------------------------------------
# Cache operations
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCacheOperations:
    """Tests for cache operations."""

    def test_clear_cache(self, embedder):
        embedder.embedding_cache = {"hash1": np.array([1, 2]), "hash2": np.array([3, 4])}
        embedder.clear_cache()
        assert len(embedder.embedding_cache) == 0

    def test_save_cache(self, embedder, tmp_path):
        cache_path = tmp_path / "cache.pkl"
        embedder.cache_path = cache_path
        embedder.embedding_cache = {"hash1": np.array([1, 2])}
        embedder._save_cache()
        assert cache_path.exists()

    def test_load_cache(self, embedder, tmp_path):
        cache_path = tmp_path / "cache.pkl"
        embedder.cache_path = cache_path
        # Save a cache file
        with open(cache_path, "wb") as f:
            pickle.dump({"hash1": np.array([1, 2])}, f)

        embedder._load_cache()
        assert "hash1" in embedder.embedding_cache

    def test_save_cache_no_path(self, embedder):
        embedder.cache_path = None
        embedder._save_cache()  # Should not raise

    def test_load_cache_no_path(self, embedder):
        embedder.cache_path = None
        embedder._load_cache()  # Should not raise
