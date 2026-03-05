"""Coverage tests for plugins.marketplace.repository module."""

from __future__ import annotations

import hashlib
import json

import pytest

from file_organizer.plugins.marketplace.errors import (
    MarketplaceRepositoryError,
    MarketplaceSchemaError,
)
from file_organizer.plugins.marketplace.repository import (
    PluginRepository,
    _to_file_url,
    _url_to_local_path,
)

pytestmark = pytest.mark.unit

_VALID_SHA = "a" * 64


def _index_payload(*packages: dict) -> dict:
    return {"plugins": list(packages)}


def _pkg(name: str = "demo", version: str = "1.0.0", **kw) -> dict:
    defaults = {
        "name": name,
        "version": version,
        "author": "tester",
        "description": "desc",
        "download_url": "demo.zip",
        "checksum_sha256": _VALID_SHA,
        "size_bytes": 1024,
    }
    defaults.update(kw)
    return defaults


class TestHelperFunctions:
    def test_to_file_url(self, tmp_path):
        url = _to_file_url(tmp_path)
        assert url.startswith("file://")

    def test_url_to_local_path_valid(self, tmp_path):
        url = _to_file_url(tmp_path)
        result = _url_to_local_path(url)
        assert result == tmp_path.resolve()

    def test_url_to_local_path_non_file_scheme(self):
        with pytest.raises(MarketplaceRepositoryError, match="Expected file URL"):
            _url_to_local_path("https://example.com/file")

    def test_url_to_local_path_unsupported_host(self):
        with pytest.raises(MarketplaceRepositoryError, match="Unsupported file URL host"):
            _url_to_local_path("file://remotehost/path")


class TestPluginRepositoryInit:
    def test_empty_url_raises(self):
        with pytest.raises(MarketplaceRepositoryError, match="must not be empty"):
            PluginRepository("  ")

    def test_http_url(self):
        repo = PluginRepository("https://example.com/plugins")
        assert repo.repo_url == "https://example.com/plugins"

    def test_local_path_becomes_file_url(self, tmp_path):
        repo = PluginRepository(str(tmp_path))
        assert repo.repo_url.startswith("file://")

    def test_file_url_with_json(self, tmp_path):
        idx = tmp_path / "index.json"
        idx.write_text(json.dumps(_index_payload()))
        repo = PluginRepository(_to_file_url(idx))
        assert repo._base_file_root == tmp_path


class TestPluginRepositoryCache:
    def test_clear_cache(self, tmp_path):
        idx = tmp_path / "index.json"
        idx.write_text(json.dumps(_index_payload(_pkg())))
        repo = PluginRepository(_to_file_url(idx))
        repo.all_plugins()
        assert repo.is_cache_fresh()
        repo.clear_cache()
        assert not repo.is_cache_fresh()

    def test_cache_expiry(self, tmp_path):
        idx = tmp_path / "index.json"
        idx.write_text(json.dumps(_index_payload(_pkg())))
        repo = PluginRepository(_to_file_url(idx), cache_ttl_seconds=0)
        repo.all_plugins()
        # Cache with 0 TTL should already be expired
        assert not repo.is_cache_fresh()


class TestPluginRepositoryListPlugins:
    def test_list_plugins_pagination(self, tmp_path):
        idx = tmp_path / "index.json"
        idx.write_text(json.dumps(_index_payload(_pkg("a"), _pkg("b"), _pkg("c"))))
        repo = PluginRepository(_to_file_url(idx))

        page1 = repo.list_plugins(page=1, per_page=2)
        assert len(page1) == 2
        page2 = repo.list_plugins(page=2, per_page=2)
        assert len(page2) == 1

    def test_list_plugins_invalid_page(self, tmp_path):
        idx = tmp_path / "index.json"
        idx.write_text(json.dumps(_index_payload()))
        repo = PluginRepository(_to_file_url(idx))
        with pytest.raises(MarketplaceRepositoryError, match="must be >= 1"):
            repo.list_plugins(page=0)


