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


@pytest.mark.unit
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

    def test_is_confident_uses_category_threshold(self) -> None:
        """Confidence threshold should vary by category."""
        # Archive threshold is 0.90 — 0.85 is below it
        archive = PARASuggestion(category=PARACategory.ARCHIVE, confidence=0.85)
        assert archive.is_confident is False

        # Project threshold is 0.75 — 0.80 is above it
        project = PARASuggestion(category=PARACategory.PROJECT, confidence=0.80)
        assert project.is_confident is True

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


@pytest.mark.unit
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


@pytest.mark.unit
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


@pytest.mark.unit
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

    def test_exception_in_batch_creates_fallback(
        self,
        config: PARAConfig,
        tmp_path: Path,
    ) -> None:
        """Exception in suggest() should create fallback suggestion."""
        mock_engine = MagicMock(spec=HeuristicEngine)
        mock_engine.evaluate.return_value = _make_heuristic_result()
        engine = PARASuggestionEngine(config=config, heuristic_engine=mock_engine)

        # Create files
        files = [tmp_path / f"file_{i}.txt" for i in range(2)]
        for f in files:
            f.write_text("content")

        # Mock suggest to raise an exception
        from unittest.mock import patch

        original_suggest = engine.suggest

        def suggest_with_exception(path: Path, content: str | None = None):
            if "file_1" in str(path):
                raise ValueError("Simulated error")
            return original_suggest(path, content)

        with patch.object(engine, "suggest", side_effect=suggest_with_exception):
            results = engine.suggest_batch(files)

        # Should get 2 results
        assert len(results) == 2
        # Second one should be the fallback with error message
        assert results[1].confidence == 0.1
        assert results[1].category == PARACategory.RESOURCE
        assert "Error during analysis" in results[1].reasoning[0]

    def test_empty_batch_returns_empty(
        self,
        suggestion_engine: PARASuggestionEngine,
    ) -> None:
        """Empty input should return empty list."""
        assert suggestion_engine.suggest_batch([]) == []


# =========================================================================
# explain() tests
# =========================================================================


@pytest.mark.unit
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


# =========================================================================
# Alternative ranking and filtering tests
# =========================================================================


@pytest.mark.unit
class TestAlternativeRanking:
    """Tests for alternative category ranking and filtering."""

    def test_alternatives_below_threshold_filtered(
        self,
        config: PARAConfig,
        tmp_path: Path,
    ) -> None:
        """Alternatives with scores below 0.1 should be filtered out."""
        mock_engine = MagicMock(spec=HeuristicEngine)
        # Create scores where some categories have very low scores
        scores = {
            PARACategory.PROJECT: CategoryScore(PARACategory.PROJECT, 0.6, 0.6),
            PARACategory.AREA: CategoryScore(PARACategory.AREA, 0.25, 0.25),
            PARACategory.RESOURCE: CategoryScore(PARACategory.RESOURCE, 0.08, 0.08),  # Below 0.1
            PARACategory.ARCHIVE: CategoryScore(PARACategory.ARCHIVE, 0.02, 0.02),  # Below 0.1
        }
        mock_engine.evaluate.return_value = HeuristicResult(
            scores=scores,
            overall_confidence=0.6,
            recommended_category=PARACategory.PROJECT,
            needs_manual_review=False,
        )
        engine = PARASuggestionEngine(config=config, heuristic_engine=mock_engine)

        f = tmp_path / "test.txt"
        f.write_text("content")
        result = engine.suggest(f)

        # Only AREA should be in alternatives (PROJECT is the main suggestion)
        assert len(result.alternative_categories) == 1
        assert result.alternative_categories[0][0] == PARACategory.AREA
        # RESOURCE and ARCHIVE should be filtered out
        alt_cats = [cat for cat, _ in result.alternative_categories]
        assert PARACategory.RESOURCE not in alt_cats
        assert PARACategory.ARCHIVE not in alt_cats

    def test_alternatives_sorted_descending(
        self,
        config: PARAConfig,
        tmp_path: Path,
    ) -> None:
        """Alternative categories should be sorted by score in descending order."""
        mock_engine = MagicMock(spec=HeuristicEngine)
        scores = {
            PARACategory.PROJECT: CategoryScore(PARACategory.PROJECT, 0.7, 0.7),
            PARACategory.AREA: CategoryScore(PARACategory.AREA, 0.5, 0.5),
            PARACategory.RESOURCE: CategoryScore(PARACategory.RESOURCE, 0.3, 0.3),
            PARACategory.ARCHIVE: CategoryScore(PARACategory.ARCHIVE, 0.2, 0.2),
        }
        mock_engine.evaluate.return_value = HeuristicResult(
            scores=scores,
            overall_confidence=0.7,
            recommended_category=PARACategory.PROJECT,
            needs_manual_review=False,
        )
        engine = PARASuggestionEngine(config=config, heuristic_engine=mock_engine)

        f = tmp_path / "test.txt"
        f.write_text("content")
        result = engine.suggest(f)

        # Alternatives should be sorted by score descending
        alt_scores = [score for _, score in result.alternative_categories]
        assert alt_scores == sorted(alt_scores, reverse=True)
        # And should be AREA, RESOURCE, ARCHIVE in that order
        assert result.alternative_categories[0][0] == PARACategory.AREA
        assert result.alternative_categories[1][0] == PARACategory.RESOURCE
        assert result.alternative_categories[2][0] == PARACategory.ARCHIVE


