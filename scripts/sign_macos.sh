#!/usr/bin/env bash
# sign_macos.sh — macOS code signing and notarization workflow for File Organizer
#
# Required environment variables for signed distribution:
#   APPLE_SIGNING_IDENTITY  — e.g. "Developer ID Application: Your Name (TEAMID)"
#   APPLE_TEAM_ID           — Apple Developer Team ID
#   APPLE_ID                — Apple ID email used for notarization
#   APPLE_APP_PASSWORD      — App-specific password for notarytool
#
# For ad-hoc (unsigned) development builds, none of these are required.
#
# Usage:
#   bash scripts/sign_macos.sh [path/to/App.app] [--debug]
#
# Examples:
#   bash scripts/sign_macos.sh target/release/bundle/macos/FileOrganizer.app
#   bash scripts/sign_macos.sh target/release/bundle/macos/FileOrganizer.app --debug

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BUILD_DIR="${REPO_ROOT}/desktop/build"
ENTITLEMENTS="${BUILD_DIR}/entitlements.plist"
DEBUG_ENTITLEMENTS="${BUILD_DIR}/macos-entitlements-debug.plist"

APP_PATH="${1:-}"
DEBUG_MODE=false

for arg in "$@"; do
    [[ "$arg" == "--debug" ]] && DEBUG_MODE=true
done

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
log()  { echo "[sign_macos] $*"; }
warn() { echo "[sign_macos] WARNING: $*" >&2; }
fail() { echo "[sign_macos] ERROR: $*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Validate inputs
# ---------------------------------------------------------------------------
if [[ -z "${APP_PATH}" ]]; then
    fail "No .app path provided. Usage: $0 <path/to/App.app> [--debug]"
fi

if [[ ! -d "${APP_PATH}" ]]; then
    fail "App bundle not found: ${APP_PATH}"
fi

ACTIVE_ENTITLEMENTS="${ENTITLEMENTS}"
if [[ "${DEBUG_MODE}" == "true" ]]; then
    ACTIVE_ENTITLEMENTS="${DEBUG_ENTITLEMENTS}"
    log "Debug mode: using ${DEBUG_ENTITLEMENTS}"
fi

if [[ ! -f "${ACTIVE_ENTITLEMENTS}" ]]; then
    fail "Entitlements file not found: ${ACTIVE_ENTITLEMENTS}"
fi

# ---------------------------------------------------------------------------
# Determine signing mode
# ---------------------------------------------------------------------------
SIGNING_IDENTITY="${APPLE_SIGNING_IDENTITY:-}"

if [[ -z "${SIGNING_IDENTITY}" ]]; then
    warn "APPLE_SIGNING_IDENTITY not set — performing ad-hoc signing (-)"
    warn "Ad-hoc signed apps will not pass Gatekeeper on other machines."
    SIGNING_IDENTITY="-"
fi

# ---------------------------------------------------------------------------
# Sign the app bundle
# ---------------------------------------------------------------------------
log "Signing: ${APP_PATH}"
log "Identity: ${SIGNING_IDENTITY}"
log "Entitlements: ${ACTIVE_ENTITLEMENTS}"

codesign \
    --force \
    --deep \
    --sign "${SIGNING_IDENTITY}" \
    --entitlements "${ACTIVE_ENTITLEMENTS}" \
    --options runtime \
    "${APP_PATH}"

log "Code signing complete."

# Verify the signature
codesign --verify --deep --strict --verbose=2 "${APP_PATH}" \
    && log "Signature verified successfully." \
    || fail "Signature verification failed."

# ---------------------------------------------------------------------------
# Notarization (only for real Developer ID, not ad-hoc)
# ---------------------------------------------------------------------------
if [[ "${SIGNING_IDENTITY}" == "-" ]]; then
    log "Skipping notarization (ad-hoc signing)."
    exit 0
fi

APPLE_ID="${APPLE_ID:-}"
APPLE_APP_PASSWORD="${APPLE_APP_PASSWORD:-}"
APPLE_TEAM_ID="${APPLE_TEAM_ID:-}"

if [[ -z "${APPLE_ID}" || -z "${APPLE_APP_PASSWORD}" || -z "${APPLE_TEAM_ID}" ]]; then
    warn "APPLE_ID, APPLE_APP_PASSWORD, or APPLE_TEAM_ID not set."
    warn "Skipping notarization. Set these env vars for App Store / Gatekeeper distribution."
    exit 0
fi

log "Creating zip archive for notarization..."
ZIP_PATH="${APP_PATH%.app}.zip"
ditto -c -k --keepParent "${APP_PATH}" "${ZIP_PATH}"

log "Submitting to Apple notary service..."
xcrun notarytool submit "${ZIP_PATH}" \
    --apple-id "${APPLE_ID}" \
    --password "${APPLE_APP_PASSWORD}" \
    --team-id "${APPLE_TEAM_ID}" \
    --wait

log "Stapling notarization ticket..."
xcrun stapler staple "${APP_PATH}"

log "Notarization and stapling complete."
rm -f "${ZIP_PATH}"
