"""Benchmark script for BM25 search performance.

Measures performance of BM25 indexing and search operations with different corpus
sizes. Outputs timing data as JSON for comparison.
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

# Try to import BM25Index - if dependencies are missing, we'll create a stub for dry-run mode
BM25Index = None
try:
    # Import BM25Index directly from module to avoid triggering package __init__.py
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "bm25_index",
        Path(__file__).parent.parent / "src" / "file_organizer" / "services" / "search" / "bm25_index.py"
    )
    bm25_module = importlib.util.module_from_spec(spec)

    # Mock loguru if not available
    try:
        import loguru
    except ImportError:
        # Create a minimal mock for loguru
        import types
        loguru = types.ModuleType("loguru")
        loguru.logger = types.SimpleNamespace(debug=lambda *args, **kwargs: None)
        sys.modules["loguru"] = loguru

    spec.loader.exec_module(bm25_module)
    BM25Index = bm25_module.BM25Index
except Exception as e:
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


def generate_test_documents(count: int) -> tuple[list[str], list[Path]]:
    """Generate test documents and paths for benchmarking.

    Args:
        count: Number of documents to generate.

    Returns:
        Tuple of (documents, paths).
    """
    tmp = Path(tempfile.gettempdir())

    # Generate diverse document content for realistic BM25 behavior
    topics = [
        "quarterly finance budget report annual revenue",
        "machine learning python neural network training",
        "legal contract software agreement license terms",
        "recipe baking chocolate cookie dessert ingredients",
        "travel itinerary japan vacation hotel booking",
        "medical diagnosis patient treatment healthcare record",
        "engineering design specification technical documentation",
        "marketing campaign strategy social media analytics",
        "research paper scientific study methodology results",
        "project management timeline milestone deliverable schedule",
    ]

    documents = []
    paths = []

    for i in range(count):
        # Rotate through topics and add unique identifiers
        topic = topics[i % len(topics)]
        doc = f"{topic} document_{i:06d} file_{i:06d}"
        documents.append(doc)
        paths.append(tmp / f"doc_{i:06d}.txt")

    return documents, paths


def benchmark_indexing(docs: list[str], paths: list[Path]) -> tuple[BM25Index, float]:
    """Benchmark BM25 index building.

    Args:
        docs: Documents to index.
        paths: Corresponding file paths.

    Returns:
        Tuple of (index, elapsed time in seconds).
    """
    index = BM25Index()
    start = time.perf_counter()
    index.index(docs, paths)
    elapsed = time.perf_counter() - start
    return index, elapsed


def benchmark_search(index: BM25Index, query: str, top_k: int) -> tuple[list[tuple[Path, float]], float]:
    """Benchmark BM25 search operation.

    Args:
        index: BM25 index to search.
        query: Search query string.
        top_k: Number of results to retrieve.

    Returns:
        Tuple of (results, elapsed time in seconds).
    """
    start = time.perf_counter()
    results = index.search(query, top_k=top_k)
    elapsed = time.perf_counter() - start
    return results, elapsed


def run_benchmark(
    num_docs: int,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Run BM25 search benchmark for given corpus size.

    Args:
        num_docs: Number of documents to index.
        dry_run: If True, skip actual operations and return dummy data.

    Returns:
        Dictionary with benchmark results.
    """
    if dry_run:
        logger.info(f"[DRY RUN] Would benchmark BM25 search with {num_docs} documents")
        return {
            "num_docs": num_docs,
            "dry_run": True,
            "indexing_time": 0.0,
            "search_time_avg": 0.0,
            "search_results_avg": 0,
        }

    if BM25Index is None:
        logger.info("ERROR: BM25Index could not be imported. Install dependencies:")
        logger.info("  pip install loguru rank-bm25")
        logger.info("Or run with --dry-run to test the script structure")
        sys.exit(1)

    logger.info(f"Starting benchmark for {num_docs} documents")

    # Generate test data
    logger.info(f"Generating {num_docs} test documents...")
    generation_start = time.perf_counter()
    documents, paths = generate_test_documents(num_docs)
    generation_time = time.perf_counter() - generation_start
    logger.info(f"Document generation completed in {generation_time:.2f}s")

    # Benchmark indexing
    logger.info("Benchmarking BM25 indexing...")
    index, indexing_time = benchmark_indexing(documents, paths)
    logger.info(f"Indexing: Built index with {index.size} documents in {indexing_time:.4f}s")

    # Benchmark searches with various queries
    queries = [
        ("finance budget report", 10),
        ("machine learning python", 10),
        ("legal contract agreement", 10),
        ("recipe chocolate cookie", 10),
        ("travel japan vacation", 10),
        ("medical patient treatment", 10),
        ("engineering design specification", 10),
        ("marketing campaign strategy", 10),
        ("research paper scientific", 10),
        ("project management timeline", 10),
    ]

    logger.info(f"Benchmarking {len(queries)} search queries...")
    search_times = []
    search_results_counts = []

    for query, top_k in queries:
        results, search_time = benchmark_search(index, query, top_k)
        search_times.append(search_time)
        search_results_counts.append(len(results))

    avg_search_time = sum(search_times) / len(search_times) if search_times else 0.0
    avg_results = sum(search_results_counts) / len(search_results_counts) if search_results_counts else 0.0

    logger.info(f"Search: Average {avg_search_time:.4f}s per query, average {avg_results:.1f} results")

    return {
        "num_docs": num_docs,
        "dry_run": False,
        "generation_time": round(generation_time, 4),
        "indexing_time": round(indexing_time, 4),
        "index_size": index.size,
        "num_queries": len(queries),
        "search_time_avg": round(avg_search_time, 6),
        "search_time_min": round(min(search_times), 6),
        "search_time_max": round(max(search_times), 6),
        "search_results_avg": round(avg_results, 2),
    }


def main() -> None:
    """Run BM25 search benchmarks."""
    parser = argparse.ArgumentParser(
        description="Benchmark BM25 search performance",
    )
    parser.add_argument(
        "--docs",
        type=int,
        default=1000,
        help="Number of documents to index (default: 1000)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run in dry-run mode without performing operations",
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

    # Check if rank-bm25 is available (unless doing dry-run)
    if not args.dry_run:
        try:
            import rank_bm25
        except ImportError:
            logger.info("ERROR: rank-bm25 package is required")
            logger.info("Install with: pip install rank-bm25")
            logger.info("Or run with --dry-run to test the script structure")
            sys.exit(1)

    # Run benchmarks
    if args.all_sizes:
        sizes = [1000, 10000, 50000]
        logger.info("Running benchmarks for all sizes: {}", sizes)
    else:
        sizes = [args.docs]

    results = []
    for size in sizes:
        result = run_benchmark(size, args.dry_run)
        results.append(result)
        logger.success(f"Completed benchmark for {size} documents")

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
