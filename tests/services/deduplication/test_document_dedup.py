"""Tests for DocumentDeduplicator orchestrator.

Covers initialization, find_duplicates, compare_documents, and space calculation.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.unit
class TestDocumentDeduplicator(unittest.TestCase):
    """Test cases for DocumentDeduplicator."""

    @patch("file_organizer.services.deduplication.document_dedup.SemanticAnalyzer")
    @patch("file_organizer.services.deduplication.document_dedup.DocumentEmbedder")
    @patch("file_organizer.services.deduplication.document_dedup.DocumentExtractor")
    def test_init_default(self, mock_ext_cls, mock_emb_cls, mock_sem_cls):
        """Test default initialization."""
        from file_organizer.services.deduplication.document_dedup import (
            DocumentDeduplicator,
        )

        dedup = DocumentDeduplicator()
        mock_ext_cls.assert_called_once()
        mock_emb_cls.assert_called_once_with(max_features=5000)
        mock_sem_cls.assert_called_once_with(threshold=0.85)
        self.assertIsNotNone(dedup.extractor)
        self.assertIsNotNone(dedup.embedder)
        self.assertIsNotNone(dedup.analyzer)

    @patch("file_organizer.services.deduplication.document_dedup.SemanticAnalyzer")
    @patch("file_organizer.services.deduplication.document_dedup.DocumentEmbedder")
    @patch("file_organizer.services.deduplication.document_dedup.DocumentExtractor")
    def test_init_custom_params(self, mock_ext_cls, mock_emb_cls, mock_sem_cls):
        """Test initialization with custom parameters."""
        from file_organizer.services.deduplication.document_dedup import (
            DocumentDeduplicator,
        )

        DocumentDeduplicator(similarity_threshold=0.9, max_features=3000)
        mock_emb_cls.assert_called_once_with(max_features=3000)
        mock_sem_cls.assert_called_once_with(threshold=0.9)

    @patch("file_organizer.services.deduplication.document_dedup.SemanticAnalyzer")
    @patch("file_organizer.services.deduplication.document_dedup.DocumentEmbedder")
    @patch("file_organizer.services.deduplication.document_dedup.DocumentExtractor")
    def test_find_duplicates_not_enough_docs(self, mock_ext_cls, mock_emb_cls, mock_sem_cls):
        """Test find_duplicates returns empty when < 2 valid docs."""
        from file_organizer.services.deduplication.document_dedup import (
            DocumentDeduplicator,
        )

        dedup = DocumentDeduplicator()

        # Mock extractor
        dedup.extractor.supports_format.return_value = True
        dedup.extractor.extract_batch.return_value = {Path("/a.txt"): "short"}

        result = dedup.find_duplicates([Path("/a.txt")], min_text_length=100)
        self.assertEqual(result["duplicate_groups"], [])
        self.assertEqual(result["total_documents"], 1)
        self.assertEqual(result["analyzed_documents"], 0)
        self.assertEqual(result["space_wasted"], 0)

    @patch("file_organizer.services.deduplication.document_dedup.SemanticAnalyzer")
    @patch("file_organizer.services.deduplication.document_dedup.DocumentEmbedder")
    @patch("file_organizer.services.deduplication.document_dedup.DocumentExtractor")
    def test_find_duplicates_success(self, mock_ext_cls, mock_emb_cls, mock_sem_cls):
        """Test find_duplicates with enough valid docs."""
        from file_organizer.services.deduplication.document_dedup import (
            DocumentDeduplicator,
        )

        dedup = DocumentDeduplicator()

        p1 = Path("/doc1.txt")
        p2 = Path("/doc2.txt")
        p3 = Path("/doc3.txt")

        # supports_format returns True for all
        dedup.extractor.supports_format.return_value = True

        # extract_batch returns long texts for 2 of 3
        dedup.extractor.extract_batch.return_value = {
            p1: "a" * 200,
            p2: "b" * 200,
            p3: "short",
        }

        mock_embeddings = MagicMock()
        dedup.embedder.fit_transform.return_value = mock_embeddings

        groups = [
            {
                "files": [str(p1), str(p2)],
                "count": 2,
                "avg_similarity": 0.92,
                "total_size": 400,
                "representative": str(p1),
            }
        ]
        dedup.analyzer.get_duplicate_groups.return_value = groups

        # Mock _calculate_space_wasted
        with patch.object(dedup, "_calculate_space_wasted", return_value=200):
            result = dedup.find_duplicates([p1, p2, p3], min_text_length=100)

        self.assertEqual(result["num_groups"], 1)
        self.assertEqual(result["analyzed_documents"], 2)
        self.assertEqual(result["total_documents"], 3)
        self.assertEqual(result["space_wasted"], 200)
        self.assertEqual(len(result["duplicate_groups"]), 1)

    @patch("file_organizer.services.deduplication.document_dedup.SemanticAnalyzer")
    @patch("file_organizer.services.deduplication.document_dedup.DocumentEmbedder")
    @patch("file_organizer.services.deduplication.document_dedup.DocumentExtractor")
    def test_find_duplicates_filters_unsupported(self, mock_ext_cls, mock_emb_cls, mock_sem_cls):
        """Test that unsupported formats are filtered out."""
        from file_organizer.services.deduplication.document_dedup import (
            DocumentDeduplicator,
        )

        dedup = DocumentDeduplicator()
        dedup.extractor.supports_format.side_effect = lambda f: f.suffix == ".txt"
        dedup.extractor.extract_batch.return_value = {}

        dedup.find_duplicates([Path("/a.txt"), Path("/b.exe")], min_text_length=100)
        # Only .txt should be passed to extract_batch
        args = dedup.extractor.extract_batch.call_args[0][0]
        self.assertEqual(len(args), 1)
        self.assertEqual(args[0].suffix, ".txt")

    @patch("file_organizer.services.deduplication.document_dedup.SemanticAnalyzer")
    @patch("file_organizer.services.deduplication.document_dedup.DocumentEmbedder")
    @patch("file_organizer.services.deduplication.document_dedup.DocumentExtractor")
    def test_compare_documents_success(self, mock_ext_cls, mock_emb_cls, mock_sem_cls):
        """Test comparing two documents returns similarity score."""
        from file_organizer.services.deduplication.document_dedup import (
            DocumentDeduplicator,
        )

        dedup = DocumentDeduplicator()

        dedup.extractor.extract_text.side_effect = [
            "text one long enough",
            "text two long enough",
        ]
        mock_embeddings = [MagicMock(), MagicMock()]
        dedup.embedder.fit_transform.return_value = mock_embeddings
        dedup.analyzer.compute_similarity.return_value = 0.87

        result = dedup.compare_documents(Path("/a.txt"), Path("/b.txt"))
        self.assertAlmostEqual(result, 0.87)

    @patch("file_organizer.services.deduplication.document_dedup.SemanticAnalyzer")
    @patch("file_organizer.services.deduplication.document_dedup.DocumentEmbedder")
    @patch("file_organizer.services.deduplication.document_dedup.DocumentExtractor")
    def test_compare_documents_empty_text(self, mock_ext_cls, mock_emb_cls, mock_sem_cls):
        """Test compare returns None when text is empty."""
        from file_organizer.services.deduplication.document_dedup import (
            DocumentDeduplicator,
        )

        dedup = DocumentDeduplicator()
        dedup.extractor.extract_text.side_effect = ["", "some text"]

        result = dedup.compare_documents(Path("/a.txt"), Path("/b.txt"))
        self.assertIsNone(result)

    @patch("file_organizer.services.deduplication.document_dedup.SemanticAnalyzer")
    @patch("file_organizer.services.deduplication.document_dedup.DocumentEmbedder")
    @patch("file_organizer.services.deduplication.document_dedup.DocumentExtractor")
    def test_compare_documents_exception(self, mock_ext_cls, mock_emb_cls, mock_sem_cls):
        """Test compare returns None on exception."""
        from file_organizer.services.deduplication.document_dedup import (
            DocumentDeduplicator,
        )

        dedup = DocumentDeduplicator()
        dedup.extractor.extract_text.side_effect = RuntimeError("boom")

        result = dedup.compare_documents(Path("/a.txt"), Path("/b.txt"))
        self.assertIsNone(result)

    @patch("file_organizer.services.deduplication.document_dedup.SemanticAnalyzer")
    @patch("file_organizer.services.deduplication.document_dedup.DocumentEmbedder")
    @patch("file_organizer.services.deduplication.document_dedup.DocumentExtractor")
    def test_calculate_space_wasted(self, mock_ext_cls, mock_emb_cls, mock_sem_cls):
        """Test _calculate_space_wasted with mock file sizes."""
        import tempfile

        from file_organizer.services.deduplication.document_dedup import (
            DocumentDeduplicator,
        )

        dedup = DocumentDeduplicator()

        # Create real temp files for stat() to work
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f1:
            f1.write(b"x" * 1000)
            f1_path = f1.name

        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f2:
            f2.write(b"y" * 1000)
            f2_path = f2.name

        groups = [
            {"files": [f1_path, f2_path]},
        ]
        wasted = dedup._calculate_space_wasted(groups)
        # 2 files, keep 1, wasted = 1 * avg_size ~ 1000
        self.assertGreater(wasted, 0)

        # Clean up
        Path(f1_path).unlink(missing_ok=True)
        Path(f2_path).unlink(missing_ok=True)

    @patch("file_organizer.services.deduplication.document_dedup.SemanticAnalyzer")
    @patch("file_organizer.services.deduplication.document_dedup.DocumentEmbedder")
    @patch("file_organizer.services.deduplication.document_dedup.DocumentExtractor")
    def test_calculate_space_wasted_nonexistent_files(
        self, mock_ext_cls, mock_emb_cls, mock_sem_cls
    ):
        """Test _calculate_space_wasted with nonexistent files."""
        from file_organizer.services.deduplication.document_dedup import (
            DocumentDeduplicator,
        )

        dedup = DocumentDeduplicator()
        groups = [
            {"files": ["/nonexistent1.txt", "/nonexistent2.txt"]},
        ]
        wasted = dedup._calculate_space_wasted(groups)
        self.assertEqual(wasted, 0)

    @patch("file_organizer.services.deduplication.document_dedup.SemanticAnalyzer")
    @patch("file_organizer.services.deduplication.document_dedup.DocumentEmbedder")
    @patch("file_organizer.services.deduplication.document_dedup.DocumentExtractor")
    def test_calculate_space_wasted_single_file_group(
        self, mock_ext_cls, mock_emb_cls, mock_sem_cls
    ):
        """Test space calculation with single-file groups."""
        from file_organizer.services.deduplication.document_dedup import (
            DocumentDeduplicator,
        )

        dedup = DocumentDeduplicator()
        groups = [{"files": ["/only_one.txt"]}]
        wasted = dedup._calculate_space_wasted(groups)
        self.assertEqual(wasted, 0)


if __name__ == "__main__":
    unittest.main()
