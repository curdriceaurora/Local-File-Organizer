"""Tests for the auto-update mechanism."""

from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import patch

import pytest

from file_organizer.updater.checker import (
    AssetInfo,
    ReleaseInfo,
    UpdateChecker,
    _parse_version,
)
from file_organizer.updater.installer import UpdateInstaller
from file_organizer.updater.manager import UpdateManager, UpdateStatus

# ---------------------------------------------------------------------------
# Version parsing
# ---------------------------------------------------------------------------


class TestParseVersion:
    def test_simple(self) -> None:
        assert _parse_version("2.0.0") == (2, 0, 0)

    def test_with_v_prefix(self) -> None:
        assert _parse_version("v2.1.3") == (2, 1, 3)

    def test_with_prerelease(self) -> None:
        assert _parse_version("2.0.0-alpha.1") == (2, 0, 0)

    def test_comparison(self) -> None:
        assert _parse_version("2.1.0") > _parse_version("2.0.0")
        assert _parse_version("2.0.1") > _parse_version("2.0.0")
        assert _parse_version("3.0.0") > _parse_version("2.9.9")

    def test_equal(self) -> None:
        assert _parse_version("v2.0.0") == _parse_version("2.0.0")

    def test_empty(self) -> None:
        assert _parse_version("") == (0,)


# ---------------------------------------------------------------------------
# ReleaseInfo / AssetInfo
# ---------------------------------------------------------------------------


class TestReleaseInfo:
    def test_default_values(self) -> None:
        r = ReleaseInfo()
        assert r.tag == ""
        assert r.assets == []
        assert r.prerelease is False

    def test_with_assets(self) -> None:
        r = ReleaseInfo(
            tag="v2.0.0",
            version="2.0.0",
            assets=[AssetInfo(name="binary.tar.gz", url="https://example.com", size=1024)],
        )
        assert len(r.assets) == 1
        assert r.assets[0].name == "binary.tar.gz"


# ---------------------------------------------------------------------------
# UpdateChecker
# ---------------------------------------------------------------------------


class TestUpdateChecker:
    def test_no_update_when_current(self) -> None:
        checker = UpdateChecker(current_version="99.99.99")
        # Mock the API call
        with patch.object(checker, "_fetch_latest_release") as mock_fetch:
            mock_fetch.return_value = ReleaseInfo(tag="v2.0.0", version="2.0.0")
            result = checker.check()
            assert result is None

    def test_update_available(self) -> None:
        checker = UpdateChecker(current_version="1.0.0")
        with patch.object(checker, "_fetch_latest_release") as mock_fetch:
            mock_fetch.return_value = ReleaseInfo(tag="v2.0.0", version="2.0.0")
            result = checker.check()
            assert result is not None
            assert result.version == "2.0.0"

    def test_handles_api_failure(self) -> None:
        checker = UpdateChecker(current_version="1.0.0")
        with patch.object(checker, "_fetch_latest_release", side_effect=Exception("Network error")):
            result = checker.check()
            assert result is None

    def test_parse_release(self) -> None:
        data = {
            "tag_name": "v2.1.0",
            "prerelease": False,
            "body": "Release notes",
            "html_url": "https://github.com/test/releases/v2.1.0",
            "published_at": "2026-01-01T00:00:00Z",
            "assets": [
                {
                    "name": "file-organizer-linux-x86_64",
                    "browser_download_url": "https://example.com/bin",
                    "size": 50000000,
                    "content_type": "application/octet-stream",
                },
            ],
        }
        result = UpdateChecker._parse_release(data)
        assert result.tag == "v2.1.0"
        assert result.version == "2.1.0"
        assert len(result.assets) == 1
        assert result.assets[0].size == 50000000


# ---------------------------------------------------------------------------
# UpdateInstaller
# ---------------------------------------------------------------------------


