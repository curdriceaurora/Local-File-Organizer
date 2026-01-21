"""
Confidence Engine - Pattern Reliability Scoring

This module implements the confidence calculation engine for learned patterns.
It provides multi-factor confidence scoring based on frequency, recency, and
consistency of pattern usage.

Features:
- Multi-factor confidence scoring (frequency 40%, recency 30%, consistency 30%)
- Time-decay algorithms for old patterns
- Recency weighting with exponential decay
- Pattern boosting for recent successes
- Confidence trend analysis
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
import math


@dataclass
class UsageRecord:
    """Record of a single pattern usage."""
    timestamp: datetime
    success: bool
    context: Dict[str, any] = field(default_factory=dict)


@dataclass
class PatternUsageData:
    """Usage data for a pattern."""
    pattern_id: str
    usage_records: List[UsageRecord] = field(default_factory=list)
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    total_uses: int = 0
    successful_uses: int = 0

    def add_usage(self, timestamp: datetime, success: bool, context: Optional[Dict] = None) -> None:
        """Add a usage record."""
        record = UsageRecord(timestamp=timestamp, success=success, context=context or {})
        self.usage_records.append(record)
        self.total_uses += 1
        if success:
            self.successful_uses += 1

        if self.first_seen is None:
            self.first_seen = timestamp
        self.last_seen = timestamp


class ConfidenceEngine:
    """
    Confidence calculation engine for learned patterns.

    This class implements multi-factor confidence scoring that considers:
    - Frequency: How often the pattern has been used (40% weight)
    - Recency: How recently the pattern has been used (30% weight)
    - Consistency: How reliably the pattern produces correct results (30% weight)
    """

    # Weights for confidence factors
    FREQUENCY_WEIGHT = 0.4
    RECENCY_WEIGHT = 0.3
    CONSISTENCY_WEIGHT = 0.3

    # Time decay parameters
    DECAY_HALF_LIFE_DAYS = 30  # Pattern confidence halves every 30 days
    OLD_PATTERN_THRESHOLD_DAYS = 90  # Patterns older than 90 days are considered old

    # Confidence thresholds
    MIN_CONFIDENCE = 0.0
    MAX_CONFIDENCE = 1.0
    HIGH_CONFIDENCE_THRESHOLD = 0.75
    MEDIUM_CONFIDENCE_THRESHOLD = 0.5
    LOW_CONFIDENCE_THRESHOLD = 0.25

    def __init__(
        self,
        decay_half_life_days: int = DECAY_HALF_LIFE_DAYS,
        old_pattern_threshold_days: int = OLD_PATTERN_THRESHOLD_DAYS
    ):
        """
        Initialize the confidence engine.

        Args:
            decay_half_life_days: Days for confidence to decay by half
            old_pattern_threshold_days: Days after which patterns are considered old
        """
        self.decay_half_life_days = decay_half_life_days
        self.old_pattern_threshold_days = old_pattern_threshold_days
        self._usage_data: Dict[str, PatternUsageData] = {}

    def calculate_confidence(
        self,
        pattern_id: str,
        usage_data: Optional[PatternUsageData] = None,
        current_time: Optional[datetime] = None
    ) -> float:
        """
        Calculate confidence score for a pattern.

        The confidence is calculated as:
        confidence = (frequency * 0.4) + (recency * 0.3) + (consistency * 0.3)

        Args:
            pattern_id: Unique identifier for the pattern
            usage_data: Optional usage data (if None, uses internal data)
            current_time: Current time for calculations (defaults to now)

        Returns:
            Confidence score between 0.0 and 1.0
        """
        if current_time is None:
            current_time = datetime.now(timezone.utc)

        # Get usage data
        if usage_data is None:
            usage_data = self._usage_data.get(pattern_id)
            if usage_data is None:
                return self.MIN_CONFIDENCE

        # Calculate individual factors
        frequency_score = self._calculate_frequency_score(usage_data)
        recency_score = self._calculate_recency_score(usage_data, current_time)
        consistency_score = self._calculate_consistency_score(usage_data)

        # Weighted combination
        confidence = (
            frequency_score * self.FREQUENCY_WEIGHT +
            recency_score * self.RECENCY_WEIGHT +
            consistency_score * self.CONSISTENCY_WEIGHT
        )

        # Clamp to valid range
        return max(self.MIN_CONFIDENCE, min(self.MAX_CONFIDENCE, confidence))

    def _calculate_frequency_score(self, usage_data: PatternUsageData) -> float:
        """
        Calculate frequency score based on usage count.

        Uses logarithmic scaling to normalize frequency:
        - 1 use: ~0.0
        - 5 uses: ~0.5
        - 20 uses: ~0.8
        - 100+ uses: ~1.0

        Args:
            usage_data: Pattern usage data

        Returns:
            Normalized frequency score between 0.0 and 1.0
        """
        if usage_data.total_uses == 0:
            return 0.0

        # Logarithmic scaling: score = log(uses + 1) / log(100)
        # This gives us a nice curve where:
        # - Low usage (1-5) grows quickly
        # - Medium usage (5-20) grows moderately
        # - High usage (20+) approaches 1.0 asymptotically
        score = math.log(usage_data.total_uses + 1) / math.log(100)
        return min(1.0, score)

    def _calculate_recency_score(
        self,
        usage_data: PatternUsageData,
        current_time: datetime
    ) -> float:
        """
        Calculate recency score with exponential time decay.

        Uses exponential decay formula:
        score = exp(-λ * days_since_last_use)
        where λ = ln(2) / half_life_days

        Args:
            usage_data: Pattern usage data
            current_time: Current time for calculations

        Returns:
            Recency score between 0.0 and 1.0
        """
        if usage_data.last_seen is None:
            return 0.0

        # Calculate days since last use
        time_delta = current_time - usage_data.last_seen
        days_since_last_use = time_delta.total_seconds() / 86400

        if days_since_last_use < 0:
            # Future timestamp (should not happen, but handle gracefully)
            days_since_last_use = 0

        # Exponential decay: score = exp(-λ * t)
        # where λ = ln(2) / half_life
        decay_constant = math.log(2) / self.decay_half_life_days
        score = math.exp(-decay_constant * days_since_last_use)

        return score

    def _calculate_consistency_score(self, usage_data: PatternUsageData) -> float:
        """
        Calculate consistency score based on success rate variance.

        Consistency = 1 - variance, where variance is calculated as the
        standard deviation of success/failure outcomes.

        For patterns with high success rates, consistency is high.
        For patterns with mixed results, consistency is lower.

        Args:
            usage_data: Pattern usage data

        Returns:
            Consistency score between 0.0 and 1.0
        """
        if usage_data.total_uses == 0:
            return 0.0

        # Simple success rate for small samples
        if usage_data.total_uses < 5:
            return usage_data.successful_uses / usage_data.total_uses

        # Calculate success rate
        success_rate = usage_data.successful_uses / usage_data.total_uses

        # For larger samples, we want to penalize inconsistent patterns
        # Calculate variance of binary outcomes (success/failure)
        # Variance of Bernoulli distribution: p(1-p)
        variance = success_rate * (1 - success_rate)

        # Consistency is inverse of variance, scaled to 0-1 range
        # Maximum variance is 0.25 (when success_rate = 0.5)
        consistency = 1.0 - (variance / 0.25)

        # Boost consistency for high success rates
        if success_rate > 0.8:
            consistency = min(1.0, consistency * 1.1)

        return consistency

    def decay_old_patterns(
        self,
        patterns: List[Dict],
        time_threshold: Optional[int] = None,
        current_time: Optional[datetime] = None
    ) -> List[Dict]:
        """
        Apply time decay to old patterns.

        Patterns older than the threshold have their confidence reduced
        according to the exponential decay function.

        Args:
            patterns: List of pattern dictionaries with 'id', 'confidence', 'last_used'
            time_threshold: Days threshold (defaults to old_pattern_threshold_days)
            current_time: Current time for calculations (defaults to now)

        Returns:
            Updated list of patterns with decayed confidence
        """
        if current_time is None:
            current_time = datetime.now(timezone.utc)

        if time_threshold is None:
            time_threshold = self.old_pattern_threshold_days

        decayed_patterns = []

        for pattern in patterns:
            pattern_copy = pattern.copy()

            # Get last used timestamp
            last_used = pattern.get('last_used')
            if last_used is None:
                # No last_used timestamp, skip decay
                decayed_patterns.append(pattern_copy)
                continue

            # Ensure last_used is a datetime
            if isinstance(last_used, str):
                last_used = datetime.fromisoformat(last_used.replace('Z', '+00:00'))

            # Calculate age in days
            age_delta = current_time - last_used
            age_days = age_delta.total_seconds() / 86400

            # Apply decay if older than threshold
            if age_days > time_threshold:
                days_over_threshold = age_days - time_threshold
                decay_constant = math.log(2) / self.decay_half_life_days
                decay_factor = math.exp(-decay_constant * days_over_threshold)

                # Apply decay to confidence
                original_confidence = pattern_copy.get('confidence', 0.5)
                pattern_copy['confidence'] = max(
                    self.MIN_CONFIDENCE,
                    original_confidence * decay_factor
                )
                pattern_copy['decayed'] = True
                pattern_copy['decay_factor'] = decay_factor

            decayed_patterns.append(pattern_copy)

        return decayed_patterns

    def boost_recent_patterns(
        self,
        patterns: List[Dict],
        boost_threshold_days: int = 7,
        boost_factor: float = 1.15,
        current_time: Optional[datetime] = None
    ) -> List[Dict]:
        """
        Boost confidence for recently used patterns.

        Patterns used within the threshold get a confidence boost to
        encourage continued use of recently successful patterns.

        Args:
            patterns: List of pattern dictionaries with 'id', 'confidence', 'last_used'
            boost_threshold_days: Days threshold for recent usage
            boost_factor: Multiplier for confidence boost (e.g., 1.15 = 15% boost)
            current_time: Current time for calculations (defaults to now)

        Returns:
            Updated list of patterns with boosted confidence
        """
        if current_time is None:
            current_time = datetime.now(timezone.utc)

        boosted_patterns = []

        for pattern in patterns:
            pattern_copy = pattern.copy()

            # Get last used timestamp
            last_used = pattern.get('last_used')
            if last_used is None:
                # No last_used timestamp, skip boost
                boosted_patterns.append(pattern_copy)
                continue

            # Ensure last_used is a datetime
            if isinstance(last_used, str):
                last_used = datetime.fromisoformat(last_used.replace('Z', '+00:00'))

            # Calculate age in days
            age_delta = current_time - last_used
            age_days = age_delta.total_seconds() / 86400

            # Apply boost if within threshold
            if age_days <= boost_threshold_days:
                original_confidence = pattern_copy.get('confidence', 0.5)
                boosted_confidence = min(
                    self.MAX_CONFIDENCE,
                    original_confidence * boost_factor
                )
                pattern_copy['confidence'] = boosted_confidence
                pattern_copy['boosted'] = True
                pattern_copy['boost_factor'] = boost_factor

            boosted_patterns.append(pattern_copy)

        return boosted_patterns

    def validate_confidence_threshold(
        self,
        confidence: float,
        threshold: float
    ) -> bool:
        """
        Validate if confidence meets the threshold.

        Args:
            confidence: Confidence score to validate
            threshold: Minimum required confidence

        Returns:
            True if confidence meets or exceeds threshold
        """
        return confidence >= threshold

    def get_confidence_level(self, confidence: float) -> str:
        """
        Get human-readable confidence level.

        Args:
            confidence: Confidence score

        Returns:
            Confidence level string: 'high', 'medium', 'low', or 'very_low'
        """
        if confidence >= self.HIGH_CONFIDENCE_THRESHOLD:
            return "high"
        elif confidence >= self.MEDIUM_CONFIDENCE_THRESHOLD:
            return "medium"
        elif confidence >= self.LOW_CONFIDENCE_THRESHOLD:
            return "low"
        else:
            return "very_low"

    def get_confidence_trend(
        self,
        pattern_id: str,
        lookback_days: int = 30,
        current_time: Optional[datetime] = None
    ) -> Dict[str, any]:
        """
        Analyze confidence trend for a pattern over time.

        Args:
            pattern_id: Pattern identifier
            lookback_days: Number of days to look back
            current_time: Current time for calculations (defaults to now)

        Returns:
            Dictionary with trend analysis including direction and rate
        """
        if current_time is None:
            current_time = datetime.now(timezone.utc)

        usage_data = self._usage_data.get(pattern_id)
        if usage_data is None or len(usage_data.usage_records) < 2:
            return {
                "trend": "unknown",
                "direction": "stable",
                "confidence_change": 0.0,
                "sample_size": 0
            }

        # Get usage records within lookback period
        lookback_start = current_time - timedelta(days=lookback_days)
        recent_records = [
            r for r in usage_data.usage_records
            if r.timestamp >= lookback_start
        ]

        if len(recent_records) < 2:
            return {
                "trend": "insufficient_data",
                "direction": "stable",
                "confidence_change": 0.0,
                "sample_size": len(recent_records)
            }

        # Calculate success rate for first and second half
        mid_point = len(recent_records) // 2
        first_half = recent_records[:mid_point]
        second_half = recent_records[mid_point:]

        first_success_rate = sum(1 for r in first_half if r.success) / len(first_half)
        second_success_rate = sum(1 for r in second_half if r.success) / len(second_half)

        confidence_change = second_success_rate - first_success_rate

        # Determine trend direction
        if abs(confidence_change) < 0.05:
            direction = "stable"
            trend = "stable"
        elif confidence_change > 0:
            direction = "increasing"
            trend = "improving" if confidence_change > 0.15 else "slightly_improving"
        else:
            direction = "decreasing"
            trend = "declining" if confidence_change < -0.15 else "slightly_declining"

        return {
            "trend": trend,
            "direction": direction,
            "confidence_change": round(confidence_change, 3),
            "sample_size": len(recent_records),
            "recent_success_rate": round(second_success_rate, 3),
            "previous_success_rate": round(first_success_rate, 3)
        }

    def track_usage(
        self,
        pattern_id: str,
        timestamp: datetime,
        success: bool,
        context: Optional[Dict] = None
    ) -> None:
        """
        Track a pattern usage for confidence calculations.

        Args:
            pattern_id: Pattern identifier
            timestamp: When the pattern was used
            success: Whether the usage was successful
            context: Additional context about the usage
        """
        if pattern_id not in self._usage_data:
            self._usage_data[pattern_id] = PatternUsageData(pattern_id=pattern_id)

        self._usage_data[pattern_id].add_usage(timestamp, success, context)

    def get_usage_data(self, pattern_id: str) -> Optional[PatternUsageData]:
        """
        Get usage data for a pattern.

        Args:
            pattern_id: Pattern identifier

        Returns:
            Usage data or None if not found
        """
        return self._usage_data.get(pattern_id)

    def clear_usage_data(self, pattern_id: Optional[str] = None) -> None:
        """
        Clear usage data for a specific pattern or all patterns.

        Args:
            pattern_id: Optional pattern identifier (if None, clears all)
        """
        if pattern_id is None:
            self._usage_data.clear()
        elif pattern_id in self._usage_data:
            del self._usage_data[pattern_id]
