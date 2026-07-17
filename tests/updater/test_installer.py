"""Tests for file_organizer.updater.installer module.

Covers InstallResult, UpdateInstaller.download_asset, install, rollback,
select_asset, find_checksum, and internal helpers.
"""

from __future__ import annotations

import hashlib
import shutil
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.updater.checker import AssetInfo, ReleaseInfo
from file_organizer.updater.installer import InstallResult, UpdateInstaller

pytestmark = [pytest.mark.ci, pytest.mark.unit]


# ---------------------------------------------------------------------------
# InstallResult
# ---------------------------------------------------------------------------


@pytest.mark.unit
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


@pytest.mark.unit
class TestInstallerInit:
    """Test UpdateInstaller init."""

    def test_with_explicit_dir(self, tmp_path):
        inst = UpdateInstaller(install_dir=tmp_path)
        assert inst.install_dir == tmp_path

    def test_install_dir_property(self, tmp_path):
        inst = UpdateInstaller(install_dir=tmp_path)
        assert isinstance(inst.install_dir, Path)

    def test_default_install_dir_detection(self):
        """When no install_dir is given, _detect_install_dir finds the Python executable's dir."""
        inst = UpdateInstaller()
        import sys

        expected = Path(sys.executable).resolve().parent
        assert inst.install_dir == expected

    @patch("platform.system", return_value="Darwin")
    def test_pip_upgrade_command_macos(self, _system, monkeypatch):
        monkeypatch.delenv("PIPX_HOME", raising=False)
        monkeypatch.delenv("PIPX_BIN_DIR", raising=False)
        inst = UpdateInstaller()
        command = inst.pip_upgrade_command()
        assert command is not None
        assert command[-4:] == ["-m", "pip", "install", "-U", "local-file-organizer"][-4:]

    @patch("platform.system", return_value="Windows")
    def test_pip_upgrade_command_pipx(self, _system, monkeypatch, tmp_path):
        monkeypatch.setattr(
            sys,
            "executable",
            str(tmp_path / "pipx" / "venvs" / "local-file-organizer" / "bin" / "python"),
        )
        inst = UpdateInstaller()
        assert inst.pip_upgrade_command() == ["pipx", "upgrade", "local-file-organizer"]

    @patch("platform.system", return_value="Darwin")
    def test_pip_upgrade_command_ignores_global_pipx_env(self, _system, monkeypatch, tmp_path):
        monkeypatch.setenv("PIPX_HOME", str(tmp_path / "pipx"))
        monkeypatch.setenv("PIPX_BIN_DIR", str(tmp_path / "bin"))
        inst = UpdateInstaller()
        command = inst.pip_upgrade_command()
        assert command is not None
        assert command[0] == sys.executable
        assert command[1:] == ["-m", "pip", "install", "-U", "local-file-organizer"]

    @patch("platform.system", return_value="Windows")
    def test_pip_upgrade_command_detects_pipx_virtualenv(self, _system, monkeypatch, tmp_path):
        monkeypatch.setenv(
            "VIRTUAL_ENV",
            str(tmp_path / "pipx" / "venvs" / "local-file-organizer"),
        )
        inst = UpdateInstaller()
        assert inst.pip_upgrade_command() == ["pipx", "upgrade", "local-file-organizer"]

    @patch("platform.system", return_value="Linux")
    def test_pip_upgrade_command_linux_none(self, _system):
        inst = UpdateInstaller()
        assert inst.pip_upgrade_command() is None


# ---------------------------------------------------------------------------
# download_asset
# ---------------------------------------------------------------------------


@pytest.mark.unit
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


@pytest.mark.unit
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


@pytest.mark.unit
class TestRollback:
    """Test rollback method."""

    def test_rollback_success(self, tmp_path):
        inst = UpdateInstaller(install_dir=tmp_path)
        backup = tmp_path / "test-app.bak"
        backup.write_bytes(b"old binary")

        with patch("platform.system", return_value="Linux"):
            assert inst.rollback("test-app") is True

    def test_rollback_no_backup(self, tmp_path):
        inst = UpdateInstaller(install_dir=tmp_path)
        with patch("platform.system", return_value="Linux"):
            assert inst.rollback("test-app") is False

    def test_rollback_failure(self, tmp_path):
        inst = UpdateInstaller(install_dir=tmp_path)
        backup = tmp_path / "test-app.bak"
        backup.write_bytes(b"old binary")

        with patch("platform.system", return_value="Linux"):
            with patch("shutil.move", side_effect=OSError("fail")):
                assert inst.rollback("test-app") is False


