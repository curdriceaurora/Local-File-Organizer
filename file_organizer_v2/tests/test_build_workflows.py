"""CI-focused tests for build workflows."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"

pytestmark = pytest.mark.ci


def _read_workflow(name: str) -> str:
    return (WORKFLOWS_DIR / name).read_text(encoding="utf-8")


def test_build_workflow_includes_macos() -> None:
    """Test that build.yml includes macOS builds."""
    content = _read_workflow("build.yml")
    assert "macos-latest" in content or "platform: macos" in content
    assert "macos" in content


def test_build_workflow_includes_windows() -> None:
    """Test that build.yml includes Windows builds."""
    content = _read_workflow("build.yml")
    assert "windows-latest" in content or "platform: windows" in content
    assert "windows" in content


def test_build_workflow_includes_linux() -> None:
    """Test that build.yml includes Linux builds."""
    content = _read_workflow("build.yml")
    assert "ubuntu-latest" in content or "platform: linux" in content
    assert "linux" in content


def test_build_workflow_builds_appimage_on_linux() -> None:
    """Test that build.yml builds AppImage on Linux."""
    content = _read_workflow("build.yml")
    assert "Build AppImage" in content
    assert "build_linux.sh" in content
