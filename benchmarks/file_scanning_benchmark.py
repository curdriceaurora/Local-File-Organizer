"""Benchmark script for file scanning performance.

Measures performance of file scanning operations with different directory sizes
and methods (rglob vs os.walk). Outputs timing data as JSON for comparison.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


class Logger:
    """Simple logger for benchmark output."""

    @staticmethod
    def info(msg: str, *args: Any) -> None:
        """Log info message."""
        if args:
            msg = msg.format(*args)
        print(f"[INFO] {msg}")

    @staticmethod
    def success(msg: str, *args: Any) -> None:
        """Log success message."""
        if args:
            msg = msg.format(*args)
        print(f"[SUCCESS] {msg}")


logger = Logger()


def create_test_files(base_dir: Path, count: int) -> None:
    """Create test files in a directory structure.

    Args:
        base_dir: Base directory to create files in.
        count: Number of files to create.
    """
    # Create directory structure with subdirectories
    num_subdirs = max(10, count // 100)
    files_per_dir = count // num_subdirs

    for i in range(num_subdirs):
        subdir = base_dir / f"subdir_{i:04d}"
        subdir.mkdir(parents=True, exist_ok=True)

        for j in range(files_per_dir):
            file_path = subdir / f"file_{j:06d}.txt"
            file_path.write_text(f"Test file {i}_{j}")

    # Create remaining files in root
    remaining = count - (num_subdirs * files_per_dir)
    for k in range(remaining):
        file_path = base_dir / f"root_file_{k:06d}.txt"
        file_path.write_text(f"Root test file {k}")


def benchmark_rglob(base_dir: Path) -> tuple[list[Path], float]:
    """Benchmark file collection using Path.rglob().

    Args:
        base_dir: Directory to scan.

    Returns:
        Tuple of (collected files, elapsed time in seconds).
    """
    start = time.perf_counter()
    files = [f for f in base_dir.rglob("*") if f.is_file()]
    elapsed = time.perf_counter() - start
    return files, elapsed


def benchmark_os_walk(base_dir: Path) -> tuple[list[Path], float]:
    """Benchmark file collection using os.walk().

    Args:
        base_dir: Directory to scan.

    Returns:
        Tuple of (collected files, elapsed time in seconds).
    """
    start = time.perf_counter()
    files: list[Path] = []
    for root, _dirnames, filenames in os.walk(base_dir):
        for filename in filenames:
            if not filename.startswith("."):
                files.append(Path(root) / filename)
    elapsed = time.perf_counter() - start
    return files, elapsed


def benchmark_glob(base_dir: Path) -> tuple[list[Path], float]:
    """Benchmark file collection using Path.glob() (non-recursive).

    Args:
        base_dir: Directory to scan.

    Returns:
        Tuple of (collected files, elapsed time in seconds).
    """
    start = time.perf_counter()
    files = [f for f in base_dir.glob("*") if f.is_file()]
    elapsed = time.perf_counter() - start
    return files, elapsed


def run_benchmark(
    size: int,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Run file scanning benchmark for given size.

    Args:
        size: Number of files to create and scan.
        dry_run: If True, skip actual file creation and use smaller test.

    Returns:
        Dictionary with benchmark results.
    """
    if dry_run:
        logger.info(f"[DRY RUN] Would benchmark scanning {size} files")
        return {
            "size": size,
            "dry_run": True,
            "rglob_time": 0.0,
            "os_walk_time": 0.0,
            "glob_time": 0.0,
            "files_found": 0,
        }

    logger.info(f"Starting benchmark for {size} files")

    # Create temporary directory
    with tempfile.TemporaryDirectory() as tmpdir:
        base_dir = Path(tmpdir)

        # Create test files
        logger.info(f"Creating {size} test files...")
        creation_start = time.perf_counter()
        create_test_files(base_dir, size)
        creation_time = time.perf_counter() - creation_start
        logger.info(f"File creation completed in {creation_time:.2f}s")

        # Benchmark rglob
        logger.info("Benchmarking Path.rglob()...")
        rglob_files, rglob_time = benchmark_rglob(base_dir)
        logger.info(f"rglob: Found {len(rglob_files)} files in {rglob_time:.4f}s")

        # Benchmark os.walk
        logger.info("Benchmarking os.walk()...")
        walk_files, walk_time = benchmark_os_walk(base_dir)
        logger.info(f"os.walk: Found {len(walk_files)} files in {walk_time:.4f}s")

        # Benchmark glob (non-recursive)
        logger.info("Benchmarking Path.glob()...")
        glob_files, glob_time = benchmark_glob(base_dir)
        logger.info(f"glob: Found {len(glob_files)} files in {glob_time:.4f}s")

        return {
            "size": size,
            "dry_run": False,
            "creation_time": round(creation_time, 4),
            "rglob_time": round(rglob_time, 4),
            "rglob_files": len(rglob_files),
            "os_walk_time": round(walk_time, 4),
            "os_walk_files": len(walk_files),
            "glob_time": round(glob_time, 4),
            "glob_files": len(glob_files),
        }


def main() -> None:
    """Run file scanning benchmarks."""
    parser = argparse.ArgumentParser(
        description="Benchmark file scanning performance",
    )
    parser.add_argument(
        "--size",
        type=int,
        default=1000,
        help="Number of files to create and scan (default: 1000)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run in dry-run mode without creating files",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output JSON file path (optional)",
    )
    parser.add_argument(
        "--all-sizes",
        action="store_true",
        help="Run benchmarks for all standard sizes (1000, 10000, 50000)",
    )

    args = parser.parse_args()

    # Run benchmarks
    if args.all_sizes:
        sizes = [1000, 10000, 50000]
        logger.info("Running benchmarks for all sizes: {}", sizes)
    else:
        sizes = [args.size]

    results = []
    for size in sizes:
        result = run_benchmark(size, args.dry_run)
        results.append(result)
        logger.success(f"Completed benchmark for {size} files")

    # Output results
    output_data = {
        "benchmarks": results,
        "summary": {
            "total_runs": len(results),
            "sizes_tested": sizes,
        },
    }

    print("\n" + "=" * 60)
    print("BENCHMARK RESULTS")
    print("=" * 60)
    print(json.dumps(output_data, indent=2))

    # Save to file if requested
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(json.dumps(output_data, indent=2))
        logger.success(f"Results saved to {output_path}")


if __name__ == "__main__":
    main()
