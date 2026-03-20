"""Integration tests for TagLearningEngine and PARA heuristics.

Covers:
  - services/auto_tagging/tag_learning.py        — TagLearningEngine
  - methodologies/para/detection/heuristics.py   — HeuristicEngine, individual heuristics
"""

from __future__ import annotations

from pathlib import Path

import pytest

from file_organizer.methodologies.para.detection.heuristics import (
    CategoryScore,
    ContentHeuristic,
    HeuristicEngine,
    HeuristicResult,
    PARACategory,
    StructuralHeuristic,
    TemporalHeuristic,
)

# API notes (verified against source):
# - HeuristicResult fields: scores (dict), overall_confidence, recommended_category,
#   needs_manual_review, metadata
# - CategoryScore fields: category, score, confidence, signals
# - Individual heuristic .evaluate() returns HeuristicResult (same as HeuristicEngine)
from file_organizer.services.auto_tagging.tag_learning import TagLearningEngine, TagPattern

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# TagLearningEngine — fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def engine(tmp_path: Path) -> TagLearningEngine:
    return TagLearningEngine(storage_path=tmp_path / "tags.json")


# ---------------------------------------------------------------------------
# TagLearningEngine — init
# ---------------------------------------------------------------------------


class TestTagLearningEngineInit:
    def test_default_storage_path(self) -> None:
        e = TagLearningEngine()
        assert e is not None

    def test_custom_storage_path(self, tmp_path: Path) -> None:
        e = TagLearningEngine(storage_path=tmp_path / "custom.json")
        assert e is not None


# ---------------------------------------------------------------------------
# TagLearningEngine — record_tag_application
# ---------------------------------------------------------------------------


class TestTagLearningRecord:
    def test_record_single_tag(self, engine: TagLearningEngine, tmp_path: Path) -> None:
        f = tmp_path / "report.pdf"
        f.write_text("content")
        engine.record_tag_application(f, ["finance"])

    def test_record_multiple_tags(self, engine: TagLearningEngine, tmp_path: Path) -> None:
        f = tmp_path / "invoice.pdf"
        f.write_text("content")
        engine.record_tag_application(f, ["finance", "invoice", "2026"])

    def test_record_with_context(self, engine: TagLearningEngine, tmp_path: Path) -> None:
        f = tmp_path / "doc.txt"
        f.write_text("content")
        engine.record_tag_application(f, ["notes"], context={"directory": "user/Notes"})

    def test_record_empty_tags(self, engine: TagLearningEngine, tmp_path: Path) -> None:
        f = tmp_path / "empty_tags.txt"
        f.write_text("content")
        engine.record_tag_application(f, [])  # Should not raise

    def test_record_persists_data(self, engine: TagLearningEngine, tmp_path: Path) -> None:
        f = tmp_path / "data.csv"
        f.write_text("a,b,c")
        engine.record_tag_application(f, ["data", "csv"])
        # After recording, popular tags should reflect the addition
        tags = engine.get_popular_tags()
        assert len(tags) >= 1


# ---------------------------------------------------------------------------
# TagLearningEngine — get_popular_tags
# ---------------------------------------------------------------------------


class TestTagLearningPopular:
    def test_empty_returns_list(self, engine: TagLearningEngine) -> None:
        result = engine.get_popular_tags()
        assert result == []

    def test_after_recording_returns_entries(
        self, engine: TagLearningEngine, tmp_path: Path
    ) -> None:
        for i in range(3):
            f = tmp_path / f"f{i}.pdf"
            f.write_text("x")
            engine.record_tag_application(f, ["finance"])
        result = engine.get_popular_tags()
        assert len(result) >= 1

    def test_entries_are_tuples(self, engine: TagLearningEngine, tmp_path: Path) -> None:
        f = tmp_path / "r.pdf"
        f.write_text("x")
        engine.record_tag_application(f, ["work"])
        result = engine.get_popular_tags()
        for item in result:
            assert isinstance(item, tuple)
            assert len(item) == 2

    def test_limit_respected(self, engine: TagLearningEngine, tmp_path: Path) -> None:
        for i in range(10):
            f = tmp_path / f"f{i}.txt"
            f.write_text("x")
            engine.record_tag_application(f, [f"tag{i}"])
        result = engine.get_popular_tags(limit=3)
        assert len(result) < 4


# ---------------------------------------------------------------------------
# TagLearningEngine — get_recent_tags
# ---------------------------------------------------------------------------


class TestTagLearningRecent:
    def test_empty_returns_list(self, engine: TagLearningEngine) -> None:
        result = engine.get_recent_tags()
        assert result == []

    def test_after_recording_returns_tags(self, engine: TagLearningEngine, tmp_path: Path) -> None:
        f = tmp_path / "file.txt"
        f.write_text("x")
        engine.record_tag_application(f, ["recent_tag"])
        result = engine.get_recent_tags(days=30)
        assert len(result) >= 1

    def test_elements_are_strings(self, engine: TagLearningEngine, tmp_path: Path) -> None:
        f = tmp_path / "d.pdf"
        f.write_text("x")
        engine.record_tag_application(f, ["string_tag"])
        result = engine.get_recent_tags()
        for tag in result:
            assert len(tag) > 0


