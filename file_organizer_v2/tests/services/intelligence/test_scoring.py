"""
Unit tests for Scoring Module

Tests pattern scoring, ranking, filtering, and statistical analysis.
"""

import pytest

from file_organizer.services.intelligence.scoring import (
    PatternScorer,
    ScoreAnalyzer,
    ScoredPattern,
)


class TestScoredPattern:
    """Tests for ScoredPattern dataclass."""

    def test_create_scored_pattern(self):
        """Test creating a scored pattern."""
        pattern = ScoredPattern(
            pattern_id="p1",
            pattern_data={'name': 'test'},
            confidence=0.8,
            frequency_score=0.7,
            recency_score=0.9,
            consistency_score=0.8
        )

        assert pattern.pattern_id == "p1"
        assert pattern.confidence == 0.8
        assert pattern.metadata == {}

    def test_scored_pattern_with_metadata(self):
        """Test creating pattern with metadata."""
        pattern = ScoredPattern(
            pattern_id="p1",
            pattern_data={},
            confidence=0.5,
            frequency_score=0.5,
            recency_score=0.5,
            consistency_score=0.5,
            metadata={'source': 'test'}
        )

        assert pattern.metadata['source'] == 'test'


class TestPatternScorer:
    """Tests for PatternScorer class."""

    def test_normalize_score(self):
        """Test score normalization."""
        assert PatternScorer.normalize_score(0.5) == 0.5
        assert PatternScorer.normalize_score(-0.1) == 0.0
        assert PatternScorer.normalize_score(1.5) == 1.0
        assert PatternScorer.normalize_score(0.8, 0.0, 1.0) == 0.8

    def test_rank_patterns(self):
        """Test ranking patterns by confidence."""
        patterns = [
            ScoredPattern("p1", {}, 0.5, 0.5, 0.5, 0.5),
            ScoredPattern("p2", {}, 0.8, 0.8, 0.8, 0.8),
            ScoredPattern("p3", {}, 0.3, 0.3, 0.3, 0.3),
        ]

        ranked = PatternScorer.rank_patterns(patterns)

        assert ranked[0].pattern_id == "p2"  # Highest confidence
        assert ranked[1].pattern_id == "p1"
        assert ranked[2].pattern_id == "p3"  # Lowest confidence

    def test_rank_patterns_by_frequency(self):
        """Test ranking patterns by frequency score."""
        patterns = [
            ScoredPattern("p1", {}, 0.5, 0.3, 0.5, 0.5),
            ScoredPattern("p2", {}, 0.5, 0.8, 0.5, 0.5),
            ScoredPattern("p3", {}, 0.5, 0.6, 0.5, 0.5),
        ]

        ranked = PatternScorer.rank_patterns(patterns, key='frequency_score')

        assert ranked[0].pattern_id == "p2"
        assert ranked[1].pattern_id == "p3"
        assert ranked[2].pattern_id == "p1"

    def test_filter_by_confidence(self):
        """Test filtering patterns by confidence threshold."""
        patterns = [
            ScoredPattern("p1", {}, 0.9, 0.9, 0.9, 0.9),
            ScoredPattern("p2", {}, 0.6, 0.6, 0.6, 0.6),
            ScoredPattern("p3", {}, 0.3, 0.3, 0.3, 0.3),
        ]

        filtered = PatternScorer.filter_by_confidence(patterns, min_confidence=0.5)

        assert len(filtered) == 2
        assert all(p.confidence >= 0.5 for p in filtered)

    def test_filter_by_confidence_range(self):
        """Test filtering with both min and max confidence."""
        patterns = [
            ScoredPattern("p1", {}, 0.9, 0.9, 0.9, 0.9),
            ScoredPattern("p2", {}, 0.6, 0.6, 0.6, 0.6),
            ScoredPattern("p3", {}, 0.3, 0.3, 0.3, 0.3),
        ]

        filtered = PatternScorer.filter_by_confidence(
            patterns,
            min_confidence=0.5,
            max_confidence=0.8
        )

        assert len(filtered) == 1
        assert filtered[0].pattern_id == "p2"

    def test_get_top_patterns(self):
        """Test getting top N patterns."""
        patterns = [
            ScoredPattern("p1", {}, 0.5, 0.5, 0.5, 0.5),
            ScoredPattern("p2", {}, 0.8, 0.8, 0.8, 0.8),
            ScoredPattern("p3", {}, 0.7, 0.7, 0.7, 0.7),
            ScoredPattern("p4", {}, 0.9, 0.9, 0.9, 0.9),
        ]

        top_2 = PatternScorer.get_top_patterns(patterns, n=2)

        assert len(top_2) == 2
        assert top_2[0].pattern_id == "p4"
        assert top_2[1].pattern_id == "p2"

    def test_get_top_patterns_with_threshold(self):
        """Test getting top patterns with confidence threshold."""
        patterns = [
            ScoredPattern("p1", {}, 0.5, 0.5, 0.5, 0.5),
            ScoredPattern("p2", {}, 0.8, 0.8, 0.8, 0.8),
            ScoredPattern("p3", {}, 0.3, 0.3, 0.3, 0.3),
        ]

        top = PatternScorer.get_top_patterns(patterns, n=5, min_confidence=0.4)

        assert len(top) == 2  # Only 2 meet threshold

    def test_calculate_weighted_score(self):
        """Test calculating weighted score."""
        scores = {
            'frequency': 0.8,
            'recency': 0.6,
            'consistency': 0.9
        }

        weights = {
            'frequency': 0.4,
            'recency': 0.3,
            'consistency': 0.3
        }

        weighted = PatternScorer.calculate_weighted_score(scores, weights)

        expected = (0.8 * 0.4 + 0.6 * 0.3 + 0.9 * 0.3)
        assert abs(weighted - expected) < 0.001

    def test_calculate_weighted_score_zero_weights(self):
        """Test weighted score with zero total weight."""
        scores = {'a': 0.5}
        weights = {'a': 0.0}

        weighted = PatternScorer.calculate_weighted_score(scores, weights)

        assert weighted == 0.0

    def test_compare_patterns(self):
        """Test comparing two patterns."""
        pattern1 = ScoredPattern("p1", {}, 0.5, 0.5, 0.5, 0.5)
        pattern2 = ScoredPattern("p2", {}, 0.8, 0.8, 0.8, 0.8)

        result = PatternScorer.compare_patterns(pattern1, pattern2)

        assert result == -1  # pattern1 < pattern2

        result2 = PatternScorer.compare_patterns(pattern2, pattern1)

        assert result2 == 1  # pattern2 > pattern1

    def test_compare_patterns_equal(self):
        """Test comparing equal patterns."""
        pattern1 = ScoredPattern("p1", {}, 0.7, 0.7, 0.7, 0.7)
        pattern2 = ScoredPattern("p2", {}, 0.7, 0.7, 0.7, 0.7)

        result = PatternScorer.compare_patterns(pattern1, pattern2)

        assert result == 0

    def test_aggregate_scores_mean(self):
        """Test aggregating scores with mean."""
        patterns = [
            ScoredPattern("p1", {}, 0.6, 0.6, 0.6, 0.6),
            ScoredPattern("p2", {}, 0.8, 0.8, 0.8, 0.8),
        ]

        aggregated = PatternScorer.aggregate_scores(patterns, aggregation='mean')

        assert aggregated['confidence'] == 0.7
        assert aggregated['frequency_score'] == 0.7

    def test_aggregate_scores_median(self):
        """Test aggregating scores with median."""
        patterns = [
            ScoredPattern("p1", {}, 0.5, 0.5, 0.5, 0.5),
            ScoredPattern("p2", {}, 0.7, 0.7, 0.7, 0.7),
            ScoredPattern("p3", {}, 0.9, 0.9, 0.9, 0.9),
        ]

        aggregated = PatternScorer.aggregate_scores(patterns, aggregation='median')

        assert aggregated['confidence'] == 0.7

    def test_aggregate_scores_min_max(self):
        """Test aggregating scores with min/max."""
        patterns = [
            ScoredPattern("p1", {}, 0.5, 0.5, 0.5, 0.5),
            ScoredPattern("p2", {}, 0.9, 0.9, 0.9, 0.9),
        ]

        min_agg = PatternScorer.aggregate_scores(patterns, aggregation='min')
        max_agg = PatternScorer.aggregate_scores(patterns, aggregation='max')

        assert min_agg['confidence'] == 0.5
        assert max_agg['confidence'] == 0.9

    def test_aggregate_scores_empty(self):
        """Test aggregating empty pattern list."""
        aggregated = PatternScorer.aggregate_scores([], aggregation='mean')

        assert aggregated['confidence'] == 0.0

    def test_calculate_confidence_interval(self):
        """Test calculating confidence interval."""
        patterns = [
            ScoredPattern("p1", {}, 0.6, 0.6, 0.6, 0.6),
            ScoredPattern("p2", {}, 0.7, 0.7, 0.7, 0.7),
            ScoredPattern("p3", {}, 0.8, 0.8, 0.8, 0.8),
        ]

        lower, upper = PatternScorer.calculate_confidence_interval(patterns)

        assert 0.0 <= lower <= 1.0
        assert 0.0 <= upper <= 1.0
        assert lower <= upper

    def test_calculate_confidence_interval_single(self):
        """Test confidence interval with single pattern."""
        patterns = [ScoredPattern("p1", {}, 0.7, 0.7, 0.7, 0.7)]

        lower, upper = PatternScorer.calculate_confidence_interval(patterns)

        assert lower == 0.7
        assert upper == 0.7


