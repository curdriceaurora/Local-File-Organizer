# Building Executables (PyInstaller)

This project uses PyInstaller to package the CLI/TUI into standalone executables.
The build configuration lives in `file_organizer_v2/scripts/build_config.py` and
is consumed by both `file_organizer_v2/scripts/build.py` and
`file_organizer_v2/file_organizer.spec`.

## Prerequisites

- Python 3.9+
- A virtual environment (recommended)
- PyInstaller (via the build extra)

```bash
cd file_organizer_v2
python -m pip install -e ".[build]"
```

## Local Build

```bash
cd file_organizer_v2
python scripts/build.py --clean
```

Artifacts are written to `file_organizer_v2/dist/` and named like:

```
file-organizer-<version>-<platform>-<arch>
```

Examples:
- `file-organizer-2.0.0-alpha.1-macos-arm64`
- `file-organizer-2.0.0-alpha.1-windows-x86_64.exe`

## macOS DMG (Single-Arch)

After building the executable for your current architecture:

```bash
cd file_organizer_v2
python scripts/build.py --clean
bash scripts/build_macos.sh
```

Optional signing and notarization:

```bash
export MACOS_SIGN_IDENTITY="Developer ID Application: Your Name (TEAMID)"
export APPLE_ID="you@example.com"
export APPLE_TEAM_ID="TEAMID"
export APPLE_APP_PASSWORD="app-specific-password"
bash scripts/build_macos.sh --sign "${MACOS_SIGN_IDENTITY}" --notarize
```

## macOS Universal DMG

You need both the arm64 and x86_64 executables. Once you have them:

```bash
cd file_organizer_v2
bash scripts/build_macos.sh --universal \\
  --arm /path/to/file-organizer-<version>-macos-arm64 \\
  --x86 /path/to/file-organizer-<version>-macos-x86_64
```

## Windows Installer (Inno Setup)

Install Inno Setup 6+ and ensure `ISCC.exe` is available (default install path:
`C:\\Program Files (x86)\\Inno Setup 6\\ISCC.exe`).

```powershell
cd file_organizer_v2
python scripts/build.py --clean
.\scripts\build_windows.ps1
```

The installer is written to `file_organizer_v2/dist/` as:

```text
file-organizer-<version>-windows-setup.exe
```

## Linux AppImage

Install AppImage runtime dependencies (Ubuntu/Debian):

```bash
sudo apt-get update
sudo apt-get install -y fuse libfuse2
```

Build the executable and AppImage:

```bash
cd file_organizer_v2
python scripts/build.py --clean
bash scripts/build_linux.sh
```

Artifacts are written to `file_organizer_v2/dist/`:

```text
file-organizer-<version>-linux-<arch>.AppImage
file-organizer-<version>-linux-<arch>.tar.gz
```

## Generate Spec File Only

If you want to regenerate the spec file without running a build:

```bash
cd file_organizer_v2
python scripts/build.py --spec-only
```

## Build as One-Dir (Debug)

```bash
cd file_organizer_v2
python scripts/build.py --one-dir
```

## CI Build Pipeline

GitHub Actions builds are defined in:
- `.github/workflows/build.yml`

The CI pipeline installs dependencies, runs tests, and invokes:

```bash
python scripts/build.py --clean
```

Artifacts are uploaded per platform.

## Notes

- Ollama and model weights are **not** bundled. Users install Ollama and pull models separately.
- For macOS and Windows distribution, code signing and notarization are handled in platform tasks (#14/#16).
- AppImage packaging is handled in task #20.
