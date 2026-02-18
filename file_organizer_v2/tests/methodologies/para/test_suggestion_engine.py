"""Tests for PARA AI Suggestion Engine.

Tests cover suggestion generation, batch processing, confidence levels,
explanation formatting, and integration with heuristics. All tests use
mocks for the heuristic engine to avoid filesystem dependencies.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from file_organizer.methodologies.para.ai.suggestion_engine import (
    PARASuggestion,
    PARASuggestionEngine,
    _confidence_label,
)
from file_organizer.methodologies.para.categories import PARACategory
from file_organizer.methodologies.para.config import PARAConfig
from file_organizer.methodologies.para.detection.heuristics import (
    CategoryScore,
    HeuristicEngine,
    HeuristicResult,
)


def _make_heuristic_result(
    top_category: PARACategory = PARACategory.PROJECT,
    top_score: float = 0.5,
    signals: list[str] | None = None,
) -> HeuristicResult:
    """Create a HeuristicResult with the given top category favored."""
    scores = {cat: CategoryScore(cat, 0.1, 0.3) for cat in PARACategory}
    scores[top_category] = CategoryScore(
        top_category,
        top_score,
        top_score,
        signals=signals or ["test_signal"],
    )
    return HeuristicResult(
        scores=scores,
        overall_confidence=top_score,
        recommended_category=top_category,
        needs_manual_review=top_score < 0.6,
    )


@pytest.fixture
def config() -> PARAConfig:
    """Create a default PARAConfig."""
    return PARAConfig()


@pytest.fixture
def mock_heuristic_engine() -> MagicMock:
    """Create a mock HeuristicEngine."""
    engine = MagicMock(spec=HeuristicEngine)
    engine.evaluate.return_value = _make_heuristic_result()
    return engine


@pytest.fixture
def suggestion_engine(config: PARAConfig, mock_heuristic_engine: MagicMock) -> PARASuggestionEngine:
    """Create a PARASuggestionEngine with mocked heuristics."""
    return PARASuggestionEngine(
        config=config,
        heuristic_engine=mock_heuristic_engine,
    )


# =========================================================================
# PARASuggestion dataclass tests
# =========================================================================


class TestPARASuggestion:
    """Tests for the PARASuggestion dataclass."""

    def test_valid_suggestion_creation(self) -> None:
        """Should create a valid suggestion."""
        suggestion = PARASuggestion(
            category=PARACategory.PROJECT,
            confidence=0.85,
            reasoning=["Test reason"],
        )
        assert suggestion.category == PARACategory.PROJECT
        assert suggestion.confidence == 0.85

    def test_invalid_confidence_raises(self) -> None:
        """Should raise ValueError for out-of-range confidence."""
        with pytest.raises(ValueError, match="confidence"):
            PARASuggestion(category=PARACategory.PROJECT, confidence=1.5)

    def test_negative_confidence_raises(self) -> None:
        """Should raise ValueError for negative confidence."""
        with pytest.raises(ValueError, match="confidence"):
            PARASuggestion(category=PARACategory.PROJECT, confidence=-0.1)

    def test_is_confident_high(self) -> None:
        """High confidence should be detected."""
        suggestion = PARASuggestion(category=PARACategory.PROJECT, confidence=0.90)
        assert suggestion.is_confident is True

    def test_is_confident_low(self) -> None:
        """Low confidence should not be detected as confident."""
        suggestion = PARASuggestion(category=PARACategory.PROJECT, confidence=0.50)
        assert suggestion.is_confident is False

    def test_requires_review_low_confidence(self) -> None:
        """Low confidence suggestions should require review."""
        suggestion = PARASuggestion(category=PARACategory.PROJECT, confidence=0.30)
        assert suggestion.requires_review is True

    def test_no_review_high_confidence(self) -> None:
        """High confidence suggestions should not require review."""
        suggestion = PARASuggestion(category=PARACategory.PROJECT, confidence=0.90)
        assert suggestion.requires_review is False

    def test_confidence_label_high(self) -> None:
        """Should return 'High' label for high confidence."""
        suggestion = PARASuggestion(category=PARACategory.PROJECT, confidence=0.90)
        assert suggestion.confidence_label == "High"

    def test_confidence_label_medium(self) -> None:
        """Should return 'Medium' label for medium confidence."""
        suggestion = PARASuggestion(category=PARACategory.PROJECT, confidence=0.70)
        assert suggestion.confidence_label == "Medium"

    def test_confidence_label_low(self) -> None:
        """Should return 'Low' label for low confidence."""
        suggestion = PARASuggestion(category=PARACategory.PROJECT, confidence=0.45)
        assert suggestion.confidence_label == "Low"

    def test_confidence_label_very_low(self) -> None:
        """Should return 'Very Low' label for very low confidence."""
        suggestion = PARASuggestion(category=PARACategory.PROJECT, confidence=0.20)
        assert suggestion.confidence_label == "Very Low"


# =========================================================================
# Confidence label helper
# =========================================================================


class TestConfidenceLabel:
    """Tests for the _confidence_label helper function."""

    def test_high_boundary(self) -> None:
        assert _confidence_label(0.85) == "High"
        assert _confidence_label(1.0) == "High"

    def test_medium_boundary(self) -> None:
        assert _confidence_label(0.60) == "Medium"
        assert _confidence_label(0.84) == "Medium"

    def test_low_boundary(self) -> None:
        assert _confidence_label(0.40) == "Low"
        assert _confidence_label(0.59) == "Low"

    def test_very_low_boundary(self) -> None:
        assert _confidence_label(0.39) == "Very Low"
        assert _confidence_label(0.0) == "Very Low"


# =========================================================================
# suggest() method tests
# =========================================================================


class TestSuggest:
    """Tests for the suggest method."""

    def test_returns_para_suggestion(
        self,
        suggestion_engine: PARASuggestionEngine,
        tmp_path: Path,
    ) -> None:
        """suggest() should return a PARASuggestion."""
        f = tmp_path / "test.txt"
        f.write_text("content")
        result = suggestion_engine.suggest(f)
        assert isinstance(result, PARASuggestion)
        assert result.category in PARACategory
        assert 0.0 <= result.confidence <= 1.0

    def test_suggestion_has_reasoning(
        self,
        suggestion_engine: PARASuggestionEngine,
        tmp_path: Path,
    ) -> None:
        """Suggestions should include at least one reasoning string."""
        f = tmp_path / "project_plan.txt"
        f.write_text("project plan with deadline")
        result = suggestion_engine.suggest(f)
        assert len(result.reasoning) >= 1

    def test_content_influences_suggestion(
        self,
        suggestion_engine: PARASuggestionEngine,
        tmp_path: Path,
    ) -> None:
        """Providing content should add content-based signals."""
        f = tmp_path / "file.txt"
        f.write_text("")
        # Content with many project keywords
        content = "deadline milestone sprint deliverable project plan goal completion"
        result = suggestion_engine.suggest(f, content=content)
        # Project keywords should boost project score
        project_score = result.metadata.get("feature_scores", {}).get("project", 0)
        assert project_score > 0

    def test_suggestion_has_metadata(
        self,
        suggestion_engine: PARASuggestionEngine,
        tmp_path: Path,
    ) -> None:
        """Suggestion metadata should contain score breakdowns."""
        f = tmp_path / "doc.txt"
        f.write_text("content")
        result = suggestion_engine.suggest(f)
        assert "heuristic_scores" in result.metadata
        assert "feature_scores" in result.metadata
        assert "combined_scores" in result.metadata

    def test_alternatives_are_ranked(
        self,
        suggestion_engine: PARASuggestionEngine,
        tmp_path: Path,
    ) -> None:
        """Alternative categories should be ranked by score (descending)."""
        f = tmp_path / "file.txt"
        f.write_text("content")
        result = suggestion_engine.suggest(f)
        if len(result.alternative_categories) > 1:
            scores = [s for _, s in result.alternative_categories]
            assert scores == sorted(scores, reverse=True)

    def test_tags_generated(
        self,
        suggestion_engine: PARASuggestionEngine,
        tmp_path: Path,
    ) -> None:
        """Tags should include file extension."""
        f = tmp_path / "report.pdf"
        f.write_bytes(b"fake pdf")
        result = suggestion_engine.suggest(f)
        assert "pdf" in result.tags

    def test_heuristic_failure_handled(
        self,
        config: PARAConfig,
        tmp_path: Path,
    ) -> None:
        """Should handle heuristic engine failure gracefully."""
        mock_engine = MagicMock(spec=HeuristicEngine)
        mock_engine.evaluate.side_effect = RuntimeError("heuristic crash")
        engine = PARASuggestionEngine(config=config, heuristic_engine=mock_engine)
        f = tmp_path / "file.txt"
        f.write_text("content")
        result = engine.suggest(f)
        assert isinstance(result, PARASuggestion)
        assert result.confidence >= 0.0

    def test_nonexistent_file_handled(
        self,
        suggestion_engine: PARASuggestionEngine,
    ) -> None:
        """Should handle non-existent file paths gracefully."""
        result = suggestion_engine.suggest(Path("/nonexistent/path/file.txt"))
        assert isinstance(result, PARASuggestion)

    def test_structural_hint_influences_category(
        self,
        config: PARAConfig,
        tmp_path: Path,
    ) -> None:
        """Parent directory named 'archive' should boost ARCHIVE score."""
        mock_engine = MagicMock(spec=HeuristicEngine)
        # Return equal scores from heuristic -- structural features should tip it
        scores = {cat: CategoryScore(cat, 0.1, 0.3) for cat in PARACategory}
        mock_engine.evaluate.return_value = HeuristicResult(
            scores=scores,
            overall_confidence=0.3,
            needs_manual_review=True,
        )
        engine = PARASuggestionEngine(config=config, heuristic_engine=mock_engine)

        archive_dir = tmp_path / "archive"
        archive_dir.mkdir()
        f = archive_dir / "old_file.txt"
        f.write_text("old content")

        result = engine.suggest(f)
        # Archive structural hint should significantly boost archive score
        archive_feature = result.metadata.get("feature_scores", {}).get("archive", 0)
        assert archive_feature > 0


# =========================================================================
# suggest_batch() tests
# =========================================================================


class TestSuggestBatch:
    """Tests for the suggest_batch method."""

    def test_returns_one_per_file(
        self,
        suggestion_engine: PARASuggestionEngine,
        tmp_path: Path,
    ) -> None:
        """Should return exactly one suggestion per file."""
        files = []
        for i in range(5):
            f = tmp_path / f"file_{i}.txt"
            f.write_text(f"content {i}")
            files.append(f)

        results = suggestion_engine.suggest_batch(files)
        assert len(results) == 5
        for r in results:
            assert isinstance(r, PARASuggestion)

    def test_handles_errors_in_batch(
        self,
        config: PARAConfig,
        tmp_path: Path,
    ) -> None:
        """Errors on individual files should not break the batch."""
        mock_engine = MagicMock(spec=HeuristicEngine)
        mock_engine.evaluate.side_effect = RuntimeError("fail")
        engine = PARASuggestionEngine(config=config, heuristic_engine=mock_engine)

        files = [tmp_path / f"file_{i}.txt" for i in range(3)]
        for f in files:
            f.write_text("content")

        results = engine.suggest_batch(files)
        assert len(results) == 3

    def test_empty_batch_returns_empty(
        self,
        suggestion_engine: PARASuggestionEngine,
    ) -> None:
        """Empty input should return empty list."""
        assert suggestion_engine.suggest_batch([]) == []


# =========================================================================
# explain() tests
# =========================================================================


class TestExplain:
    """Tests for the explain method."""

    def test_explain_includes_category(
        self,
        suggestion_engine: PARASuggestionEngine,
    ) -> None:
        """Explanation should mention the category."""
        suggestion = PARASuggestion(
            category=PARACategory.RESOURCE,
            confidence=0.78,
            reasoning=["Contains reference keywords"],
        )
        explanation = suggestion_engine.explain(suggestion)
        assert "Resource" in explanation

    def test_explain_includes_confidence(
        self,
        suggestion_engine: PARASuggestionEngine,
    ) -> None:
        """Explanation should include confidence percentage."""
        suggestion = PARASuggestion(
            category=PARACategory.PROJECT,
            confidence=0.85,
            reasoning=["Has deadlines"],
        )
        explanation = suggestion_engine.explain(suggestion)
        assert "85%" in explanation

    def test_explain_includes_reasoning(
        self,
        suggestion_engine: PARASuggestionEngine,
    ) -> None:
        """Explanation should list reasoning items."""
        suggestion = PARASuggestion(
            category=PARACategory.AREA,
            confidence=0.70,
            reasoning=["Ongoing maintenance", "Regular updates"],
        )
        explanation = suggestion_engine.explain(suggestion)
        assert "Ongoing maintenance" in explanation
        assert "Regular updates" in explanation

    def test_explain_includes_alternatives(
        self,
        suggestion_engine: PARASuggestionEngine,
    ) -> None:
        """Explanation should list alternative categories."""
        suggestion = PARASuggestion(
            category=PARACategory.PROJECT,
            confidence=0.65,
            reasoning=["Active work"],
            alternative_categories=[
                (PARACategory.AREA, 0.55),
                (PARACategory.RESOURCE, 0.30),
            ],
        )
        explanation = suggestion_engine.explain(suggestion)
        assert "Area" in explanation
        assert "Resource" in explanation

    def test_explain_includes_subfolder(
        self,
        suggestion_engine: PARASuggestionEngine,
    ) -> None:
        """Explanation should mention suggested subfolder if present."""
        suggestion = PARASuggestion(
            category=PARACategory.RESOURCE,
            confidence=0.80,
            reasoning=["Reference material"],
            suggested_subfolder="References",
        )
        explanation = suggestion_engine.explain(suggestion)
        assert "References" in explanation

    def test_explain_includes_tags(
        self,
        suggestion_engine: PARASuggestionEngine,
    ) -> None:
        """Explanation should list tags."""
        suggestion = PARASuggestion(
            category=PARACategory.PROJECT,
            confidence=0.75,
            reasoning=["Test"],
            tags=["pdf", "deadline"],
        )
        explanation = suggestion_engine.explain(suggestion)
        assert "pdf" in explanation
        assert "deadline" in explanation
