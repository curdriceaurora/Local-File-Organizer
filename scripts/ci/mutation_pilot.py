#!/usr/bin/env python3
"""Mutation-testing pilot driver (#1684, epic #1678).

Runs ``mutmut`` over a small set of per-module profiles and reports a
mutation score for each. Pilot scope only — the modules epic #1678's repair
waves touched most, so the score answers "did the repairs actually catch
anything". This is deliberately NOT suite-wide: mutation runtime is test
runtime multiplied by mutant count, and the suite is ~22.5k tests.

Usage::

    python scripts/ci/mutation_pilot.py                 # run every profile
    python scripts/ci/mutation_pilot.py batch-sizer     # run one
    python scripts/ci/mutation_pilot.py --enforce       # fail below floors
    python scripts/ci/mutation_pilot.py --list          # show profiles

Three things about this harness are load bearing. Each of them, left alone,
produces a confident number that means nothing:

1. ``--no-cov``. The project's pytest ``addopts`` carry
   ``--cov-fail-under=93``. Under mutation that gate fails for nearly every
   mutant, pytest exits non-zero, and mutmut reads a non-zero exit as "the
   suite caught it" — reporting a ~100% score that measures the coverage
   gate rather than the tests.

2. **Narrow test selection.** mutmut forks per mutant, and forks taken while
   the parent has threads running crash or hang. This is a property of the
   *test files* selected, not of the module being mutated: adding one
   thread-creating test file to an otherwise clean profile produces
   segfaults, which mutmut then records as mutant verdicts. Each profile
   names only the test files that exercise its modules, and ``segfault`` in
   the stats is treated as a hard error here rather than as a result.

3. **Config lives in ``setup.cfg``, written per profile.** mutmut reads
   ``[tool.mutmut]`` from ``pyproject.toml`` when present and only falls back
   to ``setup.cfg`` otherwise. Keeping pyproject free of that section is what
   lets this script vary ``only_mutate``/test paths per profile without
   rewriting a tracked file.

``mutmut browse`` is unavailable: it needs ``textual>=1.0`` and this project
pins ``textual~=0.50``. Install mutmut with ``--no-deps``; ``run``, ``results``
and ``export-cicd-stats`` all work against the pinned version.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SETUP_CFG = REPO_ROOT / "setup.cfg"
MUTANTS_DIR = REPO_ROOT / "mutants"
STATS_FILE = MUTANTS_DIR / "mutmut-cicd-stats.json"

#: Pytest arguments shared by every profile. `--no-cov` is not optional; see
#: the module docstring.
BASE_PYTEST_ARGS = ["--no-cov", "-p", "no:randomly", "-p", "no:cacheprovider"]

#: Reading already-written meta files should take seconds. Bounded anyway, so
#: a wedged export cannot hang the nightly the way a wedged run would.
EXPORT_TIMEOUT = 300


@dataclass(frozen=True)
class Profile:
    """One pilot target: what to mutate, and what to run against it."""

    name: str
    only_mutate: list[str]
    tests: list[str]
    #: Minimum mutation score, as a percentage, enforced under `--enforce`.
    #: `None` means "measured but not yet gated" — a floor is only meaningful
    #: once there is a baseline to set it from.
    floor: float | None = None
    notes: str = ""
    #: Why this profile cannot run. Blocked profiles are skipped in a default
    #: run — loudly, never silently — but still run when named explicitly, so
    #: anyone attempting a fix can measure it.
    blocked: str | None = None
    extra_pytest_args: list[str] = field(default_factory=list)


PROFILES: tuple[Profile, ...] = (
    Profile(
        name="batch-sizer",
        only_mutate=["*/optimization/batch_sizer.py"],
        tests=[
            "tests/optimization/test_batch_sizer.py",
            "tests/optimization/test_batch_sizer_coverage.py",
        ],
        floor=63.0,  # measured 66.5%
        notes="Absorbed the most wave-A/B repairs; the epic's own premise under test.",
    ),
    Profile(
        name="memory-limiter",
        only_mutate=["*/optimization/memory_limiter.py"],
        tests=[
            "tests/optimization/test_memory_limiter.py",
            "tests/optimization/test_memory_limiter_coverage.py",
        ],
        floor=76.0,  # measured 79.8%
    ),
    Profile(
        name="memory-profiler",
        only_mutate=["*/optimization/memory_profiler.py"],
        tests=[
            "tests/optimization/test_memory_profiler.py",
            "tests/optimization/test_memory_profiler_coverage.py",
        ],
        floor=77.0,  # measured 80.7%
    ),
    Profile(
        name="parallel",
        only_mutate=["*/parallel/processor.py"],
        tests=["tests/parallel/test_processor.py"],
        # test_processor_thread_safety.py and test_concurrency_fixes.py are
        # excluded: including them made mutmut deadlock intermittently (forked
        # children asleep, no CPU, no progress). They are the tests most worth
        # mutating, so this is a known gap, not a preference -- see
        # docs/developer/mutation-testing.md.
        notes="Wave-B repairs plus the resume/persistence assertions.",
        blocked=(
            "deadlocks intermittently: forked children go to sleep and never "
            "resume, so the run hangs until --timeout reaps it. Same root cause "
            "as the organizer profile — thread-creating tests plus fork-per-mutant "
            "— surfacing as a hang rather than a crash. Measured 44.5% (233 killed "
            "/ 291 survived) on the runs that completed, but an intermittent hang "
            "cannot gate a nightly (#1726)."
        ),
    ),
    Profile(
        name="organizer",
        only_mutate=["*/core/organizer.py"],
        tests=[
            "tests/core/test_organizer.py",
            "tests/core/test_organizer_coverage.py",
            "tests/core/test_organizer_sha256_safedir.py",
        ],
        # test_audio_video_integration.py is excluded, but the reason it was
        # excluded turned out to be wrong: it was av/torch native extensions,
        # and that explanation is retracted (see the `blocked` note below and
        # docs/developer/mutation-testing.md). There is no separate evidence
        # that this file is unsafe to fork. It stays out only because the
        # profile is blocked outright and the selection is therefore untested
        # — re-derive it when #1726 unblocks this profile rather than
        # inheriting this list.
        notes="organize()'s AI path was deletable with all 126 tests passing.",
        blocked=(
            "432 mutants segfault. Cause is the TEST files, not this module: "
            "mutating the known-clean batch_sizer.py while merely adding "
            "tests/core/test_organizer.py to the selection produces 42 segfaults. "
            "Those tests create threads, and mutmut forks per mutant. Unaffected "
            "by --max-children 1, so it is the fork itself. Needs a non-forking "
            "runner (#1726)."
        ),
    ),
)


def write_config(profile: Profile) -> None:
    """Write the mutmut config for *profile* to ``setup.cfg``."""
    pytest_args = BASE_PYTEST_ARGS + profile.extra_pytest_args + profile.tests
    lines = [
        "# Generated by scripts/ci/mutation_pilot.py -- do not edit, do not commit.",
        "[mutmut]",
        "source_paths=src/file_organizer",
        "only_mutate=" + "".join(f"\n    {p}" for p in profile.only_mutate),
        "also_copy=\n    tests/\n    pyproject.toml",
        "pytest_add_cli_args=" + "".join(f"\n    {a}" for a in pytest_args),
        "",
    ]
    SETUP_CFG.write_text("\n".join(lines), encoding="utf-8")


def run_profile(profile: Profile, max_children: int, timeout: int) -> dict[str, int]:
    """Run mutmut for *profile* and return its raw stats."""
    shutil.rmtree(MUTANTS_DIR, ignore_errors=True)
    write_config(profile)
    try:
        try:
            run = subprocess.run(
                [sys.executable, "-m", "mutmut", "run", "--max-children", str(max_children)],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            # mutmut forks per mutant, and a fork taken while the parent holds
            # a lock in a thread can deadlock: the children sit in sleep with
            # no CPU and mutmut's own per-mutant timeout never fires because
            # the child never starts running. Observed intermittently on
            # thread-heavy test files. Fail loudly rather than let a nightly
            # job hang until the runner is reaped.
            _kill_stragglers()
            raise RuntimeError(
                f"{profile.name}: mutmut hung for >{timeout}s (deadlocked fork). "
                "Narrow this profile's test selection."
            ) from None
        if run.returncode not in (0, 1):  # 1 == some mutants survived
            raise RuntimeError(
                f"mutmut run failed ({run.returncode}):\n{run.stdout[-3000:]}\n{run.stderr[-3000:]}"
            )
        try:
            export = subprocess.run(
                [sys.executable, "-m", "mutmut", "export-cicd-stats"],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                timeout=EXPORT_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError(
                f"{profile.name}: export-cicd-stats hung for >{EXPORT_TIMEOUT}s"
            ) from None
        if export.returncode != 0:
            raise RuntimeError(
                f"{profile.name}: export-cicd-stats failed ({export.returncode}):\n"
                f"{export.stdout[-2000:]}\n{export.stderr[-2000:]}"
            )
        if not STATS_FILE.exists():
            raise RuntimeError(
                f"no stats produced for {profile.name}:\n{export.stdout}\n{export.stderr}"
            )
        return json.loads(STATS_FILE.read_text(encoding="utf-8"))
    finally:
        SETUP_CFG.unlink(missing_ok=True)


def _kill_stragglers() -> None:
    """Reap mutmut children left behind by a deadlocked fork.

    ``subprocess`` kills the process it started; the forked grandchildren are
    not in that tree and would otherwise sit around holding the sandbox.

    Scoped to the current user so a shared runner — or a second profile
    running in another shell — does not lose its processes to this. ``pkill``
    is absent on some platforms, and raising ``FileNotFoundError`` here would
    mask the timeout error this is called from.
    """
    pkill = shutil.which("pkill")
    if pkill is None:
        print("pkill unavailable; mutmut children may still be running", file=sys.stderr)
        return
    subprocess.run(
        [pkill, "-u", str(os.getuid()), "-f", "mutmut run"],
        check=False,
        capture_output=True,
    )


def score_of(stats: dict[str, int]) -> float | None:
    """Mutation score: killed / (killed + survived), as a percentage.

    Mutants with no covering test are excluded from the denominator — they
    measure coverage, which the project already gates separately, and folding
    them in would let a coverage change move the mutation score on its own.
    """
    killed = stats.get("killed", 0)
    decided = killed + stats.get("survived", 0)
    if not decided:
        return None
    return killed / decided * 100


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profiles", nargs="*", help="profiles to run (default: all)")
    parser.add_argument("--enforce", action="store_true", help="exit non-zero below a floor")
    parser.add_argument("--max-children", type=int, default=4)
    parser.add_argument(
        "--timeout",
        type=int,
        default=1800,
        help="per-profile wall-clock limit; a deadlocked fork never self-clears",
    )
    parser.add_argument("--report", type=Path, help="write the JSON report here")
    parser.add_argument("--list", action="store_true", help="list profiles and exit")
    args = parser.parse_args()

    by_name = {p.name: p for p in PROFILES}
    if args.list:
        for p in PROFILES:
            floor = f"{p.floor:.0f}%" if p.floor is not None else "not gated"
            status = f"BLOCKED — {p.blocked}" if p.blocked else p.notes
            print(f"{p.name:16s} floor={floor:10s} {status}")
        return 0

    unknown = set(args.profiles) - set(by_name)
    if unknown:
        print(f"unknown profile(s): {', '.join(sorted(unknown))}", file=sys.stderr)
        return 2
    if args.profiles:
        # Named explicitly: run it even if blocked, so anyone working on the
        # blocker can measure whether they have fixed it.
        selected = [by_name[n] for n in args.profiles]
    else:
        selected = [p for p in PROFILES if not p.blocked]
        for skipped in (p for p in PROFILES if p.blocked):
            # Announce every exclusion. A pilot that quietly drops a target
            # reads as "we measured everything" when it did not.
            print(f"-- {skipped.name}: SKIPPED — {skipped.blocked}", flush=True)

    report: dict[str, dict] = {}
    failures: list[str] = []
    for profile in selected:
        print(f"-- {profile.name}: mutating {len(profile.only_mutate)} module(s)", flush=True)
        try:
            stats = run_profile(profile, args.max_children, args.timeout)
        except RuntimeError as exc:
            # One wedged profile must not cost the others their results. Left
            # to propagate, a hang in the first profile meant no report file,
            # so the nightly's artifact upload had nothing to publish and the
            # run looked like an infrastructure failure rather than a finding.
            print(f"   ERROR: {exc}", file=sys.stderr, flush=True)
            failures.append(f"{profile.name}: {exc}")
            report[profile.name] = {
                "stats": None,
                "score": None,
                "floor": profile.floor,
                "error": str(exc),
            }
            continue

        # A segfault is a broken harness, not a surviving mutant. Reporting a
        # score over crashed runs is how this pilot would start lying.
        if stats.get("segfault"):
            failures.append(f"{profile.name}: {stats['segfault']} mutant(s) segfaulted")

        score = score_of(stats)
        report[profile.name] = {"stats": stats, "score": score, "floor": profile.floor}
        shown = "n/a" if score is None else f"{score:.1f}%"
        print(
            f"   killed {stats.get('killed', 0):4d}  survived {stats.get('survived', 0):4d}"
            f"  no-tests {stats.get('no_tests', 0):4d}  score {shown}",
            flush=True,
        )
        if args.enforce and profile.floor is not None:
            if score is None:
                # "No score" must not read as "floor cleared". Every mutant
                # landing in `no_tests`, or empty stats, would otherwise pass
                # a gated profile in silence — the precise shape of failure
                # this pilot exists to detect.
                failures.append(
                    f"{profile.name}: produced no score, cannot check floor {profile.floor:.0f}%"
                )
            elif score < profile.floor:
                failures.append(f"{profile.name}: {score:.1f}% below floor {profile.floor:.0f}%")

    if args.report:
        args.report.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        print(f"\nwrote {args.report}")

    if failures:
        print("\n".join(["", "FAILED:", *(f"  {f}" for f in failures)]), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
