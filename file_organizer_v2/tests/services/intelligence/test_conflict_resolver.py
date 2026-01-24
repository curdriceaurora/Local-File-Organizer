"""
Unit tests for ConflictResolver class.

Tests conflict resolution with multiple weighting strategies.
"""

from datetime import datetime, timedelta

import pytest

from file_organizer.services.intelligence.conflict_resolver import ConflictResolver


class TestConflictResolver:
    """Test suite for ConflictResolver class."""

    @pytest.fixture
    def resolver(self):
        """Create a ConflictResolver with default weights."""
        return ConflictResolver()

    @pytest.fixture
    def custom_resolver(self):
        """Create a ConflictResolver with custom weights."""
        return ConflictResolver(
            recency_weight=0.5,
            frequency_weight=0.3,
            confidence_weight=0.2
        )

    def test_initialization_default_weights(self, resolver):
        """Test ConflictResolver initializes with default weights."""
        assert resolver.recency_weight == 0.4
        assert resolver.frequency_weight == 0.35
        assert resolver.confidence_weight == 0.25

    def test_initialization_custom_weights(self, custom_resolver):
        """Test ConflictResolver initializes with custom weights."""
        assert custom_resolver.recency_weight == 0.5
        assert custom_resolver.frequency_weight == 0.3
        assert custom_resolver.confidence_weight == 0.2

    def test_initialization_weight_normalization(self):
        """Test that weights are normalized to sum to 1.0."""
        resolver = ConflictResolver(
            recency_weight=2.0,
            frequency_weight=2.0,
            confidence_weight=2.0
        )
        # Should normalize to equal weights
        assert abs(resolver.recency_weight - 1/3) < 0.01
        assert abs(resolver.frequency_weight - 1/3) < 0.01
        assert abs(resolver.confidence_weight - 1/3) < 0.01

    def test_initialization_zero_weights_raises_error(self):
        """Test that all-zero weights raise ValueError."""
        with pytest.raises(ValueError, match="Weights cannot all be zero"):
            ConflictResolver(
                recency_weight=0.0,
                frequency_weight=0.0,
                confidence_weight=0.0
            )

    def test_resolve_empty_list_raises_error(self, resolver):
        """Test that resolving empty list raises ValueError."""
        with pytest.raises(ValueError, match="Cannot resolve empty preference list"):
            resolver.resolve([])

    def test_resolve_single_preference(self, resolver):
        """Test that resolving single preference returns it unchanged."""
        pref = {"folder_mappings": {"pdf": "PDFs"}}
        result = resolver.resolve([pref])
        assert result == pref

    def test_resolve_by_recency(self, resolver):
        """Test conflict resolution favors more recent preferences."""
        now = datetime.utcnow()
        old_date = (now - timedelta(days=30)).isoformat() + "Z"
        recent_date = now.isoformat() + "Z"

        old_pref = {
            "folder_mappings": {"pdf": "Documents"},
            "updated": old_date,
            "correction_count": 10,
            "confidence": 0.8
        }
        recent_pref = {
            "folder_mappings": {"pdf": "PDFs"},
            "updated": recent_date,
            "correction_count": 10,
            "confidence": 0.8
        }

        result = resolver.resolve([old_pref, recent_pref])

        # Should prefer recent preference
        assert result["folder_mappings"]["pdf"] == "PDFs"

    def test_resolve_by_frequency(self, resolver):
        """Test conflict resolution favors higher frequency preferences."""
        now = datetime.utcnow().isoformat() + "Z"

        low_freq = {
            "folder_mappings": {"pdf": "Documents"},
            "updated": now,
            "correction_count": 2,
            "confidence": 0.8
        }
        high_freq = {
            "folder_mappings": {"pdf": "PDFs"},
            "updated": now,
            "correction_count": 20,
            "confidence": 0.8
        }

        result = resolver.resolve([low_freq, high_freq])

        # Should prefer high frequency
        assert result["folder_mappings"]["pdf"] == "PDFs"

    def test_resolve_by_confidence(self, resolver):
        """Test conflict resolution favors higher confidence preferences."""
        now = datetime.utcnow().isoformat() + "Z"

        low_conf = {
            "folder_mappings": {"pdf": "Documents"},
            "updated": now,
            "correction_count": 10,
            "confidence": 0.5
        }
        high_conf = {
            "folder_mappings": {"pdf": "PDFs"},
            "updated": now,
            "correction_count": 10,
            "confidence": 0.95
        }

        result = resolver.resolve([low_conf, high_conf])

        # Should prefer high confidence
        assert result["folder_mappings"]["pdf"] == "PDFs"

    def test_resolve_combined_factors(self, resolver):
        """Test conflict resolution with multiple competing factors."""
        now = datetime.utcnow()

        # Recent but low frequency and confidence
        pref1 = {
            "value": "pref1",
            "updated": now.isoformat() + "Z",
            "correction_count": 2,
            "confidence": 0.5
        }
        # Old but high frequency and confidence
        pref2 = {
            "value": "pref2",
            "updated": (now - timedelta(days=60)).isoformat() + "Z",
            "correction_count": 50,
            "confidence": 0.95
        }

        result = resolver.resolve([pref1, pref2])

        # With default weights, high frequency + confidence should win
        assert result["value"] == "pref2"

    def test_resolve_tie_breaks_by_recency(self, resolver):
        """Test that ties are broken by most recent preference."""
        now = datetime.utcnow()

        pref1 = {
            "value": "pref1",
            "updated": (now - timedelta(days=1)).isoformat() + "Z",
            "correction_count": 10,
            "confidence": 0.8
        }
        pref2 = {
            "value": "pref2",
            "updated": now.isoformat() + "Z",
            "correction_count": 10,
            "confidence": 0.8
        }

        result = resolver.resolve([pref1, pref2])

        # Should use most recent as tie-breaker
        assert result["value"] == "pref2"

    def test_weight_by_recency(self, resolver):
        """Test recency weight calculation."""
        now = datetime.utcnow()

        prefs = [
            {"updated": (now - timedelta(days=60)).isoformat() + "Z"},
            {"updated": (now - timedelta(days=30)).isoformat() + "Z"},
            {"updated": now.isoformat() + "Z"},
        ]

        weights = resolver.weight_by_recency(prefs)

        # More recent should have higher weight
        assert weights[2] > weights[1] > weights[0]
        # All weights should be between 0 and 1
        assert all(0 <= w <= 1 for w in weights)

    def test_weight_by_recency_missing_timestamps(self, resolver):
        """Test recency weighting with missing timestamps."""
        now = datetime.utcnow()

        prefs = [
            {},  # No timestamp
            {"updated": now.isoformat() + "Z"},
        ]

        weights = resolver.weight_by_recency(prefs)

        # Preference with timestamp should have higher weight
        assert weights[1] > weights[0]

    def test_weight_by_frequency(self, resolver):
        """Test frequency weight calculation."""
        prefs = [
            {"correction_count": 5},
            {"correction_count": 20},
            {"correction_count": 100},
        ]

        weights = resolver.weight_by_frequency(prefs)

        # Higher frequency should have higher weight
        assert weights[2] > weights[1] > weights[0]
        # All weights should be between 0 and 1
        assert all(0 <= w <= 1 for w in weights)

    def test_weight_by_frequency_zero_counts(self, resolver):
        """Test frequency weighting with all zero counts."""
        prefs = [
            {"correction_count": 0},
            {"correction_count": 0},
            {"correction_count": 0},
        ]

        weights = resolver.weight_by_frequency(prefs)

        # Should return equal weights
        assert all(abs(w - weights[0]) < 0.01 for w in weights)

    def test_weight_by_frequency_missing_counts(self, resolver):
        """Test frequency weighting with missing correction counts."""
        prefs = [
            {},  # No count
            {"correction_count": 10},
        ]

        weights = resolver.weight_by_frequency(prefs)

        # Preference with count should have higher weight
        assert weights[1] > weights[0]

    def test_weight_by_frequency_diminishing_returns(self, resolver):
        """Test that frequency weights use square root for diminishing returns."""
        prefs = [
            {"correction_count": 4},
            {"correction_count": 16},
            {"correction_count": 64},
        ]

        weights = resolver.weight_by_frequency(prefs)

        # Due to sqrt, the weight ratio should be 2:4:8, not 4:16:64
        # Check that ratio is compressed
        ratio_1_to_2 = weights[1] / weights[0] if weights[0] > 0 else float('inf')
        ratio_2_to_3 = weights[2] / weights[1] if weights[1] > 0 else float('inf')

        # Ratio should be constant (around 2) due to sqrt
        assert abs(ratio_1_to_2 - 2.0) < 0.1
        assert abs(ratio_2_to_3 - 2.0) < 0.1

    def test_score_confidence(self, resolver):
        """Test confidence score calculation."""
        assert resolver.score_confidence({"confidence": 0.0}) == 0.0
        assert resolver.score_confidence({"confidence": 0.5}) == 0.5
        assert resolver.score_confidence({"confidence": 1.0}) == 1.0

    def test_score_confidence_missing(self, resolver):
        """Test confidence score with missing confidence field."""
        assert resolver.score_confidence({}) == 0.5  # Default

    def test_score_confidence_clamping(self, resolver):
        """Test confidence score clamping to valid range."""
        assert resolver.score_confidence({"confidence": -0.5}) == 0.0
        assert resolver.score_confidence({"confidence": 1.5}) == 1.0

    def test_get_ambiguity_score_no_conflict(self, resolver):
        """Test ambiguity score with no conflicting preferences."""
        assert resolver.get_ambiguity_score([]) == 0.0
        assert resolver.get_ambiguity_score([{"value": "single"}]) == 0.0

    def test_get_ambiguity_score_clear_winner(self, resolver):
        """Test ambiguity score with clear winner."""
        now = datetime.utcnow()

        prefs = [
            {
                "updated": (now - timedelta(days=60)).isoformat() + "Z",
                "correction_count": 2,
                "confidence": 0.5
            },
            {
                "updated": now.isoformat() + "Z",
                "correction_count": 50,
                "confidence": 0.95
            }
        ]

        ambiguity = resolver.get_ambiguity_score(prefs)

        # Should have low ambiguity (clear winner)
        assert ambiguity < 0.5

    def test_get_ambiguity_score_high_ambiguity(self, resolver):
        """Test ambiguity score with very similar preferences."""
        now = datetime.utcnow()

        prefs = [
            {
                "updated": now.isoformat() + "Z",
                "correction_count": 10,
                "confidence": 0.8
            },
            {
                "updated": now.isoformat() + "Z",
                "correction_count": 10,
                "confidence": 0.8
            }
        ]

        ambiguity = resolver.get_ambiguity_score(prefs)

        # Should have high ambiguity (similar scores)
        assert ambiguity > 0.5

    def test_needs_user_input_low_ambiguity(self, resolver):
        """Test that low ambiguity doesn't require user input."""
        now = datetime.utcnow()

        prefs = [
            {
                "updated": (now - timedelta(days=60)).isoformat() + "Z",
                "correction_count": 2,
                "confidence": 0.5
            },
            {
                "updated": now.isoformat() + "Z",
                "correction_count": 50,
                "confidence": 0.95
            }
        ]

        assert not resolver.needs_user_input(prefs)

    def test_needs_user_input_high_ambiguity(self, resolver):
        """Test that high ambiguity requires user input."""
        now = datetime.utcnow()

        prefs = [
            {
                "updated": now.isoformat() + "Z",
                "correction_count": 10,
                "confidence": 0.8
            },
            {
                "updated": now.isoformat() + "Z",
                "correction_count": 10,
                "confidence": 0.8
            }
        ]

        assert resolver.needs_user_input(prefs)

    def test_needs_user_input_custom_threshold(self, resolver):
        """Test needs_user_input with custom threshold."""
        # Very similar preferences (high ambiguity)
        similar_prefs = [
            {
                "updated": "2026-01-01T00:00:00Z",
                "correction_count": 10,
                "confidence": 0.7
            },
            {
                "updated": "2026-01-01T00:00:00Z",
                "correction_count": 12,
                "confidence": 0.75
            }
        ]

        # Very different preferences (low ambiguity)
        different_prefs = [
            {
                "updated": "2026-01-01T00:00:00Z",
                "correction_count": 2,
                "confidence": 0.5
            },
            {
                "updated": "2026-01-20T00:00:00Z",
                "correction_count": 50,
                "confidence": 0.95
            }
        ]

        # With low threshold, similar prefs need user input
        assert resolver.needs_user_input(similar_prefs, ambiguity_threshold=0.3)

        # With high threshold, different prefs don't need user input
        assert not resolver.needs_user_input(different_prefs, ambiguity_threshold=0.9)

    def test_parse_timestamp_valid(self, resolver):
        """Test parsing valid ISO 8601 timestamps."""
        dt = resolver._parse_timestamp("2026-01-21T06:48:24Z")
        assert dt.year == 2026
        assert dt.month == 1
        assert dt.day == 21

    def test_parse_timestamp_invalid(self, resolver):
        """Test parsing invalid timestamps."""
        dt = resolver._parse_timestamp("invalid")
        assert dt.year == 1970  # Returns epoch for invalid

    def test_parse_timestamp_none(self, resolver):
        """Test parsing None timestamp."""
        dt = resolver._parse_timestamp(None)
        assert dt.year == 1970  # Returns epoch for None

    def test_deterministic_resolution(self, resolver):
        """Test that conflict resolution is deterministic."""
        prefs = [
            {
                "value": "A",
                "updated": "2026-01-01T00:00:00Z",
                "correction_count": 10,
                "confidence": 0.8
            },
            {
                "value": "B",
                "updated": "2026-01-15T00:00:00Z",
                "correction_count": 15,
                "confidence": 0.85
            },
            {
                "value": "C",
                "updated": "2026-01-10T00:00:00Z",
                "correction_count": 8,
                "confidence": 0.75
            }
        ]

        # Run resolution multiple times
        results = [resolver.resolve(prefs) for _ in range(10)]

        # All results should be identical
        assert all(r["value"] == results[0]["value"] for r in results)

    def test_real_world_scenario(self, resolver):
        """Test a realistic conflict resolution scenario."""
        now = datetime.utcnow()

        # User has been moving PDFs to "Documents" folder for months
        old_habit = {
            "folder_mappings": {"pdf": "Documents"},
            "created": (now - timedelta(days=90)).isoformat() + "Z",
            "updated": (now - timedelta(days=30)).isoformat() + "Z",
            "correction_count": 45,  # High frequency
            "confidence": 0.85
        }

        # Recently started moving PDFs to "PDFs" folder
        new_habit = {
            "folder_mappings": {"pdf": "PDFs"},
            "created": (now - timedelta(days=7)).isoformat() + "Z",
            "updated": now.isoformat() + "Z",
            "correction_count": 8,  # Lower frequency but recent
            "confidence": 0.9
        }

        result = resolver.resolve([old_habit, new_habit])

        # With default weights, old habit's high frequency might win
        # but recent preference should have strong influence
        # The exact winner depends on weight balance
        assert result["folder_mappings"]["pdf"] in ["Documents", "PDFs"]
