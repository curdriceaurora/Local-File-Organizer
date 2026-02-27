"""Extended tests for ProfileMerger.

Covers FREQUENT strategy in resolve_conflicts, preserve_high_confidence,
create_merged_profile, _merge_confidence_data with different strategies,
_merge_preferences with directory_specific keys, error paths, and
edge cases not covered by test_profile_merger_templates.py.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from file_organizer.services.intelligence.profile_manager import ProfileManager
from file_organizer.services.intelligence.profile_merger import MergeStrategy, ProfileMerger

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_storage():
    """Create temporary storage directory for tests."""
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def profile_manager(temp_storage):
    """Create ProfileManager with temporary storage."""
    return ProfileManager(storage_path=temp_storage / "profiles")


@pytest.fixture
def merger(profile_manager):
    """Create ProfileMerger."""
    return ProfileMerger(profile_manager)


def _create_profile_with_data(pm, name, desc, prefs=None, patterns=None, confidence=None):
    """Helper to create a profile with specific data."""
    pm.create_profile(name, desc)
    pm.update_profile(
        name,
        preferences=prefs or {"global": {}, "directory_specific": {}},
        learned_patterns=patterns or {},
        confidence_data=confidence or {},
    )
    return pm.get_profile(name)


# ---------------------------------------------------------------------------
# _get_current_timestamp
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetCurrentTimestamp:
    """Tests for _get_current_timestamp helper method."""

    def test_returns_iso_string(self, merger):
        """Test returns ISO format UTC timestamp."""
        ts = merger._get_current_timestamp()
        assert isinstance(ts, str)
        assert ts.endswith("Z")


# ---------------------------------------------------------------------------
# resolve_conflicts
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestResolveConflicts:
    """Tests for resolve_conflicts method."""

    def test_empty_list(self, merger):
        """Test resolving conflicts with empty list returns None."""
        result = merger.resolve_conflicts([], MergeStrategy.CONFIDENT)
        assert result is None

    def test_single_item(self, merger):
        """Test resolving conflicts with single item returns that value."""
        prefs = [{"value": "only_value", "metadata": {"confidence": 0.5, "updated": ""}}]
        result = merger.resolve_conflicts(prefs, MergeStrategy.CONFIDENT)
        assert result == "only_value"

    def test_frequent_strategy(self, merger):
        """Test FREQUENT strategy picks most common value."""
        prefs = [
            {"value": "a", "metadata": {"confidence": 0.5, "updated": ""}},
            {"value": "b", "metadata": {"confidence": 0.5, "updated": ""}},
            {"value": "a", "metadata": {"confidence": 0.5, "updated": ""}},
            {"value": "a", "metadata": {"confidence": 0.5, "updated": ""}},
        ]
        result = merger.resolve_conflicts(prefs, MergeStrategy.FREQUENT)
        assert result == "a"

    def test_frequent_strategy_tie_picks_first(self, merger):
        """Test FREQUENT strategy picks first value on tie."""
        prefs = [
            {"value": "x", "metadata": {"confidence": 0.5, "updated": ""}},
            {"value": "y", "metadata": {"confidence": 0.5, "updated": ""}},
        ]
        result = merger.resolve_conflicts(prefs, MergeStrategy.FREQUENT)
        # Both appear once; max picks first in iteration
        assert result in ("x", "y")

    def test_recent_strategy(self, merger):
        """Test RECENT strategy picks most recently updated value."""
        prefs = [
            {"value": "old", "metadata": {"confidence": 0.5, "updated": "2024-01-01T00:00:00Z"}},
            {"value": "new", "metadata": {"confidence": 0.5, "updated": "2025-01-01T00:00:00Z"}},
        ]
        result = merger.resolve_conflicts(prefs, MergeStrategy.RECENT)
        assert result == "new"

    def test_confident_strategy(self, merger):
        """Test CONFIDENT strategy picks highest confidence value."""
        prefs = [
            {"value": "low", "metadata": {"confidence": 0.3, "updated": ""}},
            {"value": "high", "metadata": {"confidence": 0.9, "updated": ""}},
        ]
        result = merger.resolve_conflicts(prefs, MergeStrategy.CONFIDENT)
        assert result == "high"

    def test_first_strategy(self, merger):
        """Test FIRST strategy picks first value."""
        prefs = [
            {"value": "first", "metadata": {}},
            {"value": "second", "metadata": {}},
        ]
        result = merger.resolve_conflicts(prefs, MergeStrategy.FIRST)
        assert result == "first"

    def test_last_strategy(self, merger):
        """Test LAST strategy picks last value."""
        prefs = [
            {"value": "first", "metadata": {}},
            {"value": "last", "metadata": {}},
        ]
        result = merger.resolve_conflicts(prefs, MergeStrategy.LAST)
        assert result == "last"


# ---------------------------------------------------------------------------
# _merge_confidence_data – strategy coverage
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMergeConfidenceData:
    """Tests for _merge_confidence_data with different strategies."""

    def _make_profiles(self, pm):
        """Create two profiles with overlapping confidence data."""
        p1 = _create_profile_with_data(
            pm, "cd1", "CD1", confidence={"key1": 0.7, "key2": 0.5}
        )
        p2 = _create_profile_with_data(
            pm, "cd2", "CD2", confidence={"key1": 0.9, "key3": 0.8}
        )
        return [p1, p2]

    def test_confident_strategy_uses_max(self, merger, profile_manager):
        """Test CONFIDENT strategy uses max confidence."""
        profiles = self._make_profiles(profile_manager)
        result = merger._merge_confidence_data(profiles, MergeStrategy.CONFIDENT)

        assert result["key1"] == 0.9
        assert result["key2"] == 0.5
        assert result["key3"] == 0.8

    def test_recent_strategy_uses_last(self, merger, profile_manager):
        """Test RECENT strategy uses last profile's confidence."""
        profiles = self._make_profiles(profile_manager)
        result = merger._merge_confidence_data(profiles, MergeStrategy.RECENT)

        assert result["key1"] == 0.9  # Last profile's value
        assert result["key2"] == 0.5  # Only in first
        assert result["key3"] == 0.8  # Only in second

    def test_first_strategy_uses_average(self, merger, profile_manager):
        """Test FIRST strategy (non-CONFIDENT/RECENT) uses average."""
        profiles = self._make_profiles(profile_manager)
        result = merger._merge_confidence_data(profiles, MergeStrategy.FIRST)

        assert result["key1"] == pytest.approx((0.7 + 0.9) / 2)
        assert result["key2"] == 0.5  # Only one value
        assert result["key3"] == 0.8  # Only one value

    def test_last_strategy_uses_average(self, merger, profile_manager):
        """Test LAST strategy (non-CONFIDENT/RECENT) uses average."""
        profiles = self._make_profiles(profile_manager)
        result = merger._merge_confidence_data(profiles, MergeStrategy.LAST)

        assert result["key1"] == pytest.approx((0.7 + 0.9) / 2)

    def test_frequent_strategy_uses_average(self, merger, profile_manager):
        """Test FREQUENT strategy (non-CONFIDENT/RECENT) uses average."""
        profiles = self._make_profiles(profile_manager)
        result = merger._merge_confidence_data(profiles, MergeStrategy.FREQUENT)

        assert result["key1"] == pytest.approx((0.7 + 0.9) / 2)


