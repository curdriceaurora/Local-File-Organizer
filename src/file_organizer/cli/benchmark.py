"""Benchmark command for performance measurement and optimization analysis.

Provides performance benchmarking capabilities to measure file processing
speed, memory usage, and other performance metrics.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import typer

benchmark_app = typer.Typer(
    name="benchmark",
    help="Benchmark file processing performance.",
    no_args_is_help=True,
)


@benchmark_app.command()
def run(
    input_path: Path = typer.Argument(
        Path("tests/fixtures/"),
        help="Path to files to benchmark.",
    ),
    iterations: int = typer.Option(
        1,
        "--iterations",
        "-i",
        help="Number of iterations to run.",
        min=1,
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output results as JSON.",
    ),
) -> None:
    """Run a baseline I/O performance benchmark.

    Measures file stat access speed, memory usage, and timing statistics.
    This benchmarks simple I/O overhead (file discovery and stat calls), not
    the full file-organization pipeline. To measure real processing speed,
    run the actual organization routine or add a --process flag.
    """
    # Import Rich here to avoid affecting Typer's help text rendering
    from rich.console import Console
    from rich.table import Table

    # Initialize console for output
    console = Console()

    # Resolve path
    input_path = input_path.resolve()

    if not input_path.exists():
        console.print(f"[red]Error: Path does not exist: {input_path}[/red]")
        raise typer.Exit(code=1)

    # Get list of files
    try:
        files = list(input_path.rglob("*"))
        files = [f for f in files if f.is_file()]
    except Exception as e:
        console.print(f"[red]Error reading files: {e}[/red]")
        raise typer.Exit(code=1) from e

    if not files:
        if json_output:
            console.print(
                json.dumps(
                    {
                        "files_processed": 0,
                        "total_time_seconds": 0.0,
                        "median_time": 0.0,
                        "avg_time": 0.0,
                        "peak_memory_mb": 0.0,
                        "cache_hits": 0,
                        "cache_misses": 0,
                        "llm_calls": 0,
                    }
                )
            )
        else:
            console.print("[yellow]No files found in the specified path.[/yellow]")
        return

    # Initialize monitoring (imported lazily to reduce startup latency)
    from file_organizer.optimization.memory_profiler import MemoryProfiler
    from file_organizer.optimization.resource_monitor import ResourceMonitor

    monitor = ResourceMonitor()
    profiler = MemoryProfiler()

    # Run benchmarks
    times: list[float] = []
    total_time = 0.0

    if not json_output:
        console.print(
            f"[bold]Benchmarking[/bold] {len(files)} files over {iterations} iteration(s)..."
        )

    # Start memory profiling
    profiler.start_tracking(interval_seconds=0.1)

    for iteration in range(iterations):
        if not json_output:
            console.print(f"[dim]Iteration {iteration + 1}/{iterations}...[/dim]")

        # Baseline I/O benchmark: measures file stat access overhead only
        start_time = time.monotonic()

        for file_path in files:
            try:
                _ = file_path.stat()
            except Exception:
                pass

        end_time = time.monotonic()
        iteration_time = end_time - start_time
        times.append(iteration_time)
        total_time += iteration_time

    # Stop memory profiling
    timeline = profiler.stop_tracking()

    # Calculate statistics
    avg_time = total_time / iterations if iterations > 0 else 0.0
    if not times:
        median_time = 0.0
    else:
        sorted_times = sorted(times)
        n = len(sorted_times)
        if n % 2 == 1:
            median_time = sorted_times[n // 2]
        else:
            median_time = (sorted_times[n // 2 - 1] + sorted_times[n // 2]) / 2

    # Get peak memory from both monitor and profiler
    memory_info = monitor.get_memory_usage()
    peak_memory_mb = memory_info.rss / (1024 * 1024)

    # Also use profiler timeline data if available
    if timeline.snapshots:
        timeline_peak = max(s.rss for s in timeline.snapshots) / (1024 * 1024)
        peak_memory_mb = max(peak_memory_mb, timeline_peak)

    # Prepare results
    results = {
        "files_processed": len(files),
        "total_time_seconds": round(total_time, 4),
        "median_time": round(median_time, 4),
        "avg_time": round(avg_time, 4),
        "peak_memory_mb": round(peak_memory_mb, 2),
        # TODO: compute real cache/LLM metrics when full processing pipeline is used
        "cache_hits": 0,
        "cache_misses": 0,
        "llm_calls": 0,
    }

    # Output results
    if json_output:
        console.print(json.dumps(results))
    else:
        # Display as table
        table = Table(title="Benchmark Results")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Files Processed", str(results["files_processed"]))
        table.add_row("Total Time (s)", str(results["total_time_seconds"]))
        table.add_row("Median Time (s)", str(results["median_time"]))
        table.add_row("Average Time (s)", str(results["avg_time"]))
        table.add_row("Peak Memory (MB)", str(results["peak_memory_mb"]))
        table.add_row("Cache Hits", str(results["cache_hits"]))
        table.add_row("Cache Misses", str(results["cache_misses"]))
        table.add_row("LLM Calls", str(results["llm_calls"]))

        console.print(table)
        console.print("\n[bold green]Benchmark completed[/bold green]")