# ---------------------------------------------------------------------------
# select_asset
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSelectAsset:
    """Test select_asset platform detection."""

    def _make_release(self, asset_names: list[str]) -> ReleaseInfo:
        assets = [AssetInfo(name=n, url=f"https://example.com/{n}") for n in asset_names]
        return ReleaseInfo(tag="v1.0.0", version="1.0.0", assets=assets)

    @patch("platform.system", return_value="Linux")
    @patch("platform.machine", return_value="x86_64")
    def test_select_linux_x64(self, _m, _s):
        inst = UpdateInstaller(install_dir=Path("/") / "tmp")  # noqa: test-hardcoded-paths
        release = self._make_release(
            [
                "app-linux-x86_64.AppImage",
                "app-macos-arm64.zip",
                "SHA256SUMS.txt",
            ]
        )
        asset = inst.select_asset(release)
        assert asset is not None
        assert "linux" in asset.name.lower()

    @patch("platform.system", return_value="Darwin")
    @patch("platform.machine", return_value="arm64")
    def test_select_macos_arm(self, _m, _s):
        inst = UpdateInstaller(install_dir=Path("/") / "tmp")  # noqa: test-hardcoded-paths
        release = self._make_release(
            [
                "app-macos-universal.tar.gz",
                "app-linux-x86_64.AppImage",
            ]
        )
        asset = inst.select_asset(release)
        assert asset is not None
        assert "macos" in asset.name.lower()

    @patch("platform.system", return_value="Windows")
    @patch("platform.machine", return_value="AMD64")
    def test_select_windows(self, _m, _s):
        inst = UpdateInstaller(install_dir=Path("/") / "tmp")  # noqa: test-hardcoded-paths
        release = self._make_release(
            [
                "app-windows-amd64.exe",
                "app-linux-x86_64.AppImage",
            ]
        )
        asset = inst.select_asset(release)
        assert asset is not None
        assert "windows" in asset.name.lower()

    @patch("platform.system", return_value="Linux")
    @patch("platform.machine", return_value="x86_64")
    def test_no_matching_asset(self, _m, _s):
        inst = UpdateInstaller(install_dir=Path("/") / "tmp")  # noqa: test-hardcoded-paths
        release = self._make_release(["app-macos-arm64.zip"])
        asset = inst.select_asset(release)
        assert asset is None

    @patch("platform.system", return_value="Linux")
    @patch("platform.machine", return_value="x86_64")
    def test_skips_checksum_files(self, _m, _s):
        inst = UpdateInstaller(install_dir=Path("/") / "tmp")  # noqa: test-hardcoded-paths
        release = self._make_release(
            [
                "app-linux-x86_64.sha256",
                "app-linux-x86_64.AppImage",
            ]
        )
        asset = inst.select_asset(release)
        assert asset is not None
        assert asset.name.endswith(".AppImage")


# ---------------------------------------------------------------------------
# find_checksum
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFindChecksum:
    """Test find_checksum."""

    @patch.object(UpdateInstaller, "_download_text", return_value="abc123  app.bin")
    def test_dedicated_checksum_file(self, mock_dl):
        inst = UpdateInstaller(install_dir=Path("/") / "tmp")  # noqa: test-hardcoded-paths
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
        return_value="def456  ./app.bin\nghi789  other.bin",
    )
    def test_sha256sums_file(self, mock_dl):
        inst = UpdateInstaller(install_dir=Path("/") / "tmp")  # noqa: test-hardcoded-paths
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
        inst = UpdateInstaller(install_dir=Path("/") / "tmp")  # noqa: test-hardcoded-paths
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


@pytest.mark.unit
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
        inst._appimage_path = Path("/") / "opt" / "app.AppImage"  # noqa: test-hardcoded-paths
        target = inst._resolve_target("my-app")
        assert target == Path("/") / "opt" / "app.AppImage"  # noqa: test-hardcoded-paths


# ---------------------------------------------------------------------------
# _file_sha256
# ---------------------------------------------------------------------------


@pytest.mark.unit
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


@pytest.mark.unit
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


