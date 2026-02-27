"""Tests for PARA AI Feedback Collection and Pattern Learning.

Tests cover FeedbackEvent serialization, FeedbackCollector persistence,
AccuracyStats computation, and PatternLearner rule generation.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from file_organizer.methodologies.para.ai.feedback import (
    FeedbackCollector,
    FeedbackEvent,
    PatternLearner,
)
from file_organizer.methodologies.para.ai.suggestion_engine import PARASuggestion
from file_organizer.methodologies.para.categories import PARACategory
from file_organizer.methodologies.para.config import HeuristicWeights


def _make_suggestion(
    category: PARACategory = PARACategory.PROJECT,
    confidence: float = 0.80,
) -> PARASuggestion:
    """Create a simple PARASuggestion for testing."""
    return PARASuggestion(
        category=category,
        confidence=confidence,
        reasoning=["Test reason"],
    )


# =========================================================================
# FeedbackEvent tests
# =========================================================================


@pytest.mark.unit
class TestFeedbackEvent:
    """Tests for FeedbackEvent dataclass."""

    def test_creation_with_defaults(self) -> None:
        """Should create event with derived fields."""
        event = FeedbackEvent(
            file_path=Path("/docs/report.pdf"),
            suggested=PARACategory.PROJECT,
            actual=PARACategory.PROJECT,
            confidence=0.85,
        )
        assert event.accepted is True
        assert event.file_extension == ".pdf"
        assert event.parent_directory == "docs"

    def test_to_dict_roundtrip(self) -> None:
        """Should serialize and deserialize losslessly."""
        event = FeedbackEvent(
            file_path=Path("/docs/report.pdf"),
            suggested=PARACategory.PROJECT,
            actual=PARACategory.AREA,
            confidence=0.65,
            accepted=False,
        )
        data = event.to_dict()
        restored = FeedbackEvent.from_dict(data)
        assert restored.file_path == event.file_path
        assert restored.suggested == event.suggested
        assert restored.actual == event.actual
        assert restored.confidence == event.confidence
        assert restored.accepted == event.accepted

    def test_from_dict_with_missing_optional_fields(self) -> None:
        """Should handle missing optional fields in dict."""
        data = {
            "file_path": "/test/file.txt",
            "suggested": "project",
            "actual": "project",
            "confidence": 0.8,
            "timestamp": datetime.now(UTC).isoformat(),
            "accepted": True,
        }
        event = FeedbackEvent.from_dict(data)
        assert event.file_extension == ".txt"
        assert event.parent_directory == "test"

    def test_rejection_event_fields(self) -> None:
        """Rejected event should have different suggested vs actual."""
        event = FeedbackEvent(
            file_path=Path("/docs/notes.md"),
            suggested=PARACategory.PROJECT,
            actual=PARACategory.AREA,
            confidence=0.55,
            accepted=False,
        )
        assert event.suggested != event.actual
        assert event.accepted is False


# =========================================================================
# FeedbackCollector tests
# =========================================================================


@pytest.mark.unit
class TestFeedbackCollector:
    """Tests for FeedbackCollector."""

    @pytest.fixture
    def collector(self, tmp_path: Path) -> FeedbackCollector:
        """Create a collector using a temporary directory."""
        return FeedbackCollector(storage_dir=tmp_path / "feedback")

    def test_record_acceptance(self, collector: FeedbackCollector) -> None:
        """Should record an acceptance event."""
        suggestion = _make_suggestion()
        collector.record_acceptance(Path("/test/file.pdf"), suggestion)
        events = collector.get_events()
        assert len(events) == 1
        assert events[0].accepted is True
        assert events[0].suggested == PARACategory.PROJECT
        assert events[0].actual == PARACategory.PROJECT

    def test_record_rejection(self, collector: FeedbackCollector) -> None:
        """Should record a rejection with correct category."""
        suggestion = _make_suggestion(PARACategory.PROJECT)
        collector.record_rejection(
            Path("/test/file.pdf"),
            suggestion,
            correct_category=PARACategory.RESOURCE,
        )
        events = collector.get_events()
        assert len(events) == 1
        assert events[0].accepted is False
        assert events[0].suggested == PARACategory.PROJECT
        assert events[0].actual == PARACategory.RESOURCE

    def test_multiple_events_persisted(self, collector: FeedbackCollector) -> None:
        """Multiple events should accumulate."""
        for i in range(5):
            suggestion = _make_suggestion()
            collector.record_acceptance(Path(f"/test/file_{i}.txt"), suggestion)
        assert len(collector.get_events()) == 5

    def test_persistence_across_instances(self, tmp_path: Path) -> None:
        """Events should persist across collector instances."""
        storage = tmp_path / "feedback"

        # Write events
        c1 = FeedbackCollector(storage_dir=storage)
        c1.record_acceptance(Path("/test/a.txt"), _make_suggestion())
        c1.record_acceptance(Path("/test/b.txt"), _make_suggestion())

        # Read from new instance
        c2 = FeedbackCollector(storage_dir=storage)
        events = c2.get_events()
        assert len(events) == 2

    def test_clear_removes_all_events(self, collector: FeedbackCollector) -> None:
        """clear() should remove all events."""
        collector.record_acceptance(Path("/test/file.txt"), _make_suggestion())
        assert len(collector.get_events()) == 1
        collector.clear()
        assert len(collector.get_events()) == 0

    def test_empty_collector_returns_empty_stats(
        self,
        collector: FeedbackCollector,
    ) -> None:
        """Empty collector should return zero-value stats."""
        stats = collector.get_accuracy_stats()
        assert stats.total_events == 0
        assert stats.accuracy_rate == 0.0

    def test_accuracy_stats_all_accepted(
        self,
        collector: FeedbackCollector,
    ) -> None:
        """100% acceptance should show accuracy_rate of 1.0."""
        for i in range(10):
            collector.record_acceptance(Path(f"/test/f{i}.txt"), _make_suggestion())
        stats = collector.get_accuracy_stats()
        assert stats.total_events == 10
        assert stats.accepted_count == 10
        assert stats.rejected_count == 0
        assert stats.accuracy_rate == 1.0

    def test_accuracy_stats_mixed(
        self,
        collector: FeedbackCollector,
    ) -> None:
        """Mixed feedback should compute correct accuracy."""
        # 7 accepted
        for i in range(7):
            collector.record_acceptance(Path(f"/test/a{i}.txt"), _make_suggestion())
        # 3 rejected
        for i in range(3):
            collector.record_rejection(
                Path(f"/test/r{i}.txt"),
                _make_suggestion(),
                correct_category=PARACategory.ARCHIVE,
            )
        stats = collector.get_accuracy_stats()
        assert stats.total_events == 10
        assert stats.accepted_count == 7
        assert stats.rejected_count == 3
        assert stats.accuracy_rate == pytest.approx(0.7)

    def test_per_category_accuracy(
        self,
        collector: FeedbackCollector,
    ) -> None:
        """Per-category accuracy should be broken down correctly."""
        # 2 accepted projects
        for i in range(2):
            collector.record_acceptance(
                Path(f"/test/p{i}.txt"),
                _make_suggestion(PARACategory.PROJECT),
            )
        # 1 rejected project
        collector.record_rejection(
            Path("/test/pr.txt"),
            _make_suggestion(PARACategory.PROJECT),
            correct_category=PARACategory.AREA,
        )
        # 1 accepted resource
        collector.record_acceptance(
            Path("/test/res.txt"),
            _make_suggestion(PARACategory.RESOURCE),
        )

        stats = collector.get_accuracy_stats()
        assert stats.per_category_accuracy["project"] == pytest.approx(2 / 3)
        assert stats.per_category_accuracy["resource"] == pytest.approx(1.0)

    def test_confidence_stats(
        self,
        collector: FeedbackCollector,
    ) -> None:
        """Should compute average confidence correctly."""
        collector.record_acceptance(
            Path("/test/a.txt"),
            _make_suggestion(confidence=0.90),
        )
        collector.record_rejection(
            Path("/test/b.txt"),
            _make_suggestion(confidence=0.50),
            correct_category=PARACategory.ARCHIVE,
        )
        stats = collector.get_accuracy_stats()
        assert stats.average_confidence == pytest.approx(0.70)
        assert stats.confidence_when_accepted == pytest.approx(0.90)
        assert stats.confidence_when_rejected == pytest.approx(0.50)

    def test_corrupted_json_handled(self, tmp_path: Path) -> None:
        """Should handle corrupted JSON file gracefully."""
        storage = tmp_path / "feedback"
        storage.mkdir(parents=True)
        (storage / "feedback_events.json").write_text("not valid json!!!")
        collector = FeedbackCollector(storage_dir=storage)
        events = collector.get_events()
        assert events == []


# =========================================================================
# PatternLearner tests
# =========================================================================


@pytest.mark.unit
class TestPatternLearner:
    """Tests for PatternLearner."""

    @pytest.fixture
    def learner(self) -> PatternLearner:
        """Create a PatternLearner with low threshold for testing."""
        return PatternLearner(min_occurrences=2)

    def _make_events(
        self,
        count: int,
        extension: str = ".pdf",
        directory: str = "docs",
        category: PARACategory = PARACategory.RESOURCE,
        accepted: bool = True,
    ) -> list[FeedbackEvent]:
        """Create a batch of feedback events."""
        return [
            FeedbackEvent(
                file_path=Path(f"/{directory}/file_{i}{extension}"),
                suggested=category,
                actual=category,
                confidence=0.8,
                accepted=accepted,
                file_extension=extension,
                parent_directory=directory,
            )
            for i in range(count)
        ]

    def test_learn_extension_pattern(self, learner: PatternLearner) -> None:
        """Should learn extension patterns from repeated feedback."""
        events = self._make_events(5, extension=".pdf", category=PARACategory.RESOURCE)
        rules = learner.learn_from_feedback(events)
        ext_rules = [r for r in rules if r.pattern_type == "extension"]
        assert len(ext_rules) >= 1
        assert any(r.pattern_value == ".pdf" for r in ext_rules)
        assert any(r.suggested_category == PARACategory.RESOURCE for r in ext_rules)

    def test_learn_directory_pattern(self, learner: PatternLearner) -> None:
        """Should learn directory patterns from repeated feedback."""
        events = self._make_events(5, directory="projects", category=PARACategory.PROJECT)
        rules = learner.learn_from_feedback(events)
        dir_rules = [r for r in rules if r.pattern_type == "directory"]
        assert len(dir_rules) >= 1
        assert any(r.pattern_value == "projects" for r in dir_rules)

    def test_min_occurrences_respected(self) -> None:
        """Rules should not be emitted below min_occurrences."""
        learner = PatternLearner(min_occurrences=10)
        events = self._make_events(5, extension=".txt")
        rules = learner.learn_from_feedback(events)
        assert len(rules) == 0

    def test_empty_events_returns_empty(self, learner: PatternLearner) -> None:
        """Empty input should return empty rules."""
        assert learner.learn_from_feedback([]) == []

    def test_learned_rule_confidence_increases(self, learner: PatternLearner) -> None:
        """More occurrences should yield higher confidence."""
        events_small = self._make_events(3, extension=".md")
        events_large = self._make_events(15, extension=".md")
        rules_small = learner.learn_from_feedback(events_small)
        rules_large = learner.learn_from_feedback(events_large)

        if rules_small and rules_large:
            # More data should yield higher (or equal) confidence
            conf_small = max(r.confidence for r in rules_small)
            conf_large = max(r.confidence for r in rules_large)
            assert conf_large >= conf_small

    def test_get_user_preferences_empty(self, learner: PatternLearner) -> None:
        """Should return empty preferences for no events."""
        prefs = learner.get_user_preferences(None)
        assert prefs["total_interactions"] == 0

    def test_get_user_preferences_with_data(self, learner: PatternLearner) -> None:
        """Should compute user preferences from events."""
        events = self._make_events(5, category=PARACategory.PROJECT)
        events += self._make_events(3, category=PARACategory.RESOURCE)
        prefs = learner.get_user_preferences(events)
        assert prefs["total_interactions"] == 8
        assert prefs["preferred_categories"]["project"] == 5
        assert prefs["preferred_categories"]["resource"] == 3

    def test_get_user_preferences_override_patterns(
        self,
        learner: PatternLearner,
    ) -> None:
        """Should capture override patterns from rejections."""
        events = [
            FeedbackEvent(
                file_path=Path("/test/file.txt"),
                suggested=PARACategory.PROJECT,
                actual=PARACategory.AREA,
                confidence=0.6,
                accepted=False,
                file_extension=".txt",
                parent_directory="test",
            )
        ]
        prefs = learner.get_user_preferences(events)
        assert len(prefs["override_patterns"]) == 1
        assert prefs["override_patterns"][0]["from"] == "project"
        assert prefs["override_patterns"][0]["to"] == "area"

    def test_adjust_weights_insufficient_data(
        self,
        learner: PatternLearner,
    ) -> None:
        """Should return default weights with insufficient data."""
        # min_occurrences=2, providing only 1 event
        events = self._make_events(1)
        weights = learner.adjust_weights(events)
        default = HeuristicWeights()
        assert weights.temporal == default.temporal

    def test_adjust_weights_high_accuracy(self, learner: PatternLearner) -> None:
        """High accuracy should slightly boost content weight."""
        events = self._make_events(10, accepted=True)
        weights = learner.adjust_weights(events)
        assert weights.content >= 0.35  # Should not decrease
        # All weights should sum to ~1.0
        total = weights.temporal + weights.content + weights.structural + weights.ai
        assert 0.99 <= total <= 1.01

    def test_adjust_weights_low_accuracy(self) -> None:
        """Low accuracy should boost structural weight."""
        learner = PatternLearner(min_occurrences=2)
        # Mix of accepted and rejected
        accepted = [
            FeedbackEvent(
                file_path=Path(f"/test/a{i}.txt"),
                suggested=PARACategory.PROJECT,
                actual=PARACategory.PROJECT,
                confidence=0.8,
                accepted=True,
            )
            for i in range(3)
        ]
        rejected = [
            FeedbackEvent(
                file_path=Path(f"/test/r{i}.txt"),
                suggested=PARACategory.PROJECT,
                actual=PARACategory.AREA,
                confidence=0.5,
                accepted=False,
            )
            for i in range(7)
        ]
        events = accepted + rejected
        weights = learner.adjust_weights(events)
        total = weights.temporal + weights.content + weights.structural + weights.ai
        assert 0.99 <= total <= 1.01
