#!/usr/bin/env python3
"""Gate pip-audit findings against an accepted-risk allowlist (WP-6.3).

Reads pip-audit's `--format json` output and .github/accepted-risks.yml,
drops any (package, vulnerability_id) pair present in the allowlist, and
exits non-zero if any finding remains.

Usage:
    pip-audit --format json -o /tmp/audit.json
    python scripts/security/pip_audit_gate.py --audit /tmp/audit.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml


def _load_accepted_risks(path: Path) -> set[tuple[str, str]]:
    if not path.exists():
        return set()
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    accepted: set[tuple[str, str]] = set()
    for risk in data.get("risks", []):
        package = risk.get("package")
        vuln_id = risk.get("vulnerability_id")
        if package and vuln_id:
            accepted.add((package.lower(), vuln_id))
    return accepted


def run_gate(audit_json_path: Path, accepted_risks_path: Path) -> list[str]:
    """Return a list of unaccepted finding descriptions (empty == clean)."""
    with open(audit_json_path, encoding="utf-8") as f:
        audit_data = json.load(f)

    accepted = _load_accepted_risks(accepted_risks_path)
    findings: list[str] = []

    for dependency in audit_data.get("dependencies", []):
        name = dependency.get("name", "")
        version = dependency.get("version", "")
        for vuln in dependency.get("vulns", []):
            vuln_id = vuln.get("id", "")
            if (name.lower(), vuln_id) in accepted:
                continue
            findings.append(f"{name}=={version}: {vuln_id} (not in accepted-risks.yml)")

    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", default=".pip-audit.json", dest="audit_path")
    parser.add_argument("--accepted-risks", default=".github/accepted-risks.yml", dest="risks_path")
    args = parser.parse_args()

    audit_path = Path(args.audit_path)
    if not audit_path.exists():
        print(f"ERROR: pip-audit JSON not found: {audit_path}", file=sys.stderr)
        print(
            "Run: pip-audit --format json -o " + str(audit_path),
            file=sys.stderr,
        )
        return 1

    findings = run_gate(audit_path, Path(args.risks_path))

    if findings:
        print("❌ [pip-audit-gate] Unaccepted vulnerability findings:", file=sys.stderr)
        for finding in findings:
            print(f"  {finding}", file=sys.stderr)
        print(
            "\nFix: upgrade the package, or add an entry to "
            f"{args.risks_path} with a reason and tracking_issue.",
            file=sys.stderr,
        )
        return 1

    print("✅ [pip-audit-gate] No unaccepted vulnerability findings.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
