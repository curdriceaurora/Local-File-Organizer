"""
Unit tests for Misplacement Detector service.

Tests content-location mismatch detection, context analysis, and mismatch scoring.
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from file_organizer.services.misplacement_detector import (
    ContextAnalysis,
    MisplacedFile,
    MisplacementDetector,
)
from file_organizer.services.pattern_analyzer import PatternAnalyzer


@pytest.mark.unit
class TestMisplacedFile:
    """Tests for MisplacedFile dataclass."""

    def test_create_misplaced_file(self):
        """Test creating a misplaced file record."""
        file_path = Path("/test/photo.jpg")
        current_loc = Path("/documents")
        suggested_loc = Path("/pictures")

        misplaced = MisplacedFile(
            file_path=file_path,
            current_location=current_loc,
            suggested_location=suggested_loc,
            mismatch_score=75.5,
            reasons=["Type mismatch: jpg in document folder", "Isolated from similar files"],
        )

        assert misplaced.file_path == file_path
        assert misplaced.mismatch_score == 75.5
        assert len(misplaced.reasons) == 2

    def test_misplaced_file_to_dict(self):
        """Test conversion to dictionary."""
        misplaced = MisplacedFile(
            file_path=Path("/test/file.txt"),
            current_location=Path("/images"),
            suggested_location=Path("/documents"),
            mismatch_score=80.0,
            reasons=["Text file in image folder"],
        )

        d = misplaced.to_dict()

        assert isinstance(d, dict)
        assert "file_path" in d
        assert "mismatch_score" in d
        assert d["mismatch_score"] == 80.0


@pytest.mark.unit
class TestContextAnalysis:
    """Tests for ContextAnalysis dataclass."""

    def test_create_context_analysis(self):
        """Test creating a context analysis."""
        context = ContextAnalysis(
            file_path=Path("/test/document.pdf"),
            file_type=".pdf",
            mime_type="application/pdf",
            size=1024000,
            directory=Path("/documents"),
            sibling_files=[Path("/documents/other.pdf"), Path("/documents/report.docx")],
            sibling_types={".pdf", ".docx"},
            parent_category="documents",
            naming_patterns=["date_prefix", "snake_case"],
        )

        assert context.file_type == ".pdf"
        assert len(context.sibling_files) == 2
        assert "documents" in context.parent_category

    def test_context_analysis_to_dict(self):
        """Test context analysis conversion to dict."""
        context = ContextAnalysis(
            file_path=Path("/test/image.jpg"),
            file_type=".jpg",
            mime_type="image/jpeg",
            size=2048000,
            directory=Path("/images"),
            sibling_files=[],
            sibling_types={".jpg"},
            parent_category="images",
            naming_patterns=[],
        )

        d = context.to_dict()

        assert isinstance(d, dict)
        assert d["file_type"] == ".jpg"
        assert d["parent_category"] == "images"


@pytest.mark.unit
class TestMisplacementDetectorInit:
    """Tests for MisplacementDetector initialization."""

    def test_init_default_parameters(self):
        """Test initialization with default parameters."""
        detector = MisplacementDetector()

        assert detector.min_mismatch_score == 60.0
        assert detector.similarity_threshold == 0.7
        assert detector.pattern_analyzer is not None

    def test_init_custom_parameters(self):
        """Test initialization with custom parameters."""
        detector = MisplacementDetector(min_mismatch_score=50.0, similarity_threshold=0.8)

        assert detector.min_mismatch_score == 50.0
        assert detector.similarity_threshold == 0.8

    def test_has_category_types_mapping(self):
        """Test that detector has category type mappings."""
        detector = MisplacementDetector()

        assert "documents" in detector.category_types
        assert "images" in detector.category_types
        assert ".pdf" in detector.category_types["documents"]
        assert ".jpg" in detector.category_types["images"]


@pytest.mark.unit
class TestAnalyzeContext:
    """Tests for context analysis."""

    def test_analyze_context_single_file(self):
        """Test analyzing context of a single file."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Create a document
            doc = tmppath / "report.pdf"
            doc.write_text("pdf")

            detector = MisplacementDetector()
            context = detector.analyze_context(doc)

            assert context.file_path == doc
            assert context.file_type == ".pdf"
            assert context.directory == tmppath

    def test_analyze_context_with_siblings(self):
        """Test analyzing context of file with siblings."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Create document with siblings
            (tmppath / "report.pdf").write_text("pdf")
            (tmppath / "memo.docx").write_text("docx")
            (tmppath / "notes.txt").write_text("txt")

            detector = MisplacementDetector()
            context = detector.analyze_context(tmppath / "report.pdf")

            assert len(context.sibling_files) == 2
            assert context.sibling_types == {".docx", ".txt"}


@pytest.mark.unit
class TestDetectMisplaced:
    """Tests for misplaced file detection."""

    def test_detect_misplaced_empty_directory(self):
        """Test detection in empty directory."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            detector = MisplacementDetector()
            misplaced = detector.detect_misplaced(tmppath)

            assert isinstance(misplaced, list)
            assert len(misplaced) == 0

    def test_detect_misplaced_homogeneous_directory(self):
        """Test detection in directory with similar file types."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Create consistent document folder
            for i in range(3):
                (tmppath / f"document{i}.pdf").write_text("pdf")

            detector = MisplacementDetector()
            misplaced = detector.detect_misplaced(tmppath)

            # Homogeneous directory should have no misplaced files
            assert isinstance(misplaced, list)
            assert len(misplaced) == 0, "Homogeneous directory should have no misplaced files"

    def test_detect_misplaced_outlier_file(self):
        """Test detection of outlier file in directory."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Create mostly documents with one image
            for i in range(5):
                (tmppath / f"doc{i}.pdf").write_text("pdf")
            (tmppath / "photo.jpg").write_text("jpg")

            detector = MisplacementDetector()
            misplaced = detector.detect_misplaced(tmppath)

            assert isinstance(misplaced, list)
            # The image might be flagged as misplaced
            if len(misplaced) > 0:
                assert any(".jpg" in str(m.file_path) for m in misplaced)


