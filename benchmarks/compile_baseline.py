"""Compile individual benchmark results into baseline_results.json."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


def load_json(filepath: Path) -> dict[str, Any] | None:
    """Load JSON file, return None if it doesn't exist."""
    if not filepath.exists():
        return None
    return json.loads(filepath.read_text())


def compile_baseline_results() -> dict[str, Any]:
    """Compile all benchmark results into a single baseline document.

    Returns:
        Dictionary containing all baseline benchmark results.
    """
    benchmarks_dir = Path(__file__).parent

    # Load individual benchmark results
    file_scanning = load_json(benchmarks_dir / "file_scanning_baseline.json")
    search = load_json(benchmarks_dir / "search_baseline.json") or load_json(benchmarks_dir / "search_baseline_dry.json")
    dedup_1000 = load_json(benchmarks_dir / "dedup_1000.json") or load_json(benchmarks_dir / "dedup_baseline_dry.json")
    dedup_5000 = load_json(benchmarks_dir / "dedup_5000.json")
    dedup_10000 = load_json(benchmarks_dir / "dedup_10000.json")

    # Compile deduplication results
    dedup_benchmarks = []
    for dedup_result in [dedup_1000, dedup_5000, dedup_10000]:
        if dedup_result and dedup_result.get("benchmarks"):
            dedup_benchmarks.extend(dedup_result["benchmarks"])

    dedup_results = {
        "benchmarks": dedup_benchmarks,
        "summary": {
            "total_runs": len(dedup_benchmarks),
            "sizes_tested": [b.get("files") or b.get("num_files") for b in dedup_benchmarks if not b.get("dry_run", False)],
        },
        "note": "Some benchmarks run in dry-run mode due to missing dependencies" if any(b.get("dry_run") for b in dedup_benchmarks) else None
    } if dedup_benchmarks else None

    # Check if search or dedup used dry-run
    search_dry_run = search and search.get("benchmarks", [{}])[0].get("dry_run", False)
    dedup_dry_run = dedup_results and any(b.get("dry_run", False) for b in dedup_results.get("benchmarks", []))

    # Build baseline results document
    baseline = {
        "metadata": {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "description": "Baseline performance benchmarks for Large Library Performance Optimization",
            "purpose": "Establish performance baseline before optimizations",
            "environment": {
                "python_version": "3.14",
                "platform": "macOS",
            },
            "limitations": []
        },
        "file_scanning": file_scanning,
        "search": search,
        "deduplication": dedup_results,
        "summary": {
            "benchmarks_completed": sum([
                1 if file_scanning else 0,
                1 if search else 0,
                1 if dedup_results else 0,
            ]),
            "total_benchmark_types": 3,
            "notes": []
        }
    }

    # Add limitation notes
    if search_dry_run:
        baseline["metadata"]["limitations"].append(
            "Search benchmark run in dry-run mode due to missing rank-bm25 dependency"
        )
        baseline["summary"]["notes"].append(
            "Search benchmarks should be re-run with real data after installing dependencies"
        )
    if dedup_dry_run:
        baseline["metadata"]["limitations"].append(
            "Deduplication benchmark run in dry-run mode due to missing dependencies"
        )
        baseline["summary"]["notes"].append(
            "Deduplication benchmarks should be re-run with real data after installing dependencies"
        )

    # Clean up empty lists
    if not baseline["metadata"]["limitations"]:
        del baseline["metadata"]["limitations"]
    if not baseline["summary"]["notes"]:
        del baseline["summary"]["notes"]

    return baseline


def main() -> None:
    """Compile baseline results and save to baseline_results.json."""
    baseline = compile_baseline_results()

    output_path = Path(__file__).parent / "baseline_results.json"
    output_path.write_text(json.dumps(baseline, indent=2))

    print("=" * 60)
    print("BASELINE RESULTS COMPILED")
    print("=" * 60)
    print(f"Output: {output_path}")
    print(f"Benchmarks included: {baseline['summary']['benchmarks_completed']}/3")
    print("\nSummary:")
    if baseline.get("file_scanning"):
        sizes = baseline["file_scanning"]["summary"]["sizes_tested"]
        print(f"  - File Scanning: {len(sizes)} size(s) tested {sizes}")
    if baseline.get("search"):
        sizes = baseline["search"]["summary"]["sizes_tested"]
        print(f"  - Search: {len(sizes)} size(s) tested {sizes}")
    if baseline.get("deduplication"):
        sizes = baseline["deduplication"]["summary"]["sizes_tested"]
        print(f"  - Deduplication: {len(sizes)} size(s) tested {sizes}")


if __name__ == "__main__":
    main()
