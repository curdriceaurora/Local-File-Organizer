"""Benchmark CLI and API startup latency.

Measures import times and command execution to track startup performance.
Run with: python scripts/benchmark_startup.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path


def benchmark_cli_startup() -> float:
    """Measure time to import CLI module."""
    start = time.time()
    subprocess.run(
        [sys.executable, "-c", "from file_organizer.cli import main"],
        capture_output=True,
        timeout=10,
    )
    return time.time() - start


def benchmark_api_startup() -> float:
    """Measure time to import API module."""
    start = time.time()
    subprocess.run(
        [sys.executable, "-c", "from file_organizer.api import main"],
        capture_output=True,
        timeout=10,
    )
    return time.time() - start


def benchmark_help_command() -> float:
    """Measure time to run 'file-organizer --help'."""
    start = time.time()
    subprocess.run(
        ["file-organizer", "--help"],
        capture_output=True,
        timeout=10,
    )
    return time.time() - start


def main() -> None:
    """Run all benchmarks and report results."""
    print("Startup Latency Benchmark")
    print("=" * 50)

    benchmarks = {
        "CLI module import": benchmark_cli_startup,
        "API module import": benchmark_api_startup,
        "--help command": benchmark_help_command,
    }

    results: dict[str, float | None] = {}
    for name, func in benchmarks.items():
        try:
            elapsed = func()
            results[name] = elapsed
            print(f"{name:<25} {elapsed:.3f}s")
        except Exception as e:
            print(f"{name:<25} ERROR: {e}")
            results[name] = None

    # Check against target (should be < 0.5s)
    target = 0.5
    print(f"\nTarget: < {target}s per operation")

    cli_time = results.get("CLI module import")
    if cli_time is not None and cli_time < target:
        print(f"  CLI startup: {cli_time:.3f}s (PASS)")
    elif cli_time is not None:
        print(f"  CLI startup: {cli_time:.3f}s (FAIL)")

    # Optionally save results to JSON
    if "--json" in sys.argv:
        out = Path("benchmarks.json")
        out.write_text(json.dumps(results, indent=2))
        print(f"\nResults saved to {out}")


if __name__ == "__main__":
    main()
