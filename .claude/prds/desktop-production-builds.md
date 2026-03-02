---
name: desktop-production-builds
description: Production builds, code signing, and packaging for macOS, Windows, and Linux desktop app
status: backlog
created: 2026-03-02T14:25:52Z
updated: 2026-03-02T14:25:52Z
---

# PRD: Desktop Production Builds & Code Signing

## Problem Statement

The Desktop UI epic delivered the Tauri v2 shell with sidecar architecture, but no production builds have been verified. The app compiles in dev mode (`cargo check`, `cargo test` pass) but has never been built as a distributable package. Code signing, notarization, and platform-specific packaging remain untested.

## Goals

1. Build production `.app`/`.dmg` on macOS with code signing and notarization
2. Build production `.msi`/`.exe` on Windows with code signing
3. Build production `.deb`/`.AppImage`/Flatpak on Linux
4. Verify bundle size < 170 MB across all platforms
5. Establish CI/CD pipeline for automated release builds
6. PyInstaller sidecar binary packaging verified on all platforms

## Non-Goals

- E2E UI testing (separate epic)
- Test coverage improvements (separate epic)
- New feature development

## Success Criteria

- [ ] macOS: `.app` launches, `.dmg` installs cleanly, notarization passes
- [ ] Windows: `.msi` installs, app launches, Windows Defender doesn't flag
- [ ] Linux: `.deb` installs on Ubuntu 22.04+, Flatpak installs from manifest
- [ ] Bundle size < 170 MB on all platforms
- [ ] CI matrix builds all three platforms on push to release branch
- [ ] Sidecar binary starts and serves the API on all platforms

## Technical Approach

### Phase 1: macOS Production Build (1-2 weeks)

1. **PyInstaller sidecar build**
   - Build `file-organizer-backend` via PyInstaller `--onefile`
   - Copy to `desktop/src-tauri/binaries/file-organizer-backend-{target}`
   - Verify sidecar starts and responds to health checks

2. **Tauri production build**
   - `npm run tauri build` produces `.app` and `.dmg`
   - Code signing with Developer ID certificate
   - Notarization via `xcrun notarytool`
   - Verify entitlements.plist is applied correctly

3. **Smoke test**
   - App launches from `.dmg`
   - Splash screen → Web UI transition
   - System tray functional
   - Clean quit (sidecar shutdown)

### Phase 2: Windows Production Build (1-2 weeks)

4. **PyInstaller sidecar for Windows**
   - Cross-compile or CI build `file-organizer-backend.exe`
   - Copy to `desktop/src-tauri/binaries/file-organizer-backend-x86_64-pc-windows-msvc.exe`

5. **Tauri Windows build**
   - `npm run tauri build` produces `.msi` and `.exe`
   - Code signing with EV certificate (or self-signed for initial testing)
   - Verify `app.manifest` capabilities are applied

6. **Smoke test**
   - App installs via `.msi`
   - System tray, notifications, context menus work
   - Windows Defender scan passes

### Phase 3: Linux Production Build (1-2 weeks)

7. **PyInstaller sidecar for Linux**
   - Build on Ubuntu 22.04 runner
   - Copy to `desktop/src-tauri/binaries/file-organizer-backend-x86_64-unknown-linux-gnu`

8. **Tauri Linux build**
   - `.deb` package via Tauri bundler
   - `.AppImage` for portable distribution
   - Flatpak from existing manifest (`desktop/flatpak/`)

9. **Smoke test**
   - `.deb` installs on Ubuntu 22.04
   - Flatpak installs and runs
   - Context menus registered (Nautilus/Dolphin)

### Phase 4: CI/CD Release Pipeline (1 week)

10. **GitHub Actions matrix**
    - macOS (arm64 + x86_64), Windows (x86_64), Linux (x86_64)
    - PyInstaller sidecar build → Tauri build → artifact upload
    - Code signing secrets in GitHub repository secrets
    - Release draft creation on tag push

## Estimated Effort

- **Total**: 5-7 weeks
- **macOS**: 1-2 weeks
- **Windows**: 1-2 weeks
- **Linux**: 1-2 weeks
- **CI/CD**: 1 week

## Dependencies

- Apple Developer ID certificate (macOS code signing)
- Windows EV certificate or equivalent (Windows code signing)
- GitHub Actions runners with platform access
- PyInstaller working on all three platforms

## Risks

- PyInstaller binary size may push bundle over 170 MB target
- Code signing certificates require paid developer accounts
- Cross-platform CI may have runner availability issues
