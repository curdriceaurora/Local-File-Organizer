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

## Quick workflow: launch, configure, and verify

```bash
# 1) Ensure desktop dependencies are installed
pip install -e ".[desktop]"

# 2) Launch desktop mode
file-organizer desktop

# 3) If needed, tune the window
file-organizer desktop --title "File Organizer" --width 1280 --height 820
```

After launch, validate navigation from Home -> Organize -> Settings in the desktop window.
For UI behavior details, see [Web UI Guide](web-ui/index.md).

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

Templates should use the cross-context helpers from `desktop_api.js`:

- `window.desktopBrowseFile(inputId, fileTypes)`
- `window.desktopSaveFile(suggestedName, fileTypes)`
- `window.desktopOpenPath(path)`

These helpers wrap the desktop-only `window.pywebview.api.*` methods and add browser-safe fallbacks/no-ops so templates can run in both desktop and normal browser contexts. In desktop mode, the underlying pywebview implementation exposes `browse_directory()`, `browse_file(fileTypes)`, `save_file(suggestedName, fileTypes)`, and `open_path(path)`.

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
