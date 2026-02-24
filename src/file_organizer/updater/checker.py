"""Update checker — queries GitHub Releases API for new versions.

Compares the running version against the latest release and determines
whether an update is available.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import httpx
from loguru import logger

_GITHUB_API = "https://api.github.com"
_DEFAULT_REPO = "curdriceaurora/Local-File-Organizer"
_TIMEOUT = 15.0


@dataclass
class AssetInfo:
    """A downloadable asset from a GitHub release."""

    name: str
    url: str
    size: int = 0
    content_type: str = ""


@dataclass
class ReleaseInfo:
    """Parsed information about a GitHub release.

    Attributes:
        tag: Git tag (e.g. ``v2.0.0``).
        version: Normalised version without ``v`` prefix.
        prerelease: Whether this is a pre-release.
        body: Release notes markdown.
        assets: Downloadable files.
        published_at: ISO timestamp.
        html_url: Link to the release page.
    """

    tag: str = ""
    version: str = ""
    prerelease: bool = False
    body: str = ""
    assets: list[AssetInfo] = field(default_factory=list)
    published_at: str = ""
    html_url: str = ""


def _parse_version(version_str: str) -> tuple[int, ...]:
    """Parse a version string into a comparable tuple.

    Strips leading ``v`` and trailing pre-release labels, then splits
    on ``.``.

    Args:
        version_str: Version string like ``2.0.0-alpha.1`` or ``v2.1.0``.

    Returns:
        Tuple of integers, e.g. ``(2, 0, 0)``.
    """
    clean = re.sub(r"^v", "", version_str)
    # Strip pre-release suffix (everything after first hyphen)
    clean = clean.split("-")[0]
    parts: list[int] = []
    for segment in clean.split("."):
        try:
            parts.append(int(segment))
        except ValueError:
            break
    return tuple(parts) if parts else (0,)


class UpdateChecker:
    """Check GitHub Releases for available updates.

    Args:
        repo: GitHub ``owner/repo`` string.
        current_version: The currently running version.
        include_prereleases: Whether to consider pre-releases.
    """

    def __init__(
        self,
        *,
        repo: str = _DEFAULT_REPO,
        current_version: str = "",
        include_prereleases: bool = False,
    ) -> None:
        """Set up the update checker for the given repository and current version."""
        self._repo = repo
        self._current_version = current_version or self._detect_version()
        self._include_prereleases = include_prereleases

    @property
    def current_version(self) -> str:
        """The version of the running application."""
        return self._current_version

    def check(self) -> ReleaseInfo | None:
        """Query GitHub for the latest release.

        Returns:
            ``ReleaseInfo`` if a newer version is available, else ``None``.
        """
        try:
            release = self._fetch_latest_release()
        except Exception as exc:
            logger.warning("Update check failed: {}", exc)
            return None

        if release is None:
            return None

        current = _parse_version(self._current_version)
        latest = _parse_version(release.version)

        if latest > current:
            logger.info(
                "Update available: {} -> {} ({})",
                self._current_version,
                release.version,
                release.tag,
            )
            return release

        logger.debug("Already up to date: {} >= {}", self._current_version, release.version)
        return None

    def get_latest_release(self) -> ReleaseInfo | None:
        """Fetch the latest release without version comparison.

        Returns:
            ``ReleaseInfo`` or ``None`` on error.
        """
        try:
            return self._fetch_latest_release()
        except Exception as exc:
            logger.warning("Failed to fetch release: {}", exc)
            return None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _fetch_latest_release(self) -> ReleaseInfo | None:
        """Call the GitHub API to get the latest release.

        Returns:
            Parsed ``ReleaseInfo`` or ``None``.
        """
        headers = {"Accept": "application/vnd.github+json"}

        with httpx.Client(timeout=_TIMEOUT) as client:
            if self._include_prereleases:
                url = f"{_GITHUB_API}/repos/{self._repo}/releases"
                resp = client.get(url, headers=headers)
                if resp.status_code == 404:
                    logger.debug("No releases found for {}", self._repo)
                    return None
                resp.raise_for_status()
                data = resp.json()
                if not isinstance(data, list):
                    return None
                for entry in data:
                    if entry.get("draft"):
                        continue
                    # When prereleases are allowed, return the first non-draft
                    # release regardless of its prerelease flag.
                    return self._parse_release(entry)
                return None

            url = f"{_GITHUB_API}/repos/{self._repo}/releases/latest"
            resp = client.get(url, headers=headers)
            if resp.status_code == 404:
                logger.debug("No releases found for {}", self._repo)
                return None
            resp.raise_for_status()
            data = resp.json()

        if not isinstance(data, dict):
            return None
        return self._parse_release(data)

    @staticmethod
    def _parse_release(data: dict[str, Any]) -> ReleaseInfo:
        """Parse a GitHub release JSON response.

        Args:
            data: Raw JSON dict from the API.

        Returns:
            Parsed ``ReleaseInfo``.
        """
        tag = data.get("tag_name", "")
        assets = [
            AssetInfo(
                name=a.get("name", ""),
                url=a.get("browser_download_url", ""),
                size=a.get("size", 0),
                content_type=a.get("content_type", ""),
            )
            for a in data.get("assets", [])
        ]
        return ReleaseInfo(
            tag=tag,
            version=re.sub(r"^v", "", tag),
            prerelease=data.get("prerelease", False),
            body=data.get("body", ""),
            assets=assets,
            published_at=data.get("published_at", ""),
            html_url=data.get("html_url", ""),
        )

    @staticmethod
    def _detect_version() -> str:
        """Detect the current application version.

        Returns:
            Version string from the package metadata.
        """
        try:
            from file_organizer.version import __version__

            return __version__
        except ImportError:
            return "0.0.0"
