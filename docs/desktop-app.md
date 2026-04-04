# Desktop App

File Organizer ships as a standalone native desktop application powered by
[pywebview](https://pywebview.flowrl.com/). A single Python process hosts the
FastAPI web UI on a background thread and displays it in a native OS window —
no Electron, no Node, no Rust, no separate server to keep alive.

## Overview

- **Native window** — uses the OS system webview (WebKit on macOS, Edge
  WebView2 on Windows, WebKitGTK on Linux)
- **Zero port management** — binds to a random free ephemeral port at launch
- **Single process** — uvicorn HTTP daemon thread + pywebview main thread
- **Standalone executable** — ships as a PyInstaller single-file binary;
  no Python installation required on the end-user machine

## Installation

### Option A — Download a pre-built binary

Download the latest release from
[GitHub Releases](https://github.com/curdriceaurora/Local-File-Organizer/releases):

| Platform | File |
|----------|------|
| macOS (Apple Silicon) | `file-organizer-desktop-*-macos-arm64` |
| macOS (Intel) | `file-organizer-desktop-*-macos-x86_64` |
| Windows | `file-organizer-desktop-*-windows-x86_64.exe` |
| Linux (AppImage) | `file-organizer-desktop-*-x86_64.AppImage` |

Make the binary executable and run it:

```bash
# macOS / Linux
chmod +x file-organizer-desktop-*
./file-organizer-desktop-*

# Windows: double-click the .exe or run from PowerShell
.\file-organizer-desktop-*.exe
```

### Option B — Install from PyPI

```bash
pip install "local-file-organizer[desktop]"
file-organizer-desktop
```

### Option C — Install from source

```bash
git clone https://github.com/curdriceaurora/Local-File-Organizer.git
cd Local-File-Organizer
pip install -e ".[desktop]"
file-organizer-desktop
```

## Prerequisites

Before launching the desktop app:

1. **Ollama must be running** with at least one text model:

   ```bash
   ollama serve &
   ollama pull qwen2.5:3b-instruct-q4_K_M
   ```

2. **Linux only** — install WebKitGTK system packages:

   ```bash
   sudo apt-get install -y gir1.2-webkit2-4.1
   ```

## First Launch

When you run `file-organizer-desktop` for the first time:

1. The app allocates a free local port (e.g. `http://127.0.0.1:54321`).
2. The uvicorn server starts in the background (takes 1–3 seconds on first
   cold start).
3. The native window opens and loads the web UI automatically.
4. A setup wizard walks you through model and workspace configuration.

The window title bar shows **File Organizer** and is resizable down to 800 × 600.

## Configuration

The desktop app reads the same environment variables as the web UI. Set them
before launching:

| Variable | Description | Default |
|----------|-------------|---------|
| `FO_PROVIDER` | AI provider: `ollama`, `openai`, `claude` | `ollama` |
| `FO_OLLAMA_BASE_URL` | Ollama server URL | `http://localhost:11434` |
| `FO_OPENAI_API_KEY` | OpenAI-compatible API key | — |
| `FO_OPENAI_BASE_URL` | OpenAI-compatible base URL | — |
| `FO_CLAUDE_API_KEY` | Anthropic Claude API key | — |
| `FO_DATA_DIR` | Override the workspace data directory | `~/.local/share/file-organizer` |

See [Configuration Guide](CONFIGURATION.md) for the full list.

## Troubleshooting

### Blank window on launch

**Cause:** The uvicorn server is still starting up and the webview loaded before
it was ready.

**Fix:** The app polls for server readiness for up to 10 seconds before opening
the window. If you see a blank window, wait a moment and refresh (`⌘R` / `F5`).
If the window stays blank, check the terminal for startup errors.

### "pywebview is required" error

**Fix:**

```bash
pip install "local-file-organizer[desktop]"
```

### Port conflict / address already in use

The app always picks a free random port using the OS socket API. A port
conflict should not occur. If it does, restart the app — a different port
will be selected.

### Ollama not running

**Symptom:** The window opens but AI features show errors.

**Fix:** Start Ollama before launching the app:

```bash
ollama serve
```

### WebKitGTK missing on Linux

**Symptom:** `ImportError: cannot import name 'gtk'` or blank window on Linux.

**Fix:**

```bash
sudo apt-get install -y gir1.2-webkit2-4.1
```

For older Ubuntu / Debian, use `gir1.2-webkit2-4.0` if the 4.1 package is
not available.

### Window does not open on macOS

**Cause:** macOS Gatekeeper may block unsigned binaries downloaded from the
internet.

**Fix:** Right-click the binary, choose **Open**, then confirm in the dialog.
Alternatively:

```bash
xattr -dr com.apple.quarantine ./file-organizer-desktop-*
```
