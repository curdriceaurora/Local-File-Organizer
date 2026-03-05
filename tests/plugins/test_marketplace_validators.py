"""Tests for marketplace validators: name/version normalization, version_sort_key."""

from __future__ import annotations

import pytest

from file_organizer.plugins.marketplace.validators import (
    normalize_plugin_name,
    normalize_plugin_version,
    version_sort_key,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# normalize_plugin_name
# ---------------------------------------------------------------------------


class TestNormalizePluginName:
    """Tests for normalize_plugin_name validation and normalization."""

    @pytest.mark.parametrize(
        "name",
        [
            "my-plugin",
            "MyPlugin",
            "plugin_v2",
            "a",
            "A123",
            "plugin.name",
            "plugin-name-with-dashes",
            "0numstart",
        ],
    )
    def test_valid_names(self, name: str) -> None:
        assert normalize_plugin_name(name) == name

    def test_strips_whitespace(self) -> None:
        assert normalize_plugin_name("  my-plugin  ") == "my-plugin"

    @pytest.mark.parametrize(
        "name",
        [
            "",
            " ",
            "-starts-with-dash",
            ".starts-with-dot",
            "_starts-with-underscore",
            "has space",
            "has/slash",
            "has@at",
        ],
    )
    def test_invalid_names(self, name: str) -> None:
        with pytest.raises(ValueError, match="Invalid plugin name"):
            normalize_plugin_name(name)

    def test_name_too_long(self) -> None:
        """Name pattern allows max 128 chars total (first char + 0..127)."""
        long_name = "A" + "b" * 127  # Exactly 128 chars — valid
        assert normalize_plugin_name(long_name) == long_name

        too_long = "A" + "b" * 128  # 129 chars — exceeds pattern
        with pytest.raises(ValueError, match="Invalid plugin name"):
            normalize_plugin_name(too_long)


# ---------------------------------------------------------------------------
# normalize_plugin_version
# ---------------------------------------------------------------------------


class TestNormalizePluginVersion:
    """Tests for normalize_plugin_version validation and normalization."""

    @pytest.mark.parametrize(
        "version",
        [
            "1.0.0",
            "2.1.3-beta",
            "0.0.1",
            "1.0.0+build123",
            "v1.2.3",
            "1",
        ],
    )
    def test_valid_versions(self, version: str) -> None:
        assert normalize_plugin_version(version) == version

    def test_strips_whitespace(self) -> None:
        assert normalize_plugin_version("  1.0.0  ") == "1.0.0"

    @pytest.mark.parametrize(
        "version",
        [
            "",
            " ",
            "-1.0",
            ".1.0",
            "+build",
        ],
    )
    def test_invalid_versions(self, version: str) -> None:
        with pytest.raises(ValueError, match="Invalid plugin version"):
            normalize_plugin_version(version)

    def test_double_dot_rejected(self) -> None:
        """Versions with '..' are explicitly rejected for path traversal safety."""
        with pytest.raises(ValueError, match="Invalid plugin version"):
            normalize_plugin_version("1..0")

    def test_version_too_long(self) -> None:
        """Version pattern allows max 64 chars total."""
        long_ver = "1" + "0" * 63  # 64 chars — valid
        assert normalize_plugin_version(long_ver) == long_ver

        too_long = "1" + "0" * 64  # 65 chars — exceeds pattern
        with pytest.raises(ValueError, match="Invalid plugin version"):
            normalize_plugin_version(too_long)


# ---------------------------------------------------------------------------
# version_sort_key
# ---------------------------------------------------------------------------


class TestVersionSortKey:
    """Tests for version_sort_key semantic ordering."""

    def test_numeric_parts_sort_numerically(self) -> None:
        key_1 = version_sort_key("1.2.3")
        key_2 = version_sort_key("1.10.3")
        assert key_1 < key_2  # 2 < 10 numerically

    def test_string_parts_sort_lexicographically(self) -> None:
        key_a = version_sort_key("1.0.0-alpha")
        key_b = version_sort_key("1.0.0-beta")
        assert key_a < key_b

    def test_numeric_before_string(self) -> None:
        """Numeric parts get sort type 0, strings get 1; so numeric < string."""
        key_num = version_sort_key("1")
        key_str = version_sort_key("a")
        assert key_num < key_str

    def test_dash_treated_as_dot(self) -> None:
        """Hyphens are converted to dots for splitting."""
        key = version_sort_key("1-2-3")
        assert key == version_sort_key("1.2.3")

    def test_sort_multiple_versions(self) -> None:
        versions = ["2.0.0", "1.10.0", "1.2.0", "1.0.0-alpha", "1.0.0"]
        sorted_versions = sorted(versions, key=version_sort_key)
        # "1.0.0" (3 numeric parts) sorts before "1.0.0-alpha" (4 parts,
        # because "alpha" is a string with sort-type 1 > numeric sort-type 0
        # at a position where "1.0.0" has no part at all).
        assert sorted_versions == [
            "1.0.0",
            "1.0.0-alpha",
            "1.2.0",
            "1.10.0",
            "2.0.0",
        ]

    def test_empty_version(self) -> None:
        """Empty string should produce an empty key tuple."""
        # After split, we get [''], which is a non-digit string
        key = version_sort_key("")
        assert isinstance(key, tuple)

    def test_case_insensitive_sort(self) -> None:
        """String parts should be lowercased for sorting."""
        key_upper = version_sort_key("1.0.0-Beta")
        key_lower = version_sort_key("1.0.0-beta")
        assert key_upper == key_lower
