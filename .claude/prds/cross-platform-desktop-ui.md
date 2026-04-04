---
name: cross-platform-desktop-ui
description: Cross-Platform Desktop UI & Packaging Strategy using pywebview
status: completed
created: 2026-03-02T03:55:10Z
updated: 2026-04-04T00:00:00Z
---

# Cross-Platform Desktop UI & Packaging Strategy

## Context

File Organizer v2.0 is a Python-based AI-powered file management tool (~78,800 LOC, 314 modules)
with four existing interfaces: CLI (Typer), TUI (Textual), Web UI (FastAPI + Jinja2 + HTMX), and
REST API (FastAPI). The project ships native desktop binaries on macOS (arm64 + x86_64), Windows
(x86_64), and Linux (x86_64) using a pure-Python pywebview approach.

**Goal**: Ship native desktop binaries with a single-process Python architecture — no Rust,
no Node, no Electron.

## Strategy: pywebview (single Python process)

A single `file-organizer-desktop` process:

1. Allocates a free ephemeral port via `socket`
2. Starts uvicorn (serving the existing FastAPI web UI) in a daemon thread
3. Polls for TCP readiness (50 ms intervals, 10 s timeout)
4. Opens a native OS window via `webview.create_window()` + `webview.start()`
5. Exits cleanly when the window closes (daemon thread tears down automatically)

**Platform webview backends:**

| Platform | Backend |
|----------|---------|
| macOS | WebKit (`webview.platforms.cocoa`) |
| Linux | WebKitGTK (`webview.platforms.gtk`) |
| Windows | Edge WebView2 (`webview.platforms.edgechromium`) |

## Implementation

### Completed

- `src/file_organizer/desktop/app.py` — `launch()` entry point
- `scripts/build_config.py` — `DesktopBuildConfig`, `DESKTOP_HIDDEN_IMPORTS`
- `scripts/build.py` — `--desktop` flag, `file_organizer_desktop.spec`
- `.github/workflows/build.yml` — pywebview-only CI pipeline
- `scripts/build_linux.sh` — AppImage packaging for desktop binary
- `desktop/build/entitlements.plist` — macOS code-signing entitlements

### Bundle Size Estimate

- Python backend (PyInstaller): ~100–150 MB
- pywebview: ~5 MB
- System webview: 0 MB (uses OS built-in)
- **Total: ~105–155 MB** (vs Electron ~250–350 MB)

## Key Design Decisions

- `webview.start()` **must** be called from the main thread (OS requirement on macOS and Windows).
  The uvicorn server runs in a daemon background thread.
- Port is allocated by binding to port 0 and immediately releasing; no TOCTOU issue under
  normal single-user desktop conditions.
- No system tray, no daemon manager in v1. These are deferred to a future epic.

## Future Work

- System tray integration (show/hide window, quit)
- Auto-launch on login (launchd/systemd/Windows Task Scheduler)
- Context-menu integration (Finder/Explorer/Nautilus)
- In-app auto-update banner
