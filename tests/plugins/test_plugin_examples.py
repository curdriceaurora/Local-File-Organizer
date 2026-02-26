"""Smoke tests for bundled example plugins."""

from __future__ import annotations

from pathlib import Path

import pytest

from file_organizer.plugins import (
    PluginRecord,
    PluginRegistry,
)

EXAMPLE_ROOT = Path(__file__).resolve().parents[2] / "examples" / "plugins"
EXPECTED_EXAMPLES = {
    "hello_world",
    "file_logger",
    "auto_backup",
    "metadata_enricher",
}


def test_example_plugins_are_discoverable() -> None:
    """All expected example plugin directories exist with plugin.py and plugin.json."""
    found = {
        d.name
        for d in EXAMPLE_ROOT.iterdir()
        if d.is_dir()
        and (d / "plugin.py").exists()
        and (d / "plugin.json").exists()
    }
    assert found == EXPECTED_EXAMPLES


@pytest.mark.timeout(120)
def test_example_plugins_load_and_lifecycle() -> None:
    """Each example plugin loads successfully through PluginRegistry."""
    registry = PluginRegistry()

    for plugin_name in sorted(EXPECTED_EXAMPLES):
        plugin_dir = EXAMPLE_ROOT / plugin_name
        record = registry.load_plugin(plugin_dir)

        assert isinstance(record, PluginRecord)
        assert record.name == plugin_name

        # Metadata comes from the manifest (plugin.json), not an in-process instance.
        assert record.manifest["name"] == plugin_name
        assert record.manifest["version"] == "1.0.0"
        assert record.manifest["author"] == "File Organizer Team"

        # Clean up — unload after each so names don't collide across iterations.
        registry.unload_plugin(plugin_name)

    assert registry.list_plugins() == []


@pytest.mark.timeout(120)
def test_example_plugins_enable_disable_via_executor() -> None:
    """Enable/disable lifecycle calls go through the executor without error."""
    registry = PluginRegistry()
    plugin_dir = EXAMPLE_ROOT / "hello_world"
    record = registry.load_plugin(plugin_dir)

    try:
        # on_enable and on_disable routed through subprocess executor.
        record.executor.call("on_enable")
        record.executor.call("on_disable")
    finally:
        registry.unload_plugin("hello_world")
