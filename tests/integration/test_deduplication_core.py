"""Integration tests for deduplication service modules.

Covers: DocumentExtractor, ImageDeduplicator, SemanticAnalyzer, BackupManager,
ImageUtils (functions + ImageMetadata), ConfidenceScorer, SuggestionEngine.
External models/APIs are mocked.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.ci]


# ---------------------------------------------------------------------------
# TestDocumentExtractor
# ---------------------------------------------------------------------------


class TestDocumentExtractor:
    """Tests for DocumentExtractor (extractor.py)."""

    def _make_extractor(self) -> Any:
        from file_organizer.services.deduplication.extractor import DocumentExtractor

        with patch(
            "file_organizer.services.deduplication.extractor.DocumentExtractor._check_dependencies"
        ):
            return DocumentExtractor()

    def test_supported_formats_populated(self) -> None:
        extractor = self._make_extractor()
        fmts = extractor.get_supported_formats()
        assert len(fmts) >= 5
        assert ".pdf" in fmts
        assert ".txt" in fmts

    def test_supports_format_txt(self, tmp_path: Path) -> None:
        extractor = self._make_extractor()
        f = tmp_path / "doc.txt"
        f.touch()
        assert extractor.supports_format(f) is True

    def test_supports_format_md(self, tmp_path: Path) -> None:
        extractor = self._make_extractor()
        f = tmp_path / "doc.md"
        f.touch()
        assert extractor.supports_format(f) is True

    def test_does_not_support_png(self, tmp_path: Path) -> None:
        extractor = self._make_extractor()
        f = tmp_path / "img.png"
        f.touch()
        assert extractor.supports_format(f) is False

    def test_extract_txt_file(self, tmp_path: Path) -> None:
        extractor = self._make_extractor()
        f = tmp_path / "hello.txt"
        f.write_text("hello world", encoding="utf-8")
        result = extractor.extract_text(f)
        assert result == "hello world"

    def test_extract_md_file(self, tmp_path: Path) -> None:
        extractor = self._make_extractor()
        f = tmp_path / "notes.md"
        f.write_text("# Title\n\nContent", encoding="utf-8")
        result = extractor.extract_text(f)
        assert "Title" in result

    def test_extract_text_file_not_found_raises(self, tmp_path: Path) -> None:
        extractor = self._make_extractor()
        missing = tmp_path / "missing.txt"
        with pytest.raises(OSError, match="File not found"):
            extractor.extract_text(missing)

    def test_extract_unsupported_format_raises(self, tmp_path: Path) -> None:
        extractor = self._make_extractor()
        f = tmp_path / "data.xyz"
        f.write_text("content")
        with pytest.raises(ValueError, match="Unsupported format"):
            extractor.extract_text(f)

    def test_extract_pdf_returns_empty_when_pypdf_missing(self, tmp_path: Path) -> None:
        extractor = self._make_extractor()
        f = tmp_path / "doc.pdf"
        f.write_bytes(b"%PDF-1.4")
        with patch.dict("sys.modules", {"pypdf": None}):
            result = extractor._extract_pdf(f)
        assert result == ""

    def test_extract_pdf_with_mock_pypdf(self, tmp_path: Path) -> None:
        extractor = self._make_extractor()
        f = tmp_path / "doc.pdf"
        f.write_bytes(b"%PDF-1.4")

        mock_page = MagicMock()
        mock_page.extract_text.return_value = "page text"
        mock_reader = MagicMock()
        mock_reader.pages = [mock_page]
        mock_pypdf = MagicMock()
        mock_pypdf.PdfReader.return_value = mock_reader

        with patch.dict("sys.modules", {"pypdf": mock_pypdf, "pypdf.errors": MagicMock()}):
            result = extractor._extract_pdf(f)

        assert result == "page text"

    def test_extract_docx_returns_empty_when_docx_missing(self, tmp_path: Path) -> None:
        extractor = self._make_extractor()
        f = tmp_path / "doc.docx"
        f.write_bytes(b"PK")
        with patch.dict("sys.modules", {"docx": None}):
            result = extractor._extract_docx(f)
        assert result == ""

    def test_extract_rtf_basic_fallback(self, tmp_path: Path) -> None:
        extractor = self._make_extractor()
        f = tmp_path / "doc.rtf"
        f.write_text(r"{\rtf1 Hello World}", encoding="utf-8")
        with patch.dict("sys.modules", {"striprtf": None, "striprtf.striprtf": None}):
            result = extractor._extract_rtf(f)
        assert "Hello World" in result or result == ""

    def test_extract_odt_valid_zip(self, tmp_path: Path) -> None:
        extractor = self._make_extractor()
        f = tmp_path / "doc.odt"
        content_xml = b"""<?xml version="1.0"?>
<office:document-content
  xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
  xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">
  <office:body><office:text>
    <text:p>Hello ODT</text:p>
  </office:text></office:body>
