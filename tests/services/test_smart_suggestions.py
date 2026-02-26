"""Tests for file_organizer.services.smart_suggestions module.

Covers ConfidenceScorer and SuggestionEngine classes, hitting the
missed lines including user history, naming convention, file type match,
recency, size scoring, move reasoning, and common root calculation.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pytest

from file_organizer.models.suggestion_types import (
    ConfidenceFactors,
    Suggestion,
    SuggestionType,
)
from file_organizer.services.smart_suggestions import (
    ConfidenceScorer,
    SuggestionEngine,
)

pytestmark = [pytest.mark.unit]


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
    file_paths: list[Path] = field(
        default_factory=lambda: [Path(f"/f{i}.txt") for i in range(6)]
    )
    common_keywords: list[str] = field(
        default_factory=lambda: ["report", "quarterly", "finance"]
    )
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
    analyzed_at: datetime = field(default_factory=datetime.now)
    total_files: int = 20
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# ConfidenceScorer
# ---------------------------------------------------------------------------


class TestConfidenceScorerUserHistory:
    """Test _calculate_user_history_score."""

    def test_no_target_returns_50(self):
        scorer = ConfidenceScorer()
        result = scorer._calculate_user_history_score(
            Path("/a.txt"), None, {"move_history": {}}
        )
        assert result == 50.0

    def test_target_with_history(self, tmp_path):
        scorer = ConfidenceScorer()
        target = tmp_path / "dest"
        target.mkdir()
        history = {
            "move_history": {
                ".txt": {str(target): 3}
            }
        }
        result = scorer._calculate_user_history_score(
            tmp_path / "a.txt", target / "a.txt", history
        )
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
        result = scorer._calculate_user_history_score(
            tmp_path / "a.txt", target / "a.txt", history
        )
        assert result == 100.0


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
        result = scorer._calculate_naming_match(
            Path("/a.txt"), Path("/dest/a.txt"), analysis
        )
        assert result == 40.0

    def test_with_naming_patterns(self, tmp_path):
        scorer = ConfidenceScorer()
        target = tmp_path / "docs"
        target.mkdir()
        analysis = FakePatternAnalysis(
            location_patterns=[
                FakeLocationPattern(directory=target, naming_patterns=["report_*"])
            ]
        )
        result = scorer._calculate_naming_match(
            tmp_path / "a.txt", target / "a.txt", analysis
        )
        assert result == 70.0


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
        result = scorer._calculate_file_type_match(
            Path("/a.txt"), Path("/dest/a.txt"), analysis
        )
        assert result == 40.0

    def test_matching_type(self, tmp_path):
        scorer = ConfidenceScorer()
        target = tmp_path / "docs"
        target.mkdir()
        analysis = FakePatternAnalysis(
            location_patterns=[
                FakeLocationPattern(directory=target, file_types={".txt", ".pdf"})
            ]
        )
        result = scorer._calculate_file_type_match(
            tmp_path / "a.txt", target / "a.txt", analysis
        )
        assert result == 85.0

    def test_empty_target_types(self, tmp_path):
        scorer = ConfidenceScorer()
        target = tmp_path / "docs"
        target.mkdir()
        analysis = FakePatternAnalysis(
            location_patterns=[
                FakeLocationPattern(directory=target, file_types=set())
            ]
        )
        result = scorer._calculate_file_type_match(
            tmp_path / "a.txt", target / "a.txt", analysis
        )
        assert result == 50.0

    def test_non_matching_type(self, tmp_path):
        scorer = ConfidenceScorer()
        target = tmp_path / "docs"
        target.mkdir()
        analysis = FakePatternAnalysis(
            location_patterns=[
                FakeLocationPattern(directory=target, file_types={".pdf"})
            ]
        )
        result = scorer._calculate_file_type_match(
            tmp_path / "a.txt", target / "a.txt", analysis
        )
        assert result == 25.0


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
        result = scorer._calculate_size_score(
            tmp_path / "nope.txt", tmp_path / "also_nope"
        )
        assert result == 50.0


# ---------------------------------------------------------------------------
# SuggestionEngine
# ---------------------------------------------------------------------------


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


class TestSuggestionEngineMoveReasoning:
    """Test _generate_move_reasoning."""

    def test_high_pattern_strength(self):
        engine = SuggestionEngine()
        factors = ConfidenceFactors(pattern_strength=80.0)
        result = engine._generate_move_reasoning(
            Path("/a.txt"), Path("/dest"), factors
        )
        assert "pattern" in result

    def test_high_file_type_match(self):
        engine = SuggestionEngine()
        factors = ConfidenceFactors(file_type_match=80.0)
        result = engine._generate_move_reasoning(
            Path("/a.txt"), Path("/dest"), factors
        )
        assert "file type" in result

    def test_high_content_similarity(self):
        engine = SuggestionEngine()
        factors = ConfidenceFactors(content_similarity=80.0)
        result = engine._generate_move_reasoning(
            Path("/a.txt"), Path("/dest"), factors
        )
        assert "similar files" in result

    def test_high_user_history(self):
        engine = SuggestionEngine()
        factors = ConfidenceFactors(user_history=80.0)
        result = engine._generate_move_reasoning(
            Path("/a.txt"), Path("/dest"), factors
        )
        assert "moved similar" in result

    def test_no_reasons_fallback(self):
        engine = SuggestionEngine()
        factors = ConfidenceFactors()
        result = engine._generate_move_reasoning(
            Path("/a.txt"), Path("/dest"), factors
        )
        assert "improve organization" in result


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
                FakeLocationPattern(
                    directory=target, file_types={".txt"}, file_count=10
                )
            ]
        )
        result = engine._find_best_location(tmp_path / "sub" / "a.txt", analysis)
        assert result == target


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
