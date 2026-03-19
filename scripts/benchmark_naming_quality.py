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
    3  Import/setup failure (file_organizer package not importable)
    4  Inference failure during a benchmark run
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
# Ground-truth corpus (33 representative cases across diverse source formats)
#
# Each entry carries a ``source_format`` field indicating what type of file
# the content was extracted from.  The model always receives extracted text —
# PDFs and images go through text extraction upstream — so the corpus covers
# the meaningful diversity dimension: extracted-text character from different
# real-world source formats (plain_text, pdf, pdf_scanned, spreadsheet,
# email, image_ocr, presentation, code, config).
# ---------------------------------------------------------------------------

CORPUS: list[dict] = [
    # --- Finance (plain_text) ---
    {
        "content": "Q3 2023 budget review. Total spend: $1.2M. Under budget by 8%.",
        "original_stem": "q3_2023_budget",
        "source_format": "plain_text",
        "expected_folder": "finance",
        "expected_filename_keywords": ["budget", "2023", "q3"],
    },
    {
        "content": "Annual report 2022. Revenue grew 15% YoY. Net income: $3.4B.",
        "original_stem": "annual_report_2022",
        "source_format": "plain_text",
        "expected_folder": "finance",
        "expected_filename_keywords": ["annual", "report", "2022", "revenue"],
    },
    {
        "content": "Invoice #INV-4821. Client: Acme Corp. Amount due: $8,500. Due date: 2024-02-15.",
        "original_stem": "invoice_4821",
        "source_format": "plain_text",
        "expected_folder": "finance",
        "expected_filename_keywords": ["invoice", "acme", "4821"],
    },
    # --- Machine Learning / Programming (plain_text / code) ---
    {
        "content": "Introduction to machine learning with Python. Covers regression, classification, and clustering.",
        "original_stem": "ml_intro",
        "source_format": "plain_text",
        "expected_folder": "machine_learning",
        "expected_filename_keywords": ["machine", "learning", "python"],
    },
    {
        "content": "Python 3.12 release notes. New features: improved error messages, faster startup.",
        "original_stem": "python312_release",
        "source_format": "plain_text",
        "expected_folder": "programming",
        "expected_filename_keywords": ["python", "release", "notes", "312"],
    },
    {
        "content": "def fibonacci(n: int) -> int:\n    if n <= 1: return n\n    return fibonacci(n-1) + fibonacci(n-2)\n\n# Recursive Fibonacci implementation with memoization example.",
        "original_stem": "fibonacci_recursive",
        "source_format": "code",
        "expected_folder": "programming",
        "expected_filename_keywords": ["fibonacci", "recursive", "python"],
    },
    {
        "content": "REST API design best practices. Use nouns for endpoints, HTTP verbs for actions. Version your API with /v1/ prefix.",
        "original_stem": "api_design_guide",
        "source_format": "plain_text",
        "expected_folder": "programming",
        "expected_filename_keywords": ["api", "design", "rest"],
    },
    # --- Healthcare (plain_text) ---
    {
        "content": "Patient discharge summary. Diagnosis: Type 2 diabetes. Medication: Metformin 500mg.",
        "original_stem": "discharge_summary",
        "source_format": "plain_text",
        "expected_folder": "healthcare",
        "expected_filename_keywords": ["discharge", "summary", "diabetes", "healthcare"],
    },
    {
        "content": "MRI scan report — left knee. Findings: moderate medial meniscal tear. Recommendation: physiotherapy.",
        "original_stem": "mri_left_knee",
        "source_format": "plain_text",
        "expected_folder": "healthcare",
        "expected_filename_keywords": ["mri", "knee", "scan", "report"],
    },
    # --- Legal (plain_text) ---
    {
        "content": "Legal contract between Acme Corp and Widget LLC for software licensing.",
        "original_stem": "contract_acme_widget",
        "source_format": "plain_text",
        "expected_folder": "legal",
        "expected_filename_keywords": ["contract", "software", "legal", "licensing"],
    },
    {
        "content": "Non-disclosure agreement between parties. Confidential information shall not be shared for 5 years.",
        "original_stem": "nda_2024",
        "source_format": "plain_text",
        "expected_folder": "legal",
        "expected_filename_keywords": ["nda", "non", "disclosure", "confidential"],
    },
    # --- Engineering / Testing (plain_text) ---
    {
        "content": "Meeting notes from the weekly engineering standup. Action items: fix CI pipeline, deploy v2.3.",
        "original_stem": "standup_notes_2024",
        "source_format": "plain_text",
        "expected_folder": "engineering",
        "expected_filename_keywords": ["meeting", "notes", "engineering", "standup"],
    },
    {
        "content": "Phase 2 test results for the new authentication module. All 47 tests passing.",
        "original_stem": "phase2_auth_tests",
        "source_format": "plain_text",
        "expected_folder": "testing",
        "expected_filename_keywords": ["phase2", "auth", "test", "results"],
    },
    {
        "content": "System architecture diagram for microservices deployment. Services: auth, payments, notifications, gateway.",
        "original_stem": "microservices_arch",
        "source_format": "plain_text",
        "expected_folder": "engineering",
        "expected_filename_keywords": ["architecture", "microservices", "system"],
    },
    # --- Recipes (plain_text) ---
    {
        "content": "Chocolate chip cookie recipe. Ingredients: butter, sugar, eggs, flour, chocolate chips.",
        "original_stem": "cookie_recipe",
        "source_format": "plain_text",
        "expected_folder": "recipes",
        "expected_filename_keywords": ["chocolate", "chip", "cookie", "recipe"],
    },
    {
        "content": "Classic Italian carbonara. Ingredients: spaghetti, guanciale, eggs, pecorino romano, black pepper.",
        "original_stem": "carbonara_recipe",
        "source_format": "plain_text",
        "expected_folder": "recipes",
        "expected_filename_keywords": ["carbonara", "italian", "pasta", "recipe"],
    },
    # --- Travel (plain_text) ---
    {
        "content": "Travel itinerary for Japan trip. Flights: SFO → NRT. Hotels in Tokyo and Kyoto.",
        "original_stem": "japan_trip_itinerary",
        "source_format": "plain_text",
        "expected_folder": "travel",
        "expected_filename_keywords": ["japan", "travel", "itinerary", "tokyo"],
    },
    {
        "content": "Packing list for 2-week backpacking trip to Southeast Asia. Include: lightweight clothes, rain jacket, travel adapter.",
        "original_stem": "southeast_asia_packing",
        "source_format": "plain_text",
        "expected_folder": "travel",
        "expected_filename_keywords": ["packing", "travel", "asia", "backpacking"],
    },
    # --- Research / Academic (plain_text) ---
    {
        "content": "Abstract: This paper presents a novel approach to transformer attention mechanisms, reducing quadratic complexity to linear via sparse attention patterns.",
        "original_stem": "transformer_attention_paper",
        "source_format": "plain_text",
        "expected_folder": "research",
        "expected_filename_keywords": ["transformer", "attention", "paper", "research"],
    },
    {
        "content": "Literature review on climate change mitigation strategies. Covers carbon capture, renewable energy, and policy interventions.",
        "original_stem": "climate_literature_review",
        "source_format": "plain_text",
        "expected_folder": "research",
        "expected_filename_keywords": ["climate", "research", "review", "mitigation"],
    },
    # --- HR / Personal (plain_text) ---
    {
        "content": "Curriculum vitae — Jane Doe. Software Engineer with 8 years experience. Skills: Python, Kubernetes, distributed systems.",
        "original_stem": "jane_doe_cv",
        "source_format": "plain_text",
        "expected_folder": "hr",
        "expected_filename_keywords": ["cv", "resume", "software", "engineer"],
    },
    {
        "content": "Performance review Q4 2023. Employee: John Smith. Rating: Exceeds Expectations. Key achievements: launched product v3.",
        "original_stem": "perf_review_q4_2023",
        "source_format": "plain_text",
        "expected_folder": "hr",
        "expected_filename_keywords": ["performance", "review", "2023"],
    },
    # --- Configuration / DevOps (config) ---
    {
        "content": "nginx.conf — upstream backend { server 127.0.0.1:8000; } server { listen 80; location / { proxy_pass http://backend; } }",
        "original_stem": "nginx_config",
        "source_format": "config",
        "expected_folder": "configuration",
        "expected_filename_keywords": ["nginx", "config", "server"],
    },
    {
        "content": "Docker Compose file for local development. Services: postgres, redis, api, worker. Volumes: db_data, redis_data.",
        "original_stem": "docker_compose_dev",
        "source_format": "config",
        "expected_folder": "configuration",
        "expected_filename_keywords": ["docker", "compose", "configuration"],
    },
    # --- Presentations (presentation) ---
    {
        "content": "Q4 2023 product roadmap presentation. Key themes: AI integration, mobile-first redesign, enterprise tier launch.",
        "original_stem": "q4_roadmap_deck",
        "source_format": "presentation",
        "expected_folder": "presentations",
        "expected_filename_keywords": ["roadmap", "product", "2023", "presentation"],
    },
    # --- PDF-extracted: Financial statement ---
    {
        "content": (
            "Balance Sheet — FY 2023\n"
            "Assets:      Cash 2,400,000 | Accounts Receivable 1,100,000 | Inventory 850,000\n"
            "Liabilities: Accounts Payable 640,000 | Long-term Debt 3,200,000\n"
            "Equity:      Retained Earnings 4,510,000"
        ),
        "original_stem": "balance_sheet_fy2023",
        "source_format": "pdf",
        "expected_folder": "finance",
        "expected_filename_keywords": ["balance", "sheet", "2023"],
    },
    # --- PDF-scanned: Tax form (OCR of structured form fields) ---
    {
        "content": (
            "FORM W-2  Wage and Tax Statement  2023\n"
            "Employer: Acme Corporation  EIN: XX-XXXXXXX\n"
            "Employee: Jane Doe  SSN: XXX-XX-XXXX\n"
            "Box 1 Wages: 95,000.00  Box 2 Federal Tax Withheld: 18,500.00\n"
            "Box 16 State Wages: 95,000.00  Box 17 State Tax: 7,200.00"
        ),
        "original_stem": "w2_jane_doe_2023",
        "source_format": "pdf_scanned",
        "expected_folder": "tax",
        "expected_filename_keywords": ["w2", "tax", "2023", "wages"],
    },
    # --- Spreadsheet: Expense report (CSV-like extracted rows) ---
    {
        "content": (
            "Date,Description,Category,Amount\n"
            "2024-01-05,Team lunch,Meals,85.40\n"
            "2024-01-12,AWS monthly invoice,Cloud,1240.00\n"
            "2024-01-18,Office supplies,Admin,32.75\n"
            "Total: 1358.15"
        ),
        "original_stem": "jan_2024_expenses",
        "source_format": "spreadsheet",
        "expected_folder": "finance",
        "expected_filename_keywords": ["expense", "2024", "january"],
    },
    # --- Spreadsheet: Sprint task tracker (tabular extracted text) ---
    {
        "content": (
            "Sprint 14 Task Tracker\n"
            "ID     | Task                      | Owner | Status      | Points\n"
            "FO-201 | Auth service refactor      | Alice | Done        |  8\n"
            "FO-202 | Search API v2              | Bob   | In Progress | 13\n"
            "FO-203 | Mobile push notifications  | Carol | Blocked     |  5\n"
            "Velocity: 21 pts / Total: 29 pts"
        ),
        "original_stem": "sprint14_tracker",
        "source_format": "spreadsheet",
        "expected_folder": "engineering",
        "expected_filename_keywords": ["sprint", "tracker", "task"],
    },
    # --- Email: Project kickoff ---
    {
        "content": (
            "From: alice@acme.com\n"
            "To: bob@acme.com\n"
            "Subject: Project Kickoff — Q1 2024 Analytics Platform\n"
            "Date: Mon, 8 Jan 2024 09:15:00 +0000\n\n"
            "Hi Bob,\nConfirmed: kickoff Thursday 10am. Agenda: scope, timeline, resources.\n"
            "Please bring the draft requirements doc.\n\nBest, Alice"
        ),
        "original_stem": "email_kickoff_meeting",
        "source_format": "email",
        "expected_folder": "correspondence",
        "expected_filename_keywords": ["kickoff", "meeting", "project"],
    },
    # --- Email: Newsletter ---
    {
        "content": (
            "From: newsletter@example.com\n"
            "Subject: Weekly AI Digest — Large Language Models Edition\n"
            "This week: GPT-4o multimodal update, Gemini 1.5 Pro context window, "
            "Llama 3 open-source release. Curated links and commentary inside."
        ),
        "original_stem": "newsletter_ai_digest",
        "source_format": "email",
        "expected_folder": "newsletters",
        "expected_filename_keywords": ["newsletter", "ai", "digest"],
    },
    # --- Image OCR: Store receipt (with typical OCR layout artifacts) ---
    {
        "content": (
            "WHOLE F00DS MARKET\n"
            "1765 California St  San Francisco CA\n"
            "Date: 02/14/2024  Time: 14:32\n"
            "Organics Baby Spinach  3.99\n"
            "Almond Milk 1L         4.49\n"
            "Free Range Eggs 12ct   6.99\n"
            "SUBTOTAL              15.47\n"
            "TAX (8.5%)             1.31\n"
            "T0TAL                 16.78\n"
            "VISA ...4821  APPROVED"
        ),
        "original_stem": "grocery_receipt_feb2024",
        "source_format": "image_ocr",
        "expected_folder": "receipts",
        "expected_filename_keywords": ["receipt", "grocery", "2024"],
    },
    # --- Image OCR: Whiteboard photo (architecture review notes) ---
    {
        "content": (
            "[ Whiteboard — Architecture Review 15 Mar 2024 ]\n"
            "→ Move auth to dedicated service\n"
            "→ Redis cache for sessions (TTL 24h)\n"
            "→ API gateway rate-limit: 1000 req/min\n"
            "OPEN QUESTIONS: DB sharding strategy?  GDPR data residency (EU vs US)\n"
            "ACTION: Alice owns spike by EOW"
        ),
        "original_stem": "arch_review_whiteboard_mar2024",
        "source_format": "image_ocr",
        "expected_folder": "engineering",
        "expected_filename_keywords": ["architecture", "review", "whiteboard", "2024"],
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
            fmt = case.get("source_format", "text")
            print(f"\n[{i:02d}] {status}  {original_stem}  ({elapsed:.1f}s)  [{fmt}]")
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
        0 if all models meet the threshold.
        1 if at least one model is below threshold (regression).
        2 if a model cannot be initialized (Ollama not reachable).
        3 if the file_organizer package is not importable (setup failure).
        4 if inference fails during a benchmark run.
    """
    try:
        from file_organizer.services.text_processor import (
            TextProcessor,  # noqa: F401 (import check)
        )
    except ImportError:
        print("ERROR: file_organizer package not importable.  Run from repo root.", file=sys.stderr)
        return 3

    models_to_run: list[str | None] = MODEL_TIERS if model_name == "all" else [model_name]
    results: list[tuple[str, float, bool]] = []

    for tier in models_to_run:
        label = tier if tier is not None else "default"
        processor = None
        try:
            processor = _make_processor(tier)
        except Exception as exc:
            print(f"ERROR: could not initialize model {label!r}: {exc}", file=sys.stderr)
            print(
                "       Ensure Ollama is running before executing this benchmark.", file=sys.stderr
            )
            return 2

        try:
            accuracy, passed_threshold = _run_single(processor, label, verbose, threshold)
            results.append((label, accuracy, passed_threshold))
        except Exception as exc:
            print(f"ERROR: benchmark run failed for model {label!r}: {exc}", file=sys.stderr)
            return 4
        finally:
            if processor is not None and hasattr(processor, "cleanup"):
                try:
                    processor.cleanup()  # type: ignore[attr-defined]
                except Exception as cleanup_exc:
                    print(
                        f"WARNING: cleanup failed for model {label!r}: {cleanup_exc}",
                        file=sys.stderr,
                    )

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
