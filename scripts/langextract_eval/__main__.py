"""Run the langextract evaluation.

Off-CI, on-demand. Requires the ``eval`` extra (``pip install -e ".[eval]"``)
and, for real runs, a reachable model backend.

Usage:
    python -m scripts.langextract_eval                       # Ollama, default model
    python -m scripts.langextract_eval --model qwen2.5:7b-instruct-q4_K_M
    python -m scripts.langextract_eval --backend stub        # offline plumbing check
    python -m scripts.langextract_eval --repeats 3 --passes 2
    python -m scripts.langextract_eval --rescore output/langextract_eval/RUN/results.json

Extractors (``--extractors``, comma-separated):
    baseline    project BaseModel.generate_structured (current approach)
    lx-adapter  langextract over the project model via FileOrganizerLanguageModel
    lx-native   langextract's own Ollama provider (JSON mode; Ollama backend only)

Writes ``results.json`` and ``report.md`` to ``--output-dir``
(default ``output/langextract_eval/<UTC timestamp>/``, gitignored).

Exit codes:
    0  Evaluation completed (per-case failures are scored, not fatal)
    2  Model backend could not be initialized
    3  langextract (eval extra) not installed
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import textwrap
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path
from typing import Any

from scripts.langextract_eval.corpus import CORPUS, ENTITY_CLASSES, EvalCase, validate_corpus
from scripts.langextract_eval.scoring import (
    CaseResult,
    ExtractorScore,
    Prediction,
    grounded_only,
    paired_bootstrap_f1,
    score_extractor,
)

BACKENDS = ("stub", "ollama", "openai", "llama_cpp", "mlx", "claude")
EXTRACTORS = ("baseline", "lx-adapter", "lx-native")
BASELINE_NAME = "baseline_generate_structured"


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    from file_organizer.config.defaults import DEFAULT_TEXT_MODEL

    p = argparse.ArgumentParser(
        prog="python -m scripts.langextract_eval",
        description=textwrap.dedent(__doc__ or ""),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--backend", choices=BACKENDS, default="ollama")
    p.add_argument("--model", default=DEFAULT_TEXT_MODEL, help="Model name for the backend")
    p.add_argument("--extractors", default=",".join(EXTRACTORS))
    p.add_argument("--cases", default="", help="Comma-separated case_ids (default: all)")
    p.add_argument("--repeats", type=int, default=1, help="Runs per case (variance)")
    p.add_argument("--temperature", type=float, default=0.0)
    p.add_argument("--max-tokens", type=int, default=2048)
    p.add_argument("--max-char-buffer", type=int, default=1000, help="langextract chunk size")
    p.add_argument("--passes", type=int, default=1, help="langextract extraction_passes")
    p.add_argument(
        "--suppress-parse-errors",
        action="store_true",
        help="Let langextract skip unparseable chunks instead of failing the document",
    )
    p.add_argument("--ollama-url", default=None)
    p.add_argument("--output-dir", type=Path, default=None)
    p.add_argument(
        "--rescore",
        type=Path,
        default=None,
        metavar="RESULTS_JSON",
        help="Re-score a saved results.json with current scoring (no model calls)",
    )
    return p.parse_args(argv)


def _make_project_model(args: argparse.Namespace) -> Any:
    if args.backend == "stub":
        from scripts.langextract_eval.stub import OracleStubModel

        model: Any = OracleStubModel()
    else:
        from file_organizer.models.base import ModelConfig, ModelType
        from file_organizer.models.provider_factory import get_text_model

        config = ModelConfig(
            name=args.model,
            model_type=ModelType.TEXT,
            provider=args.backend,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            api_base_url=args.ollama_url if args.backend == "ollama" else None,
        )
        model = get_text_model(config)
    model.initialize()
    return model


def _build_extractors(args: argparse.Namespace, project_model: Any) -> list[Any]:
    from scripts.langextract_eval import extractors as ex

    wanted = [e.strip() for e in args.extractors.split(",") if e.strip()]
    unknown = sorted(set(wanted) - set(EXTRACTORS))
    if unknown:
        raise SystemExit(f"unknown extractor(s): {', '.join(unknown)}")
    if "lx-native" in wanted and args.backend != "ollama":
        print("note: lx-native needs --backend ollama; skipping it", file=sys.stderr)
        wanted.remove("lx-native")

    lx_opts = {
        "max_char_buffer": args.max_char_buffer,
        "extraction_passes": args.passes,
        "suppress_parse_errors": args.suppress_parse_errors,
    }
    built: list[Any] = []
    for name in wanted:
        if name == "baseline":
            built.append(ex.BaselineExtractor(project_model, args.temperature, args.max_tokens))
        elif name == "lx-adapter":
            lm = ex.make_adapter(project_model, args.temperature, args.max_tokens)
            built.append(ex.LangExtractExtractor("langextract_adapter", lm, **lx_opts))
        else:
            lm = ex.make_native_ollama(args.model, args.temperature, args.ollama_url)
            built.append(ex.LangExtractExtractor("langextract_native_ollama", lm, **lx_opts))
    return built


def _select_cases(spec: str) -> tuple[EvalCase, ...]:
    if not spec:
        return CORPUS
    ids = {s.strip() for s in spec.split(",") if s.strip()}
    missing = ids - {c.case_id for c in CORPUS}
    if missing:
        raise SystemExit(f"unknown case_id(s): {', '.join(sorted(missing))}")
    return tuple(c for c in CORPUS if c.case_id in ids)


def _version(dist: str) -> str | None:
    try:
        return metadata.version(dist)
    except metadata.PackageNotFoundError:
        return None


def _fmt(x: float | None) -> str:
    return "—" if x is None else f"{x:.3f}"


def render_markdown(
    meta: dict[str, Any],
    scores: list[ExtractorScore],
    comparisons: list[tuple[str, float, float, float]] | None = None,
) -> str:
    """Render a human-readable summary of an evaluation run."""
    lines = [
        "# langextract evaluation run",
        "",
        f"- Started: {meta['started_utc']}",
        f"- Backend / model: `{meta['backend']}` / `{meta['model']}`",
        f"- langextract: {meta['versions']['langextract']}",
        f"- Cases: {meta['cases']} × repeats {meta['repeats']}",
        f"- Options: temperature={meta['temperature']}, max_char_buffer="
        f"{meta['max_char_buffer']}, passes={meta['passes']}, "
        f"suppress_parse_errors={meta['suppress_parse_errors']}",
        "",
    ]
    if meta.get("note"):
        lines += [f"> **Note:** {meta['note']}", ""]
    if meta["backend"] == "stub":
        lines += ["> **Stub run** — oracle model; metrics validate plumbing only.", ""]
    lines += [
        "## Summary",
        "",
        "| Extractor | Strict P | Strict R | Strict F1 | Lenient F1 | Verbatim | "
        "Offset acc. | Failed cases | s/case | LLM calls |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for s in scores:
        d = s.to_dict()
        lines.append(
            f"| {s.name} | {_fmt(s.strict.precision)} | {_fmt(s.strict.recall)} | "
            f"{_fmt(s.strict.f1)} | {_fmt(s.lenient.f1)} | {_fmt(s.verbatim_rate)} | "
            f"{_fmt(s.offset_accuracy)} | {len(s.failed_cases)}/{s.cases} | "
            f"{d['seconds_per_case']} | {s.llm_calls} |"
        )
    lines += ["", "## Strict F1 by class", ""]
    header = "| Class | " + " | ".join(s.name for s in scores) + " |"
    lines += [header, "|---|" + "---|" * len(scores)]
    for cls in ENTITY_CLASSES:
        row = [_fmt(s.per_class[cls].f1) if cls in s.per_class else "—" for s in scores]
        lines.append(f"| {cls} | " + " | ".join(row) + " |")
    if comparisons:
        lines += [
            "",
            f"## Strict F1 vs {BASELINE_NAME} (paired bootstrap over documents)",
            "",
            "| Extractor | ΔF1 | 95% CI | Resolved? |",
            "|---|---|---|---|",
        ]
        for name, diff, lo, hi in comparisons:
            resolved = "yes" if lo > 0 or hi < 0 else "no (CI spans 0)"
            lines.append(f"| {name} | {diff:+.3f} | [{lo:+.3f}, {hi:+.3f}] | {resolved} |")
    failures = [(s.name, s.failed_cases) for s in scores if s.failed_cases]
    if failures:
        lines += ["", "## Failed cases", ""]
        lines += [f"- {name}: {', '.join(ids)}" for name, ids in failures]
    lines += [
        "",
        "`+grounded` rows re-score the same run keeping only predictions langextract "
        "aligned to a source span (no extra LLM calls). "
        "Metric definitions: `scripts/langextract_eval/scoring.py`. "
        "Raw predictions and errors: `results.json`.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Entry point; returns a process exit code."""
    args = _parse_args(argv)
    problems = validate_corpus()
    if problems:
        raise SystemExit("corpus invalid:\n  " + "\n  ".join(problems))
    if args.rescore is not None:
        return rescore(args.rescore, args.output_dir)
    if _version("langextract") is None:
        print('langextract is not installed: pip install -e ".[eval]"', file=sys.stderr)
        return 3

    cases = _select_cases(args.cases)
    started = datetime.now(UTC)
    out_dir = args.output_dir or Path("output/langextract_eval") / started.strftime(
        "%Y%m%dT%H%M%SZ"
    )

    try:
        project_model = _make_project_model(args)
        # Untimed warm-up: a cold weight load (minutes on CPU) otherwise lands
        # in the first case's latency, or fails it outright on a load timeout.
        project_model.generate("Reply with OK.", max_tokens=4)
    except Exception as exc:
        print(f"ERROR: could not initialize {args.backend} model {args.model!r}: {exc}")
        return 2

    try:
        extractors = _build_extractors(args, project_model)
        raw: dict[str, list[CaseResult]] = {}
        for extractor in extractors:
            results: list[CaseResult] = []
            for rep in range(args.repeats):
                for case in cases:
                    res = extractor.run(case)
                    results.append(res)
                    status = "ERR" if res.error else f"{len(res.predictions)} preds"
                    print(
                        f"[{extractor.name}] rep {rep + 1} {case.case_id}: "
                        f"{status} in {res.seconds:.1f}s"
                    )
            raw[extractor.name] = results
    finally:
        project_model.safe_cleanup()

    meta: dict[str, Any] = {
        "started_utc": started.isoformat(timespec="seconds"),
        "backend": args.backend,
        "model": "oracle-stub" if args.backend == "stub" else args.model,
        "cases": len(cases),
        "repeats": args.repeats,
        "temperature": args.temperature,
        "max_tokens": args.max_tokens,
        "max_char_buffer": args.max_char_buffer,
        "passes": args.passes,
        "suppress_parse_errors": args.suppress_parse_errors,
        "versions": {
            "langextract": _version("langextract"),
            "local-file-organizer": _version("local-file-organizer"),
            "python": platform.python_version(),
        },
    }
    _score_and_write(meta, cases, raw, out_dir)
    return 0


