#!/usr/bin/env python3
"""Benchmark naming quality against the ground-truth corpus.

Off-CI, on-demand script.  Requires a running Ollama instance.

Usage:
    python scripts/benchmark_naming_quality.py [--model qwen2.5:3b-instruct-q4_K_M]
    python scripts/benchmark_naming_quality.py --verbose

Outputs:
    - Per-case pass/fail with diff when wrong
    - Overall accuracy percentage
    - Regression flag if score drops below --threshold (default: 0.70)

Exit codes:
    0  Accuracy >= threshold
    1  Accuracy < threshold (regression detected)
"""

from __future__ import annotations

import argparse
import sys
import textwrap
import time

# ---------------------------------------------------------------------------
# Ground-truth corpus
# ---------------------------------------------------------------------------

CORPUS: list[dict[str, str]] = [
    # (file_content_snippet, expected_folder, expected_filename)
    {
        "content": "Q3 2023 budget review. Total spend: $1.2M. Under budget by 8%.",
        "original_stem": "q3_2023_budget",
        "expected_folder": "finance",
        "expected_filename_keywords": ["budget", "2023", "q3"],
    },
    {
        "content": "Introduction to machine learning with Python. Covers regression, classification, and clustering.",
        "original_stem": "ml_intro",
        "expected_folder": "machine_learning",
        "expected_filename_keywords": ["machine", "learning", "python"],
    },
    {
        "content": "Chocolate chip cookie recipe. Ingredients: butter, sugar, eggs, flour, chocolate chips.",
        "original_stem": "cookie_recipe",
        "expected_folder": "recipes",
        "expected_filename_keywords": ["chocolate", "chip", "cookie", "recipe"],
    },
    {
        "content": "Meeting notes from the weekly engineering standup. Action items: fix CI pipeline, deploy v2.3.",
        "original_stem": "standup_notes_2024",
        "expected_folder": "engineering",
        "expected_filename_keywords": ["meeting", "notes", "engineering", "standup"],
    },
    {
        "content": "Patient discharge summary. Diagnosis: Type 2 diabetes. Medication: Metformin 500mg.",
        "original_stem": "discharge_summary",
        "expected_folder": "healthcare",
        "expected_filename_keywords": [
            "discharge",
            "summary",
            "diabetes",
            "healthcare",
        ],
    },
    {
        "content": "Legal contract between Acme Corp and Widget LLC for software licensing.",
        "original_stem": "contract_acme_widget",
        "expected_folder": "legal",
        "expected_filename_keywords": ["contract", "software", "legal", "licensing"],
    },
    {
        "content": "Phase 2 test results for the new authentication module. All 47 tests passing.",
        "original_stem": "phase2_auth_tests",
        "expected_folder": "testing",
        "expected_filename_keywords": ["phase2", "auth", "test", "results"],
    },
    {
        "content": "Annual report 2022. Revenue grew 15% YoY. Net income: $3.4B.",
        "original_stem": "annual_report_2022",
        "expected_folder": "finance",
        "expected_filename_keywords": ["annual", "report", "2022", "revenue"],
    },
    {
        "content": "Travel itinerary for Japan trip. Flights: SFO → NRT. Hotels in Tokyo and Kyoto.",
        "original_stem": "japan_trip_itinerary",
        "expected_folder": "travel",
        "expected_filename_keywords": ["japan", "travel", "itinerary", "tokyo"],
    },
    {
        "content": "Python 3.12 release notes. New features: improved error messages, faster startup.",
        "original_stem": "python312_release",
        "expected_folder": "programming",
        "expected_filename_keywords": ["python", "release", "notes", "312"],
    },
]


def check_keywords(generated: str, keywords: list[str], require_any: int = 1) -> bool:
    """Return True if at least ``require_any`` keywords appear in ``generated``."""
    hits = sum(1 for kw in keywords if kw in generated)
    return hits >= require_any


def run_benchmark(model_name: str | None, verbose: bool, threshold: float) -> int:
    """Run all corpus cases and return exit code."""
    # Lazy import — only needed when running the benchmark
    try:
        from file_organizer.services.text_processor import TextProcessor
    except ImportError:
        print("ERROR: file_organizer package not importable.  Run from repo root.")
        return 1

    processor = TextProcessor()
    try:
        processor.initialize()
    except Exception as exc:
        print(f"ERROR: model not initialized / Ollama not reachable: {exc}")
        print("       Ensure Ollama is running before executing this benchmark.")
        return 2

    total = 0
    passed = 0
    failures: list[str] = []

    for i, case in enumerate(CORPUS, 1):
        content = case["content"]
        original_stem = case["original_stem"]
        expected_folder_kws = [case["expected_folder"]]
        expected_fname_kws = case["expected_filename_keywords"]

        t0 = time.time()
        # Use private methods directly — benchmark tests the full pipeline
        folder = processor._generate_folder_name(content, original_stem=original_stem)
        fname = processor._generate_filename(content, original_stem=original_stem)
        elapsed = time.time() - t0

        folder_ok = check_keywords(folder, expected_folder_kws, require_any=1)
        fname_ok = check_keywords(fname, expected_fname_kws, require_any=1)
        ok = folder_ok and fname_ok
        passed += ok
        total += 1

        status = "✅" if ok else "❌"
        if verbose or not ok:
            print(f"\n[{i:02d}] {status}  {original_stem}  ({elapsed:.1f}s)")
            print(f"     content : {content[:60]}…")
            print(f"     folder  : {folder!r}  (want keyword from {expected_folder_kws})")
            print(f"     filename: {fname!r}  (want keyword from {expected_fname_kws})")
            if not ok:
                failures.append(original_stem)
        else:
            print(f"[{i:02d}] {status}  {original_stem}")

    accuracy = passed / max(total, 1)
    print(f"\n{'=' * 60}")
    print(
        f"Accuracy: {passed}/{total} = {accuracy * 100:.1f}%  (threshold: {threshold * 100:.0f}%)"
    )

    if accuracy >= threshold:
        print("✅ PASS — no regression detected")
        return 0
    else:
        print("❌ FAIL — accuracy below threshold")
        if failures:
            print(f"   Failed cases: {', '.join(failures)}")
        return 1


def main() -> None:
    parser = argparse.ArgumentParser(
        description=textwrap.dedent(__doc__ or ""),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--model", default=None, help="Ollama model name override")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show all cases")
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.70,
        help="Minimum accuracy required (default: 0.70)",
    )
    args = parser.parse_args()
    sys.exit(run_benchmark(args.model, args.verbose, args.threshold))


if __name__ == "__main__":
    main()