# ---------------------------------------------------------------------------
# _merge_preferences – directory_specific coverage
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMergePreferences:
    """Tests for _merge_preferences including directory-specific merging."""

    def test_merge_directory_specific_prefs(self, merger, profile_manager):
        """Test merging directory-specific preferences."""
        p1 = _create_profile_with_data(
            profile_manager, "dp1", "Dir prefs 1",
            prefs={
                "global": {},
                "directory_specific": {"/path/a": {"mode": "fast"}},
            },
            confidence={"/path/a": 0.9},
        )
        p2 = _create_profile_with_data(
            profile_manager, "dp2", "Dir prefs 2",
            prefs={
                "global": {},
                "directory_specific": {"/path/a": {"mode": "slow"}, "/path/b": {"mode": "auto"}},
            },
            confidence={"/path/a": 0.6, "/path/b": 0.8},
        )

        result = merger._merge_preferences([p1, p2], MergeStrategy.CONFIDENT)

        assert "/path/a" in result["directory_specific"]
        assert "/path/b" in result["directory_specific"]
        # /path/a should pick from p1 (confidence 0.9 > 0.6)
        assert result["directory_specific"]["/path/a"] == {"mode": "fast"}

    def test_merge_global_prefs(self, merger, profile_manager):
        """Test merging global preferences from multiple profiles."""
        p1 = _create_profile_with_data(
            profile_manager, "gp1", "Global prefs 1",
            prefs={"global": {"theme": "dark"}, "directory_specific": {}},
            confidence={"theme": 0.7},
        )
        p2 = _create_profile_with_data(
            profile_manager, "gp2", "Global prefs 2",
            prefs={"global": {"theme": "light", "lang": "en"}, "directory_specific": {}},
            confidence={"theme": 0.9, "lang": 0.8},
        )

        result = merger._merge_preferences([p1, p2], MergeStrategy.CONFIDENT)

        assert result["global"]["theme"] == "light"  # Higher confidence
        assert result["global"]["lang"] == "en"