class TestPluginRepositorySearch:
    def test_search_by_query(self, tmp_path):
        idx = tmp_path / "index.json"
        idx.write_text(
            json.dumps(
                _index_payload(
                    _pkg("image-sort", description="sorts images"),
                    _pkg("text-proc", description="processes text"),
                )
            )
        )
        repo = PluginRepository(_to_file_url(idx))
        results = repo.search_plugins("image")
        assert len(results) == 1
        assert results[0].name == "image-sort"

    def test_search_by_tags(self, tmp_path):
        idx = tmp_path / "index.json"
        idx.write_text(
            json.dumps(
                _index_payload(
                    _pkg("a", tags=["image"]),
                    _pkg("b", tags=["text"]),
                )
            )
        )
        repo = PluginRepository(_to_file_url(idx))
        results = repo.search_plugins("", tags=["image"])
        assert len(results) == 1

    def test_search_by_category(self, tmp_path):
        idx = tmp_path / "index.json"
        idx.write_text(
            json.dumps(
                _index_payload(
                    _pkg("a", category="tools"),
                    _pkg("b", category="analytics"),
                )
            )
        )
        repo = PluginRepository(_to_file_url(idx))
        results = repo.search_plugins("", category="tools")
        assert len(results) == 1


class TestPluginRepositoryGetPlugin:
    def test_get_plugin_latest(self, tmp_path):
        idx = tmp_path / "index.json"
        idx.write_text(json.dumps(_index_payload(_pkg("demo", "1.0.0"), _pkg("demo", "2.0.0"))))
        repo = PluginRepository(_to_file_url(idx))
        result = repo.get_plugin("demo")
        assert result.version == "2.0.0"

    def test_get_plugin_specific_version(self, tmp_path):
        idx = tmp_path / "index.json"
        idx.write_text(json.dumps(_index_payload(_pkg("demo", "1.0.0"), _pkg("demo", "2.0.0"))))
        repo = PluginRepository(_to_file_url(idx))
        result = repo.get_plugin("demo", version="1.0.0")
        assert result.version == "1.0.0"

    def test_get_plugin_not_found(self, tmp_path):
        idx = tmp_path / "index.json"
        idx.write_text(json.dumps(_index_payload()))
        repo = PluginRepository(_to_file_url(idx))
        with pytest.raises(MarketplaceRepositoryError, match="not found"):
            repo.get_plugin("nonexistent")

    def test_get_plugin_version_not_found(self, tmp_path):
        idx = tmp_path / "index.json"
        idx.write_text(json.dumps(_index_payload(_pkg("demo", "1.0.0"))))
        repo = PluginRepository(_to_file_url(idx))
        with pytest.raises(MarketplaceRepositoryError, match="version"):
            repo.get_plugin("demo", version="9.9.9")

    def test_get_plugin_empty_name(self, tmp_path):
        idx = tmp_path / "index.json"
        idx.write_text(json.dumps(_index_payload()))
        repo = PluginRepository(_to_file_url(idx))
        with pytest.raises(MarketplaceRepositoryError, match="must not be empty"):
            repo.get_plugin("  ")


class TestPluginRepositoryDownload:
    def test_download_local_file(self, tmp_path):
        artifact = tmp_path / "demo-1.0.0.zip"
        artifact.write_bytes(b"fake-zip-data")

        idx = tmp_path / "index.json"
        idx.write_text(
            json.dumps(_index_payload(_pkg("demo", download_url=_to_file_url(artifact))))
        )
        repo = PluginRepository(_to_file_url(idx))
        dest = tmp_path / "dest"
        result = repo.download_plugin(repo.get_plugin("demo"), dest)
        assert result.exists()

    def test_download_local_missing_artifact(self, tmp_path):
        idx = tmp_path / "index.json"
        missing = tmp_path / "missing.zip"
        idx.write_text(json.dumps(_index_payload(_pkg("demo", download_url=_to_file_url(missing)))))
        repo = PluginRepository(_to_file_url(idx))
        with pytest.raises(MarketplaceRepositoryError, match="not found"):
            repo.download_plugin(repo.get_plugin("demo"), tmp_path / "dest")

    def test_download_unsupported_scheme(self, tmp_path):
        idx = tmp_path / "index.json"
        idx.write_text(
            json.dumps(_index_payload(_pkg("demo", download_url="ftp://example.com/a.zip")))
        )
        repo = PluginRepository(_to_file_url(idx))
        with pytest.raises(MarketplaceRepositoryError, match="network location"):
            repo.download_plugin(repo.get_plugin("demo"), tmp_path / "dest")


