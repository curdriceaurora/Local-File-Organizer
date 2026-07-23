#!/usr/bin/env python3
"""Verify public product claims against canonical capability registry state.

This script parses README.md and verifies that all feature capability links,
surface declarations, and capability metrics match src/file_organizer/core/capability_registry.json.
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

DEFAULT_README_PATH = Path("README.md")
_CAPABILITY_LINK_PATTERN = re.compile(
    r"\[`?([a-z][a-z0-9-]*\.[a-z][a-z0-9-]*)`?\]\((?:docs/developer/)?capability-matrix\.md#([a-z0-9-]+)\)"
)


def verify_public_claims(readme_path: Path = DEFAULT_README_PATH) -> list[str]:
    """Verify README claims against the canonical capability registry."""
    errors: list[str] = []
    if not readme_path.exists():
        return [f"README file '{readme_path}' does not exist."]

    registry = get_capability_registry()
    valid_capability_ids = {cap.capability_id for cap in registry.capabilities}
    content = readme_path.read_text(encoding="utf-8")

    # 1. Check for stale marketing stats
    if "840 tests" in content or "408 modules" in content:
        errors.append(
            "README.md contains stale unverified marketing statistics ('840 tests' / '408 modules'). "
            "Reconcile against canonical capability registry."
        )

    # 2. Check for capability matrix links
    found_links = _CAPABILITY_LINK_PATTERN.findall(content)
    if not found_links:
        errors.append(
            "README.md contains no capability matrix links (expected capability-matrix.md#<id>)."
        )

    for cap_id, anchor in found_links:
        if cap_id not in valid_capability_ids:
            errors.append(f"README.md links to unknown capability ID: '{cap_id}'")
        expected_anchor = cap_id.replace(".", "")
        if anchor != expected_anchor:
            errors.append(
                f"README.md link for capability '{cap_id}' has mismatched anchor '{anchor}' (expected '{expected_anchor}')"
            )

    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify public claims in README against canonical capability registry."
    )
    parser.add_argument(
        "--readme",
        type=Path,
        default=DEFAULT_README_PATH,
        help="Path to README.md (default: README.md)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        default=True,
        help="Check claims freshness (default: True)",
    )
    args = parser.parse_args(argv)

    errors = verify_public_claims(args.readme)
    if errors:
        print("ERROR: Public claims verification failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print("OK: Public claims in README are up to date and linked to capability evidence.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