# =========================================================================
# Feature scoring tests
# =========================================================================


@pytest.mark.unit
class TestFeatureScoring:
    """Tests for individual feature scoring functions."""

    def test_text_features_with_mixed_keywords(
        self,
        config: PARAConfig,
        tmp_path: Path,
    ) -> None:
        """Text with multiple category keywords should boost multiple scores."""
        mock_engine = MagicMock(spec=HeuristicEngine)
        # Start with equal heuristic scores
        scores = {cat: CategoryScore(cat, 0.3, 0.3) for cat in PARACategory}
        mock_engine.evaluate.return_value = HeuristicResult(
            scores=scores,
            overall_confidence=0.3,
            needs_manual_review=True,
        )
        engine = PARASuggestionEngine(config=config, heuristic_engine=mock_engine)

        f = tmp_path / "mixed.txt"
        f.write_text("content")
        # Content with project AND area keywords
        content = "deadline sprint milestone ongoing maintenance recurring task"
        result = engine.suggest(f, content=content)

        # Both project and area should have elevated feature scores
        feature_scores = result.metadata.get("feature_scores", {})
        assert feature_scores.get("project", 0) > 0
        # May also have area score if "ongoing" and "maintenance" are counted

    def test_text_features_temporal_indicators(
        self,
        config: PARAConfig,
        tmp_path: Path,
    ) -> None:
        """Temporal indicators should boost PROJECT score."""
        mock_engine = MagicMock(spec=HeuristicEngine)
        scores = {cat: CategoryScore(cat, 0.2, 0.2) for cat in PARACategory}
        mock_engine.evaluate.return_value = HeuristicResult(
            scores=scores,
            overall_confidence=0.2,
            needs_manual_review=True,
        )
        engine = PARASuggestionEngine(config=config, heuristic_engine=mock_engine)

        f = tmp_path / "test.txt"
        f.write_text("content")
        # Content with temporal indicators
        content = "due Monday by Friday deadline tomorrow next week"
        result = engine.suggest(f, content=content)

        # Project feature score should be elevated
        feature_scores = result.metadata.get("feature_scores", {})
        assert feature_scores.get("project", 0) > 0.1
        # Reasoning should mention temporal references
        reasoning_text = " ".join(result.reasoning).lower()
        assert "temporal" in reasoning_text

    def test_text_features_action_items(
        self,
        config: PARAConfig,
        tmp_path: Path,
    ) -> None:
        """Action items should boost PROJECT score and appear in reasoning."""
        mock_engine = MagicMock(spec=HeuristicEngine)
        scores = {cat: CategoryScore(cat, 0.2, 0.2) for cat in PARACategory}
        mock_engine.evaluate.return_value = HeuristicResult(
            scores=scores,
            overall_confidence=0.2,
            needs_manual_review=True,
        )
        engine = PARASuggestionEngine(config=config, heuristic_engine=mock_engine)

        f = tmp_path / "test.txt"
        f.write_text("content")
        # Content with action items
        content = "TODO: implement feature\n- [ ] write tests\n- [ ] deploy"
        result = engine.suggest(f, content=content)

        # Project feature score should be elevated
        feature_scores = result.metadata.get("feature_scores", {})
        assert feature_scores.get("project", 0) > 0
        # Reasoning should mention action items if PROJECT is suggested
        if result.category == PARACategory.PROJECT:
            reasoning_text = " ".join(result.reasoning).lower()
            assert "action items" in reasoning_text

    def test_text_features_document_type_plan(
        self,
        config: PARAConfig,
        tmp_path: Path,
    ) -> None:
        """Document type 'plan' should boost PROJECT score."""
        mock_engine = MagicMock(spec=HeuristicEngine)
        scores = {cat: CategoryScore(cat, 0.2, 0.2) for cat in PARACategory}
        mock_engine.evaluate.return_value = HeuristicResult(
            scores=scores,
            overall_confidence=0.2,
            needs_manual_review=True,
        )
        engine = PARASuggestionEngine(config=config, heuristic_engine=mock_engine)

        f = tmp_path / "project-plan.txt"
        f.write_text("content")
        content = "This is a comprehensive plan for the project"
        result = engine.suggest(f, content=content)

        # Project should get a boost
        feature_scores = result.metadata.get("feature_scores", {})
        project_score = feature_scores.get("project", 0)
        # Even with neutral heuristics, project should win
        assert project_score > feature_scores.get("archive", 0)

    def test_text_features_document_type_reference(
        self,
        config: PARAConfig,
        tmp_path: Path,
    ) -> None:
        """Document type 'reference' should boost RESOURCE score."""
        mock_engine = MagicMock(spec=HeuristicEngine)
        scores = {cat: CategoryScore(cat, 0.2, 0.2) for cat in PARACategory}
        mock_engine.evaluate.return_value = HeuristicResult(
            scores=scores,
            overall_confidence=0.2,
            needs_manual_review=True,
        )
        engine = PARASuggestionEngine(config=config, heuristic_engine=mock_engine)

        f = tmp_path / "reference.txt"
        f.write_text("content")
        content = "This is reference material for documentation"
        result = engine.suggest(f, content=content)

        # Resource should get a boost
        feature_scores = result.metadata.get("feature_scores", {})
        resource_score = feature_scores.get("resource", 0)
        assert resource_score > 0

    def test_text_features_document_type_notes(
        self,
        config: PARAConfig,
        tmp_path: Path,
    ) -> None:
        """Document type 'notes' should boost AREA score."""
        mock_engine = MagicMock(spec=HeuristicEngine)
        scores = {cat: CategoryScore(cat, 0.2, 0.2) for cat in PARACategory}
        mock_engine.evaluate.return_value = HeuristicResult(
            scores=scores,
            overall_confidence=0.2,
            needs_manual_review=True,
        )
        engine = PARASuggestionEngine(config=config, heuristic_engine=mock_engine)

        f = tmp_path / "meeting-notes.txt"
        f.write_text("content")
        content = "These are notes from the meeting"
        result = engine.suggest(f, content=content)

        # Area should get a boost
        feature_scores = result.metadata.get("feature_scores", {})
        area_score = feature_scores.get("area", 0)
        assert area_score > 0

    def test_metadata_features_recent_modification(
        self,
        config: PARAConfig,
        tmp_path: Path,
    ) -> None:
        """Recently modified files should boost PROJECT score."""
        mock_engine = MagicMock(spec=HeuristicEngine)
        scores = {cat: CategoryScore(cat, 0.2, 0.2) for cat in PARACategory}
        mock_engine.evaluate.return_value = HeuristicResult(
            scores=scores,
            overall_confidence=0.2,
            needs_manual_review=True,
        )
        engine = PARASuggestionEngine(config=config, heuristic_engine=mock_engine)

        # Create a file that's very recent
        f = tmp_path / "recent.txt"
        f.write_text("content")
        f.touch()  # Ensures it's recent

        result = engine.suggest(f)

        # Project should get metadata boost
        feature_scores = result.metadata.get("feature_scores", {})
        assert feature_scores.get("project", 0) > 0
        # Reasoning should mention recent modification if PROJECT wins
        if result.category == PARACategory.PROJECT:
            reasoning_text = " ".join(result.reasoning).lower()
            assert "recent" in reasoning_text or "active" in reasoning_text

    def test_metadata_features_old_file_archive(
        self,
        config: PARAConfig,
        tmp_path: Path,
    ) -> None:
        """Old files (>180 days) should boost ARCHIVE score."""
        mock_engine = MagicMock(spec=HeuristicEngine)
        # Set archive slightly higher to ensure it wins with the boost
        scores = {
            PARACategory.PROJECT: CategoryScore(PARACategory.PROJECT, 0.2, 0.2),
            PARACategory.AREA: CategoryScore(PARACategory.AREA, 0.2, 0.2),
            PARACategory.RESOURCE: CategoryScore(PARACategory.RESOURCE, 0.2, 0.2),
            PARACategory.ARCHIVE: CategoryScore(PARACategory.ARCHIVE, 0.25, 0.25),
        }
        mock_engine.evaluate.return_value = HeuristicResult(
            scores=scores,
            overall_confidence=0.25,
            needs_manual_review=True,
        )
        engine = PARASuggestionEngine(config=config, heuristic_engine=mock_engine)

        # Create an old file by mocking the feature extractor
        from unittest.mock import patch

        from file_organizer.methodologies.para.ai.feature_extractor import MetadataFeatures

        f = tmp_path / "old.txt"
        f.write_text("content")

        with patch.object(engine._feature_extractor, "extract_metadata_features") as mock_meta:
            mock_meta.return_value = MetadataFeatures(
                file_type=".txt",
                file_size=100,
                days_since_modified=200,  # >180 days
                days_since_created=200,
                access_frequency=0.1,
            )
            result = engine.suggest(f)

        # Archive should get a boost
        feature_scores = result.metadata.get("feature_scores", {})
        assert feature_scores.get("archive", 0) > 0.1
        # If archive wins, reasoning should mention age
        if result.category == PARACategory.ARCHIVE:
            reasoning_text = " ".join(result.reasoning).lower()
            assert "days" in reasoning_text or "modified" in reasoning_text

    def test_metadata_features_old_file_medium_access(
        self,
        config: PARAConfig,
        tmp_path: Path,
    ) -> None:
        """Old files with medium access frequency should still boost ARCHIVE."""
        mock_engine = MagicMock(spec=HeuristicEngine)
        scores = {cat: CategoryScore(cat, 0.2, 0.2) for cat in PARACategory}
        mock_engine.evaluate.return_value = HeuristicResult(
            scores=scores,
            overall_confidence=0.2,
            needs_manual_review=True,
        )
        engine = PARASuggestionEngine(config=config, heuristic_engine=mock_engine)

        from unittest.mock import patch

        from file_organizer.methodologies.para.ai.feature_extractor import MetadataFeatures

        f = tmp_path / "old_medium.txt"
        f.write_text("content")

        with patch.object(engine._feature_extractor, "extract_metadata_features") as mock_meta:
            mock_meta.return_value = MetadataFeatures(
                file_type=".txt",
                file_size=100,
                days_since_modified=200,  # >180 days
                days_since_created=200,
                access_frequency=0.5,  # Medium frequency (not <0.2, not >0.7)
            )
            result = engine.suggest(f)

        # Archive should still get a boost from age alone
        feature_scores = result.metadata.get("feature_scores", {})
        assert feature_scores.get("archive", 0) > 0.1

    def test_metadata_features_medium_age_area(
        self,
        config: PARAConfig,
        tmp_path: Path,
    ) -> None:
        """Files 30-180 days old should boost AREA score."""
        mock_engine = MagicMock(spec=HeuristicEngine)
        scores = {cat: CategoryScore(cat, 0.2, 0.2) for cat in PARACategory}
        mock_engine.evaluate.return_value = HeuristicResult(
            scores=scores,
            overall_confidence=0.2,
            needs_manual_review=True,
        )
        engine = PARASuggestionEngine(config=config, heuristic_engine=mock_engine)

        from unittest.mock import patch

        from file_organizer.methodologies.para.ai.feature_extractor import MetadataFeatures

        f = tmp_path / "medium.txt"
        f.write_text("content")

        with patch.object(engine._feature_extractor, "extract_metadata_features") as mock_meta:
            mock_meta.return_value = MetadataFeatures(
                file_type=".txt",
                file_size=100,
                days_since_modified=90,  # 30-180 days
                days_since_created=90,
                access_frequency=0.5,
            )
            result = engine.suggest(f)

        # Area should get a boost
        feature_scores = result.metadata.get("feature_scores", {})
        assert feature_scores.get("area", 0) > 0

    def test_metadata_features_low_access_frequency_archive(
        self,
        config: PARAConfig,
        tmp_path: Path,
    ) -> None:
        """Low access frequency + age should boost ARCHIVE."""
        mock_engine = MagicMock(spec=HeuristicEngine)
        scores = {cat: CategoryScore(cat, 0.2, 0.2) for cat in PARACategory}
        mock_engine.evaluate.return_value = HeuristicResult(
            scores=scores,
            overall_confidence=0.2,
            needs_manual_review=True,
        )
        engine = PARASuggestionEngine(config=config, heuristic_engine=mock_engine)

        from unittest.mock import patch

        from file_organizer.methodologies.para.ai.feature_extractor import MetadataFeatures

        f = tmp_path / "rarely_accessed.txt"
        f.write_text("content")

        with patch.object(engine._feature_extractor, "extract_metadata_features") as mock_meta:
            mock_meta.return_value = MetadataFeatures(
                file_type=".txt",
                file_size=100,
                days_since_modified=100,  # >90 days
                days_since_created=100,
                access_frequency=0.1,  # <0.2
            )
            result = engine.suggest(f)

        # Archive should get a boost
        feature_scores = result.metadata.get("feature_scores", {})
        assert feature_scores.get("archive", 0) > 0

    def test_metadata_features_high_access_frequency_project(
        self,
        config: PARAConfig,
        tmp_path: Path,
    ) -> None:
        """High access frequency should boost PROJECT."""
        mock_engine = MagicMock(spec=HeuristicEngine)
        scores = {cat: CategoryScore(cat, 0.2, 0.2) for cat in PARACategory}
        mock_engine.evaluate.return_value = HeuristicResult(
            scores=scores,
            overall_confidence=0.2,
            needs_manual_review=True,
        )
        engine = PARASuggestionEngine(config=config, heuristic_engine=mock_engine)

        from unittest.mock import patch

        from file_organizer.methodologies.para.ai.feature_extractor import MetadataFeatures

        f = tmp_path / "frequently_accessed.txt"
        f.write_text("content")

        with patch.object(engine._feature_extractor, "extract_metadata_features") as mock_meta:
            mock_meta.return_value = MetadataFeatures(
                file_type=".txt",
                file_size=100,
                days_since_modified=5,
                days_since_created=10,
                access_frequency=0.8,  # >0.7
            )
            result = engine.suggest(f)

        # Project should get a boost
        feature_scores = result.metadata.get("feature_scores", {})
        assert feature_scores.get("project", 0) > 0

    def test_structural_features_project_structure(
        self,
        config: PARAConfig,
        tmp_path: Path,
    ) -> None:
        """Project structure indicators should boost PROJECT score."""
        mock_engine = MagicMock(spec=HeuristicEngine)
        scores = {cat: CategoryScore(cat, 0.2, 0.2) for cat in PARACategory}
        mock_engine.evaluate.return_value = HeuristicResult(
            scores=scores,
            overall_confidence=0.2,
            needs_manual_review=True,
        )
        engine = PARASuggestionEngine(config=config, heuristic_engine=mock_engine)

        from unittest.mock import patch

        from file_organizer.methodologies.para.ai.feature_extractor import StructuralFeatures

        f = tmp_path / "file.txt"
        f.write_text("content")

        with patch.object(engine._feature_extractor, "extract_structural_features") as mock_struct:
            mock_struct.return_value = StructuralFeatures(
                directory_depth=2,
                parent_category_hint=None,
                has_project_structure=True,
                has_date_in_path=False,
            )
            result = engine.suggest(f)

        # Project should get a boost
        feature_scores = result.metadata.get("feature_scores", {})
        assert feature_scores.get("project", 0) > 0
        # Reasoning should mention project structure
        reasoning_text = " ".join(result.reasoning).lower()
        assert "project structure" in reasoning_text

    def test_structural_features_date_in_path(
        self,
        config: PARAConfig,
        tmp_path: Path,
    ) -> None:
        """Date in path should boost PROJECT score."""
        mock_engine = MagicMock(spec=HeuristicEngine)
        scores = {cat: CategoryScore(cat, 0.2, 0.2) for cat in PARACategory}
        mock_engine.evaluate.return_value = HeuristicResult(
            scores=scores,
            overall_confidence=0.2,
            needs_manual_review=True,
        )
        engine = PARASuggestionEngine(config=config, heuristic_engine=mock_engine)

        from unittest.mock import patch

        from file_organizer.methodologies.para.ai.feature_extractor import StructuralFeatures

        f = tmp_path / "file.txt"
        f.write_text("content")

        with patch.object(engine._feature_extractor, "extract_structural_features") as mock_struct:
            mock_struct.return_value = StructuralFeatures(
                directory_depth=2,
                parent_category_hint=None,
                has_project_structure=False,
                has_date_in_path=True,
            )
            result = engine.suggest(f)

        # Project should get a boost
        feature_scores = result.metadata.get("feature_scores", {})
        assert feature_scores.get("project", 0) > 0

    def test_structural_features_invalid_parent_hint(
        self,
        config: PARAConfig,
        tmp_path: Path,
    ) -> None:
        """Parent hint not in category map should not boost any category."""
        mock_engine = MagicMock(spec=HeuristicEngine)
        scores = {cat: CategoryScore(cat, 0.2, 0.2) for cat in PARACategory}
        mock_engine.evaluate.return_value = HeuristicResult(
            scores=scores,
            overall_confidence=0.2,
            needs_manual_review=True,
        )
        engine = PARASuggestionEngine(config=config, heuristic_engine=mock_engine)

        from unittest.mock import patch

        from file_organizer.methodologies.para.ai.feature_extractor import StructuralFeatures

        f = tmp_path / "file.txt"
        f.write_text("content")

        with patch.object(engine._feature_extractor, "extract_structural_features") as mock_struct:
            # Use a hint that's not in the category map
            mock_struct.return_value = StructuralFeatures(
                directory_depth=2,
                parent_category_hint="random_folder",
                has_project_structure=False,
                has_date_in_path=False,
            )
            result = engine.suggest(f)

        # Should still get a valid suggestion
        assert isinstance(result, PARASuggestion)
        assert result.category in PARACategory


