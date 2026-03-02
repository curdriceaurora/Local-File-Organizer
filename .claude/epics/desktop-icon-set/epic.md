---
name: desktop-icon-set
status: backlog
created: 2026-03-02T14:30:36Z
updated: 2026-03-02T14:30:36Z
progress: 0%
prd: .claude/prds/desktop-icon-set.md
github: Will be updated when synced to GitHub
---

# Epic: Desktop Icon Set & Build Integration

## Overview

Complete the application icon set, integrate icon generation into build workflows, and add CI validation. The icon artwork already exists (folder-with-arrow design in `desktop/icons/`) — this epic ensures all required sizes and formats are generated, validated, and properly integrated into the Tauri build pipeline across all platforms.

## Architecture Decisions

- **Single source of truth**: `desktop/icons/` holds master icons; `desktop/src-tauri/icons/` is a build artifact populated during build
- **Procedural generation**: Extend existing `scripts/generate_icons.py` rather than maintain hand-crafted assets
- **Validation script**: New `scripts/validate_icons.py` checks presence, format, dimensions, and color type
- **Build hook integration**: Icon copy/validation runs as a Tauri pre-build step (`beforeBuildCommand` in `tauri.conf.json`)

## Technical Approach

### Icon Set Completion

- Update `scripts/generate_icons.py` to produce all required sizes:
  - Standard: 16, 32, 48, 64, 128, 256, 512 px
  - HiDPI (macOS): 32@2x (64px), 128@2x (256px), 256@2x (512px)
  - Windows ICO: embed 16, 32, 48, 64, 256 sizes
  - macOS ICNS: proper type entries via `iconutil`
- Single `python scripts/generate_icons.py` invocation produces everything

### Build Integration

- Add npm script or Tauri `beforeBuildCommand` that copies `desktop/icons/*` → `desktop/src-tauri/icons/`
- Update `tauri.conf.json` icon list to include all sizes
- Update Linux `.desktop` file icon path
- Update Flatpak manifest icon references

### CI Validation

- `scripts/validate_icons.py`: checks each icon file for existence, valid header, correct dimensions, RGBA color type
- Runs in CI before `tauri build`
- Optional integration into `pre-commit-validation.sh`

## Task Breakdown Preview

- [ ] Task 1: Extend `generate_icons.py` with missing sizes and HiDPI variants
- [ ] Task 2: Create `validate_icons.py` for format/dimension/color type validation
- [ ] Task 3: Integrate icon copy + validation into Tauri build pipeline
- [ ] Task 4: Update Linux `.desktop` and Flatpak manifest icon paths
- [ ] Task 5: Add icon validation to CI workflow

## Dependencies

- Python Pillow library (already a project dependency)
- `iconutil` on macOS for ICNS generation (fallback to PNG if unavailable)
- Tauri project structure (completed in Desktop UI epic)

## Success Criteria (Technical)

- `python scripts/generate_icons.py` produces all 10+ icon files in one run
- `python scripts/validate_icons.py` exits 0 when all icons are valid
- `tauri build` automatically gets correct icons without manual copying
- CI fails if icons are missing or malformed
- macOS Retina displays show crisp HiDPI icons
- Linux AppImage/Flatpak/`.deb` include correct icon at all standard sizes

## Estimated Effort

- **Total**: 1-2 weeks
- **Icon generation script**: 2-3 days
- **Validation script**: 1-2 days
- **Build integration**: 2-3 days
- **CI integration**: 1 day