# ---------------------------------------------------------------------------
# _get_platform_hints / _get_arch_hints — branch coverage
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPlatformHints:
    """Test platform/arch hint helpers for branch coverage."""

    @patch("platform.system", return_value="Windows")
    def test_windows_platform_hints(self, _s):
        from file_organizer.updater.installer import _get_platform_hints

        hints = _get_platform_hints()
        assert "windows" in hints
        assert "win" in hints

    @patch("platform.system", return_value="Linux")
    def test_linux_platform_hints(self, _s):
        from file_organizer.updater.installer import _get_platform_hints

        hints = _get_platform_hints()
        assert "linux" in hints

    @patch("platform.machine", return_value="x86_64")
    @patch("platform.system", return_value="Linux")
    def test_x86_64_arch_hints(self, _s, _m):
        from file_organizer.updater.installer import _get_arch_hints

        hints = _get_arch_hints()
        assert "x86_64" in hints
        assert "amd64" in hints
        assert "universal" not in hints

    @patch("platform.machine", return_value="arm64")
    @patch("platform.system", return_value="Darwin")
    def test_arm64_darwin_arch_hints(self, _s, _m):
        from file_organizer.updater.installer import _get_arch_hints

        hints = _get_arch_hints()
        assert "arm64" in hints
        assert "aarch64" in hints
        assert "universal" in hints

    @patch("platform.machine", return_value="riscv64")
    @patch("platform.system", return_value="Linux")
    def test_unknown_arch_hints(self, _s, _m):
        from file_organizer.updater.installer import _get_arch_hints

        hints = _get_arch_hints()
        # No recognized arch, but no universal either (Linux)
        assert hints == []


# ---------------------------------------------------------------------------
# _score_asset — branch coverage for all platforms
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestScoreAsset:
    """Test _score_asset for branch coverage on each platform."""

    @patch("platform.system", return_value="Darwin")
    def test_darwin_dmg_penalty(self, _s):
        from file_organizer.updater.installer import _score_asset

        score = _score_asset("app-macos-arm64.dmg")
        assert score == -5  # dmg penalty

    @patch("platform.system", return_value="Darwin")
    def test_darwin_zip_penalty(self, _s):
        from file_organizer.updater.installer import _score_asset

        score = _score_asset("app-macos-arm64.tar.gz")
        assert score == -3  # .tar.gz penalty

    @patch("platform.system", return_value="Darwin")
    def test_darwin_universal_bonus(self, _s):
        from file_organizer.updater.installer import _score_asset

        score = _score_asset("app-macos-universal")
        assert score == 3  # universal bonus

    @patch("platform.system", return_value="Windows")
    def test_windows_exe_bonus(self, _s):
        from file_organizer.updater.installer import _score_asset

        score = _score_asset("app-windows-amd64.exe")
        assert score == 3

    @patch("platform.system", return_value="Windows")
    def test_windows_installer_penalty(self, _s):
        from file_organizer.updater.installer import _score_asset

        score = _score_asset("app-windows-setup.exe")
        assert score == 3 - 4  # exe bonus + setup penalty

    @patch("platform.system", return_value="Linux")
    def test_linux_appimage_bonus(self, _s):
        from file_organizer.updater.installer import _score_asset

        score = _score_asset("app-linux-x86_64.appimage")
        assert score == 5

    @patch("platform.system", return_value="Linux")
    def test_linux_tarball_bonus(self, _s):
        from file_organizer.updater.installer import _score_asset

        score = _score_asset("app-linux-x86_64.tar.gz")
        assert score == 2


# ---------------------------------------------------------------------------
# install — rollback path when target doesn't exist after failure
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestInstallRollbackPath:
    """Test install rollback when backup exists but target doesn't."""

    def test_install_failure_rollback_restores_backup(self, tmp_path):
        """When install fails and backup exists but target doesn't, rollback moves backup."""
        inst = UpdateInstaller(install_dir=tmp_path)
        target = tmp_path / "test-app"
        target.write_bytes(b"old binary")

        downloaded = tmp_path / "downloaded.bin"
        downloaded.write_bytes(b"new binary")

        call_count = 0
        original_move = shutil.move

        def selective_move(src, dst):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call is the install move — fail it
                # But first remove the target to simulate partial failure
                if target.exists():
                    target.unlink()
                raise OSError("disk full")
            # Second call is the rollback move — let it through
            return original_move(src, dst)

        with patch("shutil.move", side_effect=selective_move):
            # shutil.copy2 for backup step
            with patch("platform.system", return_value="Linux"):
                result = inst.install(downloaded, target_name="test-app")

        assert result.success is False
        assert "disk full" in result.message

    def test_install_on_windows_sets_no_exec_perms(self, tmp_path):
        """On Windows, chmod is not called."""
        inst = UpdateInstaller(install_dir=tmp_path)
        downloaded = tmp_path / "downloaded.bin"
        downloaded.write_bytes(b"new binary content")

        with patch("platform.system", return_value="Windows"):
            result = inst.install(downloaded, target_name="test-app")

        assert result.success is True
        # Windows target has .exe suffix via _resolve_target