class TestPluginRepositoryVerifyChecksum:
    def test_verify_checksum_match(self, tmp_path):
        f = tmp_path / "data.zip"
        f.write_bytes(b"hello")
        expected = hashlib.sha256(b"hello").hexdigest()
        repo = PluginRepository(str(tmp_path))
        assert repo.verify_checksum(f, expected) is True

    def test_verify_checksum_mismatch(self, tmp_path):
        f = tmp_path / "data.zip"
        f.write_bytes(b"hello")
        repo = PluginRepository(str(tmp_path))
        assert repo.verify_checksum(f, "b" * 64) is False


class TestPluginRepositoryLoadIndex:
    def test_missing_local_index_returns_empty(self, tmp_path):
        repo = PluginRepository(str(tmp_path))
        result = repo.all_plugins()
        assert result == []

    def test_invalid_json_raises(self, tmp_path):
        idx = tmp_path / "index.json"
        idx.write_text("{bad json")
        repo = PluginRepository(_to_file_url(idx))
        with pytest.raises(MarketplaceRepositoryError, match="Failed to read"):
            repo.all_plugins()

    def test_non_dict_root_raises(self, tmp_path):
        idx = tmp_path / "index.json"
        idx.write_text(json.dumps([1, 2, 3]))
        repo = PluginRepository(_to_file_url(idx))
        with pytest.raises(MarketplaceSchemaError, match="must be a JSON object"):
            repo.all_plugins()

    def test_non_list_plugins_raises(self, tmp_path):
        idx = tmp_path / "index.json"
        idx.write_text(json.dumps({"plugins": "not-a-list"}))
        repo = PluginRepository(_to_file_url(idx))
        with pytest.raises(MarketplaceSchemaError, match="must be a list"):
            repo.all_plugins()

    def test_non_dict_plugin_entry_raises(self, tmp_path):
        idx = tmp_path / "index.json"
        idx.write_text(json.dumps({"plugins": ["not-a-dict"]}))
        repo = PluginRepository(_to_file_url(idx))
        with pytest.raises(MarketplaceSchemaError, match="must be a JSON object"):
            repo.all_plugins()


class TestPluginRepositoryResolvePackageUrl:
    def test_relative_url_with_file_base(self, tmp_path):
        idx = tmp_path / "index.json"
        idx.write_text(json.dumps(_index_payload(_pkg("demo", download_url="demo.zip"))))
        repo = PluginRepository(_to_file_url(idx))
        url = repo._resolve_package_url("demo.zip")
        assert url.startswith("file://")

    def test_absolute_http_url_passthrough(self, tmp_path):
        idx = tmp_path / "index.json"
        idx.write_text(json.dumps(_index_payload()))
        repo = PluginRepository(_to_file_url(idx))
        url = repo._resolve_package_url("https://example.com/pkg.zip")
        assert url == "https://example.com/pkg.zip"

    def test_netloc_without_scheme_raises(self, tmp_path):
        idx = tmp_path / "index.json"
        idx.write_text(json.dumps(_index_payload()))
        repo = PluginRepository("https://example.com/plugins")
        with pytest.raises(MarketplaceRepositoryError, match="network location"):
            repo._resolve_package_url("//host/path")
