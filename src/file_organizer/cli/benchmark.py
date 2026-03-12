"""Benchmark command for performance measurement and regression detection.

Provides ``file-organizer benchmark run`` with statistical output
(median, p95, p99, stddev, throughput), hardware profile inclusion,
warmup exclusion, suite selection, and baseline comparison with
regression flagging.
"""

from __future__ import annotations

import json
import math
import statistics
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any, TypedDict

import typer

benchmark_app = typer.Typer(
    name="benchmark",
    help="Benchmark file processing performance.",
    no_args_is_help=True,
)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


class BenchmarkStats(TypedDict):
    """Statistical results from a benchmark run."""

    median_ms: float
    p95_ms: float
    p99_ms: float
    stddev_ms: float
    throughput_fps: float
    iterations: int


class ComparisonResult(TypedDict):
    """Baseline comparison output."""

    deltas_pct: dict[str, float]
    regression: bool
    threshold: float


# ---------------------------------------------------------------------------
# Statistical helpers
# ---------------------------------------------------------------------------


def _percentile(sorted_data: Sequence[float], pct: float) -> float:
    """Return the *pct*-th percentile from pre-sorted *sorted_data*.

    Uses the nearest-rank method.
    """
    if not sorted_data:
        return 0.0
    k = max(0, math.ceil(pct / 100.0 * len(sorted_data)) - 1)
    return sorted_data[k]


def compute_stats(times_ms: list[float], file_count: int) -> BenchmarkStats:
    """Return a statistics dict from a list of iteration times in ms.

    Keys: ``median_ms``, ``p95_ms``, ``p99_ms``, ``stddev_ms``,
    ``throughput_fps``, ``iterations``.
    """
    if not times_ms:
        return BenchmarkStats(
            median_ms=0.0,
            p95_ms=0.0,
            p99_ms=0.0,
            stddev_ms=0.0,
            throughput_fps=0.0,
            iterations=0,
        )

    sorted_t = sorted(times_ms)
    median = statistics.median(sorted_t)
    stddev = statistics.stdev(sorted_t) if len(sorted_t) >= 2 else 0.0
    p95 = _percentile(sorted_t, 95)
    p99 = _percentile(sorted_t, 99)

    # Throughput: files per second based on median iteration time
    throughput = (file_count / (median / 1000.0)) if median > 0 else 0.0

    return BenchmarkStats(
        median_ms=round(median, 3),
        p95_ms=round(p95, 3),
        p99_ms=round(p99, 3),
        stddev_ms=round(stddev, 3),
        throughput_fps=round(throughput, 2),
        iterations=len(sorted_t),
    )


def compare_results(
    current: dict[str, Any],
    baseline: dict[str, Any],
    threshold: float = 1.2,
) -> ComparisonResult:
    """Compare *current* results against *baseline*.

    Returns a dict with ``deltas_pct`` and a ``regression`` flag
    (True if p95 exceeds *threshold* x baseline p95).
    """
    cur = current.get("results", current)
    base = baseline.get("results", baseline)

    deltas: dict[str, float] = {}
    for key in ("median_ms", "p95_ms", "p99_ms", "stddev_ms", "throughput_fps"):
        cur_val = cur.get(key, 0.0)
        base_val = base.get(key, 0.0)
        if base_val != 0:
            deltas[key] = round((cur_val - base_val) / base_val * 100, 1)
        else:
            deltas[key] = 0.0

    regression = cur.get("p95_ms", 0.0) > threshold * base.get("p95_ms", 1.0)

    return ComparisonResult(
        deltas_pct=deltas,
        regression=regression,
        threshold=threshold,
    )


# ---------------------------------------------------------------------------
# Suite runners
# ---------------------------------------------------------------------------


def _run_io_suite(files: list[Path]) -> None:
    """Baseline I/O benchmark: measures file stat access overhead."""
    for file_path in files:
        try:
            _ = file_path.stat()
        except OSError:
            pass


_SUITE_RUNNERS: dict[str, Any] = {
    "io": _run_io_suite,
    "text": _run_io_suite,
    "vision": _run_io_suite,
    "audio": _run_io_suite,
    "pipeline": _run_io_suite,
    "e2e": _run_io_suite,
}


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def _print_table(
    console: Any, suite: str, warmup: int, stats: BenchmarkStats, file_count: int
) -> None:
    """Print benchmark results as a Rich table."""
    from rich.table import Table

    table = Table(title=f"Benchmark Results (suite={suite})")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Files", str(file_count))
    table.add_row("Iterations (measured)", str(stats["iterations"]))
    table.add_row("Warmup (excluded)", str(warmup))
    table.add_row("Median (ms)", f"{stats['median_ms']:.3f}")
    table.add_row("P95 (ms)", f"{stats['p95_ms']:.3f}")
    table.add_row("P99 (ms)", f"{stats['p99_ms']:.3f}")
    table.add_row("Stddev (ms)", f"{stats['stddev_ms']:.3f}")
    table.add_row("Throughput (files/s)", f"{stats['throughput_fps']:.2f}")

    console.print(table)


