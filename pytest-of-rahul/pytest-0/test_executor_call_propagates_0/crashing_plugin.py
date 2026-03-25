from file_organizer.plugins.base import Plugin, PluginMetadata
class CrashingPlugin(Plugin):
    name = 'crashing'
    version = '1.0.0'
    allowed_paths = []
    def get_metadata(self):
        return PluginMetadata(name=self.name, version=self.version, author='test', description='crashing')
    def on_load(self):
        raise RuntimeError('intentional crash')
    def on_enable(self): pass
    def on_disable(self): pass
    def on_unload(self): pass