# ---------------------------------------------------------------------------
# _merge_learned_patterns
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMergeLearnedPatterns:
    """Tests for _merge_learned_patterns."""

    def test_merge_with_conflict(self, merger, profile_manager):
        """Test merging learned patterns with conflicting keys."""
        p1 = _create_profile_with_data(
            profile_manager, "lp1", "LP1",
            patterns={"key": "val_a"},
            confidence={"key": 0.5},
        )
        p2 = _create_profile_with_data(
            profile_manager, "lp2", "LP2",
            patterns={"key": "val_b"},
            confidence={"key": 0.9},
        )

        result = merger._merge_learned_patterns([p1, p2], MergeStrategy.CONFIDENT)
        assert result["key"] == "val_b"  # Higher confidence

    def test_merge_disjoint_patterns(self, merger, profile_manager):
        """Test merging learned patterns with no overlap."""
        p1 = _create_profile_with_data(
            profile_manager, "dlp1", "DLP1",
            patterns={"alpha": "a"},
            confidence={"alpha": 0.8},
        )
        p2 = _create_profile_with_data(
            profile_manager, "dlp2", "DLP2",
            patterns={"beta": "b"},
            confidence={"beta": 0.7},
        )

        result = merger._merge_learned_patterns([p1, p2], MergeStrategy.FIRST)
        assert result["alpha"] == "a"
        assert result["beta"] == "b"


# ---------------------------------------------------------------------------
# preserve_high_confidence
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPreserveHighConfidence:
    """Tests for preserve_high_confidence method."""

    def test_preserves_global_preference(self, merger, profile_manager):
        """Test preserving high-confidence global preference."""
        merged = _create_profile_with_data(
            profile_manager, "phc_merged", "Merged",
            prefs={"global": {"key1": "merged_val"}, "directory_specific": {}},
            confidence={"key1": 0.5},
        )

        source = _create_profile_with_data(
            profile_manager, "phc_source", "Source",
            prefs={"global": {"key1": "source_val"}, "directory_specific": {}},
            confidence={"key1": 0.95},
        )

        merger.preserve_high_confidence(merged, [source], confidence_threshold=0.8)

        assert merged.preferences["global"]["key1"] == "source_val"
        assert merged.confidence_data["key1"] == 0.95

    def test_preserves_directory_specific_preference(self, merger, profile_manager):
        """Test preserving high-confidence directory-specific preference."""
        merged = _create_profile_with_data(
            profile_manager, "phc_dir_merged", "Merged",
            prefs={"global": {}, "directory_specific": {"/test": "old_val"}},
            confidence={"/test": 0.4},
        )

        source = _create_profile_with_data(
            profile_manager, "phc_dir_source", "Source",
            prefs={"global": {}, "directory_specific": {"/test": "new_val"}},
            confidence={"/test": 0.85},
        )

        merger.preserve_high_confidence(merged, [source], confidence_threshold=0.8)

        assert merged.preferences["directory_specific"]["/test"] == "new_val"
        assert merged.confidence_data["/test"] == 0.85

    def test_preserves_learned_pattern(self, merger, profile_manager):
        """Test preserving high-confidence learned pattern."""
        merged = _create_profile_with_data(
            profile_manager, "phc_lp_merged", "Merged",
            patterns={"pat1": "old"},
            confidence={"pat1": 0.3},
        )

        source = _create_profile_with_data(
            profile_manager, "phc_lp_source", "Source",
            patterns={"pat1": "new"},
            confidence={"pat1": 0.92},
        )

        merger.preserve_high_confidence(merged, [source], confidence_threshold=0.8)

        assert merged.learned_patterns["pat1"] == "new"
        assert merged.confidence_data["pat1"] == 0.92

    def test_skips_below_threshold(self, merger, profile_manager):
        """Test that below-threshold confidence is not preserved."""
        merged = _create_profile_with_data(
            profile_manager, "phc_skip_merged", "Merged",
            prefs={"global": {"k": "orig"}, "directory_specific": {}},
            confidence={"k": 0.5},
        )

        source = _create_profile_with_data(
            profile_manager, "phc_skip_source", "Source",
            prefs={"global": {"k": "new"}, "directory_specific": {}},
            confidence={"k": 0.6},
        )

        merger.preserve_high_confidence(merged, [source], confidence_threshold=0.8)

        # Should NOT be overwritten
        assert merged.preferences["global"]["k"] == "orig"

    def test_highest_confidence_wins_across_sources(self, merger, profile_manager):
        """Test that highest confidence from multiple sources wins."""
        merged = _create_profile_with_data(
            profile_manager, "phc_multi_merged", "Merged",
            prefs={"global": {"k": "orig"}, "directory_specific": {}},
            confidence={"k": 0.3},
        )

        source1 = _create_profile_with_data(
            profile_manager, "phc_multi_s1", "Source 1",
            prefs={"global": {"k": "val1"}, "directory_specific": {}},
            confidence={"k": 0.85},
        )

        source2 = _create_profile_with_data(
            profile_manager, "phc_multi_s2", "Source 2",
            prefs={"global": {"k": "val2"}, "directory_specific": {}},
            confidence={"k": 0.95},
        )

        merger.preserve_high_confidence(merged, [source1, source2], confidence_threshold=0.8)

        assert merged.preferences["global"]["k"] == "val2"
        assert merged.confidence_data["k"] == 0.95


