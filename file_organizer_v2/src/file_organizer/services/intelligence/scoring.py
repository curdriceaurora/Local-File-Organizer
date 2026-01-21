"""
Scoring Module - Confidence Scoring Utilities

This module provides utility functions and classes for confidence scoring,
including score normalization, ranking, and comparison operations.
"""

from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple, Callable
from datetime import datetime


@dataclass
class ScoredPattern:
    """A pattern with its calculated confidence score."""
    pattern_id: str
    pattern_data: Dict
    confidence: float
    frequency_score: float
    recency_score: float
    consistency_score: float
    metadata: Dict = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class PatternScorer:
    """
    Utility class for scoring and ranking patterns.

    Provides methods for normalizing scores, ranking patterns,
    and comparing pattern confidence levels.
    """

    @staticmethod
    def normalize_score(
        score: float,
        min_val: float = 0.0,
        max_val: float = 1.0
    ) -> float:
        """
        Normalize a score to a given range.

        Args:
            score: Score to normalize
            min_val: Minimum value of range
            max_val: Maximum value of range

        Returns:
            Normalized score
        """
        return max(min_val, min(max_val, score))

    @staticmethod
    def rank_patterns(
        patterns: List[ScoredPattern],
        key: str = 'confidence',
        reverse: bool = True
    ) -> List[ScoredPattern]:
        """
        Rank patterns by a given score attribute.

        Args:
            patterns: List of scored patterns
            key: Attribute to rank by ('confidence', 'frequency_score', etc.)
            reverse: Sort in descending order if True

        Returns:
            Sorted list of patterns
        """
        return sorted(patterns, key=lambda p: getattr(p, key, 0), reverse=reverse)

    @staticmethod
    def filter_by_confidence(
        patterns: List[ScoredPattern],
        min_confidence: float,
        max_confidence: Optional[float] = None
    ) -> List[ScoredPattern]:
        """
        Filter patterns by confidence threshold.

        Args:
            patterns: List of scored patterns
            min_confidence: Minimum confidence required
            max_confidence: Optional maximum confidence

        Returns:
            Filtered list of patterns
        """
        filtered = [p for p in patterns if p.confidence >= min_confidence]

        if max_confidence is not None:
            filtered = [p for p in filtered if p.confidence <= max_confidence]

        return filtered

    @staticmethod
    def get_top_patterns(
        patterns: List[ScoredPattern],
        n: int = 5,
        min_confidence: Optional[float] = None
    ) -> List[ScoredPattern]:
        """
        Get top N patterns by confidence.

        Args:
            patterns: List of scored patterns
            n: Number of patterns to return
            min_confidence: Optional minimum confidence filter

        Returns:
            Top N patterns
        """
        if min_confidence is not None:
            patterns = PatternScorer.filter_by_confidence(patterns, min_confidence)

        ranked = PatternScorer.rank_patterns(patterns, key='confidence')
        return ranked[:n]

    @staticmethod
    def calculate_weighted_score(
        scores: Dict[str, float],
        weights: Dict[str, float]
    ) -> float:
        """
        Calculate weighted score from multiple factors.

        Args:
            scores: Dictionary of score name to value
            weights: Dictionary of score name to weight

        Returns:
            Weighted score
        """
        total_weight = sum(weights.values())
        if total_weight == 0:
            return 0.0

        weighted_sum = sum(
            scores.get(key, 0) * weight
            for key, weight in weights.items()
        )

        return weighted_sum / total_weight

    @staticmethod
    def compare_patterns(
        pattern1: ScoredPattern,
        pattern2: ScoredPattern,
        comparison_key: str = 'confidence'
    ) -> int:
        """
        Compare two patterns by a given attribute.

        Args:
            pattern1: First pattern
            pattern2: Second pattern
            comparison_key: Attribute to compare

        Returns:
            -1 if pattern1 < pattern2, 0 if equal, 1 if pattern1 > pattern2
        """
        val1 = getattr(pattern1, comparison_key, 0)
        val2 = getattr(pattern2, comparison_key, 0)

        if val1 < val2:
            return -1
        elif val1 > val2:
            return 1
        else:
            return 0

    @staticmethod
    def aggregate_scores(
        patterns: List[ScoredPattern],
        aggregation: str = 'mean'
    ) -> Dict[str, float]:
        """
        Aggregate scores across patterns.

        Args:
            patterns: List of scored patterns
            aggregation: Aggregation method ('mean', 'median', 'min', 'max')

        Returns:
            Dictionary with aggregated scores
        """
        if not patterns:
            return {
                'confidence': 0.0,
                'frequency_score': 0.0,
                'recency_score': 0.0,
                'consistency_score': 0.0
            }

        scores = {
            'confidence': [p.confidence for p in patterns],
            'frequency_score': [p.frequency_score for p in patterns],
            'recency_score': [p.recency_score for p in patterns],
            'consistency_score': [p.consistency_score for p in patterns]
        }

        aggregated = {}

        for key, values in scores.items():
            if aggregation == 'mean':
                aggregated[key] = sum(values) / len(values)
            elif aggregation == 'median':
                sorted_values = sorted(values)
                mid = len(sorted_values) // 2
                if len(sorted_values) % 2 == 0:
                    aggregated[key] = (sorted_values[mid - 1] + sorted_values[mid]) / 2
                else:
                    aggregated[key] = sorted_values[mid]
            elif aggregation == 'min':
                aggregated[key] = min(values)
            elif aggregation == 'max':
                aggregated[key] = max(values)
            else:
                aggregated[key] = sum(values) / len(values)

        return aggregated

    @staticmethod
    def calculate_confidence_interval(
        patterns: List[ScoredPattern],
        confidence_level: float = 0.95
    ) -> Tuple[float, float]:
        """
        Calculate confidence interval for pattern scores.

        Args:
            patterns: List of scored patterns
            confidence_level: Confidence level (e.g., 0.95 for 95%)

        Returns:
            Tuple of (lower_bound, upper_bound)
        """
        if not patterns:
            return (0.0, 0.0)

        import statistics

        confidences = [p.confidence for p in patterns]

        if len(confidences) == 1:
            return (confidences[0], confidences[0])

        mean = statistics.mean(confidences)
        stdev = statistics.stdev(confidences)

        # Using normal distribution approximation
        # For 95% confidence: z = 1.96
        z_scores = {0.90: 1.645, 0.95: 1.96, 0.99: 2.576}
        z = z_scores.get(confidence_level, 1.96)

        margin = z * (stdev / (len(confidences) ** 0.5))

        lower = max(0.0, mean - margin)
        upper = min(1.0, mean + margin)

        return (lower, upper)


