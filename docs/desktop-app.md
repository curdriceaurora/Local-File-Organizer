# Desktop App

The desktop app runs the same web UI inside a native window using **pywebview**.

## Launch commands

Preferred unified commands:

```bash
file-organizer desktop
# or
fo desktop
```

Compatibility script (still available):

```bash
file-organizer-desktop
```

## Runtime model

At launch, the desktop app:

1. Finds a free local ephemeral port
2. Starts the FastAPI app on `127.0.0.1:<port>` in a background thread
3. Waits for server readiness
4. Opens a native OS window to the local UI

## Install

```bash
pip install "local-file-organizer[desktop]"
```

From source:

```bash
pip install -e ".[desktop]"
```

## pywebview JavaScript bridge

When running in desktop mode, the UI can call:

- `window.pywebview.api.browse_directory()`
- `window.pywebview.api.browse_file(fileTypes)`
- `window.pywebview.api.save_file(suggestedName, fileTypes)`
- `window.pywebview.api.open_path(path)`

`desktop_api.js` wraps these with browser-safe fallbacks so templates can run in both desktop and normal browser contexts.

## Troubleshooting

### `pywebview` import error

Install the desktop extra:

```bash
pip install "local-file-organizer[desktop]"
```

### Blank/slow first window

The launcher waits for backend readiness, but cold starts can still feel slow. Check terminal output for server startup errors.

### Linux WebKit packages

Install required WebKitGTK packages (distribution names can vary):

```bash
sudo apt-get install -y libgirepository1.0-dev gir1.2-webkit2-4.1
```

### AI features unavailable

Make sure your provider backend is running/configured (for default local mode, start Ollama).

## Related docs

- [Web UI Guide](web-ui/index.md)
- [Settings & Profile](web-ui/settings.md)
- [Configuration Guide](CONFIGURATION.md)
