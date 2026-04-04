---
name: desktop-production-builds
description: Production builds, code signing, and packaging for macOS, Windows, and Linux desktop app
status: in-progress
created: 2026-03-02T14:25:52Z
updated: 2026-04-04T00:00:00Z
---

# PRD: Desktop Production Builds & Code Signing

## Problem Statement

The pywebview desktop app compiles and runs in development but production builds —
code signing, notarization, and installer verification — have not been validated
on all platforms.

## Goals

1. Build production `.app`/`.dmg` on macOS with code signing and notarization
2. Build production `.exe` on Windows
3. Build production `.AppImage` on Linux
4. Verify bundle size < 170 MB across all platforms
5. Establish CI/CD pipeline for automated release builds

## Non-Goals

- E2E UI testing (separate epic)
- Test coverage improvements (separate epic)
- New feature development

## Success Criteria

- [ ] macOS: `.app` launches, `.dmg` installs cleanly, notarization passes Apple
- [ ] Windows: `.exe` installs, app launches, Windows Defender does not flag
- [ ] Linux: `.AppImage` runs on Ubuntu 22.04+
- [ ] Bundle size < 170 MB on all platforms
- [ ] CI matrix builds all three platforms on push to release branch
- [ ] Desktop binary starts, opens window, and serves the API on all platforms

## Technical Approach

### Phase 1: Build Pipeline (completed)

- `python scripts/build.py --desktop` produces `file-organizer-desktop-{version}-{platform}-{arch}`
- `DesktopBuildConfig` in `scripts/build_config.py`:
  - Entry point: `src/file_organizer/desktop/app.py`
  - `--windowed` (no console window)
  - Platform-conditional webview backend imports (cocoa / gtk / edgechromium)
  - Spec file: `file_organizer_desktop.spec`
- `.github/workflows/build.yml` matrix: macOS arm64/x86_64, Linux x86_64, Windows x86_64

### Phase 2: macOS Code Signing & Notarization

1. Build via `python scripts/build.py --desktop --clean`
2. Code signing with Developer ID certificate
3. Notarization via `xcrun notarytool` using `desktop/build/entitlements.plist`
4. Verify app launches from `.dmg`

### Phase 3: Windows Packaging

1. `python scripts/build.py --desktop --clean` produces `.exe`
2. Inno Setup installer wraps the executable (`scripts/build_windows.iss`)
3. Windows Defender scan

### Phase 4: Linux AppImage

1. `scripts/build_linux.sh` detects `file-organizer-desktop-*` binary
2. `.desktop` file generated with `Terminal=false`
3. AppImage bundled via `appimagetool`

## Estimated Effort

- **Total**: 3–5 weeks
- **macOS signing**: 1–2 weeks
- **Windows packaging**: 1 week
- **Linux AppImage**: 1 week
- **CI verification**: 1 week

## Dependencies

- Apple Developer ID certificate (macOS code signing)
- GitHub Actions macOS / Windows / Linux runners
- PyInstaller 6.x

## Risks

- PyInstaller binary size may push bundle over 170 MB target
- Code signing certificates require paid developer accounts
