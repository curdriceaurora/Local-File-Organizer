"""Update manager — high-level orchestrator for the auto-update flow.

Ties together the checker and installer into a single ``update()`` call.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from loguru import logger

from file_organizer.updater.checker import ReleaseInfo, UpdateChecker
from file_organizer.updater.installer import InstallResult, UpdateInstaller


@dataclass
class UpdateStatus:
    """Status report from an update check or installation.

    Attributes:
        available: Whether an update is available.
        current_version: The running version.
        latest_version: The latest available version (empty if N/A).
        release: Full release info (None if no update).
        install_result: Result of installation (None if not installed).
    """

    available: bool = False
    current_version: str = ""
    latest_version: str = ""
    release: ReleaseInfo | None = None
    install_result: InstallResult | None = None

    @property
    def message(self) -> str:
        """Human-readable status message."""
        if self.install_result is not None:
            return self.install_result.message
        if self.available:
            return f"Update available: {self.current_version} -> {self.latest_version}"
        return f"Up to date: {self.current_version}"


class UpdateManager:
    """High-level auto-update orchestrator.

    Usage::

        mgr = UpdateManager()
        status = mgr.check()
        if status.available:
            status = mgr.update()

    Args:
        repo: GitHub ``owner/repo`` string.
        current_version: Override the detected version.
        install_dir: Override the installation directory.
        include_prereleases: Whether to consider pre-releases.
    """

    def __init__(
        self,
        *,
        repo: str = "curdriceaurora/Local-File-Organizer",
        current_version: str = "",
        install_dir: str | Path | None = None,
        include_prereleases: bool = False,
    ) -> None:
        """Set up the update manager for the given repository and current version."""
        self._checker = UpdateChecker(
            repo=repo,
            current_version=current_version,
            include_prereleases=include_prereleases,
        )
        self._installer = UpdateInstaller(install_dir=install_dir)

    @property
    def current_version(self) -> str:
        """The running version."""
        return self._checker.current_version

    def check(self) -> UpdateStatus:
        """Check for available updates without installing.

        Returns:
            ``UpdateStatus`` with availability info.
        """
        release = self._checker.check()
        if release is None:
            return UpdateStatus(
                available=False,
                current_version=self._checker.current_version,
            )

        return UpdateStatus(
            available=True,
            current_version=self._checker.current_version,
            latest_version=release.version,
            release=release,
        )

    def update(self, *, dry_run: bool = False) -> UpdateStatus:
        """Check for and install an update.

        Args:
            dry_run: If True, check and download but don't install.

        Returns:
            ``UpdateStatus`` with full result.
        """
        status = self.check()
        if not status.available or status.release is None:
            return status

        release = status.release

        # Select platform asset
        asset = self._installer.select_asset(release)
        if asset is None:
            status.install_result = InstallResult(
                success=False,
                message="No compatible binary found for this platform.",
            )
            return status

        logger.info("Selected asset: {} ({} bytes)", asset.name, asset.size)

        # Find checksum
        expected_sha256 = self._installer.find_checksum(release, asset.name)
        if expected_sha256:
            logger.info("Expected SHA256: {}", expected_sha256[:16] + "...")

        # Download
        downloaded = self._installer.download_asset(
            asset,
            expected_sha256=expected_sha256,
        )
        if downloaded is None:
            status.install_result = InstallResult(
                success=False,
                message="Download failed or checksum mismatch.",
            )
            return status

        if dry_run:
            downloaded.unlink(missing_ok=True)
            status.install_result = InstallResult(
                success=True,
                message=f"Dry run: would install {asset.name} ({release.version})",
            )
            return status

        # Install
        result = self._installer.install(downloaded)
        status.install_result = result
        return status

    def rollback(self) -> bool:
        """Rollback to the previous version.

        Returns:
            True if rollback succeeded.
        """
        return self._installer.rollback()
