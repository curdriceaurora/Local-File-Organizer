"""Tests validating that build scripts produce Tauri sidecar naming convention.

Tauri expects sidecars named ``{binary-name}-{target-triple}``, e.g.:
  file-organizer-backend-x86_64-apple-darwin
  file-organizer-backend-aarch64-apple-darwin
  file-organizer-backend-x86_64-pc-windows-msvc
  file-organizer-backend-x86_64-unknown-linux-gnu

These tests verify that the build scripts contain the correct rename/copy
commands to produce such output without actually running the builds.

The scripts use shell/PowerShell variables to compose the final name, so tests
check for both the binary name prefix (``file-organizer-backend``) and each
target triple string in the same script.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"

MACOS_SCRIPT = SCRIPTS_DIR / "build_macos.sh"
LINUX_SCRIPT = SCRIPTS_DIR / "build_linux.sh"
WINDOWS_SCRIPT = SCRIPTS_DIR / "build_windows.ps1"

SIDECAR_PREFIX = "file-organizer-backend"

EXPECTED_TARGET_TRIPLES = {
    "x86_64-apple-darwin",
    "aarch64-apple-darwin",
    "x86_64-pc-windows-msvc",
    "x86_64-unknown-linux-gnu",
}

# macOS-specific triples
MACOS_TRIPLES = {"x86_64-apple-darwin", "aarch64-apple-darwin"}
# Linux-specific triples
LINUX_TRIPLES = {"x86_64-unknown-linux-gnu", "aarch64-unknown-linux-gnu"}
# Windows-specific triples
WINDOWS_TRIPLES = {"x86_64-pc-windows-msvc"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_script(path: Path) -> str:
    """Read a build script, failing clearly if missing."""
    assert path.exists(), f"Build script not found: {path}"
    return path.read_text(encoding="utf-8")


def _assert_triple_in_script(content: str, triple: str, script_path: Path) -> None:
    """Assert that *content* contains *triple* (as a standalone string or in a variable assignment).

    Build scripts use variables to compose the final sidecar name, e.g.:
      SIDECAR_TRIPLE="x86_64-apple-darwin"
      SIDECAR_PATH="${DIST_DIR}/file-organizer-backend-${SIDECAR_TRIPLE}"

    So the triple appears as a quoted string value, not necessarily concatenated
    with the prefix in a single literal.
    """
    assert triple in content, (
        f"Target triple '{triple}' not found in {script_path.name}.\n"
        "Expected it to appear as a shell variable value or inline string.\n"
        f'Example: SIDECAR_TRIPLE="{triple}" or file-organizer-backend-{triple}'
    )


# ---------------------------------------------------------------------------
# macOS tests
# ---------------------------------------------------------------------------


class TestMacosSidecarNaming:
    """Verify build_macos.sh produces correct Tauri sidecar names."""

    def test_script_exists(self) -> None:
        assert MACOS_SCRIPT.exists(), f"Missing: {MACOS_SCRIPT}"

    def test_contains_sidecar_prefix(self) -> None:
        content = _read_script(MACOS_SCRIPT)
        assert SIDECAR_PREFIX in content, (
            f"{MACOS_SCRIPT.name} must reference '{SIDECAR_PREFIX}' for Tauri sidecar output."
        )

    def test_x86_64_apple_darwin_triple(self) -> None:
        content = _read_script(MACOS_SCRIPT)
        _assert_triple_in_script(content, "x86_64-apple-darwin", MACOS_SCRIPT)

    def test_aarch64_apple_darwin_triple(self) -> None:
        content = _read_script(MACOS_SCRIPT)
        _assert_triple_in_script(content, "aarch64-apple-darwin", MACOS_SCRIPT)

    def test_sidecar_path_variable_defined(self) -> None:
        """Script must define SIDECAR_PATH that combines prefix and triple."""
        content = _read_script(MACOS_SCRIPT)
        assert "SIDECAR_PATH" in content, f"{MACOS_SCRIPT.name} must define SIDECAR_PATH variable."
        # The SIDECAR_PATH must incorporate the prefix
        assert re.search(rf"SIDECAR_PATH=.*{re.escape(SIDECAR_PREFIX)}", content), (
            f"{MACOS_SCRIPT.name}: SIDECAR_PATH must include '{SIDECAR_PREFIX}'."
        )

    def test_sidecar_copy_command(self) -> None:
        """Script must copy the executable to the sidecar path."""
        content = _read_script(MACOS_SCRIPT)
        assert re.search(r'cp\s+"\$\{EXECUTABLE\}"\s+"\$\{SIDECAR_PATH\}"', content), (
            f"{MACOS_SCRIPT.name} must copy EXECUTABLE to SIDECAR_PATH."
        )

    def test_sidecar_is_executable(self) -> None:
        """Script must chmod +x the sidecar."""
        content = _read_script(MACOS_SCRIPT)
        assert re.search(r"chmod\s+\+x.*SIDECAR", content), (
            f"{MACOS_SCRIPT.name} must make the sidecar executable with chmod +x."
        )

    def test_no_windows_triple_in_macos(self) -> None:
        """macOS script should not reference Windows or Linux triples."""
        content = _read_script(MACOS_SCRIPT)
        assert "pc-windows-msvc" not in content, (
            f"{MACOS_SCRIPT.name} incorrectly references a Windows target triple."
        )
        assert "unknown-linux-gnu" not in content, (
            f"{MACOS_SCRIPT.name} incorrectly references a Linux target triple."
        )


# ---------------------------------------------------------------------------
# Linux tests
# ---------------------------------------------------------------------------


class TestLinuxSidecarNaming:
    """Verify build_linux.sh produces correct Tauri sidecar names."""

    def test_script_exists(self) -> None:
        assert LINUX_SCRIPT.exists(), f"Missing: {LINUX_SCRIPT}"

    def test_contains_sidecar_prefix(self) -> None:
        content = _read_script(LINUX_SCRIPT)
        assert SIDECAR_PREFIX in content, (
            f"{LINUX_SCRIPT.name} must reference '{SIDECAR_PREFIX}' for Tauri sidecar output."
        )

    def test_x86_64_unknown_linux_gnu_triple(self) -> None:
        content = _read_script(LINUX_SCRIPT)
        _assert_triple_in_script(content, "x86_64-unknown-linux-gnu", LINUX_SCRIPT)

    def test_aarch64_linux_triple_present(self) -> None:
        """aarch64 Linux triple should also be handled."""
        content = _read_script(LINUX_SCRIPT)
        _assert_triple_in_script(content, "aarch64-unknown-linux-gnu", LINUX_SCRIPT)

    def test_sidecar_path_variable_defined(self) -> None:
        content = _read_script(LINUX_SCRIPT)
        assert "SIDECAR_PATH" in content, f"{LINUX_SCRIPT.name} must define SIDECAR_PATH variable."
        assert re.search(rf"SIDECAR_PATH=.*{re.escape(SIDECAR_PREFIX)}", content), (
            f"{LINUX_SCRIPT.name}: SIDECAR_PATH must include '{SIDECAR_PREFIX}'."
        )

    def test_sidecar_copy_command(self) -> None:
        content = _read_script(LINUX_SCRIPT)
        assert re.search(r'cp\s+"\$\{EXECUTABLE\}"\s+"\$\{SIDECAR_PATH\}"', content), (
            f"{LINUX_SCRIPT.name} must copy EXECUTABLE to SIDECAR_PATH."
        )

    def test_sidecar_is_executable(self) -> None:
        content = _read_script(LINUX_SCRIPT)
        assert re.search(r"chmod\s+\+x.*SIDECAR", content), (
            f"{LINUX_SCRIPT.name} must make the sidecar executable with chmod +x."
        )

    def test_no_apple_triple_in_linux(self) -> None:
        content = _read_script(LINUX_SCRIPT)
        assert "apple-darwin" not in content, (
            f"{LINUX_SCRIPT.name} incorrectly references an Apple target triple."
        )
        assert "pc-windows-msvc" not in content, (
            f"{LINUX_SCRIPT.name} incorrectly references a Windows target triple."
        )


# ---------------------------------------------------------------------------
# Windows tests
# ---------------------------------------------------------------------------


class TestWindowsSidecarNaming:
    """Verify build_windows.ps1 produces correct Tauri sidecar names."""

    def test_script_exists(self) -> None:
        assert WINDOWS_SCRIPT.exists(), f"Missing: {WINDOWS_SCRIPT}"

    def test_contains_sidecar_prefix(self) -> None:
        content = _read_script(WINDOWS_SCRIPT)
        assert SIDECAR_PREFIX in content, (
            f"{WINDOWS_SCRIPT.name} must reference '{SIDECAR_PREFIX}' for Tauri sidecar output."
        )

    def test_x86_64_pc_windows_msvc_triple(self) -> None:
        content = _read_script(WINDOWS_SCRIPT)
        _assert_triple_in_script(content, "x86_64-pc-windows-msvc", WINDOWS_SCRIPT)

    def test_sidecar_copy_command_present(self) -> None:
        """Script must use Copy-Item to produce the sidecar."""
        content = _read_script(WINDOWS_SCRIPT)
        assert "Copy-Item" in content, (
            f"{WINDOWS_SCRIPT.name} must use Copy-Item to create the sidecar executable."
        )

    def test_sidecar_destination_path_set(self) -> None:
        """Script must compute a sidecarPath variable."""
        content = _read_script(WINDOWS_SCRIPT)
        assert "sidecarPath" in content, (
            f"{WINDOWS_SCRIPT.name} must define a sidecarPath variable."
        )
        assert re.search(rf"sidecar.*{re.escape(SIDECAR_PREFIX)}", content, re.IGNORECASE), (
            f"{WINDOWS_SCRIPT.name}: sidecar variable must include '{SIDECAR_PREFIX}'."
        )

    def test_sidecar_has_exe_extension(self) -> None:
        """Windows sidecar must include .exe extension."""
        content = _read_script(WINDOWS_SCRIPT)
        assert re.search(r"file-organizer-backend.*\.exe", content), (
            f"{WINDOWS_SCRIPT.name}: Windows sidecar must end in .exe"
        )

    def test_no_apple_triple_in_windows(self) -> None:
        content = _read_script(WINDOWS_SCRIPT)
        assert "apple-darwin" not in content, (
            f"{WINDOWS_SCRIPT.name} incorrectly references an Apple target triple."
        )
        assert "unknown-linux-gnu" not in content, (
            f"{WINDOWS_SCRIPT.name} incorrectly references a Linux target triple."
        )


# ---------------------------------------------------------------------------
# Cross-platform naming convention tests
# ---------------------------------------------------------------------------


class TestSidecarNamingConvention:
    """Validate the naming convention across all build scripts."""

    @pytest.mark.parametrize(
        "triple,script",
        [
            ("x86_64-apple-darwin", MACOS_SCRIPT),
            ("aarch64-apple-darwin", MACOS_SCRIPT),
            ("x86_64-unknown-linux-gnu", LINUX_SCRIPT),
            ("aarch64-unknown-linux-gnu", LINUX_SCRIPT),
            ("x86_64-pc-windows-msvc", WINDOWS_SCRIPT),
        ],
    )
    def test_triple_in_expected_script(self, triple: str, script: Path) -> None:
        """Each target triple must appear in its corresponding build script."""
        assert script.exists(), f"Build script not found: {script}"
        content = script.read_text(encoding="utf-8")
        assert triple in content, (
            f"Target triple '{triple}' not found in {script.name}.\n"
            f"Expected to find it as a shell/PS variable value."
        )

    @pytest.mark.parametrize(
        "script",
        [MACOS_SCRIPT, LINUX_SCRIPT, WINDOWS_SCRIPT],
        ids=["macos", "linux", "windows"],
    )
    def test_sidecar_prefix_in_all_scripts(self, script: Path) -> None:
        """All build scripts must reference the sidecar binary prefix."""
        assert script.exists(), f"Build script not found: {script}"
        content = script.read_text(encoding="utf-8")
        assert SIDECAR_PREFIX in content, (
            f"{script.name} must reference '{SIDECAR_PREFIX}' for Tauri sidecar output."
        )

    def test_sidecar_binary_name_no_underscores(self) -> None:
        """Sidecar prefix must use hyphens, not underscores."""
        wrong_prefixes = [
            "file_organizer_backend",
            "file-organizer_backend",
            "fileorganizer-backend",
        ]
        for script in [MACOS_SCRIPT, LINUX_SCRIPT, WINDOWS_SCRIPT]:
            if not script.exists():
                continue
            content = script.read_text(encoding="utf-8")
            for wrong in wrong_prefixes:
                assert wrong not in content, (
                    f"{script.name} uses incorrect sidecar prefix '{wrong}'. "
                    f"Must use '{SIDECAR_PREFIX}'."
                )