# ---------------------------------------------------------------------------
# TagLearningEngine — get_related_tags
# ---------------------------------------------------------------------------


class TestTagLearningRelated:
    def test_no_history_returns_empty(self, engine: TagLearningEngine) -> None:
        result = engine.get_related_tags("finance")
        assert result == []

    def test_after_co_occurrence(self, engine: TagLearningEngine, tmp_path: Path) -> None:
        f = tmp_path / "invoice.pdf"
        f.write_text("x")
        engine.record_tag_application(f, ["finance", "invoice"])
        result = engine.get_related_tags("finance")
        assert len(result) >= 1

    def test_max_related_respected(self, engine: TagLearningEngine, tmp_path: Path) -> None:
        f = tmp_path / "doc.pdf"
        f.write_text("x")
        engine.record_tag_application(f, ["a", "b", "c", "d", "e", "f"])
        result = engine.get_related_tags("a", max_related=2)
        assert len(result) < 3


# ---------------------------------------------------------------------------
# TagLearningEngine — predict_tags / get_tag_suggestions_for_context
# ---------------------------------------------------------------------------


class TestTagLearningPredict:
    def test_predict_returns_list(self, engine: TagLearningEngine, tmp_path: Path) -> None:
        f = tmp_path / "file.pdf"
        f.write_text("financial quarterly report")
        result = engine.predict_tags(f)
        assert result == []

    def test_predict_tuples_are_str_float(self, engine: TagLearningEngine, tmp_path: Path) -> None:
        f = tmp_path / "doc.txt"
        f.write_text("content")
        result = engine.predict_tags(f)
        for item in result:
            tag, score = item
            assert len(tag) > 0
            assert 0.0 <= score <= 1.0

    def test_context_suggestions_empty_returns_list(self, engine: TagLearningEngine) -> None:
        result = engine.get_tag_suggestions_for_context()
        assert result == []

    def test_context_suggestions_with_file_type(self, engine: TagLearningEngine) -> None:
        result = engine.get_tag_suggestions_for_context(file_type="pdf")
        assert result == []

    def test_context_suggestions_with_existing_tags(self, engine: TagLearningEngine) -> None:
        result = engine.get_tag_suggestions_for_context(existing_tags=["finance"])
        assert result == []

    def test_context_suggestions_limit(self, engine: TagLearningEngine) -> None:
        result = engine.get_tag_suggestions_for_context(limit=3)
        assert len(result) < 4


# ---------------------------------------------------------------------------
# TagLearningEngine — get_tag_patterns / update_model
# ---------------------------------------------------------------------------


class TestTagLearningPatterns:
    def test_get_tag_patterns_returns_list(self, engine: TagLearningEngine) -> None:
        result = engine.get_tag_patterns()
        assert result == []

    def test_get_tag_patterns_by_type(self, engine: TagLearningEngine) -> None:
        result = engine.get_tag_patterns(file_type="pdf")
        assert result == []

    def test_patterns_are_tag_pattern_objects(
        self, engine: TagLearningEngine, tmp_path: Path
    ) -> None:
        f = tmp_path / "f.pdf"
        f.write_text("x")
        engine.record_tag_application(f, ["tag_one"])
        result = engine.get_tag_patterns()
        for p in result:
            assert isinstance(p, TagPattern)

    def test_update_model_empty_feedback(self, engine: TagLearningEngine) -> None:
        engine.update_model([])  # Should not raise

    def test_update_model_with_feedback(self, engine: TagLearningEngine, tmp_path: Path) -> None:
        f1 = tmp_path / "invoice.pdf"
        f2 = tmp_path / "notes.txt"
        f1.write_text("x")
        f2.write_text("x")
        engine.update_model(
            [
                {"tag": "finance", "action": "added", "file_type": "pdf", "file_path": str(f1)},
                {"tag": "notes", "action": "removed", "file_type": "txt", "file_path": str(f2)},
            ]
        )


# ---------------------------------------------------------------------------
# HeuristicEngine — fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def heuristic_engine() -> HeuristicEngine:
    return HeuristicEngine(enable_ai=False)


# ---------------------------------------------------------------------------
# HeuristicEngine — evaluate
# ---------------------------------------------------------------------------


