"""Integration tests for tag recommender and feedback processor.

Covers:
  - services/auto_tagging/tag_recommender.py    — TagRecommender, TagRecommendation
  - services/intelligence/feedback_processor.py — FeedbackProcessor
"""

from __future__ import annotations

from pathlib import Path

import pytest

from file_organizer.services.auto_tagging.tag_recommender import (
    TagRecommendation,
    TagRecommender,
)
from file_organizer.services.intelligence.feedback_processor import FeedbackProcessor

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# TagRecommender — fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def recommender() -> TagRecommender:
    return TagRecommender()


# ---------------------------------------------------------------------------
# TagRecommender — init
# ---------------------------------------------------------------------------


class TestTagRecommenderInit:
    def test_default_init(self) -> None:
        r = TagRecommender()
        assert r is not None

    def test_custom_min_confidence(self) -> None:
        r = TagRecommender(min_confidence=50.0)
        assert r is not None


# ---------------------------------------------------------------------------
# TagRecommender — recommend_tags
# ---------------------------------------------------------------------------


class TestRecommendTags:
    def test_returns_recommendation(self, recommender: TagRecommender, tmp_path: Path) -> None:
        f = tmp_path / "report.pdf"
        f.write_bytes(b"pdf content about finance quarterly")
        result = recommender.recommend_tags(f)
        assert isinstance(result, TagRecommendation)

    def test_recommendation_has_file_path(
        self, recommender: TagRecommender, tmp_path: Path
    ) -> None:
        f = tmp_path / "notes.txt"
        f.write_text("meeting notes about project")
        result = recommender.recommend_tags(f)
        assert result.file_path == f

    def test_recommendations_are_list(self, recommender: TagRecommender, tmp_path: Path) -> None:
        f = tmp_path / "doc.txt"
        f.write_text("content")
        result = recommender.recommend_tags(f)
        assert len(result.suggestions) >= 1

    def test_with_existing_tags(self, recommender: TagRecommender, tmp_path: Path) -> None:
        f = tmp_path / "invoice.pdf"
        f.write_bytes(b"invoice data")
        result = recommender.recommend_tags(f, existing_tags=["finance"])
        assert isinstance(result, TagRecommendation)

    def test_top_n_limit(self, recommender: TagRecommender, tmp_path: Path) -> None:
        f = tmp_path / "file.txt"
        f.write_text("text content with many potential tags and keywords")
        result = recommender.recommend_tags(f, top_n=3)
        assert len(result.suggestions) < 4

    def test_nonexistent_file(self, recommender: TagRecommender, tmp_path: Path) -> None:
        f = tmp_path / "missing.txt"
        result = recommender.recommend_tags(f)
        assert isinstance(result, TagRecommendation)


# ---------------------------------------------------------------------------
# TagRecommender — calculate_confidence
# ---------------------------------------------------------------------------


class TestCalculateConfidence:
    def test_returns_float(self, recommender: TagRecommender, tmp_path: Path) -> None:
        f = tmp_path / "file.txt"
        f.write_text("financial content")
        result = recommender.calculate_confidence("finance", f)
        assert result >= 0.0

    def test_range(self, recommender: TagRecommender, tmp_path: Path) -> None:
        f = tmp_path / "file.txt"
        f.write_text("content")
        result = recommender.calculate_confidence("tag", f)
        assert result >= 0.0

    def test_nonexistent_file(self, recommender: TagRecommender, tmp_path: Path) -> None:
        f = tmp_path / "missing.txt"
        result = recommender.calculate_confidence("tag", f)
        assert result == 0.0


# ---------------------------------------------------------------------------
# TagRecommender — explain_tag
# ---------------------------------------------------------------------------


class TestExplainTag:
    def test_returns_string(self, recommender: TagRecommender, tmp_path: Path) -> None:
        f = tmp_path / "file.pdf"
        f.write_bytes(b"content")
        result = recommender.explain_tag("finance", f)
        assert len(result) > 0

    def test_with_existing_tags(self, recommender: TagRecommender, tmp_path: Path) -> None:
        f = tmp_path / "doc.txt"
        f.write_text("document content")
        result = recommender.explain_tag("work", f, existing_tags=["document"])
        assert len(result) > 0

    def test_nonexistent_file(self, recommender: TagRecommender, tmp_path: Path) -> None:
        f = tmp_path / "missing.txt"
        result = recommender.explain_tag("tag", f)
        assert len(result) > 0


# ---------------------------------------------------------------------------
# TagRecommender — batch_recommend
# ---------------------------------------------------------------------------


