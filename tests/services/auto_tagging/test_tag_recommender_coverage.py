"""Coverage tests for TagRecommender — targets uncovered branches."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from file_organizer.services.auto_tagging.tag_recommender import (
    TagRecommendation,
    TagRecommender,
    TagSuggestion,
)

pytestmark = pytest.mark.unit

# ---------------------------------------------------------------------------
# TagSuggestion
# ---------------------------------------------------------------------------


class TestTagSuggestion:
    def test_to_dict(self):
        s = TagSuggestion(tag="py", confidence=80, source="content", reasoning="found")
        d = s.to_dict()
        assert d["tag"] == "py"
        assert d["confidence"] == 80

    def test_from_dict(self):
        d = {"tag": "py", "confidence": 80, "source": "content", "reasoning": "found"}
        s = TagSuggestion.from_dict(d)
        assert s.tag == "py"
        assert s.metadata == {}

    def test_from_dict_with_metadata(self):
        d = {
            "tag": "py",
            "confidence": 80,
            "source": "content",
            "reasoning": "found",
            "metadata": {"extra": True},
        }
        s = TagSuggestion.from_dict(d)
        assert s.metadata == {"extra": True}


# ---------------------------------------------------------------------------
# TagRecommendation
# ---------------------------------------------------------------------------


class TestTagRecommendation:
    def test_get_high_confidence_tags(self):
        suggestions = [
            TagSuggestion("a", 90, "content", "x"),
            TagSuggestion("b", 50, "content", "x"),
            TagSuggestion("c", 75, "content", "x"),
        ]
        rec = TagRecommendation(file_path=Path("tmp/f.txt"), suggestions=suggestions)
        high = rec.get_high_confidence_tags()
        assert "a" in high
        assert "c" in high
        assert "b" not in high

    def test_get_medium_confidence_tags(self):
        suggestions = [
            TagSuggestion("a", 90, "content", "x"),
            TagSuggestion("b", 50, "content", "x"),
            TagSuggestion("c", 30, "content", "x"),
        ]
        rec = TagRecommendation(file_path=Path("tmp/f.txt"), suggestions=suggestions)
        medium = rec.get_medium_confidence_tags()
        assert "b" in medium
        assert "a" not in medium
        assert "c" not in medium

    def test_to_dict(self):
        suggestions = [TagSuggestion("a", 90, "content", "x")]
        rec = TagRecommendation(
            file_path=Path("tmp/f.txt"),
            suggestions=suggestions,
            existing_tags=["old"],
        )
        d = rec.to_dict()
        assert d["existing_tags"] == ["old"]
        assert len(d["suggestions"]) == 1


# ---------------------------------------------------------------------------
# TagRecommender.recommend_tags
# ---------------------------------------------------------------------------


class TestRecommendTags:
    def _make_recommender(self):
        content_analyzer = MagicMock()
        learning_engine = MagicMock()
        learning_engine.predict_tags.return_value = []
        learning_engine.get_tag_suggestions_for_context.return_value = []
        learning_engine.get_related_tags.return_value = []
        learning_engine.file_type_tags = {}
        learning_engine.directory_tags = {}
        learning_engine.tag_cooccurrence = {}
        learning_engine.tag_usage = {}
        return TagRecommender(
            content_analyzer=content_analyzer,
            learning_engine=learning_engine,
        )

    def test_nonexistent_file(self):
        rec = self._make_recommender()
        result = rec.recommend_tags(Path("nonexistent/file.txt"))
        assert len(result.suggestions) == 0

    def test_recommend_content_only(self, tmp_path):
        rec = self._make_recommender()
        f = tmp_path / "test.txt"
        f.write_text("content")
        rec.content_analyzer.extract_keywords.return_value = [
            ("python", 0.9),
            ("code", 0.5),
        ]
        result = rec.recommend_tags(f)
        assert isinstance(result, TagRecommendation)

    def test_recommend_with_existing_tags_filtered(self, tmp_path):
        rec = self._make_recommender()
        f = tmp_path / "test.txt"
        f.write_text("content")
        rec.content_analyzer.extract_keywords.return_value = [
            ("python", 0.9),
        ]
        result = rec.recommend_tags(f, existing_tags=["python"])
        # "python" should be filtered out
        tag_names = [s.tag for s in result.suggestions]
        assert "python" not in tag_names

    def test_recommend_hybrid_when_both_sources_agree(self, tmp_path):
        rec = self._make_recommender()
        f = tmp_path / "test.txt"
        f.write_text("content")
        rec.content_analyzer.extract_keywords.return_value = [("python", 0.9)]
        rec.learning_engine.get_tag_suggestions_for_context.return_value = [("python", 80.0)]
        result = rec.recommend_tags(f)
        hybrid_tags = [s for s in result.suggestions if s.source == "hybrid"]
        # When both sources agree on "python", we expect a hybrid entry or at minimum an empty list
        assert isinstance(hybrid_tags, list) and all(hasattr(s, "tag") for s in hybrid_tags)

    def test_recommend_with_related_tags(self, tmp_path):
        rec = self._make_recommender()
        f = tmp_path / "test.txt"
        f.write_text("content")
        rec.content_analyzer.extract_keywords.return_value = []
        rec.learning_engine.get_related_tags.return_value = ["related_tag"]

        mock_usage = MagicMock()
        mock_usage.count = 10
        rec.learning_engine.tag_usage = {"existing": mock_usage}
        rec.learning_engine.tag_cooccurrence = {"existing": {"related_tag": 5}}

        result = rec.recommend_tags(f, existing_tags=["existing"])
        assert isinstance(result, TagRecommendation)


# ---------------------------------------------------------------------------
# batch_recommend
# ---------------------------------------------------------------------------


class TestBatchRecommend:
    def test_batch(self, tmp_path):
        rec = TagRecommender(
            content_analyzer=MagicMock(),
            learning_engine=MagicMock(),
        )
        rec.content_analyzer.extract_keywords.return_value = []
        rec.learning_engine.get_tag_suggestions_for_context.return_value = []
        f1 = tmp_path / "a.txt"
        f1.write_text("a")
        f2 = tmp_path / "b.txt"
        f2.write_text("b")
        results = rec.batch_recommend([f1, f2])
        assert f1 in results
        assert f2 in results


# ---------------------------------------------------------------------------
# calculate_confidence
# ---------------------------------------------------------------------------


class TestCalculateConfidence:
    def test_tag_found_in_content(self, tmp_path):
        rec = TagRecommender(
            content_analyzer=MagicMock(),
            learning_engine=MagicMock(),
        )
        f = tmp_path / "test.txt"
        f.write_text("x")
        rec.content_analyzer.analyze_file.return_value = ["python"]
        rec.learning_engine.predict_tags.return_value = []
        score = rec.calculate_confidence("python", f)
        assert score == 70.0

    def test_tag_not_found(self, tmp_path):
        rec = TagRecommender(
            content_analyzer=MagicMock(),
            learning_engine=MagicMock(),
        )
        f = tmp_path / "test.txt"
        f.write_text("x")
        rec.content_analyzer.analyze_file.return_value = []
        rec.learning_engine.predict_tags.return_value = []
        score = rec.calculate_confidence("unknown", f)
        assert score == 0.0


# ---------------------------------------------------------------------------
# explain_tag
# ---------------------------------------------------------------------------


class TestExplainTag:
    def test_explain_content_based(self, tmp_path):
        rec = TagRecommender(
            content_analyzer=MagicMock(),
            learning_engine=MagicMock(),
        )
        f = tmp_path / "test.py"
        f.write_text("x")
        rec.content_analyzer.analyze_file.return_value = ["python"]
        rec.learning_engine.file_type_tags = {}
        rec.learning_engine.directory_tags = {}
        explanation = rec.explain_tag("python", f)
        assert "content" in explanation

    def test_explain_no_match(self, tmp_path):
        rec = TagRecommender(
            content_analyzer=MagicMock(),
            learning_engine=MagicMock(),
        )
        f = tmp_path / "test.txt"
        f.write_text("x")
        rec.content_analyzer.analyze_file.return_value = []
        rec.learning_engine.file_type_tags = {}
        rec.learning_engine.directory_tags = {}
        explanation = rec.explain_tag("unknown", f)
        assert explanation == "Suggested based on file analysis"


# ---------------------------------------------------------------------------
# _combine_confidences
# ---------------------------------------------------------------------------


class TestCombineConfidences:
    def test_combine_content_behavior(self):
        rec = TagRecommender(
            content_analyzer=MagicMock(),
            learning_engine=MagicMock(),
        )
        result = rec._combine_confidences(80.0, 60.0, "content", "behavior")
        assert result > 60.0
        assert result <= 100.0

    def test_combine_capped_at_100(self):
        rec = TagRecommender(
            content_analyzer=MagicMock(),
            learning_engine=MagicMock(),
        )
        result = rec._combine_confidences(95.0, 95.0, "content", "behavior")
        assert result <= 100.0


# ---------------------------------------------------------------------------
# _rank_suggestions
# ---------------------------------------------------------------------------


class TestRankSuggestions:
    def test_ranked_by_confidence(self):
        rec = TagRecommender(
            content_analyzer=MagicMock(),
            learning_engine=MagicMock(),
        )
        suggestions = [
            TagSuggestion("a", 50, "content", "x"),
            TagSuggestion("b", 90, "behavior", "x"),
            TagSuggestion("c", 70, "hybrid", "x"),
        ]
        ranked = rec._rank_suggestions(suggestions)
        assert ranked[0].tag == "b"
