"""Benchmark pytest-xdist worker strategies locally.

This script is a local research harness for deciding whether CI should keep
``pytest -n=auto`` or switch to a different xdist worker configuration.

Why this exists:
- CI currently delegates worker selection to pytest-xdist via ``-n=auto``.
- GitHub-hosted runner CPU topology can make the observed worker count non-obvious.
- We want a repeatable way to compare candidate configurations before changing CI.

What it does:
- Runs selected pytest slices repeatedly across candidate xdist configurations.
- Captures wall-clock duration, exit status, and lightweight notes.
- Produces a decision-oriented summary plus optional JSON output.

Default benchmark matrix:
- worker configs: ``auto``, ``logical``, ``2``, ``4``
- slices: ``smoke`` and ``ci``

Example:
    python3 scripts/benchmark_pytest_xdist.py --repeats 3

Fast verification run:
    python3 scripts/benchmark_pytest_xdist.py --slices smoke --configs auto 2 --repeats 1
"""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import shlex
import statistics
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

DEFAULT_CONFIGS: Final[tuple[str, ...]] = ("auto", "logical", "2", "4")
DEFAULT_SLICES: Final[tuple[str, ...]] = ("smoke", "ci")
DEFAULT_REPEATS: Final[int] = 3
DEFAULT_DECISION_THRESHOLD_PCT: Final[float] = 10.0
KEEP_BASELINE_THRESHOLD_PCT: Final[float] = 5.0


@dataclass(frozen=True)
class SliceDefinition:
    """Named pytest slice used for local benchmarking."""

    name: str
    description: str
    pytest_args: tuple[str, ...]


@dataclass
class RunResult:
    """One benchmark invocation result."""

    slice_name: str
    config: str
    run_number: int
    command: list[str]
    started_at: str
    duration_seconds: float
    returncode: int
    succeeded: bool
    stdout_tail: list[str]
    stderr_tail: list[str]
    notes: list[str] = field(default_factory=list)


@dataclass
class AggregatedResult:
    """Aggregated benchmark metrics for one slice/config pair."""

    slice_name: str
    config: str
    total_runs: int
    successful_runs: int
    failed_runs: int
    median_seconds: float | None
    mean_seconds: float | None
    min_seconds: float | None
    max_seconds: float | None
    stdev_seconds: float | None


SLICES: Final[dict[str, SliceDefinition]] = {
    "smoke": SliceDefinition(
        name="smoke",
        description="Fast sanity slice for eliminating obviously bad worker configs",
        pytest_args=(
            "tests/",
            "-m",
            "smoke",
            "--timeout=30",
            "--override-ini=addopts=",
        ),
    ),
    "ci": SliceDefinition(
        name="ci",
        description="PR-representative slice matching Linux PR CI behavior",
        pytest_args=(
            "tests/",
            "-m",
            "ci",
            "--cov=file_organizer",
            "--cov-report=xml",
            "--timeout=30",
            "--override-ini=addopts=",
        ),
    ),
    "full": SliceDefinition(
        name="full",
        description="Mainline-representative full suite with coverage",
        pytest_args=(
            "tests/",
            "--cov=file_organizer",
            "--cov-fail-under=95",
            "--cov-report=xml",
            "--timeout=30",
            "--override-ini=addopts=",
        ),
    ),
}


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Benchmark pytest-xdist worker strategies locally and surface a "
            "decision-oriented summary without changing CI."
        )
    )
    parser.add_argument(
        "--configs",
        nargs="+",
        default=list(DEFAULT_CONFIGS),
        help="Worker configs to benchmark. Examples: auto logical 2 4",
    )
    parser.add_argument(
        "--slices",
        nargs="+",
        choices=sorted(SLICES),
        default=list(DEFAULT_SLICES),
        help="Pytest slices to run. Choices: smoke, ci, full",
    )
    parser.add_argument(
        "--repeats",
        type=int,
        default=DEFAULT_REPEATS,
        help=f"Number of runs per slice/config pair (default: {DEFAULT_REPEATS})",
    )
    parser.add_argument(
        "--pytest",
        default="pytest",
        help="Pytest executable to invoke (default: pytest)",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        help="Optional path to write raw results and summary as JSON",
    )
    parser.add_argument(
        "--output-markdown",
        type=Path,
        help="Optional path to write a Markdown summary",
    )
    parser.add_argument(
        "--decision-threshold-pct",
        type=float,
        default=DEFAULT_DECISION_THRESHOLD_PCT,
        help=(
            "Minimum median speedup over the auto baseline required to recommend "
            "changing CI (default: 10)"
        ),
    )
    parser.add_argument(
        "--allow-failures",
        action="store_true",
        help="Continue benchmarking all configurations even if one run fails",
    )
    parser.add_argument(
        "--extra-pytest-args",
        nargs=argparse.REMAINDER,
        default=[],
        help=(
            "Additional pytest args appended to every run. Prefix with '--'. "
            "Example: --extra-pytest-args -- --durations=25"
        ),
    )

    args = parser.parse_args()
    if args.repeats < 1:
        raise SystemExit("--repeats must be >= 1")
    if args.decision_threshold_pct < 0:
        raise SystemExit("--decision-threshold-pct must be >= 0")
    return args