# ---------------------------------------------------------------------------
# find_checksum — SHA256SUMS with no matching asset
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFindChecksumEdgeCases:
    """Test find_checksum edge cases for branch coverage."""

    @patch.object(
        UpdateInstaller,
        "_download_text",
        return_value="def456  other.bin\nghi789  another.bin",
    )
    def test_sha256sums_no_match(self, mock_dl):
        """find_checksum returns empty string when SHA256SUMS exists but asset not listed."""
        inst = UpdateInstaller(install_dir=Path("/") / "tmp")  # noqa: test-hardcoded-paths
        release = ReleaseInfo(
            tag="v1",
            version="1.0",
            assets=[
                AssetInfo(name="app.bin", url="https://example.com/app.bin"),
                AssetInfo(name="SHA256SUMS.txt", url="https://example.com/SHA256SUMS.txt"),
            ],
        )
        result = inst.find_checksum(release, "app.bin")
        assert result == ""

    @patch.object(
        UpdateInstaller,
        "_download_text",
        return_value="short",
    )
    def test_sha256sums_short_lines(self, mock_dl):
        """find_checksum handles SHA256SUMS lines with < 2 parts."""
        inst = UpdateInstaller(install_dir=Path("/") / "tmp")  # noqa: test-hardcoded-paths
        release = ReleaseInfo(
            tag="v1",
            version="1.0",
            assets=[
                AssetInfo(name="app.bin", url="https://example.com/app.bin"),
                AssetInfo(name="sha256sums", url="https://example.com/sha256sums"),
            ],
        )
        result = inst.find_checksum(release, "app.bin")
        assert result == ""