class TestUpdateInstaller:
    def test_select_asset_linux(self) -> None:
        installer = UpdateInstaller()
        release = ReleaseInfo(
            assets=[
                AssetInfo(name="file-organizer-2.0.0-linux-x86_64", url="u1"),
                AssetInfo(name="file-organizer-2.0.0-macos-arm64", url="u2"),
                AssetInfo(name="file-organizer-2.0.0-windows-x86_64.exe", url="u3"),
                AssetInfo(name="SHA256SUMS.txt", url="u4"),
            ]
        )
        with (
            patch("platform.system", return_value="Linux"),
            patch("platform.machine", return_value="x86_64"),
        ):
            asset = installer.select_asset(release)
            assert asset is not None
            assert "linux" in asset.name

    def test_select_asset_macos(self) -> None:
        installer = UpdateInstaller()
        release = ReleaseInfo(
            assets=[
                AssetInfo(name="file-organizer-2.0.0-linux-x86_64", url="u1"),
                AssetInfo(name="file-organizer-2.0.0-macos-arm64", url="u2"),
            ]
        )
        with (
            patch("platform.system", return_value="Darwin"),
            patch("platform.machine", return_value="arm64"),
        ):
            asset = installer.select_asset(release)
            assert asset is not None
            assert "macos" in asset.name

    def test_select_asset_macos_prefers_binary_over_dmg(self) -> None:
        installer = UpdateInstaller()
        release = ReleaseInfo(
            assets=[
                AssetInfo(name="file-organizer-2.0.0-macos-arm64.dmg", url="u1"),
                AssetInfo(name="file-organizer-2.0.0-macos-arm64", url="u2"),
            ]
        )
        with (
            patch("platform.system", return_value="Darwin"),
            patch("platform.machine", return_value="arm64"),
        ):
            asset = installer.select_asset(release)
            assert asset is not None
            assert asset.name.endswith("macos-arm64")

    def test_select_asset_no_match(self) -> None:
        installer = UpdateInstaller()
        release = ReleaseInfo(assets=[AssetInfo(name="other-tool.tar.gz", url="u")])
        with (
            patch("platform.system", return_value="Linux"),
            patch("platform.machine", return_value="x86_64"),
        ):
            assert installer.select_asset(release) is None

    def test_select_asset_linux_prefers_appimage(self) -> None:
        installer = UpdateInstaller()
        release = ReleaseInfo(
            assets=[
                AssetInfo(name="file-organizer-2.0.0-linux-x86_64.tar.gz", url="u1"),
                AssetInfo(name="file-organizer-2.0.0-linux-x86_64.AppImage", url="u2"),
            ]
        )
        with (
            patch("platform.system", return_value="Linux"),
            patch("platform.machine", return_value="x86_64"),
        ):
            asset = installer.select_asset(release)
            assert asset is not None
            assert asset.name.endswith(".AppImage")

    def test_select_asset_windows_prefers_non_setup(self) -> None:
        installer = UpdateInstaller()
        release = ReleaseInfo(
            assets=[
                AssetInfo(name="file-organizer-2.0.0-windows-setup.exe", url="u1"),
                AssetInfo(name="file-organizer-2.0.0-windows-x86_64.exe", url="u2"),
            ]
        )
        with (
            patch("platform.system", return_value="Windows"),
            patch("platform.machine", return_value="AMD64"),
        ):
            asset = installer.select_asset(release)
            assert asset is not None
            assert "setup" not in asset.name.lower()

    def test_install_new_binary(self, tmp_path: Path) -> None:
        installer = UpdateInstaller(install_dir=tmp_path)

        # Create a fake "download"
        downloaded = tmp_path / "new-binary"
        downloaded.write_bytes(b"new-content")

        result = installer.install(downloaded, target_name="file-organizer")
        assert result.success is True
        assert (tmp_path / "file-organizer").exists()
        assert (tmp_path / "file-organizer").read_bytes() == b"new-content"

    def test_install_uses_appimage_env(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        appimage = tmp_path / "file-organizer-2.0.0-linux-x86_64.AppImage"
        appimage.write_bytes(b"old-content")
        monkeypatch.setenv("APPIMAGE", str(appimage))
        installer = UpdateInstaller()

        downloaded = tmp_path / "new-appimage"
        downloaded.write_bytes(b"new-content")

        result = installer.install(downloaded, target_name="file-organizer")
        assert result.success is True
        assert appimage.read_bytes() == b"new-content"
        assert (tmp_path / "file-organizer-2.0.0-linux-x86_64.AppImage.bak").exists()

    def test_install_creates_backup(self, tmp_path: Path) -> None:
        installer = UpdateInstaller(install_dir=tmp_path)

        # Create existing binary
        existing = tmp_path / "file-organizer"
        existing.write_bytes(b"old-content")

        # Create download
        downloaded = tmp_path / "new-binary"
        downloaded.write_bytes(b"new-content")

        result = installer.install(downloaded, target_name="file-organizer")
        assert result.success is True
        assert (tmp_path / "file-organizer.bak").read_bytes() == b"old-content"
        assert (tmp_path / "file-organizer").read_bytes() == b"new-content"

    def test_rollback(self, tmp_path: Path) -> None:
        installer = UpdateInstaller(install_dir=tmp_path)

        # Create backup
        (tmp_path / "file-organizer.bak").write_bytes(b"old-content")

        assert installer.rollback() is True
        assert (tmp_path / "file-organizer").read_bytes() == b"old-content"

    def test_rollback_no_backup(self, tmp_path: Path) -> None:
        installer = UpdateInstaller(install_dir=tmp_path)
        assert installer.rollback() is False

    def test_file_sha256(self, tmp_path: Path) -> None:
        f = tmp_path / "test.bin"
        f.write_bytes(b"hello world")
        expected = hashlib.sha256(b"hello world").hexdigest()
        assert UpdateInstaller._file_sha256(f) == expected


# ---------------------------------------------------------------------------
# UpdateManager
# ---------------------------------------------------------------------------


class TestUpdateManager:
    def test_check_no_update(self) -> None:
        mgr = UpdateManager(current_version="99.99.99")
        with patch.object(mgr._checker, "_fetch_latest_release") as mock_fetch:
            mock_fetch.return_value = ReleaseInfo(tag="v2.0.0", version="2.0.0")
            status = mgr.check()
            assert status.available is False

    def test_check_update_available(self) -> None:
        mgr = UpdateManager(current_version="1.0.0")
        with patch.object(mgr._checker, "_fetch_latest_release") as mock_fetch:
            mock_fetch.return_value = ReleaseInfo(tag="v2.0.0", version="2.0.0")
            status = mgr.check()
            assert status.available is True
            assert status.latest_version == "2.0.0"

    def test_status_message_up_to_date(self) -> None:
        s = UpdateStatus(available=False, current_version="2.0.0")
        assert "Up to date" in s.message

    def test_status_message_available(self) -> None:
        s = UpdateStatus(available=True, current_version="1.0.0", latest_version="2.0.0")
        assert "Update available" in s.message

    def test_rollback_delegates(self, tmp_path: Path) -> None:
        mgr = UpdateManager(install_dir=tmp_path)
        (tmp_path / "file-organizer.bak").write_bytes(b"old")
        assert mgr.rollback() is True


# ---------------------------------------------------------------------------
# CLI tests
# ---------------------------------------------------------------------------


class TestUpdateCLI:
    def test_update_help(self) -> None:
        from typer.testing import CliRunner

        from file_organizer.cli.main import app

        runner = CliRunner()
        result = runner.invoke(app, ["update", "--help"])
        assert result.exit_code == 0
        assert "update" in result.output.lower()

    def test_check_help(self) -> None:
        from typer.testing import CliRunner

        from file_organizer.cli.main import app

        runner = CliRunner()
        result = runner.invoke(app, ["update", "check", "--help"])
        assert result.exit_code == 0

    def test_install_help(self) -> None:
        from typer.testing import CliRunner

        from file_organizer.cli.main import app

        runner = CliRunner()
        result = runner.invoke(app, ["update", "install", "--help"])
        assert result.exit_code == 0

    def test_rollback_help(self) -> None:
        from typer.testing import CliRunner

        from file_organizer.cli.main import app

        runner = CliRunner()
        result = runner.invoke(app, ["update", "rollback", "--help"])
        assert result.exit_code == 0
