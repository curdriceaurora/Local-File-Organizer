"""
Document embedding module using TF-IDF vectorization.

Converts text documents into numerical vectors for similarity comparison.
"""

from typing import List, Dict, Optional, Tuple
from pathlib import Path
import numpy as np
import logging
import pickle

logger = logging.getLogger(__name__)


class DocumentEmbedder:
    """
    Embeds documents using TF-IDF vectorization.

    Uses scikit-learn's TfidfVectorizer for efficient text vectorization.
    Supports caching for performance optimization.
    """

    def __init__(
        self,
        max_features: int = 5000,
        ngram_range: Tuple[int, int] = (1, 2),
        min_df: int = 1,
        max_df: float = 0.95,
        cache_path: Optional[Path] = None
    ):
        """
        Initialize the document embedder.

        Args:
            max_features: Maximum number of features (vocabulary size)
            ngram_range: Range of n-grams to consider (e.g., (1,2) for unigrams and bigrams)
            min_df: Minimum document frequency for terms
            max_df: Maximum document frequency (ignore terms appearing in >max_df of documents)
            cache_path: Path to cache embeddings (optional)
        """
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer

            self.vectorizer = TfidfVectorizer(
                max_features=max_features,
                ngram_range=ngram_range,
                min_df=min_df,
                max_df=max_df,
                stop_words='english',
                lowercase=True,
                strip_accents='unicode'
            )

        except ImportError:
            raise ImportError(
                "scikit-learn is required for document embedding. "
                "Install with: pip install scikit-learn>=1.4.0"
            )

        self.max_features = max_features
        self.ngram_range = ngram_range
        self.cache_path = cache_path
        self.is_fitted = False

        # Cache for embeddings {document_hash: embedding}
        self.embedding_cache: Dict[str, np.ndarray] = {}

        # Load cache if available
        if cache_path and cache_path.exists():
            self._load_cache()

        logger.info(
            f"DocumentEmbedder initialized: max_features={max_features}, "
            f"ngram_range={ngram_range}"
        )

    def fit_transform(self, documents: List[str]) -> np.ndarray:
        """
        Fit the vectorizer and transform documents to embeddings.

        Args:
            documents: List of document texts

        Returns:
            Matrix of document embeddings (n_documents x n_features)
        """
        if not documents:
            logger.warning("Empty document list provided")
            return np.array([])

        logger.info(f"Fitting vectorizer on {len(documents)} documents")

        try:
            # Fit and transform
            embeddings = self.vectorizer.fit_transform(documents)
            self.is_fitted = True

            # Convert to dense array for easier manipulation
            dense_embeddings = embeddings.toarray()

            logger.info(
                f"Generated embeddings: shape={dense_embeddings.shape}, "
                f"vocabulary_size={len(self.vectorizer.vocabulary_)}"
            )

            return dense_embeddings

        except Exception as e:
            logger.error(f"Error during fit_transform: {e}")
            raise

    def transform(self, document: str) -> np.ndarray:
        """
        Transform a single document to embedding.

        Args:
            document: Document text

        Returns:
            Document embedding vector

        Raises:
            RuntimeError: If vectorizer not fitted
        """
        if not self.is_fitted:
            raise RuntimeError(
                "Vectorizer not fitted. Call fit_transform() first."
            )

        # Check cache
        doc_hash = self._hash_document(document)
        if doc_hash in self.embedding_cache:
            logger.debug(f"Cache hit for document (hash={doc_hash[:8]})")
            return self.embedding_cache[doc_hash]

        # Transform
        embedding = self.vectorizer.transform([document]).toarray()[0]

        # Cache the embedding
        self.embedding_cache[doc_hash] = embedding

        return embedding

    def transform_batch(self, documents: List[str]) -> np.ndarray:
        """
        Transform multiple documents to embeddings.

        Args:
            documents: List of document texts

        Returns:
            Matrix of embeddings
        """
        if not self.is_fitted:
            raise RuntimeError(
                "Vectorizer not fitted. Call fit_transform() first."
            )

        embeddings = self.vectorizer.transform(documents).toarray()

        logger.debug(f"Transformed {len(documents)} documents")

        return embeddings

    def get_feature_names(self) -> List[str]:
        """
        Get the feature names (vocabulary terms).

        Returns:
            List of vocabulary terms

        Raises:
            RuntimeError: If vectorizer not fitted
        """
        if not self.is_fitted:
            raise RuntimeError(
                "Vectorizer not fitted. Call fit_transform() first."
            )

        try:
            # Try new API first (sklearn >= 1.0)
            return self.vectorizer.get_feature_names_out().tolist()
        except AttributeError:
            # Fall back to old API
            return self.vectorizer.get_feature_names()

    def get_vocabulary(self) -> Dict[str, int]:
        """
        Get the vocabulary dictionary.

        Returns:
            Dictionary mapping terms to indices
        """
        if not self.is_fitted:
            raise RuntimeError(
                "Vectorizer not fitted. Call fit_transform() first."
            )

        return self.vectorizer.vocabulary_

    def get_top_terms(
        self,
        embedding: np.ndarray,
        top_n: int = 10
    ) -> List[Tuple[str, float]]:
        """
        Get top N terms from an embedding by weight.

        Args:
            embedding: Document embedding vector
            top_n: Number of top terms to return

        Returns:
            List of (term, weight) tuples
        """
        if not self.is_fitted:
            raise RuntimeError(
                "Vectorizer not fitted. Call fit_transform() first."
            )

        # Get feature names
        feature_names = self.get_feature_names()

        # Get top indices
        top_indices = np.argsort(embedding)[-top_n:][::-1]

        # Get terms and weights
        top_terms = [
            (feature_names[i], embedding[i])
            for i in top_indices
            if embedding[i] > 0
        ]

        return top_terms

    def save_model(self, path: Path) -> None:
        """
        Save the fitted vectorizer to disk.

        Args:
            path: Path to save the model
        """
        if not self.is_fitted:
            logger.warning("Cannot save unfitted vectorizer")
            return

        try:
            with open(path, 'wb') as f:
                pickle.dump(self.vectorizer, f)

            logger.info(f"Saved vectorizer to {path}")

        except Exception as e:
            logger.error(f"Error saving vectorizer: {e}")

    def load_model(self, path: Path) -> None:
        """
        Load a fitted vectorizer from disk.

        Args:
            path: Path to load the model from
        """
        try:
            with open(path, 'rb') as f:
                self.vectorizer = pickle.load(f)

            self.is_fitted = True
            logger.info(f"Loaded vectorizer from {path}")

        except Exception as e:
            logger.error(f"Error loading vectorizer: {e}")
            raise

    def clear_cache(self) -> None:
        """Clear the embedding cache."""
        cache_size = len(self.embedding_cache)
        self.embedding_cache.clear()
        logger.info(f"Cleared {cache_size} cached embeddings")

    def _hash_document(self, document: str) -> str:
        """Generate hash for a document."""
        import hashlib
        return hashlib.sha256(document.encode()).hexdigest()

    def _save_cache(self) -> None:
        """Save embedding cache to disk."""
        if not self.cache_path:
            return

        try:
            with open(self.cache_path, 'wb') as f:
                pickle.dump(self.embedding_cache, f)

            logger.debug(f"Saved {len(self.embedding_cache)} embeddings to cache")

        except Exception as e:
            logger.error(f"Error saving cache: {e}")

    def _load_cache(self) -> None:
        """Load embedding cache from disk."""
        if not self.cache_path or not self.cache_path.exists():
            return

        try:
            with open(self.cache_path, 'rb') as f:
                self.embedding_cache = pickle.load(f)

            logger.info(f"Loaded {len(self.embedding_cache)} embeddings from cache")

        except Exception as e:
            logger.error(f"Error loading cache: {e}")

    def __del__(self):
        """Cleanup: save cache on destruction."""
        if self.cache_path and self.embedding_cache:
            self._save_cache()
