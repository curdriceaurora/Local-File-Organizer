"""Smoke tests for bundled example plugins."""
from __future__ import annotations

from pathlib import Path

from file_organizer.plugins import (
    PluginConfigManager,
    PluginLifecycleManager,
    PluginRegistry,
    get_hook_metadata,
)

EXAMPLE_ROOT = Path(__file__).resolve().parents[2] / "examples" / "plugins"
EXPECTED_EXAMPLES = {
    "hello_world",
    "file_logger",
    "auto_backup",
    "metadata_enricher",
}


def test_example_plugins_are_discoverable() -> None:
    registry = PluginRegistry(EXAMPLE_ROOT)
    discovered = set(registry.discover_plugins())
    assert discovered == EXPECTED_EXAMPLES


def test_example_plugins_load_and_lifecycle(tmp_path: Path) -> None:
    registry = PluginRegistry(
        EXAMPLE_ROOT,
        config_manager=PluginConfigManager(tmp_path / "plugin-config"),
    )
    lifecycle = PluginLifecycleManager(registry)

    for plugin_name in sorted(EXPECTED_EXAMPLES):
        plugin = lifecycle.load(plugin_name)
        metadata = plugin.get_metadata()
        assert metadata.name == plugin_name

        lifecycle.enable(plugin_name)
        assert plugin.enabled

        if hasattr(plugin, "on_file_organized"):
            callback = plugin.on_file_organized  # type: ignore[attr-defined]
            hook_metadata = get_hook_metadata(callback)
            assert hook_metadata is not None
            assert hook_metadata[0] == "file.organized"

        lifecycle.disable(plugin_name)
        assert not plugin.enabled
        lifecycle.unload(plugin_name)
