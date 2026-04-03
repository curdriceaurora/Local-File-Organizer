"""Unit tests for the coordinated update system.

Tests cover:
- Both components update together successfully
- Rollback on sidecar failure
- SHA256 verification (pass and fail)
- Update notification events
- Dry-run behaviour
- No-update-available short-circuit
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from file_organizer.updater.checker import AssetInfo, ReleaseInfo
from file_organizer.updater.installer import InstallResult
from file_organizer.updater.sidecar_updater import (
    check_sidecar_update,
    coordinated_update,
    verify_sha256,
)

pytestmark = pytest.mark.unit

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def fake_release() -> ReleaseInfo:
    """A minimal release with one Linux asset and a checksum asset."""
    return ReleaseInfo(
        tag="v2.1.0",
        version="2.1.0",
        prerelease=False,
        body="Bug fixes.",
        assets=[
            AssetInfo(
                name="file-organizer-linux-x86_64",
                url="https://example.com/file-organizer-linux-x86_64",
                size=1024,
                content_type="application/octet-stream",
            ),
        ],
        published_at="2026-03-01T00:00:00Z",
        html_url="https://github.com/curdriceaurora/Local-File-Organizer/releases/tag/v2.1.0",
    )


@pytest.fixture()
def mock_checker_with_update(fake_release: ReleaseInfo) -> Iterator[Any]:
    """Patch UpdateChecker so it always returns ``fake_release``."""
    with patch("file_organizer.updater.sidecar_updater.UpdateChecker") as MockChecker:
        instance = MockChecker.return_value
        instance.current_version = "2.0.0"
        instance.check.return_value = fake_release
        yield MockChecker


@pytest.fixture()
def mock_checker_no_update() -> Iterator[Any]:
    """Patch UpdateChecker so it always returns ``None`` (no update)."""
    with patch("file_organizer.updater.sidecar_updater.UpdateChecker") as MockChecker:
        instance = MockChecker.return_value
        instance.current_version = "2.1.0"
        instance.check.return_value = None
        yield MockChecker


# ---------------------------------------------------------------------------
# Tests for check_sidecar_update
# ---------------------------------------------------------------------------


class TestCheckSidecarUpdate:
    """Tests for :func:`check_sidecar_update`."""

    def test_returns_available_when_update_exists(
        self, mock_checker_with_update, fake_release: ReleaseInfo
    ) -> None:
        status = check_sidecar_update()
        assert status.available is True
        assert status.latest_version == "2.1.0"
        assert status.current_version == "2.0.0"
        assert status.release is fake_release

    def test_returns_not_available_when_up_to_date(self, mock_checker_no_update) -> None:
        status = check_sidecar_update()
        assert status.available is False
        assert status.latest_version == ""
        assert status.release is None

    def test_message_contains_version_when_available(self, mock_checker_with_update) -> None:
        status = check_sidecar_update()
        assert "2.0.0" in status.message
        assert "2.1.0" in status.message

    def test_message_says_up_to_date_when_no_update(self, mock_checker_no_update) -> None:
        status = check_sidecar_update()
        assert "up to date" in status.message.lower()


# ---------------------------------------------------------------------------
# Tests for verify_sha256
# ---------------------------------------------------------------------------


class TestVerifySha256:
    """Tests for :func:`verify_sha256`."""

    def test_correct_digest_returns_true(self, tmp_path: Path) -> None:
        data = b"hello coordinated update"
        f = tmp_path / "payload.bin"
        f.write_bytes(data)
        expected = hashlib.sha256(data).hexdigest()
        assert verify_sha256(f, expected) is True

    def test_wrong_digest_returns_false(self, tmp_path: Path) -> None:
        data = b"hello coordinated update"
        f = tmp_path / "payload.bin"
        f.write_bytes(data)
        assert verify_sha256(f, "deadbeef" * 8) is False

    def test_missing_file_returns_false(self, tmp_path: Path) -> None:
        assert verify_sha256(tmp_path / "nonexistent.bin", "abc123") is False

    def test_digest_is_case_insensitive(self, tmp_path: Path) -> None:
        data = b"case insensitive check"
        f = tmp_path / "file.bin"
        f.write_bytes(data)
        expected = hashlib.sha256(data).hexdigest().upper()
        assert verify_sha256(f, expected) is True


# ---------------------------------------------------------------------------
# Tests for coordinated_update — both components succeed
# ---------------------------------------------------------------------------


class TestCoordinatedUpdateSuccess:
    """Tests for :func:`coordinated_update` when both components update."""

    def _patch_installer(self, fake_release: ReleaseInfo, tmp_path: Path):
        """Return a context manager that patches UpdateInstaller for success."""
        import contextlib

        @contextlib.contextmanager
        def _ctx():
            with patch("file_organizer.updater.sidecar_updater.UpdateInstaller") as MockInstaller:
                inst = MockInstaller.return_value
                inst.select_asset.return_value = fake_release.assets[0]
                inst.find_checksum.return_value = ""
                downloaded = tmp_path / "sidecar.bin"
                downloaded.write_bytes(b"fake binary")
                inst.download_asset.return_value = downloaded
                inst.install.return_value = InstallResult(
                    success=True,
                    message="Installed successfully.",
                    new_path=str(downloaded),
                )
                yield MockInstaller

        return _ctx()

    def test_success_sets_sidecar_updated(
        self, mock_checker_with_update, fake_release: ReleaseInfo, tmp_path: Path
    ) -> None:
        with self._patch_installer(fake_release, tmp_path):
            result = coordinated_update()
        assert result.success is True
        assert result.sidecar_updated is True

    def test_success_records_new_version(
        self, mock_checker_with_update, fake_release: ReleaseInfo, tmp_path: Path
    ) -> None:
        with self._patch_installer(fake_release, tmp_path):
            result = coordinated_update()
        assert result.sidecar_version == "2.1.0"

    def test_update_installed_event_emitted(
        self, mock_checker_with_update, fake_release: ReleaseInfo, tmp_path: Path
    ) -> None:
        received: list[str] = []

        def capture(event: str, _payload: object) -> None:
            received.append(event)

        with self._patch_installer(fake_release, tmp_path):
            coordinated_update(event_callback=capture)

        assert "update-installed" in received

    def test_update_available_event_emitted_first(
        self, mock_checker_with_update, fake_release: ReleaseInfo, tmp_path: Path
    ) -> None:
        received: list[str] = []

        def capture(event: str, _payload: object) -> None:
            received.append(event)

        with self._patch_installer(fake_release, tmp_path):
            coordinated_update(event_callback=capture)

        assert received[0] == "update-available"

    def test_no_update_returns_early_without_events(self, mock_checker_no_update) -> None:
        received: list[str] = []

        def capture(event: str, _payload: object) -> None:
            received.append(event)

        result = coordinated_update(event_callback=capture)
        assert result.success is False
        assert received == []


# ---------------------------------------------------------------------------
# Tests for coordinated_update — sidecar failure triggers rollback
# ---------------------------------------------------------------------------


class TestCoordinatedUpdateRollback:
    """Tests for rollback behaviour when the sidecar install fails."""

    def _setup_failed_install(self, fake_release: ReleaseInfo, tmp_path: Path):
        import contextlib

        @contextlib.contextmanager
        def _ctx():
            with (
                patch("file_organizer.updater.sidecar_updater.UpdateInstaller") as MockInstaller,
                patch("file_organizer.updater.sidecar_updater.UpdateManager") as MockManager,
            ):
                inst = MockInstaller.return_value
                inst.select_asset.return_value = fake_release.assets[0]
                inst.find_checksum.return_value = ""
                downloaded = tmp_path / "sidecar.bin"
                downloaded.write_bytes(b"corrupt binary")
                inst.download_asset.return_value = downloaded
                inst.install.return_value = InstallResult(
                    success=False,
                    message="SHA256 mismatch.",
                )

                mgr = MockManager.return_value
                mgr.rollback.return_value = True

                yield MockInstaller, MockManager

        return _ctx()

    def test_rollback_on_sidecar_failure(
        self, mock_checker_with_update, fake_release: ReleaseInfo, tmp_path: Path
    ) -> None:
        with self._setup_failed_install(fake_release, tmp_path):
            result = coordinated_update()
        assert result.success is False
        assert result.rolled_back is True

    def test_update_failed_event_emitted_on_failure(
        self, mock_checker_with_update, fake_release: ReleaseInfo, tmp_path: Path
    ) -> None:
        received: list[str] = []

        def capture(event: str, _payload: object) -> None:
            received.append(event)

        with self._setup_failed_install(fake_release, tmp_path):
            coordinated_update(event_callback=capture)

        assert "update-failed" in received

    def test_sidecar_not_marked_updated_on_failure(
        self, mock_checker_with_update, fake_release: ReleaseInfo, tmp_path: Path
    ) -> None:
        with self._setup_failed_install(fake_release, tmp_path):
            result = coordinated_update()
        assert result.sidecar_updated is False

    def test_message_mentions_rollback(
        self, mock_checker_with_update, fake_release: ReleaseInfo, tmp_path: Path
    ) -> None:
        with self._setup_failed_install(fake_release, tmp_path):
            result = coordinated_update()
        assert "roll" in result.message.lower()


# ---------------------------------------------------------------------------
# Tests for dry-run mode
# ---------------------------------------------------------------------------


class TestCoordinatedUpdateDryRun:
    """Tests for dry-run behaviour."""

    def test_dry_run_returns_success_without_installing(
        self, mock_checker_with_update, fake_release: ReleaseInfo, tmp_path: Path
    ) -> None:
        with patch("file_organizer.updater.sidecar_updater.UpdateInstaller") as MockInstaller:
            inst = MockInstaller.return_value
            inst.select_asset.return_value = fake_release.assets[0]
            inst.find_checksum.return_value = ""
            downloaded = tmp_path / "sidecar.bin"
            downloaded.write_bytes(b"fake binary")
            inst.download_asset.return_value = downloaded

            result = coordinated_update(dry_run=True)

        assert result.success is True
        # install() must NOT have been called
        inst.install.assert_not_called()

    def test_dry_run_message_mentions_dry_run(
        self, mock_checker_with_update, fake_release: ReleaseInfo, tmp_path: Path
    ) -> None:
        with patch("file_organizer.updater.sidecar_updater.UpdateInstaller") as MockInstaller:
            inst = MockInstaller.return_value
            inst.select_asset.return_value = fake_release.assets[0]
            inst.find_checksum.return_value = ""
            downloaded = tmp_path / "sidecar.bin"
            downloaded.write_bytes(b"x")
            inst.download_asset.return_value = downloaded

            result = coordinated_update(dry_run=True)

        assert "dry run" in result.message.lower()


# ---------------------------------------------------------------------------
# Tests for coordinated_update — no compatible asset
# ---------------------------------------------------------------------------


class TestCoordinatedUpdateNoAsset:
    """Tests for coordinated_update when no compatible asset is found."""

    def test_no_asset_returns_failure(
        self, mock_checker_with_update, fake_release: ReleaseInfo
    ) -> None:
        """Returns failure when select_asset returns None."""
        with patch("file_organizer.updater.sidecar_updater.UpdateInstaller") as MockInstaller:
            inst = MockInstaller.return_value
            inst.select_asset.return_value = None

            result = coordinated_update()

        assert result.success is False
        assert "no compatible" in result.message.lower()
        assert "update-failed" in result.events

    def test_no_asset_emits_update_failed_event(
        self, mock_checker_with_update, fake_release: ReleaseInfo
    ) -> None:
        """Emits update-failed event when no compatible asset found."""
        received: list[str] = []

        def capture(event: str, _payload: object) -> None:
            received.append(event)

        with patch("file_organizer.updater.sidecar_updater.UpdateInstaller") as MockInstaller:
            inst = MockInstaller.return_value
            inst.select_asset.return_value = None

            coordinated_update(event_callback=capture)

        assert "update-failed" in received


# ---------------------------------------------------------------------------
# Tests for coordinated_update — download failure
# ---------------------------------------------------------------------------


class TestCoordinatedUpdateDownloadFailure:
    """Tests for coordinated_update when download fails."""

    def test_download_failure_returns_failure(
        self, mock_checker_with_update, fake_release: ReleaseInfo
    ) -> None:
        """Returns failure when download_asset returns None."""
        with patch("file_organizer.updater.sidecar_updater.UpdateInstaller") as MockInstaller:
            inst = MockInstaller.return_value
            inst.select_asset.return_value = fake_release.assets[0]
            inst.find_checksum.return_value = ""
            inst.download_asset.return_value = None

            result = coordinated_update()

        assert result.success is False
        assert (
            "download failed" in result.message.lower()
            or "verification failed" in result.message.lower()
        )
        assert "update-failed" in result.events

    def test_download_failure_emits_events(
        self, mock_checker_with_update, fake_release: ReleaseInfo
    ) -> None:
        """Emits update-available then update-failed on download failure."""
        received: list[str] = []

        def capture(event: str, _payload: object) -> None:
            received.append(event)

        with patch("file_organizer.updater.sidecar_updater.UpdateInstaller") as MockInstaller:
            inst = MockInstaller.return_value
            inst.select_asset.return_value = fake_release.assets[0]
            inst.find_checksum.return_value = ""
            inst.download_asset.return_value = None

            coordinated_update(event_callback=capture)

        assert "update-available" in received
        assert "update-downloading" in received
        assert "update-failed" in received


# ---------------------------------------------------------------------------
# Tests for coordinated_update — checksum found path
# ---------------------------------------------------------------------------


class TestCoordinatedUpdateWithChecksum:
    """Tests for coordinated_update when checksum is found."""

    def test_checksum_found_logs_prefix(
        self, mock_checker_with_update, fake_release: ReleaseInfo, tmp_path: Path
    ) -> None:
        """When find_checksum returns a hash, it is passed to download_asset."""
        with patch("file_organizer.updater.sidecar_updater.UpdateInstaller") as MockInstaller:
            inst = MockInstaller.return_value
            inst.select_asset.return_value = fake_release.assets[0]
            inst.find_checksum.return_value = "abc123def456" * 4
            downloaded = tmp_path / "sidecar.bin"
            downloaded.write_bytes(b"fake binary")
            inst.download_asset.return_value = downloaded
            inst.install.return_value = InstallResult(success=True, message="Installed.")

            result = coordinated_update()

        assert result.success is True
        inst.download_asset.assert_called_once_with(
            fake_release.assets[0],
            expected_sha256="abc123def456" * 4,
        )


# ---------------------------------------------------------------------------
# Tests for coordinated_update — rollback failure
# ---------------------------------------------------------------------------


class TestCoordinatedUpdateRollbackFailure:
    """Tests when sidecar install fails AND shell rollback also fails."""

    def test_rollback_failure_message(
        self, mock_checker_with_update, fake_release: ReleaseInfo, tmp_path: Path
    ) -> None:
        """Message says rollback also failed when rollback returns False."""
        with (
            patch("file_organizer.updater.sidecar_updater.UpdateInstaller") as MockInstaller,
            patch("file_organizer.updater.sidecar_updater.UpdateManager") as MockManager,
        ):
            inst = MockInstaller.return_value
            inst.select_asset.return_value = fake_release.assets[0]
            inst.find_checksum.return_value = ""
            downloaded = tmp_path / "sidecar.bin"
            downloaded.write_bytes(b"corrupt binary")
            inst.download_asset.return_value = downloaded
            inst.install.return_value = InstallResult(
                success=False,
                message="SHA256 mismatch.",
            )

            mgr = MockManager.return_value
            mgr.rollback.return_value = False

            result = coordinated_update()

        assert result.success is False
        assert result.rolled_back is False
        assert "rollback also failed" in result.message.lower()


# ---------------------------------------------------------------------------
# Tests for verify_sha256 — OSError during read
# ---------------------------------------------------------------------------


class TestVerifySha256OsError:
    """Test verify_sha256 when file read raises OSError."""

    def test_os_error_returns_false(self, tmp_path: Path) -> None:
        """verify_sha256 returns False when file read fails with OSError."""
        f = tmp_path / "file.bin"
        f.write_bytes(b"data")

        with patch.object(Path, "open", side_effect=OSError("permission denied")):
            result = verify_sha256(f, "abc123")

        assert result is False
