#!/usr/bin/env python3
"""Benchmark naming quality against the ground-truth corpus.

Off-CI, on-demand script.  Requires a running Ollama instance.

Usage:
    python scripts/benchmark_naming_quality.py
    python scripts/benchmark_naming_quality.py --model qwen2.5:3b-instruct-q4_K_M
    python scripts/benchmark_naming_quality.py --model all
    python scripts/benchmark_naming_quality.py --verbose

Outputs:
    - Per-case pass/fail with diff when wrong
    - Overall accuracy percentage per model
    - Comparison table when --model all is used
    - Regression flag if score drops below --threshold (default: 0.70)

Exit codes:
    0  All models at or above threshold
    1  At least one model below threshold (regression detected)
    2  Model initialization failure (Ollama not reachable)
"""

from __future__ import annotations

import argparse
import sys
import textwrap
import time

# ---------------------------------------------------------------------------
# Model tiers evaluated by --model all
# ---------------------------------------------------------------------------

MODEL_TIERS: list[str] = [
    "qwen2.5:3b-instruct-q4_K_M",
    "qwen2.5:7b-instruct-q4_K_M",
    "qwen2.5:14b-instruct-q4_K_M",
]

# ---------------------------------------------------------------------------
# Ground-truth corpus (25 representative cases across diverse file types)
# ---------------------------------------------------------------------------

