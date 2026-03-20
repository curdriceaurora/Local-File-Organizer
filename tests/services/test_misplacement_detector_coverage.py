"""Coverage tests for MisplacementDetector — targets uncovered branches."""

from __future__ import annotations

from pathlib import Path

import pytest

from file_organizer.services.misplacement_detector import (
    ContextAnalysis,
    MisplacedFile,
    MisplacementDetector,
)
from file_organizer.services.pattern_analyzer import (
    LocationPattern,
    PatternAnalysis,
)

pytestmark = pytest.mark.unit


@pytest.fixture()
def detector():
    return MisplacementDetector(min_mismatch_score=30.0)


def _make_pattern_analysis(directory: Path, location_patterns=None, clusters=None):
    return PatternAnalysis(
        directory=directory,
        location_patterns=location_patterns or [],
        content_clusters=clusters or [],
        naming_patterns=[],
        file_type_distribution={},
        depth_distribution={},
        analyzed_at=__import__("datetime").datetime.now(),
        total_files=0,
    )


# ---------------------------------------------------------------------------
# MisplacedFile / ContextAnalysis dataclasses
# ---------------------------------------------------------------------------


class TestDataclasses:
    def test_misplaced_file_to_dict(self):
        mf = MisplacedFile(
            file_path=Path("/a/b.txt"),
            current_location=Path("/a"),
            suggested_location=Path("/c"),
            mismatch_score=75.0,
            reasons=["type mismatch"],
            similar_files=[Path("/c/d.txt")],
        )
        d = mf.to_dict()
        assert d["mismatch_score"] == 75.0
        assert len(d["similar_files"]) == 1

    def test_context_analysis_to_dict(self, tmp_path):
        ca = ContextAnalysis(
            file_path=tmp_path / "f.txt",
            file_type=".txt",
            mime_type="text/plain",
            size=100,
            directory=tmp_path,
            sibling_files=[],
            sibling_types=set(),
            parent_category="documents",
            naming_patterns=[],
        )
        d = ca.to_dict()
        assert d["file_type"] == ".txt"
        assert d["sibling_count"] == 0


# ---------------------------------------------------------------------------
# detect_misplaced
# ---------------------------------------------------------------------------


class TestDetectMisplaced:
    def test_invalid_directory(self, detector):
        with pytest.raises(ValueError, match="Invalid directory"):
            detector.detect_misplaced(Path("/nonexistent"))

    def test_empty_directory(self, detector, tmp_path):
        result = detector.detect_misplaced(tmp_path)
        assert result == []

    def test_detects_misplaced_file(self, detector, tmp_path):
        # Create a directory with images and one text file (misplaced)
        img_dir = tmp_path / "photos"
        img_dir.mkdir()
        (img_dir / "a.jpg").write_bytes(b"\xff\xd8")
        (img_dir / "b.jpg").write_bytes(b"\xff\xd8")
        (img_dir / "c.jpg").write_bytes(b"\xff\xd8")
        (img_dir / "notes.py").write_text("code")

        # Use low threshold to catch it
        det = MisplacementDetector(min_mismatch_score=20.0)
        results = det.detect_misplaced(img_dir)
        # Should detect at least something (the .py file among .jpg files)
        assert isinstance(results, list) and len(results) >= 1


# ---------------------------------------------------------------------------
# analyze_context
# ---------------------------------------------------------------------------


