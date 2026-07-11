#!/usr/bin/env python3
"""Sync hardcoded version stamps (docs, README, Windows manifest) to ``__version__``.

The package version is single-sourced in ``src/file_organizer/version.py``
(``__version__``), but a handful of other files also carry their own copy of
it for humans or platform tooling to read: doc "**Version**: X.Y.Z" stamps
and the Windows desktop manifest's assembly version. Nothing kept those in
sync, so they drifted independently across release cycles (see #1540 — at
time of filing, version.py said 2.0.2 while README.md and docs/index.md
still said 2.0.0 and 2.0.1). This script is *not* the semantic-version
bumper (that's ``release.py``'s ``bump_version()``, which bumps
major/minor/patch); it only rewrites these stamps to match whatever
``__version__`` already is.

``tests/ci/test_version_drift.py`` fails CI if a stamp disagrees with
``__version__``, using the same ``TOUCHPOINTS`` list as this script so the
two can't drift apart from each other.

Usage:
    python scripts/bump_version.py          # rewrite every stale touchpoint
    python scripts/bump_version.py --check  # exit 1 if any touchpoint is stale; write nothing
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from file_organizer.version import __version__  # noqa: E402


def _same_as_version(version: str) -> str:
    """Default touchpoint formatter: the stamp should read exactly ``__version__``."""
    return version


def _windows_assembly_version(version: str) -> str:
    """Windows assembly versions are 4-part (major.minor.build.revision)."""
    return f"{version}.0"


# Matches the "**Version**: X.Y.Z" stamp used verbatim (optionally inside a
# blockquote, as in docs/tui.md's "> **Version**: X.Y.Z").
_DOC_VERSION_STAMP = re.compile(r"\*\*Version\*\*:\s*(?P<version>\S+)")

# Matches only File Organizer's own <assemblyIdentity> in the Windows
# manifest (not the nested Microsoft.Windows.Common-Controls dependency,
# which is a fixed OS component version and must never be touched).
_WINDOWS_MANIFEST_STAMP = re.compile(
    r'<assemblyIdentity\s+version="(?P<version>[\d.]+)"\s+'
    r'processorArchitecture="\*"\s+name="com\.fileorganizer\.app"'
)


@dataclass(frozen=True)
class Touchpoint:
    """A single hardcoded version stamp somewhere in the repo."""

    path: Path
    pattern: re.Pattern[str] = _DOC_VERSION_STAMP
    expected: Callable[[str], str] = _same_as_version


TOUCHPOINTS: list[Touchpoint] = [
    Touchpoint(REPO_ROOT / "README.md"),
    Touchpoint(REPO_ROOT / "docs" / "index.md"),
    Touchpoint(REPO_ROOT / "docs" / "tui.md"),
    Touchpoint(
        REPO_ROOT / "desktop" / "build" / "app.manifest",
        _WINDOWS_MANIFEST_STAMP,
        _windows_assembly_version,
    ),
]


def find_drift(*, fix: bool, touchpoints: list[Touchpoint] | None = None) -> list[str]:
    """Check every touchpoint against ``__version__``, optionally rewriting stale ones.

    Args:
        fix: If True, rewrite stale touchpoints in place. If False, only report.
        touchpoints: Touchpoints to check. Defaults to ``TOUCHPOINTS``; overridable
            for testing against synthetic files.

    Returns:
        Human-readable description of each stale touchpoint found (before any
        fix was applied). Empty list means everything already matched.

    Raises:
        SystemExit: If a touchpoint file has no recognizable version stamp.
    """
    stale: list[str] = []
    for touchpoint in touchpoints if touchpoints is not None else TOUCHPOINTS:
        text = touchpoint.path.read_text(encoding="utf-8")
        match = touchpoint.pattern.search(text)
        if match is None:
            raise SystemExit(f"error: no version stamp found in {touchpoint.path}")

        current = match.group("version")
        expected = touchpoint.expected(__version__)
        if current == expected:
            continue

        try:
            display_path = touchpoint.path.relative_to(REPO_ROOT)
        except ValueError:
            display_path = touchpoint.path
        stale.append(f"{display_path}: {current} (expected {expected})")

        if fix:
            start, end = match.span("version")
            touchpoint.path.write_text(text[:start] + expected + text[end:], encoding="utf-8")

    return stale


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 if any touchpoint is stale, without writing changes.",
    )
    args = parser.parse_args(argv)

    stale = find_drift(fix=not args.check)

    if not stale:
        print(f"All version touchpoints already match {__version__}.")
        return 0

    if args.check:
        print("Version drift detected:", file=sys.stderr)
        for line in stale:
            print(f"  {line}", file=sys.stderr)
        print("Run `python scripts/bump_version.py` to fix.", file=sys.stderr)
        return 1

    print(f"Updated {len(stale)} version touchpoint(s) to {__version__}:")
    for line in stale:
        print(f"  {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