CORPUS: list[dict] = [
    # --- Finance ---
    {
        "content": "Q3 2023 budget review. Total spend: $1.2M. Under budget by 8%.",
        "original_stem": "q3_2023_budget",
        "expected_folder": "finance",
        "expected_filename_keywords": ["budget", "2023", "q3"],
    },
    {
        "content": "Annual report 2022. Revenue grew 15% YoY. Net income: $3.4B.",
        "original_stem": "annual_report_2022",
        "expected_folder": "finance",
        "expected_filename_keywords": ["annual", "report", "2022", "revenue"],
    },
    {
        "content": "Invoice #INV-4821. Client: Acme Corp. Amount due: $8,500. Due date: 2024-02-15.",
        "original_stem": "invoice_4821",
        "expected_folder": "finance",
        "expected_filename_keywords": ["invoice", "acme", "4821"],
    },
    # --- Machine Learning / Programming ---
    {
        "content": "Introduction to machine learning with Python. Covers regression, classification, and clustering.",
        "original_stem": "ml_intro",
        "expected_folder": "machine_learning",
        "expected_filename_keywords": ["machine", "learning", "python"],
    },
    {
        "content": "Python 3.12 release notes. New features: improved error messages, faster startup.",
        "original_stem": "python312_release",
        "expected_folder": "programming",
        "expected_filename_keywords": ["python", "release", "notes", "312"],
    },
    {
        "content": "def fibonacci(n: int) -> int:\n    if n <= 1: return n\n    return fibonacci(n-1) + fibonacci(n-2)\n\n# Recursive Fibonacci implementation with memoization example.",
        "original_stem": "fibonacci_recursive",
        "expected_folder": "programming",
        "expected_filename_keywords": ["fibonacci", "recursive", "python"],
    },
    {
        "content": "REST API design best practices. Use nouns for endpoints, HTTP verbs for actions. Version your API with /v1/ prefix.",
        "original_stem": "api_design_guide",
        "expected_folder": "programming",
        "expected_filename_keywords": ["api", "design", "rest"],
    },
    # --- Healthcare ---
    {
        "content": "Patient discharge summary. Diagnosis: Type 2 diabetes. Medication: Metformin 500mg.",
        "original_stem": "discharge_summary",
        "expected_folder": "healthcare",
        "expected_filename_keywords": ["discharge", "summary", "diabetes", "healthcare"],
    },
    {
        "content": "MRI scan report — left knee. Findings: moderate medial meniscal tear. Recommendation: physiotherapy.",
        "original_stem": "mri_left_knee",
        "expected_folder": "healthcare",
        "expected_filename_keywords": ["mri", "knee", "scan", "report"],
    },
    # --- Legal ---
    {
        "content": "Legal contract between Acme Corp and Widget LLC for software licensing.",
        "original_stem": "contract_acme_widget",
        "expected_folder": "legal",
        "expected_filename_keywords": ["contract", "software", "legal", "licensing"],
    },
    {
        "content": "Non-disclosure agreement between parties. Confidential information shall not be shared for 5 years.",
        "original_stem": "nda_2024",
        "expected_folder": "legal",
        "expected_filename_keywords": ["nda", "non", "disclosure", "confidential"],
    },
    # --- Engineering / Testing ---
    {
        "content": "Meeting notes from the weekly engineering standup. Action items: fix CI pipeline, deploy v2.3.",
        "original_stem": "standup_notes_2024",
        "expected_folder": "engineering",
        "expected_filename_keywords": ["meeting", "notes", "engineering", "standup"],
    },
    {
        "content": "Phase 2 test results for the new authentication module. All 47 tests passing.",
        "original_stem": "phase2_auth_tests",
        "expected_folder": "testing",
        "expected_filename_keywords": ["phase2", "auth", "test", "results"],
    },
    {
        "content": "System architecture diagram for microservices deployment. Services: auth, payments, notifications, gateway.",
        "original_stem": "microservices_arch",
        "expected_folder": "engineering",
        "expected_filename_keywords": ["architecture", "microservices", "system"],
    },
    # --- Recipes ---
    {
        "content": "Chocolate chip cookie recipe. Ingredients: butter, sugar, eggs, flour, chocolate chips.",
        "original_stem": "cookie_recipe",
        "expected_folder": "recipes",
        "expected_filename_keywords": ["chocolate", "chip", "cookie", "recipe"],
    },
    {
        "content": "Classic Italian carbonara. Ingredients: spaghetti, guanciale, eggs, pecorino romano, black pepper.",
        "original_stem": "carbonara_recipe",
        "expected_folder": "recipes",
        "expected_filename_keywords": ["carbonara", "italian", "pasta", "recipe"],
    },
    # --- Travel ---
    {
        "content": "Travel itinerary for Japan trip. Flights: SFO → NRT. Hotels in Tokyo and Kyoto.",
        "original_stem": "japan_trip_itinerary",
        "expected_folder": "travel",
        "expected_filename_keywords": ["japan", "travel", "itinerary", "tokyo"],
    },
    {
        "content": "Packing list for 2-week backpacking trip to Southeast Asia. Include: lightweight clothes, rain jacket, travel adapter.",
        "original_stem": "southeast_asia_packing",
        "expected_folder": "travel",
        "expected_filename_keywords": ["packing", "travel", "asia", "backpacking"],
    },
    # --- Research / Academic ---
    {
        "content": "Abstract: This paper presents a novel approach to transformer attention mechanisms, reducing quadratic complexity to linear via sparse attention patterns.",
        "original_stem": "transformer_attention_paper",
        "expected_folder": "research",
        "expected_filename_keywords": ["transformer", "attention", "paper", "research"],
    },
    {
        "content": "Literature review on climate change mitigation strategies. Covers carbon capture, renewable energy, and policy interventions.",
        "original_stem": "climate_literature_review",
        "expected_folder": "research",
        "expected_filename_keywords": ["climate", "research", "review", "mitigation"],
    },
    # --- HR / Personal ---
    {
        "content": "Curriculum vitae — Jane Doe. Software Engineer with 8 years experience. Skills: Python, Kubernetes, distributed systems.",
        "original_stem": "jane_doe_cv",
        "expected_folder": "hr",
        "expected_filename_keywords": ["cv", "resume", "software", "engineer"],
    },
    {
        "content": "Performance review Q4 2023. Employee: John Smith. Rating: Exceeds Expectations. Key achievements: launched product v3.",
        "original_stem": "perf_review_q4_2023",
        "expected_folder": "hr",
        "expected_filename_keywords": ["performance", "review", "2023"],
    },
    # --- Configuration / DevOps ---
    {
        "content": "nginx.conf — upstream backend { server 127.0.0.1:8000; } server { listen 80; location / { proxy_pass http://backend; } }",
        "original_stem": "nginx_config",
        "expected_folder": "configuration",
        "expected_filename_keywords": ["nginx", "config", "server"],
    },
    {
        "content": "Docker Compose file for local development. Services: postgres, redis, api, worker. Volumes: db_data, redis_data.",
        "original_stem": "docker_compose_dev",
        "expected_folder": "configuration",
        "expected_filename_keywords": ["docker", "compose", "configuration"],
    },
    # --- Presentations ---
    {
        "content": "Q4 2023 product roadmap presentation. Key themes: AI integration, mobile-first redesign, enterprise tier launch.",
        "original_stem": "q4_roadmap_deck",
        "expected_folder": "presentations",
        "expected_filename_keywords": ["roadmap", "product", "2023", "presentation"],
    },
]


