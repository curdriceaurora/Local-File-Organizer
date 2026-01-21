"""
Semantic similarity analysis module.

Computes cosine similarity between document embeddings and identifies similar documents.
"""

from typing import List, Dict, Optional, Tuple
from pathlib import Path
import numpy as np
import logging

logger = logging.getLogger(__name__)


class SemanticAnalyzer:
    """
    Analyzes semantic similarity between documents.

    Uses cosine similarity on TF-IDF embeddings to find similar documents.
    Supports clustering and efficient pairwise comparisons.
    """

    def __init__(self, threshold: float = 0.85):
        """
        Initialize the semantic analyzer.

        Args:
            threshold: Minimum similarity score to consider documents similar (0-1)
        """
        if not 0 <= threshold <= 1:
            raise ValueError("Threshold must be between 0 and 1")

        self.threshold = threshold
        logger.info(f"SemanticAnalyzer initialized with threshold={threshold}")

    def compute_similarity(
        self,
        doc1_vector: np.ndarray,
        doc2_vector: np.ndarray
    ) -> float:
        """
        Compute cosine similarity between two document vectors.

        Args:
            doc1_vector: First document embedding
            doc2_vector: Second document embedding

        Returns:
            Similarity score between 0 and 1
        """
        # Cosine similarity = dot(A, B) / (norm(A) * norm(B))
        dot_product = np.dot(doc1_vector, doc2_vector)

        norm1 = np.linalg.norm(doc1_vector)
        norm2 = np.linalg.norm(doc2_vector)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        similarity = dot_product / (norm1 * norm2)

        # Clamp to [0, 1] range (floating point errors can cause slight overshoots)
        return float(np.clip(similarity, 0.0, 1.0))

    def find_similar_documents(
        self,
        embeddings: np.ndarray,
        paths: List[Path],
        min_similarity: Optional[float] = None
    ) -> Dict[Path, List[Tuple[Path, float]]]:
        """
        Find similar documents based on embeddings.

        Args:
            embeddings: Matrix of document embeddings (n_documents x n_features)
            paths: List of file paths corresponding to embeddings
            min_similarity: Minimum similarity threshold (default: self.threshold)

        Returns:
            Dictionary mapping each path to list of (similar_path, similarity) tuples
        """
        if min_similarity is None:
            min_similarity = self.threshold

        if len(embeddings) != len(paths):
            raise ValueError(
                f"Embeddings count ({len(embeddings)}) must match paths count ({len(paths)})"
            )

        logger.info(f"Finding similar documents among {len(paths)} documents")

        similar_docs: Dict[Path, List[Tuple[Path, float]]] = {path: [] for path in paths}

        # Compute pairwise similarities
        for i in range(len(paths)):
            for j in range(i + 1, len(paths)):
                similarity = self.compute_similarity(embeddings[i], embeddings[j])

                if similarity >= min_similarity:
                    similar_docs[paths[i]].append((paths[j], similarity))
                    similar_docs[paths[j]].append((paths[i], similarity))

        # Sort by similarity (descending)
        for path in similar_docs:
            similar_docs[path].sort(key=lambda x: x[1], reverse=True)

        # Count duplicates found
        duplicate_count = sum(1 for v in similar_docs.values() if len(v) > 0)
        logger.info(f"Found {duplicate_count} documents with similar content")

        return similar_docs

    def find_similar_to_query(
        self,
        query_embedding: np.ndarray,
        document_embeddings: np.ndarray,
        paths: List[Path],
        top_k: Optional[int] = None,
        min_similarity: Optional[float] = None
    ) -> List[Tuple[Path, float]]:
        """
        Find documents similar to a query document.

        Args:
            query_embedding: Query document embedding
            document_embeddings: Matrix of document embeddings
            paths: List of file paths
            top_k: Return top K most similar (optional)
            min_similarity: Minimum similarity threshold

        Returns:
            List of (path, similarity) tuples, sorted by similarity
        """
        if min_similarity is None:
            min_similarity = self.threshold

        similarities = []

        for i, doc_embedding in enumerate(document_embeddings):
            similarity = self.compute_similarity(query_embedding, doc_embedding)

            if similarity >= min_similarity:
                similarities.append((paths[i], similarity))

        # Sort by similarity (descending)
        similarities.sort(key=lambda x: x[1], reverse=True)

        # Return top K if specified
        if top_k is not None:
            similarities = similarities[:top_k]

        logger.debug(f"Found {len(similarities)} similar documents to query")

        return similarities

    def cluster_by_similarity(
        self,
        similar_docs: Dict[Path, List[Tuple[Path, float]]]
    ) -> List[List[Path]]:
        """
        Cluster documents by similarity into groups.

        Uses a simple greedy clustering approach: documents are clustered if they
        share similar documents.

        Args:
            similar_docs: Dictionary from find_similar_documents()

        Returns:
            List of document clusters (each cluster is a list of paths)
        """
        logger.info("Clustering similar documents")

        # Track which documents have been assigned to clusters
        assigned = set()
        clusters = []

        for path, similars in similar_docs.items():
            if path in assigned or not similars:
                continue

            # Create new cluster
            cluster = {path}
            assigned.add(path)

            # Add all similar documents
            for similar_path, _ in similars:
                if similar_path not in assigned:
                    cluster.add(similar_path)
                    assigned.add(similar_path)

            clusters.append(list(cluster))

        logger.info(f"Created {len(clusters)} document clusters")

        return clusters

    def compute_similarity_matrix(
        self,
        embeddings: np.ndarray
    ) -> np.ndarray:
        """
        Compute full pairwise similarity matrix.

        Args:
            embeddings: Matrix of document embeddings

        Returns:
            Similarity matrix (n_documents x n_documents)
        """
        # Normalize embeddings for efficient cosine similarity
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        norms[norms == 0] = 1  # Avoid division by zero
        normalized = embeddings / norms

        # Cosine similarity matrix = normalized @ normalized.T
        similarity_matrix = np.dot(normalized, normalized.T)

        # Clamp values to [0, 1]
        similarity_matrix = np.clip(similarity_matrix, 0.0, 1.0)

        logger.debug(f"Computed similarity matrix: shape={similarity_matrix.shape}")

        return similarity_matrix

    def get_duplicate_groups(
        self,
        embeddings: np.ndarray,
        paths: List[Path],
        min_similarity: Optional[float] = None
    ) -> List[Dict]:
        """
        Get groups of duplicate/similar documents with metadata.

        Args:
            embeddings: Document embeddings
            paths: File paths
            min_similarity: Minimum similarity threshold

        Returns:
            List of duplicate group dictionaries
        """
        similar_docs = self.find_similar_documents(
            embeddings, paths, min_similarity
        )

        clusters = self.cluster_by_similarity(similar_docs)

        # Build group metadata
        groups = []

        for cluster in clusters:
            if len(cluster) < 2:
                continue

            # Calculate average similarity within cluster
            cluster_sims = []
            for i, path1 in enumerate(cluster):
                for path2 in cluster[i + 1:]:
                    # Find similarity from similar_docs
                    sims = [s for p, s in similar_docs.get(path1, []) if p == path2]
                    if sims:
                        cluster_sims.append(sims[0])

            avg_similarity = (
                sum(cluster_sims) / len(cluster_sims)
                if cluster_sims else 0.0
            )

            # Calculate total size
            total_size = sum(
                path.stat().st_size if path.exists() else 0
                for path in cluster
            )

            groups.append({
                'files': [str(p) for p in cluster],
                'count': len(cluster),
                'avg_similarity': avg_similarity,
                'total_size': total_size,
                'representative': str(cluster[0])  # First file as representative
            })

        # Sort by similarity (descending)
        groups.sort(key=lambda g: g['avg_similarity'], reverse=True)

        logger.info(f"Identified {len(groups)} duplicate groups")

        return groups

    def set_threshold(self, threshold: float) -> None:
        """
        Update the similarity threshold.

        Args:
            threshold: New threshold value (0-1)
        """
        if not 0 <= threshold <= 1:
            raise ValueError("Threshold must be between 0 and 1")

        self.threshold = threshold
        logger.info(f"Updated similarity threshold to {threshold}")

    def get_statistics(
        self,
        similarity_matrix: np.ndarray
    ) -> Dict:
        """
        Compute statistics from similarity matrix.

        Args:
            similarity_matrix: Pairwise similarity matrix

        Returns:
            Statistics dictionary
        """
        # Exclude diagonal (self-similarity)
        n = similarity_matrix.shape[0]
        mask = ~np.eye(n, dtype=bool)
        similarities = similarity_matrix[mask]

        stats = {
            'mean_similarity': float(np.mean(similarities)),
            'median_similarity': float(np.median(similarities)),
            'std_similarity': float(np.std(similarities)),
            'max_similarity': float(np.max(similarities)),
            'min_similarity': float(np.min(similarities)),
            'above_threshold_count': int(np.sum(similarities >= self.threshold))
        }

        return stats
