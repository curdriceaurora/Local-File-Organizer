#!/usr/bin/env bash
# build_linux.sh — Create Linux AppImage from PyInstaller output.
#
# Usage:
#   bash scripts/build_linux.sh
#
# Requires:
#   - PyInstaller build output in dist/
#   - appimagetool (downloaded automatically if missing)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
export PROJECT_ROOT
DIST_DIR="${PROJECT_ROOT}/dist"
BUILD_DIR="${PROJECT_ROOT}/build"
APP_NAME="file-organizer"
VERSION="$(python3 - <<'PY'
import os
import re
from pathlib import Path

root = Path(os.environ.get("PROJECT_ROOT", ".")) / "pyproject.toml"
text = root.read_text(encoding="utf-8")
match = re.search(r'(?m)^version\\s*=\\s*\"([^\"]+)\"', text)
print(match.group(1) if match else "0.0.0")
PY
)"
ARCH="$(uname -m | tr '[:upper:]' '[:lower:]')"
APPIMAGE_ARCH=""

if [[ "$ARCH" == "arm64" || "$ARCH" == "aarch64" ]]; then
    ARCH="arm64"
    APPIMAGE_ARCH="aarch64"
elif [[ "$ARCH" == "x86_64" || "$ARCH" == "amd64" ]]; then
    ARCH="x86_64"
    APPIMAGE_ARCH="x86_64"
else
    APPIMAGE_ARCH="$ARCH"
fi

APPIMAGE_NAME="${APP_NAME}-${VERSION}-linux-${ARCH}"

# ---------------------------------------------------------------------------
# Ensure PyInstaller output exists
# ---------------------------------------------------------------------------
echo "==> Checking for PyInstaller output..."
EXECUTABLE=$(find "${DIST_DIR}" -maxdepth 1 -name "file-organizer-*" -not -name "*.dmg" -not -name "*.exe" -not -name "*.AppImage" -not -name "*.sha256" -type f 2>/dev/null | head -1)

if [[ -z "$EXECUTABLE" ]]; then
    echo "ERROR: No executable found in ${DIST_DIR}/"
    echo "Run 'python scripts/build.py' first."
    exit 1
fi

echo "    Found: ${EXECUTABLE}"

# ---------------------------------------------------------------------------
# Download appimagetool if needed
# ---------------------------------------------------------------------------
APPIMAGETOOL="${BUILD_DIR}/appimagetool-${APPIMAGE_ARCH}"
TOOL_URL=""

if [[ "${APPIMAGE_ARCH}" == "x86_64" ]]; then
    TOOL_URL="https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"
elif [[ "${APPIMAGE_ARCH}" == "aarch64" ]]; then
    TOOL_URL="https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-aarch64.AppImage"
fi

if [[ ! -x "$APPIMAGETOOL" ]]; then
    if [[ -z "${TOOL_URL}" ]]; then
        echo "    WARNING: No appimagetool available for ${APPIMAGE_ARCH}. Will create tarball instead."
        APPIMAGETOOL=""
    else
        echo "==> Downloading appimagetool..."
        mkdir -p "${BUILD_DIR}"
        curl -fsSL -o "${APPIMAGETOOL}" "${TOOL_URL}" || {
            echo "    WARNING: Could not download appimagetool. Will create tarball instead."
            APPIMAGETOOL=""
        }
        if [[ -n "$APPIMAGETOOL" ]]; then
            chmod +x "${APPIMAGETOOL}"
            echo "    Downloaded: ${APPIMAGETOOL}"
        fi
    fi
fi

# ---------------------------------------------------------------------------
# Create AppDir structure
# ---------------------------------------------------------------------------
echo "==> Creating AppDir..."

APPDIR="${BUILD_DIR}/${APP_NAME}.AppDir"
rm -rf "${APPDIR}"
mkdir -p "${APPDIR}/usr/bin"
mkdir -p "${APPDIR}/usr/share/applications"
mkdir -p "${APPDIR}/usr/share/icons/hicolor/256x256/apps"

# Copy executable
cp "${EXECUTABLE}" "${APPDIR}/usr/bin/file-organizer"
chmod +x "${APPDIR}/usr/bin/file-organizer"

# Create .desktop file
cat > "${APPDIR}/usr/share/applications/${APP_NAME}.desktop" << DESKTOP
[Desktop Entry]
Type=Application
Name=File Organizer
Comment=AI-powered local file management
Exec=file-organizer
Icon=file-organizer
Categories=Utility;FileManager;
Terminal=true
DESKTOP

# Copy desktop file to root (required by AppImage spec)
cp "${APPDIR}/usr/share/applications/${APP_NAME}.desktop" "${APPDIR}/"

# Create a simple icon (SVG placeholder)
cat > "${APPDIR}/usr/share/icons/hicolor/256x256/apps/file-organizer.svg" << 'SVG'
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256">
  <rect width="256" height="256" rx="32" fill="#4A90D9"/>
  <text x="128" y="160" text-anchor="middle" fill="white"
        font-family="sans-serif" font-size="120" font-weight="bold">FO</text>
</svg>
SVG
cp "${APPDIR}/usr/share/icons/hicolor/256x256/apps/file-organizer.svg" "${APPDIR}/file-organizer.svg"
cp "${APPDIR}/usr/share/icons/hicolor/256x256/apps/file-organizer.svg" "${APPDIR}/.DirIcon"

# Create AppRun
cat > "${APPDIR}/AppRun" << 'APPRUN'
#!/bin/bash
SELF=$(readlink -f "$0")
HERE="${SELF%/*}"
export PATH="${HERE}/usr/bin:${PATH}"
exec "${HERE}/usr/bin/file-organizer" "$@"
APPRUN
chmod +x "${APPDIR}/AppRun"

echo "    Created: ${APPDIR}"

# ---------------------------------------------------------------------------
# Build AppImage or tarball
# ---------------------------------------------------------------------------
if [[ -n "${APPIMAGETOOL:-}" && -x "${APPIMAGETOOL:-}" ]]; then
    echo "==> Building AppImage..."
    APPIMAGE_PATH="${DIST_DIR}/${APPIMAGE_NAME}.AppImage"
    rm -f "${APPIMAGE_PATH}"

    ARCH="${APPIMAGE_ARCH}" "${APPIMAGETOOL}" "${APPDIR}" "${APPIMAGE_PATH}" || {
        echo "    WARNING: appimagetool failed. Creating tarball instead."
        APPIMAGE_PATH=""
    }

    if [[ -n "${APPIMAGE_PATH:-}" && -f "${APPIMAGE_PATH}" ]]; then
        chmod +x "${APPIMAGE_PATH}"
        echo "    Created: ${APPIMAGE_PATH}"
    fi
fi

# Always create a tarball as fallback
echo "==> Creating tarball..."
TARBALL="${DIST_DIR}/${APPIMAGE_NAME}.tar.gz"
tar -czf "${TARBALL}" -C "${BUILD_DIR}" "${APP_NAME}.AppDir"
echo "    Created: ${TARBALL}"

# ---------------------------------------------------------------------------
# Checksum
# ---------------------------------------------------------------------------
echo "==> Generating checksums..."
for f in "${DIST_DIR}/${APPIMAGE_NAME}".*; do
    if [[ -f "$f" ]]; then
        sha256sum "$f" > "$f.sha256"
        echo "    $(basename "$f"): $(cat "$f.sha256" | awk '{print $1}')"
    fi
done

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "==> Linux build complete!"
ls -lh "${DIST_DIR}/${APPIMAGE_NAME}"* 2>/dev/null || true