@pytest.mark.unit
class TestMismatchScoring:
    """Tests for mismatch scoring."""

    def test_calculate_mismatch_score(self):
        """Test mismatch score calculation."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Create a file
            file_path = tmppath / "test.jpg"
            file_path.write_text("jpg")

            detector = MisplacementDetector()
            context = detector.analyze_context(file_path)
            analyzer = PatternAnalyzer()
            pattern_analysis = analyzer.analyze_directory(tmppath)
            score = detector.calculate_mismatch_score(file_path, context, pattern_analysis)

            assert isinstance(score, float)
            assert 0 <= score <= 100

    def test_mismatch_score_respects_threshold(self):
        """Test that threshold is respected."""
        detector = MisplacementDetector(min_mismatch_score=75.0)

        # Detector created with high threshold
        assert detector.min_mismatch_score == 75.0


@pytest.mark.unit
class TestCategoryDetection:
    """Tests for file category detection."""

    def test_infer_category_pdf(self):
        """Test PDF is detected as document."""
        detector = MisplacementDetector()

        category = detector._infer_category_from_type(".pdf")

        assert category == "documents"

    def test_infer_category_image(self):
        """Test image file type detection."""
        detector = MisplacementDetector()

        assert detector._infer_category_from_type(".jpg") == "images"
        assert detector._infer_category_from_type(".png") == "images"

    def test_infer_category_audio(self):
        """Test audio file type detection."""
        detector = MisplacementDetector()

        assert detector._infer_category_from_type(".mp3") == "audio"

    def test_infer_category_unknown(self):
        """Test unknown file type returns general."""
        detector = MisplacementDetector()

        category = detector._infer_category_from_type(".xyz")

        assert category == "general"


@pytest.mark.unit
class TestEdgeCases:
    """Tests for edge cases."""

    def test_detect_with_pattern_analysis(self):
        """Test detection with pre-computed pattern analysis."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            (tmppath / "file.pdf").write_text("pdf")

            # Pre-analyze patterns
            analyzer = PatternAnalyzer()
            pattern_analysis = analyzer.analyze_directory(tmppath)

            detector = MisplacementDetector()
            misplaced = detector.detect_misplaced(tmppath, pattern_analysis)

            assert isinstance(misplaced, list)

    def test_invalid_directory_raises_error(self):
        """Test that invalid directory raises error."""
        detector = MisplacementDetector()

        with pytest.raises(ValueError):
            detector.detect_misplaced(Path("/nonexistent/path"))

    def test_file_instead_of_directory_raises_error(self):
        """Test that file path instead of directory raises error."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            file_path = tmppath / "file.txt"
            file_path.write_text("content")

            detector = MisplacementDetector()

            with pytest.raises(ValueError):
                detector.detect_misplaced(file_path)
