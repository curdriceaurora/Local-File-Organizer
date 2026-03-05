"""Coverage tests for plugins.marketplace.metadata module."""

from __future__ import annotations

import json

import pytest

from file_organizer.plugins.marketplace.errors import MarketplaceRepositoryError
from file_organizer.plugins.marketplace.metadata import PluginMetadataStore
from file_organizer.plugins.marketplace.models import PluginPackage

pytestmark = pytest.mark.unit


def _package(name: str = "demo", version: str = "1.0.0", **kwargs) -> PluginPackage:
    defaults = {
        "name": name,
        "version": version,
        "author": "tester",
        "description": "test plugin",
        "downloads": 0,
        "rating": 0.0,
        "tags": [],
        "category": "general",
        "checksum_sha256": "a" * 64,
        "download_url": "https://example.com/plugin.zip",
        "size_bytes": 1024,
    }
    defaults.update(kwargs)
    return PluginPackage.from_dict(defaults)


class TestPluginMetadataStore:
    def test_sync_and_list_all(self, tmp_path):
        db = tmp_path / "meta.json"
        store = PluginMetadataStore(db)
        pkgs = [_package("alpha", "1.0.0"), _package("beta", "2.0.0")]
        store.sync(pkgs)

        result = store.list_all()
        names = [p.name for p in result]
        assert "alpha" in names
        assert "beta" in names

    def test_list_all_empty(self, tmp_path):
        db = tmp_path / "meta.json"
        store = PluginMetadataStore(db)
        result = store.list_all()
        assert result == []

    def test_list_all_invalid_plugins_field(self, tmp_path):
        db = tmp_path / "meta.json"
        db.write_text(json.dumps({"plugins": "not-a-list"}))
        store = PluginMetadataStore(db)

        with pytest.raises(MarketplaceRepositoryError, match="invalid"):
            store.list_all()

    def test_list_all_skips_non_dict_items(self, tmp_path):
        db = tmp_path / "meta.json"
        payload = {
            "plugins": [
                {
                    "name": "good",
                    "version": "1.0",
                    "author": "a",
                    "description": "d",
                    "downloads": 0,
                    "rating": 0,
                    "tags": [],
                    "category": "general",
                    "checksum_sha256": "b" * 64,
                    "download_url": "https://example.com/p.zip",
                    "size_bytes": 512,
                },
                "not-a-dict",
                42,
            ]
        }
        db.write_text(json.dumps(payload))
        store = PluginMetadataStore(db)
        result = store.list_all()
        assert len(result) == 1

    def test_get_plugin_found(self, tmp_path):
        db = tmp_path / "meta.json"
        store = PluginMetadataStore(db)
        store.sync([_package("demo", "1.0.0"), _package("demo", "2.0.0")])

        result = store.get_plugin("demo")
        assert result is not None
        assert result.version == "2.0.0"

    def test_get_plugin_not_found(self, tmp_path):
        db = tmp_path / "meta.json"
        store = PluginMetadataStore(db)
        store.sync([_package("other")])
        assert store.get_plugin("missing") is None

    def test_get_plugin_empty_name(self, tmp_path):
        db = tmp_path / "meta.json"
        store = PluginMetadataStore(db)
        assert store.get_plugin("  ") is None

    def test_search_by_query(self, tmp_path):
        db = tmp_path / "meta.json"
        store = PluginMetadataStore(db)
        store.sync(
            [
                _package("image-sorter", description="sorts images"),
                _package("text-analyzer", description="analyzes text"),
            ]
        )

        result = store.search("image")
        assert len(result) == 1
        assert result[0].name == "image-sorter"

    def test_search_by_tags(self, tmp_path):
        db = tmp_path / "meta.json"
        store = PluginMetadataStore(db)
        store.sync(
            [
                _package("a", tags=["image", "sort"]),
                _package("b", tags=["text"]),
            ]
        )

        result = store.search("", tags=["image"])
        assert len(result) == 1

    def test_search_by_category(self, tmp_path):
        db = tmp_path / "meta.json"
        store = PluginMetadataStore(db)
        store.sync(
            [
                _package("a", category="tools"),
                _package("b", category="analytics"),
            ]
        )

        result = store.search("", category="tools")
        assert len(result) == 1
        assert result[0].name == "a"

    def test_read_payload_invalid_json(self, tmp_path):
        db = tmp_path / "meta.json"
        db.write_text("{bad json")
        store = PluginMetadataStore(db)

        with pytest.raises(MarketplaceRepositoryError, match="Failed to read"):
            store._read_payload()

    def test_read_payload_non_dict(self, tmp_path):
        db = tmp_path / "meta.json"
        db.write_text(json.dumps([1, 2, 3]))
        store = PluginMetadataStore(db)

        with pytest.raises(MarketplaceRepositoryError, match="must be a JSON object"):
            store._read_payload()