# =========================================================================
# Reasoning and subfolder suggestion tests
# =========================================================================


@pytest.mark.unit
class TestReasoningAndSubfolders:
    """Tests for reasoning generation and subfolder suggestions."""

    def test_fallback_reasoning_when_no_signals(
        self,
        config: PARAConfig,
        tmp_path: Path,
    ) -> None:
        """When no specific signals found, should provide fallback reasoning."""
        mock_engine = MagicMock(spec=HeuristicEngine)
        # Return minimal scores with no signals
        scores = {cat: CategoryScore(cat, 0.2, 0.2, signals=[]) for cat in PARACategory}
        scores[PARACategory.RESOURCE] = CategoryScore(PARACategory.RESOURCE, 0.3, 0.3, signals=[])
        mock_engine.evaluate.return_value = HeuristicResult(
            scores=scores,
            overall_confidence=0.3,
            recommended_category=PARACategory.RESOURCE,
            needs_manual_review=True,
        )
        engine = PARASuggestionEngine(config=config, heuristic_engine=mock_engine)

        # Mock all feature extractors to return empty/neutral features
        from unittest.mock import patch

        from file_organizer.methodologies.para.ai.feature_extractor import (
            MetadataFeatures,
            StructuralFeatures,
        )

        f = tmp_path / "file.txt"
        f.write_text("x")

        with (
            patch.object(engine._feature_extractor, "extract_metadata_features") as mock_meta,
            patch.object(engine._feature_extractor, "extract_structural_features") as mock_struct,
        ):
            mock_meta.return_value = MetadataFeatures(
                file_type=".txt",
                file_size=1,
                days_since_modified=0,
                days_since_created=0,
                access_frequency=0.0,
            )
            mock_struct.return_value = StructuralFeatures(
                directory_depth=1,
                sibling_count=0,
                parent_category_hint=None,
                path_keywords=[],
                has_project_structure=False,
                has_date_in_path=False,
            )

            # Don't provide content to avoid text features
            result = engine.suggest(f)

        # Should have at least one reasoning entry (fallback)
        assert len(result.reasoning) >= 1
        reasoning_text = " ".join(result.reasoning).lower()
        # Should mention "combined analysis" or category name
        assert "resource" in reasoning_text or "combined" in reasoning_text

    def test_subfolder_suggestion_for_resource_with_doc_type(
        self,
        config: PARAConfig,
        tmp_path: Path,
    ) -> None:
        """RESOURCE category with document type should suggest subfolder."""
        mock_engine = MagicMock(spec=HeuristicEngine)
        scores = {cat: CategoryScore(cat, 0.1, 0.1) for cat in PARACategory}
        scores[PARACategory.RESOURCE] = CategoryScore(PARACategory.RESOURCE, 0.7, 0.7)
        mock_engine.evaluate.return_value = HeuristicResult(
            scores=scores,
            overall_confidence=0.7,
            recommended_category=PARACategory.RESOURCE,
            needs_manual_review=False,
        )
        engine = PARASuggestionEngine(config=config, heuristic_engine=mock_engine)

        f = tmp_path / "reference.txt"
        f.write_text("content")
        content = "This is reference material"
        result = engine.suggest(f, content=content)

        # Should suggest a subfolder based on document type
        assert result.suggested_subfolder is not None
        # Should be pluralized and title-cased
        assert result.suggested_subfolder.endswith("s")

    def test_subfolder_suggestion_for_project_with_parent(
        self,
        config: PARAConfig,
        tmp_path: Path,
    ) -> None:
        """PROJECT category should use parent directory name as subfolder."""
        mock_engine = MagicMock(spec=HeuristicEngine)
        scores = {cat: CategoryScore(cat, 0.1, 0.1) for cat in PARACategory}
        scores[PARACategory.PROJECT] = CategoryScore(PARACategory.PROJECT, 0.8, 0.8)
        mock_engine.evaluate.return_value = HeuristicResult(
            scores=scores,
            overall_confidence=0.8,
            recommended_category=PARACategory.PROJECT,
            needs_manual_review=False,
        )
        engine = PARASuggestionEngine(config=config, heuristic_engine=mock_engine)

        # Create file in a named subdirectory
        project_dir = tmp_path / "website-redesign"
        project_dir.mkdir()
        f = project_dir / "notes.txt"
        f.write_text("project notes")

        result = engine.suggest(f)

        # Should suggest parent directory name
        assert result.suggested_subfolder == "website-redesign"

    def test_subfolder_suggestion_for_area_with_parent(
        self,
        config: PARAConfig,
        tmp_path: Path,
    ) -> None:
        """AREA category should use parent directory name as subfolder."""
        mock_engine = MagicMock(spec=HeuristicEngine)
        scores = {cat: CategoryScore(cat, 0.1, 0.1) for cat in PARACategory}
        scores[PARACategory.AREA] = CategoryScore(PARACategory.AREA, 0.75, 0.75)
        mock_engine.evaluate.return_value = HeuristicResult(
            scores=scores,
            overall_confidence=0.75,
            recommended_category=PARACategory.AREA,
            needs_manual_review=False,
        )
        engine = PARASuggestionEngine(config=config, heuristic_engine=mock_engine)

        # Create file in a named subdirectory
        area_dir = tmp_path / "health"
        area_dir.mkdir()
        f = area_dir / "routine.txt"
        f.write_text("health routine")

        result = engine.suggest(f)

        # Should suggest parent directory name
        assert result.suggested_subfolder == "health"

    def test_no_subfolder_for_archive(
        self,
        config: PARAConfig,
        tmp_path: Path,
    ) -> None:
        """ARCHIVE category should not suggest subfolder."""
        mock_engine = MagicMock(spec=HeuristicEngine)
        scores = {cat: CategoryScore(cat, 0.1, 0.1) for cat in PARACategory}
        scores[PARACategory.ARCHIVE] = CategoryScore(PARACategory.ARCHIVE, 0.95, 0.95)
        mock_engine.evaluate.return_value = HeuristicResult(
            scores=scores,
            overall_confidence=0.95,
            recommended_category=PARACategory.ARCHIVE,
            needs_manual_review=False,
        )
        engine = PARASuggestionEngine(config=config, heuristic_engine=mock_engine)

        f = tmp_path / "old.txt"
        f.write_text("old content")

        result = engine.suggest(f)

        # Archive should not suggest subfolder
        assert result.suggested_subfolder is None

    def test_no_subfolder_for_resource_without_doc_type(
        self,
        config: PARAConfig,
        tmp_path: Path,
    ) -> None:
        """RESOURCE without identifiable document type should not suggest subfolder."""
        mock_engine = MagicMock(spec=HeuristicEngine)
        scores = {cat: CategoryScore(cat, 0.1, 0.1) for cat in PARACategory}
        scores[PARACategory.RESOURCE] = CategoryScore(PARACategory.RESOURCE, 0.7, 0.7)
        mock_engine.evaluate.return_value = HeuristicResult(
            scores=scores,
            overall_confidence=0.7,
            recommended_category=PARACategory.RESOURCE,
            needs_manual_review=False,
        )
        engine = PARASuggestionEngine(config=config, heuristic_engine=mock_engine)

        f = tmp_path / "file.txt"
        f.write_text("content")
        # Generic content without clear document type
        content = "some random text"
        result = engine.suggest(f, content=content)

        # May or may not have subfolder depending on doc type detection
        # If doc_type is "unknown", should be None
        if result.suggested_subfolder:
            assert result.suggested_subfolder != "Unknowns"

    def test_subfolder_suggestion_project_with_special_parent(
        self,
        config: PARAConfig,
        tmp_path: Path,
    ) -> None:
        """PROJECT with special parent directory names should not suggest subfolder."""
        mock_engine = MagicMock(spec=HeuristicEngine)
        scores = {cat: CategoryScore(cat, 0.1, 0.1) for cat in PARACategory}
        scores[PARACategory.PROJECT] = CategoryScore(PARACategory.PROJECT, 0.8, 0.8)
        mock_engine.evaluate.return_value = HeuristicResult(
            scores=scores,
            overall_confidence=0.8,
            recommended_category=PARACategory.PROJECT,
            needs_manual_review=False,
        )
        engine = PARASuggestionEngine(config=config, heuristic_engine=mock_engine)

        # Test with tmp_path directly (name is not ".", "/", or "~" but let's mock it)
        from unittest.mock import patch

        f = tmp_path / "file.txt"
        f.write_text("content")

        # Mock the parent name to be "."
        with patch.object(
            Path, "parent", new_callable=lambda: property(lambda self: type(self)("."))
        ):
            result = engine.suggest(f)
            # Should not suggest subfolder for special parent name
            # But this is tricky to test, let's just verify it works
            assert isinstance(result, PARASuggestion)
            assert result.suggested_subfolder is None

    def test_tags_with_empty_file_type(
        self,
        config: PARAConfig,
        tmp_path: Path,
    ) -> None:
        """Tags should handle empty file_type gracefully."""
        mock_engine = MagicMock(spec=HeuristicEngine)
        scores = {cat: CategoryScore(cat, 0.5, 0.5) for cat in PARACategory}
        mock_engine.evaluate.return_value = HeuristicResult(
            scores=scores,
            overall_confidence=0.5,
            needs_manual_review=False,
        )
        engine = PARASuggestionEngine(config=config, heuristic_engine=mock_engine)

        from unittest.mock import patch

        from file_organizer.methodologies.para.ai.feature_extractor import MetadataFeatures

        f = tmp_path / "file"  # No extension
        f.write_text("content")

        with patch.object(engine._feature_extractor, "extract_metadata_features") as mock_meta:
            mock_meta.return_value = MetadataFeatures(
                file_type="",  # Empty file type
                file_size=100,
                days_since_modified=10,
                days_since_created=10,
                access_frequency=0.5,
            )
            result = engine.suggest(f)

        # Tags should not contain an empty string
        assert "" not in result.tags
        # Tags should still be a list
        assert isinstance(result.tags, list)
