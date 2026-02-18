"""Tests for build/packaging scripts and configs."""

from __future__ import annotations

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.ci


def test_build_windows_ps1_exists_and_has_iscc_path() -> None:
    script = PROJECT_ROOT / "scripts" / "build_windows.ps1"
    assert script.exists()
    content = script.read_text(encoding="utf-8")
    assert "ISCC.exe" in content
    assert "build_windows.iss" in content


def test_build_windows_iss_supports_version_override() -> None:
    iss = PROJECT_ROOT / "scripts" / "build_windows.iss"
    assert iss.exists()
    content = iss.read_text(encoding="utf-8")
    assert "#ifndef AppVersion" in content
    assert "#define AppVersion" in content
    assert "/DAppVersion" in (PROJECT_ROOT / "scripts" / "build_windows.ps1").read_text(
        encoding="utf-8"
    )


def test_build_macos_has_universal_flags() -> None:
    script = PROJECT_ROOT / "scripts" / "build_macos.sh"
    assert script.exists()
    content = script.read_text(encoding="utf-8")
    assert "--universal" in content
    assert "--arm" in content
    assert "--x86" in content


def test_build_linux_script_exists_and_mentions_appimage() -> None:
    script = PROJECT_ROOT / "scripts" / "build_linux.sh"
    assert script.exists()
    content = script.read_text(encoding="utf-8")
    assert "appimagetool" in content
    assert "AppRun" in content
    assert "AppImage" in content
