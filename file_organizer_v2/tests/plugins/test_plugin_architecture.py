"""Tests for Phase 6 plugin architecture foundations."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from file_organizer.plugins import (
    HookExecutionError,
    HookRegistry,
    PluginConfig,
    PluginConfigError,
    PluginConfigManager,
    PluginDependencyError,
    PluginDiscoveryError,
    PluginLifecycleManager,
    PluginPermissionError,
    PluginRegistry,
    PluginSandbox,
    PluginSecurityPolicy,
    PluginState,
)


def _write_plugin(plugin_root: Path, plugin_name: str, source: str) -> Path:
    plugin_dir = plugin_root / plugin_name
    plugin_dir.mkdir(parents=True, exist_ok=True)
    plugin_file = plugin_dir / "plugin.py"
    plugin_file.write_text(source, encoding="utf-8")
    return plugin_file


def test_plugin_registry_and_lifecycle_flow(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugins"
    source = """
from file_organizer.plugins import Plugin, PluginMetadata

EVENTS = []

class ExamplePlugin(Plugin):
    def get_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="example",
            version="1.0.0",
            author="test",
            description="example plugin",
        )

    def on_load(self) -> None:
        EVENTS.append("load")

    def on_enable(self) -> None:
        EVENTS.append("enable")

    def on_disable(self) -> None:
        EVENTS.append("disable")

    def on_unload(self) -> None:
        EVENTS.append("unload")
"""
    _write_plugin(plugin_root, "example", source)
    registry = PluginRegistry(plugin_root, config_manager=PluginConfigManager(tmp_path / "config"))

    assert registry.discover_plugins() == ["example"]

    plugin = registry.load_plugin("example")
    record = registry.get_record("example")
    module_name = record.module_name
    assert record.metadata.name == "example"
    assert record.module.EVENTS == ["load"]  # type: ignore[attr-defined]

    same_plugin = registry.load_plugin("example")
    assert same_plugin is plugin
    assert record.module.EVENTS == ["load"]  # type: ignore[attr-defined]

    lifecycle = PluginLifecycleManager(registry)
    lifecycle.enable("example")
    assert plugin.enabled
    assert lifecycle.get_state("example") == PluginState.ENABLED

    lifecycle.disable("example")
    assert not plugin.enabled
    assert lifecycle.get_state("example") == PluginState.DISABLED

    lifecycle.unload("example")
    assert lifecycle.get_state("example") == PluginState.UNLOADED
    assert module_name not in sys.modules
    assert record.module.EVENTS == ["load", "enable", "disable", "unload"]  # type: ignore[attr-defined]


def test_plugin_registry_dependency_error(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugins"
    source = """
from file_organizer.plugins import Plugin, PluginMetadata

class DependsPlugin(Plugin):
    def get_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="dependent",
            version="1.0.0",
            author="test",
            description="dependency plugin",
            dependencies=("missing_dependency",),
        )

    def on_load(self) -> None:
        return None

    def on_enable(self) -> None:
        return None

    def on_disable(self) -> None:
        return None

    def on_unload(self) -> None:
        return None
"""
    _write_plugin(plugin_root, "dependent", source)
    registry = PluginRegistry(plugin_root)

    with pytest.raises(PluginDependencyError):
        registry.load_plugin("dependent")


def test_plugin_discovery_requires_directory(tmp_path: Path) -> None:
    not_a_dir = tmp_path / "not_a_dir.py"
    not_a_dir.write_text("# not a plugin directory", encoding="utf-8")
    registry = PluginRegistry(not_a_dir)
    with pytest.raises(PluginDiscoveryError):
        registry.discover_plugins()


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
