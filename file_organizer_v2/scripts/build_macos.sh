#!/usr/bin/env bash
# build_macos.sh — Create macOS DMG installer from PyInstaller output.
#
# Usage:
#   bash scripts/build_macos.sh [--sign IDENTITY] [--notarize]
#
# Requires:
#   - PyInstaller build output in dist/
#   - hdiutil (ships with macOS)
#   - Optional: codesign identity for signing
#   - Optional: notarytool for notarization

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
DIST_DIR="${PROJECT_ROOT}/dist"
BUILD_DIR="${PROJECT_ROOT}/build"
APP_NAME="File Organizer"
BUNDLE_ID="com.fileorganizer.app"
VERSION="2.0.0-alpha.1"
DMG_NAME="file-organizer-${VERSION}-macos"
SIGN_IDENTITY=""
NOTARIZE=false

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
    case $1 in
        --sign)     SIGN_IDENTITY="$2"; shift 2 ;;
        --notarize) NOTARIZE=true; shift ;;
        --help)
            echo "Usage: $0 [--sign IDENTITY] [--notarize]"
            echo ""
            echo "Options:"
            echo "  --sign IDENTITY   Code signing identity (Developer ID Application)"
            echo "  --notarize        Submit to Apple notary service after signing"
            exit 0
            ;;
        *)          echo "Unknown option: $1"; exit 1 ;;
    esac
done

# ---------------------------------------------------------------------------
# Ensure PyInstaller output exists
# ---------------------------------------------------------------------------
echo "==> Checking for PyInstaller output..."
EXECUTABLE=$(find "${DIST_DIR}" -maxdepth 1 -name "file-organizer-*" -type f 2>/dev/null | head -1)

if [[ -z "$EXECUTABLE" ]]; then
    echo "ERROR: No executable found in ${DIST_DIR}/"
    echo "Run 'python scripts/build.py' first."
    exit 1
fi

echo "    Found: ${EXECUTABLE}"

# ---------------------------------------------------------------------------
# Create .app bundle structure
# ---------------------------------------------------------------------------
echo "==> Creating .app bundle..."

APP_DIR="${BUILD_DIR}/${APP_NAME}.app"
rm -rf "${APP_DIR}"
mkdir -p "${APP_DIR}/Contents/MacOS"
mkdir -p "${APP_DIR}/Contents/Resources"

# Copy executable
cp "${EXECUTABLE}" "${APP_DIR}/Contents/MacOS/file-organizer"
chmod +x "${APP_DIR}/Contents/MacOS/file-organizer"

# Create Info.plist
cat > "${APP_DIR}/Contents/Info.plist" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>${APP_NAME}</string>
    <key>CFBundleDisplayName</key>
    <string>${APP_NAME}</string>
    <key>CFBundleIdentifier</key>
    <string>${BUNDLE_ID}</string>
    <key>CFBundleVersion</key>
    <string>${VERSION}</string>
    <key>CFBundleShortVersionString</key>
    <string>${VERSION}</string>
    <key>CFBundleExecutable</key>
    <string>file-organizer</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>LSMinimumSystemVersion</key>
    <string>11.0</string>
    <key>NSHighResolutionCapable</key>
    <true/>
</dict>
</plist>
PLIST

echo "    Created: ${APP_DIR}"

# ---------------------------------------------------------------------------
# Code signing (optional)
# ---------------------------------------------------------------------------
if [[ -n "$SIGN_IDENTITY" ]]; then
    echo "==> Signing with identity: ${SIGN_IDENTITY}..."
    codesign --deep --force --options runtime \
        --sign "${SIGN_IDENTITY}" \
        --entitlements /dev/null \
        "${APP_DIR}"
    echo "    Signed successfully."

    # Verify
    codesign --verify --deep --strict "${APP_DIR}"
    echo "    Verification passed."
fi

# ---------------------------------------------------------------------------
# Create DMG
# ---------------------------------------------------------------------------
echo "==> Creating DMG installer..."

DMG_STAGING="${BUILD_DIR}/dmg-staging"
rm -rf "${DMG_STAGING}"
mkdir -p "${DMG_STAGING}"

# Copy app to staging
cp -R "${APP_DIR}" "${DMG_STAGING}/"

# Create Applications symlink
ln -s /Applications "${DMG_STAGING}/Applications"

# Create README
cat > "${DMG_STAGING}/README.txt" << 'README'
File Organizer — AI-powered local file management

INSTALLATION:
1. Drag "File Organizer" to the Applications folder
2. Install Ollama: https://ollama.ai
3. Pull required models:
   ollama pull qwen2.5:3b-instruct-q4_K_M
   ollama pull qwen2.5vl:7b-q4_K_M
4. Run from terminal: /Applications/File Organizer.app/Contents/MacOS/file-organizer --help

REQUIREMENTS:
- macOS 11.0 or later
- Ollama (installed separately)
- 8 GB RAM minimum
README

# Create DMG
DMG_PATH="${DIST_DIR}/${DMG_NAME}.dmg"
rm -f "${DMG_PATH}"

hdiutil create -volname "${APP_NAME}" \
    -srcfolder "${DMG_STAGING}" \
    -ov -format UDZO \
    "${DMG_PATH}"

echo "    Created: ${DMG_PATH}"

# ---------------------------------------------------------------------------
# Notarization (optional)
# ---------------------------------------------------------------------------
if [[ "$NOTARIZE" == "true" && -n "$SIGN_IDENTITY" ]]; then
    echo "==> Submitting for notarization..."
    echo "    NOTE: Requires APPLE_ID, APPLE_TEAM_ID, and APPLE_APP_PASSWORD env vars."

    if [[ -z "${APPLE_ID:-}" || -z "${APPLE_TEAM_ID:-}" ]]; then
        echo "    SKIPPED: Set APPLE_ID, APPLE_TEAM_ID, and APPLE_APP_PASSWORD."
    else
        xcrun notarytool submit "${DMG_PATH}" \
            --apple-id "${APPLE_ID}" \
            --team-id "${APPLE_TEAM_ID}" \
            --password "${APPLE_APP_PASSWORD:-}" \
            --wait

        # Staple the notarization ticket
        xcrun stapler staple "${DMG_PATH}"
        echo "    Notarization complete."
    fi
fi

# ---------------------------------------------------------------------------
# Checksum
# ---------------------------------------------------------------------------
echo "==> Generating checksum..."
CHECKSUM=$(shasum -a 256 "${DMG_PATH}" | awk '{print $1}')
echo "${CHECKSUM}  ${DMG_NAME}.dmg" > "${DIST_DIR}/${DMG_NAME}.sha256"
echo "    SHA256: ${CHECKSUM}"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "==> macOS build complete!"
echo "    DMG:      ${DMG_PATH}"
echo "    Size:     $(du -h "${DMG_PATH}" | cut -f1)"
echo "    Checksum: ${DIST_DIR}/${DMG_NAME}.sha256"
