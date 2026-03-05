"""Coverage tests for ConfidenceEngine — targets uncovered branches."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from file_organizer.services.intelligence.confidence import (
    ConfidenceEngine,
    PatternUsageData,
)

pytestmark = pytest.mark.unit


@pytest.fixture()
def engine():
    return ConfidenceEngine()


# ---------------------------------------------------------------------------
# PatternUsageData.add_usage
# ---------------------------------------------------------------------------


class TestPatternUsageData:
    def test_add_first_usage_sets_first_seen(self):
        data = PatternUsageData(pattern_id="p1")
        now = datetime.now(UTC)
        data.add_usage(now, success=True)
        assert data.first_seen == now
        assert data.last_seen == now
        assert data.total_uses == 1
        assert data.successful_uses == 1

    def test_add_failure(self):
        data = PatternUsageData(pattern_id="p1")
        data.add_usage(datetime.now(UTC), success=False)
        assert data.total_uses == 1
        assert data.successful_uses == 0


# ---------------------------------------------------------------------------
# calculate_confidence
# ---------------------------------------------------------------------------


class TestCalculateConfidence:
    def test_no_data_returns_zero(self, engine):
        assert engine.calculate_confidence("unknown") == 0.0

    def test_with_usage_data_returns_positive(self, engine):
        data = PatternUsageData(pattern_id="p1")
        now = datetime.now(UTC)
        for _ in range(10):
            data.add_usage(now, success=True)
        score = engine.calculate_confidence("p1", usage_data=data, current_time=now)
        assert score > 0.0

    def test_internal_usage_data(self, engine):
        now = datetime.now(UTC)
        for _ in range(5):
            engine.track_usage("p1", now, success=True)
        score = engine.calculate_confidence("p1", current_time=now)
        assert score > 0.0


# ---------------------------------------------------------------------------
# _calculate_frequency_score
# ---------------------------------------------------------------------------


class TestFrequencyScore:
    def test_zero_uses(self, engine):
        data = PatternUsageData(pattern_id="p1")
        assert engine._calculate_frequency_score(data) == 0.0

    def test_many_uses(self, engine):
        data = PatternUsageData(pattern_id="p1", total_uses=100)
        score = engine._calculate_frequency_score(data)
        assert score >= 0.9


# ---------------------------------------------------------------------------
# _calculate_recency_score
# ---------------------------------------------------------------------------


class TestRecencyScore:
    def test_no_last_seen(self, engine):
        data = PatternUsageData(pattern_id="p1")
        assert engine._calculate_recency_score(data, datetime.now(UTC)) == 0.0

    def test_just_now(self, engine):
        data = PatternUsageData(pattern_id="p1")
        now = datetime.now(UTC)
        data.last_seen = now
        score = engine._calculate_recency_score(data, now)
        assert score > 0.99

    def test_old_pattern(self, engine):
        data = PatternUsageData(pattern_id="p1")
        now = datetime.now(UTC)
        data.last_seen = now - timedelta(days=180)
        score = engine._calculate_recency_score(data, now)
        assert score < 0.1

    def test_future_timestamp_handled(self, engine):
        data = PatternUsageData(pattern_id="p1")
        now = datetime.now(UTC)
        data.last_seen = now + timedelta(days=1)
        score = engine._calculate_recency_score(data, now)
        assert score >= 0.99  # Treated as 0 days old


# ---------------------------------------------------------------------------
# _calculate_consistency_score
# ---------------------------------------------------------------------------


class TestConsistencyScore:
    def test_zero_uses(self, engine):
        data = PatternUsageData(pattern_id="p1")
        assert engine._calculate_consistency_score(data) == 0.0

    def test_few_uses_returns_success_rate(self, engine):
        data = PatternUsageData(pattern_id="p1", total_uses=3, successful_uses=2)
        score = engine._calculate_consistency_score(data)
        assert abs(score - 2 / 3) < 0.01

    def test_high_success_rate_boost(self, engine):
        data = PatternUsageData(pattern_id="p1", total_uses=20, successful_uses=19)
        score = engine._calculate_consistency_score(data)
        assert score > 0.85

    def test_mixed_results(self, engine):
        data = PatternUsageData(pattern_id="p1", total_uses=20, successful_uses=10)
        score = engine._calculate_consistency_score(data)
        assert score < 0.5  # High variance


# ---------------------------------------------------------------------------
# decay_old_patterns
# ---------------------------------------------------------------------------


class TestDecayOldPatterns:
    def test_no_last_used_skips_decay(self, engine):
        patterns = [{"id": "p1", "confidence": 0.8}]
        result = engine.decay_old_patterns(patterns)
        assert result[0]["confidence"] == 0.8
        assert "decayed" not in result[0]

    def test_recent_pattern_not_decayed(self, engine):
        now = datetime.now(UTC)
        patterns = [{"id": "p1", "confidence": 0.8, "last_used": now}]
        result = engine.decay_old_patterns(patterns, current_time=now)
        assert result[0]["confidence"] == 0.8

    def test_old_pattern_decayed(self, engine):
        now = datetime.now(UTC)
        old = now - timedelta(days=180)
        patterns = [{"id": "p1", "confidence": 0.8, "last_used": old}]
        result = engine.decay_old_patterns(patterns, current_time=now)
        assert result[0]["confidence"] < 0.8
        assert result[0]["decayed"] is True

    def test_string_timestamp(self, engine):
        now = datetime.now(UTC)
        old = (now - timedelta(days=200)).isoformat().replace("+00:00", "Z")
        patterns = [{"id": "p1", "confidence": 0.8, "last_used": old}]
        result = engine.decay_old_patterns(patterns, current_time=now)
        assert result[0]["confidence"] < 0.8

    def test_custom_threshold(self, engine):
        now = datetime.now(UTC)
        old = now - timedelta(days=10)
        patterns = [{"id": "p1", "confidence": 0.8, "last_used": old}]
        result = engine.decay_old_patterns(patterns, time_threshold=5, current_time=now)
        assert result[0]["confidence"] < 0.8


# ---------------------------------------------------------------------------
# boost_recent_patterns
# ---------------------------------------------------------------------------


class TestBoostRecentPatterns:
    def test_no_last_used_skips_boost(self, engine):
        patterns = [{"id": "p1", "confidence": 0.5}]
        result = engine.boost_recent_patterns(patterns)
        assert result[0]["confidence"] == 0.5

    def test_recent_gets_boost(self, engine):
        now = datetime.now(UTC)
        patterns = [{"id": "p1", "confidence": 0.5, "last_used": now}]
        result = engine.boost_recent_patterns(patterns, current_time=now)
        assert result[0]["confidence"] > 0.5
        assert result[0]["boosted"] is True

    def test_old_not_boosted(self, engine):
        now = datetime.now(UTC)
        old = now - timedelta(days=30)
        patterns = [{"id": "p1", "confidence": 0.5, "last_used": old}]
        result = engine.boost_recent_patterns(patterns, current_time=now)
        assert result[0]["confidence"] == 0.5

    def test_string_timestamp_boost(self, engine):
        now = datetime.now(UTC)
        recent = now.isoformat().replace("+00:00", "Z")
        patterns = [{"id": "p1", "confidence": 0.5, "last_used": recent}]
        result = engine.boost_recent_patterns(patterns, current_time=now)
        assert result[0]["confidence"] > 0.5

    def test_boost_capped_at_max(self, engine):
        now = datetime.now(UTC)
        patterns = [{"id": "p1", "confidence": 0.99, "last_used": now}]
        result = engine.boost_recent_patterns(patterns, boost_factor=1.5, current_time=now)
        assert result[0]["confidence"] <= 1.0


# ---------------------------------------------------------------------------
# get_confidence_level
# ---------------------------------------------------------------------------


class TestGetConfidenceLevel:
    def test_high(self, engine):
        assert engine.get_confidence_level(0.8) == "high"

    def test_medium(self, engine):
        assert engine.get_confidence_level(0.6) == "medium"

    def test_low(self, engine):
        assert engine.get_confidence_level(0.3) == "low"

    def test_very_low(self, engine):
        assert engine.get_confidence_level(0.1) == "very_low"


# ---------------------------------------------------------------------------
# get_confidence_trend
# ---------------------------------------------------------------------------


class TestGetConfidenceTrend:
    def test_no_data(self, engine):
        result = engine.get_confidence_trend("unknown")
        assert result["trend"] == "unknown"

    def test_insufficient_records(self, engine):
        now = datetime.now(UTC)
        engine.track_usage("p1", now, success=True)
        result = engine.get_confidence_trend("p1", current_time=now)
        # Only 1 record — not enough
        assert result["trend"] in ("unknown", "insufficient_data")

    def test_improving_trend(self, engine):
        now = datetime.now(UTC)
        # First half: failures, second half: successes
        for i in range(10):
            t = now - timedelta(days=20 - i)
            engine.track_usage("p1", t, success=(i >= 5))
        result = engine.get_confidence_trend("p1", lookback_days=30, current_time=now)
        assert result["direction"] in ("increasing", "stable")

    def test_declining_trend(self, engine):
        now = datetime.now(UTC)
        for i in range(10):
            t = now - timedelta(days=20 - i)
            engine.track_usage("p1", t, success=(i < 3))
        result = engine.get_confidence_trend("p1", lookback_days=30, current_time=now)
        assert result["direction"] in ("decreasing", "stable")

    def test_stable_trend(self, engine):
        now = datetime.now(UTC)
        for i in range(10):
            t = now - timedelta(days=20 - i)
            engine.track_usage("p1", t, success=True)
        result = engine.get_confidence_trend("p1", lookback_days=30, current_time=now)
        assert result["direction"] == "stable"


# ---------------------------------------------------------------------------
# track_usage, get_usage_data, clear_usage_data
# ---------------------------------------------------------------------------


class TestUsageTracking:
    def test_track_creates_data(self, engine):
        now = datetime.now(UTC)
        engine.track_usage("p1", now, True)
        data = engine.get_usage_data("p1")
        assert data is not None
        assert data.total_uses == 1

    def test_get_unknown_returns_none(self, engine):
        assert engine.get_usage_data("nope") is None

    def test_clear_specific(self, engine):
        engine.track_usage("p1", datetime.now(UTC), True)
        engine.clear_usage_data("p1")
        assert engine.get_usage_data("p1") is None

    def test_clear_all(self, engine):
        engine.track_usage("p1", datetime.now(UTC), True)
        engine.track_usage("p2", datetime.now(UTC), True)
        engine.clear_usage_data()
        assert engine.get_usage_data("p1") is None
        assert engine.get_usage_data("p2") is None

    def test_clear_nonexistent_is_noop(self, engine):
        engine.clear_usage_data("nope")  # Should not raise


# ---------------------------------------------------------------------------
# validate_confidence_threshold
# ---------------------------------------------------------------------------


class TestValidateThreshold:
    def test_meets_threshold(self, engine):
        assert engine.validate_confidence_threshold(0.8, 0.5) is True

    def test_below_threshold(self, engine):
        assert engine.validate_confidence_threshold(0.3, 0.5) is False

    def test_exact_threshold(self, engine):
        assert engine.validate_confidence_threshold(0.5, 0.5) is True
