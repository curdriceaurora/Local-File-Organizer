"""
Unit tests for Confidence Engine

Tests multi-factor confidence scoring, time decay, pattern boosting,
and trend analysis functionality.
"""

from datetime import UTC, datetime, timedelta

import pytest

from file_organizer.services.intelligence.confidence import (
    ConfidenceEngine,
    PatternUsageData,
    UsageRecord,
)


class TestUsageRecord:
    """Tests for UsageRecord dataclass."""

    def test_create_usage_record(self):
        """Test creating a usage record."""
        timestamp = datetime.now(UTC)
        record = UsageRecord(
            timestamp=timestamp,
            success=True,
            context={'action': 'file_move'}
        )

        assert record.timestamp == timestamp
        assert record.success is True
        assert record.context['action'] == 'file_move'

    def test_usage_record_defaults(self):
        """Test usage record with default context."""
        timestamp = datetime.now(UTC)
        record = UsageRecord(timestamp=timestamp, success=False)

        assert record.timestamp == timestamp
        assert record.success is False
        assert record.context == {}


class TestPatternUsageData:
    """Tests for PatternUsageData dataclass."""

    def test_create_usage_data(self):
        """Test creating pattern usage data."""
        data = PatternUsageData(pattern_id="test_pattern")

        assert data.pattern_id == "test_pattern"
        assert data.usage_records == []
        assert data.first_seen is None
        assert data.last_seen is None
        assert data.total_uses == 0
        assert data.successful_uses == 0

    def test_add_usage(self):
        """Test adding usage records."""
        data = PatternUsageData(pattern_id="test_pattern")
        timestamp = datetime.now(UTC)

        data.add_usage(timestamp, success=True)

        assert data.total_uses == 1
        assert data.successful_uses == 1
        assert data.first_seen == timestamp
        assert data.last_seen == timestamp
        assert len(data.usage_records) == 1

    def test_add_multiple_usages(self):
        """Test adding multiple usage records."""
        data = PatternUsageData(pattern_id="test_pattern")
        now = datetime.now(UTC)

        data.add_usage(now - timedelta(days=10), success=True)
        data.add_usage(now - timedelta(days=5), success=False)
        data.add_usage(now, success=True)

        assert data.total_uses == 3
        assert data.successful_uses == 2
        assert data.first_seen == now - timedelta(days=10)
        assert data.last_seen == now


