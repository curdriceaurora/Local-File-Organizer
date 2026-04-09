#!/usr/bin/env python3
"""Generate or refresh [tool.coverage.floors.integration] in pyproject.toml.

Usage:
    python .claude/scripts/generate-integration-floors.py [--json PATH] [--pyproject PATH]

Reads coverage JSON (default: .coverage-integration.json), computes per-file
floors using int(pct // 5) * 5, and updates pyproject.toml in-place.

Rules:
- Never auto-downgrades an existing entry that is already higher.
- Sorts keys alphabetically for deterministic diffs.
- Flags stale entries (in table but absent from JSON) to stderr -- does not remove them.
"""
from __future__ import annotations

import argparse
import json
import sys
import tomllib
from pathlib import Path


def compute_floor(summary: dict) -> int:
    total = summary.get("num_statements", 0) + summary.get("num_branches", 0)
    if total == 0:
        return 0
    hits = summary.get("covered_lines", 0) + summary.get("covered_branches", 0)
    pct = hits / total * 100
    return int(pct // 5) * 5


def _find_section_bounds(text: str, header: str) -> tuple[int, int] | None:
    """Return (start, end) byte offsets of the section including its header line."""
    if header not in text:
        return None
    start = text.index(header)
    rest = text[start + len(header):]
    next_section = rest.find("\n[")
    end = start + len(header) + next_section + 1 if next_section != -1 else len(text)
    return start, end


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", default=".coverage-integration.json", dest="json_path")
    parser.add_argument("--pyproject", default="pyproject.toml")
    args = parser.parse_args()

    # Resolve paths relative to CWD (allows tests to pass tmp_path)
    json_path = Path(args.json_path)
    pyproject_path = Path(args.pyproject)

    with open(json_path) as f:
        coverage_data = json.load(f)

    with open(pyproject_path, "rb") as f:
        pyproject = tomllib.load(f)

    existing: dict[str, int] = (
        pyproject.get("tool", {})
        .get("coverage", {})
        .get("floors", {})
        .get("integration", {})
    )

    new_floors: dict[str, int] = {}
    added = updated = 0

    for path, info in coverage_data["files"].items():
        norm = str(Path(path).as_posix())
        computed = compute_floor(info["summary"])
        current = existing.get(norm)
        if current is None:
            new_floors[norm] = computed
            added += 1
        else:
            kept = max(current, computed)
            new_floors[norm] = kept
            if kept > current:
                updated += 1

    # Flag stale entries -- preserve them in the output
    stale = 0
    json_norms = {str(Path(p).as_posix()) for p in coverage_data["files"]}
    for key, val in existing.items():
        if key not in json_norms:
            print(f"STALE: {key} (in floors table but absent from coverage JSON)", file=sys.stderr)
            new_floors[key] = val
            stale += 1

    sorted_floors = dict(sorted(new_floors.items()))

    # Build new section text
    header = "[tool.coverage.floors.integration]"
    section_lines = [header] + [f'"{k}" = {v}' for k, v in sorted_floors.items()]
    new_section = "\n".join(section_lines) + "\n"

    text = pyproject_path.read_text()
    bounds = _find_section_bounds(text, header)
    if bounds:
        start, end = bounds
        text = text[:start] + new_section + text[end:]
    else:
        text = text.rstrip("\n") + "\n\n" + new_section

    pyproject_path.write_text(text)

    print(f"Floors updated: {added} added, {updated} bumped, {stale} stale (see stderr)")
    print(f"  Total entries: {len(sorted_floors)}")


if __name__ == "__main__":
    main()
