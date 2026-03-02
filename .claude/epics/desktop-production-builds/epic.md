---
name: desktop-production-builds
status: backlog
created: 2026-03-02T14:30:36Z
updated: 2026-03-02T14:30:36Z
progress: 0%
prd: .claude/prds/desktop-production-builds.md
github: Will be updated when synced to GitHub
---

# Epic: Desktop Production Builds & Code Signing

## Overview

Ship distributable desktop binaries for macOS, Windows, and Linux. This covers the full build pipeline: PyInstaller sidecar packaging, Tauri production build, platform-specific code signing/notarization, and CI/CD automation. The Tauri v2 shell and sidecar architecture already exist from the Desktop UI epic — this epic focuses exclusively on making them production-ready.

## Architecture Decisions

- **PyInstaller `--onefile`** for sidecar binary — single executable, simplest distribution
- **Tauri bundler** for platform packages — `.dmg`/`.app` (macOS), `.msi` (Windows), `.deb`/`.AppImage`/`.rpm` (Linux)
- **Flatpak built separately** via `flatpak-builder` using an existing manifest (not produced by Tauri bundler)
- **GitHub Actions matrix** for CI — native runners per platform, no cross-compilation for sidecar
- **Code signing via CI secrets** — certificates stored as GitHub encrypted secrets, applied during build
- **Existing build scripts** (`scripts/build_macos.sh`, `scripts/build_windows.ps1`, `scripts/build_linux.sh`) will be extended rather than rewritten

## Technical Approach

### Sidecar Packaging

- PyInstaller builds the Python backend as a standalone binary per platform
- Binary is named `file-organizer-backend-{target_triple}` (Tauri sidecar convention)
- Placed in `desktop/src-tauri/binaries/` before `tauri build`
- Health check verification after build ensures sidecar is functional

### Platform Builds

- **macOS**: `tauri build` → `.app` + `.dmg`, then `codesign` + `xcrun notarytool` for notarization
- **Windows**: `tauri build` → `.msi` + `.exe`, then `signtool` for Authenticode signing
- **Linux**: `tauri build` → `.deb` + `.AppImage`, plus Flatpak from existing manifest

### CI/CD Pipeline

- GitHub Actions workflow triggered on release tags
- Matrix: macOS (arm64, x86_64), Windows (x86_64), Linux (x86_64)
- Steps: install deps → PyInstaller sidecar → `tauri build` → sign → upload artifacts → draft release

## Task Breakdown Preview

- [ ] Task 1: macOS sidecar build + Tauri production build + smoke test
- [ ] Task 2: macOS code signing and notarization
- [ ] Task 3: Windows sidecar build + Tauri production build + smoke test
- [ ] Task 4: Windows code signing (Authenticode)
- [ ] Task 5: Linux sidecar build + `.deb` + `.AppImage` + Flatpak
- [ ] Task 6: CI/CD release pipeline (GitHub Actions matrix)
- [ ] Task 7: Bundle size optimization and verification (< 170 MB)

## Dependencies

- Apple Developer ID certificate (macOS code signing)
- Windows EV or OV certificate (Authenticode signing)
- GitHub Actions runners: `macos-latest`, `windows-latest`, `ubuntu-22.04`
- Existing Tauri project at `desktop/` (completed in Desktop UI epic)
- Existing build scripts at `scripts/build_*.sh`

## Success Criteria (Technical)

- `tauri build` succeeds on all three platforms
- Sidecar binary starts and responds to `/api/v1/health` on all platforms
- Code signing passes on macOS (notarization) and Windows (SmartScreen)
- Bundle size < 170 MB per platform
- CI builds complete in < 30 minutes per platform
- Release artifacts uploaded to GitHub Releases

## Estimated Effort

- **Total**: 5-7 weeks
- **macOS builds + signing**: 1-2 weeks
- **Windows builds + signing**: 1-2 weeks
- **Linux builds + packaging**: 1-2 weeks
- **CI/CD pipeline**: 1 week
- **Critical path**: Platform builds can run in parallel; CI/CD depends on all three