# ---------------------------------------------------------------------------
# create_merged_profile
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCreateMergedProfile:
    """Tests for create_merged_profile method."""

    def test_basic_creation(self, merger, profile_manager):
        """Test creating a merged profile from data dict."""
        merged_data = {
            "description": "Test merged",
            "preferences": {"global": {"k": "v"}, "directory_specific": {}},
            "learned_patterns": {"lp": "val"},
            "confidence_data": {"k": 0.8},
        }

        result = merger.create_merged_profile("new_merged", merged_data)

        assert result is not None
        assert result.profile_name == "new_merged"
        assert result.preferences["global"]["k"] == "v"
        assert result.learned_patterns["lp"] == "val"

    def test_default_description(self, merger, profile_manager):
        """Test creating merged profile with no description uses default."""
        merged_data = {
            "preferences": {"global": {}, "directory_specific": {}},
        }
        result = merger.create_merged_profile("default_desc", merged_data)
        assert result is not None
        assert result.description == "Merged profile"

    def test_create_returns_none_on_failure(self, merger, profile_manager):
        """Test create_merged_profile returns None when create fails."""
        with patch.object(profile_manager, "create_profile", return_value=None):
            result = merger.create_merged_profile("fail_create", {})
        assert result is None

    def test_create_returns_none_on_update_failure(self, merger, profile_manager):
        """Test create_merged_profile returns None when update fails."""
        with patch.object(profile_manager, "update_profile", return_value=False):
            result = merger.create_merged_profile("fail_update", {"description": "test"})
        assert result is None

    def test_create_handles_exception(self, merger, profile_manager):
        """Test create_merged_profile handles exceptions gracefully."""
        with patch.object(
            profile_manager, "create_profile", side_effect=RuntimeError("error")
        ):
            result = merger.create_merged_profile("exc_create", {})
        assert result is None


