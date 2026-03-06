"""Tests for file_organizer.services.smart_suggestions module.

Covers ConfidenceScorer and SuggestionEngine classes, hitting the
missed lines including user history, naming convention, file type match,
recency, size scoring, move reasoning, and common root calculation.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import pytest

from file_organizer.models.suggestion_types import (
    ConfidenceFactors,
    Suggestion,
    SuggestionType,
)
from file_organizer.services.misplacement_detector import MisplacementDetector
from file_organizer.services.pattern_analyzer import PatternAnalyzer
from file_organizer.services.smart_suggestions import (
    ConfidenceScorer,
    SuggestionEngine,
)
from file_organizer.services.suggestion_feedback import SuggestionFeedback

# ---------------------------------------------------------------------------
# Fake PatternAnalysis helpers
# ---------------------------------------------------------------------------


@dataclass
class FakeNamingPattern:
    pattern: str = "report_*"
    regex: str = r"report_.*"
    example_files: list[str] = field(default_factory=lambda: ["report_q1", "report_q2"])
    count: int = 5
    confidence: float = 80.0
    description: str = "report pattern"


@dataclass
class FakeLocationPattern:
    directory: Path = field(default_factory=lambda: Path("/docs"))
    file_types: set[str] = field(default_factory=lambda: {".pdf", ".txt"})
    naming_patterns: list[str] = field(default_factory=lambda: ["report_*"])
    file_count: int = 10
    depth_level: int = 1
    category: str | None = "documents"


@dataclass
class FakeContentCluster:
    cluster_id: str = "cluster-1"
    file_paths: list[Path] = field(default_factory=lambda: [Path(f"/f{i}.txt") for i in range(6)])
    common_keywords: list[str] = field(default_factory=lambda: ["report", "quarterly", "finance"])
    file_types: set[str] = field(default_factory=lambda: {".txt"})
    size_range: tuple[int, int] = (100, 5000)
    category: str = "reports"
    confidence: float = 75.0


@dataclass
class FakePatternAnalysis:
    directory: Path = field(default_factory=lambda: Path("/root"))
    naming_patterns: list[FakeNamingPattern] = field(default_factory=list)
    location_patterns: list[FakeLocationPattern] = field(default_factory=list)
    content_clusters: list[FakeContentCluster] = field(default_factory=list)
    file_type_distribution: dict[str, int] = field(default_factory=dict)
    depth_distribution: dict[int, int] = field(default_factory=dict)
    analyzed_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
    total_files: int = 20
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# ConfidenceScorer
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestConfidenceScorerUserHistory:
    """Test _calculate_user_history_score."""

    def test_no_target_returns_50(self):
        scorer = ConfidenceScorer()
        result = scorer._calculate_user_history_score(Path("/a.txt"), None, {"move_history": {}})
        assert result == 50.0

    def test_target_with_history(self, tmp_path):
        scorer = ConfidenceScorer()
        target = tmp_path / "dest"
        target.mkdir()
        history = {"move_history": {".txt": {str(target): 3}}}
        result = scorer._calculate_user_history_score(tmp_path / "a.txt", target / "a.txt", history)
        assert result > 50.0

    def test_target_no_match_in_history(self, tmp_path):
        scorer = ConfidenceScorer()
        history = {"move_history": {".txt": {"/other": 5}}}
        result = scorer._calculate_user_history_score(
            tmp_path / "a.txt", tmp_path / "dest" / "a.txt", history
        )
        assert result == 40.0

    def test_high_count_caps_at_100(self, tmp_path):
        scorer = ConfidenceScorer()
        target = tmp_path / "dest"
        target.mkdir()
        history = {"move_history": {".txt": {str(target): 20}}}
        result = scorer._calculate_user_history_score(tmp_path / "a.txt", target / "a.txt", history)
        assert result == 100.0


@pytest.mark.unit
class TestConfidenceScorerContentSimilarity:
    """Test _calculate_content_similarity."""

    def test_no_suffix(self, tmp_path):
        scorer = ConfidenceScorer()
        f = tmp_path / "noext"
        f.write_text("x")
        target = tmp_path / "dest"
        target.mkdir()
        result = scorer._calculate_content_similarity(f, target)
        assert result == 30.0

    def test_no_similar_files(self, tmp_path):
        scorer = ConfidenceScorer()
        f = tmp_path / "a.xyz"
        f.write_text("x")
        target = tmp_path / "dest"
        target.mkdir()
        result = scorer._calculate_content_similarity(f, target)
        assert result == 20.0

    def test_with_similar_files(self, tmp_path):
        scorer = ConfidenceScorer()
        f = tmp_path / "a.txt"
        f.write_text("x")
        target = tmp_path / "dest"
        target.mkdir()
        for i in range(5):
            (target / f"f{i}.txt").write_text("y")
        result = scorer._calculate_content_similarity(f, target)
        assert result >= 50.0


@pytest.mark.unit
class TestConfidenceScorerNamingMatch:
    """Test _calculate_naming_match."""

    def test_no_analysis(self):
        scorer = ConfidenceScorer()
        result = scorer._calculate_naming_match(Path("/a.txt"), Path("/dest"), None)
        assert result == 50.0

    def test_no_target_patterns(self):
        scorer = ConfidenceScorer()
        analysis = FakePatternAnalysis(
            location_patterns=[FakeLocationPattern(directory=Path("/other"))]
        )
        result = scorer._calculate_naming_match(Path("/a.txt"), Path("/dest/a.txt"), analysis)
        assert result == 40.0

    def test_with_naming_patterns(self, tmp_path):
        scorer = ConfidenceScorer()
        target = tmp_path / "docs"
        target.mkdir()
        analysis = FakePatternAnalysis(
            location_patterns=[FakeLocationPattern(directory=target, naming_patterns=["report_*"])]
        )
        result = scorer._calculate_naming_match(tmp_path / "a.txt", target / "a.txt", analysis)
        assert result == 70.0


@pytest.mark.unit
class TestConfidenceScorerFileTypeMatch:
    """Test _calculate_file_type_match."""

    def test_no_analysis(self):
        scorer = ConfidenceScorer()
        result = scorer._calculate_file_type_match(Path("/a.txt"), Path("/dest"), None)
        assert result == 50.0

    def test_no_target_patterns(self):
        scorer = ConfidenceScorer()
        analysis = FakePatternAnalysis(
            location_patterns=[FakeLocationPattern(directory=Path("/other"))]
        )
        result = scorer._calculate_file_type_match(Path("/a.txt"), Path("/dest/a.txt"), analysis)
        assert result == 40.0

    def test_matching_type(self, tmp_path):
        scorer = ConfidenceScorer()
        target = tmp_path / "docs"
        target.mkdir()
        analysis = FakePatternAnalysis(
            location_patterns=[FakeLocationPattern(directory=target, file_types={".txt", ".pdf"})]
        )
        result = scorer._calculate_file_type_match(tmp_path / "a.txt", target / "a.txt", analysis)
        assert result == 85.0

    def test_empty_target_types(self, tmp_path):
        scorer = ConfidenceScorer()
        target = tmp_path / "docs"
        target.mkdir()
        analysis = FakePatternAnalysis(
            location_patterns=[FakeLocationPattern(directory=target, file_types=set())]
        )
        result = scorer._calculate_file_type_match(tmp_path / "a.txt", target / "a.txt", analysis)
        assert result == 50.0

    def test_non_matching_type(self, tmp_path):
        scorer = ConfidenceScorer()
        target = tmp_path / "docs"
        target.mkdir()
        analysis = FakePatternAnalysis(
            location_patterns=[FakeLocationPattern(directory=target, file_types={".pdf"})]
        )
        result = scorer._calculate_file_type_match(tmp_path / "a.txt", target / "a.txt", analysis)
        assert result == 25.0


@pytest.mark.unit
class TestConfidenceScorerRecency:
    """Test _calculate_recency_score."""

    def test_recent_file(self, tmp_path):
        scorer = ConfidenceScorer()
        f = tmp_path / "new.txt"
        f.write_text("x")
        result = scorer._calculate_recency_score(f)
        assert result == 60.0

    def test_old_file(self, tmp_path):
        import os

        scorer = ConfidenceScorer()
        f = tmp_path / "old.txt"
        f.write_text("x")
        old_ts = time.time() - (100 * 86400)
        os.utime(f, (old_ts, old_ts))
        result = scorer._calculate_recency_score(f)
        assert result == 45.0

    def test_missing_file(self, tmp_path):
        scorer = ConfidenceScorer()
        result = scorer._calculate_recency_score(tmp_path / "nope.txt")
        assert result == 50.0


@pytest.mark.unit
class TestConfidenceScorerSizeScore:
    """Test _calculate_size_score."""

    def test_similar_size(self, tmp_path):
        scorer = ConfidenceScorer()
        f = tmp_path / "a.txt"
        f.write_bytes(b"x" * 100)
        target = tmp_path / "dest"
        target.mkdir()
        (target / "b.txt").write_bytes(b"y" * 100)
        result = scorer._calculate_size_score(f, target)
        assert result == 70.0

    def test_very_different_size(self, tmp_path):
        scorer = ConfidenceScorer()
        f = tmp_path / "big.txt"
        f.write_bytes(b"x" * 10000)
        target = tmp_path / "dest"
        target.mkdir()
        (target / "small.txt").write_bytes(b"y" * 1)
        result = scorer._calculate_size_score(f, target)
        assert result == 30.0

    def test_empty_target_dir(self, tmp_path):
        scorer = ConfidenceScorer()
        f = tmp_path / "a.txt"
        f.write_bytes(b"x" * 100)
        target = tmp_path / "dest"
        target.mkdir()
        result = scorer._calculate_size_score(f, target)
        assert result == 50.0

    def test_error_handling(self, tmp_path):
        scorer = ConfidenceScorer()
        result = scorer._calculate_size_score(tmp_path / "nope.txt", tmp_path / "also_nope")
        assert result == 50.0


# ---------------------------------------------------------------------------
# SuggestionEngine
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSuggestionEngineGenerateSuggestions:
    """Test generate_suggestions."""

    def test_empty_files_returns_empty(self):
        engine = SuggestionEngine()
        result = engine.generate_suggestions([])
        assert result == []

    def test_basic_generation(self, tmp_path):
        engine = SuggestionEngine(min_confidence=0.0)
        f = tmp_path / "a.txt"
        f.write_text("x")
        analysis = FakePatternAnalysis(
            directory=tmp_path,
            location_patterns=[
                FakeLocationPattern(
                    directory=tmp_path / "docs",
                    file_types={".txt"},
                    file_count=20,
                )
            ],
        )
        (tmp_path / "docs").mkdir()
        result = engine.generate_suggestions([f], pattern_analysis=analysis)
        assert isinstance(result, list)


@pytest.mark.unit
class TestSuggestionEngineExplain:
    """Test explain_suggestion."""

    def test_with_factors(self):
        engine = SuggestionEngine()
        factors = ConfidenceFactors(pattern_strength=80.0, content_similarity=60.0)
        suggestion = Suggestion(
            suggestion_id="test",
            suggestion_type=SuggestionType.MOVE,
            file_path=Path("/a.txt"),
            confidence=70.0,
            reasoning="test reason",
            metadata={"factors": factors.to_dict()},
        )
        explanation = engine.explain_suggestion(suggestion)
        assert "MOVE" in explanation
        assert "70.0" in explanation
        assert "pattern_strength" in explanation

    def test_without_factors(self):
        engine = SuggestionEngine()
        suggestion = Suggestion(
            suggestion_id="test",
            suggestion_type=SuggestionType.RENAME,
            file_path=Path("/a.txt"),
            confidence=50.0,
            reasoning="rename reason",
            metadata={},
        )
        explanation = engine.explain_suggestion(suggestion)
        assert "RENAME" in explanation


@pytest.mark.unit
class TestSuggestionEngineMoveReasoning:
    """Test _generate_move_reasoning."""

    def test_high_pattern_strength(self):
        engine = SuggestionEngine()
        factors = ConfidenceFactors(pattern_strength=80.0)
        result = engine._generate_move_reasoning(Path("/a.txt"), Path("/dest"), factors)
        assert "pattern" in result

    def test_high_file_type_match(self):
        engine = SuggestionEngine()
        factors = ConfidenceFactors(file_type_match=80.0)
        result = engine._generate_move_reasoning(Path("/a.txt"), Path("/dest"), factors)
        assert "file type" in result

    def test_high_content_similarity(self):
        engine = SuggestionEngine()
        factors = ConfidenceFactors(content_similarity=80.0)
        result = engine._generate_move_reasoning(Path("/a.txt"), Path("/dest"), factors)
        assert "similar files" in result

    def test_high_user_history(self):
        engine = SuggestionEngine()
        factors = ConfidenceFactors(user_history=80.0)
        result = engine._generate_move_reasoning(Path("/a.txt"), Path("/dest"), factors)
        assert "moved similar" in result

    def test_no_reasons_fallback(self):
        engine = SuggestionEngine()
        factors = ConfidenceFactors()
        result = engine._generate_move_reasoning(Path("/a.txt"), Path("/dest"), factors)
        assert "improve organization" in result


@pytest.mark.unit
class TestSuggestionEngineCommonRoot:
    """Test _get_common_root."""

    def test_empty_files(self):
        engine = SuggestionEngine()
        assert engine._get_common_root([]) == Path.cwd()

    def test_single_file(self, tmp_path):
        engine = SuggestionEngine()
        f = tmp_path / "a.txt"
        result = engine._get_common_root([f])
        assert result == tmp_path

    def test_multiple_files_same_dir(self, tmp_path):
        engine = SuggestionEngine()
        files = [tmp_path / "a.txt", tmp_path / "b.txt"]
        result = engine._get_common_root(files)
        assert result == tmp_path

    def test_different_dirs(self, tmp_path):
        engine = SuggestionEngine()
        d1 = tmp_path / "sub1"
        d1.mkdir()
        d2 = tmp_path / "sub2"
        d2.mkdir()
        files = [d1 / "a.txt", d2 / "b.txt"]
        result = engine._get_common_root(files)
        # Should find a common ancestor
        assert isinstance(result, Path)


@pytest.mark.unit
class TestSuggestionEngineFindBestLocation:
    """Test _find_best_location."""

    def test_no_candidates(self, tmp_path):
        engine = SuggestionEngine()
        analysis = FakePatternAnalysis(location_patterns=[])
        result = engine._find_best_location(tmp_path / "a.txt", analysis)
        assert result is None

    def test_matching_candidate(self, tmp_path):
        engine = SuggestionEngine()
        target = tmp_path / "docs"
        target.mkdir()
        analysis = FakePatternAnalysis(
            location_patterns=[
                FakeLocationPattern(directory=target, file_types={".txt"}, file_count=10)
            ]
        )
        result = engine._find_best_location(tmp_path / "sub" / "a.txt", analysis)
        assert result == target


@pytest.mark.unit
class TestSuggestionEngineRank:
    """Test rank_suggestions."""

    def test_sort_by_confidence(self):
        engine = SuggestionEngine()
        s1 = Suggestion(
            suggestion_id="1",
            suggestion_type=SuggestionType.MOVE,
            file_path=Path("/a"),
            confidence=50.0,
        )
        s2 = Suggestion(
            suggestion_id="2",
            suggestion_type=SuggestionType.MOVE,
            file_path=Path("/b"),
            confidence=90.0,
        )
        ranked = engine.rank_suggestions([s1, s2])
        assert ranked[0].suggestion_id == "2"

    def test_sort_by_type_priority(self):
        engine = SuggestionEngine()
        s1 = Suggestion(
            suggestion_id="1",
            suggestion_type=SuggestionType.RENAME,
            file_path=Path("/a"),
            confidence=70.0,
        )
        s2 = Suggestion(
            suggestion_id="2",
            suggestion_type=SuggestionType.RESTRUCTURE,
            file_path=Path("/b"),
            confidence=70.0,
        )
        ranked = engine.rank_suggestions([s1, s2])
        assert ranked[0].suggestion_type == SuggestionType.RESTRUCTURE


# ---------------------------------------------------------------------------
# PatternAnalyzer (real file I/O tests)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPatternAnalyzer:
    """Tests for PatternAnalyzer with real file structures."""

    @pytest.fixture
    def sample_files(self, tmp_path):
        """Create sample file structure."""
        docs_dir = tmp_path / "documents"
        docs_dir.mkdir()
        (docs_dir / "2024-01-15_report.pdf").touch()
        (docs_dir / "2024-02-20_meeting.pdf").touch()
        (docs_dir / "2024-03-10_notes.pdf").touch()

        images_dir = tmp_path / "images"
        images_dir.mkdir()
        (images_dir / "photo_001.jpg").touch()
        (images_dir / "photo_002.jpg").touch()
        (images_dir / "photo_003.jpg").touch()

        code_dir = tmp_path / "code"
        code_dir.mkdir()
        (code_dir / "main_app.py").touch()
        (code_dir / "test_utils.py").touch()
        (code_dir / "helper_functions.py").touch()

        return tmp_path

    def test_analyze_directory(self, sample_files):
        """Test complete directory analysis."""
        analyzer = PatternAnalyzer(min_pattern_count=2)
        analysis = analyzer.analyze_directory(sample_files)

        assert analysis.directory == sample_files
        assert analysis.total_files == 9
        assert len(analysis.naming_patterns) > 0
        assert len(analysis.location_patterns) > 0
        assert len(analysis.file_type_distribution) > 0

    def test_detect_naming_patterns(self, sample_files):
        """Test naming pattern detection."""
        analyzer = PatternAnalyzer(min_pattern_count=2)
        files = [f for f in sample_files.rglob("*") if f.is_file()]
        patterns = analyzer.detect_naming_patterns(files)

        pattern_types = [p.pattern for p in patterns]
        assert "DATE_PREFIX" in pattern_types or "NUMERIC_SUFFIX" in pattern_types

        for pattern in patterns:
            assert pattern.count >= 2
            assert 0 <= pattern.confidence <= 100
            assert len(pattern.example_files) > 0

    def test_get_location_patterns(self, sample_files):
        """Test location pattern detection."""
        analyzer = PatternAnalyzer(min_pattern_count=2)
        location_patterns = analyzer.get_location_patterns(sample_files)

        assert len(location_patterns) >= 3
        for pattern in location_patterns:
            assert pattern.file_count >= 2
            assert len(pattern.file_types) > 0
            assert pattern.depth_level >= 0

    def test_cluster_by_content(self, sample_files):
        """Test content-based clustering."""
        analyzer = PatternAnalyzer(min_pattern_count=2)
        files = [f for f in sample_files.rglob("*") if f.is_file()]
        clusters = analyzer.cluster_by_content(files)

        assert len(clusters) > 0
        for cluster in clusters:
            assert len(cluster.file_paths) >= 2
            assert 0 <= cluster.confidence <= 100
            assert cluster.category in ["documents", "images", "code", "general"]

    def test_empty_directory(self, tmp_path):
        """Test analysis of empty directory."""
        analyzer = PatternAnalyzer()
        analysis = analyzer.analyze_directory(tmp_path)
        assert analysis.total_files == 0
        assert len(analysis.naming_patterns) == 0


# ---------------------------------------------------------------------------
# SuggestionEngine — integration-level tests with real file I/O
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestSuggestionEngineIntegration:
    """Integration-level tests for SuggestionEngine with real files."""

    @pytest.fixture
    def organized_structure(self, tmp_path):
        """Create organized file structure."""
        docs = tmp_path / "documents"
        docs.mkdir()
        (docs / "report1.pdf").touch()
        (docs / "report2.pdf").touch()

        images = tmp_path / "images"
        images.mkdir()
        (images / "photo1.jpg").touch()
        (images / "photo2.jpg").touch()

        (tmp_path / "misplaced_photo.jpg").touch()
        return tmp_path

    def test_generate_suggestions_real(self, organized_structure):
        """Test suggestion generation with real files."""
        engine = SuggestionEngine(min_confidence=30.0)
        files = [organized_structure / "misplaced_photo.jpg"]
        suggestions = engine.generate_suggestions(files)

        assert len(suggestions) > 0
        for suggestion in suggestions:
            assert suggestion.confidence >= 30.0
            assert suggestion.reasoning != ""
            assert suggestion.suggestion_type in SuggestionType

    def test_confidence_scorer_real(self, organized_structure):
        """Test confidence scoring with real analysis."""
        scorer = ConfidenceScorer()
        analyzer = PatternAnalyzer()
        analysis = analyzer.analyze_directory(organized_structure)

        file_path = organized_structure / "misplaced_photo.jpg"
        target_path = organized_structure / "images"

        factors = scorer.score_suggestion(file_path, target_path, SuggestionType.MOVE, analysis)

        assert 0 <= factors.pattern_strength <= 100
        assert 0 <= factors.content_similarity <= 100
        assert 0 <= factors.file_type_match <= 100

        score = factors.calculate_weighted_score()
        assert 0 <= score <= 100


# ---------------------------------------------------------------------------
# MisplacementDetector
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMisplacementDetector:
    """Tests for MisplacementDetector."""

    @pytest.fixture
    def misplaced_structure(self, tmp_path):
        """Create structure with misplaced files."""
        docs = tmp_path / "documents"
        docs.mkdir()
        (docs / "report1.pdf").touch()
        (docs / "report2.pdf").touch()
        (docs / "vacation_photo.jpg").touch()

        images = tmp_path / "images"
        images.mkdir()
        (images / "photo1.jpg").touch()
        (images / "photo2.jpg").touch()
        (images / "important_report.pdf").touch()

        return tmp_path

    def test_detect_misplaced(self, misplaced_structure):
        """Test misplaced file detection."""
        detector = MisplacementDetector(min_mismatch_score=50.0)
        misplaced = detector.detect_misplaced(misplaced_structure)

        assert len(misplaced) >= 1
        for mp in misplaced:
            assert mp.mismatch_score >= 50.0
            assert len(mp.reasons) > 0
            assert mp.suggested_location != mp.current_location

    def test_analyze_context(self, misplaced_structure):
        """Test context analysis."""
        detector = MisplacementDetector()
        file_path = misplaced_structure / "documents" / "vacation_photo.jpg"
        context = detector.analyze_context(file_path)

        assert context.file_type == ".jpg"
        assert context.directory == misplaced_structure / "documents"
        assert len(context.sibling_files) >= 2
        assert context.parent_category == "images"

    def test_calculate_mismatch_score(self, misplaced_structure):
        """Test mismatch score calculation."""
        detector = MisplacementDetector()
        analyzer = PatternAnalyzer()
        analysis = analyzer.analyze_directory(misplaced_structure)

        file_path = misplaced_structure / "documents" / "vacation_photo.jpg"
        context = detector.analyze_context(file_path)
        score = detector.calculate_mismatch_score(file_path, context, analysis)

        assert score > 40.0

    def test_find_correct_location(self, misplaced_structure):
        """Test finding correct location."""
        detector = MisplacementDetector()
        analyzer = PatternAnalyzer()
        analysis = analyzer.analyze_directory(misplaced_structure)

        file_path = misplaced_structure / "documents" / "vacation_photo.jpg"
        suggested = detector.find_correct_location(file_path, analysis)

        assert suggested.name == "images" or "image" in str(suggested).lower()


# ---------------------------------------------------------------------------
# SuggestionFeedback
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSuggestionFeedback:
    """Tests for SuggestionFeedback."""

    @pytest.fixture
    def temp_feedback_file(self, tmp_path):
        """Create temporary feedback file."""
        return tmp_path / "feedback.json"

    def test_record_action(self, temp_feedback_file):
        """Test recording feedback."""
        feedback = SuggestionFeedback(feedback_file=temp_feedback_file)
        suggestion = Suggestion(
            suggestion_id="test1",
            suggestion_type=SuggestionType.MOVE,
            file_path=Path("test.jpg"),
            target_path=Path("images/test.jpg"),
            confidence=75.0,
            reasoning="Test",
        )
        feedback.record_action(suggestion, "accepted")
        assert len(feedback.feedback_entries) == 1
        assert feedback.feedback_entries[0].action == "accepted"

    def test_get_acceptance_rate(self, temp_feedback_file):
        """Test acceptance rate calculation."""
        feedback = SuggestionFeedback(feedback_file=temp_feedback_file)
        for i in range(5):
            suggestion = Suggestion(
                suggestion_id=f"test{i}",
                suggestion_type=SuggestionType.MOVE,
                file_path=Path(f"test{i}.jpg"),
                confidence=70.0,
                reasoning="Test",
            )
            action = "accepted" if i < 3 else "rejected"
            feedback.record_action(suggestion, action)

        rate = feedback.get_acceptance_rate()
        assert rate == 60.0

    def test_get_learning_stats(self, temp_feedback_file):
        """Test learning statistics."""
        feedback = SuggestionFeedback(feedback_file=temp_feedback_file)
        actions = ["accepted", "accepted", "rejected", "ignored", "modified"]
        for i, action in enumerate(actions):
            suggestion = Suggestion(
                suggestion_id=f"test{i}",
                suggestion_type=SuggestionType.MOVE,
                file_path=Path(f"test{i}.jpg"),
                confidence=70.0,
                reasoning="Test",
            )
            feedback.record_action(suggestion, action)

        stats = feedback.get_learning_stats()
        assert stats.total_suggestions == 5
        assert stats.accepted == 2
        assert stats.rejected == 1
        assert stats.ignored == 1
        assert stats.modified == 1
        assert stats.acceptance_rate == 40.0

    def test_get_user_history(self, temp_feedback_file):
        """Test user history retrieval."""
        feedback = SuggestionFeedback(feedback_file=temp_feedback_file)
        for i in range(3):
            suggestion = Suggestion(
                suggestion_id=f"test{i}",
                suggestion_type=SuggestionType.MOVE,
                file_path=Path(f"test{i}.jpg"),
                target_path=Path("images") / f"test{i}.jpg",
                confidence=70.0,
                reasoning="Test",
            )
            feedback.record_action(suggestion, "accepted")

        history = feedback.get_user_history()
        assert "move_history" in history
        assert ".jpg" in history["move_history"]

    def test_persistence(self, temp_feedback_file):
        """Test feedback persistence."""
        feedback1 = SuggestionFeedback(feedback_file=temp_feedback_file)
        suggestion = Suggestion(
            suggestion_id="test",
            suggestion_type=SuggestionType.MOVE,
            file_path=Path("test.jpg"),
            confidence=70.0,
            reasoning="Test",
        )
        feedback1.record_action(suggestion, "accepted")

        feedback2 = SuggestionFeedback(feedback_file=temp_feedback_file)
        assert len(feedback2.feedback_entries) == 1
        assert feedback2.feedback_entries[0].suggestion_id == "test"

    def test_clear_old_feedback(self, temp_feedback_file):
        """Test clearing old feedback."""
        feedback = SuggestionFeedback(feedback_file=temp_feedback_file)
        for i in range(5):
            suggestion = Suggestion(
                suggestion_id=f"test{i}",
                suggestion_type=SuggestionType.MOVE,
                file_path=Path(f"test{i}.jpg"),
                confidence=70.0,
                reasoning="Test",
            )
            feedback.record_action(suggestion, "accepted")

        initial_count = len(feedback.feedback_entries)
        removed = feedback.clear_old_feedback(days=90)
        assert removed == 0
        assert len(feedback.feedback_entries) == initial_count


# ---------------------------------------------------------------------------
# End-to-end integration
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestSmartSuggestionsIntegration:
    """End-to-end integration tests for the smart suggestions system."""

    @pytest.fixture
    def complete_structure(self, tmp_path):
        """Create complete file structure for integration tests."""
        docs = tmp_path / "documents"
        docs.mkdir()
        for i in range(5):
            (docs / f"report_{i:03d}.pdf").touch()

        images = tmp_path / "photos"
        images.mkdir()
        for i in range(5):
            (images / f"IMG_{i:04d}.jpg").touch()

        (tmp_path / "random_photo.jpg").touch()
        (tmp_path / "lost_document.pdf").touch()
        return tmp_path

    def test_end_to_end_workflow(self, complete_structure, tmp_path):
        """Test complete workflow from analysis to suggestions."""
        analyzer = PatternAnalyzer(min_pattern_count=2)
        analysis = analyzer.analyze_directory(complete_structure)

        assert analysis.total_files == 12
        assert len(analysis.naming_patterns) > 0

        engine = SuggestionEngine(min_confidence=30.0)
        misplaced_files = [
            complete_structure / "random_photo.jpg",
            complete_structure / "lost_document.pdf",
        ]
        suggestions = engine.generate_suggestions(misplaced_files, pattern_analysis=analysis)
        assert len(suggestions) > 0

        detector = MisplacementDetector(min_mismatch_score=40.0)
        misplaced = detector.detect_misplaced(complete_structure, pattern_analysis=analysis)
        assert len(misplaced) >= 1

        feedback = SuggestionFeedback(feedback_file=tmp_path / "feedback.json")
        if suggestions:
            feedback.record_action(suggestions[0], "accepted")
        stats = feedback.get_learning_stats()
        assert stats.total_suggestions >= 1

    @pytest.mark.slow
    def test_performance(self, tmp_path):
        """Test performance on larger dataset."""
        for i in range(100):
            category = ["docs", "images", "code"][i % 3]
            cat_dir = tmp_path / category
            cat_dir.mkdir(exist_ok=True)
            ext = {"docs": ".pdf", "images": ".jpg", "code": ".py"}[category]
            (cat_dir / f"file_{i:04d}{ext}").touch()

        start = time.time()
        analyzer = PatternAnalyzer()
        analysis = analyzer.analyze_directory(tmp_path)
        elapsed = time.time() - start

        assert elapsed < 5.0
        assert analysis.total_files == 100
