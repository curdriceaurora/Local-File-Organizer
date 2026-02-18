"""Plugin example that writes event logs to a text file."""

from __future__ import annotations

from pathlib import Path

from file_organizer.plugins import Plugin, PluginMetadata
from file_organizer.plugins.sdk import hook


class FileLoggerPlugin(Plugin):
    """Records selected plugin events in a plain text log."""

    def on_load(self) -> None:
        return None

    def on_enable(self) -> None:
        log_name = (
            str(self.config.get("log_file", "plugin-events.log")).strip() or "plugin-events.log"
        )
        self.log_file = Path(log_name)

    def on_disable(self) -> None:
        return None

    def on_unload(self) -> None:
        return None

    def get_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="file_logger",
            version="1.0.0",
            author="File Organizer Team",
            description="Writes plugin event activity to a log file.",
        )

    @hook("file.organized", priority=10)
    def on_file_organized(self, payload: dict[str, object]) -> dict[str, object]:
        line = f"organized:{payload.get('source_path')}->{payload.get('destination_path')}\n"
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        with self.log_file.open("a", encoding="utf-8") as log_fp:
            log_fp.write(line)
        return {"logged": True, "file": str(self.log_file)}
