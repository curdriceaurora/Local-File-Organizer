"""Tests for file_organizer.services.suggestion_feedback module.

Covers SuggestionFeedback CRUD, learning stats, confidence adjustment,
user history, old feedback cleanup, and export.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from file_organizer.models.suggestion_types import Suggestion, SuggestionType
from file_organizer.services.suggestion_feedback import (
    FeedbackEntry,
    LearningStats,
    SuggestionFeedback,
)

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_suggestion(
    sid: str = "s1",
    stype: SuggestionType = SuggestionType.MOVE,
    confidence: float = 75.0,
    file_path: str = "/a.txt",
    target_path: str | None = "/dest/a.txt",
) -> Suggestion:
    return Suggestion(
        suggestion_id=sid,
        suggestion_type=stype,
        file_path=Path(file_path),
        target_path=Path(target_path) if target_path else None,
        confidence=confidence,
    )


# ---------------------------------------------------------------------------
# FeedbackEntry
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFeedbackEntry:
    """Test FeedbackEntry serialization."""

    def test_to_dict(self):
        entry = FeedbackEntry(
            suggestion_id="s1",
            suggestion_type=SuggestionType.MOVE,
            action="accepted",
            file_path="/a.txt",
            target_path="/dest",
            confidence=80.0,
        )
        d = entry.to_dict()
        assert d["suggestion_type"] == "move"
        assert d["action"] == "accepted"

    def test_from_dict(self):
        d = {
            "suggestion_id": "s1",
            "suggestion_type": "move",
            "action": "rejected",
            "file_path": "/a.txt",
            "target_path": None,
            "confidence": 60.0,
            "timestamp": "2024-01-15T10:00:00",
        }
        entry = FeedbackEntry.from_dict(d)
        assert entry.suggestion_type == SuggestionType.MOVE
        assert entry.action == "rejected"


@pytest.mark.unit
class TestLearningStats:
    """Test LearningStats."""

    def test_to_dict(self):
        stats = LearningStats(total_suggestions=10, accepted=5)
        d = stats.to_dict()
        assert d["total_suggestions"] == 10
        assert d["accepted"] == 5


# ---------------------------------------------------------------------------
# SuggestionFeedback
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSuggestionFeedbackInit:
    """Test initialization and loading."""

    def test_default_path(self, tmp_path):
        fb = SuggestionFeedback(feedback_file=tmp_path / "feedback.json")
        assert fb.feedback_entries == []
        assert fb.pattern_adjustments == {}

    def test_load_existing(self, tmp_path):
        fb_file = tmp_path / "feedback.json"
        data = {
            "entries": [
                {
                    "suggestion_id": "s1",
                    "suggestion_type": "move",
                    "action": "accepted",
                    "file_path": "/a.txt",
                    "target_path": "/b.txt",
                    "confidence": 80.0,
                    "timestamp": "2024-01-15T10:00:00",
                    "metadata": {},
                }
            ],
            "pattern_adjustments": {"move:.txt": 5.0},
        }
        fb_file.write_text(json.dumps(data))
        fb = SuggestionFeedback(feedback_file=fb_file)
        assert len(fb.feedback_entries) == 1
        assert fb.pattern_adjustments["move:.txt"] == 5.0

    def test_load_corrupted_file(self, tmp_path):
        fb_file = tmp_path / "feedback.json"
        fb_file.write_text("NOT VALID JSON {{{")
        fb = SuggestionFeedback(feedback_file=fb_file)
        assert fb.feedback_entries == []

    def test_load_missing_file(self, tmp_path):
        fb = SuggestionFeedback(feedback_file=tmp_path / "nope.json")
        assert fb.feedback_entries == []


# ---------------------------------------------------------------------------
# record_action
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRecordAction:
    """Test recording user actions."""

    def test_record_accepted(self, tmp_path):
        fb = SuggestionFeedback(feedback_file=tmp_path / "fb.json")
        s = _make_suggestion()
        fb.record_action(s, "accepted")
        assert len(fb.feedback_entries) == 1
        assert fb.feedback_entries[0].action == "accepted"

    def test_record_rejected(self, tmp_path):
        fb = SuggestionFeedback(feedback_file=tmp_path / "fb.json")
        s = _make_suggestion()
        fb.record_action(s, "rejected")
        assert fb.feedback_entries[0].action == "rejected"

    def test_record_with_metadata(self, tmp_path):
        fb = SuggestionFeedback(feedback_file=tmp_path / "fb.json")
        s = _make_suggestion()
        fb.record_action(s, "modified", metadata={"reason": "test"})
        assert fb.feedback_entries[0].metadata["reason"] == "test"

    def test_saves_to_file(self, tmp_path):
        fb_file = tmp_path / "fb.json"
        fb = SuggestionFeedback(feedback_file=fb_file)
        fb.record_action(_make_suggestion(), "accepted")
        assert fb_file.exists()
        data = json.loads(fb_file.read_text())
        assert len(data["entries"]) == 1


# ---------------------------------------------------------------------------
# get_acceptance_rate / get_rejection_rate
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAcceptanceRejectionRates:
    """Test acceptance and rejection rate calculations."""

    def test_empty_entries(self, tmp_path):
        fb = SuggestionFeedback(feedback_file=tmp_path / "fb.json")
        assert fb.get_acceptance_rate() == 0.0
        assert fb.get_rejection_rate() == 0.0

    def test_filtered_empty(self, tmp_path):
        fb = SuggestionFeedback(feedback_file=tmp_path / "fb.json")
        fb.record_action(_make_suggestion(stype=SuggestionType.MOVE), "accepted")
        assert fb.get_acceptance_rate("rename") == 0.0
        assert fb.get_rejection_rate("rename") == 0.0

    def test_acceptance_rate(self, tmp_path):
        fb = SuggestionFeedback(feedback_file=tmp_path / "fb.json")
        fb.record_action(_make_suggestion(sid="1"), "accepted")
        fb.record_action(_make_suggestion(sid="2"), "rejected")
        assert fb.get_acceptance_rate() == 50.0

    def test_rejection_rate(self, tmp_path):
        fb = SuggestionFeedback(feedback_file=tmp_path / "fb.json")
        fb.record_action(_make_suggestion(sid="1"), "accepted")
        fb.record_action(_make_suggestion(sid="2"), "rejected")
        fb.record_action(_make_suggestion(sid="3"), "rejected")
        assert abs(fb.get_rejection_rate() - 66.666) < 1.0

    def test_type_filter(self, tmp_path):
        fb = SuggestionFeedback(feedback_file=tmp_path / "fb.json")
        fb.record_action(_make_suggestion(sid="1", stype=SuggestionType.MOVE), "accepted")
        fb.record_action(
            _make_suggestion(sid="2", stype=SuggestionType.RENAME), "rejected"
        )
        assert fb.get_acceptance_rate("move") == 100.0
        assert fb.get_rejection_rate("move") == 0.0


# ---------------------------------------------------------------------------
# get_learning_stats
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLearningStatsComputation:
    """Test get_learning_stats."""

    def test_empty(self, tmp_path):
        fb = SuggestionFeedback(feedback_file=tmp_path / "fb.json")
        stats = fb.get_learning_stats()
        assert stats.total_suggestions == 0

    def test_full_stats(self, tmp_path):
        fb = SuggestionFeedback(feedback_file=tmp_path / "fb.json")
        fb.record_action(
            _make_suggestion(sid="1", confidence=90.0), "accepted"
        )
        fb.record_action(
            _make_suggestion(sid="2", confidence=30.0), "rejected"
        )
        fb.record_action(_make_suggestion(sid="3"), "ignored")
        fb.record_action(_make_suggestion(sid="4"), "modified")

        stats = fb.get_learning_stats()
        assert stats.total_suggestions == 4
        assert stats.accepted == 1
        assert stats.rejected == 1
        assert stats.ignored == 1
        assert stats.modified == 1
        assert stats.acceptance_rate == 25.0
        assert stats.avg_accepted_confidence == 90.0
        assert stats.avg_rejected_confidence == 30.0
        assert "move" in stats.by_type


# ---------------------------------------------------------------------------
# update_patterns / get_confidence_adjustment
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPatternUpdates:
    """Test pattern adjustment logic."""

    def test_accepted_increases_confidence(self, tmp_path):
        fb = SuggestionFeedback(feedback_file=tmp_path / "fb.json")
        entry = FeedbackEntry(
            suggestion_id="s1",
            suggestion_type=SuggestionType.MOVE,
            action="accepted",
            file_path="/a.txt",
            target_path="/b.txt",
            confidence=70.0,
        )
        fb.update_patterns([entry])
        adj = fb.get_confidence_adjustment(SuggestionType.MOVE, ".txt")
        assert adj > 0.0

    def test_rejected_decreases_confidence(self, tmp_path):
        fb = SuggestionFeedback(feedback_file=tmp_path / "fb.json")
        entry = FeedbackEntry(
            suggestion_id="s1",
            suggestion_type=SuggestionType.MOVE,
            action="rejected",
            file_path="/a.txt",
            target_path="/b.txt",
            confidence=70.0,
        )
        fb.update_patterns([entry])
        adj = fb.get_confidence_adjustment(SuggestionType.MOVE, ".txt")
        assert adj < 0.0

    def test_no_adjustment_default(self, tmp_path):
        fb = SuggestionFeedback(feedback_file=tmp_path / "fb.json")
        adj = fb.get_confidence_adjustment(SuggestionType.RENAME, ".pdf")
        assert adj == 0.0


# ---------------------------------------------------------------------------
# get_user_history
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestUserHistory:
    """Test get_user_history."""

    def test_empty_history(self, tmp_path):
        fb = SuggestionFeedback(feedback_file=tmp_path / "fb.json")
        h = fb.get_user_history()
        assert "move_history" in h

    def test_with_accepted_moves(self, tmp_path):
        fb = SuggestionFeedback(feedback_file=tmp_path / "fb.json")
        fb.record_action(
            _make_suggestion(file_path="/a.txt", target_path="/docs/a.txt"),
            "accepted",
        )
        h = fb.get_user_history()
        assert ".txt" in h["move_history"]


# ---------------------------------------------------------------------------
# clear_old_feedback
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestClearOldFeedback:
    """Test clearing old feedback entries."""

    def test_remove_old_entries(self, tmp_path):
        fb = SuggestionFeedback(feedback_file=tmp_path / "fb.json")
        # Add an old entry manually
        old_entry = FeedbackEntry(
            suggestion_id="old",
            suggestion_type=SuggestionType.MOVE,
            action="accepted",
            file_path="/a.txt",
            target_path="/b.txt",
            confidence=80.0,
            timestamp=datetime.now(UTC) - timedelta(days=200),
        )
        fb.feedback_entries.append(old_entry)
        fb.record_action(_make_suggestion(sid="new"), "accepted")

        removed = fb.clear_old_feedback(days=90)
        assert removed == 1
        assert len(fb.feedback_entries) == 1

    def test_nothing_to_remove(self, tmp_path):
        fb = SuggestionFeedback(feedback_file=tmp_path / "fb.json")
        fb.record_action(_make_suggestion(), "accepted")
        removed = fb.clear_old_feedback(days=90)
        assert removed == 0


# ---------------------------------------------------------------------------
# export_feedback
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExportFeedback:
    """Test exporting feedback."""

    def test_export_creates_file(self, tmp_path):
        fb = SuggestionFeedback(feedback_file=tmp_path / "fb.json")
        fb.record_action(_make_suggestion(), "accepted")
        export_file = tmp_path / "export.json"
        fb.export_feedback(export_file)
        assert export_file.exists()
        data = json.loads(export_file.read_text())
        assert "entries" in data
        assert "stats" in data
        assert "exported_at" in data


# ---------------------------------------------------------------------------
# _save_feedback error handling
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSaveFeedbackError:
    """Test save error handling."""

    def test_save_error_logged(self, tmp_path):
        fb = SuggestionFeedback(feedback_file=tmp_path / "fb.json")
        with patch("builtins.open", side_effect=PermissionError("denied")):
            # Should not raise
            fb._save_feedback()
