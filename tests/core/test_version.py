"""Tests for version management module.

Covers version parsing, comparison, bumping, and metadata access.
"""

from __future__ import annotations

import pytest

from file_organizer.version import (
    VersionInfo,
    __version__,
    bump_version,
    get_version,
    get_version_info,
    parse_version,
)


@pytest.mark.unit
class TestParseVersion:
    """Tests for parse_version function."""

    def test_parse_simple_version(self) -> None:
        """Parse a simple major.minor.patch version."""
        info = parse_version("2.0.0")
        assert info.major == 2
        assert info.minor == 0
        assert info.patch == 0
        assert info.pre_release is None

    def test_parse_version_with_pre_release(self) -> None:
        """Parse a version with pre-release suffix."""
        info = parse_version("2.0.0-alpha.1")
        assert info.major == 2
        assert info.minor == 0
        assert info.patch == 0
        assert info.pre_release == "alpha.1"

    def test_parse_version_with_single_pre_release(self) -> None:
        """Parse a version with simple pre-release identifier."""
        info = parse_version("1.0.0-beta")
        assert info.pre_release == "beta"

    def test_parse_large_version_numbers(self) -> None:
        """Parse versions with large numbers."""
        info = parse_version("100.200.300")
        assert info.major == 100
        assert info.minor == 200
        assert info.patch == 300

    def test_parse_zero_version(self) -> None:
        """Parse a 0.x.x version."""
        info = parse_version("0.1.0")
        assert info.major == 0
        assert info.minor == 1
        assert info.patch == 0

    def test_parse_version_strips_whitespace(self) -> None:
        """Parse version string with surrounding whitespace."""
        info = parse_version("  1.2.3  ")
        assert info.major == 1
        assert info.minor == 2
        assert info.patch == 3

    def test_parse_invalid_version_raises(self) -> None:
        """Invalid version strings raise ValueError."""
        with pytest.raises(ValueError, match="Invalid version string"):
            parse_version("not.a.version")

    def test_parse_missing_patch_raises(self) -> None:
        """Version missing patch component raises ValueError."""
        with pytest.raises(ValueError, match="Invalid version string"):
            parse_version("1.2")

    def test_parse_empty_string_raises(self) -> None:
        """Empty version string raises ValueError."""
        with pytest.raises(ValueError, match="Invalid version string"):
            parse_version("")

    def test_parse_leading_zeros_raises(self) -> None:
        """Version with leading zeros in numeric parts raises ValueError."""
        with pytest.raises(ValueError, match="Invalid version string"):
            parse_version("01.2.3")

    def test_parse_negative_raises(self) -> None:
        """Negative version numbers raise ValueError."""
        with pytest.raises(ValueError, match="Invalid version string"):
            parse_version("-1.0.0")


@pytest.mark.unit
class TestVersionInfo:
    """Tests for VersionInfo dataclass."""

    def test_str_simple(self) -> None:
        """String representation of simple version."""
        info = VersionInfo(major=2, minor=1, patch=0)
        assert str(info) == "2.1.0"

    def test_str_with_pre_release(self) -> None:
        """String representation with pre-release suffix."""
        info = VersionInfo(major=1, minor=0, patch=0, pre_release="rc.1")
        assert str(info) == "1.0.0-rc.1"

    def test_is_pre_release_true(self) -> None:
        """Pre-release detection when suffix is present."""
        info = VersionInfo(major=1, minor=0, patch=0, pre_release="alpha")
        assert info.is_pre_release is True

    def test_is_pre_release_false(self) -> None:
        """Pre-release detection when no suffix."""
        info = VersionInfo(major=1, minor=0, patch=0)
        assert info.is_pre_release is False

    def test_base_version(self) -> None:
        """Base version strips pre-release suffix."""
        info = VersionInfo(major=2, minor=0, patch=0, pre_release="beta.2")
        assert info.base_version == "2.0.0"

    def test_frozen_dataclass(self) -> None:
        """VersionInfo instances are immutable."""
        info = VersionInfo(major=1, minor=0, patch=0)
        with pytest.raises(AttributeError):
            info.major = 2  # type: ignore[misc]

    def test_equality(self) -> None:
        """VersionInfo instances with same values are equal."""
        a = VersionInfo(major=1, minor=2, patch=3)
        b = VersionInfo(major=1, minor=2, patch=3)
        assert a == b

    def test_inequality(self) -> None:
        """VersionInfo instances with different values are not equal."""
        a = VersionInfo(major=1, minor=2, patch=3)
        b = VersionInfo(major=1, minor=2, patch=4)
        assert a != b


