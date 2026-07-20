#!/usr/bin/env python3
"""Extract a single version's section from ``CHANGELOG.md``.

Used by the release workflow to build the GitHub Release body from the curated
changelog (Keep a Changelog format) instead of relying solely on auto-generated
notes. Prints the section body (without its ``## [version]`` heading) to stdout.

Usage:
    python scripts/extract_changelog.py 2.0.0
    python scripts/extract_changelog.py v2.0.0 --changelog CHANGELOG.md
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def _normalize_version(version: str) -> str:
    """Strip a leading ``v`` from a tag name (``v2.0.0`` -> ``2.0.0``)."""
    return version[1:] if version.startswith("v") else version


def extract_section(changelog: str, version: str) -> str:
    """Return the body of the ``## [<version>]`` section without its heading.

    The section runs from just after its heading up to (but excluding) the next
    ``## [`` heading or end of file. A leading ``v`` on ``version`` is ignored so
    a git tag name can be passed directly.

    Raises:
        KeyError: if no heading for ``version`` is found.
    """
    version = _normalize_version(version)
    heading = re.compile(r"^##\s+\[" + re.escape(version) + r"\](?:\s|$)")
    next_heading = re.compile(r"^##\s+\[")

    lines = changelog.splitlines()
    start: int | None = None
    for index, line in enumerate(lines):
        if heading.match(line):
            start = index
            break
    if start is None:
        raise KeyError(version)

    body: list[str] = []
    for line in lines[start + 1 :]:
        if next_heading.match(line):
            break
        body.append(line)
    return "\n".join(body).strip("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", help="Version or tag name, e.g. 2.0.0 or v2.0.0")
    parser.add_argument(
        "--changelog",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "CHANGELOG.md",
        help="Path to CHANGELOG.md (default: repo root CHANGELOG.md)",
    )
    args = parser.parse_args(argv)

    try:
        text = args.changelog.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"error: cannot read {args.changelog}: {exc}", file=sys.stderr)
        return 2

    try:
        section = extract_section(text, args.version)
    except KeyError:
        print(
            f"error: no changelog section for version {args.version!r}",
            file=sys.stderr,
        )
        return 1

    if not section:
        print(
            f"error: changelog section for {args.version!r} is empty",
            file=sys.stderr,
        )
        return 1

    print(section)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