class TestConfidenceEngine:
    """Tests for ConfidenceEngine class."""

    def test_initialization(self):
        """Test confidence engine initialization."""
        engine = ConfidenceEngine()

        assert engine.decay_half_life_days == 30
        assert engine.old_pattern_threshold_days == 90
        assert engine._usage_data == {}

    def test_custom_initialization(self):
        """Test confidence engine with custom parameters."""
        engine = ConfidenceEngine(
            decay_half_life_days=60,
            old_pattern_threshold_days=120
        )

        assert engine.decay_half_life_days == 60
        assert engine.old_pattern_threshold_days == 120

    def test_calculate_confidence_no_data(self):
        """Test confidence calculation with no usage data."""
        engine = ConfidenceEngine()
        confidence = engine.calculate_confidence("unknown_pattern")

        assert confidence == 0.0

    def test_calculate_confidence_single_use(self):
        """Test confidence calculation with single use."""
        engine = ConfidenceEngine()
        now = datetime.now(UTC)

        engine.track_usage("pattern1", now, success=True)
        confidence = engine.calculate_confidence("pattern1")

        # Should be non-zero but not too high (single use gives moderate confidence)
        assert 0.0 < confidence < 0.8

    def test_calculate_confidence_multiple_uses(self):
        """Test confidence calculation with multiple successful uses."""
        engine = ConfidenceEngine()
        now = datetime.now(UTC)

        # Add 20 successful uses
        for i in range(20):
            engine.track_usage("pattern1", now - timedelta(days=i), success=True)

        confidence = engine.calculate_confidence("pattern1")

        # High frequency + good consistency should give high confidence
        assert confidence > 0.6

    def test_calculate_confidence_with_failures(self):
        """Test confidence calculation with mixed success/failure."""
        engine = ConfidenceEngine()
        now = datetime.now(UTC)

        # 5 successes, 5 failures
        for i in range(10):
            success = (i % 2 == 0)
            engine.track_usage("pattern1", now - timedelta(days=i), success=success)

        confidence = engine.calculate_confidence("pattern1")

        # Mixed results should give moderate confidence
        assert 0.3 < confidence < 0.7

    def test_frequency_score(self):
        """Test frequency score calculation."""
        engine = ConfidenceEngine()
        now = datetime.now(UTC)

        # Test different frequencies
        data_1_use = PatternUsageData(pattern_id="p1")
        data_1_use.add_usage(now, True)

        data_20_uses = PatternUsageData(pattern_id="p2")
        for _ in range(20):
            data_20_uses.add_usage(now, True)

        score_1 = engine._calculate_frequency_score(data_1_use)
        score_20 = engine._calculate_frequency_score(data_20_uses)

        assert score_1 < score_20
        assert score_20 > 0.5  # 20 uses should give good frequency score

    def test_recency_score(self):
        """Test recency score calculation."""
        engine = ConfidenceEngine()
        now = datetime.now(UTC)

        # Recent usage
        data_recent = PatternUsageData(pattern_id="p1")
        data_recent.add_usage(now, True)

        # Old usage (60 days ago)
        data_old = PatternUsageData(pattern_id="p2")
        data_old.add_usage(now - timedelta(days=60), True)

        score_recent = engine._calculate_recency_score(data_recent, now)
        score_old = engine._calculate_recency_score(data_old, now)

        assert score_recent > score_old
        assert score_recent > 0.9  # Very recent should be near 1.0

    def test_consistency_score(self):
        """Test consistency score calculation."""
        engine = ConfidenceEngine()
        now = datetime.now(UTC)

        # Consistent pattern (all successes)
        data_consistent = PatternUsageData(pattern_id="p1")
        for _ in range(10):
            data_consistent.add_usage(now, True)

        # Inconsistent pattern (mixed)
        data_inconsistent = PatternUsageData(pattern_id="p2")
        for i in range(10):
            data_inconsistent.add_usage(now, success=(i % 2 == 0))

        score_consistent = engine._calculate_consistency_score(data_consistent)
        score_inconsistent = engine._calculate_consistency_score(data_inconsistent)

        assert score_consistent > score_inconsistent
        assert score_consistent > 0.8  # All successes should give high consistency

    def test_decay_old_patterns(self):
        """Test time decay for old patterns."""
        engine = ConfidenceEngine()
        now = datetime.now(UTC)

        patterns = [
            {
                'id': 'p1',
                'confidence': 0.8,
                'last_used': (now - timedelta(days=100)).isoformat()
            },
            {
                'id': 'p2',
                'confidence': 0.8,
                'last_used': now.isoformat()
            }
        ]

        decayed = engine.decay_old_patterns(patterns, current_time=now)

        # Old pattern should have lower confidence
        assert decayed[0]['confidence'] < 0.8
        assert decayed[0]['decayed'] is True

        # Recent pattern should be unchanged
        assert decayed[1]['confidence'] == 0.8
        assert 'decayed' not in decayed[1]

    def test_boost_recent_patterns(self):
        """Test confidence boost for recent patterns."""
        engine = ConfidenceEngine()
        now = datetime.now(UTC)

        patterns = [
            {
                'id': 'p1',
                'confidence': 0.6,
                'last_used': (now - timedelta(days=2)).isoformat()
            },
            {
                'id': 'p2',
                'confidence': 0.6,
                'last_used': (now - timedelta(days=30)).isoformat()
            }
        ]

        boosted = engine.boost_recent_patterns(patterns, current_time=now)

        # Recent pattern should be boosted
        assert boosted[0]['confidence'] > 0.6
        assert boosted[0]['boosted'] is True

        # Old pattern should be unchanged
        assert boosted[1]['confidence'] == 0.6
        assert 'boosted' not in boosted[1]

    def test_validate_confidence_threshold(self):
        """Test confidence threshold validation."""
        engine = ConfidenceEngine()

        assert engine.validate_confidence_threshold(0.8, 0.5) is True
        assert engine.validate_confidence_threshold(0.4, 0.5) is False
        assert engine.validate_confidence_threshold(0.5, 0.5) is True

    def test_get_confidence_level(self):
        """Test getting human-readable confidence level."""
        engine = ConfidenceEngine()

        assert engine.get_confidence_level(0.9) == "high"
        assert engine.get_confidence_level(0.6) == "medium"
        assert engine.get_confidence_level(0.3) == "low"
        assert engine.get_confidence_level(0.1) == "very_low"

    def test_get_confidence_trend(self):
        """Test confidence trend analysis."""
        engine = ConfidenceEngine()
        now = datetime.now(UTC)

        # Improving trend: more successes in recent period
        for i in range(20):
            success = i > 10  # First half failures, second half successes
            engine.track_usage("pattern1", now - timedelta(days=19-i), success=success)

        trend = engine.get_confidence_trend("pattern1", current_time=now)

        assert trend['direction'] in ['increasing', 'stable']
        assert trend['confidence_change'] >= 0

    def test_get_confidence_trend_insufficient_data(self):
        """Test trend analysis with insufficient data."""
        engine = ConfidenceEngine()
        now = datetime.now(UTC)

        engine.track_usage("pattern1", now, success=True)

        trend = engine.get_confidence_trend("pattern1", current_time=now)

        # With only 1 usage record, trend should be unknown or insufficient_data
        assert trend['trend'] in ["unknown", "insufficient_data"]
        assert trend['sample_size'] < 2

    def test_track_usage(self):
        """Test tracking pattern usage."""
        engine = ConfidenceEngine()
        now = datetime.now(UTC)

        engine.track_usage("pattern1", now, success=True, context={'action': 'test'})

        data = engine.get_usage_data("pattern1")
        assert data is not None
        assert data.total_uses == 1
        assert data.successful_uses == 1
        assert len(data.usage_records) == 1

    def test_get_usage_data(self):
        """Test retrieving usage data."""
        engine = ConfidenceEngine()
        now = datetime.now(UTC)

        engine.track_usage("pattern1", now, success=True)

        data = engine.get_usage_data("pattern1")
        assert data is not None
        assert data.pattern_id == "pattern1"

        # Non-existent pattern
        data2 = engine.get_usage_data("unknown")
        assert data2 is None

    def test_clear_usage_data(self):
        """Test clearing usage data."""
        engine = ConfidenceEngine()
        now = datetime.now(UTC)

        engine.track_usage("pattern1", now, success=True)
        engine.track_usage("pattern2", now, success=True)

        # Clear specific pattern
        engine.clear_usage_data("pattern1")
        assert engine.get_usage_data("pattern1") is None
        assert engine.get_usage_data("pattern2") is not None

        # Clear all
        engine.clear_usage_data()
        assert engine.get_usage_data("pattern2") is None

    def test_confidence_weights_sum_to_one(self):
        """Test that confidence factor weights sum to 1.0."""
        assert (
            ConfidenceEngine.FREQUENCY_WEIGHT +
            ConfidenceEngine.RECENCY_WEIGHT +
            ConfidenceEngine.CONSISTENCY_WEIGHT
        ) == 1.0

    def test_confidence_bounds(self):
        """Test that confidence scores are always in valid range."""
        engine = ConfidenceEngine()
        now = datetime.now(UTC)

        # Test various scenarios
        scenarios = [
            (1, True),    # Single success
            (100, True),  # Many successes
            (10, False),  # Failures
            (5, True),    # Few successes
        ]

        for count, success in scenarios:
            pattern_id = f"pattern_{count}_{success}"
            for _ in range(count):
                engine.track_usage(pattern_id, now, success=success)

            confidence = engine.calculate_confidence(pattern_id)

            assert ConfidenceEngine.MIN_CONFIDENCE <= confidence <= ConfidenceEngine.MAX_CONFIDENCE


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
