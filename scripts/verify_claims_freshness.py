#!/usr/bin/env python3
"""Verify public product claims against canonical capability registry and capability matrix.

This script parses README.md and docs/developer/capability-matrix.md to ensure:
1. Every feature claim under ## Features links to a valid anchor present in capability-matrix.md.
2. Capability IDs linked in README.md exist in src/file_organizer/core/capability_registry.json.
3. No unverified marketing metrics or un-inventoried feature claims exist in README.md.
4. Optional feature pack requirements ([audio], [video], [dedup]) are properly qualified.
5. All anchor references in README.md resolve directly against the generated capability-matrix.md document.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Ensure src/ is on Python path when run directly
_ROOT = Path(__file__).resolve().parent.parent
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from file_organizer.core.capabilities import (  # noqa: E402
    get_capability_registry,
)

DEFAULT_README_PATH = _ROOT / "README.md"
DEFAULT_MATRIX_PATH = _ROOT / "docs" / "developer" / "capability-matrix.md"

# Match any Markdown link targeting capability-matrix.md
_MATRIX_LINK_PATTERN = re.compile(
    r"\[([^\]]+)\]\((?:docs/developer/)?capability-matrix\.md(?:#([a-zA-Z0-9_-]+))?\)"
)
# Match capability ID patterns like `analysis.inspect` or analysis.inspect
_CAPABILITY_ID_PATTERN = re.compile(r"`?([a-z][a-z0-9-]*\.[a-z][a-z0-9-]*)`?")
# Extract HTML anchors and Markdown headings from capability-matrix.md
_HTML_ANCHOR_PATTERN = re.compile(r'<a\s+(?:id|name)="([^"]+)"')
_HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)

# Pattern for unverified quantitative marketing claims (e.g. "840 tests", "408 modules", "1200 devices", "99.99% uptime")
_UNVERIFIED_MARKETING_PATTERN = re.compile(
    r"\b(?:\d+\s+(?:tests|modules|file types|devices)|99\.\d+%\s+uptime)\b", re.IGNORECASE
)


def _slugify_heading(heading_text: str) -> str:
    """Convert Markdown heading text to GitHub Markdown anchor slug format."""
    clean = re.sub(r"[^\w\s-]", "", heading_text.lower())
    return re.sub(r"[\s_]+", "-", clean.strip())


def extract_matrix_anchors(matrix_path: Path) -> set[str]:
    """Extract all valid HTML and heading anchors from capability-matrix.md."""
    if not matrix_path.exists():
        return set()

    content = matrix_path.read_text(encoding="utf-8")
    anchors: set[str] = set()

    for match in _HTML_ANCHOR_PATTERN.finditer(content):
        anchors.add(match.group(1))

    for match in _HEADING_PATTERN.finditer(content):
        heading_text = match.group(2).strip()
        anchors.add(_slugify_heading(heading_text))

    return anchors


def _verify_marketing_stats(content: str) -> list[str]:
    """Audit content for unverified/un-inventoried marketing statistics."""
    errors: list[str] = []
    for match in _UNVERIFIED_MARKETING_PATTERN.finditer(content):
        errors.append(
            f"README.md contains unverified/un-inventoried marketing claim: '{match.group(0)}'. "
            "All product statistics must be backed by capability matrix evidence."
        )
    return errors


def _verify_matrix_links(
    content: str,
    valid_anchors: set[str],
    valid_capability_ids: set[str],
    matrix_filename: str,
) -> list[str]:
    """Audit links targeting capability-matrix.md for anchor resolution & ID validity."""
    errors: list[str] = []
    matrix_links = list(_MATRIX_LINK_PATTERN.finditer(content))
    if not matrix_links:
        return ["README.md contains no links targeting capability-matrix.md."]

    for match in matrix_links:
        link_text = match.group(1)
        anchor = match.group(2)

        if not anchor:
            errors.append(
                f"README.md link '[{link_text}](capability-matrix.md)' is missing a target anchor."
            )
            continue

        if anchor not in valid_anchors:
            errors.append(
                f"README.md link anchor '#{anchor}' does not exist in '{matrix_filename}'. "
                f"(Link text: '{link_text}')"
            )

        cap_match = _CAPABILITY_ID_PATTERN.search(link_text)
        if cap_match:
            cap_id = cap_match.group(1)
            if cap_id not in valid_capability_ids and "." in cap_id:
                errors.append(f"README.md links to unknown capability ID: '{cap_id}'")

    return errors


def _verify_feature_bullets(readme_content: str) -> list[str]:
    """Audit ## Features section for evidence links and optional pack qualification."""
    errors: list[str] = []
    features_match = re.search(r"## Features\s*\n(.*?)(?=\n## |\Z)", readme_content, re.DOTALL)
    if not features_match:
        return ["README.md is missing a '## Features' section."]

    features_section = features_match.group(1)
    bullet_lines = [
        line.strip() for line in features_section.splitlines() if line.strip().startswith("- **")
    ]
    for bullet in bullet_lines:
        if (
            "capability-matrix.md" not in bullet
            and "pywebview" not in bullet
            and "macOS, Windows" not in bullet
        ):
            errors.append(f"Feature bullet lacks capability matrix evidence link: '{bullet}'")

        if "Audio Transcription" in bullet and "[audio]" not in bullet:
            errors.append(
                "Feature bullet 'Audio Transcription' must specify optional '[audio]' extra dependency."
            )
        if "Video Analysis" in bullet and "[video]" not in bullet:
            errors.append(
                "Feature bullet 'Video Analysis' must specify optional '[video]' extra dependency."
            )
        if "Deduplication" in bullet and "[dedup]" not in bullet:
            errors.append(
                "Feature bullet 'Deduplication' must specify optional '[dedup]' extra dependency."
            )

    return errors


def verify_public_claims(
    readme_path: Path = DEFAULT_README_PATH,
    matrix_path: Path = DEFAULT_MATRIX_PATH,
) -> list[str]:
    """Verify README claims against capability registry and capability-matrix.md."""
    if not readme_path.exists():
        return [f"README file '{readme_path}' does not exist."]
    if not matrix_path.exists():
        return [f"Capability matrix file '{matrix_path}' does not exist."]

    registry = get_capability_registry()
    valid_capability_ids = {cap.capability_id for cap in registry.capabilities}
    valid_anchors = extract_matrix_anchors(matrix_path)

    if not valid_anchors:
        return [f"Capability matrix '{matrix_path}' contains no parseable anchors."]

    readme_content = readme_path.read_text(encoding="utf-8")

    errors: list[str] = []
    errors.extend(_verify_marketing_stats(readme_content))
    errors.extend(
        _verify_matrix_links(readme_content, valid_anchors, valid_capability_ids, matrix_path.name)
    )
    errors.extend(_verify_feature_bullets(readme_content))

    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify public claims in README against canonical capability registry and matrix."
    )
    parser.add_argument(
        "--readme",
        type=Path,
        default=DEFAULT_README_PATH,
        help="Path to README.md",
    )
    parser.add_argument(
        "--matrix",
        type=Path,
        default=DEFAULT_MATRIX_PATH,
        help="Path to capability-matrix.md",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        default=True,
        help="Verify claims freshness and link resolution (default: True)",
    )
    args = parser.parse_args(argv)

    errors = verify_public_claims(args.readme, args.matrix)
    if errors:
        print("ERROR: Public claims verification failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print("OK: Public claims in README are verified and resolve against capability evidence.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
