"""Update installer — downloads, verifies, and atomically replaces binaries.

All operations are designed to be safe: the old binary is backed up before
replacement, and the download is verified via SHA256 before installation.
"""

from __future__ import annotations

import hashlib
import os
import platform
import shutil
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path

import httpx
from loguru import logger

from file_organizer.updater.checker import AssetInfo, ReleaseInfo

_CHUNK_SIZE = 65536  # 64 KB download chunks


@dataclass
class InstallResult:
    """Result of an update installation attempt."""

    success: bool
    message: str
    old_path: str = ""
    new_path: str = ""
    backup_path: str = ""
    sha256: str = ""


class UpdateInstaller:
    """Download and install updates with integrity verification.

    Args:
        install_dir: Directory where the executable lives.
            Defaults to the directory containing the running binary.
    """

    def __init__(self, install_dir: str | Path | None = None) -> None:
        self._install_dir = Path(install_dir) if install_dir else self._detect_install_dir()
        appimage = os.environ.get("APPIMAGE")
        self._appimage_path = Path(appimage) if appimage else None

    @property
    def install_dir(self) -> Path:
        """The installation directory."""
        return self._install_dir

    def download_asset(
        self,
        asset: AssetInfo,
        *,
        expected_sha256: str = "",
        progress_callback: object | None = None,
    ) -> Path | None:
        """Download an asset to a temporary file.

        Args:
            asset: The asset to download.
            expected_sha256: Expected hex digest for verification.
            progress_callback: Optional callable(downloaded, total) for progress.

        Returns:
            Path to the downloaded temp file, or ``None`` on failure.
        """
        logger.info("Downloading {} ({} bytes)...", asset.name, asset.size)

        try:
            tmp = tempfile.NamedTemporaryFile(
                prefix="fo-update-",
                suffix=f"-{asset.name}",
                delete=False,
            )
            tmp_path = Path(tmp.name)

            hasher = hashlib.sha256()
            downloaded = 0

            with httpx.stream("GET", asset.url, follow_redirects=True, timeout=120.0) as resp:
                resp.raise_for_status()
                for chunk in resp.iter_bytes(chunk_size=_CHUNK_SIZE):
                    tmp.write(chunk)
                    hasher.update(chunk)
                    downloaded += len(chunk)
                    if progress_callback is not None and callable(progress_callback):
                        progress_callback(downloaded, asset.size)  # type: ignore[operator]

            tmp.close()

            actual_sha256 = hasher.hexdigest()
            logger.debug("Download complete. SHA256: {}", actual_sha256)

            if expected_sha256 and actual_sha256 != expected_sha256:
                logger.error(
                    "SHA256 mismatch! Expected {} got {}",
                    expected_sha256,
                    actual_sha256,
                )
                tmp_path.unlink(missing_ok=True)
                return None

            return tmp_path

        except Exception as exc:
            logger.error("Download failed: {}", exc)
            return None

    def install(
        self,
        downloaded_path: Path,
        target_name: str = "file-organizer",
    ) -> InstallResult:
        """Atomically replace the existing binary with the downloaded one.

        Steps:
            1. Back up the existing binary.
            2. Move the new binary into place.
            3. Set executable permissions.

        Args:
            downloaded_path: Path to the verified download.
            target_name: Name of the target binary.

        Returns:
            ``InstallResult`` with outcome details.
        """
        target = self._resolve_target(target_name)
        backup = target.with_name(f"{target.name}.bak")

        try:
            # Step 1: Backup
            if target.exists():
                shutil.copy2(str(target), str(backup))
                logger.debug("Backed up {} -> {}", target, backup)

            # Step 2: Atomic move
            shutil.move(str(downloaded_path), str(target))
            logger.debug("Installed new binary: {}", target)

            # Step 3: Permissions
            if platform.system() != "Windows":
                target.chmod(target.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

            # Compute SHA256 of installed file
            sha256 = self._file_sha256(target)

            return InstallResult(
                success=True,
                message=f"Updated successfully: {target}",
                old_path=str(backup) if backup.exists() else "",
                new_path=str(target),
                backup_path=str(backup) if backup.exists() else "",
                sha256=sha256,
            )

        except Exception as exc:
            logger.error("Installation failed: {}", exc)
            # Attempt rollback
            if backup.exists() and not target.exists():
                shutil.move(str(backup), str(target))
                logger.info("Rolled back to previous version")
            return InstallResult(
                success=False,
                message=f"Installation failed: {exc}",
            )

    def rollback(self, target_name: str = "file-organizer") -> bool:
        """Restore the backup binary.

        Args:
            target_name: Name of the binary to restore.

        Returns:
            True if rollback succeeded.
        """
        target = self._resolve_target(target_name)
        backup = target.with_name(f"{target.name}.bak")
        if not backup.exists():
            logger.warning("No backup found at {}", backup)
            return False

        try:
            shutil.move(str(backup), str(target))
            logger.info("Rolled back: {} -> {}", backup, target)
            return True
        except Exception as exc:
            logger.error("Rollback failed: {}", exc)
            return False

    def select_asset(self, release: ReleaseInfo) -> AssetInfo | None:
        """Select the appropriate asset for the current platform.

        Args:
            release: Release with available assets.

        Returns:
            The matching asset, or ``None``.
        """
        system = platform.system().lower()
        machine = platform.machine().lower()

        platform_hints: list[str] = []
        if system == "darwin":
            platform_hints = ["macos", "darwin"]
        elif system == "windows":
            platform_hints = ["windows", "win"]
        else:
            platform_hints = ["linux"]

        arch_hints: list[str] = []
        if machine in ("x86_64", "amd64"):
            arch_hints = ["x86_64", "amd64"]
        elif machine in ("arm64", "aarch64"):
            arch_hints = ["arm64", "aarch64"]

        if system == "darwin":
            arch_hints.append("universal")

        candidates: list[tuple[int, AssetInfo]] = []
        for asset in release.assets:
            name_lower = asset.name.lower()
            # Skip checksum files
            if name_lower.endswith((".sha256", ".md5", ".asc", ".sig")):
                continue
            plat_match = any(h in name_lower for h in platform_hints)
            arch_match = not arch_hints or any(h in name_lower for h in arch_hints)
            if not (plat_match and arch_match):
                continue

            score = 0
            if system == "darwin":
                if "universal" in name_lower:
                    score += 3
                if name_lower.endswith(".dmg"):
                    score -= 5
                if name_lower.endswith((".zip", ".tar.gz", ".tgz")):
                    score -= 3
            elif system == "windows":
                if name_lower.endswith(".exe"):
                    score += 3
                if "setup" in name_lower or "installer" in name_lower:
                    score -= 4
            else:
                if name_lower.endswith(".appimage"):
                    score += 5
                elif name_lower.endswith((".tar.gz", ".tgz")):
                    score += 2

            candidates.append((score, asset))

        if not candidates:
            logger.warning("No matching asset for {}/{}", system, machine)
            return None

        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1]

    def _resolve_target(self, target_name: str) -> Path:
        """Resolve the target path to update based on platform context."""
        if self._appimage_path is not None:
            return self._appimage_path

        target = self._install_dir / target_name
        if platform.system() == "Windows":
            target = target.with_suffix(".exe")
        return target

    def find_checksum(self, release: ReleaseInfo, asset_name: str) -> str:
        """Find the SHA256 checksum for an asset from the release.

        Looks for a ``SHA256SUMS.txt`` or ``<asset>.sha256`` file.

        Args:
            release: Release info.
            asset_name: Name of the asset to find checksum for.

        Returns:
            Hex digest string, or empty string if not found.
        """
        # Look for dedicated checksum file
        for a in release.assets:
            if a.name.lower() == f"{asset_name.lower()}.sha256":
                return self._download_text(a.url).strip().split()[0]

        # Look for SHA256SUMS.txt
        for a in release.assets:
            if a.name.lower() in ("sha256sums.txt", "sha256sums"):
                content = self._download_text(a.url)
                for line in content.splitlines():
                    parts = line.strip().split()
                    if len(parts) >= 2 and asset_name in parts[-1]:
                        return parts[0]

        return ""

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_install_dir() -> Path:
        """Detect the directory containing the running executable."""
        import sys

        exe = Path(sys.executable).resolve()
        return exe.parent

    @staticmethod
    def _file_sha256(path: Path) -> str:
        """Compute SHA256 of a file.

        Args:
            path: File path.

        Returns:
            Hex digest.
        """
        hasher = hashlib.sha256()
        with open(path, "rb") as f:
            while True:
                chunk = f.read(_CHUNK_SIZE)
                if not chunk:
                    break
                hasher.update(chunk)
        return hasher.hexdigest()

    @staticmethod
    def _download_text(url: str) -> str:
        """Download a small text file.

        Args:
            url: URL to download.

        Returns:
            File content as string.
        """
        try:
            resp = httpx.get(url, follow_redirects=True, timeout=15.0)
            resp.raise_for_status()
            return resp.text
        except Exception:
            return ""
