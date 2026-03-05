"""Coverage tests for plugins.marketplace.models module."""

from __future__ import annotations

import pytest

from file_organizer.plugins.marketplace.errors import MarketplaceSchemaError
from file_organizer.plugins.marketplace.models import (
    InstalledPlugin,
    PluginPackage,
    PluginReview,
    _parse_str_list,
    compute_sha256,
    utc_now_iso,
)

pytestmark = pytest.mark.unit

_VALID_SHA = "a" * 64


def _pkg_dict(**overrides) -> dict:
    base = {
        "name": "demo",
        "version": "1.0.0",
        "author": "tester",
        "description": "desc",
        "download_url": "https://example.com/demo.zip",
        "checksum_sha256": _VALID_SHA,
        "size_bytes": 1024,
    }
    base.update(overrides)
    return base


class TestUtcNowIso:
    def test_returns_z_suffix(self):
        result = utc_now_iso()
        assert result.endswith("Z")


class TestParseStrList:
    def test_none_returns_empty_tuple(self):
        assert _parse_str_list(None, field_name="tags") == ()

    def test_valid_list(self):
        result = _parse_str_list(["a", "b"], field_name="tags")
        assert result == ("a", "b")

    def test_strips_empty_strings(self):
        result = _parse_str_list(["a", "  ", "b"], field_name="tags")
        assert result == ("a", "b")

    def test_non_list_raises(self):
        with pytest.raises(MarketplaceSchemaError, match="must be a list"):
            _parse_str_list("not-a-list", field_name="tags")

    def test_non_string_item_raises(self):
        with pytest.raises(MarketplaceSchemaError, match="only strings"):
            _parse_str_list([1, 2], field_name="tags")


class TestComputeSha256:
    def test_compute(self, tmp_path):
        f = tmp_path / "data.bin"
        f.write_bytes(b"hello")
        result = compute_sha256(f)
        assert len(result) == 64


class TestPluginPackageFromDict:
    def test_valid_minimal(self):
        pkg = PluginPackage.from_dict(_pkg_dict())
        assert pkg.name == "demo"
        assert pkg.version == "1.0.0"

    def test_missing_required_raises(self):
        d = _pkg_dict()
        del d["name"]
        with pytest.raises(MarketplaceSchemaError, match="missing required"):
            PluginPackage.from_dict(d)

    def test_empty_values_raises(self):
        with pytest.raises(MarketplaceSchemaError, match="empty required"):
            PluginPackage.from_dict(_pkg_dict(author="  "))

    def test_invalid_checksum_length(self):
        with pytest.raises(MarketplaceSchemaError, match="64-character"):
            PluginPackage.from_dict(_pkg_dict(checksum_sha256="short"))

    def test_invalid_size_bytes_type(self):
        with pytest.raises(MarketplaceSchemaError, match="size_bytes"):
            PluginPackage.from_dict(_pkg_dict(size_bytes="not-int"))

    def test_negative_size_bytes(self):
        with pytest.raises(MarketplaceSchemaError, match="positive"):
            PluginPackage.from_dict(_pkg_dict(size_bytes=-1))

    def test_rating_out_of_range(self):
        with pytest.raises(MarketplaceSchemaError, match="between 0.0"):
            PluginPackage.from_dict(_pkg_dict(rating=6.0))

    def test_negative_downloads(self):
        with pytest.raises(MarketplaceSchemaError, match="cannot be negative"):
            PluginPackage.from_dict(_pkg_dict(downloads=-1))

    def test_invalid_rating_type(self):
        with pytest.raises(MarketplaceSchemaError, match="rating must be numeric"):
            PluginPackage.from_dict(_pkg_dict(rating="bad"))

    def test_invalid_downloads_type(self):
        with pytest.raises(MarketplaceSchemaError, match="must be integers"):
            PluginPackage.from_dict(_pkg_dict(downloads="bad"))

    def test_dependencies_parsed(self):
        pkg = PluginPackage.from_dict(_pkg_dict(dependencies=["dep-a", "dep-b"]))
        assert pkg.dependencies == ("dep-a", "dep-b")

    def test_max_organizer_version(self):
        pkg = PluginPackage.from_dict(_pkg_dict(max_organizer_version="3.0.0"))
        assert pkg.max_organizer_version == "3.0.0"

    def test_empty_max_organizer_version(self):
        pkg = PluginPackage.from_dict(_pkg_dict(max_organizer_version=""))
        assert pkg.max_organizer_version is None

    def test_homepage_parsed(self):
        pkg = PluginPackage.from_dict(_pkg_dict(homepage="https://example.com"))
        assert pkg.homepage == "https://example.com"

    def test_empty_homepage(self):
        pkg = PluginPackage.from_dict(_pkg_dict(homepage=""))
        assert pkg.homepage is None


