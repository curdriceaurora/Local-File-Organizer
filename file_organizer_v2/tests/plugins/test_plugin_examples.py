"""Smoke tests for bundled example plugins."""

from __future__ import annotations

from pathlib import Path

from file_organizer.plugins import (
    PluginConfig,
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


def test_file_logger_example_appends_entries(tmp_path: Path) -> None:
    config_manager = PluginConfigManager(tmp_path / "plugin-config")
    log_path = tmp_path / "events.log"
    config_manager.save_config(
        PluginConfig(
            name="file_logger",
            enabled=True,
            settings={"log_file": str(log_path)},
        )
    )

    registry = PluginRegistry(EXAMPLE_ROOT, config_manager=config_manager)
    lifecycle = PluginLifecycleManager(registry)

    plugin = lifecycle.load("file_logger")
    lifecycle.enable("file_logger")
    callback = plugin.on_file_organized  # type: ignore[attr-defined]

    callback({"source_path": "a.txt", "destination_path": "A/a.txt"})
    callback({"source_path": "b.txt", "destination_path": "B/b.txt"})

    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert lines == [
        "organized:a.txt->A/a.txt",
        "organized:b.txt->B/b.txt",
    ]
