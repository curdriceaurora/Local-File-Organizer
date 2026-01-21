"""
Document deduplication orchestrator.

Integrates text extraction, embedding, and semantic similarity analysis
for finding duplicate and similar documents.
"""

from pathlib import Path
from typing import List, Dict, Optional
import logging

from .extractor import DocumentExtractor
from .embedder import DocumentEmbedder
from .semantic import SemanticAnalyzer

logger = logging.getLogger(__name__)


class DocumentDeduplicator:
    """
    Orchestrates document deduplication using semantic similarity.

    Workflow:
    1. Extract text from documents
    2. Generate TF-IDF embeddings
    3. Compute similarity
    4. Identify duplicate groups
    """

    def __init__(
        self,
        similarity_threshold: float = 0.85,
        max_features: int = 5000
    ):
        """
        Initialize document deduplicator.

        Args:
            similarity_threshold: Minimum similarity to consider duplicates
            max_features: Maximum TF-IDF features
        """
        self.extractor = DocumentExtractor()
        self.embedder = DocumentEmbedder(max_features=max_features)
        self.analyzer = SemanticAnalyzer(threshold=similarity_threshold)

        logger.info(
            f"DocumentDeduplicator initialized: "
            f"threshold={similarity_threshold}, features={max_features}"
        )

    def find_duplicates(
        self,
        file_paths: List[Path],
        min_text_length: int = 100
    ) -> Dict:
        """
        Find duplicate and similar documents.

        Args:
            file_paths: List of document paths to analyze
            min_text_length: Minimum text length to consider

        Returns:
            Dictionary with duplicate groups and statistics
        """
        logger.info(f"Finding duplicates among {len(file_paths)} documents")

        # Filter supported formats
        supported_files = [
            f for f in file_paths
            if self.extractor.supports_format(f)
        ]

        logger.info(f"Analyzing {len(supported_files)} supported documents")

        # Extract text
        extracted_texts = self.extractor.extract_batch(supported_files)

        # Filter by minimum length
        valid_docs = {}
        valid_paths = []

        for path, text in extracted_texts.items():
            if len(text) >= min_text_length:
                valid_docs[path] = text
                valid_paths.append(path)
            else:
                logger.debug(f"Skipping {path.name}: text too short ({len(text)} chars)")

        logger.info(f"{len(valid_docs)} documents have sufficient text")

        if len(valid_docs) < 2:
            logger.warning("Not enough valid documents for comparison")
            return {
                'duplicate_groups': [],
                'total_documents': len(file_paths),
                'analyzed_documents': len(valid_docs),
                'space_wasted': 0
            }

        # Generate embeddings
        texts = [valid_docs[p] for p in valid_paths]
        embeddings = self.embedder.fit_transform(texts)

        # Find similar documents
        duplicate_groups = self.analyzer.get_duplicate_groups(
            embeddings, valid_paths
        )

        # Calculate space wasted
        space_wasted = self._calculate_space_wasted(duplicate_groups)

        results = {
            'duplicate_groups': duplicate_groups,
            'total_documents': len(file_paths),
            'analyzed_documents': len(valid_docs),
            'space_wasted': space_wasted,
            'num_groups': len(duplicate_groups)
        }

        logger.info(
            f"Found {len(duplicate_groups)} duplicate groups, "
            f"{space_wasted / (1024*1024):.2f}MB wasted"
        )

        return results

    def compare_documents(
        self,
        doc1_path: Path,
        doc2_path: Path
    ) -> Optional[float]:
        """
        Compare two documents for similarity.

        Args:
            doc1_path: First document path
            doc2_path: Second document path

        Returns:
            Similarity score (0-1) or None if comparison fails
        """
        try:
            # Extract text
            text1 = self.extractor.extract_text(doc1_path)
            text2 = self.extractor.extract_text(doc2_path)

            if not text1 or not text2:
                logger.warning("One or both documents have no extractable text")
                return None

            # Generate embeddings
            embeddings = self.embedder.fit_transform([text1, text2])

            # Compute similarity
            similarity = self.analyzer.compute_similarity(
                embeddings[0], embeddings[1]
            )

            logger.info(
                f"Similarity between {doc1_path.name} and {doc2_path.name}: "
                f"{similarity:.2f}"
            )

            return similarity

        except Exception as e:
            logger.error(f"Error comparing documents: {e}")
            return None

    def _calculate_space_wasted(self, duplicate_groups: List[Dict]) -> int:
        """Calculate total space wasted by duplicates."""
        wasted = 0

        for group in duplicate_groups:
            # Assume keeping first file, rest are wasted
            files = [Path(f) for f in group['files']]
            if len(files) > 1:
                sizes = [
                    f.stat().st_size for f in files if f.exists()
                ]
                if sizes:
                    # Wasted = (count - 1) * avg_size
                    avg_size = sum(sizes) / len(sizes)
                    wasted += int((len(files) - 1) * avg_size)

        return wasted
