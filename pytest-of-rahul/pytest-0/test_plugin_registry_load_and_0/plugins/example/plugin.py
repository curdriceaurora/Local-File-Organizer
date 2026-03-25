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
