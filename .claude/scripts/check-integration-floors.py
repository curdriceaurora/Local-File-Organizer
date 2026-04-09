#!/usr/bin/env python3
"""Check per-file integration coverage floors.

Reads .coverage-integration.json and [tool.coverage.floors.integration] from
pyproject.toml. Exits 1 if any violation is found.

Violations:
  BELOW FLOOR   -- file coverage < configured floor (floor > 0 only)
  MISSING FLOOR -- file has coverage > 0 in JSON but no table entry
  STALE ENTRY   -- file is in table but absent from JSON

Usage:
    python .claude/scripts/check-integration-floors.py [--json PATH] [--pyproject PATH]
"""
from __future__ import annotations

import argparse
import json
import sys
import tomllib
from pathlib import Path


def compute_combined(summary: dict) -> float | None:
    total = summary.get("num_statements", 0) + summary.get("num_branches", 0)
    if total == 0:
        return None
    hits = summary.get("covered_lines", 0) + summary.get("covered_branches", 0)
    return hits / total * 100


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", default=".coverage-integration.json", dest="json_path")
    parser.add_argument("--pyproject", default="pyproject.toml")
    args = parser.parse_args()

    json_path = Path(args.json_path)
    pyproject_path = Path(args.pyproject)

    try:
        with open(json_path) as f:
            coverage_data = json.load(f)
    except FileNotFoundError:
        print(f"ERROR: coverage JSON not found: {json_path}", file=sys.stderr)
        print("Run: bash .claude/scripts/measure-integration-coverage.sh --cov-report=json:.coverage-integration.json", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as exc:
        print(f"ERROR: malformed coverage JSON {json_path}: {exc}", file=sys.stderr)
        sys.exit(1)

    try:
        with open(pyproject_path, "rb") as f:
            pyproject = tomllib.load(f)
    except FileNotFoundError:
        print(f"ERROR: pyproject.toml not found: {pyproject_path}", file=sys.stderr)
        sys.exit(1)

    floors: dict[str, int] = (
        pyproject.get("tool", {})
        .get("coverage", {})
        .get("floors", {})
        .get("integration", {})
    )

    # Normalize JSON paths
    json_files: dict[str, dict] = {
        str(Path(p).as_posix()): info
        for p, info in coverage_data["files"].items()
    }

    violations: list[str] = []

    # Check 1: below floor + Check 2: missing entry
    for norm, info in json_files.items():
        combined = compute_combined(info["summary"])
        if combined is None:
            continue
        if norm not in floors:
            if combined > 0:
                violations.append(
                    f"MISSING FLOOR: {norm} ({combined:.1f}% coverage, no floor entry)"
                    " -- run generate-integration-floors.py"
                )
        else:
            floor = floors[norm]
            if floor > 0 and combined < floor:
                violations.append(
                    f"BELOW FLOOR: {norm}: {combined:.1f}% < {floor}% floor"
                )

    # Check 3: stale entries
    for key in floors:
        if key not in json_files:
            violations.append(
                f"STALE ENTRY: {key} is in floors table but absent from coverage JSON"
                " -- remove or rename the entry"
            )

    if violations:
        print("Integration coverage floor violations:", file=sys.stderr)
        for v in sorted(violations):
            print(f"  {v}", file=sys.stderr)
        sys.exit(1)

    enforced = sum(1 for f in floors.values() if f > 0)
    unenforced = len(floors) - enforced
    print(
        f"All per-file integration coverage floors met "
        f"({enforced} enforced, {unenforced} at floor 0)"
    )


if __name__ == "__main__":
    main()
