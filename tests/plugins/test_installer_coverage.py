"""Coverage tests for plugins.marketplace.installer module."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from file_organizer.plugins.marketplace.errors import MarketplaceInstallError
from file_organizer.plugins.marketplace.installer import (
    PluginInstaller,
    _normalize_version,
)
from file_organizer.plugins.marketplace.models import PluginPackage

pytestmark = pytest.mark.unit

_VALID_SHA = "a" * 64


def _make_package(
    name: str = "demo",
    version: str = "1.0.0",
    checksum: str = _VALID_SHA,
    **kw,
) -> PluginPackage:
    defaults = {
        "name": name,
        "version": version,
        "author": "tester",
        "description": "desc",
        "download_url": "demo.zip",
        "checksum_sha256": checksum,
        "size_bytes": 1024,
    }
    defaults.update(kw)
    return PluginPackage.from_dict(defaults)


def _make_archive(path: Path, files: dict[str, bytes] | None = None) -> Path:
    """Create a valid plugin zip archive."""
    archive_path = path / "demo-1.0.0.zip"
    with zipfile.ZipFile(archive_path, "w") as zf:
        zf.writestr("plugin.py", (files or {}).get("plugin.py", b"# plugin"))
    return archive_path


class TestNormalizeVersion:
    def test_numeric(self):
        assert _normalize_version("1.2.3") < _normalize_version("1.2.4")

    def test_mixed(self):
        assert _normalize_version("1.0.0") < _normalize_version("2.0.0")

    def test_prerelease(self):
        result = _normalize_version("1.0.0-alpha")
        assert isinstance(result, tuple)


class TestPluginInstallerInit:
    def test_default_installed_file(self, tmp_path):
        repo = MagicMock()
        installer = PluginInstaller(tmp_path / "plugins", repo)
        assert installer.installed_plugins_file == tmp_path / "plugins" / "installed.json"

    def test_custom_installed_file(self, tmp_path):
        repo = MagicMock()
        custom = tmp_path / "custom.json"
        installer = PluginInstaller(tmp_path / "plugins", repo, installed_plugins_file=custom)
        assert installer.installed_plugins_file == custom


class TestPluginInstallerListInstalled:
    def test_empty_when_no_file(self, tmp_path):
        repo = MagicMock()
        installer = PluginInstaller(tmp_path / "plugins", repo)
        assert installer.list_installed() == []

    def test_load_existing(self, tmp_path):
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        state_file = plugins_dir / "installed.json"
        state_file.write_text(
            json.dumps(
                {
                    "demo": {
                        "name": "demo",
                        "version": "1.0.0",
                        "source_url": "https://example.com",
                        "installed_at": "2024-01-01T00:00:00Z",
                    }
                }
            )
        )
        repo = MagicMock()
        installer = PluginInstaller(plugins_dir, repo)
        installed = installer.list_installed()
        assert len(installed) == 1
        assert installed[0].name == "demo"

    def test_invalid_json_raises(self, tmp_path):
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        (plugins_dir / "installed.json").write_text("{bad")
        repo = MagicMock()
        installer = PluginInstaller(plugins_dir, repo)
        with pytest.raises(MarketplaceInstallError, match="Failed to read"):
            installer.list_installed()

    def test_non_dict_raises(self, tmp_path):
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        (plugins_dir / "installed.json").write_text(json.dumps([1, 2]))
        repo = MagicMock()
        installer = PluginInstaller(plugins_dir, repo)
        with pytest.raises(MarketplaceInstallError, match="must be a JSON object"):
            installer.list_installed()


class TestPluginInstallerUninstall:
    def test_uninstall_not_installed_raises(self, tmp_path):
        repo = MagicMock()
        installer = PluginInstaller(tmp_path / "plugins", repo)
        with pytest.raises(MarketplaceInstallError, match="not installed"):
            installer.uninstall("demo")

    def test_uninstall_removes_directory(self, tmp_path):
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        plugin_dir = plugins_dir / "demo"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.py").write_text("# code")

        state_file = plugins_dir / "installed.json"
        state_file.write_text(
            json.dumps(
                {
                    "demo": {
                        "name": "demo",
                        "version": "1.0.0",
                        "source_url": "https://example.com",
                        "installed_at": "2024-01-01T00:00:00Z",
                    }
                }
            )
        )
        repo = MagicMock()
        installer = PluginInstaller(plugins_dir, repo)
        installer.uninstall("demo")
        assert not plugin_dir.exists()
        assert installer.list_installed() == []


class TestPluginInstallerUpdate:
    def test_update_not_installed_raises(self, tmp_path):
        repo = MagicMock()
        installer = PluginInstaller(tmp_path / "plugins", repo)
        with pytest.raises(MarketplaceInstallError, match="not installed"):
            installer.update("demo")

    def test_update_no_newer_version(self, tmp_path):
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        state_file = plugins_dir / "installed.json"
        state_file.write_text(
            json.dumps(
                {
                    "demo": {
                        "name": "demo",
                        "version": "2.0.0",
                        "source_url": "https://example.com",
                        "installed_at": "2024-01-01T00:00:00Z",
                    }
                }
            )
        )
        repo = MagicMock()
        repo.get_plugin.return_value = _make_package(version="1.0.0")
        installer = PluginInstaller(plugins_dir, repo)
        result = installer.update("demo")
        assert result is None


class TestPluginInstallerVersionCompatibility:
    def test_min_version_too_high(self, tmp_path):
        repo = MagicMock()
        installer = PluginInstaller(tmp_path / "plugins", repo)
        with pytest.raises(MarketplaceInstallError, match="requires"):
            installer._validate_version_compatibility("999.0.0", None)

    def test_max_version_too_low(self, tmp_path):
        repo = MagicMock()
        installer = PluginInstaller(tmp_path / "plugins", repo)
        with pytest.raises(MarketplaceInstallError, match="supports"):
            installer._validate_version_compatibility("0.0.1", "0.0.2")


class TestPluginInstallerExtractArchive:
    def test_extract_valid(self, tmp_path):
        archive = _make_archive(tmp_path)
        dest = tmp_path / "extract"
        dest.mkdir()
        repo = MagicMock()
        installer = PluginInstaller(tmp_path / "plugins", repo)
        installer._extract_plugin_archive(archive, dest)
        assert (dest / "plugin.py").exists()

    def test_extract_absolute_path_raises(self, tmp_path):
        archive_path = tmp_path / "bad.zip"
        with zipfile.ZipFile(archive_path, "w") as zf:
            zf.writestr("/etc/passwd", "malicious")
        dest = tmp_path / "extract"
        dest.mkdir()
        repo = MagicMock()
        installer = PluginInstaller(tmp_path / "plugins", repo)
        with pytest.raises(MarketplaceInstallError, match="unsafe paths"):
            installer._extract_plugin_archive(archive_path, dest)

    def test_extract_dotdot_raises(self, tmp_path):
        archive_path = tmp_path / "bad.zip"
        with zipfile.ZipFile(archive_path, "w") as zf:
            zf.writestr("../escape.txt", "malicious")
        dest = tmp_path / "extract"
        dest.mkdir()
        repo = MagicMock()
        installer = PluginInstaller(tmp_path / "plugins", repo)
        with pytest.raises(MarketplaceInstallError, match="unsafe paths"):
            installer._extract_plugin_archive(archive_path, dest)


class TestPluginInstallerLocateRoot:
    def test_direct_plugin_py(self, tmp_path):
        extracted = tmp_path / "extract"
        extracted.mkdir()
        (extracted / "plugin.py").write_text("# code")
        repo = MagicMock()
        installer = PluginInstaller(tmp_path / "plugins", repo)
        result = installer._locate_plugin_root(extracted)
        assert result == extracted

    def test_nested_single_dir(self, tmp_path):
        extracted = tmp_path / "extract"
        nested = extracted / "my-plugin"
        nested.mkdir(parents=True)
        (nested / "plugin.py").write_text("# code")
        repo = MagicMock()
        installer = PluginInstaller(tmp_path / "plugins", repo)
        result = installer._locate_plugin_root(extracted)
        assert result == nested

    def test_no_plugin_py_raises(self, tmp_path):
        extracted = tmp_path / "extract"
        extracted.mkdir()
        repo = MagicMock()
        installer = PluginInstaller(tmp_path / "plugins", repo)
        with pytest.raises(MarketplaceInstallError, match="plugin.py"):
            installer._locate_plugin_root(extracted)


class TestPluginInstallerResolvePluginPath:
    def test_normal_name(self, tmp_path):
        repo = MagicMock()
        installer = PluginInstaller(tmp_path / "plugins", repo)
        result = installer._resolve_plugin_path("demo")
        assert result.name == "demo"

    def test_path_traversal_raises(self, tmp_path):
        repo = MagicMock()
        installer = PluginInstaller(tmp_path / "plugins", repo)
        with pytest.raises(MarketplaceInstallError):
            installer._resolve_plugin_path("../../etc")


class TestPluginInstallerCircularDeps:
    def test_circular_dependency_raises(self, tmp_path):
        repo = MagicMock()
        pkg_a = _make_package("plugin-a", dependencies=["plugin-b"])
        pkg_b = _make_package("plugin-b", dependencies=["plugin-a"])
        repo.get_plugin.side_effect = lambda name, **kw: pkg_a if name == "plugin-a" else pkg_b
        repo.download_plugin.return_value = _make_archive(tmp_path)
        repo.verify_checksum.return_value = True

        installer = PluginInstaller(tmp_path / "plugins", repo)
        with pytest.raises(MarketplaceInstallError, match="Circular"):
            installer.install("plugin-a")
