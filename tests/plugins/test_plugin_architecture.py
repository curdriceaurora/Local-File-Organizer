"""Tests for Phase 6 plugin architecture foundations."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from file_organizer.plugins import (
    HookExecutionError,
    HookRegistry,
    PluginConfig,
    PluginConfigError,
    PluginConfigManager,
    PluginLoadError,
    PluginNotLoadedError,
    PluginPermissionError,
    PluginRecord,
    PluginRegistry,
    PluginSandbox,
    PluginSecurityPolicy,
)


def _write_plugin(
    plugin_root: Path,
    plugin_name: str,
    source: str,
    *,
    manifest: dict | None = None,
) -> Path:
    """Create a plugin directory with ``plugin.py`` and ``plugin.json``.

    Returns the **directory** path (not the ``.py`` file).
    """
    plugin_dir = plugin_root / plugin_name
    plugin_dir.mkdir(parents=True, exist_ok=True)
    plugin_file = plugin_dir / "plugin.py"
    plugin_file.write_text(source, encoding="utf-8")

    # Write manifest — use sensible defaults when not provided.
    manifest_data = manifest or {
        "name": plugin_name,
        "version": "1.0.0",
        "author": "test",
        "description": f"{plugin_name} plugin",
        "entry_point": "plugin.py",
    }
    manifest_path = plugin_dir / "plugin.json"
    manifest_path.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")

    return plugin_dir


def test_plugin_registry_load_and_unload(tmp_path: Path) -> None:
    """Registry correctly loads a plugin via subprocess executor and unloads it."""
    plugin_root = tmp_path / "plugins"
    source = """\
from file_organizer.plugins.base import Plugin

class ExamplePlugin(Plugin):
    name = "example"
    version = "1.0.0"
    allowed_paths: list = []

    def get_metadata(self):  # type: ignore[override]
        from file_organizer.plugins.base import PluginMetadata
        return PluginMetadata(
            name=self.name,
            version=self.version,
            author="test",
            description="example plugin",
        )

    def on_load(self) -> None:
        pass

    def on_enable(self) -> None:
        pass

    def on_disable(self) -> None:
        pass

    def on_unload(self) -> None:
        pass
