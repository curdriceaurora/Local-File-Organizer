#!/usr/bin/env python3
"""Advisory CI-rail runner (WP-0.1 scaffolding, #1222).

Runs the rails declared in ``scripts/ci/rails.toml``. Each rail has a *mode*:

- ``advisory`` — a non-zero exit prints a warning but never fails the run.
- ``enforce``  — a non-zero exit fails the run (the runner returns 1).

This lets later work packages (WP-6.x in the fo-core pull-back plan) author
rails *now* as ``advisory`` and flip them to ``enforce`` only once the code they
guard has merged — without touching this runner.

At WP-0.1 the registry is intentionally empty, so the runner is a no-op
(exit 0): zero behavior change.

Usage::

    python scripts/ci/ci_rails.py              # respect each rail's mode
    python scripts/ci/ci_rails.py --list       # list registered rails
    python scripts/ci/ci_rails.py --enforce-all # treat every rail as enforce (CI)
    python scripts/ci/ci_rails.py --registry PATH
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

ADVISORY = "advisory"
ENFORCE = "enforce"
_MODES = frozenset({ADVISORY, ENFORCE})

# scripts/ci/ci_rails.py -> scripts/ci/rails.toml
DEFAULT_REGISTRY = Path(__file__).resolve().parent / "rails.toml"


@dataclass(frozen=True)
class Rail:
    """A single registered CI rail."""

    name: str
    command: list[str]
    mode: str = ADVISORY
    description: str = ""


@dataclass
class RailResult:
    """Outcome of running one rail."""

    rail: Rail
    returncode: int
    enforced: bool

    @property
    def passed(self) -> bool:
        """True when the rail's command exited 0."""
        return self.returncode == 0

    @property
    def blocking(self) -> bool:
        """True when this failure should fail the overall run."""
        return self.enforced and not self.passed


@dataclass
class RunSummary:
    """Aggregate outcome of a rail run."""

    results: list[RailResult] = field(default_factory=list)

    @property
    def exit_code(self) -> int:
        """0 unless an enforce rail failed (then 1)."""
        return 1 if any(r.blocking for r in self.results) else 0


def load_rails(registry: Path) -> list[Rail]:
    """Parse the rail registry. A missing file yields an empty list (no-op)."""
    if not registry.exists():
        return []
    data = tomllib.loads(registry.read_text(encoding="utf-8"))
    rails: list[Rail] = []
    for entry in data.get("rail", []):
        try:
            name = entry["name"]
            command = entry["command"]
        except KeyError as exc:
            raise ValueError(f"rail entry missing required key: {exc}") from exc
        mode = entry.get("mode", ADVISORY)
        if mode not in _MODES:
            raise ValueError(
                f"rail {name!r}: invalid mode {mode!r} (expected one of {sorted(_MODES)})"
            )
        if not isinstance(command, list) or not all(isinstance(part, str) for part in command):
            raise ValueError(f"rail {name!r}: command must be a list of strings")
        if not command:
            raise ValueError(f"rail {name!r}: command must not be empty")
        rails.append(
            Rail(
                name=name,
                command=list(command),
                mode=mode,
                description=str(entry.get("description", "")),
            )
        )
    return rails


_LAUNCH_FAILURE = 127  # conventional "command not found" exit code


def _run_rail(rail: Rail) -> int:
    """Execute a rail's command and return its exit code.

    Commands are sourced from the in-repo registry (trusted), not user input.
    A command that fails to launch (missing/non-executable binary) is reported
    as a failure (exit 127) rather than raised, so the advisory/enforce policy
    still applies — an advisory rail must never crash the run.
    """
    try:
        completed = subprocess.run(rail.command, check=False)
    except OSError as exc:
        print(
            f"ci-rails: rail {rail.name!r} command failed to launch: {exc}",
            file=sys.stderr,
        )
        return _LAUNCH_FAILURE
    return completed.returncode


def run_rails(rails: list[Rail], *, enforce_all: bool = False) -> RunSummary:
    """Run every rail, honoring its mode unless ``enforce_all`` overrides it."""
    summary = RunSummary()
    for rail in rails:
        returncode = _run_rail(rail)
        enforced = enforce_all or rail.mode == ENFORCE
        result = RailResult(rail=rail, returncode=returncode, enforced=enforced)
        summary.results.append(result)
        if result.passed:
            print(f"✅ {rail.name}")
        elif result.blocking:
            print(f"❌ [enforce] {rail.name} failed (exit {returncode})", file=sys.stderr)
        else:
            print(f"⚠️  [advisory] {rail.name} failed (exit {returncode})", file=sys.stderr)
    return summary


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: load the registry, run rails, return the exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--list", action="store_true", help="List registered rails and exit.")
    parser.add_argument(
        "--enforce-all",
        action="store_true",
        help="Treat every rail as enforce (used by CI once rails should block).",
    )
    args = parser.parse_args(argv)

    rails = load_rails(args.registry)

    if args.list:
        if not rails:
            print("ci-rails: no rails registered")
        for rail in rails:
            print(f"{rail.mode:8}  {rail.name}  — {rail.description}")
        return 0

    if not rails:
        print("ci-rails: no rails registered (advisory framework active, no-op)")
        return 0

    summary = run_rails(rails, enforce_all=args.enforce_all)
    return summary.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