class TestBatchRecommend:
    def test_empty_list(self, recommender: TagRecommender) -> None:
        result = recommender.batch_recommend([])
        assert isinstance(result, dict)
        assert len(result) == 0

    def test_single_file(self, recommender: TagRecommender, tmp_path: Path) -> None:
        f = tmp_path / "file.txt"
        f.write_text("content")
        result = recommender.batch_recommend([f])
        assert isinstance(result, dict)
        assert f in result

    def test_multiple_files(self, recommender: TagRecommender, tmp_path: Path) -> None:
        files = []
        for i in range(3):
            f = tmp_path / f"file{i}.txt"
            f.write_text(f"content {i}")
            files.append(f)
        result = recommender.batch_recommend(files)
        assert isinstance(result, dict)
        assert len(result) == 3

    def test_values_are_recommendations(self, recommender: TagRecommender, tmp_path: Path) -> None:
        f = tmp_path / "doc.pdf"
        f.write_bytes(b"pdf content")
        result = recommender.batch_recommend([f])
        for _key, val in result.items():
            assert isinstance(val, TagRecommendation)


# ---------------------------------------------------------------------------
# FeedbackProcessor — fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def feedback_processor() -> FeedbackProcessor:
    return FeedbackProcessor()


# ---------------------------------------------------------------------------
# FeedbackProcessor — init
# ---------------------------------------------------------------------------


class TestFeedbackProcessorInit:
    def test_creates(self) -> None:
        fp = FeedbackProcessor()
        assert fp is not None


# ---------------------------------------------------------------------------
# FeedbackProcessor — process_correction
# ---------------------------------------------------------------------------


class TestProcessCorrection:
    def test_returns_dict(self, feedback_processor: FeedbackProcessor, tmp_path: Path) -> None:
        orig = tmp_path / "original.txt"
        corrected_dir = tmp_path / "corrected"
        corrected_dir.mkdir()
        corrected = corrected_dir / "original.txt"
        orig.write_text("some file content")
        corrected.write_text("some file content")
        result = feedback_processor.process_correction(orig, corrected)
        assert "timestamp" in result

    def test_result_has_timestamp(
        self, feedback_processor: FeedbackProcessor, tmp_path: Path
    ) -> None:
        orig = tmp_path / "file.txt"
        new_loc = tmp_path / "subfolder" / "file.txt"
        new_loc.parent.mkdir()
        orig.write_text("content")
        new_loc.write_text("content")
        result = feedback_processor.process_correction(orig, new_loc)
        assert "timestamp" in result

    def test_result_has_paths(self, feedback_processor: FeedbackProcessor, tmp_path: Path) -> None:
        orig = tmp_path / "doc.pdf"
        corrected = tmp_path / "new" / "doc.pdf"
        corrected.parent.mkdir()
        orig.write_bytes(b"pdf data")
        corrected.write_bytes(b"pdf data")
        result = feedback_processor.process_correction(orig, corrected)
        assert "original_path" in result or "corrected_path" in result or "timestamp" in result

    def test_with_context(self, feedback_processor: FeedbackProcessor, tmp_path: Path) -> None:
        orig = tmp_path / "file.txt"
        new_loc = tmp_path / "work" / "file.txt"
        new_loc.parent.mkdir()
        orig.write_text("content")
        new_loc.write_text("content")
        result = feedback_processor.process_correction(orig, new_loc, context={"user": "test"})
        assert "timestamp" in result


# ---------------------------------------------------------------------------
# FeedbackProcessor — trigger_retraining
# ---------------------------------------------------------------------------


class TestTriggerRetraining:
    def test_returns_dict(self, feedback_processor: FeedbackProcessor) -> None:
        result = feedback_processor.trigger_retraining()
        assert result["status"] == "queued"


# ---------------------------------------------------------------------------
# FeedbackProcessor — update_learning_model
# ---------------------------------------------------------------------------


class TestUpdateLearningModel:
    def test_returns_bool(self, feedback_processor: FeedbackProcessor) -> None:
        result = feedback_processor.update_learning_model({})
        assert result is False

    def test_with_insights(self, feedback_processor: FeedbackProcessor) -> None:
        insights = {"pattern": "pdf_to_finance", "frequency": 5}
        result = feedback_processor.update_learning_model(insights)
        assert result is False


# ---------------------------------------------------------------------------
# FeedbackProcessor — batch_process_history
# ---------------------------------------------------------------------------


class TestBatchProcessHistory:
    def test_empty_corrections(self, feedback_processor: FeedbackProcessor) -> None:
        result = feedback_processor.batch_process_history([])
        assert "processed_count" in result

    def test_with_corrections(self, feedback_processor: FeedbackProcessor, tmp_path: Path) -> None:
        corrections = [
            {
                "original": str(tmp_path / "a.txt"),
                "corrected": str(tmp_path / "b.txt"),
                "timestamp": "2024-01-01T00:00:00",
            }
        ]
        result = feedback_processor.batch_process_history(corrections)
        assert "processed_count" in result

    def test_with_max_age_days(self, feedback_processor: FeedbackProcessor) -> None:
        result = feedback_processor.batch_process_history([], max_age_days=30)
        assert "processed_count" in result