"""
    plugin_dir = _write_plugin(plugin_root, "example", source)

    registry = PluginRegistry()
    assert registry.list_plugins() == []

    record = registry.load_plugin(plugin_dir)
    assert isinstance(record, PluginRecord)
    assert record.name == "example"
    assert record.version == "1.0.0"
    assert record.plugin_dir == plugin_dir
    assert registry.list_plugins() == ["example"]

    # Attempting to load the same plugin again raises PluginLoadError
    with pytest.raises(PluginLoadError, match="already loaded"):
        registry.load_plugin(plugin_dir)

    # Retrieve the record by name
    fetched = registry.get_plugin("example")
    assert fetched.name == record.name

    # Unload cleans up the registry entry
    registry.unload_plugin("example")
    assert registry.list_plugins() == []

    # get_plugin after unload raises PluginNotLoadedError
    with pytest.raises(PluginNotLoadedError):
        registry.get_plugin("example")


def test_plugin_registry_load_error_on_missing_manifest(tmp_path: Path) -> None:
    """load_plugin raises PluginLoadError when plugin.json is missing."""
    registry = PluginRegistry()
    # Directory exists but has no plugin.json
    empty_dir = tmp_path / "no_manifest"
    empty_dir.mkdir()
    (empty_dir / "plugin.py").write_text("# empty\n", encoding="utf-8")

    with pytest.raises(PluginLoadError, match="plugin.json"):
        registry.load_plugin(empty_dir)


def test_plugin_registry_load_error_on_missing_entry_point(tmp_path: Path) -> None:
    """load_plugin raises PluginLoadError when the entry-point file is missing."""
    registry = PluginRegistry()
    plugin_dir = tmp_path / "bad_entry"
    plugin_dir.mkdir()
    manifest = {
        "name": "bad-entry",
        "version": "1.0.0",
        "author": "test",
        "description": "bad entry point",
        "entry_point": "nonexistent.py",
    }
    (plugin_dir / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(PluginLoadError, match="Entry-point"):
        registry.load_plugin(plugin_dir)


def test_plugin_registry_load_error_on_invalid_manifest(tmp_path: Path) -> None:
    """load_plugin raises PluginLoadError when plugin.json has bad JSON."""
    registry = PluginRegistry()
    plugin_dir = tmp_path / "bad_json"
    plugin_dir.mkdir()
    (plugin_dir / "plugin.json").write_text("{bad json}", encoding="utf-8")

    with pytest.raises(PluginLoadError, match="Invalid JSON"):
        registry.load_plugin(plugin_dir)


def test_plugin_registry_load_error_on_missing_required_field(tmp_path: Path) -> None:
    """load_plugin raises PluginLoadError when a required field is missing."""
    registry = PluginRegistry()
    plugin_dir = tmp_path / "missing_field"
    plugin_dir.mkdir()
    # Missing "author" required field
    manifest = {
        "name": "incomplete",
        "version": "1.0.0",
        "description": "missing author",
        "entry_point": "plugin.py",
    }
    (plugin_dir / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
    (plugin_dir / "plugin.py").write_text("# empty\n", encoding="utf-8")

    with pytest.raises(PluginLoadError, match="author"):
        registry.load_plugin(plugin_dir)


def test_plugin_registry_load_error_on_entry_point_traversal(tmp_path: Path) -> None:
    """load_plugin raises PluginLoadError when entry_point escapes plugin dir."""
    registry = PluginRegistry()
    plugin_dir = tmp_path / "traversal"
    plugin_dir.mkdir()
    # Entry point that tries to escape via path traversal
    manifest = {
        "name": "traversal",
        "version": "1.0.0",
        "author": "test",
        "description": "path traversal attempt",
        "entry_point": "../../etc/passwd",
    }
    (plugin_dir / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(PluginLoadError, match="escapes plugin directory"):
        registry.load_plugin(plugin_dir)


def test_plugin_config_manager_roundtrip(tmp_path: Path) -> None:
    manager = PluginConfigManager(tmp_path / "config")
    saved = PluginConfig(
        name="sample-plugin",
        enabled=True,
        settings={"threshold": 0.8, "mode": "strict"},
        permissions=["organize", "read"],
    )

    manager.save_config(saved)
    loaded = manager.load_config("sample-plugin")
    assert loaded == saved
    assert manager.list_configured_plugins() == ["sample-plugin"]


def test_plugin_config_manager_validation(tmp_path: Path) -> None:
    manager = PluginConfigManager(tmp_path / "config")
    with pytest.raises(PluginConfigError):
        manager.config_path("../invalid")


def test_hook_registry_collects_errors() -> None:
    hooks = HookRegistry()

    def good_callback(value: int) -> int:
        return value + 1

    def bad_callback(_: int) -> int:
        raise RuntimeError("boom")

    hooks.register_hook("after_scan", good_callback)
    hooks.register_hook("after_scan", bad_callback)

    results = hooks.trigger_hook("after_scan", 10)
    assert len(results) == 2
    assert results[0].succeeded
    assert results[0].value == 11
    assert not results[1].succeeded
    assert isinstance(results[1].error, RuntimeError)

    with pytest.raises(HookExecutionError):
        hooks.trigger_hook("after_scan", 10, stop_on_error=True)


def test_plugin_sandbox_enforces_permissions(tmp_path: Path) -> None:
    allowed_root = tmp_path / "allowed"
    allowed_root.mkdir()
    allowed_file = allowed_root / "file.txt"
    blocked_file = tmp_path / "blocked.txt"
    policy = PluginSecurityPolicy.from_permissions(
        allowed_paths=[allowed_root],
        allowed_operations=["organize", "scan"],
    )
    sandbox = PluginSandbox("demo", policy)

    assert sandbox.validate_file_access(allowed_file)
    assert sandbox.validate_operation("scan")
    assert not sandbox.validate_file_access(blocked_file)
    assert not sandbox.validate_operation("delete")

    with pytest.raises(PluginPermissionError):
        sandbox.require_file_access(blocked_file)

    with pytest.raises(PluginPermissionError):
        sandbox.require_operation("delete")