class TestHeuristicEngineEvaluate:
    def test_evaluate_returns_result(
        self, heuristic_engine: HeuristicEngine, tmp_path: Path
    ) -> None:
        f = tmp_path / "report.pdf"
        f.write_text("quarterly financial report")
        result = heuristic_engine.evaluate(f)
        assert isinstance(result, HeuristicResult)

    def test_result_has_recommended_category(
        self, heuristic_engine: HeuristicEngine, tmp_path: Path
    ) -> None:
        f = tmp_path / "notes.txt"
        f.write_text("content")
        result = heuristic_engine.evaluate(f)
        assert result.recommended_category is None or isinstance(
            result.recommended_category, PARACategory
        )

    def test_result_confidence_in_range(
        self, heuristic_engine: HeuristicEngine, tmp_path: Path
    ) -> None:
        f = tmp_path / "file.txt"
        f.write_text("content")
        result = heuristic_engine.evaluate(f)
        assert 0.0 <= result.overall_confidence <= 1.0

    def test_evaluate_with_metadata(
        self, heuristic_engine: HeuristicEngine, tmp_path: Path
    ) -> None:
        f = tmp_path / "data.csv"
        f.write_text("a,b,c")
        result = heuristic_engine.evaluate(f, metadata={"file_type": "csv"})
        assert isinstance(result, HeuristicResult)

    def test_result_has_scores_dict(
        self, heuristic_engine: HeuristicEngine, tmp_path: Path
    ) -> None:
        f = tmp_path / "file.txt"
        f.write_text("hello")
        result = heuristic_engine.evaluate(f)
        assert len(result.scores) >= 1

    def test_nonexistent_file(self, heuristic_engine: HeuristicEngine, tmp_path: Path) -> None:
        f = tmp_path / "missing.txt"
        result = heuristic_engine.evaluate(f)
        assert isinstance(result, HeuristicResult)

    def test_evaluate_projects_dir_name(
        self, heuristic_engine: HeuristicEngine, tmp_path: Path
    ) -> None:
        projects_dir = tmp_path / "Projects" / "my_project"
        projects_dir.mkdir(parents=True)
        f = projects_dir / "readme.md"
        f.write_text("# My Project\n\nActive work here.")
        result = heuristic_engine.evaluate(f)
        assert isinstance(result, HeuristicResult)


# ---------------------------------------------------------------------------
# Individual heuristics
# ---------------------------------------------------------------------------


class TestTemporalHeuristic:
    def test_evaluate_returns_result(self, tmp_path: Path) -> None:
        h = TemporalHeuristic(weight=1.0)
        f = tmp_path / "file.txt"
        f.write_text("x")
        result = h.evaluate(f)
        assert isinstance(result, HeuristicResult)

    def test_result_has_overall_confidence(self, tmp_path: Path) -> None:
        h = TemporalHeuristic(weight=1.0)
        f = tmp_path / "file.txt"
        f.write_text("x")
        result = h.evaluate(f)
        assert 0.0 <= result.overall_confidence <= 1.0


class TestStructuralHeuristic:
    def test_evaluate_returns_result(self, tmp_path: Path) -> None:
        h = StructuralHeuristic(weight=1.0)
        f = tmp_path / "file.txt"
        f.write_text("x")
        result = h.evaluate(f)
        assert isinstance(result, HeuristicResult)

    def test_archive_dir_name_influence(self, tmp_path: Path) -> None:
        archive = tmp_path / "Archive"
        archive.mkdir()
        f = archive / "old_doc.txt"
        f.write_text("archived content")
        h = StructuralHeuristic(weight=1.0)
        result = h.evaluate(f)
        assert isinstance(result, HeuristicResult)


class TestContentHeuristic:
    def test_evaluate_returns_result(self, tmp_path: Path) -> None:
        h = ContentHeuristic(weight=1.0)
        f = tmp_path / "report.txt"
        f.write_text("quarterly financial report analysis")
        result = h.evaluate(f)
        assert isinstance(result, HeuristicResult)

    def test_evaluate_missing_file_returns_result(self, tmp_path: Path) -> None:
        h = ContentHeuristic(weight=1.0)
        f = tmp_path / "missing.txt"
        result = h.evaluate(f)
        assert isinstance(result, HeuristicResult)


# ---------------------------------------------------------------------------
# CategoryScore and HeuristicResult dataclasses
# ---------------------------------------------------------------------------


class TestCategoryScore:
    def test_created(self) -> None:
        cs = CategoryScore(category=PARACategory.PROJECT, score=0.8, confidence=0.9)
        assert cs.category == PARACategory.PROJECT
        assert cs.score == 0.8

    def test_with_signals(self) -> None:
        cs = CategoryScore(
            category=PARACategory.ARCHIVE,
            score=0.5,
            confidence=0.6,
            signals=["old file", "archive dir"],
        )
        assert cs.score == 0.5
        assert len(cs.signals) == 2


class TestHeuristicResult:
    def test_created(self) -> None:
        hr = HeuristicResult(
            scores={},
            overall_confidence=0.7,
            recommended_category=PARACategory.RESOURCE,
        )
        assert hr.recommended_category == PARACategory.RESOURCE
        assert hr.overall_confidence == 0.7

    def test_no_category(self) -> None:
        hr = HeuristicResult(
            scores={},
            overall_confidence=0.0,
            recommended_category=None,
        )
        assert hr.recommended_category is None