class ScoreAnalyzer:
    """
    Analyzer for pattern score distributions and statistics.
    """

    @staticmethod
    def analyze_score_distribution(
        patterns: List[ScoredPattern]
    ) -> Dict[str, any]:
        """
        Analyze the distribution of confidence scores.

        Args:
            patterns: List of scored patterns

        Returns:
            Dictionary with distribution statistics
        """
        if not patterns:
            return {
                'count': 0,
                'mean': 0.0,
                'median': 0.0,
                'std_dev': 0.0,
                'min': 0.0,
                'max': 0.0,
                'quartiles': (0.0, 0.0, 0.0)
            }

        import statistics

        confidences = [p.confidence for p in patterns]
        confidences_sorted = sorted(confidences)

        result = {
            'count': len(confidences),
            'mean': statistics.mean(confidences),
            'median': statistics.median(confidences),
            'min': min(confidences),
            'max': max(confidences)
        }

        if len(confidences) > 1:
            result['std_dev'] = statistics.stdev(confidences)
        else:
            result['std_dev'] = 0.0

        # Calculate quartiles
        n = len(confidences_sorted)
        if n >= 4:
            q1_idx = n // 4
            q2_idx = n // 2
            q3_idx = 3 * n // 4
            result['quartiles'] = (
                confidences_sorted[q1_idx],
                confidences_sorted[q2_idx],
                confidences_sorted[q3_idx]
            )
        else:
            result['quartiles'] = (result['min'], result['median'], result['max'])

        return result

    @staticmethod
    def identify_outliers(
        patterns: List[ScoredPattern],
        method: str = 'iqr',
        threshold: float = 1.5
    ) -> Tuple[List[ScoredPattern], List[ScoredPattern]]:
        """
        Identify outlier patterns based on confidence scores.

        Args:
            patterns: List of scored patterns
            method: Method to use ('iqr' or 'zscore')
            threshold: Threshold for outlier detection

        Returns:
            Tuple of (outliers, inliers)
        """
        if len(patterns) < 4:
            return ([], patterns)

        import statistics

        confidences = [p.confidence for p in patterns]

        if method == 'iqr':
            # Interquartile range method
            confidences_sorted = sorted(confidences)
            n = len(confidences_sorted)

            q1 = confidences_sorted[n // 4]
            q3 = confidences_sorted[3 * n // 4]
            iqr = q3 - q1

            lower_bound = q1 - threshold * iqr
            upper_bound = q3 + threshold * iqr

            outliers = [p for p in patterns if p.confidence < lower_bound or p.confidence > upper_bound]
            inliers = [p for p in patterns if lower_bound <= p.confidence <= upper_bound]

        elif method == 'zscore':
            # Z-score method
            mean = statistics.mean(confidences)
            stdev = statistics.stdev(confidences) if len(confidences) > 1 else 0

            if stdev == 0:
                return ([], patterns)

            outliers = []
            inliers = []

            for pattern in patterns:
                zscore = abs((pattern.confidence - mean) / stdev)
                if zscore > threshold:
                    outliers.append(pattern)
                else:
                    inliers.append(pattern)
        else:
            return ([], patterns)

        return (outliers, inliers)

    @staticmethod
    def calculate_score_variance(
        patterns: List[ScoredPattern],
        score_type: str = 'confidence'
    ) -> float:
        """
        Calculate variance for a specific score type.

        Args:
            patterns: List of scored patterns
            score_type: Type of score to analyze

        Returns:
            Variance value
        """
        if len(patterns) < 2:
            return 0.0

        import statistics

        scores = [getattr(p, score_type, 0) for p in patterns]
        return statistics.variance(scores)

    @staticmethod
    def compare_score_groups(
        group1: List[ScoredPattern],
        group2: List[ScoredPattern]
    ) -> Dict[str, any]:
        """
        Compare two groups of patterns statistically.

        Args:
            group1: First group of patterns
            group2: Second group of patterns

        Returns:
            Dictionary with comparison statistics
        """
        import statistics

        if not group1 or not group2:
            return {'valid': False, 'reason': 'Empty group'}

        scores1 = [p.confidence for p in group1]
        scores2 = [p.confidence for p in group2]

        mean1 = statistics.mean(scores1)
        mean2 = statistics.mean(scores2)

        return {
            'valid': True,
            'group1_mean': mean1,
            'group2_mean': mean2,
            'mean_difference': mean2 - mean1,
            'group1_size': len(group1),
            'group2_size': len(group2),
            'group1_std': statistics.stdev(scores1) if len(scores1) > 1 else 0,
            'group2_std': statistics.stdev(scores2) if len(scores2) > 1 else 0
        }