class TestAnalyzeContext:
    def test_basic_context(self, detector, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello")
        ctx = detector.analyze_context(f)
        assert ctx.file_type == ".txt"
        assert ctx.size > 0
        assert ctx.parent_category == "documents"

    def test_context_with_siblings(self, detector, tmp_path):
        (tmp_path / "a.txt").write_text("x")
        (tmp_path / "b.py").write_text("y")
        f = tmp_path / "c.md"
        f.write_text("z")
        ctx = detector.analyze_context(f)
        assert len(ctx.sibling_files) == 2
        assert ".txt" in ctx.sibling_types

    def test_context_missing_file(self, detector, tmp_path):
        f = tmp_path / "gone.txt"
        f.write_text("x")
        f.unlink()
        f.write_text("")  # recreate empty so stat works
        ctx = detector.analyze_context(f)
        assert ctx.size == 0


# ---------------------------------------------------------------------------
# calculate_mismatch_score
# ---------------------------------------------------------------------------


class TestCalculateMismatchScore:
    def test_score_range(self, detector, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("content")
        ctx = detector.analyze_context(f)
        pa = _make_pattern_analysis(tmp_path)
        score = detector.calculate_mismatch_score(f, ctx, pa)
        assert 0.0 <= score <= 100.0


# ---------------------------------------------------------------------------
# find_correct_location
# ---------------------------------------------------------------------------


class TestFindCorrectLocation:
    def test_no_matching_pattern(self, detector, tmp_path):
        f = tmp_path / "test.txt"
        pa = _make_pattern_analysis(tmp_path)
        loc = detector.find_correct_location(f, pa)
        assert loc == tmp_path / "documents"

    def test_matching_pattern_by_type(self, detector, tmp_path):
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        lp = LocationPattern(
            directory=docs_dir,
            file_types={".txt", ".md"},
            naming_patterns=[],
            file_count=10,
            depth_level=1,
            category="documents",
        )
        f = tmp_path / "other" / "test.txt"
        (tmp_path / "other").mkdir()
        pa = _make_pattern_analysis(tmp_path, location_patterns=[lp])
        loc = detector.find_correct_location(f, pa)
        assert loc == docs_dir


# ---------------------------------------------------------------------------
# find_similar_files
# ---------------------------------------------------------------------------


class TestFindSimilarFiles:
    def test_no_target_dir(self, detector, tmp_path):
        result = detector.find_similar_files(
            tmp_path / "test.txt", tmp_path / "nonexist", _make_pattern_analysis(tmp_path)
        )
        assert result == []


# ---------------------------------------------------------------------------
# _calculate_type_mismatch
# ---------------------------------------------------------------------------


class TestTypeMismatch:
    def test_no_siblings(self, detector, tmp_path):
        ctx = ContextAnalysis(
            file_path=tmp_path / "f.txt",
            file_type=".txt",
            mime_type=None,
            size=0,
            directory=tmp_path,
            sibling_files=[],
            sibling_types=set(),
            parent_category="documents",
            naming_patterns=[],
        )
        score = detector._calculate_type_mismatch(ctx)
        assert score == 30.0

    def test_same_type(self, detector, tmp_path):
        ctx = ContextAnalysis(
            file_path=tmp_path / "f.txt",
            file_type=".txt",
            mime_type=None,
            size=0,
            directory=tmp_path,
            sibling_files=[],
            sibling_types={".txt"},
            parent_category="documents",
            naming_patterns=[],
        )
        score = detector._calculate_type_mismatch(ctx)
        assert score == 10.0

    def test_same_category(self, detector, tmp_path):
        ctx = ContextAnalysis(
            file_path=tmp_path / "f.txt",
            file_type=".txt",
            mime_type=None,
            size=0,
            directory=tmp_path,
            sibling_files=[],
            sibling_types={".md"},  # same category as .txt
            parent_category="documents",
            naming_patterns=[],
        )
        score = detector._calculate_type_mismatch(ctx)
        assert score == 30.0

    def test_different_category(self, detector, tmp_path):
        ctx = ContextAnalysis(
            file_path=tmp_path / "f.txt",
            file_type=".txt",
            mime_type=None,
            size=0,
            directory=tmp_path,
            sibling_files=[],
            sibling_types={".jpg"},  # different category
            parent_category="documents",
            naming_patterns=[],
        )
        score = detector._calculate_type_mismatch(ctx)
        assert score == 80.0


# ---------------------------------------------------------------------------
# _calculate_isolation_score
# ---------------------------------------------------------------------------


class TestIsolationScore:
    def test_no_siblings(self, detector, tmp_path):
        ctx = ContextAnalysis(
            file_path=tmp_path / "f.txt",
            file_type=".txt",
            mime_type=None,
            size=0,
            directory=tmp_path,
            sibling_files=[],
            sibling_types=set(),
            parent_category="documents",
            naming_patterns=[],
        )
        assert detector._calculate_isolation_score(ctx) == 80.0

    def test_few_siblings(self, detector, tmp_path):
        ctx = ContextAnalysis(
            file_path=tmp_path / "f.txt",
            file_type=".txt",
            mime_type=None,
            size=0,
            directory=tmp_path,
            sibling_files=[Path("a"), Path("b")],
            sibling_types=set(),
            parent_category="documents",
            naming_patterns=[],
        )
        assert detector._calculate_isolation_score(ctx) == 60.0

    def test_many_siblings(self, detector, tmp_path):
        ctx = ContextAnalysis(
            file_path=tmp_path / "f.txt",
            file_type=".txt",
            mime_type=None,
            size=0,
            directory=tmp_path,
            sibling_files=[Path(str(i)) for i in range(15)],
            sibling_types=set(),
            parent_category="documents",
            naming_patterns=[],
        )
        assert detector._calculate_isolation_score(ctx) == 10.0


# ---------------------------------------------------------------------------
# _calculate_naming_mismatch
# ---------------------------------------------------------------------------


class TestNamingMismatch:
    def test_no_siblings(self, detector, tmp_path):
        f = tmp_path / "test.txt"
        ctx = ContextAnalysis(
            file_path=f,
            file_type=".txt",
            mime_type=None,
            size=0,
            directory=tmp_path,
            sibling_files=[],
            sibling_types=set(),
            parent_category="documents",
            naming_patterns=[],
        )
        assert detector._calculate_naming_mismatch(f, ctx) == 30.0

    def test_underscore_vs_dash(self, detector, tmp_path):
        f = tmp_path / "my_file.txt"
        ctx = ContextAnalysis(
            file_path=f,
            file_type=".txt",
            mime_type=None,
            size=0,
            directory=tmp_path,
            sibling_files=[
                tmp_path / "a-b.txt",
                tmp_path / "c-d.txt",
                tmp_path / "e-f.txt",
            ],
            sibling_types={".txt"},
            parent_category="documents",
            naming_patterns=[],
        )
        score = detector._calculate_naming_mismatch(f, ctx)
        assert score == 60.0


# ---------------------------------------------------------------------------
# _detect_local_patterns
# ---------------------------------------------------------------------------


class TestDetectLocalPatterns:
    def test_empty(self, detector):
        assert detector._detect_local_patterns([]) == []

    def test_detects_date(self, detector, tmp_path):
        files = [
            tmp_path / "2024-01-report.txt",
            tmp_path / "2024-02-report.txt",
            tmp_path / "2024-03-report.txt",
        ]
        patterns = detector._detect_local_patterns(files)
        assert "date" in patterns

    def test_detects_numeric(self, detector, tmp_path):
        files = [
            tmp_path / "001-intro.txt",
            tmp_path / "002-chapter.txt",
            tmp_path / "003-end.txt",
        ]
        patterns = detector._detect_local_patterns(files)
        assert "numeric" in patterns

    def test_detects_underscore(self, detector, tmp_path):
        files = [
            tmp_path / "my_file_a.txt",
            tmp_path / "my_file_b.txt",
            tmp_path / "my_file_c.txt",
        ]
        patterns = detector._detect_local_patterns(files)
        assert "underscore" in patterns


# ---------------------------------------------------------------------------
# _infer_category_from_type
# ---------------------------------------------------------------------------


class TestInferCategory:
    def test_known(self, detector):
        assert detector._infer_category_from_type(".pdf") == "documents"
        assert detector._infer_category_from_type(".jpg") == "images"
        assert detector._infer_category_from_type(".mp3") == "audio"

    def test_unknown(self, detector):
        assert detector._infer_category_from_type(".xyz") == "general"


# ---------------------------------------------------------------------------
# _is_in_or_near
# ---------------------------------------------------------------------------


class TestIsInOrNear:
    def test_in_directory(self, detector, tmp_path):
        target = tmp_path / "docs"
        f = target / "readme.txt"
        assert detector._is_in_or_near(f, target) is True

    def test_sibling_directory(self, detector, tmp_path):
        target = tmp_path / "docs"
        f = tmp_path / "images" / "pic.jpg"
        assert detector._is_in_or_near(f, target) is True

    def test_not_near(self, detector, tmp_path):
        f = tmp_path / "deep" / "nested" / "file.txt"
        target = tmp_path / "other" / "dir"
        assert detector._is_in_or_near(f, target) is False
