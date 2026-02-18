"""Plugin installation and update orchestration for marketplace packages."""

from __future__ import annotations

import json
import os
import shutil
import stat
import tempfile
import zipfile
from pathlib import Path
from typing import Optional

from file_organizer.plugins.marketplace.errors import MarketplaceInstallError
from file_organizer.plugins.marketplace.models import InstalledPlugin
from file_organizer.plugins.marketplace.repository import PluginRepository
from file_organizer.plugins.marketplace.validators import normalize_plugin_name
from file_organizer.version import __version__

_MAX_EXTRACTED_BYTES = 100 * 1024 * 1024  # 100 MB safety guard


def _normalize_version(version: str) -> tuple[tuple[int, str], ...]:
    parts = version.replace("-", ".").split(".")
    result: list[tuple[int, str]] = []
    for part in parts:
        token = part.strip()
        if token.isdigit():
            result.append((0, f"{int(token):08d}"))
        else:
            result.append((1, token.lower()))
    return tuple(result)


class PluginInstaller:
    """Install/uninstall/update plugins from a repository."""

    def __init__(
        self,
        plugin_dir: Path,
        repository: PluginRepository,
        *,
        installed_plugins_file: Optional[Path] = None,
    ) -> None:
        self.plugin_dir = plugin_dir
        self.repository = repository
        self.installed_plugins_file = installed_plugins_file or (plugin_dir / "installed.json")

    def install(self, name: str, *, version: Optional[str] = None) -> InstalledPlugin:
        """Install a plugin package and its dependencies."""
        return self._install_recursive(name, version=version, install_stack=[])

    def _install_recursive(
        self,
        name: str,
        *,
        version: Optional[str],
        install_stack: list[str],
    ) -> InstalledPlugin:
        try:
            normalized_name = normalize_plugin_name(name)
        except ValueError as exc:
            raise MarketplaceInstallError(str(exc)) from exc
        if normalized_name in install_stack:
            cycle = " -> ".join([*install_stack, normalized_name])
            raise MarketplaceInstallError(f"Circular plugin dependency detected: {cycle}.")
        install_stack.append(normalized_name)

        try:
            installed = self._load_installed()
            package = self.repository.get_plugin(normalized_name, version=version)
            self._validate_version_compatibility(
                package.min_organizer_version,
                package.max_organizer_version,
            )

            for dependency in package.dependencies:
                dep_name = dependency.strip()
                if not dep_name:
                    continue
                if dep_name in installed:
                    continue
                self._install_recursive(dep_name, version=None, install_stack=install_stack)
                installed = self._load_installed()

            with tempfile.TemporaryDirectory(prefix="fo-marketplace-") as temp_dir_raw:
                temp_dir = Path(temp_dir_raw)
                archive_path = self.repository.download_plugin(package, temp_dir)
                if not self.repository.verify_checksum(archive_path, package.checksum_sha256):
                    raise MarketplaceInstallError(
                        f"Checksum verification failed for plugin '{package.name}'."
                    )

                extracted_dir = temp_dir / "extract"
                extracted_dir.mkdir(parents=True, exist_ok=True)
                self._extract_plugin_archive(archive_path, extracted_dir)
                source_dir = self._locate_plugin_root(extracted_dir)

                destination = self._resolve_plugin_path(package.name)
                self.plugin_dir.mkdir(parents=True, exist_ok=True)
                if destination.exists():
                    shutil.rmtree(destination)
                shutil.copytree(source_dir, destination)

            installed_plugin = InstalledPlugin(
                name=package.name,
                version=package.version,
                source_url=self.repository.repo_url,
            )
            installed[package.name] = installed_plugin
            self._save_installed(installed)
            return installed_plugin
        finally:
            install_stack.pop()

    def uninstall(self, name: str) -> None:
        """Uninstall plugin and remove installed metadata."""
        normalized_name = self._normalize_plugin_name(name)
        destination = self._resolve_plugin_path(normalized_name)
        installed = self._load_installed()
        if normalized_name not in installed:
            raise MarketplaceInstallError(f"Plugin '{normalized_name}' is not installed.")
        if destination.exists():
            shutil.rmtree(destination)

        installed.pop(normalized_name, None)
        self._save_installed(installed)

    def update(self, name: str) -> Optional[InstalledPlugin]:
        """Update installed plugin to latest version if newer exists."""
        installed = self._load_installed()
        current = installed.get(name)
        if current is None:
            raise MarketplaceInstallError(f"Plugin '{name}' is not installed.")

        latest = self.repository.get_plugin(name)
        if _normalize_version(latest.version) <= _normalize_version(current.version):
            return None
        return self.install(name, version=latest.version)

    def list_installed(self) -> list[InstalledPlugin]:
        """List installed plugins sorted by name."""
        installed = self._load_installed()
        items = list(installed.values())
        items.sort(key=lambda plugin: plugin.name.lower())
        return items

    def check_updates(self) -> list[str]:
        """Return names of installed plugins that have newer versions available."""
        updates: list[str] = []
        for installed in self.list_installed():
            latest = self.repository.get_plugin(installed.name)
            if _normalize_version(latest.version) > _normalize_version(installed.version):
                updates.append(installed.name)
        return updates

    def _validate_version_compatibility(
        self,
        min_version: str,
        max_version: Optional[str],
    ) -> None:
        current = _normalize_version(__version__)
        minimum = _normalize_version(min_version)
        if current < minimum:
            raise MarketplaceInstallError(
                f"Plugin requires file-organizer >= {min_version} (current: {__version__})."
            )
        if max_version is not None and current > _normalize_version(max_version):
            raise MarketplaceInstallError(
                f"Plugin supports file-organizer <= {max_version} (current: {__version__})."
            )

    def _extract_plugin_archive(self, archive_path: Path, destination: Path) -> None:
        total_uncompressed = 0
        destination_root = destination.resolve()

        with zipfile.ZipFile(archive_path, "r") as archive:
            for info in archive.infolist():
                member = Path(info.filename)
                if member.is_absolute() or ".." in member.parts:
                    raise MarketplaceInstallError("Plugin archive contains unsafe paths.")

                mode = info.external_attr >> 16
                if stat.S_ISLNK(mode):
                    raise MarketplaceInstallError("Plugin archive contains symbolic links.")

                if info.is_dir():
                    continue
                total_uncompressed += info.file_size
                if total_uncompressed > _MAX_EXTRACTED_BYTES:
                    raise MarketplaceInstallError("Plugin archive exceeds extraction size limit.")

                target = (destination_root / member).resolve()
                try:
                    target.relative_to(destination_root)
                except ValueError as exc:
                    raise MarketplaceInstallError(
                        "Plugin archive extraction escaped target path."
                    ) from exc
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info, "r") as source, target.open("wb") as handle:
                    shutil.copyfileobj(source, handle)

    def _locate_plugin_root(self, extracted_dir: Path) -> Path:
        """Resolve plugin root directory after archive extraction."""
        direct_plugin = extracted_dir / "plugin.py"
        if direct_plugin.exists():
            return extracted_dir

        children = [path for path in extracted_dir.iterdir() if path.name != "__MACOSX"]
        directory_children = [path for path in children if path.is_dir()]
        if len(directory_children) == 1 and (directory_children[0] / "plugin.py").exists():
            return directory_children[0]
        raise MarketplaceInstallError(
            "Plugin archive must include plugin.py at root or one top-level directory."
        )

    def _load_installed(self) -> dict[str, InstalledPlugin]:
        if not self.installed_plugins_file.exists():
            return {}
        try:
            payload = json.loads(self.installed_plugins_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise MarketplaceInstallError("Failed to read installed plugin registry.") from exc
        if not isinstance(payload, dict):
            raise MarketplaceInstallError("Installed plugin registry must be a JSON object.")

        installed: dict[str, InstalledPlugin] = {}
        for key, raw in payload.items():
            if not isinstance(key, str) or not isinstance(raw, dict):
                continue
            plugin = InstalledPlugin.from_dict(raw)
            installed[key] = plugin
        return installed

    def _save_installed(self, installed: dict[str, InstalledPlugin]) -> None:
        self.installed_plugins_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {name: plugin.to_dict() for name, plugin in installed.items()}

        fd, temp_path = tempfile.mkstemp(
            dir=str(self.installed_plugins_file.parent),
            prefix=f".{self.installed_plugins_file.name}.",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
            Path(temp_path).replace(self.installed_plugins_file)
        except OSError as exc:
            raise MarketplaceInstallError("Failed to persist installed plugin registry.") from exc
        finally:
            leftover = Path(temp_path)
            if leftover.exists():
                leftover.unlink(missing_ok=True)

    def _resolve_plugin_path(self, name: str) -> Path:
        normalized = self._normalize_plugin_name(name)
        plugin_root = self.plugin_dir.resolve()
        destination = (plugin_root / normalized).resolve()
        try:
            destination.relative_to(plugin_root)
        except ValueError as exc:
            raise MarketplaceInstallError(
                f"Resolved plugin path escapes plugin directory for '{normalized}'."
            ) from exc
        return destination

    def _normalize_plugin_name(self, name: str) -> str:
        try:
            return normalize_plugin_name(name)
        except ValueError as exc:
            raise MarketplaceInstallError(str(exc)) from exc
