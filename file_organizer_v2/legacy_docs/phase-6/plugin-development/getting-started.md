# Plugin Development: Getting Started

This guide is optimized for the Phase 6 plugin API surface added in Task #241.

## Why This API Exists

The plugin API separates **extension logic** from **core internals** so plugins can evolve independently without direct imports into private app modules. The stable boundary is HTTP + hook metadata.

## Prerequisites

- Python 3.9+
- Editable install: `pip install -e ".[dev]"`
- API server running: `uvicorn file_organizer.api.main:app --reload`
- A valid API token from `/api/v1/auth/login`

## Quick Start

1. Create a plugin package directory under `examples/plugins/` (for local iteration).
1. Implement `Plugin` lifecycle methods and metadata.
1. Use SDK decorators from `file_organizer.plugins.sdk`.
1. Call plugin API endpoints via `PluginClient`.

Example skeleton:

```python
from file_organizer.plugins import Plugin, PluginMetadata
from file_organizer.plugins.sdk import hook

class MyPlugin(Plugin):
    def get_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="my_plugin",
            version="1.0.0",
            author="You",
            description="Example plugin",
        )

    def on_load(self) -> None:
        return None

    def on_enable(self) -> None:
        return None

    def on_disable(self) -> None:
        return None

    def on_unload(self) -> None:
        return None

    @hook("file.organized", priority=10)
    def handle_file_organized(self, payload: dict[str, object]) -> dict[str, object]:
        return {"ok": True, "payload": payload}
```

## Common Pitfalls

- Metadata `name` must match directory name for registry loading.
- Hook callbacks should not assume keys exist in payload.
- Plugin code should handle missing config keys and malformed values.
- Avoid writing outside explicitly configured directories.
