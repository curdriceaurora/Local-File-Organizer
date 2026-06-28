#!/usr/bin/env python3
"""Generate or refresh [tool.coverage.floors.unit] in pyproject.toml.

Usage:
    python scripts/coverage/generate_module_coverage_floor.py [--json PATH] [--pyproject PATH]

Reads coverage JSON (default: .coverage-unit.json), computes per-file
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
    rest = text[start + len(header) :]
    next_section = rest.find("\n[")
    end = start + len(header) + next_section + 1 if next_section != -1 else len(text)
    return start, end


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", default=".coverage-unit.json", dest="json_path")
    parser.add_argument("--pyproject", default="pyproject.toml")
    args = parser.parse_args(argv)

    json_path = Path(args.json_path)
    pyproject_path = Path(args.pyproject)

    try:
        with open(json_path) as f:
            coverage_data = json.load(f)
    except FileNotFoundError:
        print(f"ERROR: coverage JSON not found: {json_path}", file=sys.stderr)
        sys.exit(1)

    with open(pyproject_path, "rb") as f:
        pyproject = tomllib.load(f)
    existing: dict[str, int] = (
        pyproject.get("tool", {}).get("coverage", {}).get("floors", {}).get("unit", {})
    )

    json_files: dict[str, dict] = {
        str(Path(p).as_posix()): info for p, info in coverage_data["files"].items()
    }

    new_floors: dict[str, int] = dict(existing)
    for norm, info in json_files.items():
        floor = compute_floor(info["summary"])
        if norm in existing and existing[norm] >= floor:
            continue
        new_floors[norm] = floor

    for key in existing:
        if key not in json_files:
            print(f"WARNING: stale entry not removed: {key}", file=sys.stderr)

    lines = ["[tool.coverage.floors.unit]\n"]
    for key in sorted(new_floors):
        lines.append(f'"{key}" = {new_floors[key]}\n')
    new_section = "".join(lines)

    text = pyproject_path.read_text(encoding="utf-8")
    bounds = _find_section_bounds(text, "[tool.coverage.floors.unit]\n")
    if bounds is None:
        text = text.rstrip("\n") + "\n\n" + new_section
    else:
        start, end = bounds
        text = text[:start] + new_section + text[end:]

    pyproject_path.write_text(text, encoding="utf-8")
    print(f"Wrote {len(new_floors)} unit coverage floor entries to {pyproject_path}")


if __name__ == "__main__":
    main()