@pytest.mark.unit
class TestVersionComparison:
    """Tests for version comparison operators."""

    def test_less_than_patch(self) -> None:
        """Lower patch version is less than higher."""
        assert VersionInfo(1, 0, 0) < VersionInfo(1, 0, 1)

    def test_less_than_minor(self) -> None:
        """Lower minor version is less than higher."""
        assert VersionInfo(1, 0, 9) < VersionInfo(1, 1, 0)

    def test_less_than_major(self) -> None:
        """Lower major version is less than higher."""
        assert VersionInfo(1, 9, 9) < VersionInfo(2, 0, 0)

    def test_pre_release_less_than_release(self) -> None:
        """Pre-release version is less than the corresponding release."""
        assert VersionInfo(1, 0, 0, "alpha") < VersionInfo(1, 0, 0)

    def test_release_not_less_than_pre_release(self) -> None:
        """Release version is not less than pre-release."""
        assert not (VersionInfo(1, 0, 0) < VersionInfo(1, 0, 0, "alpha"))

    def test_greater_than(self) -> None:
        """Greater-than comparison works."""
        assert VersionInfo(2, 0, 0) > VersionInfo(1, 9, 9)

    def test_less_than_or_equal(self) -> None:
        """Less-than-or-equal comparison works."""
        assert VersionInfo(1, 0, 0) <= VersionInfo(1, 0, 0)
        assert VersionInfo(1, 0, 0) <= VersionInfo(1, 0, 1)

    def test_greater_than_or_equal(self) -> None:
        """Greater-than-or-equal comparison works."""
        assert VersionInfo(1, 0, 0) >= VersionInfo(1, 0, 0)
        assert VersionInfo(1, 0, 1) >= VersionInfo(1, 0, 0)

    def test_comparison_with_non_version_returns_not_implemented(self) -> None:
        """Comparison with non-VersionInfo returns NotImplemented."""
        v = VersionInfo(1, 0, 0)
        assert v.__lt__("1.0.0") is NotImplemented
        assert v.__gt__("1.0.0") is NotImplemented
        assert v.__le__("1.0.0") is NotImplemented
        assert v.__ge__("1.0.0") is NotImplemented


@pytest.mark.unit
class TestBumpVersion:
    """Tests for bump_version function."""

    def test_bump_patch(self) -> None:
        """Bumping patch increments patch number."""
        assert bump_version("1.0.0", "patch") == "1.0.1"

    def test_bump_minor(self) -> None:
        """Bumping minor increments minor and resets patch."""
        assert bump_version("1.2.3", "minor") == "1.3.0"

    def test_bump_major(self) -> None:
        """Bumping major increments major and resets minor and patch."""
        assert bump_version("1.2.3", "major") == "2.0.0"

    def test_bump_pre_release_strips_suffix(self) -> None:
        """Bumping a pre-release version strips the pre-release suffix."""
        assert bump_version("1.0.0-alpha.1", "patch") == "1.0.1"

    def test_bump_invalid_part_raises(self) -> None:
        """Invalid bump part raises ValueError."""
        with pytest.raises(ValueError, match="Invalid version part"):
            bump_version("1.0.0", "invalid")


@pytest.mark.unit
class TestGetVersion:
    """Tests for get_version and get_version_info."""

    def test_get_version_returns_string(self) -> None:
        """get_version returns a non-empty string."""
        version = get_version()
        assert isinstance(version, str)
        assert len(version) > 0

    def test_get_version_matches_module(self) -> None:
        """get_version returns the module __version__."""
        assert get_version() == __version__

    def test_get_version_info_returns_version_info(self) -> None:
        """get_version_info returns a VersionInfo instance."""
        info = get_version_info()
        assert isinstance(info, VersionInfo)

    def test_get_version_info_matches_string(self) -> None:
        """get_version_info string matches get_version."""
        info = get_version_info()
        assert str(info) == get_version()
