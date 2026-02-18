"""CI-focused tests for build workflows."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"

pytestmark = pytest.mark.ci


def _read_workflow(name: str) -> str:
    return (WORKFLOWS_DIR / name).read_text(encoding="utf-8")


def test_macos_workflow_includes_universal_build() -> None:
    content = _read_workflow("build-macos.yml")
    assert "build-universal" in content
    assert "--universal" in content
    assert "file-organizer-macos-universal-dmg" in content
    assert "build_macos.sh" in content


def test_windows_workflow_builds_installer() -> None:
    content = _read_workflow("build-windows.yml")
    assert "choco install innosetup" in content
    assert "build_windows.ps1" in content
    assert "windows-setup.exe" in content


def test_linux_workflow_builds_appimage() -> None:
    content = _read_workflow("build-linux.yml")
    assert "build_linux.sh" in content
    assert ".AppImage" in content
    assert "Upload AppImage" in content


def test_release_workflow_builds_appimage_on_linux() -> None:
    content = _read_workflow("build.yml")
    assert "Build AppImage" in content
    assert "build_linux.sh" in content
