"""Integration tests for services/intelligence modules.

Covers:
- PatternScorer: normalize_score, rank_patterns, filter_by_confidence,
  get_top_patterns, calculate_weighted_score, compare_patterns, aggregate_scores,
  calculate_confidence_interval
- ScoreAnalyzer: analyze_score_distribution, identify_outliers (iqr + zscore),
  calculate_score_variance, compare_score_groups
- ProfileMerger: resolve_conflicts (all strategies), merge_profiles,
  get_merge_conflicts, preserve_high_confidence, create_merged_profile
- ProfileMigrator: _find_migration_path, validate_migration,
  backup_before_migration, rollback_migration, migrate_version
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_profile(name: str, prefs: dict | None = None, confidence: float = 0.5):
    """Return a Profile with given prefs saved to an in-memory-like state."""
    from file_organizer.services.intelligence.profile_manager import Profile

    return Profile(
        profile_name=name,
        description=f"Test profile {name}",
        preferences=prefs
        or {"global": {"sort_by": "name", "theme": "dark"}, "directory_specific": {}},
        confidence_data={"sort_by": confidence, "theme": confidence},
        updated=datetime.now(UTC).isoformat(),
    )


def _make_pattern(pattern_id: str, confidence: float, frequency: float = 0.5):
    from file_organizer.services.intelligence.scoring import ScoredPattern

    return ScoredPattern(
        pattern_id=pattern_id,
        pattern_data={"key": pattern_id},
        confidence=confidence,
        frequency_score=frequency,
        recency_score=0.5,
        consistency_score=0.5,
    )


# ---------------------------------------------------------------------------
# PatternScorer
# ---------------------------------------------------------------------------


class TestPatternScorer:
    def test_normalize_score_midpoint(self) -> None:
        from file_organizer.services.intelligence.scoring import PatternScorer

        result = PatternScorer.normalize_score(0.5, min_val=0.0, max_val=1.0)
        assert result == pytest.approx(0.5, abs=1e-6)

    def test_normalize_score_clamps_above_max(self) -> None:
        from file_organizer.services.intelligence.scoring import PatternScorer

        result = PatternScorer.normalize_score(2.0, min_val=0.0, max_val=1.0)
        assert result == pytest.approx(1.0, abs=1e-6)

    def test_normalize_score_clamps_below_min(self) -> None:
        from file_organizer.services.intelligence.scoring import PatternScorer

        result = PatternScorer.normalize_score(-1.0, min_val=0.0, max_val=1.0)
        assert result == pytest.approx(0.0, abs=1e-6)

    def test_rank_patterns_sorted_descending_by_confidence(self) -> None:
        from file_organizer.services.intelligence.scoring import PatternScorer

        patterns = [
            _make_pattern("a", confidence=0.3),
            _make_pattern("b", confidence=0.9),
            _make_pattern("c", confidence=0.6),
        ]
        ranked = PatternScorer.rank_patterns(patterns)
        assert len(ranked) == 3
        assert ranked[0].pattern_id == "b"
        assert ranked[1].pattern_id == "c"
        assert ranked[2].pattern_id == "a"

    def test_rank_patterns_empty_returns_empty(self) -> None:
        from file_organizer.services.intelligence.scoring import PatternScorer

        assert PatternScorer.rank_patterns([]) == []

    def test_filter_by_confidence_threshold(self) -> None:
        from file_organizer.services.intelligence.scoring import PatternScorer

        patterns = [
            _make_pattern("low", confidence=0.3),
            _make_pattern("med", confidence=0.6),
            _make_pattern("high", confidence=0.9),
        ]
        filtered = PatternScorer.filter_by_confidence(patterns, min_confidence=0.5)
        assert len(filtered) == 2
        ids = {p.pattern_id for p in filtered}
        assert "low" not in ids
        assert "med" in ids
        assert "high" in ids

    def test_filter_by_confidence_all_below_returns_empty(self) -> None:
        from file_organizer.services.intelligence.scoring import PatternScorer

        patterns = [_make_pattern("x", confidence=0.1)]
        assert PatternScorer.filter_by_confidence(patterns, min_confidence=0.9) == []

    def test_get_top_patterns_limits_count(self) -> None:
        from file_organizer.services.intelligence.scoring import PatternScorer

        patterns = [_make_pattern(str(i), confidence=float(i) / 10) for i in range(10)]
        top = PatternScorer.get_top_patterns(patterns, n=3)
        assert len(top) == 3
        assert top[0].confidence >= top[1].confidence >= top[2].confidence

    def test_calculate_weighted_score_returns_float(self) -> None:
        from file_organizer.services.intelligence.scoring import PatternScorer

        scores = {"confidence": 0.8, "frequency": 0.5, "recency": 0.6}
        weights = {"confidence": 0.5, "frequency": 0.3, "recency": 0.2}
        result = PatternScorer.calculate_weighted_score(scores, weights)
        assert isinstance(result, float)
        assert 0.0 <= result <= 1.0

    def test_calculate_weighted_score_zero_weights(self) -> None:
        from file_organizer.services.intelligence.scoring import PatternScorer

        result = PatternScorer.calculate_weighted_score({}, {})
        assert result == 0.0

    def test_aggregate_scores_mean_returns_dict(self) -> None:
        from file_organizer.services.intelligence.scoring import PatternScorer

        patterns = [
            _make_pattern("a", confidence=0.2, frequency=0.4),
            _make_pattern("b", confidence=0.8, frequency=0.6),
        ]
        result = PatternScorer.aggregate_scores(patterns, aggregation="mean")
        assert isinstance(result, dict)
        assert "confidence" in result
        assert result["confidence"] == pytest.approx(0.5, abs=1e-9)

    def test_aggregate_scores_empty_returns_zeros(self) -> None:
        from file_organizer.services.intelligence.scoring import PatternScorer

        result = PatternScorer.aggregate_scores([])
        assert isinstance(result, dict)
        assert result["confidence"] == 0.0

    def test_compare_patterns_higher_confidence_wins(self) -> None:
        from file_organizer.services.intelligence.scoring import PatternScorer

        low = _make_pattern("low", confidence=0.2)
        high = _make_pattern("high", confidence=0.9)
        assert PatternScorer.compare_patterns(high, low) > 0

    def test_compare_patterns_equal_confidence(self) -> None:
        from file_organizer.services.intelligence.scoring import PatternScorer

        p1 = _make_pattern("a", confidence=0.5)
        p2 = _make_pattern("b", confidence=0.5)
        assert PatternScorer.compare_patterns(p1, p2) == 0

    def test_compare_patterns_lower_confidence_loses(self) -> None:
        from file_organizer.services.intelligence.scoring import PatternScorer

        low = _make_pattern("low", confidence=0.1)
        high = _make_pattern("high", confidence=0.9)
        assert PatternScorer.compare_patterns(low, high) < 0

    def test_calculate_confidence_interval_returns_tuple(self) -> None:
        from file_organizer.services.intelligence.scoring import PatternScorer

        patterns = [_make_pattern(str(i), confidence=0.7 + i * 0.02) for i in range(5)]
        lower, upper = PatternScorer.calculate_confidence_interval(patterns)
        assert isinstance(lower, float)
        assert isinstance(upper, float)
        assert lower <= upper

    def test_calculate_confidence_interval_single_pattern(self) -> None:
        from file_organizer.services.intelligence.scoring import PatternScorer

        patterns = [_make_pattern("only", confidence=0.75)]
        lower, upper = PatternScorer.calculate_confidence_interval(patterns)
        assert lower == pytest.approx(0.75)
        assert upper == pytest.approx(0.75)

    def test_calculate_confidence_interval_empty(self) -> None:
        from file_organizer.services.intelligence.scoring import PatternScorer

        lower, upper = PatternScorer.calculate_confidence_interval([])
        assert lower == 0.0
        assert upper == 0.0


# ---------------------------------------------------------------------------
# ScoreAnalyzer
# ---------------------------------------------------------------------------


class TestScoreAnalyzer:
    def test_analyze_score_distribution_basic(self) -> None:
        from file_organizer.services.intelligence.scoring import ScoreAnalyzer

        patterns = [_make_pattern(str(i), confidence=float(i) * 0.1) for i in range(1, 6)]
        distribution = ScoreAnalyzer.analyze_score_distribution(patterns)
        assert isinstance(distribution, dict)
        assert "mean" in distribution
        assert distribution["count"] == 5
        assert distribution["min"] < distribution["max"]

    def test_analyze_score_distribution_empty(self) -> None:
        from file_organizer.services.intelligence.scoring import ScoreAnalyzer

        result = ScoreAnalyzer.analyze_score_distribution([])
        assert isinstance(result, dict)
        assert result["count"] == 0

    def test_identify_outliers_iqr_returns_tuple(self) -> None:
        from file_organizer.services.intelligence.scoring import ScoreAnalyzer

        patterns = [_make_pattern(str(i), confidence=0.5) for i in range(6)]
        outliers, inliers = ScoreAnalyzer.identify_outliers(patterns, method="iqr")
        assert isinstance(outliers, list)
        assert isinstance(inliers, list)
        assert len(outliers) + len(inliers) == len(patterns)

    def test_identify_outliers_zscore_returns_tuple(self) -> None:
        from file_organizer.services.intelligence.scoring import ScoreAnalyzer

        patterns = [_make_pattern(str(i), confidence=0.5) for i in range(6)]
        outliers, inliers = ScoreAnalyzer.identify_outliers(patterns, method="zscore")
        assert isinstance(outliers, list)
        assert isinstance(inliers, list)
        assert len(outliers) + len(inliers) == len(patterns)

    def test_identify_outliers_too_few_returns_empty_outliers(self) -> None:
        from file_organizer.services.intelligence.scoring import ScoreAnalyzer

        patterns = [_make_pattern("a", confidence=0.5), _make_pattern("b", confidence=0.9)]
        outliers, inliers = ScoreAnalyzer.identify_outliers(patterns)
        assert outliers == []
        assert len(inliers) == 2

    def test_calculate_score_variance_non_negative(self) -> None:
        from file_organizer.services.intelligence.scoring import ScoreAnalyzer

        patterns = [_make_pattern(str(i), confidence=0.3 + i * 0.1) for i in range(5)]
        variance = ScoreAnalyzer.calculate_score_variance(patterns)
        assert isinstance(variance, float)
        assert variance >= 0.0

    def test_calculate_score_variance_identical_is_zero(self) -> None:
        from file_organizer.services.intelligence.scoring import ScoreAnalyzer

        patterns = [_make_pattern(str(i), confidence=0.5) for i in range(3)]
        variance = ScoreAnalyzer.calculate_score_variance(patterns)
        assert variance == pytest.approx(0.0, abs=1e-9)

    def test_calculate_score_variance_single_returns_zero(self) -> None:
        from file_organizer.services.intelligence.scoring import ScoreAnalyzer

        patterns = [_make_pattern("only", confidence=0.7)]
        variance = ScoreAnalyzer.calculate_score_variance(patterns)
        assert variance == 0.0

    def test_compare_score_groups_returns_dict(self) -> None:
        from file_organizer.services.intelligence.scoring import ScoreAnalyzer

        group_a = [_make_pattern(f"a{i}", confidence=0.3 + i * 0.05) for i in range(3)]
        group_b = [_make_pattern(f"b{i}", confidence=0.7 + i * 0.05) for i in range(3)]
        result = ScoreAnalyzer.compare_score_groups(group_a, group_b)
        assert isinstance(result, dict)
        assert result["valid"] is True
        assert result["group1_mean"] < result["group2_mean"]

    def test_compare_score_groups_empty_returns_invalid(self) -> None:
        from file_organizer.services.intelligence.scoring import ScoreAnalyzer

        result = ScoreAnalyzer.compare_score_groups([], [])
        assert result["valid"] is False


# ---------------------------------------------------------------------------
# ProfileMerger
# ---------------------------------------------------------------------------


class TestProfileMerger:
    def _make_manager(self, tmp_path: Path):
        from file_organizer.services.intelligence.profile_manager import ProfileManager

        return ProfileManager(storage_path=tmp_path)

    def _make_pref(self, value: str, updated: str, confidence: float) -> dict:
        return {"value": value, "metadata": {"updated": updated, "confidence": confidence}}

    def test_resolve_conflicts_recent_returns_most_recent(self, tmp_path: Path) -> None:
        from file_organizer.services.intelligence.profile_merger import MergeStrategy, ProfileMerger

        merger = ProfileMerger(self._make_manager(tmp_path))
        prefs = [
            self._make_pref("dark", "2026-01-01T00:00:00Z", confidence=0.9),
            self._make_pref("light", "2026-01-02T00:00:00Z", confidence=0.5),
        ]
        result = merger.resolve_conflicts(prefs, MergeStrategy.RECENT)
        assert result == "light"

    def test_resolve_conflicts_confident_picks_highest(self, tmp_path: Path) -> None:
        from file_organizer.services.intelligence.profile_merger import MergeStrategy, ProfileMerger

        merger = ProfileMerger(self._make_manager(tmp_path))
        prefs = [
            self._make_pref("option_a", "2026-01-01Z", confidence=0.9),
            self._make_pref("option_b", "2026-01-02Z", confidence=0.3),
        ]
        result = merger.resolve_conflicts(prefs, MergeStrategy.CONFIDENT)
        assert result == "option_a"

    def test_resolve_conflicts_first_returns_first(self, tmp_path: Path) -> None:
        from file_organizer.services.intelligence.profile_merger import MergeStrategy, ProfileMerger

        merger = ProfileMerger(self._make_manager(tmp_path))
        prefs = [
            self._make_pref("first_val", "2026-01-01Z", confidence=0.5),
            self._make_pref("second_val", "2026-01-02Z", confidence=0.5),
        ]
        result = merger.resolve_conflicts(prefs, MergeStrategy.FIRST)
        assert result == "first_val"

    def test_resolve_conflicts_last_returns_last(self, tmp_path: Path) -> None:
        from file_organizer.services.intelligence.profile_merger import MergeStrategy, ProfileMerger

        merger = ProfileMerger(self._make_manager(tmp_path))
        prefs = [
            self._make_pref("first_val", "2026-01-01Z", confidence=0.5),
            self._make_pref("last_val", "2026-01-02Z", confidence=0.5),
        ]
        result = merger.resolve_conflicts(prefs, MergeStrategy.LAST)
        assert result == "last_val"

    def test_resolve_conflicts_frequent_picks_most_common(self, tmp_path: Path) -> None:
        from file_organizer.services.intelligence.profile_merger import MergeStrategy, ProfileMerger

        merger = ProfileMerger(self._make_manager(tmp_path))
        prefs = [
            self._make_pref("dark", "2026-01-01Z", confidence=0.5),
            self._make_pref("dark", "2026-01-02Z", confidence=0.5),
            self._make_pref("light", "2026-01-03Z", confidence=0.5),
        ]
        result = merger.resolve_conflicts(prefs, MergeStrategy.FREQUENT)
        assert result == "dark"

    def test_resolve_conflicts_single_pref_returns_value(self, tmp_path: Path) -> None:
        from file_organizer.services.intelligence.profile_merger import MergeStrategy, ProfileMerger

        merger = ProfileMerger(self._make_manager(tmp_path))
        prefs = [self._make_pref("only", "2026-01-01Z", confidence=0.8)]
        result = merger.resolve_conflicts(prefs, MergeStrategy.CONFIDENT)
        assert result == "only"

    def test_get_merge_conflicts_detects_differing_prefs(self, tmp_path: Path) -> None:
        from file_organizer.services.intelligence.profile_merger import ProfileMerger

        manager = self._make_manager(tmp_path)
        merger = ProfileMerger(manager)

        p1 = manager.create_profile("alice_mc", "Alice")
        p2 = manager.create_profile("bob_mc", "Bob")
        assert p1 is not None and p2 is not None

        manager.update_profile(
            "alice_mc", preferences={"global": {"sort_by": "name"}, "directory_specific": {}}
        )
        manager.update_profile(
            "bob_mc", preferences={"global": {"sort_by": "date"}, "directory_specific": {}}
        )

        conflicts = merger.get_merge_conflicts(["alice_mc", "bob_mc"])
        assert isinstance(conflicts, dict)
        assert "global.sort_by" in conflicts

    def test_get_merge_conflicts_no_conflicts_when_identical(self, tmp_path: Path) -> None:
        from file_organizer.services.intelligence.profile_merger import ProfileMerger

        manager = self._make_manager(tmp_path)
        merger = ProfileMerger(manager)

        manager.create_profile("same_a", "Same A")
        manager.create_profile("same_b", "Same B")
        prefs = {"global": {"sort_by": "name"}, "directory_specific": {}}
        manager.update_profile("same_a", preferences=prefs)
        manager.update_profile("same_b", preferences=prefs)

        conflicts = merger.get_merge_conflicts(["same_a", "same_b"])
        assert isinstance(conflicts, dict)
        assert len(conflicts) == 0

    def test_create_merged_profile_returns_profile(self, tmp_path: Path) -> None:
        from file_organizer.services.intelligence.profile_merger import ProfileMerger

        manager = self._make_manager(tmp_path)
        merger = ProfileMerger(manager)
        merged_data = {
            "description": "Merged test profile",
            "preferences": {"global": {"sort_by": "name"}, "directory_specific": {}},
            "learned_patterns": {},
            "confidence_data": {},
        }
        profile = merger.create_merged_profile("merged_result_unique", merged_data)
        assert profile is not None
        assert profile.profile_name == "merged_result_unique"

    def test_merge_profiles_returns_profile(self, tmp_path: Path) -> None:
        from file_organizer.services.intelligence.profile_merger import ProfileMerger

        manager = self._make_manager(tmp_path)
        merger = ProfileMerger(manager)

        manager.create_profile("mp_source_a", "Source A")
        manager.create_profile("mp_source_b", "Source B")

        merged = merger.merge_profiles(["mp_source_a", "mp_source_b"], merge_strategy="confident")
        assert merged is not None
        assert merged.preferences is not None
        assert "global" in merged.preferences

    def test_preserve_high_confidence_does_not_raise(self, tmp_path: Path) -> None:
        from file_organizer.services.intelligence.profile_merger import ProfileMerger

        merger = ProfileMerger(self._make_manager(tmp_path))
        merged = _make_profile("merged", prefs={"global": {}, "directory_specific": {}})
        source = _make_profile(
            "source",
            prefs={"global": {"sort_by": "name"}, "directory_specific": {}},
            confidence=0.95,
        )
        merger.preserve_high_confidence(merged, [source], confidence_threshold=0.8)
        assert merged.preferences["global"]["sort_by"] == "name"


# ---------------------------------------------------------------------------
# ProfileMigrator
# ---------------------------------------------------------------------------


class TestProfileMigrator:
    def _make_manager(self, tmp_path: Path):
        from file_organizer.services.intelligence.profile_manager import ProfileManager

        return ProfileManager(storage_path=tmp_path)

    def test_find_migration_path_same_version_returns_empty(self, tmp_path: Path) -> None:
        from file_organizer.services.intelligence.profile_migrator import ProfileMigrator

        migrator = ProfileMigrator(self._make_manager(tmp_path))
        path = migrator._find_migration_path("1.0", "1.0")
        assert path == []

    def test_find_migration_path_unknown_version_returns_none(self, tmp_path: Path) -> None:
        from file_organizer.services.intelligence.profile_migrator import ProfileMigrator

        migrator = ProfileMigrator(self._make_manager(tmp_path))
        path = migrator._find_migration_path("0.9", "2.0")
        assert path is None

    def test_validate_migration_valid_profile_returns_true(self, tmp_path: Path) -> None:
        from file_organizer.services.intelligence.profile_migrator import ProfileMigrator

        manager = self._make_manager(tmp_path)
        manager.create_profile("test_valid", "A test profile")

        migrator = ProfileMigrator(manager)
        assert migrator.validate_migration("test_valid") is True

    def test_validate_migration_missing_profile_returns_false(self, tmp_path: Path) -> None:
        from file_organizer.services.intelligence.profile_migrator import ProfileMigrator

        migrator = ProfileMigrator(self._make_manager(tmp_path))
        assert migrator.validate_migration("nonexistent_profile") is False

    def test_backup_before_migration_creates_backup_file(self, tmp_path: Path) -> None:
        from file_organizer.services.intelligence.profile_migrator import ProfileMigrator

        manager = self._make_manager(tmp_path)
        p = manager.create_profile("backup_test", "Backup test profile")
        assert p is not None

        migrator = ProfileMigrator(manager)
        backup_path = migrator.backup_before_migration(p)
        assert backup_path is not None
        assert backup_path.exists()

    def test_rollback_migration_restores_from_backup(self, tmp_path: Path) -> None:
        from file_organizer.services.intelligence.profile_migrator import ProfileMigrator

        manager = self._make_manager(tmp_path)
        p = manager.create_profile("rollback_test", "Rollback test profile")
        assert p is not None

        migrator = ProfileMigrator(manager)
        backup_path = migrator.backup_before_migration(p)
        assert backup_path is not None

        result = migrator.rollback_migration("rollback_test", backup_path)
        assert result is True
        restored = manager.get_profile("rollback_test")
        assert restored is not None
        assert restored.profile_name == "rollback_test"

    def test_migrate_version_same_version_succeeds(self, tmp_path: Path) -> None:
        from file_organizer.services.intelligence.profile_migrator import ProfileMigrator

        manager = self._make_manager(tmp_path)
        p = manager.create_profile("migrate_test", "Migrate test")
        assert p is not None

        migrator = ProfileMigrator(manager)
        assert migrator.migrate_version("migrate_test", "1.0") is True

    def test_migrate_version_unsupported_target_returns_false(self, tmp_path: Path) -> None:
        from file_organizer.services.intelligence.profile_migrator import ProfileMigrator

        manager = self._make_manager(tmp_path)
        p = manager.create_profile("migrate_fail", "Migrate fail test")
        assert p is not None

        migrator = ProfileMigrator(manager)
        assert migrator.migrate_version("migrate_fail", "99.0") is False
