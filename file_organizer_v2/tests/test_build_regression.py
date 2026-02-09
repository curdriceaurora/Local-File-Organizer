"""Regression tests for build/packaging scripts."""
from __future__ import annotations

from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"

pytestmark = pytest.mark.regression


def test_macos_script_uses_pyproject_version() -> None:
    script = (SCRIPTS_DIR / "build_macos.sh").read_text(encoding="utf-8")
    assert "pyproject.toml" in script
    assert "version" in script


def test_macos_script_names_dmg_with_version() -> None:
    script = (SCRIPTS_DIR / "build_macos.sh").read_text(encoding="utf-8")
    assert 'DMG_NAME="file-organizer-${VERSION}-macos-${ARCH}"' in script
    assert 'DMG_NAME="file-organizer-${VERSION}-macos-universal"' in script


def test_macos_universal_build_uses_lipo() -> None:
    script = (SCRIPTS_DIR / "build_macos.sh").read_text(encoding="utf-8")
    assert "lipo -create" in script


def test_windows_script_reads_version_from_pyproject() -> None:
    script = (SCRIPTS_DIR / "build_windows.ps1").read_text(encoding="utf-8")
    assert "pyproject.toml" in script
    assert "tomllib" in script


def test_windows_script_passes_version_to_iscc() -> None:
    script = (SCRIPTS_DIR / "build_windows.ps1").read_text(encoding="utf-8")
    assert "/DAppVersion=$version" in script


def test_windows_installer_names_include_version() -> None:
    iss = (SCRIPTS_DIR / "build_windows.iss").read_text(encoding="utf-8")
    assert "OutputBaseFilename=file-organizer-{#AppVersion}-windows-setup" in iss


def test_linux_script_uses_pyproject_version() -> None:
    script = (SCRIPTS_DIR / "build_linux.sh").read_text(encoding="utf-8")
    assert "pyproject.toml" in script
    assert "version" in script


def test_linux_appimage_naming_uses_version() -> None:
    script = (SCRIPTS_DIR / "build_linux.sh").read_text(encoding="utf-8")
    assert 'APPIMAGE_NAME="${APP_NAME}-${VERSION}-linux-${ARCH}"' in script
