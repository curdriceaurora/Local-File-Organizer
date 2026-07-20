#!/usr/bin/env python3
"""Scaffold a release cut without creating the GitHub Release by hand."""

from __future__ import annotations

import argparse
import re
from datetime import UTC, date, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

_VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+(?:[-.][0-9A-Za-z]+(?:[-.][0-9A-Za-z]+)*)?$")
_VERSION_ASSIGNMENT = re.compile(r'(?m)^(__version__\s*=\s*")[^"]+(")')
_PYPROJECT_VERSION = re.compile(r'(?m)^(version\s*=\s*")[^"]+(")')
_CHANGELOG_HEADING = re.compile(r"(?m)^## \[(?P<version>[^\]]+)\]")


def normalize_version(raw: str) -> str:
    """Return a tag-free version string, validating the expected release shape."""
    version = raw.strip()
    if version.startswith("v"):
        version = version[1:]
    if not _VERSION_PATTERN.fullmatch(version):
        raise ValueError(f"Invalid version: {raw!r}")
    return version


def tag_for(version: str) -> str:
    """Return the release tag for *version*."""
    return f"v{normalize_version(version)}"


def _replace_once(path: Path, pattern: re.Pattern[str], version: str) -> bool:
    """Replace the first version assignment matched by *pattern* in *path*."""
    text = path.read_text(encoding="utf-8")
    updated, count = pattern.subn(rf"\g<1>{version}\2", text, count=1)
    if count:
        path.write_text(updated, encoding="utf-8")
    return bool(count)


def update_version_files(version: str, *, root: Path = REPO_ROOT) -> list[Path]:
    """Update package version files and synchronized version touchpoints."""
    normalized = normalize_version(version)
    touched: list[Path] = []
    replacements = [
        (root / "src" / "file_organizer" / "version.py", _VERSION_ASSIGNMENT),
    ]
    for path, pattern in replacements:
        if _replace_once(path, pattern, normalized):
            touched.append(path)
        else:
            raise RuntimeError(
                f"Failed to find version pattern {pattern.pattern!r} in {path.relative_to(root)}"
            )

    # Reuse the drift-sync contract from #1540 for docs and platform stamps.
    import sys

    sys.path.insert(0, str(root / "scripts"))
    import bump_version

    stale = bump_version.find_drift(fix=True)
    if stale:
        touched.extend(t.path for t in bump_version.TOUCHPOINTS)
    return touched


def ensure_changelog_section(
    version: str,
    *,
    changelog: Path = REPO_ROOT / "CHANGELOG.md",
    today: date | None = None,
) -> bool:
    """Insert a placeholder CHANGELOG section for *version* if one is missing."""
    normalized = normalize_version(version)
    text = changelog.read_text(encoding="utf-8")
    if any(match.group("version") == normalized for match in _CHANGELOG_HEADING.finditer(text)):
        return False

    release_date = today or datetime.now(UTC).date()
    marker = "## [Unreleased]\n"
    if marker not in text:
        raise RuntimeError("CHANGELOG.md must contain a '## [Unreleased]' section")
    section = (
        f"{marker}\n"
        f"## [{normalized}] - {release_date.isoformat()}\n\n"
        "### Highlights\n\n"
        "- TODO: add 3-5 bullets summarizing the most impactful changes.\n\n"
        "### Changed\n\n"
        "- TODO: summarize the user-visible changes for this release.\n"
    )
    changelog.write_text(text.replace(marker, section, 1), encoding="utf-8")
    return True


def release_commands(version: str) -> list[str]:
    """Return the final manual commands for publishing the tag-triggered release."""
    tag = tag_for(version)
    return [
        "python scripts/bump_version.py --check",
        f"python scripts/extract_changelog.py {tag} > local-file-organizer-{tag}-notes.md",
        f"git tag -a {tag} -m 'Release {tag}'",
        f"git push origin {tag}",
    ]


def main(argv: list[str] | None = None) -> int:
    """Run the release-cut scaffolding CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", help="Release version, with or without leading 'v'")
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="Only print the release commands; do not update files.",
    )
    args = parser.parse_args(argv)

    version = normalize_version(args.version)
    if not args.no_write:
        touched = update_version_files(version)
        changelog_changed = ensure_changelog_section(version)
        for path in touched:
            print(f"updated {path.relative_to(REPO_ROOT)}")
        if changelog_changed:
            print("updated CHANGELOG.md")

    print("\nDo not hand-create the GitHub Release.")
    print("Push the tag and let .github/workflows/build.yml create the draft with assets:\n")
    for command in release_commands(version):
        print(f"  {command}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
