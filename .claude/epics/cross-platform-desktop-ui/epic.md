---
name: cross-platform-desktop-ui
status: completed
created: 2026-03-02T03:55:10Z
updated: 2026-03-02T14:12:19Z
prd: cross-platform-desktop-ui
github: https://github.com/curdriceaurora/Local-File-Organizer/issues/537
progress: 100%
---

# Epic: Cross-Platform Desktop UI & Packaging

## Overview

Ship native desktop binaries on macOS, Windows, and Linux using Tauri v2 as a lightweight shell around the existing Web UI, with native OS integration (system tray, context menus, daemon management), proper packaging, and code signing.

## Architecture

Tauri v2 shell (Rust, ~5-10 MB) wraps the existing Web UI (Jinja2 + HTMX) in a native webview. The Python backend runs as a PyInstaller sidecar managed by the Tauri sidecar plugin. Communication is via HTTP localhost.

## Phases

### Phase 1: Service Facade + Config Consolidation (1-2 weeks)

- Create `services/facade.py` wrapping `FileOrganizer` + key services
- Fix hardcoded config paths to use `PathManager`
- Ensure `/api/v1/health` endpoint is reliable

### Phase 2: Tauri Shell Scaffold (2-3 weeks)

- Initialize Tauri v2 project at `desktop/`
- Configure sidecar: spawn PyInstaller backend, webview points to localhost
- Splash screen, basic system tray, native file dialogs
- Verify Web UI in webview on macOS

### Phase 3: Cross-Platform Builds + Packaging (2-3 weeks)

- Sidecar-named binaries, platform build scripts
- CI/CD with Rust toolchain, app icons
- entitlements.plist, Windows app.manifest

### Phase 4: Native OS Integration (3-4 weeks)

- Full system tray menu (Organize Now, Recent Activity, Pause/Resume, Settings)
- Daemon manager (launchd/systemd/Windows Service)
- Context menus (Finder Sync Extension, Windows Shell Extension, Linux scripts)
- Native notifications, auto-launch on login

### Phase 5: Update System Integration (1-2 weeks)

- tauri-plugin-updater + existing UpdateInstaller coordination
- In-app update banner via WebSocket

### Phase 6: Additional Linux Packaging (1-2 weeks)

- Flatpak manifest with permissions
- Debian packaging (.deb)
- CI matrix additions

## Success Criteria

- Native desktop app launches on macOS, Windows, Linux
- Existing Web UI works identically in webview
- System tray with full menu functionality
- Context menus registered on all platforms
- Auto-update works for both shell and sidecar
- Bundle size < 170 MB (vs Electron ~300 MB)
- All existing tests continue to pass
- New tests cover all new code at >= 74% coverage

## Estimated Effort

- Total: 11-16 weeks across 6 phases
- Many tasks within each phase can run in parallel

## Tasks Created

### Phase 1: Service Facade + Config Consolidation

- [x] #542 - Create Service Facade (parallel: true)
- [x] #554 - Fix Config Path Consistency (parallel: true)
- [x] #558 - Harden Health Endpoint (depends: #542)

### Phase 2: Tauri Shell Scaffold

- [x] #559 - Initialize Tauri v2 Project (parallel: true)
- [x] #560 - Implement Sidecar Process Manager (depends: #558, #559)
- [x] #540 - Implement Splash Screen (depends: #560)
- [x] #544 - Implement Basic System Tray (depends: #559)

### Phase 3: Cross-Platform Builds + Packaging

- [x] #546 - Web UI Viewport Adjustments (parallel: true)
- [x] #548 - Rename PyInstaller Output to Sidecar Convention (parallel: true)
- [x] #549 - Generate App Icons (parallel: true)
- [x] #538 - Create macOS Entitlements and Code Signing (depends: #559, #548)
- [x] #541 - Create Windows Manifest and Build Configuration (depends: #559, #548)
- [x] #547 - Update CI/CD Pipeline for Tauri Builds (depends: #548, #538, #541)

### Phase 4: Native OS Integration

- [x] #552 - Full System Tray Menu (depends: #560, #544)
- [x] #556 - Implement Daemon Manager - macOS (depends: #559)
- [x] #539 - Implement Daemon Manager - Linux (depends: #559)
- [x] #545 - Implement Daemon Manager - Windows (depends: #559)
- [x] #551 - Context Menus - macOS Finder Extension (depends: #560)
- [x] #555 - Context Menus - Linux (Nautilus/Dolphin) (depends: #560)
- [x] #557 - Native Notifications (depends: #560)

### Phase 5: Update System Integration

- [x] #543 - Coordinated Update System (depends: #560, #547)

### Phase 6: Additional Linux Packaging

- [x] #550 - Flatpak Packaging (depends: #547)
- [x] #553 - Debian Packaging (depends: #547)

**Total tasks**: 23
**Parallel tasks**: 18
**Sequential tasks**: 5
**Estimated total effort**: 155-196 hours (~4-5 developer-months)
