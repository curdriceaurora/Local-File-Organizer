#!/usr/bin/env python3
"""Verify public product claims against canonical capability registry and capability matrix.

This script parses README.md and docs/developer/capability-matrix.md to ensure:
1. Every feature claim under ## Features links to a valid anchor present in capability-matrix.md.
2. Capability IDs linked in README.md exist in src/file_organizer/core/capability_registry.json.
3. README capability link anchors match the expected anchor for their capability ID.
4. Product metrics (capability count, surface count, TUI views) match canonical registry state.
5. No unverified marketing metrics or un-inventoried feature claims exist in README.md.
6. Optional feature pack requirements ([audio], [video], [dedup]) are properly qualified.
7. Capabilities advertised as conformance-verified actually hold conformance evidence, and no
   conformance-verified capability is omitted from that claim.
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

from file_organizer.core.capabilities import (  # noqa: E402  # copilot: wontfix - sys.path modification required for direct script execution
    Surface,
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

# Retired hand-maintained inventory claims. These counted source artefacts rather than product
# capabilities and were never reproducible; the canonical counts below replace them. Uptime is
# listed because a locally executed tool cannot substantiate an availability figure at all.
_UNVERIFIED_MARKETING_PATTERN = re.compile(
    r"\b(?:\d+\s+(?:tests|modules|file types)|\d+(?:\.\d+)?%\s+uptime)\b", re.IGNORECASE
)

# Canonical counts verification patterns
_CAPABILITY_COUNT_CLAIM_PATTERN = re.compile(r"\b(\d+)\s+product capabilities\b", re.IGNORECASE)
_SURFACE_COUNT_CLAIM_PATTERN = re.compile(r"\b(\d+)\s+official surfaces\b", re.IGNORECASE)
_TUI_VIEW_COUNT_CLAIM_PATTERN = re.compile(r"\b(\d+)-view Textual TUI\b", re.IGNORECASE)

# Clause advertising which capabilities hold conformance evidence, e.g.
# "conformance-verified for [`organization.execute`](...), and [`methodology.configure`](...))".
_CONFORMANCE_CLAIM_PATTERN = re.compile(r"conformance-verified for\b(?P<claim>[^\n]*)")

CANONICAL_TUI_VIEW_COUNT = 8


def _slugify_heading(heading_text: str) -> set[str]:
    """Return candidate GitHub anchor slugs for one Markdown heading.

    GitHub emits one hyphen per whitespace character, while many Markdown tools collapse runs of
    whitespace into a single hyphen. Headings here contain em dashes surrounded by spaces, so the
    two conventions disagree. Accept both rather than guess which renderer the reader uses.
    """
    clean = re.sub(r"[^\w\s-]", "", heading_text.lower()).strip()
    if not clean:
        return set()
    return {
        re.sub(r"[\s_]+", "-", clean),  # collapsed runs
        re.sub(r"[\s_]", "-", clean),  # one hyphen per whitespace character
    }


def extract_matrix_anchors(matrix_path: Path) -> set[str]:
    """Extract all valid HTML and heading anchors from capability-matrix.md."""
    if not matrix_path.exists():
        return set()

    content = matrix_path.read_text(encoding="utf-8")
    anchors: set[str] = set()

    for match in _HTML_ANCHOR_PATTERN.finditer(content):
        anchors.add(match.group(1))

    # GitHub disambiguates repeated heading slugs with -1, -2, ... in document order.
    seen: dict[str, int] = {}
    for match in _HEADING_PATTERN.finditer(content):
        for slug in _slugify_heading(match.group(2).strip()):
            occurrence = seen.get(slug, 0)
            anchors.add(slug if occurrence == 0 else f"{slug}-{occurrence}")
            seen[slug] = occurrence + 1

    return anchors


def _verified_capability_ids() -> set[str]:
    """Return capability IDs holding conformance evidence on at least one surface.

    Iterate declared surfaces rather than the Surface enum: ``support_for`` raises for a surface a
    capability does not declare, so enum iteration would depend on the registry loader's
    completeness invariant holding forever.
    """
    from file_organizer.core.capabilities import ConformanceStatus

    return {
        capability.capability_id
        for capability in get_capability_registry().capabilities
        for status in capability.surfaces
        if status.conformance_status is ConformanceStatus.VERIFIED
    }


def _verify_conformance_claims(content: str) -> list[str]:
    """Audit the conformance-verified claim against actual registry evidence.

    A link resolving to a real capability proves nothing about that capability holding evidence.
    This closes the loop in both directions: nothing may be advertised as conformance-verified
    without evidence, and nothing holding evidence may be quietly omitted.

    The clause is required only when the README advertises a capability count. Quoting a headline
    capability total without scoping which of those capabilities are actually proven is the claim
    this whole script exists to prevent, so deleting the clause must not be a way to pass. A README
    that makes no capability-count claim has nothing to scope and is left alone.
    """
    claim_match = _CONFORMANCE_CLAIM_PATTERN.search(content)
    if not claim_match:
        if _CAPABILITY_COUNT_CLAIM_PATTERN.search(content):
            return [
                "README.md advertises a product capability count but no conformance-verified "
                "claim scoping which of those capabilities hold evidence."
            ]
        return []

    claimed: set[str] = set()
    for link in _MATRIX_LINK_PATTERN.finditer(claim_match.group("claim")):
        cap_match = _CAPABILITY_ID_PATTERN.search(link.group(1))
        if cap_match:
            claimed.add(cap_match.group(1))
    if not claimed:
        return ["README.md advertises conformance-verified capabilities but links none of them."]

    verified = _verified_capability_ids()
    errors: list[str] = []
    for capability_id in sorted(claimed - verified):
        errors.append(
            f"README.md advertises '{capability_id}' as conformance-verified, but it holds no "
            "verified surface in the capability registry."
        )
    for capability_id in sorted(verified - claimed):
        errors.append(
            f"README.md omits '{capability_id}' from its conformance-verified claim even though "
            "it holds verified conformance evidence."
        )
    return errors


def _verify_marketing_stats(content: str) -> list[str]:
    """Audit content for unverified/un-inventoried marketing statistics and canonical metrics."""
    errors: list[str] = []
    registry = get_capability_registry()
    canonical_cap_count = len(registry.capabilities)
    canonical_surface_count = len(Surface)

    # 1. Un-inventoried marketing claims check
    for match in _UNVERIFIED_MARKETING_PATTERN.finditer(content):
        errors.append(
            f"README.md contains unverified/un-inventoried marketing claim: '{match.group(0)}'. "
            "All product statistics must be backed by capability matrix evidence."
        )

    # 2. Canonical capability count check
    for match in _CAPABILITY_COUNT_CLAIM_PATTERN.finditer(content):
        claimed_count = int(match.group(1))
        if claimed_count != canonical_cap_count:
            errors.append(
                f"README.md contains stale product capability count '{claimed_count}' (expected '{canonical_cap_count}')."
            )

    # 3. Canonical surface count check
    for match in _SURFACE_COUNT_CLAIM_PATTERN.finditer(content):
        claimed_count = int(match.group(1))
        if claimed_count != canonical_surface_count:
            errors.append(
                f"README.md contains stale surface count '{claimed_count}' (expected '{canonical_surface_count}')."
            )

    # 4. Canonical TUI views count check
    for match in _TUI_VIEW_COUNT_CLAIM_PATTERN.finditer(content):
        claimed_count = int(match.group(1))
        if claimed_count != CANONICAL_TUI_VIEW_COUNT:
            errors.append(
                f"README.md contains stale TUI view count '{claimed_count}' (expected '{CANONICAL_TUI_VIEW_COUNT}')."
            )

    return errors


def _verify_matrix_links(
    content: str,
    valid_anchors: set[str],
    valid_capability_ids: set[str],
    matrix_filename: str,
) -> list[str]:
    """Audit links targeting capability-matrix.md for anchor resolution, ID validity, and ID-anchor mapping."""
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
            elif cap_id in valid_capability_ids:
                expected_anchor = cap_id.replace(".", "")
                if anchor != expected_anchor:
                    errors.append(
                        f"README.md link for capability '{cap_id}' has mismatched anchor '#{anchor}' (expected '#{expected_anchor}')."
                    )

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
        if "capability-matrix.md" not in bullet:
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
    errors.extend(_verify_conformance_claims(readme_content))

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
        help=(
            "Accepted for symmetry with generate_capability_matrix.py --check. This script has no "
            "write mode, so verification always runs whether or not the flag is passed."
        ),
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
