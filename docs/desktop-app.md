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

The launcher waits for backend readiness, but cold starts can still feel slow. Check terminal output for server startup errors. If the window stays blank for more than 30 seconds:

```bash
# Run with verbose output to see the backend startup log
file-organizer desktop --verbose
```

### Backend Startup Failure

**Symptom**: The native window never opens and the terminal shows a traceback.

**Cause**: The embedded FastAPI server failed to start — common causes are port conflict, missing dependency, or Ollama not running.

**Solution**:

```bash
# Run the web server separately to see the full error
file-organizer serve --verbose

# If AI features fail to load, ensure Ollama (or your configured provider) is running
ollama serve

# For non-Ollama providers, verify environment variables are set
file-organizer config show
```

See [AI Provider Issues](troubleshooting.md#ai-provider-issues) in the Troubleshooting Guide for provider-specific fixes.

### Linux WebKit packages

Install required WebKitGTK packages (distribution names can vary):

```bash
sudo apt-get install -y libgirepository1.0-dev gir1.2-webkit2-4.1
```

### Native File Picker Dialog Not Appearing

**Symptom**: Clicking a file/folder browse button in the desktop app opens a standard HTML input instead of the native OS file picker.

**Cause**: The `window.pywebview.api` JavaScript bridge is only injected in full desktop mode. If pywebview is not fully initialized, the bridge falls back to a browser-safe no-op.

**Solution**:

- Ensure you launched with `file-organizer desktop` (not `file-organizer serve` in a browser).
- On Linux, confirm the WebKitGTK packages above are installed and up to date.
- Restart the desktop app; the bridge is injected during window load and may be missing if the page loaded before the backend was fully ready.

### Window Appears Off-Screen or Wrong Size

**Symptom**: The desktop window opens in the wrong position, off-screen, or too small to use.

**Cause**: pywebview restores the last saved window position, which can be off-screen after switching monitors or changing display resolution.

**Solution**:

Close the app and delete the saved window state, then relaunch:

```bash
# The state file location depends on your OS and pywebview version
# macOS
rm -rf ~/Library/Application\ Support/file-organizer/window_state*

# Linux
rm -f ~/.local/share/file-organizer/window_state*

# Windows
del %APPDATA%\file-organizer\window_state*

file-organizer desktop
```

### AI features unavailable

Make sure your provider backend is running/configured (for default local mode, start Ollama).

## Related docs

- [Web UI Guide](web-ui/index.md)
- [Settings & Profile](web-ui/settings.md)
- [Configuration Guide](CONFIGURATION.md)
