from pathlib import Path
from typing import Any
from file_organizer.plugins.base import Plugin, PluginMetadata
class ReturningPlugin(Plugin):
    name = 'returning'
    version = '1.0.0'
    allowed_paths = []
    def get_metadata(self):
        return PluginMetadata(name=self.name, version=self.version, author='test', description='returning')
    def on_load(self): pass
    def on_enable(self): pass
    def on_disable(self): pass
    def on_unload(self): pass
    def on_file(self, file_path: Path, metadata: dict[str, Any]):
        return {'tag': 'injected', 'source': 'plugin'}
