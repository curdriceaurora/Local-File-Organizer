"""Version management for File Organizer.

This module is the single source of truth for the package version.
It provides utilities for parsing, comparing, and bumping semantic versions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__version__ = "2.0.0"

# Pattern for semantic versioning with optional pre-release and build metadata
_VERSION_PATTERN = re.compile(
    r"^(?P<major>0|[1-9]\d*)"
    r"\.(?P<minor>0|[1-9]\d*)"
    r"\.(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<pre_release>[a-zA-Z0-9]+(?:\.[a-zA-Z0-9]+)*))?$"
)


@dataclass(frozen=True)
class VersionInfo:
    """Structured version information following semantic versioning."""

    major: int
    minor: int
    patch: int
    pre_release: str | None = None

    def __str__(self) -> str:
        """Return the version string."""
        base = f"{self.major}.{self.minor}.{self.patch}"
        if self.pre_release:
            return f"{base}-{self.pre_release}"
        return base

    def __lt__(self, other: object) -> bool:
        """Compare versions for ordering."""
        if not isinstance(other, VersionInfo):
            return NotImplemented
        # Compare major.minor.patch first
        self_tuple = (self.major, self.minor, self.patch)
        other_tuple = (other.major, other.minor, other.patch)
        if self_tuple != other_tuple:
            return self_tuple < other_tuple
        # Pre-release versions have lower precedence than release
        if self.pre_release is None and other.pre_release is None:
            return False
        if self.pre_release is not None and other.pre_release is None:
            return True  # pre-release < release
        if self.pre_release is None and other.pre_release is not None:
            return False  # release > pre-release
        # Both have pre-release, compare lexicographically
        return str(self.pre_release) < str(other.pre_release)

    def __le__(self, other: object) -> bool:
        """Return True if this version is less than or equal to other."""
        if not isinstance(other, VersionInfo):
            return NotImplemented
        return self == other or self < other

    def __gt__(self, other: object) -> bool:
        """Return True if this version is greater than other."""
        if not isinstance(other, VersionInfo):
            return NotImplemented
        return not self <= other

    def __ge__(self, other: object) -> bool:
        """Return True if this version is greater than or equal to other."""
        if not isinstance(other, VersionInfo):
            return NotImplemented
        return not self < other

    @property
    def is_pre_release(self) -> bool:
        """Check if this is a pre-release version."""
        return self.pre_release is not None

    @property
    def base_version(self) -> str:
        """Return version without pre-release suffix."""
        return f"{self.major}.{self.minor}.{self.patch}"


def get_version() -> str:
    """Return the current version string."""
    return __version__


def get_version_info() -> VersionInfo:
    """Return structured version information for the current version."""
    return parse_version(__version__)


def parse_version(version_str: str) -> VersionInfo:
    """Parse a semantic version string into a VersionInfo object.

    Args:
        version_str: A version string like "2.0.0" or "2.0.0-alpha.1".

    Returns:
        A VersionInfo instance with parsed components.

    Raises:
        ValueError: If the version string does not match semantic versioning format.
    """
    match = _VERSION_PATTERN.match(version_str.strip())
    if not match:
        raise ValueError(
            f"Invalid version string: {version_str!r}. "
            f"Expected format: MAJOR.MINOR.PATCH[-PRE_RELEASE]"
        )

    return VersionInfo(
        major=int(match.group("major")),
        minor=int(match.group("minor")),
        patch=int(match.group("patch")),
        pre_release=match.group("pre_release"),
    )


def bump_version(current: str, part: str) -> str:
    """Bump a version string by the specified part.

    Args:
        current: The current version string (e.g., "2.0.0").
        part: Which part to bump: "major", "minor", or "patch".

    Returns:
        The bumped version string. Pre-release suffixes are dropped on bump.

    Raises:
        ValueError: If the part is not one of major/minor/patch or version is invalid.
    """
    info = parse_version(current)

    if part == "major":
        return str(VersionInfo(major=info.major + 1, minor=0, patch=0))
    elif part == "minor":
        return str(VersionInfo(major=info.major, minor=info.minor + 1, patch=0))
    elif part == "patch":
        return str(VersionInfo(major=info.major, minor=info.minor, patch=info.patch + 1))
    else:
        raise ValueError(f"Invalid version part: {part!r}. Must be 'major', 'minor', or 'patch'.")
