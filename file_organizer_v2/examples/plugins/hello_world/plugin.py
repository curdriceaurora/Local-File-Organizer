"""Minimal plugin example for lifecycle hooks."""

from __future__ import annotations

from file_organizer.plugins import Plugin, PluginMetadata


class HelloWorldPlugin(Plugin):
    """Simple plugin that records lifecycle transitions."""

    name = "hello_world"
    version = "1.0.0"
    allowed_paths: list = []

    def on_load(self) -> None:
        self.config.setdefault("events", []).append("loaded")

    def on_enable(self) -> None:
        self.config.setdefault("events", []).append("enabled")

    def on_disable(self) -> None:
        self.config.setdefault("events", []).append("disabled")

    def on_unload(self) -> None:
        self.config.setdefault("events", []).append("unloaded")

    def get_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="hello_world",
            version="1.0.0",
            author="File Organizer Team",
            description="Lifecycle hello world plugin.",
        )