# ---------------------------------------------------------------------------
# Trust and Signed Manifest Verification
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestTrustAndManifestVerification:
    """Test signed release manifest verification and trust logic."""

    def test_verify_manifest_success(self, monkeypatch):
        import base64
        import json

        from Cryptodome.PublicKey import ECC
        from Cryptodome.Signature import eddsa

        from file_organizer.updater import trust

        test_key = ECC.generate(curve="ed25519")
        monkeypatch.setattr(
            trust, "PINNED_PUBLIC_KEY", test_key.public_key().export_key(format="PEM")
        )

        manifest = {
            "schema_version": 1,
            "repo": "owner/repo",
            "tag": "v1.0.0",
            "version": "1.0.0",
            "published_at": "2026-07-17T12:00:00Z",
            "assets": [{"name": "asset1.bin", "size": 100, "sha256": "abc123hash"}],
        }
        canonical_bytes = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
        signer = eddsa.new(test_key, "rfc8032")
        sig_bytes = signer.sign(canonical_bytes)
        sig_b64 = base64.b64encode(sig_bytes).decode("utf-8")

        result = trust.verify_release_manifest(
            json.dumps(manifest),
            sig_b64,
            expected_repo="owner/repo",
            expected_tag="v1.0.0",
            expected_version="1.0.0",
        )
        assert result is not None
        assert result["schema_version"] == 1
        assert result["assets"][0]["name"] == "asset1.bin"

    def test_verify_manifest_failures(self, monkeypatch):
        import base64
        import json

        from Cryptodome.PublicKey import ECC
        from Cryptodome.Signature import eddsa

        from file_organizer.updater import trust

        test_key = ECC.generate(curve="ed25519")
        monkeypatch.setattr(
            trust, "PINNED_PUBLIC_KEY", test_key.public_key().export_key(format="PEM")
        )

        manifest = {
            "schema_version": 1,
            "repo": "owner/repo",
            "tag": "v1.0.0",
            "version": "1.0.0",
            "published_at": "2026-07-17T12:00:00Z",
            "assets": [],
        }
        canonical_bytes = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
        signer = eddsa.new(test_key, "rfc8032")
        sig_b64 = base64.b64encode(signer.sign(canonical_bytes)).decode("utf-8")

        # Bad signature
        assert (
            trust.verify_release_manifest(
                json.dumps(manifest), "bad_sig", "owner/repo", "v1.0.0", "1.0.0"
            )
            is None
        )

        # Repo mismatch
        assert (
            trust.verify_release_manifest(
                json.dumps(manifest), sig_b64, "other/repo", "v1.0.0", "1.0.0"
            )
            is None
        )

        # Tag mismatch
        assert (
            trust.verify_release_manifest(
                json.dumps(manifest), sig_b64, "owner/repo", "v2.0.0", "1.0.0"
            )
            is None
        )

        # Version mismatch
        assert (
            trust.verify_release_manifest(
                json.dumps(manifest), sig_b64, "owner/repo", "v1.0.0", "2.0.0"
            )
            is None
        )

        # Schema version mismatch
        manifest_bad_schema = manifest.copy()
        manifest_bad_schema["schema_version"] = 2
        canonical_bytes_bad = json.dumps(
            manifest_bad_schema, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        sig_bad_schema = base64.b64encode(
            eddsa.new(test_key, "rfc8032").sign(canonical_bytes_bad)
        ).decode("utf-8")
        assert (
            trust.verify_release_manifest(
                json.dumps(manifest_bad_schema), sig_bad_schema, "owner/repo", "v1.0.0", "1.0.0"
            )
            is None
        )

    def test_verify_release_manifest_rejects_invalid_manifest_json(self):
        from file_organizer.updater import trust

        with patch.object(trust, "verify_manifest_signature", return_value=True):
            result = trust.verify_release_manifest(
                "{not-json",
                "signature",
                expected_repo="owner/repo",
                expected_tag="v1.0.0",
                expected_version="1.0.0",
            )

        assert result is None

    @patch.object(UpdateInstaller, "_download_text")
    def test_fetch_and_verify_manifest_missing_manifest_asset(self, mock_download):
        inst = UpdateInstaller()
        release = ReleaseInfo(
            tag="v1.0.0",
            version="1.0.0",
            assets=[
                AssetInfo(name="file-organizer-release-manifest.json.sig", url="url2"),
            ],
        )

        assert inst.fetch_and_verify_manifest(release, "owner/repo") is None
        mock_download.assert_not_called()

    @patch.object(UpdateInstaller, "_download_text")
    def test_fetch_and_verify_manifest_rejects_empty_download(self, mock_download):
        inst = UpdateInstaller()
        release = ReleaseInfo(
            tag="v1.0.0",
            version="1.0.0",
            assets=[
                AssetInfo(name="file-organizer-release-manifest.json", url="url1"),
                AssetInfo(name="file-organizer-release-manifest.json.sig", url="url2"),
            ],
        )
        mock_download.side_effect = ["{}", ""]

        assert inst.fetch_and_verify_manifest(release, "owner/repo") is None

    @patch.object(UpdateInstaller, "_download_text")
    def test_fetch_and_verify_manifest_helper(self, mock_download, monkeypatch):
        import base64
        import json

        from Cryptodome.PublicKey import ECC
        from Cryptodome.Signature import eddsa

        from file_organizer.updater import trust

        test_key = ECC.generate(curve="ed25519")
        monkeypatch.setattr(
            trust, "PINNED_PUBLIC_KEY", test_key.public_key().export_key(format="PEM")
        )

        manifest = {
            "schema_version": 1,
            "repo": "owner/repo",
            "tag": "v1.0.0",
            "version": "1.0.0",
            "published_at": "2026-07-17T12:00:00Z",
            "assets": [],
        }
        canonical_bytes = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
        sig_b64 = base64.b64encode(eddsa.new(test_key, "rfc8032").sign(canonical_bytes)).decode(
            "utf-8"
        )

        # Mock download returns manifest and then signature
        mock_download.side_effect = [json.dumps(manifest), sig_b64]

        inst = UpdateInstaller()
        release = ReleaseInfo(
            tag="v1.0.0",
            version="1.0.0",
            assets=[
                AssetInfo(name="file-organizer-release-manifest.json", url="url1"),
                AssetInfo(name="file-organizer-release-manifest.json.sig", url="url2"),
            ],
        )

        res = inst.fetch_and_verify_manifest(release, "owner/repo")
        assert res is not None
        assert res["repo"] == "owner/repo"

    def test_download_asset_with_size_check(self, tmp_path):
        inst = UpdateInstaller(install_dir=tmp_path)
        asset = AssetInfo(name="test.bin", url="https://example.com/test.bin", size=10)

        # Mock httpx.stream to return 15 bytes instead of 10
        mock_response = MagicMock()
        mock_response.iter_bytes.return_value = [b"123456789012345"]

        with patch("httpx.stream") as mock_stream:
            mock_stream.return_value.__enter__.return_value = mock_response
            res = inst.download_asset(asset, expected_size=10)
            assert res is None  # Fails due to size mismatch (too large)

        # Mock httpx.stream to return 5 bytes instead of 10
        mock_response_short = MagicMock()
        mock_response_short.iter_bytes.return_value = [b"12345"]
        with patch("httpx.stream") as mock_stream:
            mock_stream.return_value.__enter__.return_value = mock_response_short
            res = inst.download_asset(asset, expected_size=10)
            assert res is None  # Fails due to size mismatch (too small)