def _score_and_write(
    meta: dict[str, Any],
    cases: tuple[EvalCase, ...],
    raw: dict[str, list[CaseResult]],
    out_dir: Path,
) -> None:
    variants: dict[str, list[CaseResult]] = {}
    for name, results in raw.items():
        variants[name] = results
        if name.startswith("langextract"):
            variants[f"{name}+grounded"] = grounded_only(results)
    scores = [score_extractor(name, cases, results) for name, results in variants.items()]
    comparisons = [
        (name, *paired_bootstrap_f1(cases, variants[BASELINE_NAME], results))
        for name, results in variants.items()
        if BASELINE_NAME in variants and name != BASELINE_NAME
    ]
    payload = {
        "meta": meta,
        "scores": [s.to_dict() for s in scores],
        "comparisons": [
            {"name": n, "delta_f1": round(d, 4), "ci95": [round(lo, 4), round(hi, 4)]}
            for n, d, lo, hi in comparisons
        ],
        "results": {
            name: [
                {
                    "case_id": r.case_id,
                    "seconds": round(r.seconds, 3),
                    "llm_calls": r.llm_calls,
                    "error": r.error,
                    "predictions": [vars(p) for p in r.predictions],
                }
                for r in results
            ]
            for name, results in raw.items()
        },
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "results.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    report = render_markdown(meta, scores, comparisons)
    (out_dir / "report.md").write_text(report, encoding="utf-8")
    print("\n" + report)
    print(f"Wrote {out_dir / 'results.json'} and {out_dir / 'report.md'}")


def rescore(results_json: Path, out_dir: Path | None) -> int:
    """Re-score a saved run with the current scoring code (no model needed)."""
    payload = json.loads(results_json.read_text(encoding="utf-8"))
    by_id = {c.case_id: c for c in CORPUS}
    raw = {
        name: [
            CaseResult(
                r["case_id"],
                [Prediction(**p) for p in r["predictions"]],
                r["seconds"],
                r["llm_calls"],
                r["error"],
            )
            for r in results
        ]
        for name, results in payload["results"].items()
    }
    seen = {r.case_id for results in raw.values() for r in results}
    cases = tuple(by_id[c] for c in by_id if c in seen)
    _score_and_write(payload["meta"], cases, raw, out_dir or results_json.parent)
    return 0


if __name__ == "__main__":
    sys.exit(main())
