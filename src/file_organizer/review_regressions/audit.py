"""CLI entrypoint for review-regression audits."""

from __future__ import annotations

import argparse
import importlib
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from file_organizer.review_regressions.framework import (
    ReviewRegressionDetector,
    render_report_json,
    run_audit,
)


def _coerce_detectors(obj: Any) -> list[ReviewRegressionDetector]:
    if hasattr(obj, "find_violations"):
        return [obj]
    if isinstance(obj, Iterable) and not isinstance(obj, (str, bytes)):
        items = list(obj)
        detectors = [item for item in items if hasattr(item, "find_violations")]
        if len(detectors) != len(items):
            raise TypeError("Iterable import spec must contain only detector instances")
        return detectors
    raise TypeError("Import spec must resolve to a detector, detector iterable, or factory")


def load_detectors(import_specs: Sequence[str]) -> list[ReviewRegressionDetector]:
    """Load detector instances from ``module:attribute`` import specs."""
    detectors: list[ReviewRegressionDetector] = []
    for spec in import_specs:
        if ":" not in spec:
            raise ValueError(f"Invalid detector spec {spec!r}; expected 'module:attribute'")
        module_name, attr_name = spec.split(":", 1)
        module = importlib.import_module(module_name)
        target = getattr(module, attr_name)
        loaded = target() if callable(target) else target
        detectors.extend(_coerce_detectors(loaded))
    return detectors


def build_parser() -> argparse.ArgumentParser:
    """Build the audit entrypoint argument parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Directory to scan")
    parser.add_argument(
        "--detector",
        dest="detectors",
        action="append",
        default=[],
        help="Import spec for detector or detector factory: module:attribute",
    )
    parser.add_argument(
        "--fail-on-findings",
        action="store_true",
        help="Exit non-zero when findings are present",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Emit compact JSON instead of indented JSON",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the review-regression audit entrypoint."""
    parser = build_parser()
    args = parser.parse_args(argv)

    detectors = load_detectors(args.detectors)
    report = run_audit(Path(args.root), detectors)
    sys.stdout.write(render_report_json(report, pretty=not args.compact))

    if args.fail_on_findings and report.findings:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