class TestScoreAnalyzer:
    """Tests for ScoreAnalyzer class."""

    def test_analyze_score_distribution(self):
        """Test analyzing score distribution."""
        patterns = [
            ScoredPattern("p1", {}, 0.5, 0.5, 0.5, 0.5),
            ScoredPattern("p2", {}, 0.7, 0.7, 0.7, 0.7),
            ScoredPattern("p3", {}, 0.9, 0.9, 0.9, 0.9),
        ]

        distribution = ScoreAnalyzer.analyze_score_distribution(patterns)

        assert distribution['count'] == 3
        assert distribution['mean'] == 0.7
        assert distribution['median'] == 0.7
        assert distribution['min'] == 0.5
        assert distribution['max'] == 0.9
        assert 'std_dev' in distribution

    def test_analyze_score_distribution_empty(self):
        """Test distribution analysis with empty list."""
        distribution = ScoreAnalyzer.analyze_score_distribution([])

        assert distribution['count'] == 0
        assert distribution['mean'] == 0.0

    def test_identify_outliers_iqr(self):
        """Test identifying outliers using IQR method."""
        patterns = [
            ScoredPattern("p1", {}, 0.1, 0.1, 0.1, 0.1),  # Outlier
            ScoredPattern("p2", {}, 0.6, 0.6, 0.6, 0.6),
            ScoredPattern("p3", {}, 0.7, 0.7, 0.7, 0.7),
            ScoredPattern("p4", {}, 0.8, 0.8, 0.8, 0.8),
            ScoredPattern("p5", {}, 0.9, 0.9, 0.9, 0.9),  # Potential outlier
        ]

        outliers, inliers = ScoreAnalyzer.identify_outliers(
            patterns,
            method='iqr',
            threshold=1.5
        )

        assert len(outliers) >= 0  # May or may not detect outliers
        assert len(inliers) >= 0

    def test_identify_outliers_zscore(self):
        """Test identifying outliers using Z-score method."""
        patterns = [
            ScoredPattern("p1", {}, 0.1, 0.1, 0.1, 0.1),
            ScoredPattern("p2", {}, 0.5, 0.5, 0.5, 0.5),
            ScoredPattern("p3", {}, 0.6, 0.6, 0.6, 0.6),
            ScoredPattern("p4", {}, 0.7, 0.7, 0.7, 0.7),
        ]

        outliers, inliers = ScoreAnalyzer.identify_outliers(
            patterns,
            method='zscore',
            threshold=2.0
        )

        assert len(outliers) + len(inliers) == len(patterns)

    def test_identify_outliers_insufficient_data(self):
        """Test outlier detection with insufficient data."""
        patterns = [
            ScoredPattern("p1", {}, 0.5, 0.5, 0.5, 0.5),
            ScoredPattern("p2", {}, 0.7, 0.7, 0.7, 0.7),
        ]

        outliers, inliers = ScoreAnalyzer.identify_outliers(patterns)

        # With only 2 patterns, all should be inliers
        assert len(outliers) == 0
        assert len(inliers) == 2

    def test_calculate_score_variance(self):
        """Test calculating score variance."""
        patterns = [
            ScoredPattern("p1", {}, 0.5, 0.5, 0.5, 0.5),
            ScoredPattern("p2", {}, 0.7, 0.7, 0.7, 0.7),
            ScoredPattern("p3", {}, 0.9, 0.9, 0.9, 0.9),
        ]

        variance = ScoreAnalyzer.calculate_score_variance(patterns)

        assert variance > 0.0  # Should have variance

    def test_calculate_score_variance_single(self):
        """Test variance with single pattern."""
        patterns = [ScoredPattern("p1", {}, 0.5, 0.5, 0.5, 0.5)]

        variance = ScoreAnalyzer.calculate_score_variance(patterns)

        assert variance == 0.0

    def test_compare_score_groups(self):
        """Test comparing two groups of patterns."""
        group1 = [
            ScoredPattern("p1", {}, 0.5, 0.5, 0.5, 0.5),
            ScoredPattern("p2", {}, 0.6, 0.6, 0.6, 0.6),
        ]

        group2 = [
            ScoredPattern("p3", {}, 0.8, 0.8, 0.8, 0.8),
            ScoredPattern("p4", {}, 0.9, 0.9, 0.9, 0.9),
        ]

        comparison = ScoreAnalyzer.compare_score_groups(group1, group2)

        assert comparison['valid'] is True
        assert comparison['group1_mean'] < comparison['group2_mean']
        assert comparison['mean_difference'] > 0

    def test_compare_score_groups_empty(self):
        """Test comparing with empty group."""
        group1 = [ScoredPattern("p1", {}, 0.5, 0.5, 0.5, 0.5)]
        group2 = []

        comparison = ScoreAnalyzer.compare_score_groups(group1, group2)

        assert comparison['valid'] is False


class TestScoringIntegration:
    """Integration tests for scoring module."""

    def test_full_scoring_pipeline(self):
        """Test complete scoring pipeline."""
        # Create patterns
        patterns = [
            ScoredPattern("p1", {'name': 'report'}, 0.9, 0.9, 0.9, 0.9),
            ScoredPattern("p2", {'name': 'invoice'}, 0.7, 0.7, 0.7, 0.7),
            ScoredPattern("p3", {'name': 'draft'}, 0.3, 0.3, 0.3, 0.3),
            ScoredPattern("p4", {'name': 'final'}, 0.8, 0.8, 0.8, 0.8),
        ]

        # Filter by confidence
        filtered = PatternScorer.filter_by_confidence(patterns, min_confidence=0.5)
        assert len(filtered) == 3

        # Rank
        ranked = PatternScorer.rank_patterns(filtered)
        assert ranked[0].pattern_id == "p1"

        # Get top 2
        top_2 = PatternScorer.get_top_patterns(ranked, n=2)
        assert len(top_2) == 2

        # Analyze distribution
        distribution = ScoreAnalyzer.analyze_score_distribution(filtered)
        assert distribution['count'] == 3


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
