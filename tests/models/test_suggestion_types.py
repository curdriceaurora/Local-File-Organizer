"""Tests for suggestion types: Suggestion, SuggestionBatch, ConfidenceFactors models."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from file_organizer.models.suggestion_types import (
    ConfidenceFactors,
    ConfidenceLevel,
    Suggestion,
    SuggestionBatch,
    SuggestionType,
)


@pytest.mark.unit
class TestSuggestionType:
    """Tests for SuggestionType enum."""

    def test_enum_values(self) -> None:
        """Test all SuggestionType enum members."""
        assert SuggestionType.MOVE.value == "move"
        assert SuggestionType.RENAME.value == "rename"
        assert SuggestionType.TAG.value == "tag"
        assert SuggestionType.RESTRUCTURE.value == "restructure"
        assert SuggestionType.DELETE.value == "delete"
        assert SuggestionType.MERGE.value == "merge"

    def test_enum_count(self) -> None:
        """Test correct number of suggestion types."""
        assert len(SuggestionType) == 6

    def test_from_value(self) -> None:
        """Test constructing enum from string value."""
        assert SuggestionType("move") == SuggestionType.MOVE
        assert SuggestionType("rename") == SuggestionType.RENAME
        assert SuggestionType("tag") == SuggestionType.TAG

    def test_invalid_value(self) -> None:
        """Test invalid enum value raises ValueError."""
        with pytest.raises(ValueError):
            SuggestionType("invalid")


@pytest.mark.unit
class TestConfidenceLevel:
    """Tests for ConfidenceLevel enum."""

    def test_enum_values(self) -> None:
        """Test all ConfidenceLevel enum members."""
        assert ConfidenceLevel.VERY_LOW.value == "very_low"
        assert ConfidenceLevel.LOW.value == "low"
        assert ConfidenceLevel.MEDIUM.value == "medium"
        assert ConfidenceLevel.HIGH.value == "high"
        assert ConfidenceLevel.VERY_HIGH.value == "very_high"

    def test_enum_count(self) -> None:
        """Test correct number of confidence levels."""
        assert len(ConfidenceLevel) == 5


@pytest.mark.unit
class TestSuggestion:
    """Tests for Suggestion dataclass."""

    def test_create_basic_suggestion(self) -> None:
        """Test creating a basic suggestion."""
        suggestion = Suggestion(
            suggestion_id="sugg-001",
            suggestion_type=SuggestionType.MOVE,
            file_path=Path("/home/user/file.txt"),
        )

        assert suggestion.suggestion_id == "sugg-001"
        assert suggestion.suggestion_type == SuggestionType.MOVE
        assert suggestion.file_path == Path("/home/user/file.txt")
        assert suggestion.target_path is None
        assert suggestion.confidence == 0.0

    def test_create_suggestion_with_target(self) -> None:
        """Test creating suggestion with target path."""
        suggestion = Suggestion(
            suggestion_id="sugg-002",
            suggestion_type=SuggestionType.MOVE,
            file_path=Path("/home/user/file.txt"),
            target_path=Path("/home/user/Documents/file.txt"),
            confidence=85.5,
        )

        assert suggestion.target_path == Path("/home/user/Documents/file.txt")
        assert suggestion.confidence == 85.5

    def test_confidence_level_very_high(self) -> None:
        """Test confidence level for very high confidence."""
        suggestion = Suggestion(
            suggestion_id="s1",
            suggestion_type=SuggestionType.MOVE,
            file_path=Path("file.txt"),
            confidence=95.0,
        )
        assert suggestion.confidence_level == ConfidenceLevel.VERY_HIGH

    def test_confidence_level_high(self) -> None:
        """Test confidence level for high confidence."""
        suggestion = Suggestion(
            suggestion_id="s1",
            suggestion_type=SuggestionType.MOVE,
            file_path=Path("file.txt"),
            confidence=70.0,
        )
        assert suggestion.confidence_level == ConfidenceLevel.HIGH

    def test_confidence_level_medium(self) -> None:
        """Test confidence level for medium confidence."""
        suggestion = Suggestion(
            suggestion_id="s1",
            suggestion_type=SuggestionType.MOVE,
            file_path=Path("file.txt"),
            confidence=50.0,
        )
        assert suggestion.confidence_level == ConfidenceLevel.MEDIUM

    def test_confidence_level_low(self) -> None:
        """Test confidence level for low confidence."""
        suggestion = Suggestion(
            suggestion_id="s1",
            suggestion_type=SuggestionType.MOVE,
            file_path=Path("file.txt"),
            confidence=30.0,
        )
        assert suggestion.confidence_level == ConfidenceLevel.LOW

    def test_confidence_level_very_low(self) -> None:
        """Test confidence level for very low confidence."""
        suggestion = Suggestion(
            suggestion_id="s1",
            suggestion_type=SuggestionType.MOVE,
            file_path=Path("file.txt"),
            confidence=10.0,
        )
        assert suggestion.confidence_level == ConfidenceLevel.VERY_LOW

    def test_confidence_level_boundary_80(self) -> None:
        """Test confidence level at 80% boundary."""
        suggestion = Suggestion(
            suggestion_id="s1",
            suggestion_type=SuggestionType.MOVE,
            file_path=Path("file.txt"),
            confidence=80.0,
        )
        assert suggestion.confidence_level == ConfidenceLevel.VERY_HIGH

    def test_suggestion_with_reasoning(self) -> None:
        """Test suggestion with reasoning."""
        suggestion = Suggestion(
            suggestion_id="s1",
            suggestion_type=SuggestionType.MOVE,
            file_path=Path("file.txt"),
            reasoning="File name matches pattern of documents directory",
        )
        assert suggestion.reasoning == "File name matches pattern of documents directory"

    def test_suggestion_with_metadata(self) -> None:
        """Test suggestion with metadata."""
        metadata = {"source": "pattern_analyzer", "rule_id": "doc-001"}
        suggestion = Suggestion(
            suggestion_id="s1",
            suggestion_type=SuggestionType.MOVE,
            file_path=Path("file.txt"),
            metadata=metadata,
        )
        assert suggestion.metadata == metadata
        assert suggestion.metadata["source"] == "pattern_analyzer"

    def test_suggestion_with_tags(self) -> None:
        """Test suggestion with tags."""
        suggestion = Suggestion(
            suggestion_id="s1",
            suggestion_type=SuggestionType.TAG,
            file_path=Path("file.txt"),
            tags=["important", "work", "2024"],
        )
        assert suggestion.tags == ["important", "work", "2024"]

    def test_suggestion_rename(self) -> None:
        """Test rename suggestion."""
        suggestion = Suggestion(
            suggestion_id="s1",
            suggestion_type=SuggestionType.RENAME,
            file_path=Path("old_name.txt"),
            new_name="new_name_2024.txt",
            confidence=75.0,
        )
        assert suggestion.suggestion_type == SuggestionType.RENAME
        assert suggestion.new_name == "new_name_2024.txt"

    def test_suggestion_with_related_files(self) -> None:
        """Test suggestion with related files."""
        related = [Path("file1.txt"), Path("file2.txt")]
        suggestion = Suggestion(
            suggestion_id="s1",
            suggestion_type=SuggestionType.MERGE,
            file_path=Path("file.txt"),
            related_files=related,
        )
        assert suggestion.related_files == related

    def test_suggestion_created_at(self) -> None:
        """Test that created_at timestamp is set."""
        suggestion = Suggestion(
            suggestion_id="s1",
            suggestion_type=SuggestionType.MOVE,
            file_path=Path("file.txt"),
        )
        assert suggestion.created_at is not None
        assert isinstance(suggestion.created_at, datetime)

    def test_suggestion_to_dict(self) -> None:
        """Test converting suggestion to dictionary."""
        suggestion = Suggestion(
            suggestion_id="sugg-001",
            suggestion_type=SuggestionType.MOVE,
            file_path=Path("/home/user/file.txt"),
            target_path=Path("/home/user/Documents/file.txt"),
            confidence=85.5,
            reasoning="File matches document pattern",
            tags=["doc", "important"],
            new_name="renamed_file.txt",
        )

        data = suggestion.to_dict()

        assert data["suggestion_id"] == "sugg-001"
        assert data["suggestion_type"] == "move"
        assert data["file_path"] == "/home/user/file.txt"
        assert data["target_path"] == "/home/user/Documents/file.txt"
        assert data["confidence"] == 85.5
        assert data["confidence_level"] == "very_high"
        assert data["reasoning"] == "File matches document pattern"
        assert data["tags"] == ["doc", "important"]
        assert data["new_name"] == "renamed_file.txt"

    def test_suggestion_to_dict_empty_target(self) -> None:
        """Test to_dict with None target_path."""
        suggestion = Suggestion(
            suggestion_id="s1",
            suggestion_type=SuggestionType.DELETE,
            file_path=Path("file.txt"),
        )
        data = suggestion.to_dict()
        assert data["target_path"] is None


@pytest.mark.unit
class TestSuggestionBatch:
    """Tests for SuggestionBatch dataclass."""

    @pytest.fixture
    def sample_suggestions(self) -> list[Suggestion]:
        """Create sample suggestions for testing."""
        return [
            Suggestion(
                suggestion_id="s1",
                suggestion_type=SuggestionType.MOVE,
                file_path=Path("file1.txt"),
                confidence=85.0,
            ),
            Suggestion(
                suggestion_id="s2",
                suggestion_type=SuggestionType.MOVE,
                file_path=Path("file2.txt"),
                confidence=75.0,
            ),
            Suggestion(
                suggestion_id="s3",
                suggestion_type=SuggestionType.MOVE,
                file_path=Path("file3.txt"),
                confidence=95.0,
            ),
        ]

    def test_create_batch(self, sample_suggestions: list[Suggestion]) -> None:
        """Test creating a suggestion batch."""
        batch = SuggestionBatch(
            batch_id="batch-001",
            suggestions=sample_suggestions,
            category="documents",
            description="Move PDF files to Documents folder",
        )

        assert batch.batch_id == "batch-001"
        assert len(batch.suggestions) == 3
        assert batch.category == "documents"

    def test_batch_avg_confidence(
        self, sample_suggestions: list[Suggestion]
    ) -> None:
        """Test average confidence calculation."""
        batch = SuggestionBatch(
            batch_id="b1",
            suggestions=sample_suggestions,
            category="docs",
            description="Test batch",
        )
        expected_avg = (85.0 + 75.0 + 95.0) / 3
        assert batch.avg_confidence == expected_avg

    def test_batch_avg_confidence_empty(self) -> None:
        """Test average confidence with empty suggestions."""
        batch = SuggestionBatch(
            batch_id="b1",
            suggestions=[],
            category="empty",
            description="Empty batch",
        )
        assert batch.avg_confidence == 0.0

    def test_batch_total_suggestions(
        self, sample_suggestions: list[Suggestion]
    ) -> None:
        """Test total suggestions count."""
        batch = SuggestionBatch(
            batch_id="b1",
            suggestions=sample_suggestions,
            category="docs",
            description="Test",
        )
        assert batch.total_suggestions == 3

    def test_batch_created_at(self, sample_suggestions: list[Suggestion]) -> None:
        """Test that created_at timestamp is set."""
        batch = SuggestionBatch(
            batch_id="b1",
            suggestions=sample_suggestions,
            category="docs",
            description="Test",
        )
        assert batch.created_at is not None
        assert isinstance(batch.created_at, datetime)

    def test_batch_to_dict(self, sample_suggestions: list[Suggestion]) -> None:
        """Test converting batch to dictionary."""
        batch = SuggestionBatch(
            batch_id="batch-001",
            suggestions=sample_suggestions,
            category="documents",
            description="Move PDF files to Documents",
        )

        data = batch.to_dict()

        assert data["batch_id"] == "batch-001"
        assert data["category"] == "documents"
        assert data["description"] == "Move PDF files to Documents"
        assert data["total_suggestions"] == 3
        assert len(data["suggestions"]) == 3
        assert "avg_confidence" in data
        assert "created_at" in data


@pytest.mark.unit
class TestConfidenceFactors:
    """Tests for ConfidenceFactors dataclass."""

    def test_create_confidence_factors(self) -> None:
        """Test creating confidence factors."""
        factors = ConfidenceFactors(
            pattern_strength=80.0,
            content_similarity=75.0,
            user_history=70.0,
            naming_convention=85.0,
            file_type_match=90.0,
            recency=60.0,
            size_appropriateness=50.0,
        )

        assert factors.pattern_strength == 80.0
        assert factors.content_similarity == 75.0

    def test_default_weights(self) -> None:
        """Test default weights sum to 1.0."""
        factors = ConfidenceFactors()
        total_weight = sum(factors.weights.values())
        assert abs(total_weight - 1.0) < 0.001

    def test_calculate_weighted_score(self) -> None:
        """Test weighted score calculation."""
        factors = ConfidenceFactors(
            pattern_strength=100.0,
            content_similarity=100.0,
            user_history=100.0,
            naming_convention=100.0,
            file_type_match=100.0,
            recency=100.0,
            size_appropriateness=100.0,
        )
        score = factors.calculate_weighted_score()
        assert score == 100.0

    def test_calculate_weighted_score_all_zero(self) -> None:
        """Test weighted score with all zero factors."""
        factors = ConfidenceFactors(
            pattern_strength=0.0,
            content_similarity=0.0,
            user_history=0.0,
            naming_convention=0.0,
            file_type_match=0.0,
            recency=0.0,
            size_appropriateness=0.0,
        )
        score = factors.calculate_weighted_score()
        assert score == 0.0

    def test_calculate_weighted_score_partial(self) -> None:
        """Test weighted score with partial factors."""
        factors = ConfidenceFactors(
            pattern_strength=100.0,  # weight 0.25
            content_similarity=0.0,  # weight 0.20
            user_history=0.0,  # weight 0.15
            naming_convention=0.0,  # weight 0.15
            file_type_match=0.0,  # weight 0.15
            recency=0.0,  # weight 0.05
            size_appropriateness=0.0,  # weight 0.05
        )
        score = factors.calculate_weighted_score()
        expected = 100.0 * 0.25
        assert abs(score - expected) < 0.001

    def test_weighted_score_clamping_max(self) -> None:
        """Test that weighted score is clamped to max 100."""
        factors = ConfidenceFactors()
        # Set all to 150 (beyond 100)
        factors.pattern_strength = 150.0
        factors.content_similarity = 150.0
        factors.user_history = 150.0
        factors.naming_convention = 150.0
        factors.file_type_match = 150.0
        factors.recency = 150.0
        factors.size_appropriateness = 150.0

        score = factors.calculate_weighted_score()
        assert score == 100.0

    def test_weighted_score_clamping_min(self) -> None:
        """Test that weighted score is clamped to min 0."""
        factors = ConfidenceFactors()
        # Set all to -50 (below 0)
        factors.pattern_strength = -50.0
        factors.content_similarity = -50.0
        factors.user_history = -50.0
        factors.naming_convention = -50.0
        factors.file_type_match = -50.0
        factors.recency = -50.0
        factors.size_appropriateness = -50.0

        score = factors.calculate_weighted_score()
        assert score == 0.0

    def test_factors_to_dict(self) -> None:
        """Test converting factors to dictionary."""
        factors = ConfidenceFactors(
            pattern_strength=80.0,
            content_similarity=75.0,
            user_history=70.0,
            naming_convention=85.0,
            file_type_match=90.0,
            recency=60.0,
            size_appropriateness=50.0,
        )

        data = factors.to_dict()

        assert data["pattern_strength"] == 80.0
        assert data["content_similarity"] == 75.0
        assert "weighted_score" in data
        assert "weights" in data
        assert isinstance(data["weighted_score"], float)

    def test_factors_with_custom_weights(self) -> None:
        """Test confidence factors with custom weights."""
        custom_weights = {
            "pattern_strength": 0.5,
            "content_similarity": 0.3,
            "user_history": 0.1,
            "naming_convention": 0.05,
            "file_type_match": 0.03,
            "recency": 0.01,
            "size_appropriateness": 0.01,
        }
        factors = ConfidenceFactors(
            pattern_strength=100.0,
            weights=custom_weights,
        )

        score = factors.calculate_weighted_score()
        expected = 100.0 * 0.5
        assert abs(score - expected) < 0.001