</office:document-content>"""
        with zipfile.ZipFile(f, "w") as zf:
            zf.writestr("content.xml", content_xml)
        result = extractor._extract_odt(f)
        assert isinstance(result, str)
        assert "Hello ODT" in result

    def test_extract_odt_bad_zip_returns_empty(self, tmp_path: Path) -> None:
        extractor = self._make_extractor()
        f = tmp_path / "bad.odt"
        f.write_bytes(b"not a zip")
        result = extractor._extract_odt(f)
        assert result == ""

    def test_extract_batch_returns_dict(self, tmp_path: Path) -> None:
        extractor = self._make_extractor()
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("alpha")
        f2.write_text("beta")
        results = extractor.extract_batch([f1, f2])
        assert isinstance(results, dict)
        assert results[f1] == "alpha"
        assert results[f2] == "beta"

    def test_extract_batch_handles_missing_files(self, tmp_path: Path) -> None:
        extractor = self._make_extractor()
        missing = tmp_path / "gone.txt"
        results = extractor.extract_batch([missing])
        assert isinstance(results, dict)
        assert results[missing] == ""

    def test_extract_batch_empty_list(self) -> None:
        extractor = self._make_extractor()
        results = extractor.extract_batch([])
        assert isinstance(results, dict)
        assert len(results) == 0

    def test_get_supported_formats_sorted(self) -> None:
        extractor = self._make_extractor()
        fmts = extractor.get_supported_formats()
        assert fmts == sorted(fmts)

    def test_extract_text_latin1_file(self, tmp_path: Path) -> None:
        extractor = self._make_extractor()
        f = tmp_path / "latin.txt"
        f.write_bytes("caf\xe9".encode("latin-1"))
        result = extractor.extract_text(f)
        assert isinstance(result, str)
        assert len(result) >= 1

    def test_extract_text_catches_os_error_in_batch(self, tmp_path: Path) -> None:
        extractor = self._make_extractor()
        f = tmp_path / "file.txt"
        f.write_text("data")
        with patch.object(extractor, "extract_text", side_effect=OSError("disk error")):
            results = extractor.extract_batch([f])
        assert results[f] == ""

    def test_extract_rtf_with_striprtf(self, tmp_path: Path) -> None:
        extractor = self._make_extractor()
        f = tmp_path / "doc.rtf"
        f.write_text(r"{\rtf1 Hello World}", encoding="utf-8")
        mock_striprtf = MagicMock()
        mock_striprtf.striprtf.rtf_to_text.return_value = "Hello World"
        with patch.dict(
            "sys.modules", {"striprtf": mock_striprtf, "striprtf.striprtf": mock_striprtf.striprtf}
        ):
            result = extractor._extract_rtf(f)

        assert result == "Hello World"

    def test_supports_format_case_insensitive(self, tmp_path: Path) -> None:
        extractor = self._make_extractor()
        f = tmp_path / "DOC.TXT"
        f.touch()
        assert extractor.supports_format(f) is True


# ---------------------------------------------------------------------------
# TestImageDeduplicator
# ---------------------------------------------------------------------------


class TestImageDeduplicator:
    """Tests for ImageDeduplicator (image_dedup.py)."""

    @pytest.fixture(autouse=True)
    def _require_imagededup(self) -> None:
        pytest.importorskip("imagededup")

    @pytest.fixture(autouse=True)
    def _require_pil(self) -> None:
        pytest.importorskip("PIL")

    def _make_deduplicator(self, method: str = "phash", threshold: int = 10) -> Any:
        from file_organizer.services.deduplication.image_dedup import ImageDeduplicator

        mock_hasher = MagicMock()
        with (
            patch(
                "file_organizer.services.deduplication.image_dedup.PHash", return_value=mock_hasher
            ),
            patch(
                "file_organizer.services.deduplication.image_dedup.DHash", return_value=mock_hasher
            ),
            patch(
                "file_organizer.services.deduplication.image_dedup.AHash", return_value=mock_hasher
            ),
            patch("file_organizer.services.deduplication.image_dedup._IMAGEDEDUP_AVAILABLE", True),
        ):
            dedup = ImageDeduplicator(hash_method=method, threshold=threshold)
            dedup.hasher = mock_hasher
        return dedup

    def test_init_phash(self) -> None:
        dedup = self._make_deduplicator("phash")
        assert dedup.hash_method == "phash"
        assert dedup.threshold == 10

    def test_init_dhash(self) -> None:
        dedup = self._make_deduplicator("dhash")
        assert dedup.hash_method == "dhash"

    def test_init_ahash(self) -> None:
        dedup = self._make_deduplicator("ahash")
        assert dedup.hash_method == "ahash"

    def test_init_invalid_method_raises(self) -> None:
        from file_organizer.services.deduplication.image_dedup import ImageDeduplicator

        with (
            patch("file_organizer.services.deduplication.image_dedup._IMAGEDEDUP_AVAILABLE", True),
            patch("file_organizer.services.deduplication.image_dedup.PHash"),
        ):
            with pytest.raises(ValueError, match="Unsupported hash method"):
                ImageDeduplicator(hash_method="whash")

    def test_init_invalid_threshold_raises(self) -> None:
        from file_organizer.services.deduplication.image_dedup import ImageDeduplicator

        with (
            patch("file_organizer.services.deduplication.image_dedup._IMAGEDEDUP_AVAILABLE", True),
            patch("file_organizer.services.deduplication.image_dedup.PHash"),
        ):
            with pytest.raises(ValueError, match="Threshold must be between"):
                ImageDeduplicator(hash_method="phash", threshold=100)

    def test_init_imagededup_not_available_raises(self) -> None:
        from file_organizer.services.deduplication.image_dedup import ImageDeduplicator

        with patch(
            "file_organizer.services.deduplication.image_dedup._IMAGEDEDUP_AVAILABLE", False
        ):
            with pytest.raises(ImportError, match="imagededup is required"):
                ImageDeduplicator()

    def test_compute_hamming_distance_same_hashes(self) -> None:
        dedup = self._make_deduplicator()
        dist = dedup.compute_hamming_distance("ff00ff00", "ff00ff00")
        assert dist == 0

    def test_compute_hamming_distance_different_hashes(self) -> None:
        dedup = self._make_deduplicator()
        dist = dedup.compute_hamming_distance("ff00", "00ff")
        assert dist >= 1

    def test_compute_hamming_distance_invalid_raises(self) -> None:
        dedup = self._make_deduplicator()
        with pytest.raises(ValueError):
            dedup.compute_hamming_distance("zzzz", "1234")

    def test_get_image_hash_missing_file(self, tmp_path: Path) -> None:
        dedup = self._make_deduplicator()
        result = dedup.get_image_hash(tmp_path / "missing.jpg")
        assert result is None

    def test_get_image_hash_unsupported_format(self, tmp_path: Path) -> None:
        dedup = self._make_deduplicator()
        f = tmp_path / "file.txt"
        f.write_text("text")
        result = dedup.get_image_hash(f)
        assert result is None

    def test_get_image_hash_supported_format_calls_hasher(self, tmp_path: Path) -> None:
        dedup = self._make_deduplicator()
        f = tmp_path / "img.jpg"
        f.write_bytes(b"\xff\xd8\xff")
        dedup.hasher.encode_image.return_value = "abcd1234"
        result = dedup.get_image_hash(f)
        assert result == "abcd1234"
        dedup.hasher.encode_image.assert_called_once_with(str(f))

    def test_get_image_hash_hasher_returns_none(self, tmp_path: Path) -> None:
        dedup = self._make_deduplicator()
        f = tmp_path / "img.jpg"
        f.write_bytes(b"\xff\xd8\xff")
        dedup.hasher.encode_image.return_value = None
        result = dedup.get_image_hash(f)
        assert result is None

    def test_get_image_hash_oserror(self, tmp_path: Path) -> None:
        dedup = self._make_deduplicator()
        f = tmp_path / "bad.jpg"
        f.write_bytes(b"corrupt")
        dedup.hasher.encode_image.side_effect = OSError("cannot read")
        result = dedup.get_image_hash(f)
        assert result is None

    def test_compute_similarity_both_hashed(self, tmp_path: Path) -> None:
        dedup = self._make_deduplicator()
        img1 = tmp_path / "a.jpg"
        img2 = tmp_path / "b.jpg"
        img1.write_bytes(b"\xff\xd8\xff")
        img2.write_bytes(b"\xff\xd8\xff")
        dedup.hasher.encode_image.return_value = "ff00ff00ff00ff00"
        result = dedup.compute_similarity(img1, img2)
        assert result == pytest.approx(1.0)

    def test_compute_similarity_returns_none_when_hash_fails(self, tmp_path: Path) -> None:
        dedup = self._make_deduplicator()
        img1 = tmp_path / "a.jpg"
        img2 = tmp_path / "b.jpg"
        # only img1 exists
        img1.write_bytes(b"\xff\xd8\xff")
        dedup.hasher.encode_image.side_effect = [OSError(), OSError()]
        result = dedup.compute_similarity(img1, img2)
        assert result is None

    def test_find_duplicates_directory_not_found(self, tmp_path: Path) -> None:
        dedup = self._make_deduplicator()
        with pytest.raises(FileNotFoundError):
            dedup.find_duplicates(tmp_path / "nonexistent")

    def test_find_duplicates_not_a_directory(self, tmp_path: Path) -> None:
        dedup = self._make_deduplicator()
        f = tmp_path / "file.txt"
        f.write_text("x")
        with pytest.raises(ValueError, match="not a directory"):
            dedup.find_duplicates(f)

    def test_find_duplicates_empty_directory(self, tmp_path: Path) -> None:
        dedup = self._make_deduplicator()
        result = dedup.find_duplicates(tmp_path)
        assert isinstance(result, dict)
        assert len(result) == 0

    def test_find_duplicates_with_images(self, tmp_path: Path) -> None:
        dedup = self._make_deduplicator()
        img1 = tmp_path / "a.jpg"
        img2 = tmp_path / "b.jpg"
        img1.write_bytes(b"\xff\xd8\xff")
        img2.write_bytes(b"\xff\xd8\xff")
        hash_val = "ff00ff00ff00ff00"
        dedup.hasher.encode_image.return_value = hash_val
        dedup.hasher.find_duplicates.return_value = {
            str(img1): [str(img2)],
            str(img2): [],
        }
        result = dedup.find_duplicates(tmp_path)
        assert result == {hash_val: [img1, img2]}

    def test_batch_compute_hashes_empty_list(self) -> None:
        dedup = self._make_deduplicator()
        result = dedup.batch_compute_hashes([])
        assert isinstance(result, dict)
        assert len(result) == 0

    def test_batch_compute_hashes_with_images(self, tmp_path: Path) -> None:
        dedup = self._make_deduplicator()
        img = tmp_path / "img.jpg"
        img.write_bytes(b"\xff\xd8\xff")
        dedup.hasher.encode_image.return_value = "aabbccdd"
        result = dedup.batch_compute_hashes([img])
        assert img in result
        assert result[img] == "aabbccdd"

    def test_cluster_by_similarity_empty_list(self) -> None:
        dedup = self._make_deduplicator()
        result = dedup.cluster_by_similarity([])
        assert result == []

    def test_cluster_by_similarity_no_similar_images(self, tmp_path: Path) -> None:
        dedup = self._make_deduplicator(threshold=0)
        img1 = tmp_path / "a.jpg"
        img2 = tmp_path / "b.jpg"
        img1.write_bytes(b"\xff\xd8\xff")
        img2.write_bytes(b"\xff\xd8\xff")
        # Return very different hashes
        dedup.hasher.encode_image.side_effect = ["ff00000000000000", "00ff000000000000"]
        result = dedup.cluster_by_similarity([img1, img2])
        # With threshold=0, only identical hashes cluster; different hashes → no clusters
        assert result == []

    def test_validate_image_missing_file(self, tmp_path: Path) -> None:
        dedup = self._make_deduplicator()
        valid, err = dedup.validate_image(tmp_path / "missing.jpg")
        assert valid is False
        assert err is not None
        assert "not found" in err.lower()

    def test_validate_image_unsupported_format(self, tmp_path: Path) -> None:
        dedup = self._make_deduplicator()
        f = tmp_path / "doc.txt"
        f.write_text("not an image")
        valid, err = dedup.validate_image(f)
        assert valid is False
        assert err is not None

    def test_validate_image_valid(self, tmp_path: Path) -> None:
        from PIL import Image as PILImage

        dedup = self._make_deduplicator()
        f = tmp_path / "real.png"
        img = PILImage.new("RGB", (10, 10), color=(128, 0, 0))
        img.save(str(f))
        valid, err = dedup.validate_image(f)
        assert valid is True
        assert err is None

    def test_progress_callback_called(self, tmp_path: Path) -> None:
        dedup = self._make_deduplicator()
        img = tmp_path / "img.jpg"
        img.write_bytes(b"\xff\xd8\xff")
        dedup.hasher.encode_image.return_value = "aabb"
        calls: list[tuple[int, int]] = []
        dedup.batch_compute_hashes([img], progress_callback=lambda c, t: calls.append((c, t)))
        assert len(calls) == 1
        assert calls[0] == (1, 1)

    def test_find_image_files_non_recursive(self, tmp_path: Path) -> None:
        dedup = self._make_deduplicator()
        sub = tmp_path / "sub"
        sub.mkdir()
        top_img = tmp_path / "top.jpg"
        sub_img = sub / "nested.jpg"
        top_img.write_bytes(b"\xff\xd8\xff")
        sub_img.write_bytes(b"\xff\xd8\xff")
        files = dedup._find_image_files(tmp_path, recursive=False)
        paths = [str(f) for f in files]
        assert str(top_img) in paths
        assert str(sub_img) not in paths


# ---------------------------------------------------------------------------
# TestSemanticAnalyzer
# ---------------------------------------------------------------------------


class TestSemanticAnalyzer:
    """Tests for SemanticAnalyzer (semantic.py)."""

    def _make_analyzer(self, threshold: float = 0.85) -> Any:
        from file_organizer.services.deduplication.semantic import SemanticAnalyzer

        return SemanticAnalyzer(threshold=threshold)

    def test_init_valid_threshold(self) -> None:
        analyzer = self._make_analyzer(0.7)
        assert analyzer.threshold == 0.7

    def test_init_invalid_threshold_low(self) -> None:
        from file_organizer.services.deduplication.semantic import SemanticAnalyzer

        with pytest.raises(ValueError, match="Threshold must be between 0 and 1"):
            SemanticAnalyzer(threshold=-0.1)

    def test_init_invalid_threshold_high(self) -> None:
        from file_organizer.services.deduplication.semantic import SemanticAnalyzer

        with pytest.raises(ValueError, match="Threshold must be between 0 and 1"):
            SemanticAnalyzer(threshold=1.5)

    def test_compute_similarity_identical_vectors(self) -> None:
        analyzer = self._make_analyzer()
        v = np.array([1.0, 0.0, 0.0])
        result = analyzer.compute_similarity(v, v)
        assert abs(result - 1.0) < 1e-6

    def test_compute_similarity_orthogonal_vectors(self) -> None:
        analyzer = self._make_analyzer()
        v1 = np.array([1.0, 0.0])
        v2 = np.array([0.0, 1.0])
        result = analyzer.compute_similarity(v1, v2)
        assert abs(result - 0.0) < 1e-6

    def test_compute_similarity_zero_vector(self) -> None:
        analyzer = self._make_analyzer()
        v1 = np.array([0.0, 0.0])
        v2 = np.array([1.0, 0.0])
        result = analyzer.compute_similarity(v1, v2)
        assert result == 0.0

    def test_compute_similarity_matrix_shape(self) -> None:
        analyzer = self._make_analyzer()
        emb = np.random.rand(4, 10)
        matrix = analyzer.compute_similarity_matrix(emb)
        assert matrix.shape == (4, 4)

    def test_compute_similarity_matrix_diagonal_ones(self) -> None:
        analyzer = self._make_analyzer()
        emb = np.random.rand(3, 5)
        matrix = analyzer.compute_similarity_matrix(emb)
        for i in range(3):
            assert abs(matrix[i, i] - 1.0) < 1e-5

    def test_compute_similarity_matrix_symmetric(self) -> None:
        analyzer = self._make_analyzer()
        emb = np.random.rand(3, 5)
        matrix = analyzer.compute_similarity_matrix(emb)
        np.testing.assert_allclose(matrix, matrix.T, atol=1e-6)

    def test_find_similar_documents_mismatched_raises(self, tmp_path: Path) -> None:
        analyzer = self._make_analyzer()
        emb = np.random.rand(3, 5)
        paths = [tmp_path / "a.txt", tmp_path / "b.txt"]
        with pytest.raises(ValueError, match="must match paths count"):
            analyzer.find_similar_documents(emb, paths)

    def test_find_similar_documents_identical_docs_found(self, tmp_path: Path) -> None:
        analyzer = self._make_analyzer(threshold=0.9)
        # Two identical vectors → similarity=1.0
        v = np.array([1.0, 0.0, 0.0])
        emb = np.stack([v, v])
        p1 = tmp_path / "a.txt"
        p2 = tmp_path / "b.txt"
        p1.write_text("a")
        p2.write_text("b")
        result = analyzer.find_similar_documents(emb, [p1, p2])
        assert p1 in result
        assert len(result[p1]) == 1
        assert result[p1][0][0] == p2

    def test_find_similar_documents_no_similar(self, tmp_path: Path) -> None:
        analyzer = self._make_analyzer(threshold=0.99)
        v1 = np.array([1.0, 0.0])
        v2 = np.array([0.0, 1.0])
        emb = np.stack([v1, v2])
        p1 = tmp_path / "a.txt"
        p2 = tmp_path / "b.txt"
        p1.write_text("a")
        p2.write_text("b")
        result = analyzer.find_similar_documents(emb, [p1, p2])
        assert result[p1] == []
        assert result[p2] == []

    def test_find_similar_to_query_returns_sorted(self, tmp_path: Path) -> None:
        analyzer = self._make_analyzer(threshold=0.0)
        query = np.array([1.0, 0.0])
        doc1 = np.array([0.9, 0.1])
        doc2 = np.array([0.5, 0.5])
        doc_emb = np.stack([doc1, doc2])
        p1 = tmp_path / "a.txt"
        p2 = tmp_path / "b.txt"
        p1.write_text("a")
        p2.write_text("b")
        result = analyzer.find_similar_to_query(query, doc_emb, [p1, p2])
        assert len(result) >= 1
        if len(result) >= 2:
            assert result[0][1] >= result[1][1]

    def test_find_similar_to_query_top_k(self, tmp_path: Path) -> None:
        analyzer = self._make_analyzer(threshold=0.0)
        query = np.array([1.0, 0.0])
        # Use deterministic embeddings that guarantee non-zero similarity with query
        doc_emb = np.array([[0.9, 0.1], [0.8, 0.2], [0.7, 0.3], [0.6, 0.4], [0.5, 0.5]])
        paths = [tmp_path / f"{i}.txt" for i in range(5)]
        result = analyzer.find_similar_to_query(query, doc_emb, paths, top_k=2)
        # top_k=2 must limit result to exactly 2 items (all 5 have positive similarity)
        assert len(result) == 2

    def test_cluster_by_similarity_empty_input(self) -> None:
        analyzer = self._make_analyzer()
        result = analyzer.cluster_by_similarity({})
        assert result == []

    def test_cluster_by_similarity_two_similar_docs(self, tmp_path: Path) -> None:
        p1 = tmp_path / "a.txt"
        p2 = tmp_path / "b.txt"
        p1.write_text("a")
        p2.write_text("b")
        analyzer = self._make_analyzer()
        similar_docs = {p1: [(p2, 0.95)], p2: [(p1, 0.95)]}
        clusters = analyzer.cluster_by_similarity(similar_docs)
        assert len(clusters) == 1
        assert len(clusters[0]) == 2

    def test_set_threshold_updates_value(self) -> None:
        analyzer = self._make_analyzer(0.7)
        analyzer.set_threshold(0.5)
        assert analyzer.threshold == 0.5

    def test_set_threshold_invalid_raises(self) -> None:
        analyzer = self._make_analyzer()
        with pytest.raises(ValueError, match="Threshold must be between 0 and 1"):
            analyzer.set_threshold(2.0)

    def test_get_statistics_returns_dict_with_keys(self) -> None:
        analyzer = self._make_analyzer()
        emb = np.random.rand(4, 5)
        matrix = analyzer.compute_similarity_matrix(emb)
        stats = analyzer.get_statistics(matrix)
        assert "mean_similarity" in stats
        assert "max_similarity" in stats
        assert "min_similarity" in stats
        assert "above_threshold_count" in stats
        assert 0.0 <= stats["mean_similarity"] <= 1.0

    def test_get_duplicate_groups_returns_list(self, tmp_path: Path) -> None:
        analyzer = self._make_analyzer(threshold=0.9)
        v = np.array([1.0, 0.0])
        emb = np.stack([v, v])
        p1 = tmp_path / "a.txt"
        p2 = tmp_path / "b.txt"
        p1.write_text("a")
        p2.write_text("b")
        groups = analyzer.get_duplicate_groups(emb, [p1, p2])
        assert isinstance(groups, list)
        assert groups
        assert "files" in groups[0]
        assert "count" in groups[0]
        assert len(groups[0]["files"]) == 2
        assert groups[0]["count"] == 2

    def test_get_statistics_above_threshold_count_is_int(self) -> None:
        analyzer = self._make_analyzer(threshold=0.5)
        emb = np.eye(3)
        matrix = analyzer.compute_similarity_matrix(emb)
        stats = analyzer.get_statistics(matrix)
        # With identity matrix (3x3) and threshold=0.5, off-diagonal elements are 0.0
        # so above_threshold_count should be 0
        assert stats["above_threshold_count"] == 0


# ---------------------------------------------------------------------------
# TestBackupManager
# ---------------------------------------------------------------------------


class TestBackupManager:
    """Tests for BackupManager (backup.py)."""

    def _make_manager(self, tmp_path: Path) -> Any:
        from file_organizer.services.deduplication.backup import BackupManager

        return BackupManager(base_dir=tmp_path)

    def test_init_creates_backup_dir(self, tmp_path: Path) -> None:
        mgr = self._make_manager(tmp_path)
        assert mgr.backup_dir.exists()
        assert mgr.backup_dir.is_dir()

    def test_init_creates_manifest(self, tmp_path: Path) -> None:
        mgr = self._make_manager(tmp_path)
        assert mgr.manifest_path.exists()

    def test_create_backup_returns_path(self, tmp_path: Path) -> None:
        mgr = self._make_manager(tmp_path)
        src = tmp_path / "source.txt"
        src.write_text("hello")
        backup = mgr.create_backup(src)
        assert backup.exists()
        assert backup.read_text() == "hello"

    def test_create_backup_records_in_manifest(self, tmp_path: Path) -> None:
        mgr = self._make_manager(tmp_path)
        src = tmp_path / "data.txt"
        src.write_text("data")
        backup = mgr.create_backup(src)
        manifest = mgr._load_manifest()
        assert str(backup) in manifest
        assert manifest[str(backup)]["original_path"] == str(src.resolve())

    def test_create_backup_file_not_found_raises(self, tmp_path: Path) -> None:
        mgr = self._make_manager(tmp_path)
        with pytest.raises(FileNotFoundError, match="Source file not found"):
            mgr.create_backup(tmp_path / "ghost.txt")

    def test_create_backup_not_a_file_raises(self, tmp_path: Path) -> None:
        mgr = self._make_manager(tmp_path)
        with pytest.raises(ValueError, match="not a file"):
            mgr.create_backup(tmp_path)

    def test_restore_backup_to_original_location(self, tmp_path: Path) -> None:
        mgr = self._make_manager(tmp_path)
        src = tmp_path / "original.txt"
        src.write_text("content")
        backup = mgr.create_backup(src)
        src.unlink()
        restored = mgr.restore_backup(backup)
        assert restored.exists()
        assert restored.read_text() == "content"

    def test_restore_backup_to_custom_location(self, tmp_path: Path) -> None:
        mgr = self._make_manager(tmp_path)
        src = tmp_path / "file.txt"
        src.write_text("stuff")
        backup = mgr.create_backup(src)
        target = tmp_path / "restored_file.txt"
        restored = mgr.restore_backup(backup, target_path=target)
        assert restored == target
        assert target.read_text() == "stuff"

    def test_restore_backup_not_in_manifest_raises(self, tmp_path: Path) -> None:
        mgr = self._make_manager(tmp_path)
        fake_backup = tmp_path / "fake_backup.txt"
        fake_backup.write_text("ghost")
        with pytest.raises(ValueError, match="not found in manifest"):
            mgr.restore_backup(fake_backup)

    def test_restore_backup_file_not_found_raises(self, tmp_path: Path) -> None:
        mgr = self._make_manager(tmp_path)
        with pytest.raises(FileNotFoundError, match="Backup file not found"):
            mgr.restore_backup(tmp_path / "nonexistent_backup.txt")

    def test_list_backups_returns_list(self, tmp_path: Path) -> None:
        mgr = self._make_manager(tmp_path)
        backups = mgr.list_backups()
        assert isinstance(backups, list)
        assert len(backups) == 0  # Fresh manager has no backups

    def test_list_backups_after_create(self, tmp_path: Path) -> None:
        mgr = self._make_manager(tmp_path)
        src = tmp_path / "listed.txt"
        src.write_text("listed")
        mgr.create_backup(src)
        backups = mgr.list_backups()
        assert len(backups) == 1
        assert "original_path" in backups[0]

    def test_get_backup_info_returns_dict(self, tmp_path: Path) -> None:
        mgr = self._make_manager(tmp_path)
        src = tmp_path / "info.txt"
        src.write_text("info")
        backup = mgr.create_backup(src)
        info = mgr.get_backup_info(backup)
        assert info is not None
        assert info["file_size"] == src.stat().st_size

    def test_get_backup_info_missing_returns_none(self, tmp_path: Path) -> None:
        mgr = self._make_manager(tmp_path)
        result = mgr.get_backup_info(tmp_path / "no_such_backup.txt")
        assert result is None

    def test_get_statistics_returns_dict_with_keys(self, tmp_path: Path) -> None:
        mgr = self._make_manager(tmp_path)
        stats = mgr.get_statistics()
        assert "total_backups" in stats
        assert "existing_backups" in stats
        assert "total_size_bytes" in stats
        assert "backup_directory" in stats

    def test_verify_backups_empty_is_clean(self, tmp_path: Path) -> None:
        mgr = self._make_manager(tmp_path)
        issues = mgr.verify_backups()
        assert isinstance(issues, list)
        assert len(issues) == 0

    def test_verify_backups_missing_file_detected(self, tmp_path: Path) -> None:
        mgr = self._make_manager(tmp_path)
        src = tmp_path / "verif.txt"
        src.write_text("verify")
        backup = mgr.create_backup(src)
        backup.unlink()  # Delete the backup file
        issues = mgr.verify_backups()
        assert len(issues) >= 1
        assert any("Missing" in issue for issue in issues)

    def test_cleanup_old_backups_removes_old_entries(self, tmp_path: Path) -> None:
        mgr = self._make_manager(tmp_path)
        src = tmp_path / "old.txt"
        src.write_text("old content")
        mgr.create_backup(src)
        # Cleanup with max_age_days=0 removes everything
        removed = mgr.cleanup_old_backups(max_age_days=0)
        assert isinstance(removed, list)
        backups = mgr.list_backups()
        assert len(backups) == 0

    def test_cleanup_negative_age_raises(self, tmp_path: Path) -> None:
        mgr = self._make_manager(tmp_path)
        with pytest.raises(ValueError, match="non-negative"):
            mgr.cleanup_old_backups(max_age_days=-1)

    def test_cleanup_keeps_recent_backups(self, tmp_path: Path) -> None:
        mgr = self._make_manager(tmp_path)
        src = tmp_path / "recent.txt"
        src.write_text("recent")
        mgr.create_backup(src)
        removed = mgr.cleanup_old_backups(max_age_days=30)
        # Backup just created should not be removed
        assert len(removed) == 0
        backups = mgr.list_backups()
        assert len(backups) == 1

    def test_manifest_is_valid_json(self, tmp_path: Path) -> None:
        mgr = self._make_manager(tmp_path)
        src = tmp_path / "check.txt"
        src.write_text("check")
        mgr.create_backup(src)
        with open(mgr.manifest_path, encoding="utf-8") as f:
            data = json.load(f)
        assert isinstance(data, dict)
        assert len(data) == 1

    def test_multiple_backups_accumulate(self, tmp_path: Path) -> None:
        mgr = self._make_manager(tmp_path)
        for i in range(3):
            f = tmp_path / f"file_{i}.txt"
            f.write_text(f"content {i}")
            mgr.create_backup(f)
        backups = mgr.list_backups()
        assert len(backups) == 3


# ---------------------------------------------------------------------------
# TestImageUtils
# ---------------------------------------------------------------------------


class TestImageUtils:
    """Tests for image_utils.py (module-level functions + ImageMetadata)."""

    @pytest.fixture(autouse=True)
    def _require_pil(self) -> None:
        pytest.importorskip("PIL")

    def _make_real_png(self, path: Path) -> Path:
        from PIL import Image as PILImage

        img = PILImage.new("RGB", (20, 30), color=(10, 20, 30))
        img.save(str(path), format="PNG")
        return path

    def test_supported_formats_constant(self) -> None:
        from file_organizer.services.deduplication.image_utils import SUPPORTED_FORMATS

        assert ".jpg" in SUPPORTED_FORMATS
        assert ".png" in SUPPORTED_FORMATS
        assert len(SUPPORTED_FORMATS) >= 5

    def test_is_supported_format_jpg(self, tmp_path: Path) -> None:
        from file_organizer.services.deduplication.image_utils import is_supported_format

        assert is_supported_format(tmp_path / "img.jpg") is True

    def test_is_supported_format_txt_false(self, tmp_path: Path) -> None:
        from file_organizer.services.deduplication.image_utils import is_supported_format

        assert is_supported_format(tmp_path / "doc.txt") is False

    def test_get_image_metadata_valid_png(self, tmp_path: Path) -> None:
        from file_organizer.services.deduplication.image_utils import get_image_metadata

        f = self._make_real_png(tmp_path / "img.png")
        meta = get_image_metadata(f)
        assert meta is not None
        assert meta.width == 20
        assert meta.height == 30
        assert meta.resolution == 600

    def test_get_image_metadata_missing_file(self, tmp_path: Path) -> None:
        from file_organizer.services.deduplication.image_utils import get_image_metadata

        result = get_image_metadata(tmp_path / "ghost.png")
        assert result is None

    def test_get_image_metadata_to_dict(self, tmp_path: Path) -> None:
        from file_organizer.services.deduplication.image_utils import get_image_metadata

        f = self._make_real_png(tmp_path / "img.png")
        meta = get_image_metadata(f)
        assert meta is not None
        d = meta.to_dict()
        assert "width" in d
        assert "height" in d
        assert "format" in d
        assert d["width"] == 20

    def test_image_metadata_repr(self, tmp_path: Path) -> None:
        from file_organizer.services.deduplication.image_utils import get_image_metadata

        f = self._make_real_png(tmp_path / "img.png")
        meta = get_image_metadata(f)
        assert meta is not None
        r = repr(meta)
        assert "ImageMetadata" in r
        assert "img.png" in r

    def test_get_image_dimensions_valid(self, tmp_path: Path) -> None:
        from file_organizer.services.deduplication.image_utils import get_image_dimensions

        f = self._make_real_png(tmp_path / "dim.png")
        dims = get_image_dimensions(f)
        assert dims is not None
        assert dims == (20, 30)

    def test_get_image_dimensions_invalid(self, tmp_path: Path) -> None:
        from file_organizer.services.deduplication.image_utils import get_image_dimensions

        f = tmp_path / "bad.jpg"
        f.write_bytes(b"not an image")
        result = get_image_dimensions(f)
        assert result is None

    def test_get_image_format_valid(self, tmp_path: Path) -> None:
        from file_organizer.services.deduplication.image_utils import get_image_format

        f = self._make_real_png(tmp_path / "fmt.png")
        fmt = get_image_format(f)
        assert fmt == "PNG"

    def test_get_image_format_invalid(self, tmp_path: Path) -> None:
        from file_organizer.services.deduplication.image_utils import get_image_format

        f = tmp_path / "bad.jpg"
        f.write_bytes(b"corrupt")
        result = get_image_format(f)
        assert result is None

    def test_validate_image_file_valid(self, tmp_path: Path) -> None:
        from file_organizer.services.deduplication.image_utils import validate_image_file

        f = self._make_real_png(tmp_path / "valid.png")
        valid, err = validate_image_file(f)
        assert valid is True
        assert err is None

    def test_validate_image_file_missing(self, tmp_path: Path) -> None:
        from file_organizer.services.deduplication.image_utils import validate_image_file

        valid, err = validate_image_file(tmp_path / "missing.png")
        assert valid is False
        assert err is not None

    def test_validate_image_file_corrupt(self, tmp_path: Path) -> None:
        from file_organizer.services.deduplication.image_utils import validate_image_file

        f = tmp_path / "corrupt.jpg"
        f.write_bytes(b"\xff\xd8\xff garbage")
        valid, err = validate_image_file(f)
        assert valid is False
        assert err is not None

    def test_validate_image_file_unsupported_ext(self, tmp_path: Path) -> None:
        from file_organizer.services.deduplication.image_utils import validate_image_file

        f = tmp_path / "doc.xyz"
        f.write_text("not image")
        valid, err = validate_image_file(f)
        assert valid is False
        assert "Unsupported" in (err or "")

    def test_filter_valid_images_empty_list(self) -> None:
        from file_organizer.services.deduplication.image_utils import filter_valid_images

        result = filter_valid_images([])
        assert isinstance(result, list)
        assert len(result) == 0

    def test_filter_valid_images_mixed(self, tmp_path: Path) -> None:
        from file_organizer.services.deduplication.image_utils import filter_valid_images

        valid_f = self._make_real_png(tmp_path / "good.png")
        bad_f = tmp_path / "bad.png"
        bad_f.write_bytes(b"garbage")
        result = filter_valid_images([valid_f, bad_f])
        assert valid_f in result
        assert bad_f not in result

    def test_find_images_in_directory_not_found(self, tmp_path: Path) -> None:
        from file_organizer.services.deduplication.image_utils import find_images_in_directory

        with pytest.raises(FileNotFoundError):
            find_images_in_directory(tmp_path / "nonexistent")

    def test_find_images_in_directory_not_a_dir(self, tmp_path: Path) -> None:
        from file_organizer.services.deduplication.image_utils import find_images_in_directory

        f = tmp_path / "file.txt"
        f.write_text("x")
        with pytest.raises(ValueError, match="not a directory"):
            find_images_in_directory(f)

    def test_find_images_in_directory_finds_pngs(self, tmp_path: Path) -> None:
        from file_organizer.services.deduplication.image_utils import find_images_in_directory

        self._make_real_png(tmp_path / "img1.png")
        self._make_real_png(tmp_path / "img2.png")
        result = find_images_in_directory(tmp_path)
        assert len(result) == 2

    def test_find_images_non_recursive_excludes_subdirs(self, tmp_path: Path) -> None:
        from file_organizer.services.deduplication.image_utils import find_images_in_directory

        sub = tmp_path / "sub"
        sub.mkdir()
        self._make_real_png(tmp_path / "top.png")
        self._make_real_png(sub / "nested.png")
        result = find_images_in_directory(tmp_path, recursive=False)
        names = [f.name for f in result]
        assert "top.png" in names
        assert "nested.png" not in names

    def test_group_images_by_format(self, tmp_path: Path) -> None:
        from file_organizer.services.deduplication.image_utils import group_images_by_format

        imgs = [tmp_path / "a.jpg", tmp_path / "b.png", tmp_path / "c.jpg"]
        groups = group_images_by_format(imgs)
        assert ".jpg" in groups
        assert ".png" in groups
        assert len(groups[".jpg"]) == 2

    def test_get_format_quality_score_png(self, tmp_path: Path) -> None:
        from file_organizer.services.deduplication.image_utils import get_format_quality_score

        score = get_format_quality_score(tmp_path / "img.png")
        assert score == 5

    def test_get_format_quality_score_jpg(self, tmp_path: Path) -> None:
        from file_organizer.services.deduplication.image_utils import get_format_quality_score

        score = get_format_quality_score(tmp_path / "img.jpg")
        assert score == 2

    def test_get_format_quality_score_unknown(self, tmp_path: Path) -> None:
        from file_organizer.services.deduplication.image_utils import get_format_quality_score

        score = get_format_quality_score(tmp_path / "img.xyz")
        assert score == 0

    def test_compare_image_quality_higher_resolution_wins(self, tmp_path: Path) -> None:
        from PIL import Image as PILImage

        from file_organizer.services.deduplication.image_utils import compare_image_quality

        big = tmp_path / "big.png"
        small = tmp_path / "small.png"
        PILImage.new("RGB", (100, 100)).save(str(big))
        PILImage.new("RGB", (10, 10)).save(str(small))
        result = compare_image_quality(big, small)
        assert result == -1  # big is better

    def test_compare_image_quality_equal(self, tmp_path: Path) -> None:
        from PIL import Image as PILImage

        from file_organizer.services.deduplication.image_utils import compare_image_quality

        img1 = tmp_path / "img1.png"
        img2 = tmp_path / "img2.png"
        PILImage.new("RGB", (10, 10), color=(0, 0, 0)).save(str(img1))
        PILImage.new("RGB", (10, 10), color=(0, 0, 0)).save(str(img2))
        result = compare_image_quality(img1, img2)
        assert result in (-1, 0, 1)

    def test_get_best_quality_image_from_list(self, tmp_path: Path) -> None:
        from PIL import Image as PILImage

        from file_organizer.services.deduplication.image_utils import get_best_quality_image

        big = tmp_path / "big.png"
        small = tmp_path / "small.png"
        PILImage.new("RGB", (100, 100)).save(str(big))
        PILImage.new("RGB", (10, 10)).save(str(small))
        best = get_best_quality_image([big, small])
        assert best == big

    def test_get_best_quality_image_empty_list(self) -> None:
        from file_organizer.services.deduplication.image_utils import get_best_quality_image

        result = get_best_quality_image([])
        assert result is None

    def test_format_file_size_bytes(self) -> None:
        from file_organizer.services.deduplication.image_utils import format_file_size

        result = format_file_size(512)
        assert "512" in result
        assert "B" in result

    def test_format_file_size_kilobytes(self) -> None:
        from file_organizer.services.deduplication.image_utils import format_file_size

        result = format_file_size(2048)
        assert "KB" in result

    def test_format_file_size_megabytes(self) -> None:
        from file_organizer.services.deduplication.image_utils import format_file_size

        result = format_file_size(2 * 1024 * 1024)
        assert "MB" in result

    def test_get_image_info_string_valid(self, tmp_path: Path) -> None:
        from file_organizer.services.deduplication.image_utils import get_image_info_string

        f = self._make_real_png(tmp_path / "info.png")
        result = get_image_info_string(f)
        assert "info.png" in result
        assert "20x30" in result

    def test_get_image_info_string_invalid(self, tmp_path: Path) -> None:
        from file_organizer.services.deduplication.image_utils import get_image_info_string

        f = tmp_path / "bad.png"
        f.write_bytes(b"garbage")
        result = get_image_info_string(f)
        assert "bad.png" in result
        assert "Cannot read" in result


# ---------------------------------------------------------------------------
# TestConfidenceScorer
# ---------------------------------------------------------------------------


class TestConfidenceScorer:
    """Tests for ConfidenceScorer (smart_suggestions.py)."""

    def _make_scorer(self) -> Any:
        from file_organizer.services.smart_suggestions import ConfidenceScorer

        return ConfidenceScorer()

    def _make_mock_pattern_analysis(self) -> Any:
        pa = MagicMock()
        pa.naming_patterns = []
        pa.location_patterns = []
        pa.content_clusters = []
        return pa

    def test_score_suggestion_returns_confidence_factors(self, tmp_path: Path) -> None:
        from file_organizer.models.suggestion_types import SuggestionType

        scorer = self._make_scorer()
        f = tmp_path / "file.txt"
        f.write_text("data")
        result = scorer.score_suggestion(f, None, SuggestionType.MOVE)
        assert result is not None
        assert hasattr(result, "pattern_strength")

    def test_score_suggestion_with_pattern_analysis(self, tmp_path: Path) -> None:
        from file_organizer.models.suggestion_types import SuggestionType

        scorer = self._make_scorer()
        f = tmp_path / "file.txt"
        f.write_text("data")
        pa = self._make_mock_pattern_analysis()
        pattern = MagicMock()
        pattern.example_files = ["file.txt"]
        pattern.confidence = 80.0
        pa.naming_patterns = [pattern]
        baseline = scorer.score_suggestion(f, None, SuggestionType.MOVE)
        result = scorer.score_suggestion(f, None, SuggestionType.MOVE, pattern_analysis=pa)
        assert result.pattern_strength != baseline.pattern_strength
        assert result.pattern_strength == 80.0

    def test_calculate_recency_score_recent_file(self, tmp_path: Path) -> None:
        scorer = self._make_scorer()
        f = tmp_path / "recent.txt"
        f.write_text("new")
        score = scorer._calculate_recency_score(f)
        assert score >= 55.0

    def test_calculate_recency_score_missing_file(self, tmp_path: Path) -> None:
        scorer = self._make_scorer()
        score = scorer._calculate_recency_score(tmp_path / "gone.txt")
        assert score == 50.0

    def test_calculate_content_similarity_no_suffix(self, tmp_path: Path) -> None:
        scorer = self._make_scorer()
        f = tmp_path / "file"
        f.write_text("content")
        score = scorer._calculate_content_similarity(f, tmp_path)
        assert score == 30.0

    def test_calculate_content_similarity_same_type_in_dir(self, tmp_path: Path) -> None:
        scorer = self._make_scorer()
        source = tmp_path / "source.txt"
        source.write_text("source")
        existing = tmp_path / "existing.txt"
        existing.write_text("other")
        score = scorer._calculate_content_similarity(source, tmp_path)
        assert score >= 10.0

    def test_calculate_user_history_score_no_target(self, tmp_path: Path) -> None:
        scorer = self._make_scorer()
        f = tmp_path / "f.txt"
        f.write_text("x")
        score = scorer._calculate_user_history_score(f, None, {})
        assert score == 50.0

    def test_calculate_user_history_score_with_history(self, tmp_path: Path) -> None:
        scorer = self._make_scorer()
        f = tmp_path / "f.txt"
        f.write_text("x")
        target = tmp_path / "subdir"
        target.mkdir()
        history = {"move_history": {".txt": {str(target): 3}}}
        score = scorer._calculate_user_history_score(f, target / "f.txt", history)
        assert score >= 50.0

    def test_calculate_size_score_empty_dir(self, tmp_path: Path) -> None:
        scorer = self._make_scorer()
        empty = tmp_path / "empty"
        empty.mkdir()
        f = tmp_path / "f.txt"
        f.write_text("data")
        score = scorer._calculate_size_score(f, empty)
        assert score == 50.0

    def test_calculate_size_score_similar_sized_files(self, tmp_path: Path) -> None:
        scorer = self._make_scorer()
        target_dir = tmp_path / "target"
        target_dir.mkdir()
        for i in range(3):
            (target_dir / f"existing_{i}.txt").write_text("a" * 100)
        source = tmp_path / "source.txt"
        source.write_text("b" * 90)
        score = scorer._calculate_size_score(source, target_dir)
        assert score >= 50.0

    def test_calculate_naming_match_no_analysis(self, tmp_path: Path) -> None:
        scorer = self._make_scorer()
        f = tmp_path / "f.txt"
        f.write_text("x")
        score = scorer._calculate_naming_match(f, tmp_path, None)
        assert score == 50.0

    def test_calculate_file_type_match_no_analysis(self, tmp_path: Path) -> None:
        scorer = self._make_scorer()
        f = tmp_path / "f.txt"
        f.write_text("x")
        score = scorer._calculate_file_type_match(f, tmp_path, None)
        assert score == 50.0

    def test_score_suggestion_with_user_history(self, tmp_path: Path) -> None:
        from file_organizer.models.suggestion_types import SuggestionType

        scorer = self._make_scorer()
        f = tmp_path / "file.txt"
        f.write_text("data")
        target = tmp_path / "archive" / "file.txt"
        target.parent.mkdir()
        history = {"move_history": {".txt": {str(target.parent): 2}}}
        baseline = scorer.score_suggestion(f, target, SuggestionType.MOVE)
        result = scorer.score_suggestion(f, target, SuggestionType.MOVE, user_history=history)
        assert result.user_history != baseline.user_history
        assert result.user_history == 70.0

    def test_calculate_pattern_strength_no_patterns(self, tmp_path: Path) -> None:
        scorer = self._make_scorer()
        f = tmp_path / "file.txt"
        f.write_text("x")
        pa = self._make_mock_pattern_analysis()
        pa.naming_patterns = []
        score = scorer._calculate_pattern_strength(f, pa)
        assert score == 50.0

    def test_calculate_file_type_match_type_in_target(self, tmp_path: Path) -> None:
        scorer = self._make_scorer()
        f = tmp_path / "f.txt"
        f.write_text("x")
        target_dir = tmp_path / "docs"
        target_dir.mkdir()

        pa = self._make_mock_pattern_analysis()
        mock_loc = MagicMock()
        mock_loc.directory = target_dir
        mock_loc.file_types = {".txt"}
        pa.location_patterns = [mock_loc]

        score = scorer._calculate_file_type_match(f, target_dir, pa)
        assert score == 85.0


# ---------------------------------------------------------------------------
# TestSuggestionEngine
# ---------------------------------------------------------------------------


class TestSuggestionEngine:
    """Tests for SuggestionEngine (smart_suggestions.py)."""

    def _make_engine(self, min_confidence: float = 0.0) -> Any:
        from file_organizer.services.smart_suggestions import SuggestionEngine

        return SuggestionEngine(text_model=None, min_confidence=min_confidence)

    def _make_mock_pattern_analysis(self, directory: Path) -> Any:
        pa = MagicMock()
        pa.directory = directory
        pa.naming_patterns = []
        pa.location_patterns = []
        pa.content_clusters = []
        return pa

    def test_init_default(self) -> None:
        engine = self._make_engine()
        assert engine.text_model is None
        assert engine.min_confidence == 0.0

    def test_generate_suggestions_empty_files(self) -> None:
        engine = self._make_engine()
        result = engine.generate_suggestions([])
        assert isinstance(result, list)
        assert len(result) == 0

    def test_generate_suggestions_returns_list(self, tmp_path: Path) -> None:
        engine = self._make_engine()
        f = tmp_path / "file.txt"
        f.write_text("content")
        pa = self._make_mock_pattern_analysis(tmp_path)
        result = engine.generate_suggestions([f], pattern_analysis=pa)
        # No location patterns means no move suggestions; result is a list (possibly empty)
        assert result is not None
        # Every item in result is a Suggestion
        for s in result:
            assert s.confidence >= 0.0

    def test_rank_suggestions_sorted_by_confidence(self, tmp_path: Path) -> None:
        from file_organizer.models.suggestion_types import Suggestion, SuggestionType

        engine = self._make_engine()
        s1 = Suggestion(
            "id1", SuggestionType.MOVE, tmp_path / "a.txt", confidence=30.0, reasoning="r"
        )
        s2 = Suggestion(
            "id2", SuggestionType.MOVE, tmp_path / "b.txt", confidence=80.0, reasoning="r"
        )
        s3 = Suggestion(
            "id3", SuggestionType.MOVE, tmp_path / "c.txt", confidence=50.0, reasoning="r"
        )
        ranked = engine.rank_suggestions([s1, s2, s3])
        assert ranked[0].confidence >= ranked[1].confidence
        assert ranked[1].confidence >= ranked[2].confidence

    def test_rank_suggestions_empty_list(self) -> None:
        engine = self._make_engine()
        result = engine.rank_suggestions([])
        assert result == []

    def test_explain_suggestion_contains_type(self, tmp_path: Path) -> None:
        from file_organizer.models.suggestion_types import Suggestion, SuggestionType

        engine = self._make_engine()
        s = Suggestion(
            "id1",
            SuggestionType.MOVE,
            tmp_path / "file.txt",
            confidence=75.0,
            reasoning="test reason",
        )
        explanation = engine.explain_suggestion(s)
        assert "MOVE" in explanation
        assert "75.0" in explanation
        assert "test reason" in explanation

    def test_explain_suggestion_with_factors(self, tmp_path: Path) -> None:
        from file_organizer.models.suggestion_types import Suggestion, SuggestionType

        engine = self._make_engine()
        s = Suggestion(
            "id2",
            SuggestionType.RENAME,
            tmp_path / "file.txt",
            confidence=60.0,
            reasoning="reason",
            metadata={"factors": {"pattern_strength": 70.0}},
        )
        explanation = engine.explain_suggestion(s)
        assert "pattern_strength" in explanation

    def test_generate_id_returns_string(self, tmp_path: Path) -> None:
        engine = self._make_engine()
        result = engine._generate_id(tmp_path / "file.txt", tmp_path / "target")
        assert isinstance(result, str)
        assert len(result) == 16

    def test_generate_id_different_paths_differ(self, tmp_path: Path) -> None:
        engine = self._make_engine()
        id1 = engine._generate_id(tmp_path / "a.txt", None)
        id2 = engine._generate_id(tmp_path / "b.txt", None)
        assert id1 != id2

    def test_get_common_root_empty_returns_cwd(self) -> None:
        engine = self._make_engine()
        result = engine._get_common_root([])
        assert isinstance(result, Path)

    def test_get_common_root_single_file(self, tmp_path: Path) -> None:
        engine = self._make_engine()
        f = tmp_path / "file.txt"
        result = engine._get_common_root([f])
        assert isinstance(result, Path)

    def test_find_best_location_no_candidates(self, tmp_path: Path) -> None:
        engine = self._make_engine()
        f = tmp_path / "file.txt"
        pa = self._make_mock_pattern_analysis(tmp_path)
        result = engine._find_best_location(f, pa)
        assert result is None

    def test_suggest_better_name_returns_none_by_default(self, tmp_path: Path) -> None:
        engine = self._make_engine()
        f = tmp_path / "file.txt"
        pa = self._make_mock_pattern_analysis(tmp_path)
        result = engine._suggest_better_name(f, pa)
        assert result is None

    def test_generate_move_reasoning_no_strong_factors(self, tmp_path: Path) -> None:
        from file_organizer.models.suggestion_types import ConfidenceFactors

        engine = self._make_engine()
        f = tmp_path / "file.txt"
        target = tmp_path / "docs"
        factors = ConfidenceFactors()  # All zeros
        result = engine._generate_move_reasoning(f, target, factors)
        assert isinstance(result, str)
        assert len(result) >= 5

    def test_generate_move_reasoning_with_strong_pattern(self, tmp_path: Path) -> None:
        from file_organizer.models.suggestion_types import ConfidenceFactors

        engine = self._make_engine()
        f = tmp_path / "file.txt"
        target = tmp_path / "docs"
        factors = ConfidenceFactors(pattern_strength=80.0, file_type_match=70.0)
        result = engine._generate_move_reasoning(f, target, factors)
        assert "pattern" in result.lower() or "type" in result.lower()

    def test_suggest_restructures_empty_clusters(self, tmp_path: Path) -> None:
        engine = self._make_engine()
        pa = self._make_mock_pattern_analysis(tmp_path)
        pa.content_clusters = []
        result = engine._suggest_restructures(pa)
        assert result == []

    def test_suggest_restructures_below_threshold(self, tmp_path: Path) -> None:
        engine = self._make_engine()
        pa = self._make_mock_pattern_analysis(tmp_path)
        cluster = MagicMock()
        cluster.file_paths = [tmp_path / f"f{i}.txt" for i in range(3)]  # fewer than 5
        cluster.confidence = 80
        cluster.category = "documents"
        cluster.common_keywords = ["report", "data"]
        pa.content_clusters = [cluster]
        result = engine._suggest_restructures(pa)
        assert result == []  # < 5 files, not suggested

    def test_generate_suggestions_max_suggestions_respected(self, tmp_path: Path) -> None:
        engine = self._make_engine(min_confidence=0.0)
        files = [tmp_path / f"file_{i}.txt" for i in range(20)]
        for f in files:
            f.write_text("content")
        # Create a location pattern so move suggestions are generated
        pa = self._make_mock_pattern_analysis(tmp_path)
        target_dir = tmp_path / "docs"
        target_dir.mkdir()
        mock_loc = MagicMock()
        mock_loc.file_types = {".txt"}
        mock_loc.directory = target_dir
        mock_loc.file_count = 10
        pa.location_patterns = [mock_loc]
        result = engine.generate_suggestions(files, pattern_analysis=pa, max_suggestions=5)
        # max_suggestions=5 is a hard cap on the returned list
        assert len(result) == 5