def ensure_repo_root() -> Path:
    """Return the repository root."""
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        check=True,
        capture_output=True,
        text=True,
    )
    return Path(result.stdout.strip())


def build_pytest_command(
    pytest_executable: str,
    slice_definition: SliceDefinition,
    config: str,
    extra_pytest_args: list[str],
) -> list[str]:
    """Build the pytest command for one benchmark run."""
    return [
        pytest_executable,
        *slice_definition.pytest_args,
        f"-n={config}",
        *extra_pytest_args,
    ]


def tail_lines(text: str, limit: int = 10) -> list[str]:
    """Return the last few non-empty lines for debug context."""
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    return lines[-limit:]


def run_one(
    repo_root: Path,
    pytest_executable: str,
    slice_definition: SliceDefinition,
    config: str,
    run_number: int,
    extra_pytest_args: list[str],
) -> RunResult:
    """Run one benchmark command and capture timing + diagnostics."""
    command = build_pytest_command(
        pytest_executable=pytest_executable,
        slice_definition=slice_definition,
        config=config,
        extra_pytest_args=extra_pytest_args,
    )

    start_timestamp = datetime.now(tz=UTC).isoformat()
    start = time.perf_counter()
    proc = subprocess.run(
        command,
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    duration = time.perf_counter() - start

    notes: list[str] = []
    combined_output = "\n".join([proc.stdout, proc.stderr])
    if "worker" in combined_output.lower():
        notes.append("xdist output present")
    if proc.returncode != 0:
        notes.append("pytest failed")

    return RunResult(
        slice_name=slice_definition.name,
        config=config,
        run_number=run_number,
        command=command,
        started_at=start_timestamp,
        duration_seconds=duration,
        returncode=proc.returncode,
        succeeded=(proc.returncode == 0),
        stdout_tail=tail_lines(proc.stdout),
        stderr_tail=tail_lines(proc.stderr),
        notes=notes,
    )


def aggregate_results(results: list[RunResult]) -> list[AggregatedResult]:
    """Aggregate raw run data by slice/config."""
    grouped: dict[tuple[str, str], list[RunResult]] = {}
    for result in results:
        grouped.setdefault((result.slice_name, result.config), []).append(result)

    aggregated: list[AggregatedResult] = []
    for (slice_name, config), group in sorted(grouped.items()):
        durations = [result.duration_seconds for result in group if result.succeeded]
        successful_runs = len(durations)
        failed_runs = len(group) - successful_runs
        aggregated.append(
            AggregatedResult(
                slice_name=slice_name,
                config=config,
                total_runs=len(group),
                successful_runs=successful_runs,
                failed_runs=failed_runs,
                median_seconds=(statistics.median(durations) if durations else None),
                mean_seconds=(statistics.fmean(durations) if durations else None),
                min_seconds=(min(durations) if durations else None),
                max_seconds=(max(durations) if durations else None),
                stdev_seconds=(
                    statistics.stdev(durations)
                    if len(durations) > 1
                    else 0.0
                    if durations
                    else None
                ),
            )
        )
    return aggregated


def pct_faster(baseline_seconds: float, candidate_seconds: float) -> float:
    """Return positive percentage improvement over the baseline."""
    if baseline_seconds <= 0:
        return 0.0
    return ((baseline_seconds - candidate_seconds) / baseline_seconds) * 100.0


def decide_for_slice(
    slice_name: str,
    aggregated: list[AggregatedResult],
    threshold_pct: float,
) -> tuple[str, list[str]]:
    """Generate a recommendation for one slice."""
    by_config = {item.config: item for item in aggregated if item.slice_name == slice_name}
    reasons: list[str] = []
    baseline = by_config.get("auto")
    if baseline is None or baseline.median_seconds is None:
        return "No recommendation", ["No successful auto baseline run available."]
    if baseline.failed_runs:
        return "Keep auto", [
            "Baseline auto configuration is unstable; do not change CI from local data."
        ]

    eligible = [
        item
        for item in by_config.values()
        if item.median_seconds is not None and item.failed_runs == 0
    ]
    if not eligible:
        return "Keep auto", ["No configuration completed successfully."]

    winner = min(
        eligible,
        key=lambda item: item.median_seconds if item.median_seconds is not None else math.inf,
    )
    if winner.config == "auto":
        return "Keep auto", ["Auto baseline is already the fastest successful configuration."]

    assert winner.median_seconds is not None  # For type-checkers.
    speedup = pct_faster(baseline.median_seconds, winner.median_seconds)
    if speedup < KEEP_BASELINE_THRESHOLD_PCT:
        reasons.append(
            f"Best alternative ({winner.config}) is only {speedup:.1f}% faster than auto; keep auto below the 5% noise threshold."
        )
        return "Keep auto", reasons
    if speedup < threshold_pct:
        reasons.append(
            f"Best alternative ({winner.config}) is {speedup:.1f}% faster than auto, below the decision threshold of {threshold_pct:.1f}%."
        )
        return "Keep auto", reasons

    reasons.append(
        f"{winner.config} is {speedup:.1f}% faster than auto on median runtime with no failed runs."
    )
    reasons.append("Validate this winner on GitHub Actions before changing CI.")
    return f"Promote {winner.config} for CI validation", reasons


def markdown_summary(
    *,
    aggregated: list[AggregatedResult],
    decision_threshold_pct: float,
    args: argparse.Namespace,
) -> str:
    """Render a Markdown summary for artifacts or notes."""
    lines = [
        "# pytest-xdist Local Benchmark Summary",
        "",
        "## Parameters",
        f"- configs: {', '.join(args.configs)}",
        f"- slices: {', '.join(args.slices)}",
        f"- repeats: {args.repeats}",
        f"- pytest executable: `{args.pytest}`",
        f"- decision threshold: {decision_threshold_pct:.1f}%",
        "",
        "## Results",
        "",
        "| Slice | Config | Median (s) | Mean (s) | Min (s) | Max (s) | Stddev (s) | Success | Fail |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]

    for item in aggregated:
        lines.append(
            f"| {item.slice_name} | {item.config} | "
            f"{format_optional_float(item.median_seconds)} | "
            f"{format_optional_float(item.mean_seconds)} | "
            f"{format_optional_float(item.min_seconds)} | "
            f"{format_optional_float(item.max_seconds)} | "
            f"{format_optional_float(item.stdev_seconds)} | "
            f"{item.successful_runs} | {item.failed_runs} |"
        )

    lines.append("")
    lines.append("## Recommendations")
    for slice_name in args.slices:
        decision, reasons = decide_for_slice(slice_name, aggregated, decision_threshold_pct)
        lines.append(f"### {slice_name}")
        lines.append(f"- decision: {decision}")
        for reason in reasons:
            lines.append(f"- {reason}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def format_optional_float(value: float | None) -> str:
    """Format an optional float for tables."""
    return f"{value:.2f}" if value is not None else "n/a"


def print_run_banner(
    slice_definition: SliceDefinition, config: str, run_number: int, total_runs: int
) -> None:
    """Print a short progress banner."""
    print(
        f"[{slice_definition.name}] config={config} run={run_number}/{total_runs} "
        f"-> {slice_definition.description}"
    )


def print_result(result: RunResult) -> None:
    """Print a short one-line result plus compact diagnostics on failure."""
    status = "PASS" if result.succeeded else "FAIL"
    print(
        f"  {status} {result.duration_seconds:.2f}s :: {' '.join(shlex.quote(part) for part in result.command)}"
    )
    if not result.succeeded:
        if result.stdout_tail:
            print("  stdout tail:")
            for line in result.stdout_tail:
                print(f"    {line}")
        if result.stderr_tail:
            print("  stderr tail:")
            for line in result.stderr_tail:
                print(f"    {line}")


def detect_environment() -> dict[str, str]:
    """Return lightweight environment metadata for result context."""
    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "processor": platform.processor() or "unknown",
        "executable": sys.executable,
        "cwd": str(Path.cwd()),
        "pid": str(os.getpid()),
    }


def write_if_requested(path: Path | None, content: str) -> None:
    """Write output to disk when requested."""
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    print(f"Wrote {path}")


def main() -> int:
    """Run the benchmark matrix and print a decision-oriented summary."""
    args = parse_args()
    repo_root = ensure_repo_root()
    environment = detect_environment()
    all_results: list[RunResult] = []

    print("pytest-xdist Local Benchmark")
    print("=" * 60)
    print(f"Repo root: {repo_root}")
    print(f"Python:    {environment['python']} ({environment['executable']})")
    print(f"Platform:  {environment['platform']}")
    print(f"Configs:   {', '.join(args.configs)}")
    print(f"Slices:    {', '.join(args.slices)}")
    print(f"Repeats:   {args.repeats}")
    print("")

    for slice_name in args.slices:
        slice_definition = SLICES[slice_name]
        for config in args.configs:
            for run_number in range(1, args.repeats + 1):
                print_run_banner(slice_definition, config, run_number, args.repeats)
                result = run_one(
                    repo_root=repo_root,
                    pytest_executable=args.pytest,
                    slice_definition=slice_definition,
                    config=config,
                    run_number=run_number,
                    extra_pytest_args=args.extra_pytest_args,
                )
                all_results.append(result)
                print_result(result)
                if not result.succeeded and not args.allow_failures:
                    print("")
                    print(
                        "Stopping early because a benchmark run failed. Re-run with --allow-failures to continue."
                    )
                    aggregated = aggregate_results(all_results)
                    emit_outputs(
                        args=args,
                        environment=environment,
                        aggregated=aggregated,
                        all_results=all_results,
                    )
                    return 1
                print("")

    aggregated = aggregate_results(all_results)
    emit_outputs(
        args=args,
        environment=environment,
        aggregated=aggregated,
        all_results=all_results,
    )

    return 0 if all(result.succeeded for result in all_results) else 1


def emit_outputs(
    *,
    args: argparse.Namespace,
    environment: dict[str, str],
    aggregated: list[AggregatedResult],
    all_results: list[RunResult],
) -> None:
    """Print console summary and optionally write JSON/Markdown artifacts."""
    print("=" * 60)
    print("Summary")
    print("=" * 60)
    for item in aggregated:
        print(
            f"{item.slice_name:<8} config={item.config:<7} "
            f"median={format_optional_float(item.median_seconds):>6}s "
            f"success={item.successful_runs}/{item.total_runs} "
            f"fail={item.failed_runs}"
        )

    print("")
    print("Recommendations")
    print("-" * 60)
    for slice_name in args.slices:
        decision, reasons = decide_for_slice(slice_name, aggregated, args.decision_threshold_pct)
        print(f"{slice_name}: {decision}")
        for reason in reasons:
            print(f"  - {reason}")
        print("")

    markdown = markdown_summary(
        aggregated=aggregated,
        decision_threshold_pct=args.decision_threshold_pct,
        args=args,
    )
    json_payload = {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "environment": environment,
        "parameters": {
            "configs": args.configs,
            "slices": args.slices,
            "repeats": args.repeats,
            "pytest": args.pytest,
            "decision_threshold_pct": args.decision_threshold_pct,
            "extra_pytest_args": args.extra_pytest_args,
        },
        "aggregated": [asdict(item) for item in aggregated],
        "runs": [asdict(item) for item in all_results],
        "recommendations": {
            slice_name: {
                "decision": decide_for_slice(slice_name, aggregated, args.decision_threshold_pct)[
                    0
                ],
                "reasons": decide_for_slice(slice_name, aggregated, args.decision_threshold_pct)[1],
            }
            for slice_name in args.slices
        },
    }

    write_if_requested(args.output_markdown, markdown)
    if args.output_json is not None:
        write_if_requested(args.output_json, json.dumps(json_payload, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
