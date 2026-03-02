---
name: desktop-icon-set
description: Complete standalone icon set, integrate into build workflows, and add validation
status: backlog
created: 2026-03-02T14:30:36Z
updated: 2026-03-02T14:30:36Z
---

# PRD: Desktop Icon Set & Build Integration

## Problem Statement

The project has a procedurally-generated icon set at `desktop/icons/` (7 files) created by `scripts/generate_icons.py`. However:

1. **Incomplete duplication**: `desktop/src-tauri/icons/` is missing `icon.png` (512x512 master) and `icon_64x64.png` that exist in `desktop/icons/`
2. **No CI validation**: Nothing verifies icons are present, valid RGBA PNGs, correct dimensions, or proper ICO/ICNS format before builds
3. **No high-DPI variants**: Missing `@2x` HiDPI icons for macOS Retina displays (icon_32x32@2x.png, icon_128x128@2x.png)
4. **Linux desktop integration**: Only an SVG fallback placeholder exists for Linux; proper `.desktop` file icon paths and XDG icon theme integration are incomplete
5. **Build script gaps**: `scripts/generate_icons.py` exists but isn't integrated into the Tauri build pipeline or CI

## Goals

1. Complete the icon set with all required sizes and HiDPI variants
2. Integrate icon generation/validation into build workflows
3. Add CI validation to catch missing or malformed icons before builds
4. Ensure proper icon paths for all platforms (macOS, Windows, Linux)
5. Single source of truth: `desktop/icons/` as master, copy to `src-tauri/icons/` during build

## Non-Goals

- Redesigning the icon artwork (current folder-with-arrow design is final)
- Animated icons or dynamic tray icons
- Favicon for web UI (separate concern)

## Success Criteria

- [ ] All Tauri-required icons present and valid in `desktop/src-tauri/icons/`
- [ ] HiDPI variants generated for macOS (@2x sizes)
- [ ] `scripts/generate_icons.py` produces all required formats in one run
- [ ] CI step validates icon presence, format, dimensions before `tauri build`
- [ ] Linux `.desktop` file references correct icon path
- [ ] Build pipeline copies icons from `desktop/icons/` to `desktop/src-tauri/icons/` automatically
- [ ] Icon validation integrated into pre-commit or build script

## Technical Approach

### Phase 1: Complete the Icon Set
- Add missing sizes to `generate_icons.py`: `icon_16x16.png`, `icon_48x48.png`, `icon_512x512.png`
- Add HiDPI: `icon_32x32@2x.png` (64px), `icon_128x128@2x.png` (256px), `icon_256x256@2x.png` (512px)
- Regenerate all icons with updated script
- Validate ICO contains all required embedded sizes (16, 32, 48, 64, 256)
- Validate ICNS contains proper type entries

### Phase 2: Build Workflow Integration
- Add `copy-icons` step to Tauri build (pre-build hook or npm script)
- Update `tauri.conf.json` to reference all icon sizes
- Update Linux `.desktop` file and Flatpak manifest icon paths
- Integrate `generate_icons.py` into `scripts/build_*.sh` scripts

### Phase 3: CI Validation
- Add icon validation script (`scripts/validate_icons.py`)
- Verify: file exists, is valid PNG/ICO/ICNS, correct dimensions, RGBA color type
- Run in CI before `tauri build` step
- Optional: add to `pre-commit-validation.sh`

## Estimated Effort

- **Total**: 1-2 weeks
- **Icon set completion**: 2-3 days
- **Build integration**: 2-3 days
- **CI validation**: 1-2 days
