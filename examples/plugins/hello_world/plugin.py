"""Minimal plugin example for lifecycle hooks."""

from __future__ import annotations

from file_organizer.plugins import Plugin, PluginMetadata


class HelloWorldPlugin(Plugin):
    """Simple plugin that records lifecycle transitions."""

    name = "hello_world"
    version = "1.0.0"
    allowed_paths: list = []

    def on_load(self) -> None:
        """Handle plugin load event."""
        self.config.setdefault("events", []).append("loaded")

    def on_enable(self) -> None:
        """Handle plugin enable event."""
        self.config.setdefault("events", []).append("enabled")

    def on_disable(self) -> None:
        """Handle plugin disable event."""
        self.config.setdefault("events", []).append("disabled")

    def on_unload(self) -> None:
        """Handle plugin unload event."""
        self.config.setdefault("events", []).append("unloaded")

    def get_metadata(self) -> PluginMetadata:
        """Return plugin metadata."""
        return PluginMetadata(
            name="hello_world",
            version="1.0.0",
            author="File Organizer Team",
            description="Lifecycle hello world plugin.",
        )
