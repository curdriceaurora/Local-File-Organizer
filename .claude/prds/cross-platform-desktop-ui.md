---
name: cross-platform-desktop-ui
description: Cross-Platform Desktop UI & Packaging Strategy using Tauri v2
status: in-progress
created: 2026-03-02T03:55:10Z
updated: 2026-03-02T03:55:10Z
---

# Cross-Platform Desktop UI & Packaging Strategy

## Context

File Organizer v2.0 is a Python-based AI-powered file management tool (~78,800 LOC, 314 modules) with four existing interfaces: CLI (Typer), TUI (Textual), Web UI (FastAPI + Jinja2 + HTMX), and REST API (FastAPI). All UIs directly couple to `FileOrganizer` core with no service facade. The project currently ships via PyInstaller with platform-specific packaging scripts (macOS .dmg, Windows Inno Setup .exe, Linux AppImage) but lacks native OS integration (no system tray, no context menus, no daemon management via launchd/systemd/Windows Service).

**Goal**: Ship native desktop binaries on macOS (arm64 + x86_64), Windows (x86_64 + arm64), and Linux (x86_64 + arm64) with proper packaging, code signing, permissions, and native OS integration.

## Strategy: Hybrid (Tauri v2 Shell + Existing Web UI)

**Tauri v2** uses system webview (0 MB added), shell adds only ~5-10 MB, existing Web UI works as-is inside webview, first-class system tray/notifications/dialogs/updater, sidecar plugin manages PyInstaller backend.

## Phases

### Phase 1: Service Facade + Config Consolidation (1-2 weeks)
- Create `services/facade.py` wrapping `FileOrganizer` + key services
- Fix hardcoded config paths to use `PathManager`
- Ensure `/api/v1/health` endpoint is reliable

### Phase 2: Tauri Shell Scaffold (2-3 weeks)
- Initialize Tauri v2 project at `desktop/`
- Configure sidecar process management
- Splash screen, basic system tray, native file dialogs
- Verify Web UI in webview on macOS

### Phase 3: Cross-Platform Builds + Packaging (2-3 weeks)
- Sidecar-named binaries, platform build scripts
- CI/CD with Rust toolchain, app icons
- entitlements.plist, Windows app.manifest

### Phase 4: Native OS Integration (3-4 weeks)
- Full system tray menu
- Daemon manager (launchd/systemd/Windows Service)
- Context menus (Finder/Explorer/Nautilus)
- Native notifications, auto-launch

### Phase 5: Update System Integration (1-2 weeks)
- tauri-plugin-updater + existing UpdateInstaller coordination
- In-app update banner via WebSocket

### Phase 6: Additional Linux Packaging (1-2 weeks)
- Flatpak manifest
- Debian packaging (.deb)
- CI matrix additions

## Bundle Size Estimate
- Python backend (PyInstaller): ~100-150 MB
- Tauri shell: ~5-10 MB
- System webview: 0 MB
- **Total: ~110-165 MB** (vs Electron ~250-350 MB)

## Key Risks
- WebView2 missing on older Windows 10 (mitigated: Tauri bundles bootstrapper)
- WebKitGTK version variance on Linux (mitigated: AppImage/Flatpak bundles it)
- Python sidecar startup latency (mitigated: splash screen + daemon pre-warm)
- Rust learning curve (mitigated: small shell ~500-1000 LOC)