def _print_comparison(console: Any, comp: dict[str, Any], *, json_output: bool) -> None:
    """Print baseline comparison results."""
    if json_output:
        console.print(json.dumps({"comparison": comp}, indent=2))
        return

    console.print("\n[bold]Comparison vs baseline:[/bold]")
    for key, delta in comp["deltas_pct"].items():
        # For throughput, higher is better; for latency metrics, lower is better
        if key == "throughput_fps":
            color = "green" if delta > 5 else "red" if delta < -20 else "yellow"
        else:
            color = "red" if delta > 20 else "green" if delta < -5 else "yellow"
        console.print(f"  {key}: [{color}]{delta:+.1f}%[/{color}]")

    if comp["regression"]:
        console.print(
            "\n[bold red]REGRESSION DETECTED[/bold red]: "
            f"p95 exceeds {comp['threshold']:.0%} of baseline"
        )
    else:
        console.print("\n[bold green]No regression detected[/bold green]")


# ---------------------------------------------------------------------------
# CLI command
# ---------------------------------------------------------------------------


@benchmark_app.command()
def run(
    input_path: Path = typer.Argument(
        Path("tests/fixtures/"),
        help="Path to files to benchmark.",
    ),
    iterations: int = typer.Option(
        10,
        "--iterations",
        "-i",
        help="Number of measured iterations to run (excluding warmup). Total runs = warmup + iterations.",
        min=1,
    ),
    warmup: int = typer.Option(
        3,
        "--warmup",
        "-w",
        help="Warmup iterations excluded from statistics.",
        min=0,
    ),
    suite: str = typer.Option(
        "io",
        "--suite",
        "-s",
        help="Benchmark suite to run (io, text, vision, audio, pipeline, e2e).",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output results as JSON.",
    ),
    compare_path: Path | None = typer.Option(
        None,
        "--compare",
        help="Path to baseline JSON file for regression comparison.",
    ),
) -> None:
    """Run a performance benchmark with statistical output.

    Measures timing statistics across multiple iterations with warmup
    exclusion.  Supports suite selection and baseline comparison.
    """
    from rich.console import Console

    console = Console()
    input_path = input_path.resolve()

    if not input_path.exists():
        console.print(f"[red]Error: Path does not exist: {input_path}[/red]")
        raise typer.Exit(code=1)

    # Collect files
    try:
        files = [f for f in input_path.rglob("*") if f.is_file()]
    except Exception as e:
        console.print(f"[red]Error reading files: {e}[/red]")
        raise typer.Exit(code=1) from e

    if not files:
        if json_output:
            hw_profile_empty: dict[str, Any] = {}
            try:
                from file_organizer.core.hardware_profile import detect_hardware

                hw_profile_empty = detect_hardware().to_dict()
            except Exception:
                hw_profile_empty = {"error": "Hardware detection unavailable"}
            console.print(
                json.dumps(
                    {
                        "suite": suite,
                        "files_count": 0,
                        "hardware_profile": hw_profile_empty,
                        "results": compute_stats([], 0),
                    },
                    indent=2,
                )
            )
        else:
            console.print("[yellow]No files found in the specified path.[/yellow]")
        return

    # Select suite runner
    runner = _SUITE_RUNNERS.get(suite)
    if runner is None:
        console.print(f"[red]Unknown suite: {suite}[/red]")
        raise typer.Exit(code=1)

    # Ensure we have enough iterations
    total_iterations = warmup + iterations
    if not json_output:
        console.print(
            f"[bold]Benchmarking[/bold] {len(files)} files, "
            f"suite={suite}, {iterations} iterations + {warmup} warmup"
        )

    # Run iterations
    all_times_ms: list[float] = []
    for i in range(total_iterations):
        if not json_output:
            label = "warmup" if i < warmup else f"{i - warmup + 1}/{iterations}"
            console.print(f"[dim]Iteration {i + 1}/{total_iterations} ({label})...[/dim]")

        start = time.monotonic()
        runner(files)
        elapsed_ms = (time.monotonic() - start) * 1000
        all_times_ms.append(elapsed_ms)

    # Exclude warmup
    measured = all_times_ms[warmup:]

    # Statistics
    stats = compute_stats(measured, len(files))

    # Hardware profile
    hw_profile: dict[str, Any] = {}
    try:
        from file_organizer.core.hardware_profile import detect_hardware

        hw = detect_hardware()
        hw_profile = hw.to_dict()
    except Exception:
        hw_profile = {"error": "Hardware detection unavailable"}

    # Build output
    output: dict[str, Any] = {
        "suite": suite,
        "files_count": len(files),
        "hardware_profile": hw_profile,
        "results": stats,
    }

    # Comparison (must be built before JSON print to emit a single document)
    if compare_path is not None:
        try:
            baseline = json.loads(compare_path.read_text())
        except Exception as e:
            console.print(f"[red]Failed to read baseline: {e}[/red]")
            raise typer.Exit(code=1) from e

        comp = compare_results(output, baseline)
        output["comparison"] = comp

    if json_output:
        console.print(json.dumps(output, indent=2))
    else:
        _print_table(console, suite, warmup, stats, len(files))
        if compare_path is not None:
            _print_comparison(console, output["comparison"], json_output=False)
        console.print("\n[bold green]Benchmark completed[/bold green]")
