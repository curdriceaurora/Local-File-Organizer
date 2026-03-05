"""Coverage tests for file_organizer.models.suggestion_types — uncovered branches."""

from __future__ import annotations

from pathlib import Path

import pytest

from file_organizer.models.suggestion_types import (
    ConfidenceFactors,
    ConfidenceLevel,
    Suggestion,
    SuggestionBatch,
    SuggestionType,
)

pytestmark = pytest.mark.unit


class TestSuggestionConfidenceLevel:
    """Covers all confidence_level property branches."""

    def test_very_high(self) -> None:
        s = Suggestion(
            suggestion_id="s1",
            suggestion_type=SuggestionType.MOVE,
            file_path=Path("a.txt"),
            confidence=95.0,
        )
        assert s.confidence_level == ConfidenceLevel.VERY_HIGH

    def test_high(self) -> None:
        s = Suggestion(
            suggestion_id="s2",
            suggestion_type=SuggestionType.MOVE,
            file_path=Path("a.txt"),
            confidence=70.0,
        )
        assert s.confidence_level == ConfidenceLevel.HIGH

    def test_medium(self) -> None:
        s = Suggestion(
            suggestion_id="s3",
            suggestion_type=SuggestionType.MOVE,
            file_path=Path("a.txt"),
            confidence=50.0,
        )
        assert s.confidence_level == ConfidenceLevel.MEDIUM

    def test_low(self) -> None:
        s = Suggestion(
            suggestion_id="s4",
            suggestion_type=SuggestionType.MOVE,
            file_path=Path("a.txt"),
            confidence=30.0,
        )
        assert s.confidence_level == ConfidenceLevel.LOW

    def test_very_low(self) -> None:
        s = Suggestion(
            suggestion_id="s5",
            suggestion_type=SuggestionType.MOVE,
            file_path=Path("a.txt"),
            confidence=10.0,
        )
        assert s.confidence_level == ConfidenceLevel.VERY_LOW


class TestSuggestionToDict:
    """Covers to_dict method with all fields."""

    def test_to_dict_with_target(self) -> None:
        s = Suggestion(
            suggestion_id="s1",
            suggestion_type=SuggestionType.RENAME,
            file_path=Path("a.txt"),
            target_path=Path("b.txt"),
            confidence=60.0,
            reasoning="test reason",
            tags=["doc"],
            new_name="b.txt",
            related_files=[Path("c.txt")],
        )
        d = s.to_dict()
        assert d["suggestion_type"] == "rename"
        assert d["target_path"] == "b.txt"
        assert d["new_name"] == "b.txt"
        assert d["related_files"] == ["c.txt"]

    def test_to_dict_without_target(self) -> None:
        s = Suggestion(
            suggestion_id="s2",
            suggestion_type=SuggestionType.TAG,
            file_path=Path("a.txt"),
        )
        d = s.to_dict()
        assert d["target_path"] is None


class TestSuggestionBatch:
    """Covers SuggestionBatch properties and to_dict."""

    def test_empty_batch(self) -> None:
        batch = SuggestionBatch(
            batch_id="b1",
            suggestions=[],
            category="test",
            description="empty batch",
        )
        assert batch.avg_confidence == 0.0
        assert batch.total_suggestions == 0

    def test_batch_with_suggestions(self) -> None:
        s1 = Suggestion(
            suggestion_id="s1",
            suggestion_type=SuggestionType.MOVE,
            file_path=Path("a.txt"),
            confidence=80.0,
        )
        s2 = Suggestion(
            suggestion_id="s2",
            suggestion_type=SuggestionType.MOVE,
            file_path=Path("b.txt"),
            confidence=60.0,
        )
        batch = SuggestionBatch(
            batch_id="b2",
            suggestions=[s1, s2],
            category="test",
            description="two suggestions",
        )
        assert batch.avg_confidence == 70.0
        assert batch.total_suggestions == 2

    def test_batch_to_dict(self) -> None:
        batch = SuggestionBatch(
            batch_id="b3",
            suggestions=[],
            category="test",
            description="empty",
        )
        d = batch.to_dict()
        assert d["batch_id"] == "b3"
        assert "avg_confidence" in d
        assert "total_suggestions" in d


class TestConfidenceFactors:
    """Covers weighted score and to_dict."""

    def test_calculate_weighted_score(self) -> None:
        cf = ConfidenceFactors(
            pattern_strength=80.0,
            content_similarity=60.0,
            user_history=40.0,
            naming_convention=50.0,
            file_type_match=70.0,
            recency=30.0,
            size_appropriateness=20.0,
        )
        score = cf.calculate_weighted_score()
        assert 0.0 <= score <= 100.0

    def test_calculate_weighted_score_clamped_high(self) -> None:
        cf = ConfidenceFactors(
            pattern_strength=200.0,
            content_similarity=200.0,
            user_history=200.0,
            naming_convention=200.0,
            file_type_match=200.0,
            recency=200.0,
            size_appropriateness=200.0,
        )
        score = cf.calculate_weighted_score()
        assert score == 100.0

    def test_to_dict(self) -> None:
        cf = ConfidenceFactors()
        d = cf.to_dict()
        assert "weighted_score" in d
        assert "weights" in d
