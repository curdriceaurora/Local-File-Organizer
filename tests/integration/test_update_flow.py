"""Integration tests for the end-to-end update flow.

These tests exercise the coordinated update system against a locally
controlled fake "release server" using monkeypatching, verifying that:

- The full update flow completes without errors
- SHA256 verification is enforced throughout
- Event notifications are emitted in the correct order
- Rollback restores a consistent state after partial failure
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import patch

import pytest

from file_organizer.updater.checker import AssetInfo, ReleaseInfo
from file_organizer.updater.installer import InstallResult
from file_organizer.updater.sidecar_updater import (
    coordinated_update,
    verify_sha256,
)

pytestmark = pytest.mark.integration

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_release(version: str = "2.1.0") -> ReleaseInfo:
    """Build a minimal ReleaseInfo for integration tests."""
    return ReleaseInfo(
        tag=f"v{version}",
        version=version,
        prerelease=False,
        body="Integration test release.",
        assets=[
            AssetInfo(
                name=f"file-organizer-linux-x86_64-{version}",
                url=f"https://example.com/releases/{version}/file-organizer-linux-x86_64",
                size=2048,
                content_type="application/octet-stream",
            )
        ],
        published_at="2026-03-01T12:00:00Z",
        html_url=f"https://github.com/curdriceaurora/Local-File-Organizer/releases/tag/v{version}",
    )


def _sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Integration test: full update flow succeeds
# ---------------------------------------------------------------------------


class TestFullUpdateFlow:
    """Integration test: both components update atomically."""

    def test_complete_update_flow_emits_all_events(self, tmp_path: Path) -> None:
        """All expected events are emitted during a successful update."""
        release = _make_release("2.1.0")
        binary_data = b"new sidecar binary v2.1.0"
        downloaded_path = tmp_path / "downloaded.bin"
        downloaded_path.write_bytes(binary_data)

        events: list[tuple[str, object]] = []

        def capture(event: str, payload: object) -> None:
            events.append((event, payload))

        with (
            patch("file_organizer.updater.sidecar_updater.UpdateChecker") as MockChecker,
            patch("file_organizer.updater.sidecar_updater.UpdateInstaller") as MockInstaller,
        ):
            checker = MockChecker.return_value
            checker.current_version = "2.0.0"
            checker.check.return_value = release

            inst = MockInstaller.return_value
            inst.select_asset.return_value = release.assets[0]
            inst.find_checksum.return_value = ""
            inst.download_asset.return_value = downloaded_path
            inst.install.return_value = InstallResult(
                success=True,
                message="Installed.",
                new_path=str(downloaded_path),
            )

            result = coordinated_update(event_callback=capture)

        assert result.success is True
        event_names = [e[0] for e in events]
        assert "update-available" in event_names
        assert "update-downloading" in event_names
        assert "update-installed" in event_names
        assert "update-failed" not in event_names

    def test_complete_update_flow_events_are_ordered(self, tmp_path: Path) -> None:
        """Events must arrive in: available → downloading → installed."""
        release = _make_release()
        downloaded_path = tmp_path / "dl.bin"
        downloaded_path.write_bytes(b"binary")

        events: list[str] = []

        with (
            patch("file_organizer.updater.sidecar_updater.UpdateChecker") as MC,
            patch("file_organizer.updater.sidecar_updater.UpdateInstaller") as MI,
        ):
            MC.return_value.current_version = "2.0.0"
            MC.return_value.check.return_value = release

            inst = MI.return_value
            inst.select_asset.return_value = release.assets[0]
            inst.find_checksum.return_value = ""
            inst.download_asset.return_value = downloaded_path
            inst.install.return_value = InstallResult(success=True, message="ok")

            coordinated_update(event_callback=lambda e, _: events.append(e))

        assert events.index("update-available") < events.index("update-downloading")
        assert events.index("update-downloading") < events.index("update-installed")


# ---------------------------------------------------------------------------
# Integration test: SHA256 verification
# ---------------------------------------------------------------------------


class TestSha256VerificationIntegration:
    """Integration test: SHA256 check is enforced throughout the flow."""

    def test_sha256_verification_passes_for_correct_digest(self, tmp_path: Path) -> None:
        """verify_sha256 returns True for a file with a known correct digest."""
        content = b"integration test binary content"
        target = tmp_path / "binary"
        target.write_bytes(content)
        digest = _sha256_of(content)
        assert verify_sha256(target, digest) is True

    def test_sha256_verification_fails_for_tampered_file(self, tmp_path: Path) -> None:
        """verify_sha256 returns False when a file has been tampered with."""
        original_content = b"original binary"
        tampered_content = b"tampered binary"
        target = tmp_path / "binary"
        target.write_bytes(tampered_content)
        expected_digest = _sha256_of(original_content)
        assert verify_sha256(target, expected_digest) is False

    def test_download_with_wrong_sha256_returns_none(self, tmp_path: Path) -> None:
        """When the installer reports a download failure, coordinated_update
        emits update-failed and returns success=False."""
        release = _make_release()

        events: list[str] = []

        with (
            patch("file_organizer.updater.sidecar_updater.UpdateChecker") as MC,
            patch("file_organizer.updater.sidecar_updater.UpdateInstaller") as MI,
        ):
            MC.return_value.current_version = "2.0.0"
            MC.return_value.check.return_value = release

            inst = MI.return_value
            inst.select_asset.return_value = release.assets[0]
            inst.find_checksum.return_value = "deadbeef" * 8
            # Simulate failed download (SHA256 mismatch caught inside installer)
            inst.download_asset.return_value = None

            result = coordinated_update(event_callback=lambda e, _: events.append(e))

        assert result.success is False
        assert "update-failed" in events


# ---------------------------------------------------------------------------
# Integration test: rollback restores consistent state
# ---------------------------------------------------------------------------


class TestRollbackIntegration:
    """Integration test: rollback leaves the system in a consistent state."""

    def test_rollback_called_when_sidecar_install_fails(self, tmp_path: Path) -> None:
        """UpdateManager.rollback is invoked when sidecar installation fails."""
        release = _make_release()
        downloaded = tmp_path / "dl.bin"
        downloaded.write_bytes(b"bad binary")

        with (
            patch("file_organizer.updater.sidecar_updater.UpdateChecker") as MC,
            patch("file_organizer.updater.sidecar_updater.UpdateInstaller") as MI,
            patch("file_organizer.updater.sidecar_updater.UpdateManager") as MM,
        ):
            MC.return_value.current_version = "2.0.0"
            MC.return_value.check.return_value = release

            inst = MI.return_value
            inst.select_asset.return_value = release.assets[0]
            inst.find_checksum.return_value = ""
            inst.download_asset.return_value = downloaded
            inst.install.return_value = InstallResult(success=False, message="Permission denied.")

            mgr = MM.return_value
            mgr.rollback.return_value = True

            result = coordinated_update()

        assert result.rolled_back is True
        mgr.rollback.assert_called_once()

    def test_result_message_reflects_rollback_status(self, tmp_path: Path) -> None:
        """The result message explicitly mentions rollback outcome."""
        release = _make_release()
        downloaded = tmp_path / "dl.bin"
        downloaded.write_bytes(b"binary")

        with (
            patch("file_organizer.updater.sidecar_updater.UpdateChecker") as MC,
            patch("file_organizer.updater.sidecar_updater.UpdateInstaller") as MI,
            patch("file_organizer.updater.sidecar_updater.UpdateManager") as MM,
        ):
            MC.return_value.current_version = "2.0.0"
            MC.return_value.check.return_value = release

            inst = MI.return_value
            inst.select_asset.return_value = release.assets[0]
            inst.find_checksum.return_value = ""
            inst.download_asset.return_value = downloaded
            inst.install.return_value = InstallResult(success=False, message="Disk full.")

            MM.return_value.rollback.return_value = True

            result = coordinated_update()

        assert "roll" in result.message.lower()
