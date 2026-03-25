from file_organizer.plugins.base import Plugin, PluginMetadata
class BenignPlugin(Plugin):
    name = 'benign'
    version = '1.0.0'
    allowed_paths = []
    def get_metadata(self):
        return PluginMetadata(name=self.name, version=self.version, author='test', description='benign')
    def on_load(self): pass
    def on_enable(self): pass
    def on_disable(self): pass
    def on_unload(self): pass
