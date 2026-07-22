# Desktop App

The desktop app runs the web UI in a native window. It uses **pywebview**.

## Launch commands

Use these commands:

```bash
file-organizer desktop
# or
fo desktop
```

Use this script for compatibility:

```bash
file-organizer-desktop
```

## Quick workflow: launch, configure, and verify

```bash
# 1) Install desktop dependencies
pip install -e ".[desktop]"

# 2) Launch desktop mode
file-organizer desktop

# 3) Adjust the window
file-organizer desktop --title "File Organizer" --width 1280 --height 820
```

Verify navigation from Home to Organize to Settings in the desktop window.
Read the [Web UI Guide](web-ui/index.md) for UI behavior details.

## Runtime model

When you start the app, it does these steps:

1. It finds a free local port.
2. It starts the FastAPI app on `127.0.0.1:<port>` in a background thread.
3. It waits for the server.
4. It opens a native window to the local UI.

The Desktop application does not implement a second organization workflow.
It loads the same `/ui/organize` routes, canonical option mapping, reviewed
plans, jobs, and results as a browser. Its only additions are native directory,
file, and save dialogs plus reveal-in-file-manager behavior; those affordances
select or display paths and do not alter organization semantics.

## Install

```bash
pip install "local-file-organizer[desktop]"
```

Install from source:

```bash
pip install -e ".[desktop]"
```

## JavaScript bridge

Templates must use the helpers from `desktop_api.js`:

- `window.desktopBrowseFile(inputId, fileTypes)`
- `window.desktopBrowseDirectory(inputId)`
- `window.desktopSaveFile(suggestedName, fileTypes)`
- `window.desktopOpenPath(path)`

These helpers wrap the `window.pywebview.api.*` methods. They add fallbacks for standard browsers. Thus, templates operate in desktop and browser contexts. In desktop mode, pywebview exposes `browse_directory()`, `browse_file(fileTypes)`, `save_file(suggestedName, fileTypes)`, and `open_path(path)`.

## Troubleshooting

### Import error

Install the desktop extra:

```bash
pip install "local-file-organizer[desktop]"
```

### Blank or slow window

The launcher waits for the backend. Cold starts can be slow. Read the terminal output for server errors. If the window stays blank for more than 30 seconds:

```bash
# Run with verbose output to read the backend log
file-organizer desktop --verbose
```

### Backend startup failure

**Problem**: The native window does not open. The terminal shows an error.

**Cause**: The FastAPI server failed to start. Possible causes are a port conflict, a missing dependency, or Ollama is offline.

**Solution**:

```bash
# Run the web server to read the error
file-organizer serve --verbose

# Start Ollama if AI features fail
ollama serve

# Check environment variables for other providers
file-organizer config show
```

Read [AI Provider Issues](troubleshooting.md#ai-provider-issues) to find provider-specific solutions.

### Linux WebKit packages

Install the necessary WebKitGTK packages:

```bash
sudo apt-get install -y libgirepository1.0-dev gir1.2-webkit2-4.1
```

### Native file picker does not show

**Problem**: You click a browse button. The app opens a standard HTML input. It does not open the native OS file picker.

**Cause**: The system injects the `window.pywebview.api` bridge only in desktop mode. If pywebview is incomplete, the bridge uses a browser fallback.

**Solution**:

- Start the app with `file-organizer desktop`. Do not use `file-organizer serve`.
- On Linux, install the WebKitGTK packages.
- Restart the desktop app. The bridge loads during window load.

### Window position or size is incorrect

**Problem**: The desktop window opens off-screen or is too small.

**Cause**: pywebview restores the last saved window position.

**Solution**:

Close the app. Delete the window state file. Start the app again:

```bash
# macOS
rm -rf ~/Library/Application\ Support/file-organizer/window_state*

# Linux
rm -f ~/.local/share/file-organizer/window_state*

# Windows
del %APPDATA%\file-organizer\window_state*

file-organizer desktop
```

### AI features are not available

Start your provider backend. For local mode, start Ollama.

## Related docs

- [Web UI Guide](web-ui/index.md)
- [Settings & Profile](web-ui/settings.md)
- [Configuration Guide](CONFIGURATION.md)