class TestPluginPackageToDict:
    def test_roundtrip(self):
        pkg = PluginPackage.from_dict(_pkg_dict())
        d = pkg.to_dict()
        assert d["name"] == "demo"
        assert d["version"] == "1.0.0"
        assert isinstance(d["dependencies"], list)


class TestInstalledPluginFromDict:
    def test_valid(self):
        ip = InstalledPlugin.from_dict(
            {
                "name": "demo",
                "version": "1.0.0",
                "source_url": "https://example.com",
                "installed_at": "2024-01-01T00:00:00Z",
            }
        )
        assert ip.name == "demo"

    def test_missing_fields_raises(self):
        with pytest.raises(MarketplaceSchemaError, match="missing required"):
            InstalledPlugin.from_dict({"name": "demo", "version": "1.0.0"})

    def test_empty_installed_at_uses_default(self):
        ip = InstalledPlugin.from_dict(
            {
                "name": "demo",
                "version": "1.0.0",
                "source_url": "https://example.com",
                "installed_at": "",
            }
        )
        assert ip.installed_at.endswith("Z")


class TestInstalledPluginToDict:
    def test_roundtrip(self):
        ip = InstalledPlugin(name="demo", version="1.0.0", source_url="https://example.com")
        d = ip.to_dict()
        assert d["name"] == "demo"


class TestPluginReviewValidation:
    def test_valid_review(self):
        r = PluginReview(
            plugin_name="demo",
            user_id="u1",
            rating=3,
            title="OK",
            content="Works",
        )
        assert r.rating == 3

    def test_empty_plugin_name_raises(self):
        with pytest.raises(MarketplaceSchemaError, match="plugin_name"):
            PluginReview(plugin_name="  ", user_id="u1", rating=3, title="T", content="C")

    def test_empty_user_id_raises(self):
        with pytest.raises(MarketplaceSchemaError, match="user_id"):
            PluginReview(plugin_name="demo", user_id="  ", rating=3, title="T", content="C")

    def test_rating_too_low_raises(self):
        with pytest.raises(MarketplaceSchemaError, match="between 1 and 5"):
            PluginReview(plugin_name="demo", user_id="u1", rating=0, title="T", content="C")

    def test_rating_too_high_raises(self):
        with pytest.raises(MarketplaceSchemaError, match="between 1 and 5"):
            PluginReview(plugin_name="demo", user_id="u1", rating=6, title="T", content="C")

    def test_empty_title_raises(self):
        with pytest.raises(MarketplaceSchemaError, match="title"):
            PluginReview(plugin_name="demo", user_id="u1", rating=3, title="  ", content="C")

    def test_negative_helpful_count_raises(self):
        with pytest.raises(MarketplaceSchemaError, match="helpful_count"):
            PluginReview(
                plugin_name="demo",
                user_id="u1",
                rating=3,
                title="T",
                content="C",
                helpful_count=-1,
            )


class TestPluginReviewFromDict:
    def test_valid(self):
        d = {
            "plugin_name": "demo",
            "user_id": "u1",
            "rating": 4,
            "title": "Good",
            "content": "Works",
        }
        r = PluginReview.from_dict(d)
        assert r.plugin_name == "demo"

    def test_invalid_rating_type_raises(self):
        d = {
            "plugin_name": "demo",
            "user_id": "u1",
            "rating": "bad",
            "title": "T",
            "content": "C",
        }
        with pytest.raises(MarketplaceSchemaError, match="must be integers"):
            PluginReview.from_dict(d)


class TestPluginReviewToDict:
    def test_roundtrip(self):
        r = PluginReview(
            plugin_name="demo",
            user_id="u1",
            rating=4,
            title="Good",
            content="Works",
        )
        d = r.to_dict()
        assert d["plugin_name"] == "demo"
        assert d["rating"] == 4
