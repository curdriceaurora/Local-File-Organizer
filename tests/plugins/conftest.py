"""Shared fixtures for plugin tests."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from file_organizer.plugins.registry import PluginRecord
from file_organizer.plugins.security import PluginSecurityPolicy


@pytest.fixture
def plugin_manifest_writer() -> Callable[[Path, dict[str, object]], Path]:
    """Write a plugin manifest and return the manifest path."""

    def write_manifest(plugin_dir: Path, manifest: dict[str, object]) -> Path:
        plugin_dir.mkdir(parents=True, exist_ok=True)
        path = plugin_dir / "plugin.json"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        return path

    return write_manifest


@pytest.fixture
def plugin_manifest_dir(
    plugin_manifest_writer: Callable[[Path, dict[str, object]], Path],
) -> Callable[[Path, dict[str, object] | None], Path]:
    """Create a minimal plugin directory with plugin.json and entry point."""

    def make_manifest_dir(tmp_path: Path, manifest: dict[str, object] | None = None) -> Path:
        plugin_dir = tmp_path / "my-plugin"
        data = manifest or {
            "name": "test-plugin",
            "version": "1.0.0",
            "author": "tester",
            "description": "A test plugin",
            "entry_point": "plugin.py",
        }
        plugin_manifest_writer(plugin_dir, data)
        (plugin_dir / str(data["entry_point"])).write_text("# empty plugin\n", encoding="utf-8")
        return plugin_dir

    return make_manifest_dir


@pytest.fixture
def plugin_record_factory() -> Callable[[str], PluginRecord]:
    """Create a mock-backed PluginRecord for direct registry tests."""

    def make_record(name: str = "test-plugin") -> PluginRecord:
        return PluginRecord(
            name=name,
            version="1.0.0",
            plugin_dir=Path("fake"),
            policy=PluginSecurityPolicy.unrestricted(),
            manifest={"name": name},
            executor=MagicMock(),
        )

    return make_record
