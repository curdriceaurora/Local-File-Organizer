"""Tests for build configuration and build script utilities."""

from __future__ import annotations
import pytest

import sys
from pathlib import Path
from unittest.mock import patch

# Add scripts dir to path so we can import build_config
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from build_config import (
    APP_NAME,
    APP_VERSION,
    EXCLUDES,
    HIDDEN_IMPORTS,
    BuildConfig,
    current_arch,
    current_platform,
)


@pytest.mark.unit
class TestCurrentPlatform:
    def test_macos(self) -> None:
        with patch("platform.system", return_value="Darwin"):
            assert current_platform() == "macos"

    def test_windows(self) -> None:
        with patch("platform.system", return_value="Windows"):
            assert current_platform() == "windows"

    def test_linux(self) -> None:
        with patch("platform.system", return_value="Linux"):
            assert current_platform() == "linux"

    def test_unknown_defaults_to_linux(self) -> None:
        with patch("platform.system", return_value="FreeBSD"):
            assert current_platform() == "linux"


@pytest.mark.unit
class TestCurrentArch:
    def test_x86_64(self) -> None:
        with patch("platform.machine", return_value="x86_64"):
            assert current_arch() == "x86_64"

    def test_amd64(self) -> None:
        with patch("platform.machine", return_value="AMD64"):
            assert current_arch() == "x86_64"

    def test_arm64(self) -> None:
        with patch("platform.machine", return_value="arm64"):
            assert current_arch() == "arm64"

    def test_aarch64(self) -> None:
        with patch("platform.machine", return_value="aarch64"):
            assert current_arch() == "arm64"


@pytest.mark.unit
class TestBuildConfig:
    def test_defaults(self) -> None:
        cfg = BuildConfig()
        assert cfg.app_name == APP_NAME
        assert cfg.version == APP_VERSION
        assert cfg.console is True
        assert cfg.one_file is True
        assert cfg.strip is True

    def test_output_name_unix(self) -> None:
        cfg = BuildConfig(platform="linux", arch="x86_64")
        name = cfg.output_name
        assert "linux" in name
        assert "x86_64" in name
        assert not name.endswith(".exe")

    def test_output_name_windows(self) -> None:
        cfg = BuildConfig(platform="windows", arch="x86_64")
        assert cfg.output_name.endswith(".exe")

    def test_dist_dir(self) -> None:
        cfg = BuildConfig()
        assert cfg.dist_dir == Path("dist")

    def test_build_dir(self) -> None:
        cfg = BuildConfig()
        assert cfg.build_dir == Path("build")


@pytest.mark.unit
class TestHiddenImports:
    def test_contains_core_modules(self) -> None:
        assert "ollama" in HIDDEN_IMPORTS
        assert "textual" in HIDDEN_IMPORTS
        assert "typer" in HIDDEN_IMPORTS
        assert "file_organizer" in HIDDEN_IMPORTS
        assert "file_organizer.services.copilot" in HIDDEN_IMPORTS

    def test_no_duplicates(self) -> None:
        assert len(HIDDEN_IMPORTS) == len(set(HIDDEN_IMPORTS))


@pytest.mark.unit
class TestExcludes:
    def test_excludes_test_frameworks(self) -> None:
        assert "tkinter" in EXCLUDES
        assert "unittest" in EXCLUDES
        assert "test" in EXCLUDES

    def test_no_duplicates(self) -> None:
        assert len(EXCLUDES) == len(set(EXCLUDES))


@pytest.mark.unit
class TestConstants:
    def test_app_name(self) -> None:
        assert APP_NAME == "file-organizer"

    def test_version_format(self) -> None:
        # Should be semver-like
        parts = APP_VERSION.split(".")
        assert len(parts) >= 2
