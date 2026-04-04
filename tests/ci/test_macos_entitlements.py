"""Tests for macOS entitlements files and code signing script.

Validates that plist files exist with required entitlements and that
the signing script is present and executable.
"""

from __future__ import annotations

import plistlib
import stat
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).parent.parent.parent
BUILD_DIR = REPO_ROOT / "desktop" / "build"
SCRIPTS_DIR = REPO_ROOT / "scripts"

ENTITLEMENTS_PLIST = BUILD_DIR / "entitlements.plist"
DEBUG_ENTITLEMENTS_PLIST = BUILD_DIR / "macos-entitlements-debug.plist"
SIGN_SCRIPT = SCRIPTS_DIR / "sign_macos.sh"

# ---------------------------------------------------------------------------
# Required entitlements for both production and debug
# ---------------------------------------------------------------------------
REQUIRED_ENTITLEMENTS: dict[str, bool] = {
    "com.apple.security.network.client": True,
    "com.apple.security.network.server": True,
    "com.apple.security.files.user-selected.read-write": True,
    "com.apple.security.automation.apple-events": False,
}

# Debug-only additional entitlements
DEBUG_ONLY_ENTITLEMENTS: dict[str, bool] = {
    "com.apple.security.cs.allow-jit": True,
    "com.apple.security.cs.disable-library-validation": True,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def load_plist(path: Path) -> dict:
    """Load and return a plist file as a dictionary."""
    with path.open("rb") as f:
        return plistlib.load(f)


# ---------------------------------------------------------------------------
# File existence tests
# ---------------------------------------------------------------------------


class TestEntitlementsFilesExist:
    def test_entitlements_plist_exists(self) -> None:
        assert ENTITLEMENTS_PLIST.exists(), f"entitlements.plist not found at {ENTITLEMENTS_PLIST}"

    def test_debug_entitlements_plist_exists(self) -> None:
        assert DEBUG_ENTITLEMENTS_PLIST.exists(), (
            f"macos-entitlements-debug.plist not found at {DEBUG_ENTITLEMENTS_PLIST}"
        )

    def test_sign_script_exists(self) -> None:
        assert SIGN_SCRIPT.exists(), f"sign_macos.sh not found at {SIGN_SCRIPT}"

    def test_sign_script_is_executable(self) -> None:
        mode = SIGN_SCRIPT.stat().st_mode
        is_executable = bool(mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))
        assert is_executable, f"sign_macos.sh is not executable. Run: chmod +x {SIGN_SCRIPT}"


# ---------------------------------------------------------------------------
# Production entitlements tests
# ---------------------------------------------------------------------------


class TestProductionEntitlements:
    def test_plist_is_valid_xml(self) -> None:
        data = load_plist(ENTITLEMENTS_PLIST)
        assert isinstance(data, dict) and len(data) > 0, (
            "entitlements.plist root must be a non-empty dict"
        )

    @pytest.mark.parametrize("key,expected_value", list(REQUIRED_ENTITLEMENTS.items()))
    def test_required_entitlement_present(self, key: str, expected_value: bool) -> None:
        data = load_plist(ENTITLEMENTS_PLIST)
        assert key in data, f"Missing entitlement key: {key}"
        assert data[key] == expected_value, (
            f"Entitlement '{key}' expected {expected_value}, got {data[key]}"
        )

    def test_no_jit_in_production(self) -> None:
        """JIT entitlement must NOT be present in the production plist."""
        data = load_plist(ENTITLEMENTS_PLIST)
        assert "com.apple.security.cs.allow-jit" not in data, (
            "com.apple.security.cs.allow-jit must not appear in the production plist"
        )

    def test_no_library_validation_disable_in_production(self) -> None:
        """Library validation disable must NOT be in the production plist."""
        data = load_plist(ENTITLEMENTS_PLIST)
        assert "com.apple.security.cs.disable-library-validation" not in data, (
            "com.apple.security.cs.disable-library-validation must not appear in "
            "the production plist"
        )


# ---------------------------------------------------------------------------
# Debug entitlements tests
# ---------------------------------------------------------------------------


class TestDebugEntitlements:
    def test_plist_is_valid_xml(self) -> None:
        data = load_plist(DEBUG_ENTITLEMENTS_PLIST)
        assert isinstance(data, dict) and len(data) > 0, (
            "macos-entitlements-debug.plist root must be a non-empty dict"
        )

    @pytest.mark.parametrize("key,expected_value", list(REQUIRED_ENTITLEMENTS.items()))
    def test_required_entitlement_present(self, key: str, expected_value: bool) -> None:
        data = load_plist(DEBUG_ENTITLEMENTS_PLIST)
        assert key in data, f"Missing entitlement key in debug plist: {key}"
        assert data[key] == expected_value, (
            f"Debug plist entitlement '{key}' expected {expected_value}, got {data[key]}"
        )

    @pytest.mark.parametrize("key,expected_value", list(DEBUG_ONLY_ENTITLEMENTS.items()))
    def test_debug_only_entitlement_present(self, key: str, expected_value: bool) -> None:
        data = load_plist(DEBUG_ENTITLEMENTS_PLIST)
        assert key in data, f"Missing debug-only entitlement key: {key}"
        assert data[key] == expected_value, (
            f"Debug entitlement '{key}' expected {expected_value}, got {data[key]}"
        )


# ---------------------------------------------------------------------------
# Sign script content tests
# ---------------------------------------------------------------------------


class TestSignScript:
    def _read_script(self) -> str:
        return SIGN_SCRIPT.read_text()

    def test_checks_signing_identity_env_var(self) -> None:
        content = self._read_script()
        assert "APPLE_SIGNING_IDENTITY" in content, (
            "sign_macos.sh must reference APPLE_SIGNING_IDENTITY env var"
        )

    def test_supports_adhoc_signing(self) -> None:
        content = self._read_script()
        assert 'SIGNING_IDENTITY="-"' in content or "ad-hoc" in content, (
            "sign_macos.sh must support ad-hoc signing (identity '-')"
        )

    def test_references_entitlements_plist(self) -> None:
        content = self._read_script()
        assert "entitlements.plist" in content, "sign_macos.sh must reference entitlements.plist"

    def test_references_debug_entitlements_plist(self) -> None:
        content = self._read_script()
        assert "macos-entitlements-debug.plist" in content, (
            "sign_macos.sh must reference macos-entitlements-debug.plist"
        )

    def test_uses_codesign(self) -> None:
        content = self._read_script()
        assert "codesign" in content, "sign_macos.sh must invoke the codesign tool"

    def test_notarytool_present(self) -> None:
        content = self._read_script()
        assert "notarytool" in content, (
            "sign_macos.sh must reference xcrun notarytool for notarization"
        )

    def test_has_debug_flag_support(self) -> None:
        content = self._read_script()
        assert "--debug" in content, (
            "sign_macos.sh must support a --debug flag to select debug entitlements"
        )
