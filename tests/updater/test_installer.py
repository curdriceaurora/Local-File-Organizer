"""Tests for file_organizer.updater.installer module.

Covers InstallResult, UpdateInstaller.download_asset, install, rollback,
select_asset, find_checksum, and internal helpers.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.updater.checker import AssetInfo, ReleaseInfo
from file_organizer.updater.installer import InstallResult, UpdateInstaller

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# InstallResult
# ---------------------------------------------------------------------------


class TestInstallResult:
    """Test InstallResult dataclass."""

    def test_defaults(self):
        r = InstallResult(success=True, message="ok")
        assert r.success is True
        assert r.old_path == ""
        assert r.sha256 == ""

    def test_full(self):
        r = InstallResult(
            success=False,
            message="fail",
            old_path="/old",
            new_path="/new",
            backup_path="/bak",
            sha256="abc123",
        )
        assert r.backup_path == "/bak"


# ---------------------------------------------------------------------------
# UpdateInstaller.__init__
# ---------------------------------------------------------------------------


class TestInstallerInit:
    """Test UpdateInstaller init."""

    def test_with_explicit_dir(self, tmp_path):
        inst = UpdateInstaller(install_dir=tmp_path)
        assert inst.install_dir == tmp_path

    def test_install_dir_property(self, tmp_path):
        inst = UpdateInstaller(install_dir=tmp_path)
        assert isinstance(inst.install_dir, Path)


# ---------------------------------------------------------------------------
# download_asset
# ---------------------------------------------------------------------------


class TestDownloadAsset:
    """Test download_asset method."""

    @patch("file_organizer.updater.installer.httpx")
    def test_download_success(self, mock_httpx, tmp_path):
        asset = AssetInfo(name="app.bin", url="https://example.com/app.bin", size=100)
        inst = UpdateInstaller(install_dir=tmp_path)

        # Set up streaming mock
        mock_resp = MagicMock()
        mock_resp.iter_bytes.return_value = [b"data_chunk"]
        mock_resp.raise_for_status.return_value = None
        mock_cm = MagicMock()
        mock_cm.__enter__ = MagicMock(return_value=mock_resp)
        mock_cm.__exit__ = MagicMock(return_value=False)
        mock_httpx.stream.return_value = mock_cm

        result = inst.download_asset(asset)
        assert result is not None
        assert result.exists()
        result.unlink()

    @patch("file_organizer.updater.installer.httpx")
    def test_download_sha_mismatch(self, mock_httpx, tmp_path):
        asset = AssetInfo(name="app.bin", url="https://example.com/app.bin", size=100)
        inst = UpdateInstaller(install_dir=tmp_path)

        mock_resp = MagicMock()
        mock_resp.iter_bytes.return_value = [b"data"]
        mock_resp.raise_for_status.return_value = None
        mock_cm = MagicMock()
        mock_cm.__enter__ = MagicMock(return_value=mock_resp)
        mock_cm.__exit__ = MagicMock(return_value=False)
        mock_httpx.stream.return_value = mock_cm

        result = inst.download_asset(asset, expected_sha256="wrong_sha")
        assert result is None

    @patch("file_organizer.updater.installer.httpx")
    def test_download_with_callback(self, mock_httpx, tmp_path):
        asset = AssetInfo(name="app.bin", url="https://example.com/app.bin", size=100)
        inst = UpdateInstaller(install_dir=tmp_path)
        callback = MagicMock()

        mock_resp = MagicMock()
        mock_resp.iter_bytes.return_value = [b"data"]
        mock_resp.raise_for_status.return_value = None
        mock_cm = MagicMock()
        mock_cm.__enter__ = MagicMock(return_value=mock_resp)
        mock_cm.__exit__ = MagicMock(return_value=False)
        mock_httpx.stream.return_value = mock_cm

        result = inst.download_asset(asset, progress_callback=callback)
        assert result is not None
        callback.assert_called_once()
        result.unlink()

    @patch("file_organizer.updater.installer.httpx")
    def test_download_network_error(self, mock_httpx, tmp_path):
        asset = AssetInfo(name="app.bin", url="https://example.com/app.bin", size=100)
        inst = UpdateInstaller(install_dir=tmp_path)
        mock_httpx.stream.side_effect = Exception("network error")
        result = inst.download_asset(asset)
        assert result is None


# ---------------------------------------------------------------------------
# install
# ---------------------------------------------------------------------------


class TestInstall:
    """Test install method."""

    def test_install_success(self, tmp_path):
        inst = UpdateInstaller(install_dir=tmp_path)
        downloaded = tmp_path / "downloaded.bin"
        downloaded.write_bytes(b"new binary content")

        with patch("platform.system", return_value="Linux"):
            result = inst.install(downloaded, target_name="test-app")

        assert result.success is True
        assert "Updated successfully" in result.message
        target = tmp_path / "test-app"
        assert target.exists()

    def test_install_with_backup(self, tmp_path):
        inst = UpdateInstaller(install_dir=tmp_path)
        # Create existing binary
        target = tmp_path / "test-app"
        target.write_bytes(b"old binary")

        downloaded = tmp_path / "downloaded.bin"
        downloaded.write_bytes(b"new binary")

        with patch("platform.system", return_value="Linux"):
            result = inst.install(downloaded, target_name="test-app")

        assert result.success is True
        backup = tmp_path / "test-app.bak"
        assert backup.exists()

    def test_install_failure_with_rollback(self, tmp_path):
        inst = UpdateInstaller(install_dir=tmp_path)
        # Create existing binary and backup
        target = tmp_path / "test-app"
        target.write_bytes(b"old binary")

        downloaded = tmp_path / "downloaded.bin"
        downloaded.write_bytes(b"new binary")

        with patch("shutil.move", side_effect=Exception("move failed")):
            with patch("shutil.copy2"):
                with patch("platform.system", return_value="Linux"):
                    result = inst.install(downloaded, target_name="test-app")

        assert result.success is False


# ---------------------------------------------------------------------------
# rollback
# ---------------------------------------------------------------------------


class TestRollback:
    """Test rollback method."""

    def test_rollback_success(self, tmp_path):
        inst = UpdateInstaller(install_dir=tmp_path)
        backup = tmp_path / "test-app.bak"
        backup.write_bytes(b"old binary")

        assert inst.rollback("test-app") is True

    def test_rollback_no_backup(self, tmp_path):
        inst = UpdateInstaller(install_dir=tmp_path)
        assert inst.rollback("test-app") is False

    def test_rollback_failure(self, tmp_path):
        inst = UpdateInstaller(install_dir=tmp_path)
        backup = tmp_path / "test-app.bak"
        backup.write_bytes(b"old binary")

        with patch("shutil.move", side_effect=OSError("fail")):
            assert inst.rollback("test-app") is False


# ---------------------------------------------------------------------------
# select_asset
# ---------------------------------------------------------------------------


class TestSelectAsset:
    """Test select_asset platform detection."""

    def _make_release(self, asset_names: list[str]) -> ReleaseInfo:
        assets = [AssetInfo(name=n, url=f"https://example.com/{n}") for n in asset_names]
        return ReleaseInfo(tag="v1.0.0", version="1.0.0", assets=assets)

    @patch("platform.system", return_value="Linux")
    @patch("platform.machine", return_value="x86_64")
    def test_select_linux_x64(self, _m, _s):
        inst = UpdateInstaller(install_dir=Path("/tmp"))
        release = self._make_release([
            "app-linux-x86_64.AppImage",
            "app-macos-arm64.zip",
            "SHA256SUMS.txt",
        ])
        asset = inst.select_asset(release)
        assert asset is not None
        assert "linux" in asset.name.lower()

    @patch("platform.system", return_value="Darwin")
    @patch("platform.machine", return_value="arm64")
    def test_select_macos_arm(self, _m, _s):
        inst = UpdateInstaller(install_dir=Path("/tmp"))
        release = self._make_release([
            "app-macos-universal.tar.gz",
            "app-linux-x86_64.AppImage",
        ])
        asset = inst.select_asset(release)
        assert asset is not None
        assert "macos" in asset.name.lower()

    @patch("platform.system", return_value="Windows")
    @patch("platform.machine", return_value="AMD64")
    def test_select_windows(self, _m, _s):
        inst = UpdateInstaller(install_dir=Path("/tmp"))
        release = self._make_release([
            "app-windows-amd64.exe",
            "app-linux-x86_64.AppImage",
        ])
        asset = inst.select_asset(release)
        assert asset is not None
        assert "windows" in asset.name.lower()

    @patch("platform.system", return_value="Linux")
    @patch("platform.machine", return_value="x86_64")
    def test_no_matching_asset(self, _m, _s):
        inst = UpdateInstaller(install_dir=Path("/tmp"))
        release = self._make_release(["app-macos-arm64.zip"])
        asset = inst.select_asset(release)
        assert asset is None

    @patch("platform.system", return_value="Linux")
    @patch("platform.machine", return_value="x86_64")
    def test_skips_checksum_files(self, _m, _s):
        inst = UpdateInstaller(install_dir=Path("/tmp"))
        release = self._make_release([
            "app-linux-x86_64.sha256",
            "app-linux-x86_64.AppImage",
        ])
        asset = inst.select_asset(release)
        assert asset is not None
        assert asset.name.endswith(".AppImage")


# ---------------------------------------------------------------------------
# find_checksum
# ---------------------------------------------------------------------------


class TestFindChecksum:
    """Test find_checksum."""

    @patch.object(UpdateInstaller, "_download_text", return_value="abc123  app.bin")
    def test_dedicated_checksum_file(self, mock_dl):
        inst = UpdateInstaller(install_dir=Path("/tmp"))
        release = ReleaseInfo(
            tag="v1",
            version="1.0",
            assets=[
                AssetInfo(name="app.bin", url="https://example.com/app.bin"),
                AssetInfo(name="app.bin.sha256", url="https://example.com/app.bin.sha256"),
            ],
        )
        result = inst.find_checksum(release, "app.bin")
        assert result == "abc123"

    @patch.object(
        UpdateInstaller,
        "_download_text",
        return_value="def456  app.bin\nghi789  other.bin",
    )
    def test_sha256sums_file(self, mock_dl):
        inst = UpdateInstaller(install_dir=Path("/tmp"))
        release = ReleaseInfo(
            tag="v1",
            version="1.0",
            assets=[
                AssetInfo(name="app.bin", url="https://example.com/app.bin"),
                AssetInfo(name="SHA256SUMS.txt", url="https://example.com/SHA256SUMS.txt"),
            ],
        )
        result = inst.find_checksum(release, "app.bin")
        assert result == "def456"

    def test_no_checksum_file(self):
        inst = UpdateInstaller(install_dir=Path("/tmp"))
        release = ReleaseInfo(
            tag="v1",
            version="1.0",
            assets=[AssetInfo(name="app.bin", url="https://example.com/app.bin")],
        )
        result = inst.find_checksum(release, "app.bin")
        assert result == ""


# ---------------------------------------------------------------------------
# _resolve_target
# ---------------------------------------------------------------------------


class TestResolveTarget:
    """Test _resolve_target method."""

    def test_normal_target(self, tmp_path):
        inst = UpdateInstaller(install_dir=tmp_path)
        with patch("platform.system", return_value="Linux"):
            target = inst._resolve_target("my-app")
        assert target == tmp_path / "my-app"

    def test_windows_target(self, tmp_path):
        inst = UpdateInstaller(install_dir=tmp_path)
        with patch("platform.system", return_value="Windows"):
            target = inst._resolve_target("my-app")
        assert target == tmp_path / "my-app.exe"

    def test_appimage_target(self, tmp_path):
        inst = UpdateInstaller(install_dir=tmp_path)
        inst._appimage_path = Path("/opt/app.AppImage")
        target = inst._resolve_target("my-app")
        assert target == Path("/opt/app.AppImage")


# ---------------------------------------------------------------------------
# _file_sha256
# ---------------------------------------------------------------------------


class TestFileSha256:
    """Test _file_sha256 static method."""

    def test_computes_hash(self, tmp_path):
        f = tmp_path / "test.bin"
        f.write_bytes(b"hello world")
        expected = hashlib.sha256(b"hello world").hexdigest()
        assert UpdateInstaller._file_sha256(f) == expected


# ---------------------------------------------------------------------------
# _download_text
# ---------------------------------------------------------------------------


class TestDownloadText:
    """Test _download_text static method."""

    @patch("file_organizer.updater.installer.httpx")
    def test_success(self, mock_httpx):
        mock_resp = MagicMock()
        mock_resp.text = "file content"
        mock_httpx.get.return_value = mock_resp
        result = UpdateInstaller._download_text("https://example.com/file.txt")
        assert result == "file content"

    @patch("file_organizer.updater.installer.httpx")
    def test_failure(self, mock_httpx):
        mock_httpx.get.side_effect = Exception("error")
        result = UpdateInstaller._download_text("https://example.com/file.txt")
        assert result == ""
