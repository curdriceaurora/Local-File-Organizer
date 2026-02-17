# Plugin SDK Guide

## Why Use the SDK

The SDK removes repeated plumbing (auth headers, endpoint paths, decorator metadata), keeping plugins focused on behavior.

## Core SDK Surface

- `PluginClient`
- `hook(...)`
- `command(...)`
- `PluginTestCase`

## PluginClient Example

```python
from file_organizer.plugins.api.hooks import HookEvent
from file_organizer.plugins.sdk import PluginClient

with PluginClient(base_url="http://localhost:8000", token="YOUR_TOKEN") as client:
    files = client.list_files(path="./demo", recursive=True)
    client.register_hook(event=HookEvent.FILE_ORGANIZED, callback_url="http://localhost:9000/hook")
```

## Decorator Metadata Example

```python
from file_organizer.plugins.sdk import command, hook

@hook("file.organized", priority=5)
def on_file_organized(payload: dict[str, object]) -> dict[str, object]:
    return {"handled": True}

@command("refresh-index", description="Rebuild plugin cache")
def refresh_index() -> None:
    ...
```

## Error Handling

- `PluginClientAuthError`: auth/permission failures
- `PluginClientError`: network failures, API validation errors, unexpected payloads
