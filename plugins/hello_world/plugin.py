"""Reference plugin used for development and integration checks."""

from __future__ import annotations

from file_organizer.plugins import Plugin, PluginMetadata


class HelloWorldPlugin(Plugin):
    """Minimal plugin demonstrating lifecycle handlers."""

    def get_metadata(self) -> PluginMetadata:
        """Return plugin metadata."""
        return PluginMetadata(
            name="hello_world",
            version="1.0.0",
            author="Local File Organizer Team",
            description="Reference plugin for lifecycle and registry checks.",
        )

    def on_load(self) -> None:
        """Handle plugin load event."""
        return None

    def on_enable(self) -> None:
        """Handle plugin enable event."""
        return None

    def on_disable(self) -> None:
        """Handle plugin disable event."""
        return None

    def on_unload(self) -> None:
        """Handle plugin unload event."""
        return None
