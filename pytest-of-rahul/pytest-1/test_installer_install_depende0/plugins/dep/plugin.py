from file_organizer.plugins import Plugin, PluginMetadata

class ExamplePlugin(Plugin):
    def get_metadata(self):
        return PluginMetadata(name='dep', version='1.0.0', author='tests', description='plugin')
    def on_load(self): pass
    def on_enable(self): pass
    def on_disable(self): pass
    def on_unload(self): pass