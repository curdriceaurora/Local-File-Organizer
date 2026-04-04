# File Organizer Desktop

Native desktop application for File Organizer, built with [pywebview](https://pywebview.flowrl.com/).

## Overview

The `desktop/` directory contains icons, build assets, and the pywebview launcher
(`src/file_organizer/desktop/app.py`). The desktop app is a single Python process:
a uvicorn HTTP daemon thread serves the FastAPI web UI, and a pywebview native OS
window displays it. No Rust, no Node, no separate sidecar binary.

## Architecture

```text
desktop/
├── icons/              # App icons (PNG, ICO, ICNS)
├── build/              # Code-signing assets
│   ├── entitlements.plist              # macOS production entitlements
│   └── macos-entitlements-debug.plist  # macOS debug entitlements
├── context-menus/      # OS context-menu integration scripts
└── README.md           # This file

src/file_organizer/desktop/
└── app.py              # pywebview launcher (launch() entry point)
```

### How It Works

```text
main thread                       daemon thread
-----------                       -------------
launch()
  ├── _find_free_port()
  ├── threading.Thread(target=_run_server, daemon=True).start()
  │                                 _run_server()
  │                                   uvicorn.run(app, host="127.0.0.1", port=N)
  ├── _wait_for_server(port)  ←── polls TCP every 50 ms, up to 10 s
  ├── webview.create_window(url=f"http://127.0.0.1:{port}")
  └── webview.start()         ←── blocks until window closed; OS requirement
```

The server thread is a daemon so it is torn down automatically when
`webview.start()` returns (i.e. when the user closes the window).

## Window Configuration

| Setting | Value |
|---------|-------|
| Default title | `File Organizer` |
| Default size | 1280 × 800 (resizable) |
| Minimum size | 800 × 600 |
| Server address | `http://127.0.0.1:<ephemeral port>` |
| Server ready timeout | 10 seconds |

## Prerequisites

- Python 3.11 or higher
- [Ollama](https://ollama.com/) installed and running
- `pip install -e ".[desktop,dev]"`

### Platform system dependencies (development)

**Linux:**

```bash
sudo apt-get install -y \
    libgirepository1.0-dev libcairo2-dev gir1.2-webkit2-4.1
```

**macOS / Windows:** No extra system packages required; pywebview uses the OS
native webview (WebKit on macOS, Edge WebView2 on Windows).

## Development

```bash
# Install from source with desktop extras
pip install -e ".[desktop,dev]"

# Ensure Ollama is running with at least one model
ollama serve &
ollama pull qwen2.5:3b-instruct-q4_K_M

# Launch the desktop window
file-organizer-desktop
```

The window opens at the web UI served on a random ephemeral port. No port
conflicts, no fixed port to manage.

## Building a Standalone Executable

```bash
# Install PyInstaller
pip install pyinstaller

# Generate spec and build (windowed, single-file)
python scripts/build.py --desktop --clean

# Output lands in dist/
ls dist/file-organizer-desktop-*
```

The `--desktop` flag selects `DesktopBuildConfig`:

- Entry point: `src/file_organizer/desktop/app.py`
- `--windowed` (no console window)
- Spec file: `file_organizer_desktop.spec`
- Output name: `file-organizer-desktop-{version}-{platform}-{arch}`

For CI-style builds see `.github/workflows/build.yml`.

## macOS Entitlements

`desktop/build/entitlements.plist` grants two entitlements required at
production code-signing time:

- `com.apple.security.cs.allow-unsigned-executable-memory` — required for
  PyInstaller's code injection and Ollama's Metal/GPU JIT compilation
- `com.apple.security.network.client` — allows outbound connections to the
  local Ollama server

The debug variant (`macos-entitlements-debug.plist`) additionally grants
`com.apple.security.get-task-allow` for the Xcode debugger.
