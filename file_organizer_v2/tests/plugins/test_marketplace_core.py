"""Tests for marketplace repository, installer, and review managers."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from file_organizer.plugins.marketplace import (
    MarketplaceInstallError,
    MarketplaceRepositoryError,
    MarketplaceSchemaError,
    MarketplaceService,
    PluginInstaller,
    PluginMetadataStore,
    PluginPackage,
    PluginRepository,
    PluginReview,
    ReviewManager,
    compute_sha256,
)

pytestmark = pytest.mark.ci


def _write_plugin_archive(
    repo_dir: Path,
    *,
    name: str,
    version: str,
    dependency: str | None = None,
) -> dict[str, object]:
    archive_name = f"{name}-{version}.zip"
    archive_path = repo_dir / archive_name
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(
            "plugin.py",
            "\n".join(
                [
                    "from file_organizer.plugins import Plugin, PluginMetadata",
                    "",
                    "class ExamplePlugin(Plugin):",
                    "    def get_metadata(self):",
                    f"        return PluginMetadata(name='{name}', version='{version}', author='tests', description='plugin')",
                    "    def on_load(self): pass",
                    "    def on_enable(self): pass",
                    "    def on_disable(self): pass",
                    "    def on_unload(self): pass",
                ]
            ),
        )
    metadata: dict[str, object] = {
        "name": name,
        "version": version,
        "author": "tests",
        "description": f"{name} plugin",
        "homepage": "https://example.invalid",
        "download_url": archive_name,
        "checksum_sha256": compute_sha256(archive_path),
        "size_bytes": archive_path.stat().st_size,
        "dependencies": [dependency] if dependency else [],
        "tags": ["utility"],
        "category": "utility",
        "license": "MIT",
        "min_organizer_version": "2.0.0",
        "max_organizer_version": None,
        "downloads": 0,
        "rating": 0.0,
        "reviews_count": 0,
    }
    return metadata


def _write_index(repo_dir: Path, plugins: list[dict[str, object]]) -> None:
    payload = {"plugins": plugins}
    (repo_dir / "index.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_repository_listing_search_and_get(tmp_path: Path) -> None:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    alpha = _write_plugin_archive(repo_dir, name="alpha", version="1.0.0")
    beta = _write_plugin_archive(repo_dir, name="beta", version="1.2.0")
    _write_index(repo_dir, [alpha, beta])

    repository = PluginRepository(str(repo_dir))
    listed = repository.list_plugins(page=1, per_page=10)
    assert len(listed) == 2
    assert {item.name for item in listed} == {"alpha", "beta"}

    searched = repository.search_plugins("bet")
    assert len(searched) == 1
    assert searched[0].name == "beta"

    plugin = repository.get_plugin("alpha")
    assert plugin.version == "1.0.0"


def test_installer_install_dependency_and_update(tmp_path: Path) -> None:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    dep = _write_plugin_archive(repo_dir, name="dep", version="1.0.0")
    alpha_v1 = _write_plugin_archive(repo_dir, name="alpha", version="1.0.0", dependency="dep")
    alpha_v2 = _write_plugin_archive(repo_dir, name="alpha", version="1.1.0", dependency="dep")
    _write_index(repo_dir, [dep, alpha_v1, alpha_v2])

    repository = PluginRepository(str(repo_dir))
    installer = PluginInstaller(tmp_path / "plugins", repository)

    installed_alpha = installer.install("alpha", version="1.0.0")
    assert installed_alpha.version == "1.0.0"
    assert (tmp_path / "plugins" / "alpha" / "plugin.py").exists()
    assert (tmp_path / "plugins" / "dep" / "plugin.py").exists()

    updates = installer.check_updates()
    assert "alpha" in updates

    updated_alpha = installer.update("alpha")
    assert updated_alpha is not None
    assert updated_alpha.version == "1.1.0"

    installer.uninstall("alpha")
    assert not (tmp_path / "plugins" / "alpha").exists()


def test_installer_rejects_zip_slip_archive(tmp_path: Path) -> None:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    archive_path = repo_dir / "evil-1.0.0.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("../outside.txt", "malicious")
    plugin_metadata = {
        "name": "evil",
        "version": "1.0.0",
        "author": "tests",
        "description": "evil",
        "download_url": archive_path.name,
        "checksum_sha256": compute_sha256(archive_path),
        "size_bytes": archive_path.stat().st_size,
        "dependencies": [],
        "tags": [],
        "category": "utility",
        "license": "MIT",
        "min_organizer_version": "2.0.0",
        "max_organizer_version": None,
        "downloads": 0,
        "rating": 0.0,
        "reviews_count": 0,
    }
    _write_index(repo_dir, [plugin_metadata])

    repository = PluginRepository(str(repo_dir))
    installer = PluginInstaller(tmp_path / "plugins", repository)
    with pytest.raises(MarketplaceInstallError):
        installer.install("evil")
    assert not (tmp_path / "outside.txt").exists()


def test_installer_detects_circular_dependencies(tmp_path: Path) -> None:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    alpha = _write_plugin_archive(repo_dir, name="alpha", version="1.0.0", dependency="beta")
    beta = _write_plugin_archive(repo_dir, name="beta", version="1.0.0", dependency="alpha")
    _write_index(repo_dir, [alpha, beta])

    repository = PluginRepository(str(repo_dir))
    installer = PluginInstaller(tmp_path / "plugins", repository)
    with pytest.raises(MarketplaceInstallError, match="Circular plugin dependency"):
        installer.install("alpha")


def test_installer_uninstall_rejects_invalid_plugin_name(tmp_path: Path) -> None:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    alpha = _write_plugin_archive(repo_dir, name="alpha", version="1.0.0")
    _write_index(repo_dir, [alpha])

    repository = PluginRepository(str(repo_dir))
    installer = PluginInstaller(tmp_path / "plugins", repository)
    installer.install("alpha")

    with pytest.raises(MarketplaceInstallError, match="Invalid plugin name"):
        installer.uninstall("../alpha")


def test_repository_file_url_handles_percent_encoded_paths(tmp_path: Path) -> None:
    repo_dir = tmp_path / "repo with spaces"
    repo_dir.mkdir()
    alpha = _write_plugin_archive(repo_dir, name="alpha", version="1.0.0")
    _write_index(repo_dir, [alpha])

    repository = PluginRepository(repo_dir.as_uri())
    package = repository.get_plugin("alpha")
    downloaded = repository.download_plugin(package, tmp_path / "downloads")
    assert downloaded.exists()


def test_repository_rejects_scheme_relative_download_url(tmp_path: Path) -> None:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    alpha = _write_plugin_archive(repo_dir, name="alpha", version="1.0.0")
    alpha["download_url"] = "//attacker.example/alpha-1.0.0.zip"
    _write_index(repo_dir, [alpha])

    repository = PluginRepository(str(repo_dir))
    package = repository.get_plugin("alpha")
    with pytest.raises(MarketplaceRepositoryError, match="network location"):
        repository.download_plugin(package, tmp_path / "downloads")


def test_metadata_store_uses_version_sorting(tmp_path: Path) -> None:
    store = PluginMetadataStore(tmp_path / "metadata.json")
    package_v2 = PluginPackage.from_dict(
        {
            "name": "alpha",
            "version": "1.2.0",
            "author": "tests",
            "description": "alpha",
            "download_url": "alpha-1.2.0.zip",
            "checksum_sha256": "0" * 64,
            "size_bytes": 10,
            "dependencies": [],
            "tags": [],
            "category": "utility",
            "license": "MIT",
            "min_organizer_version": "2.0.0",
            "max_organizer_version": None,
            "downloads": 0,
            "rating": 0.0,
            "reviews_count": 0,
        }
    )
    package_v10 = PluginPackage.from_dict(
        {
            "name": "alpha",
            "version": "1.10.0",
            "author": "tests",
            "description": "alpha",
            "download_url": "alpha-1.10.0.zip",
            "checksum_sha256": "1" * 64,
            "size_bytes": 10,
            "dependencies": [],
            "tags": [],
            "category": "utility",
            "license": "MIT",
            "min_organizer_version": "2.0.0",
            "max_organizer_version": None,
            "downloads": 0,
            "rating": 0.0,
            "reviews_count": 0,
        }
    )
    store.sync([package_v2, package_v10])
    newest = store.get_plugin("alpha")
    assert newest is not None
    assert newest.version == "1.10.0"


def test_service_list_plugins_avoids_redundant_metadata_writes(tmp_path: Path) -> None:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    alpha = _write_plugin_archive(repo_dir, name="alpha", version="1.0.0")
    _write_index(repo_dir, [alpha])

    service = MarketplaceService(
        home_dir=tmp_path / "marketplace-home",
        repo_url=str(repo_dir),
    )
    first_page, first_total = service.list_plugins()
    assert first_total == 1
    assert first_page[0].name == "alpha"

    metadata_path = service.home_dir / "metadata.json"
    before_mtime = metadata_path.stat().st_mtime_ns
    second_page, second_total = service.list_plugins()
    assert second_total == 1
    assert second_page[0].name == "alpha"
    after_mtime = metadata_path.stat().st_mtime_ns
    assert after_mtime == before_mtime


def test_plugin_package_rejects_unsafe_name_and_version() -> None:
    with pytest.raises(MarketplaceSchemaError, match="Invalid plugin name"):
        PluginPackage.from_dict(
            {
                "name": "../alpha",
                "version": "1.0.0",
                "author": "tests",
                "description": "alpha",
                "download_url": "alpha.zip",
                "checksum_sha256": "0" * 64,
                "size_bytes": 10,
                "dependencies": [],
                "tags": [],
                "category": "utility",
                "license": "MIT",
                "min_organizer_version": "2.0.0",
                "max_organizer_version": None,
                "downloads": 0,
                "rating": 0.0,
                "reviews_count": 0,
            }
        )

    with pytest.raises(MarketplaceSchemaError, match="Invalid plugin version"):
        PluginPackage.from_dict(
            {
                "name": "alpha",
                "version": "../1.0.0",
                "author": "tests",
                "description": "alpha",
                "download_url": "alpha.zip",
                "checksum_sha256": "0" * 64,
                "size_bytes": 10,
                "dependencies": [],
                "tags": [],
                "category": "utility",
                "license": "MIT",
                "min_organizer_version": "2.0.0",
                "max_organizer_version": None,
                "downloads": 0,
                "rating": 0.0,
                "reviews_count": 0,
            }
        )


def test_reviews_add_update_delete_and_average(tmp_path: Path) -> None:
    manager = ReviewManager(tmp_path / "reviews.json")
    manager.add_review(
        PluginReview(
            plugin_name="alpha",
            user_id="u1",
            rating=4,
            title="Good",
            content="Works well",
        )
    )
    manager.add_review(
        PluginReview(
            plugin_name="alpha",
            user_id="u2",
            rating=2,
            title="Needs work",
            content="Rough edges",
        )
    )
    assert pytest.approx(manager.get_average_rating("alpha"), 0.01) == 3.0

    manager.update_review(
        PluginReview(
            plugin_name="alpha",
            user_id="u2",
            rating=5,
            title="Improved",
            content="Now excellent",
        )
    )
    assert pytest.approx(manager.get_average_rating("alpha"), 0.01) == 4.5

    manager.mark_helpful("alpha", "u1", "u3")
    reviews = manager.get_reviews("alpha")
    assert reviews[0].helpful_count >= 0

    manager.delete_review("alpha", "u1")
    remaining = manager.get_reviews("alpha", limit=10)
    assert len(remaining) == 1
    assert remaining[0].user_id == "u2"
