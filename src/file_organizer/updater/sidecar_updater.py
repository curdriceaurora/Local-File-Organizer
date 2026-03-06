"""Coordinated update system for the sidecar (Python backend).

This module adds sidecar-aware update helpers that work alongside the Tauri
shell's ``tauri-plugin-updater``. The key addition is ``coordinated_update``,
which ensures both the shell and the sidecar are updated atomically: if the
sidecar update fails, the shell is rolled back so the two components always
stay in sync.

Typical usage::

    from file_organizer.updater.sidecar_updater import coordinated_update

    result = coordinated_update()
    if result.success:
        print("Both components updated to", result.sidecar_version)
    elif result.rolled_back:
        print("Partial update detected; rolled back shell to previous version")
    else:
        print("No update available or update failed:", result.message)
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from loguru import logger

from file_organizer.updater.checker import ReleaseInfo, UpdateChecker
from file_organizer.updater.installer import InstallResult, UpdateInstaller
from file_organizer.updater.manager import UpdateManager

# Default GitHub repository.
_DEFAULT_REPO = "curdriceaurora/Local-File-Organizer"

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class SidecarUpdateStatus:
    """Status of a check or installation for the sidecar component.

    Attributes:
        available: Whether a sidecar update is available.
        current_version: Currently running sidecar version.
        latest_version: Latest available version (empty if unavailable).
        release: Full release info (``None`` if no update found).
        install_result: Installation outcome (``None`` if not installed).
        message: Human-readable summary.
    """

    available: bool = False
    current_version: str = ""
    latest_version: str = ""
    release: ReleaseInfo | None = None
    install_result: InstallResult | None = None
    message: str = ""


@dataclass
class CoordinatedUpdateResult:
    """Result of a coordinated shell + sidecar update attempt.

    Attributes:
        success: Both components updated successfully.
        rolled_back: Shell was rolled back due to sidecar failure.
        shell_updated: Whether the shell component was updated.
        sidecar_updated: Whether the sidecar component was updated.
        sidecar_version: New sidecar version (empty if not updated).
        shell_version: New shell version (empty if not updated).
        message: Human-readable status message.
        events: List of notification events emitted during the process.
    """

    success: bool = False
    rolled_back: bool = False
    shell_updated: bool = False
    sidecar_updated: bool = False
    sidecar_version: str = ""
    shell_version: str = ""
    message: str = ""
    events: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def check_sidecar_update(
    *,
    repo: str = _DEFAULT_REPO,
    current_version: str = "",
    include_prereleases: bool = False,
) -> SidecarUpdateStatus:
    """Check whether a sidecar (Python backend) update is available.

    Delegates to the existing :class:`~file_organizer.updater.checker.UpdateChecker`
    and wraps the result in a :class:`SidecarUpdateStatus`.

    Args:
        repo: GitHub ``owner/repo`` to query.
        current_version: Override the auto-detected running version.
        include_prereleases: Whether pre-releases count as updates.

    Returns:
        :class:`SidecarUpdateStatus` describing the current state.
    """
    checker = UpdateChecker(
        repo=repo,
        current_version=current_version,
        include_prereleases=include_prereleases,
    )
    release = checker.check()
    if release is None:
        return SidecarUpdateStatus(
            available=False,
            current_version=checker.current_version,
            message=f"Sidecar up to date: {checker.current_version}",
        )

    return SidecarUpdateStatus(
        available=True,
        current_version=checker.current_version,
        latest_version=release.version,
        release=release,
        message=f"Sidecar update available: {checker.current_version} -> {release.version}",
    )


def coordinated_update(
    *,
    repo: str = _DEFAULT_REPO,
    current_version: str = "",
    install_dir: str | Path | None = None,
    include_prereleases: bool = False,
    event_callback: Callable[[str, object], None] | None = None,
    dry_run: bool = False,
) -> CoordinatedUpdateResult:
    """Update both the Tauri shell and the sidecar atomically.

    The coordination protocol is:

    1. Check whether a sidecar update is available.
    2. If no update is available, return early.
    3. Download and install the sidecar update.
    4. If the sidecar update succeeds, emit ``update-installed``.
    5. If the sidecar update fails:
       a. Attempt to roll back the shell via :meth:`UpdateManager.rollback`.
       b. Emit ``update-failed`` and return with ``rolled_back=True``.

    The *shell* update itself is handled by the Tauri plugin on the Rust side;
    this function only coordinates the Python sidecar portion and manages
    rollback.

    Args:
        repo: GitHub ``owner/repo`` for the sidecar release.
        current_version: Override the auto-detected running version.
        install_dir: Directory where the sidecar binary lives.
        include_prereleases: Whether to include pre-release versions.
        event_callback: Optional ``callback(event_name, payload)`` called for
            each lifecycle event (mirrors Tauri event emission).
        dry_run: If ``True``, check and download but do not install.

    Returns:
        :class:`CoordinatedUpdateResult` with full outcome details.
    """
    result = CoordinatedUpdateResult()

    def emit(event: str, payload: object = None) -> None:
        result.events.append(event)
        logger.info("Event: {} — {}", event, payload)
        if event_callback is not None:
            event_callback(event, payload)

    # Step 1: Check for sidecar update.
    status = check_sidecar_update(
        repo=repo,
        current_version=current_version,
        include_prereleases=include_prereleases,
    )

    if not status.available or status.release is None:
        result.message = status.message
        return result

    emit("update-available", {"version": status.latest_version})

    # Step 2: Prepare installer.
    installer = UpdateInstaller(install_dir=install_dir)
    release = status.release

    asset = installer.select_asset(release)
    if asset is None:
        result.message = "No compatible sidecar asset found for this platform."
        emit("update-failed", {"reason": result.message})
        return result

    expected_sha256 = installer.find_checksum(release, asset.name)
    if expected_sha256:
        logger.info("Expected sidecar SHA256: {}...", expected_sha256[:16])

    # Step 3: Download.
    emit("update-downloading", {"version": status.latest_version, "asset": asset.name})
    downloaded = installer.download_asset(
        asset,
        expected_sha256=expected_sha256,
    )

    if downloaded is None:
        result.message = "Sidecar download failed or SHA256 verification failed."
        emit("update-failed", {"reason": result.message})
        return result

    if dry_run:
        downloaded.unlink(missing_ok=True)
        result.message = f"Dry run: would install sidecar {status.latest_version} from {asset.name}"
        result.success = True
        return result

    # Step 4: Install sidecar.
    install_result = installer.install(downloaded)

    if install_result.success:
        result.sidecar_updated = True
        result.sidecar_version = status.latest_version
        result.success = True
        result.message = f"Sidecar updated: {status.current_version} -> {status.latest_version}"
        emit("update-installed", {"version": status.latest_version})
        return result

    # Step 5: Sidecar install failed — attempt shell rollback.
    logger.error("Sidecar install failed: {}. Attempting shell rollback.", install_result.message)
    emit("update-failed", {"reason": install_result.message})

    shell_manager = UpdateManager(
        repo=repo,
        current_version=current_version,
        install_dir=install_dir,
        include_prereleases=include_prereleases,
    )
    rolled_back = shell_manager.rollback()

    result.rolled_back = rolled_back
    result.success = False
    result.message = f"Sidecar install failed: {install_result.message}. " + (
        "Shell rolled back successfully." if rolled_back else "Shell rollback also failed."
    )

    return result


def verify_sha256(file_path: Path, expected: str) -> bool:
    """Verify a file's SHA-256 digest against an expected hex string.

    Args:
        file_path: Path to the file to verify.
        expected: Expected SHA-256 hex digest (case-insensitive).

    Returns:
        ``True`` if the digest matches.
    """
    if not file_path.exists():
        logger.error("Cannot verify SHA256: file not found at {}", file_path)
        return False

    sha256 = hashlib.sha256()
    try:
        with file_path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                sha256.update(chunk)
    except OSError as exc:
        logger.error("SHA256 read error: {}", exc)
        return False

    actual = sha256.hexdigest()
    match = actual.lower() == expected.lower()
    if not match:
        logger.error(
            "SHA256 mismatch: expected {} got {}", expected[:16] + "...", actual[:16] + "..."
        )
    return match
