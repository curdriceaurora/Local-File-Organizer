"""
Conflict resolution for contradictory preferences.

This module provides deterministic conflict resolution using multiple
weighting strategies including recency, frequency, and confidence scoring.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
import logging
import math

logger = logging.getLogger(__name__)


class ConflictResolver:
    """
    Resolves conflicts between contradictory preferences.

    Uses multiple weighted factors:
    - Recency: More recent preferences are weighted higher
    - Frequency: More frequently used preferences are weighted higher
    - Confidence: Higher confidence scores are weighted higher

    The resolver produces deterministic results for reproducibility.
    """

    def __init__(
        self,
        recency_weight: float = 0.4,
        frequency_weight: float = 0.35,
        confidence_weight: float = 0.25
    ):
        """
        Initialize the conflict resolver with weighting factors.

        Args:
            recency_weight: Weight for recency factor (0.0 to 1.0)
            frequency_weight: Weight for frequency factor (0.0 to 1.0)
            confidence_weight: Weight for confidence factor (0.0 to 1.0)

        Note:
            Weights should sum to 1.0 for normalized scoring.

        Example:
            >>> resolver = ConflictResolver()
            >>> resolver = ConflictResolver(
            ...     recency_weight=0.5,
            ...     frequency_weight=0.3,
            ...     confidence_weight=0.2
            ... )
        """
        # Normalize weights
        total = recency_weight + frequency_weight + confidence_weight
        if total == 0:
            raise ValueError("Weights cannot all be zero")

        self.recency_weight = recency_weight / total
        self.frequency_weight = frequency_weight / total
        self.confidence_weight = confidence_weight / total

        logger.debug(
            f"ConflictResolver initialized with weights: "
            f"recency={self.recency_weight:.2f}, "
            f"frequency={self.frequency_weight:.2f}, "
            f"confidence={self.confidence_weight:.2f}"
        )

    def resolve(self, conflicting_preferences: List[dict]) -> dict:
        """
        Resolve conflicts between multiple preferences.

        Uses weighted scoring to determine the best preference. If preferences
        have equal scores, the most recent one is chosen for determinism.

        Args:
            conflicting_preferences: List of preference dictionaries, each
                containing preference data and metadata (created, updated,
                correction_count, confidence)

        Returns:
            The resolved preference dictionary

        Raises:
            ValueError: If conflicting_preferences is empty

        Example:
            >>> resolver = ConflictResolver()
            >>> prefs = [
            ...     {
            ...         "folder_mappings": {"pdf": "Documents"},
            ...         "created": "2026-01-01T00:00:00Z",
            ...         "updated": "2026-01-10T00:00:00Z",
            ...         "correction_count": 5,
            ...         "confidence": 0.8
            ...     },
            ...     {
            ...         "folder_mappings": {"pdf": "PDFs"},
            ...         "created": "2026-01-15T00:00:00Z",
            ...         "updated": "2026-01-20T00:00:00Z",
            ...         "correction_count": 10,
            ...         "confidence": 0.9
            ...     }
            ... ]
            >>> resolved = resolver.resolve(prefs)
            >>> resolved["folder_mappings"]["pdf"]
            'PDFs'
        """
        if not conflicting_preferences:
            raise ValueError("Cannot resolve empty preference list")

        if len(conflicting_preferences) == 1:
            logger.debug("Only one preference, no conflict to resolve")
            return conflicting_preferences[0]

        # Calculate weights for each preference
        recency_weights = self.weight_by_recency(conflicting_preferences)
        frequency_weights = self.weight_by_frequency(conflicting_preferences)
        confidence_scores = [
            self.score_confidence(pref) for pref in conflicting_preferences
        ]

        # Combine weights
        combined_scores = []
        for i in range(len(conflicting_preferences)):
            score = (
                recency_weights[i] * self.recency_weight +
                frequency_weights[i] * self.frequency_weight +
                confidence_scores[i] * self.confidence_weight
            )
            combined_scores.append(score)

        # Find preference with highest score
        # If tie, use most recent (last in sorted order)
        max_score = max(combined_scores)
        best_indices = [
            i for i, score in enumerate(combined_scores)
            if score == max_score
        ]

        if len(best_indices) > 1:
            # Tie-breaker: choose most recent
            logger.debug(
                f"Tie between {len(best_indices)} preferences, "
                "using recency as tie-breaker"
            )
            best_index = max(
                best_indices,
                key=lambda i: self._parse_timestamp(
                    conflicting_preferences[i].get("updated")
                )
            )
        else:
            best_index = best_indices[0]

        resolved = conflicting_preferences[best_index]

        logger.info(
            f"Resolved conflict between {len(conflicting_preferences)} preferences "
            f"(scores: {[f'{s:.3f}' for s in combined_scores]}, "
            f"selected index {best_index})"
        )

        return resolved

    def weight_by_recency(self, preferences: List[dict]) -> List[float]:
        """
        Calculate recency weights for preferences.

        Uses exponential decay: weight = exp(-days_old / decay_factor)

        Args:
            preferences: List of preference dictionaries with 'updated' timestamps

        Returns:
            List of normalized weights (0.0 to 1.0)

        Example:
            >>> resolver = ConflictResolver()
            >>> prefs = [
            ...     {"updated": "2026-01-01T00:00:00Z"},
            ...     {"updated": "2026-01-20T00:00:00Z"}
            ... ]
            >>> weights = resolver.weight_by_recency(prefs)
            >>> weights[1] > weights[0]  # More recent has higher weight
            True
        """
        if not preferences:
            return []

        now = datetime.utcnow().replace(tzinfo=None)  # Make timezone-naive
        decay_factor = 30.0  # Days for weight to decay to ~37% (1/e)

        # Calculate days old for each preference
        days_old = []
        for pref in preferences:
            timestamp = pref.get("updated") or pref.get("created")
            if timestamp:
                dt = self._parse_timestamp(timestamp)
                age_days = (now - dt).total_seconds() / 86400.0  # seconds to days
                days_old.append(age_days)
            else:
                # No timestamp, assume very old
                days_old.append(365.0)

        # Calculate exponential decay weights
        weights = [math.exp(-age / decay_factor) for age in days_old]

        # Normalize to 0-1 range
        max_weight = max(weights) if weights else 1.0
        if max_weight > 0:
            weights = [w / max_weight for w in weights]

        logger.debug(
            f"Recency weights calculated: "
            f"{[f'{w:.3f}' for w in weights]} "
            f"(ages: {[f'{d:.1f}d' for d in days_old]})"
        )

        return weights

    def weight_by_frequency(self, preferences: List[dict]) -> List[float]:
        """
        Calculate frequency weights for preferences.

        Uses correction_count as a proxy for frequency of use.

        Args:
            preferences: List of preference dictionaries with 'correction_count'

        Returns:
            List of normalized weights (0.0 to 1.0)

        Example:
            >>> resolver = ConflictResolver()
            >>> prefs = [
            ...     {"correction_count": 5},
            ...     {"correction_count": 20}
            ... ]
            >>> weights = resolver.weight_by_frequency(prefs)
            >>> weights[1] > weights[0]  # Higher frequency has higher weight
            True
        """
        if not preferences:
            return []

        # Get correction counts
        counts = [
            pref.get("correction_count", 0) for pref in preferences
        ]

        # Handle all-zero case
        total_count = sum(counts)
        if total_count == 0:
            # Equal weights if no frequency data
            return [1.0 / len(preferences)] * len(preferences)

        # Normalize using square root to prevent one very high count
        # from dominating (diminishing returns)
        sqrt_counts = [math.sqrt(count) for count in counts]
        max_sqrt = max(sqrt_counts)

        if max_sqrt > 0:
            weights = [sc / max_sqrt for sc in sqrt_counts]
        else:
            weights = [1.0 / len(preferences)] * len(preferences)

        logger.debug(
            f"Frequency weights calculated: "
            f"{[f'{w:.3f}' for w in weights]} "
            f"(counts: {counts})"
        )

        return weights

    def score_confidence(self, preference: dict) -> float:
        """
        Calculate confidence score for a preference.

        Confidence is a value between 0.0 and 1.0 indicating how
        confident we are that this preference is correct.

        Args:
            preference: Preference dictionary with optional 'confidence' field

        Returns:
            Confidence score (0.0 to 1.0)

        Example:
            >>> resolver = ConflictResolver()
            >>> resolver.score_confidence({"confidence": 0.85})
            0.85
            >>> resolver.score_confidence({})  # No confidence field
            0.5
        """
        confidence = preference.get("confidence")

        if confidence is None:
            # Default to medium confidence if not specified
            return 0.5

        # Clamp to valid range
        confidence = max(0.0, min(1.0, float(confidence)))

        return confidence

    def _parse_timestamp(self, timestamp: Optional[str]) -> datetime:
        """
        Parse ISO 8601 timestamp string to datetime.

        Args:
            timestamp: ISO 8601 formatted timestamp string

        Returns:
            Datetime object, or very old date if parsing fails

        Example:
            >>> resolver = ConflictResolver()
            >>> dt = resolver._parse_timestamp("2026-01-21T06:48:24Z")
            >>> dt.year
            2026
        """
        if not timestamp:
            # Return very old date for missing timestamps
            return datetime(1970, 1, 1)

        try:
            # Handle both with and without 'Z' suffix
            if timestamp.endswith("Z"):
                timestamp = timestamp[:-1]  # Remove Z for naive datetime

            # Parse and remove timezone info to make it naive
            dt = datetime.fromisoformat(timestamp)
            # Make timezone-naive
            return dt.replace(tzinfo=None)
        except (ValueError, AttributeError) as e:
            logger.warning(f"Failed to parse timestamp '{timestamp}': {e}")
            return datetime(1970, 1, 1)

    def get_ambiguity_score(self, conflicting_preferences: List[dict]) -> float:
        """
        Calculate ambiguity score for a set of conflicting preferences.

        A score of 0.0 means clear winner, 1.0 means complete ambiguity.

        Args:
            conflicting_preferences: List of preference dictionaries

        Returns:
            Ambiguity score (0.0 to 1.0)

        Example:
            >>> resolver = ConflictResolver()
            >>> prefs = [
            ...     {"confidence": 0.9, "correction_count": 20},
            ...     {"confidence": 0.5, "correction_count": 2}
            ... ]
            >>> score = resolver.get_ambiguity_score(prefs)
            >>> score < 0.5  # Clear winner, low ambiguity
            True
        """
        if len(conflicting_preferences) <= 1:
            return 0.0  # No ambiguity with 0 or 1 preference

        # Calculate all combined scores
        recency_weights = self.weight_by_recency(conflicting_preferences)
        frequency_weights = self.weight_by_frequency(conflicting_preferences)
        confidence_scores = [
            self.score_confidence(pref) for pref in conflicting_preferences
        ]

        combined_scores = []
        for i in range(len(conflicting_preferences)):
            score = (
                recency_weights[i] * self.recency_weight +
                frequency_weights[i] * self.frequency_weight +
                confidence_scores[i] * self.confidence_weight
            )
            combined_scores.append(score)

        # Calculate coefficient of variation (normalized std dev)
        if not combined_scores:
            return 1.0

        mean_score = sum(combined_scores) / len(combined_scores)
        if mean_score == 0:
            return 1.0  # Complete ambiguity

        variance = sum((s - mean_score) ** 2 for s in combined_scores) / len(combined_scores)
        std_dev = math.sqrt(variance)

        # Invert: high variance = low ambiguity (clear winner)
        # Normalize to 0-1 range (assuming max reasonable CV is 1.0)
        cv = std_dev / mean_score
        ambiguity = 1.0 - min(1.0, cv)

        logger.debug(
            f"Ambiguity score: {ambiguity:.3f} "
            f"(scores: {[f'{s:.3f}' for s in combined_scores]})"
        )

        return ambiguity

    def needs_user_input(
        self,
        conflicting_preferences: List[dict],
        ambiguity_threshold: float = 0.7
    ) -> bool:
        """
        Determine if user input is needed to resolve conflict.

        Args:
            conflicting_preferences: List of preference dictionaries
            ambiguity_threshold: Threshold above which user input is needed

        Returns:
            True if user input should be requested

        Example:
            >>> resolver = ConflictResolver()
            >>> prefs = [
            ...     {"confidence": 0.6, "correction_count": 5},
            ...     {"confidence": 0.6, "correction_count": 5}
            ... ]
            >>> resolver.needs_user_input(prefs)
            True
        """
        ambiguity = self.get_ambiguity_score(conflicting_preferences)
        needs_input = ambiguity >= ambiguity_threshold

        if needs_input:
            logger.info(
                f"High ambiguity detected ({ambiguity:.3f} >= {ambiguity_threshold}), "
                "user input recommended"
            )

        return needs_input
