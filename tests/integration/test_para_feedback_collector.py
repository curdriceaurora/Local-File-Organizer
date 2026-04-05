"""Integration tests for PARA feedback collection and pattern learning.

Covers FeedbackEvent, AccuracyStats, LearnedRule, FeedbackCollector,
and PatternLearner — all pure Python with local JSON persistence.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.ci]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_suggestion(category: Any, confidence: float = 0.8) -> Any:
    """Build a minimal object that quacks like PARASuggestion."""
    from file_organizer.methodologies.para.ai.suggestion_engine import PARASuggestion

    return PARASuggestion(category=category, confidence=confidence)


# ---------------------------------------------------------------------------
# FeedbackEvent
# ---------------------------------------------------------------------------


class TestFeedbackEvent:
    """Tests for FeedbackEvent dataclass."""

    def test_to_dict_round_trip(self, tmp_path: Path) -> None:
        """FeedbackEvent.to_dict() / from_dict() round-trips all fields."""
        from file_organizer.methodologies.para.ai.feedback import FeedbackEvent
        from file_organizer.methodologies.para.categories import PARACategory

        file_path = tmp_path / "docs" / "report.pdf"
        ts = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)

        event = FeedbackEvent(
            file_path=file_path,
            suggested=PARACategory.PROJECT,
            actual=PARACategory.RESOURCE,
            confidence=0.72,
            timestamp=ts,
            accepted=False,
            file_extension=".pdf",
            parent_directory="docs",
        )

        d = event.to_dict()
        assert d["file_path"] == str(file_path)
        assert d["suggested"] == "project"
        assert d["actual"] == "resource"
        assert d["confidence"] == 0.72
        assert d["accepted"] is False
        assert d["file_extension"] == ".pdf"
        assert d["parent_directory"] == "docs"

        restored = FeedbackEvent.from_dict(d)
        assert restored.file_path == file_path
        assert restored.suggested == PARACategory.PROJECT
        assert restored.actual == PARACategory.RESOURCE
        assert restored.confidence == 0.72
        assert restored.accepted is False
        assert restored.file_extension == ".pdf"
        assert restored.parent_directory == "docs"
        assert restored.timestamp == ts

    def test_timestamp_auto_set_when_none_is_not_possible(self) -> None:
        """timestamp has a default_factory so it is always set at construction."""
        from file_organizer.methodologies.para.ai.feedback import FeedbackEvent
        from file_organizer.methodologies.para.categories import PARACategory

        before = datetime.now(UTC)
        event = FeedbackEvent(
            file_path=Path("/mock/file.txt"),
            suggested=PARACategory.AREA,
            actual=PARACategory.AREA,
            confidence=0.5,
        )
        after = datetime.now(UTC)

        assert event.timestamp is not None
        assert before <= event.timestamp <= after

    def test_post_init_sets_extension_from_file_path(self) -> None:
        """__post_init__ derives file_extension from file_path when not provided."""
        from file_organizer.methodologies.para.ai.feedback import FeedbackEvent
        from file_organizer.methodologies.para.categories import PARACategory

        event = FeedbackEvent(
            file_path=Path("/mock/projects/budget.xlsx"),
            suggested=PARACategory.PROJECT,
            actual=PARACategory.PROJECT,
            confidence=0.9,
        )

        assert event.file_extension == ".xlsx"

    def test_post_init_sets_parent_directory_from_file_path(self) -> None:
        """__post_init__ derives parent_directory from file_path when not provided."""
        from file_organizer.methodologies.para.ai.feedback import FeedbackEvent
        from file_organizer.methodologies.para.categories import PARACategory

        event = FeedbackEvent(
            file_path=Path("/mock/invoices/q3.pdf"),
            suggested=PARACategory.RESOURCE,
            actual=PARACategory.RESOURCE,
            confidence=0.75,
        )

        assert event.parent_directory == "invoices"

    def test_post_init_does_not_overwrite_explicit_extension(self) -> None:
        """__post_init__ skips deriving fields when they are already supplied."""
        from file_organizer.methodologies.para.ai.feedback import FeedbackEvent
        from file_organizer.methodologies.para.categories import PARACategory

        event = FeedbackEvent(
            file_path=Path("/mock/data/file.pdf"),
            suggested=PARACategory.AREA,
            actual=PARACategory.AREA,
            confidence=0.6,
            file_extension=".custom",
            parent_directory="override_dir",
        )

        assert event.file_extension == ".custom"
        assert event.parent_directory == "override_dir"

    def test_from_dict_handles_missing_optional_fields(self) -> None:
        """from_dict tolerates missing file_extension / parent_directory keys.

        When those keys are absent from the serialised dict, from_dict passes
        empty strings to the constructor.  __post_init__ then derives them from
        file_path, so the final fields will reflect the path — this is the
        correct, expected behaviour.
        """
        from file_organizer.methodologies.para.ai.feedback import FeedbackEvent
        from file_organizer.methodologies.para.categories import PARACategory

        ts = datetime(2024, 1, 1, tzinfo=UTC)
        data = {
            "file_path": "/mock/docs/file.txt",
            "suggested": "archive",
            "actual": "archive",
            "confidence": 0.55,
            "timestamp": ts.isoformat(),
            "accepted": True,
        }

        event = FeedbackEvent.from_dict(data)
        # __post_init__ derives extension and directory from file_path
        assert event.file_extension == ".txt"
        assert event.parent_directory == "docs"
        assert event.suggested == PARACategory.ARCHIVE


# ---------------------------------------------------------------------------
# FeedbackCollector
# ---------------------------------------------------------------------------


class TestFeedbackCollector:
    """Tests for FeedbackCollector persistence and query methods."""

    def test_record_acceptance_then_get_events(self, tmp_path: Path) -> None:
        """record_acceptance stores an event that get_events returns."""
        from file_organizer.methodologies.para.ai.feedback import FeedbackCollector
        from file_organizer.methodologies.para.categories import PARACategory

        collector = FeedbackCollector(storage_dir=tmp_path)
        suggestion = _make_suggestion(PARACategory.PROJECT, confidence=0.85)

        collector.record_acceptance(Path("/mock/sprint.md"), suggestion)

        events = collector.get_events()
        assert len(events) == 1
        assert events[0].accepted is True
        assert events[0].suggested == PARACategory.PROJECT
        assert events[0].actual == PARACategory.PROJECT
        assert events[0].confidence == 0.85

    def test_record_rejection_with_correction(self, tmp_path: Path) -> None:
        """record_rejection stores a rejection event with the corrected category."""
        from file_organizer.methodologies.para.ai.feedback import FeedbackCollector
        from file_organizer.methodologies.para.categories import PARACategory

        collector = FeedbackCollector(storage_dir=tmp_path)
        suggestion = _make_suggestion(PARACategory.PROJECT, confidence=0.65)

        collector.record_rejection(
            Path("/mock/reference.pdf"),
            suggestion,
            correct_category=PARACategory.RESOURCE,
        )

        events = collector.get_events()
        assert len(events) == 1
        assert events[0].accepted is False
        assert events[0].suggested == PARACategory.PROJECT
        assert events[0].actual == PARACategory.RESOURCE

    def test_get_accuracy_stats_counts(self, tmp_path: Path) -> None:
        """get_accuracy_stats reflects total, accepted, rejected counts and rate."""
        from file_organizer.methodologies.para.ai.feedback import FeedbackCollector
        from file_organizer.methodologies.para.categories import PARACategory

        collector = FeedbackCollector(storage_dir=tmp_path)
        sugg = _make_suggestion(PARACategory.AREA, confidence=0.7)

        # 3 acceptances, 1 rejection
        for _ in range(3):
            collector.record_acceptance(Path("/mock/file.txt"), sugg)
        collector.record_rejection(
            Path("/mock/other.txt"), sugg, correct_category=PARACategory.RESOURCE
        )

        stats = collector.get_accuracy_stats()
        assert stats.total_events == 4
        assert stats.accepted_count == 3
        assert stats.rejected_count == 1
        assert abs(stats.accuracy_rate - 0.75) < 1e-9

    def test_get_accuracy_stats_empty(self, tmp_path: Path) -> None:
        """get_accuracy_stats returns zeroed AccuracyStats when no events exist."""
        from file_organizer.methodologies.para.ai.feedback import AccuracyStats, FeedbackCollector

        collector = FeedbackCollector(storage_dir=tmp_path)
        stats = collector.get_accuracy_stats()

        assert isinstance(stats, AccuracyStats)
        assert stats.total_events == 0
        assert stats.accuracy_rate == 0.0

    def test_clear_empties_events(self, tmp_path: Path) -> None:
        """clear() removes all events; subsequent get_events() returns empty list."""
        from file_organizer.methodologies.para.ai.feedback import FeedbackCollector
        from file_organizer.methodologies.para.categories import PARACategory

        collector = FeedbackCollector(storage_dir=tmp_path)
        sugg = _make_suggestion(PARACategory.PROJECT)
        collector.record_acceptance(Path("/mock/file.txt"), sugg)
        assert len(collector.get_events()) == 1

        collector.clear()
        assert collector.get_events() == []
        # Also verify a fresh instance sees no events (proves clear() persisted to disk)
        fresh = FeedbackCollector(storage_dir=tmp_path)
        assert fresh.get_events() == []

    def test_persistence_across_instances(self, tmp_path: Path) -> None:
        """Events written by one FeedbackCollector are loaded by a new instance."""
        from file_organizer.methodologies.para.ai.feedback import FeedbackCollector
        from file_organizer.methodologies.para.categories import PARACategory

        collector1 = FeedbackCollector(storage_dir=tmp_path)
        sugg = _make_suggestion(PARACategory.ARCHIVE, confidence=0.9)
        collector1.record_acceptance(Path("/mock/old.pdf"), sugg)

        # New instance pointing to same directory
        collector2 = FeedbackCollector(storage_dir=tmp_path)
        events = collector2.get_events()

        assert len(events) == 1
        assert events[0].suggested == PARACategory.ARCHIVE
        assert events[0].confidence == 0.9

    def test_ensure_loaded_lazy_and_idempotent(self, tmp_path: Path) -> None:
        """_ensure_loaded loads on first call; the _loaded flag prevents double-load."""
        from file_organizer.methodologies.para.ai.feedback import FeedbackCollector
        from file_organizer.methodologies.para.categories import PARACategory

        # Seed storage with one event
        seed = FeedbackCollector(storage_dir=tmp_path)
        sugg = _make_suggestion(PARACategory.PROJECT)
        seed.record_acceptance(Path("/mock/seed.txt"), sugg)

        collector = FeedbackCollector(storage_dir=tmp_path)
        assert collector._loaded is False  # not yet loaded

        # First call loads
        collector._ensure_loaded()
        assert collector._loaded is True
        assert len(collector._events) == 1

        # Second call is a no-op — patch _load_events to verify it isn't invoked
        with patch.object(collector, "_load_events", side_effect=AssertionError("called twice")):
            collector._ensure_loaded()  # should not call _load_events again

    def test_multiple_events_persisted_and_loaded(self, tmp_path: Path) -> None:
        """Multiple events survive a write-load cycle with correct field values."""
        from file_organizer.methodologies.para.ai.feedback import FeedbackCollector
        from file_organizer.methodologies.para.categories import PARACategory

        collector = FeedbackCollector(storage_dir=tmp_path)
        sugg_proj = _make_suggestion(PARACategory.PROJECT, confidence=0.8)
        sugg_res = _make_suggestion(PARACategory.RESOURCE, confidence=0.6)

        collector.record_acceptance(Path("/mock/plan.md"), sugg_proj)
        collector.record_rejection(
            Path("/mock/ref.pdf"), sugg_proj, correct_category=PARACategory.RESOURCE
        )
        collector.record_acceptance(Path("/mock/guide.txt"), sugg_res)

        loaded = FeedbackCollector(storage_dir=tmp_path)
        events = loaded.get_events()

        assert len(events) == 3
        accepted = [e for e in events if e.accepted]
        rejected = [e for e in events if not e.accepted]
        assert len(accepted) == 2
        assert len(rejected) == 1

    def test_feedback_file_created_in_storage_dir(self, tmp_path: Path) -> None:
        """Recording an event creates feedback_events.json inside storage_dir."""
        from file_organizer.methodologies.para.ai.feedback import FeedbackCollector
        from file_organizer.methodologies.para.categories import PARACategory

        storage = tmp_path / "subdir"
        collector = FeedbackCollector(storage_dir=storage)
        sugg = _make_suggestion(PARACategory.AREA)
        collector.record_acceptance(Path("/mock/notes.txt"), sugg)

        assert (storage / "feedback_events.json").exists()

    def test_accuracy_stats_confidence_averages(self, tmp_path: Path) -> None:
        """get_accuracy_stats computes per-acceptance/rejection confidence averages."""
        from file_organizer.methodologies.para.ai.feedback import FeedbackCollector
        from file_organizer.methodologies.para.categories import PARACategory

        collector = FeedbackCollector(storage_dir=tmp_path)
        sugg_high = _make_suggestion(PARACategory.PROJECT, confidence=0.9)
        sugg_low = _make_suggestion(PARACategory.PROJECT, confidence=0.3)

        collector.record_acceptance(Path("/mock/a.txt"), sugg_high)
        collector.record_rejection(
            Path("/mock/b.txt"), sugg_low, correct_category=PARACategory.AREA
        )

        stats = collector.get_accuracy_stats()
        assert abs(stats.confidence_when_accepted - 0.9) < 1e-9
        assert abs(stats.confidence_when_rejected - 0.3) < 1e-9
        assert abs(stats.average_confidence - 0.6) < 1e-9

    def test_per_category_accuracy_in_stats(self, tmp_path: Path) -> None:
        """get_accuracy_stats includes per-category accuracy dict."""
        from file_organizer.methodologies.para.ai.feedback import FeedbackCollector
        from file_organizer.methodologies.para.categories import PARACategory

        collector = FeedbackCollector(storage_dir=tmp_path)
        sugg = _make_suggestion(PARACategory.RESOURCE, confidence=0.8)

        # 2 acceptances for RESOURCE
        collector.record_acceptance(Path("/mock/r1.pdf"), sugg)
        collector.record_acceptance(Path("/mock/r2.pdf"), sugg)

        stats = collector.get_accuracy_stats()
        assert "resource" in stats.per_category_accuracy
        assert stats.per_category_accuracy["resource"] == 1.0


# ---------------------------------------------------------------------------
# PatternLearner
# ---------------------------------------------------------------------------


class TestPatternLearner:
    """Tests for PatternLearner rule discovery and weight adjustment."""

    def _build_events(
        self,
        category: Any,
        extension: str,
        parent_dir: str,
        count: int,
        accepted: bool = True,
    ) -> list[Any]:
        """Return `count` FeedbackEvent objects for the given parameters."""
        from file_organizer.methodologies.para.ai.feedback import FeedbackEvent

        return [
            FeedbackEvent(
                file_path=Path(f"/mock/{parent_dir}/file_{i}{extension}"),
                suggested=category,
                actual=category,
                confidence=0.75,
                accepted=accepted,
                file_extension=extension,
                parent_directory=parent_dir,
            )
            for i in range(count)
        ]

    def test_learn_from_empty_events_returns_empty(self) -> None:
        """learn_from_feedback([]) returns an empty list."""
        from file_organizer.methodologies.para.ai.feedback import PatternLearner

        learner = PatternLearner(min_occurrences=3)
        rules = learner.learn_from_feedback([])
        assert rules == []

    def test_learn_extension_pattern_above_threshold(self) -> None:
        """Extension pattern emitted when occurrences >= min_occurrences."""
        from file_organizer.methodologies.para.ai.feedback import PatternLearner
        from file_organizer.methodologies.para.categories import PARACategory

        learner = PatternLearner(min_occurrences=3)
        events = self._build_events(PARACategory.PROJECT, ".md", "work", count=4)
        rules = learner.learn_from_feedback(events)

        ext_rules = [r for r in rules if r.pattern_type == "extension" and r.pattern_value == ".md"]
        assert len(ext_rules) == 1
        assert ext_rules[0].suggested_category == PARACategory.PROJECT
        assert ext_rules[0].occurrences == 4
        assert 0.0 < ext_rules[0].confidence <= 0.9

    def test_learn_extension_pattern_below_threshold(self) -> None:
        """Extension pattern not emitted when occurrences < min_occurrences."""
        from file_organizer.methodologies.para.ai.feedback import PatternLearner
        from file_organizer.methodologies.para.categories import PARACategory

        learner = PatternLearner(min_occurrences=5)
        events = self._build_events(PARACategory.AREA, ".pdf", "misc", count=3)
        rules = learner.learn_from_feedback(events)

        ext_rules = [r for r in rules if r.pattern_type == "extension"]
        assert ext_rules == []

    def test_learn_directory_pattern_above_threshold(self) -> None:
        """Directory pattern emitted when occurrences >= min_occurrences."""
        from file_organizer.methodologies.para.ai.feedback import PatternLearner
        from file_organizer.methodologies.para.categories import PARACategory

        learner = PatternLearner(min_occurrences=3)
        events = self._build_events(PARACategory.RESOURCE, ".txt", "references", count=5)
        rules = learner.learn_from_feedback(events)

        dir_rules = [
            r for r in rules if r.pattern_type == "directory" and r.pattern_value == "references"
        ]
        assert len(dir_rules) == 1
        assert dir_rules[0].suggested_category == PARACategory.RESOURCE
        assert dir_rules[0].occurrences == 5

    def test_learn_mixed_acceptance_and_rejection_events(self) -> None:
        """Rejected events use the actual category, not suggested."""
        from file_organizer.methodologies.para.ai.feedback import FeedbackEvent, PatternLearner
        from file_organizer.methodologies.para.categories import PARACategory

        learner = PatternLearner(min_occurrences=3)

        # 4 acceptances: .pdf → PROJECT (actual = PROJECT)
        acc_events = [
            FeedbackEvent(
                file_path=Path(f"/mock/work/doc{i}.pdf"),
                suggested=PARACategory.PROJECT,
                actual=PARACategory.PROJECT,
                confidence=0.8,
                accepted=True,
                file_extension=".pdf",
                parent_directory="work",
            )
            for i in range(4)
        ]
        # 4 rejections: suggested=PROJECT, actual=RESOURCE
        rej_events = [
            FeedbackEvent(
                file_path=Path(f"/mock/work/ref{i}.pdf"),
                suggested=PARACategory.PROJECT,
                actual=PARACategory.RESOURCE,
                confidence=0.5,
                accepted=False,
                file_extension=".pdf",
                parent_directory="work",
            )
            for i in range(4)
        ]

        rules = learner.learn_from_feedback(acc_events + rej_events)

        # Both (project, .pdf) and (resource, .pdf) meet threshold
        ext_categories = {r.suggested_category for r in rules if r.pattern_type == "extension"}
        assert PARACategory.PROJECT in ext_categories
        assert PARACategory.RESOURCE in ext_categories

    def test_get_user_preferences_empty(self) -> None:
        """get_user_preferences returns zeroed dict for empty/None events."""
        from file_organizer.methodologies.para.ai.feedback import PatternLearner

        learner = PatternLearner()
        prefs = learner.get_user_preferences(events=None)

        assert prefs["total_interactions"] == 0
        assert prefs["preferred_categories"] == {}
        assert prefs["override_patterns"] == []

    def test_get_user_preferences_counts_categories(self) -> None:
        """get_user_preferences counts user's actual category choices."""
        from file_organizer.methodologies.para.ai.feedback import PatternLearner
        from file_organizer.methodologies.para.categories import PARACategory

        learner = PatternLearner()
        events = self._build_events(
            PARACategory.PROJECT, ".md", "p", count=3, accepted=True
        ) + self._build_events(PARACategory.RESOURCE, ".pdf", "r", count=2, accepted=True)

        prefs = learner.get_user_preferences(events=events)

        assert prefs["total_interactions"] == 5
        assert prefs["preferred_categories"]["project"] == 3
        assert prefs["preferred_categories"]["resource"] == 2

    def test_get_user_preferences_override_patterns(self) -> None:
        """get_user_preferences lists rejection overrides with from/to fields."""
        from file_organizer.methodologies.para.ai.feedback import FeedbackEvent, PatternLearner
        from file_organizer.methodologies.para.categories import PARACategory

        learner = PatternLearner()
        events = [
            FeedbackEvent(
                file_path=Path("/mock/docs/ref.pdf"),
                suggested=PARACategory.PROJECT,
                actual=PARACategory.RESOURCE,
                confidence=0.5,
                accepted=False,
                file_extension=".pdf",
                parent_directory="docs",
            )
        ]

        prefs = learner.get_user_preferences(events=events)

        assert len(prefs["override_patterns"]) == 1
        override = prefs["override_patterns"][0]
        assert override["from"] == "project"
        assert override["to"] == "resource"
        assert override["extension"] == ".pdf"

    def test_adjust_weights_below_min_occurrences_returns_defaults(self) -> None:
        """adjust_weights returns default HeuristicWeights when events < min_occurrences."""
        from file_organizer.methodologies.para.ai.feedback import PatternLearner
        from file_organizer.methodologies.para.categories import PARACategory
        from file_organizer.methodologies.para.config import HeuristicWeights

        learner = PatternLearner(min_occurrences=5)
        events = self._build_events(PARACategory.PROJECT, ".md", "work", count=2)

        weights = learner.adjust_weights(events)

        defaults = HeuristicWeights()
        assert weights.temporal == defaults.temporal
        assert weights.content == defaults.content
        assert weights.structural == defaults.structural
        assert weights.ai == defaults.ai

    def test_adjust_weights_high_acceptance_boosts_content(self) -> None:
        """High acceptance rate (> 80%) increases content weight."""
        from file_organizer.methodologies.para.ai.feedback import PatternLearner
        from file_organizer.methodologies.para.categories import PARACategory

        learner = PatternLearner(min_occurrences=3)
        # 5 acceptances → 100% acceptance rate
        events = self._build_events(PARACategory.AREA, ".txt", "areas", count=5, accepted=True)

        weights = learner.adjust_weights(events)

        assert weights.content > 0.35  # default content is 0.35

    def test_adjust_weights_low_acceptance_rate_deviates_from_defaults(self) -> None:
        """Low acceptance rate (< 50%) produces weights different from high acceptance.

        With 0% acceptance the low-acceptance branch fires (structural += 0.05,
        content -= 0.05).  The dir-rejection branch may also fire and cancel the
        structural change, but the content change is always applied first.
        Regardless, the resulting weights must still normalise to 1.0 and differ
        from what high-acceptance events produce.
        """
        from file_organizer.methodologies.para.ai.feedback import PatternLearner
        from file_organizer.methodologies.para.categories import PARACategory

        learner = PatternLearner(min_occurrences=3)

        low_events = self._build_events(PARACategory.AREA, ".txt", "areas", count=5, accepted=False)
        high_events = self._build_events(PARACategory.AREA, ".txt", "areas", count=5, accepted=True)

        low_weights = learner.adjust_weights(low_events)
        high_weights = learner.adjust_weights(high_events)

        # Both sets produce normalised weights
        total_low = (
            low_weights.temporal + low_weights.content + low_weights.structural + low_weights.ai
        )
        total_high = (
            high_weights.temporal + high_weights.content + high_weights.structural + high_weights.ai
        )
        assert abs(total_low - 1.0) < 1e-6
        assert abs(total_high - 1.0) < 1e-6

        # The two acceptance rates must yield different weight distributions
        assert (
            low_weights.content != high_weights.content
            or low_weights.structural != high_weights.structural
        ), "Low and high acceptance should produce different weight adjustments"

    def test_adjust_weights_sum_to_one(self) -> None:
        """Adjusted weights always sum to 1.0 (within floating point tolerance)."""
        from file_organizer.methodologies.para.ai.feedback import PatternLearner
        from file_organizer.methodologies.para.categories import PARACategory

        learner = PatternLearner(min_occurrences=3)
        events = self._build_events(PARACategory.PROJECT, ".md", "proj", count=6, accepted=True)

        weights = learner.adjust_weights(events)
        total = weights.temporal + weights.content + weights.structural + weights.ai

        assert abs(total - 1.0) < 1e-6
