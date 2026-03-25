"""Benchmark script for deduplication performance.

Measures performance of file hashing, duplicate indexing, and detection
operations with different file counts and duplicate ratios. Outputs timing
data as JSON for comparison.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Try to import deduplication modules
DuplicateDetector = None
DuplicateIndex = None
FileHasher = None
ScanOptions = None

try:
    from file_organizer.services.deduplication.detector import (
        DuplicateDetector,
        ScanOptions,
    )
    from file_organizer.services.deduplication.hasher import FileHasher
    from file_organizer.services.deduplication.index import DuplicateIndex
except ImportError:
    # If we can't import, we'll only support dry-run mode
    pass


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


def create_test_files(base_dir: Path, count: int, duplicate_ratio: float = 0.3) -> None:
    """Create test files with duplicates for benchmarking.

    Args:
        base_dir: Base directory to create files in.
        count: Total number of files to create.
        duplicate_ratio: Ratio of files that should be duplicates (0.0-1.0).
    """
    # Create subdirectories
    num_subdirs = max(10, count // 100)
    files_per_dir = count // num_subdirs

    # Calculate how many unique files vs duplicates
    num_unique = int(count * (1 - duplicate_ratio))
    num_duplicates = count - num_unique

    # Create unique file contents
    unique_contents = []
    for i in range(num_unique):
        content = f"Unique file content {i:06d} with some text to make it larger\n" * 10
        unique_contents.append(content)

    # Create duplicate contents (reuse from unique)
    all_contents = unique_contents.copy()
    for i in range(num_duplicates):
        # Reuse content from unique files to create duplicates
        all_contents.append(unique_contents[i % num_unique])

    # Write files across subdirectories
    file_index = 0
    for i in range(num_subdirs):
        subdir = base_dir / f"subdir_{i:04d}"
        subdir.mkdir(parents=True, exist_ok=True)

        for j in range(files_per_dir):
            if file_index < len(all_contents):
                file_path = subdir / f"file_{j:06d}.txt"
                file_path.write_text(all_contents[file_index])
                file_index += 1

    # Create remaining files in root
    remaining = count - file_index
    for k in range(remaining):
        if file_index < len(all_contents):
            file_path = base_dir / f"root_file_{k:06d}.txt"
            file_path.write_text(all_contents[file_index])
            file_index += 1


def benchmark_hashing(base_dir: Path, algorithm: str = "sha256") -> tuple[dict[Path, str], float]:
    """Benchmark file hashing operation.

    Args:
        base_dir: Directory containing files to hash.
        algorithm: Hash algorithm to use.

    Returns:
        Tuple of (hash results, elapsed time in seconds).
    """
    hasher = FileHasher()
    files = [f for f in base_dir.rglob("*") if f.is_file()]

    start = time.perf_counter()
    results = hasher.compute_batch(files, algorithm)
    elapsed = time.perf_counter() - start

    return results, elapsed


def benchmark_indexing(base_dir: Path, algorithm: str = "sha256") -> tuple[DuplicateIndex, float]:
    """Benchmark duplicate index building.

    Args:
        base_dir: Directory to scan and index.
        algorithm: Hash algorithm to use.

    Returns:
        Tuple of (index, elapsed time in seconds).
    """
    detector = DuplicateDetector()
    options = ScanOptions(algorithm=algorithm)

    start = time.perf_counter()
    index = detector.scan_directory(base_dir, options)
    elapsed = time.perf_counter() - start

    return index, elapsed


def benchmark_duplicate_detection(index: DuplicateIndex) -> tuple[dict, float]:
    """Benchmark duplicate detection from index.

    Args:
        index: DuplicateIndex to query for duplicates.

    Returns:
        Tuple of (duplicate groups, elapsed time in seconds).
    """
    start = time.perf_counter()
    duplicates = index.get_duplicates()
    stats = index.get_statistics()
    elapsed = time.perf_counter() - start

    return stats, elapsed


def run_benchmark(
    num_files: int,
    dry_run: bool = False,
    duplicate_ratio: float = 0.3,
    algorithm: str = "sha256",
) -> dict[str, Any]:
    """Run deduplication benchmark for given file count.

    Args:
        num_files: Number of files to create and process.
        dry_run: If True, skip actual file creation and operations.
        duplicate_ratio: Ratio of files that should be duplicates.
        algorithm: Hash algorithm to use.

    Returns:
        Dictionary with benchmark results.
    """
    if dry_run:
        logger.info(f"[DRY RUN] Would benchmark dedup with {num_files} files")
        return {
            "num_files": num_files,
            "duplicate_ratio": duplicate_ratio,
            "algorithm": algorithm,
            "dry_run": True,
            "file_creation_time": 0.0,
            "hashing_time": 0.0,
            "indexing_time": 0.0,
            "detection_time": 0.0,
            "total_time": 0.0,
        }

    if DuplicateDetector is None or FileHasher is None or DuplicateIndex is None:
        logger.info("ERROR: Deduplication modules could not be imported")
        logger.info("Make sure the file_organizer package is available")
        logger.info("Or run with --dry-run to test the script structure")
        sys.exit(1)

    logger.info(f"Starting benchmark for {num_files} files with {duplicate_ratio*100:.0f}% duplicates")

    # Create temporary directory
    with tempfile.TemporaryDirectory() as tmpdir:
        base_dir = Path(tmpdir)

        # Create test files
        logger.info(f"Creating {num_files} test files...")
        creation_start = time.perf_counter()
        create_test_files(base_dir, num_files, duplicate_ratio)
        creation_time = time.perf_counter() - creation_start
        logger.info(f"File creation completed in {creation_time:.2f}s")

        # Benchmark hashing
        logger.info(f"Benchmarking file hashing ({algorithm})...")
        hash_results, hashing_time = benchmark_hashing(base_dir, algorithm)
        logger.info(f"Hashing: Processed {len(hash_results)} files in {hashing_time:.4f}s")

        # Benchmark indexing
        logger.info("Benchmarking duplicate indexing...")
        index, indexing_time = benchmark_indexing(base_dir, algorithm)
        logger.info(f"Indexing: Built index with {len(index)} files in {indexing_time:.4f}s")

        # Benchmark duplicate detection
        logger.info("Benchmarking duplicate detection...")
        stats, detection_time = benchmark_duplicate_detection(index)
        logger.info(f"Detection: Found {stats['duplicate_groups']} duplicate groups in {detection_time:.4f}s")

        total_time = creation_time + hashing_time + indexing_time + detection_time

        return {
            "num_files": num_files,
            "duplicate_ratio": duplicate_ratio,
            "algorithm": algorithm,
            "dry_run": False,
            "file_creation_time": round(creation_time, 4),
            "hashing_time": round(hashing_time, 4),
            "hashing_files": len(hash_results),
            "indexing_time": round(indexing_time, 4),
            "index_size": len(index),
            "detection_time": round(detection_time, 6),
            "duplicate_groups": stats["duplicate_groups"],
            "duplicate_files": stats["duplicate_files"],
            "wasted_space_mb": stats["wasted_space_mb"],
            "total_time": round(total_time, 4),
            "avg_time_per_file": round(hashing_time / len(hash_results), 6) if hash_results else 0,
        }


def main() -> None:
    """Run deduplication benchmarks."""
    parser = argparse.ArgumentParser(
        description="Benchmark deduplication performance",
    )
    parser.add_argument(
        "--files",
        type=int,
        default=1000,
        help="Number of files to create and process (default: 1000)",
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
    parser.add_argument(
        "--duplicate-ratio",
        type=float,
        default=0.3,
        help="Ratio of duplicate files (0.0-1.0, default: 0.3)",
    )
    parser.add_argument(
        "--algorithm",
        type=str,
        default="sha256",
        choices=["md5", "sha256"],
        help="Hash algorithm to use (default: sha256)",
    )

    args = parser.parse_args()

    # Validate duplicate ratio
    if not 0.0 <= args.duplicate_ratio <= 1.0:
        logger.info("ERROR: --duplicate-ratio must be between 0.0 and 1.0")
        sys.exit(1)

    # Run benchmarks
    if args.all_sizes:
        sizes = [1000, 10000, 50000]
        logger.info("Running benchmarks for all sizes: {}", sizes)
    else:
        sizes = [args.files]

    results = []
    for size in sizes:
        result = run_benchmark(size, args.dry_run, args.duplicate_ratio, args.algorithm)
        results.append(result)
        logger.success(f"Completed benchmark for {size} files")

    # Output results
    output_data = {
        "benchmarks": results,
        "summary": {
            "total_runs": len(results),
            "sizes_tested": sizes,
            "duplicate_ratio": args.duplicate_ratio,
            "algorithm": args.algorithm,
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
