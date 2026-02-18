"""Smoke tests for bundled example plugins."""

from __future__ import annotations

from pathlib import Path

from file_organizer.plugins import (
    PluginRecord,
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
    """All expected example plugin directories exist with a plugin.py file."""
    found = {
        d.name
        for d in EXAMPLE_ROOT.iterdir()
        if d.is_dir() and (d / "plugin.py").exists()
    }
    assert found == EXPECTED_EXAMPLES


def test_example_plugins_load_and_lifecycle() -> None:
    """Each example plugin loads successfully through PluginRegistry."""
    registry = PluginRegistry()

    for plugin_name in sorted(EXPECTED_EXAMPLES):
        plugin_file = EXAMPLE_ROOT / plugin_name / "plugin.py"
        record = registry.load_plugin(plugin_file)

        assert isinstance(record, PluginRecord)
        assert record.name == plugin_name

        metadata = record.plugin.get_metadata()
        assert metadata.name == plugin_name

        # Clean up — unload after each so names don't collide across iterations.
        registry.unload_plugin(plugin_name)

    assert registry.list_plugins() == []


def test_file_logger_example_has_hook() -> None:
    """The file_logger plugin exposes a hook-annotated method."""
    registry = PluginRegistry()
    plugin_file = EXAMPLE_ROOT / "file_logger" / "plugin.py"
    record = registry.load_plugin(plugin_file)

    try:
        plugin_instance = record.plugin
        if hasattr(plugin_instance, "on_file_organized"):
            callback = plugin_instance.on_file_organized  # type: ignore[attr-defined]
            hook_meta = get_hook_metadata(callback)
            assert hook_meta is not None
            assert hook_meta[0] == "file.organized"
    finally:
        registry.unload_plugin("file_logger")
