"""CI-focused tests for build workflows."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
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


def test_build_workflow_has_no_rust_steps() -> None:
    """Test that build.yml contains no Rust/Tauri references."""
    content = _read_workflow("build.yml")
    assert "cargo" not in content
    assert "rustc" not in content
    assert "dtolnay/rust-toolchain" not in content
    assert "Swatinem/rust-cache" not in content
    assert "src-tauri" not in content
    assert "TAURI_SIGNING" not in content


def test_build_workflow_has_desktop_build_step() -> None:
    """Test that build.yml includes the pywebview desktop build step."""
    content = _read_workflow("build.yml")
    assert "--desktop" in content


def test_build_workflow_installs_pywebview_linux_deps() -> None:
    """Test that build.yml installs GTK/WebKit deps on Linux."""
    content = _read_workflow("build.yml")
    # pywebview on Linux requires GTK and WebKit
    assert "libgirepository" in content or "gir1.2-webkit2" in content


def test_build_workflow_release_needs_build_only() -> None:
    """Test that the release job depends only on build, not test-rust."""
    content = _read_workflow("build.yml")
    assert "needs: [build]" in content or "needs:\n    - build" in content
    assert "test-rust" not in content


def test_build_workflow_uploads_from_dist() -> None:
    """Test that artifacts are uploaded from dist/, not combined-artifacts/."""
    content = _read_workflow("build.yml")
    assert "combined-artifacts" not in content
    assert "dist/" in content or "dist/*" in content
