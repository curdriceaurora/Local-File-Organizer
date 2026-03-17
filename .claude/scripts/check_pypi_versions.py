#!/usr/bin/env python3
"""Verify that >=version constraints in pyproject.toml are satisfiable on PyPI.

A constraint ``package>=X.Y.Z`` is satisfiable when at least one published
version of *package* is >= X.Y.Z.  This catches cases like
``rank-bm25>=0.7.2`` where the latest published version is 0.2.2 — no
installation is possible, so the requirement is effectively broken.

Only pre-1.0 packages are checked (version < 1.0.0) because those have the
highest risk of invented or nonexistent version constraints.

Exit codes:
  0 — all checked constraints are satisfiable (or network is unavailable)
  1 — one or more constraints cannot be satisfied by any PyPI release
"""

from __future__ import annotations

import json
import re
import sys
import tomllib
from pathlib import Path
from urllib import error, parse, request


def _version_is_pre_1(version: str) -> bool:
    """Return True for pre-1.0 versions like 0.7.2, 0.0.19."""
    return version.startswith("0.")


def _version_tuple(version: str) -> tuple[int, ...]:
    """Return a comparable integer tuple for a version string."""
    parts = re.split(r"[^0-9]+", version.split("+")[0].split("a")[0].split("b")[0].split("rc")[0])
    return tuple(int(p) for p in parts if p.isdigit())


def _get_all_versions(package: str) -> list[str] | None:
    """Return all published versions for *package* from PyPI.

    Returns None on network error; the caller should skip the check.
    """
    url = f"https://pypi.org/pypi/{parse.quote(package, safe='')}/json"
    try:
        with request.urlopen(url, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return list(data.get("releases", {}).keys())
    except error.HTTPError as exc:
        if exc.code == 404:
            return []  # package not found — let the caller report the error
        return None  # unexpected HTTP error — don't block commit
    except OSError:
        return None  # network unavailable


def _constraint_is_satisfiable(minimum: str, available: list[str]) -> bool:
    """Return True if any version in *available* is >= *minimum*."""
    min_tuple = _version_tuple(minimum)
    for ver in available:
        try:
            if _version_tuple(ver) >= min_tuple:
                return True
        except (ValueError, TypeError):
            continue
    return False


def _collect_deps(data: dict) -> list[str]:
    deps: list[str] = []
    deps.extend(data.get("project", {}).get("dependencies", []))
    for group in data.get("project", {}).get("optional-dependencies", {}).values():
        deps.extend(group)
    return deps


_CONSTRAINT_RE = re.compile(
    r"^([A-Za-z0-9_.-]+)"  # package name
    r"[^;]*"               # extras / markers prefix (skip semicolons)
    r">=\s*([0-9][0-9a-zA-Z._-]*)"  # >= version
)


def main() -> int:
    pyproject = Path("pyproject.toml")
    if not pyproject.exists():
        return 0

    with open(pyproject, "rb") as fh:
        data = tomllib.load(fh)

    failures: list[str] = []
    network_ok = True
    # Cache results to avoid duplicate PyPI calls for the same package
    _version_cache: dict[str, list[str] | None] = {}

    for dep in _collect_deps(data):
        dep = dep.strip()
        dep_no_marker = dep.split(";")[0].strip()
        match = _CONSTRAINT_RE.match(dep_no_marker)
        if not match:
            continue

        package = match.group(1)
        version = match.group(2)

        if not _version_is_pre_1(version):
            continue  # Only validate pre-1.0 packages (higher risk of invented versions)

        pkg_norm = package.lower().replace("_", "-")

        if pkg_norm not in _version_cache:
            _version_cache[pkg_norm] = _get_all_versions(pkg_norm)

        available = _version_cache[pkg_norm]
        if available is None:
            network_ok = False
            break  # network unavailable — skip remaining checks

        if not available:
            failures.append(
                f"  {package}>={version} — package {package!r} not found on PyPI at all"
            )
        elif not _constraint_is_satisfiable(version, available):
            latest = max(available, key=_version_tuple, default="?")
            failures.append(
                f"  {package}>={version} — no published version >= {version} "
                f"(latest is {latest})"
            )

    if not network_ok:
        print("pypi-version-check: network unavailable, skipping version validation.")
        return 0

    if failures:
        print("pypi-version-check: unsatisfiable version constraints in pyproject.toml:")
        for line in failures:
            print(line)
        print(
            "\nFix: verify the package version with "
            "`pip index versions <package>` before updating pyproject.toml."
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