def check_keywords(generated: str, keywords: list[str], require_any: int = 1) -> bool:
    """Return True if at least ``require_any`` keywords appear in ``generated``."""
    hits = sum(1 for kw in keywords if kw in generated)
    return hits >= require_any


def _make_processor(model_name: str | None) -> object:
    """Build and return an initialized TextProcessor for ``model_name``.

    Raises:
        ImportError: If the file_organizer package is not importable.
        Exception: If the model cannot be initialized (Ollama not reachable).
    """
    from file_organizer.models.base import ModelConfig, ModelType
    from file_organizer.services.text_processor import TextProcessor

    if model_name is not None:
        config = ModelConfig(name=model_name, model_type=ModelType.TEXT)
        processor = TextProcessor(config=config)
    else:
        processor = TextProcessor()

    processor.initialize()
    return processor


def _run_single(
    processor: object, model_label: str, verbose: bool, threshold: float
) -> tuple[float, bool]:
    """Run the full corpus against an already-initialized processor.

    Returns:
        (accuracy, passed_threshold) tuple.
    """
    total = 0
    passed = 0
    failures: list[str] = []

    print(f"\n{'=' * 60}")
    print(f"Model: {model_label}")
    print("=" * 60)

    for i, case in enumerate(CORPUS, 1):
        content = case["content"]
        original_stem = case["original_stem"]
        expected_folder_kws = [case["expected_folder"]]
        expected_fname_kws = case["expected_filename_keywords"]

        t0 = time.time()
        # Use private methods directly — benchmark tests the full pipeline
        folder = processor._generate_folder_name(content, original_stem=original_stem)  # type: ignore[attr-defined]
        fname = processor._generate_filename(content, original_stem=original_stem)  # type: ignore[attr-defined]
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
    print(
        f"\nAccuracy: {passed}/{total} = {accuracy * 100:.1f}%  (threshold: {threshold * 100:.0f}%)"
    )

    if accuracy >= threshold:
        print("✅ PASS — no regression detected")
    else:
        print("❌ FAIL — accuracy below threshold")
        if failures:
            print(f"   Failed cases: {', '.join(failures)}")

    return accuracy, accuracy >= threshold


def run_benchmark(model_name: str | None, verbose: bool, threshold: float) -> int:
    """Run the benchmark for one model or all tiers and return exit code.

    When ``model_name`` is ``"all"``, iterates over :data:`MODEL_TIERS` and
    prints a comparison table at the end.

    Returns:
        0 if all models meet the threshold, 1 if any fail, 2 on init error.
    """
    try:
        from file_organizer.services.text_processor import (
            TextProcessor,  # noqa: F401 (import check)
        )
    except ImportError:
        print("ERROR: file_organizer package not importable.  Run from repo root.")
        return 1

    models_to_run: list[str | None] = MODEL_TIERS if model_name == "all" else [model_name]
    results: list[tuple[str, float, bool]] = []

    for tier in models_to_run:
        label = tier if tier is not None else "default"
        try:
            processor = _make_processor(tier)
        except Exception as exc:
            print(f"ERROR: could not initialize model {label!r}: {exc}")
            print("       Ensure Ollama is running before executing this benchmark.")
            return 2

        accuracy, passed_threshold = _run_single(processor, label, verbose, threshold)
        results.append((label, accuracy, passed_threshold))

        # Clean up model resources between tiers
        if hasattr(processor, "cleanup"):
            try:
                processor.cleanup()  # type: ignore[attr-defined]
            except Exception:
                pass

    # Comparison table for --model all
    if len(results) > 1:
        print(f"\n{'=' * 60}")
        print("Per-model summary")
        print(f"{'=' * 60}")
        print(f"{'Model':<45} {'Accuracy':>10} {'Pass?':>6}")
        print("-" * 60)
        for label, accuracy, ok in results:
            mark = "✅" if ok else "❌"
            print(f"{label:<45} {accuracy * 100:>9.1f}% {mark:>6}")

    any_failed = any(not ok for _, _, ok in results)
    return 1 if any_failed else 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description=textwrap.dedent(__doc__ or ""),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--model",
        default=None,
        help=(
            "Ollama model name override, or 'all' to run all tiers "
            f"({', '.join(MODEL_TIERS)}) and print a comparison table"
        ),
    )
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