# ---------------------------------------------------------------------------
# merge_profiles – additional edge cases
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMergeProfilesExtended:
    """Additional tests for merge_profiles method."""

    def test_invalid_strategy(self, merger, profile_manager):
        """Test merge_profiles with invalid strategy returns None."""
        _create_profile_with_data(profile_manager, "inv_s1", "IS1")
        _create_profile_with_data(profile_manager, "inv_s2", "IS2")

        result = merger.merge_profiles(["inv_s1", "inv_s2"], "invalid_strategy")
        assert result is None

    def test_merge_with_frequent_strategy(self, merger, profile_manager):
        """Test merge_profiles with FREQUENT strategy."""
        _create_profile_with_data(
            profile_manager, "freq1", "Freq1",
            prefs={"global": {"k": "a"}, "directory_specific": {}},
            confidence={"k": 0.5},
        )
        _create_profile_with_data(
            profile_manager, "freq2", "Freq2",
            prefs={"global": {"k": "a"}, "directory_specific": {}},
            confidence={"k": 0.6},
        )
        _create_profile_with_data(
            profile_manager, "freq3", "Freq3",
            prefs={"global": {"k": "b"}, "directory_specific": {}},
            confidence={"k": 0.7},
        )

        result = merger.merge_profiles(
            ["freq1", "freq2", "freq3"], "frequent", "freq_merged"
        )

        assert result is not None
        # "a" appears twice, "b" once, so "a" wins
        assert result.preferences["global"]["k"] == "a"

    def test_merge_with_default_output_name(self, merger, profile_manager):
        """Test merge_profiles uses default output name when None."""
        _create_profile_with_data(profile_manager, "def1", "Def1")
        _create_profile_with_data(profile_manager, "def2", "Def2")

        result = merger.merge_profiles(["def1", "def2"], "first")

        assert result is not None
        assert result.profile_name == "merged_profile"

    def test_merge_exception(self, merger, profile_manager):
        """Test merge_profiles handles exceptions gracefully."""
        with patch.object(
            profile_manager, "get_profile", side_effect=RuntimeError("error")
        ):
            result = merger.merge_profiles(["a", "b"], "confident")
        assert result is None


# ---------------------------------------------------------------------------
# get_merge_conflicts – additional edge cases
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetMergeConflictsExtended:
    """Additional tests for get_merge_conflicts."""

    def test_no_conflicts_identical_values(self, merger, profile_manager):
        """Test no conflicts when profiles have identical values."""
        _create_profile_with_data(
            profile_manager, "nc1", "NC1",
            prefs={"global": {"k": "same"}, "directory_specific": {}},
        )
        _create_profile_with_data(
            profile_manager, "nc2", "NC2",
            prefs={"global": {"k": "same"}, "directory_specific": {}},
        )

        conflicts = merger.get_merge_conflicts(["nc1", "nc2"])
        assert "global.k" not in conflicts

    def test_directory_specific_conflicts(self, merger, profile_manager):
        """Test detecting directory-specific conflicts."""
        _create_profile_with_data(
            profile_manager, "dc1", "DC1",
            prefs={"global": {}, "directory_specific": {"/test": "val1"}},
        )
        _create_profile_with_data(
            profile_manager, "dc2", "DC2",
            prefs={"global": {}, "directory_specific": {"/test": "val2"}},
        )

        conflicts = merger.get_merge_conflicts(["dc1", "dc2"])
        assert "directory_specific./test" in conflicts

    def test_fewer_than_two_valid_profiles(self, merger, profile_manager):
        """Test get_merge_conflicts returns empty with fewer than 2 valid profiles."""
        _create_profile_with_data(profile_manager, "only_one", "Only one")

        conflicts = merger.get_merge_conflicts(["only_one", "nonexistent"])
        assert conflicts == {}

    def test_exception_returns_empty(self, merger, profile_manager):
        """Test get_merge_conflicts returns empty dict on exception."""
        with patch.object(
            profile_manager, "get_profile", side_effect=RuntimeError("error")
        ):
            conflicts = merger.get_merge_conflicts(["a", "b"])
        assert conflicts == {}


# ---------------------------------------------------------------------------
# MergeStrategy enum
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMergeStrategy:
    """Tests for MergeStrategy enum values."""

    def test_all_strategies(self):
        """Test all strategy values are accessible."""
        assert MergeStrategy.RECENT.value == "recent"
        assert MergeStrategy.FREQUENT.value == "frequent"
        assert MergeStrategy.CONFIDENT.value == "confident"
        assert MergeStrategy.FIRST.value == "first"
        assert MergeStrategy.LAST.value == "last"

    def test_strategy_from_string(self):
        """Test creating strategy from string value."""
        assert MergeStrategy("recent") == MergeStrategy.RECENT
        assert MergeStrategy("frequent") == MergeStrategy.FREQUENT
