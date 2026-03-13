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


def _is_detector(value: Any) -> bool:
    """Return whether *value* satisfies the detector surface expected by the framework."""
    if isinstance(value, type):
        return False
    if not callable(getattr(value, "find_violations", None)):
        return False

    detector_id = getattr(value, "detector_id", None)
    rule_class = getattr(value, "rule_class", None)
    description = getattr(value, "description", None)
    return (
        isinstance(detector_id, str)
        and bool(detector_id)
        and isinstance(rule_class, str)
        and bool(rule_class)
        and isinstance(description, str)
        and bool(description)
    )


def _coerce_detectors(obj: Any) -> list[ReviewRegressionDetector]:
    if _is_detector(obj):
        return [obj]
    if isinstance(obj, Iterable) and not isinstance(obj, (str, bytes)):
        items = list(obj)
        detectors = [item for item in items if _is_detector(item)]
        if len(detectors) != len(items):
            raise TypeError(
                "Iterable import spec must contain only detector instances with "
                "detector_id, rule_class, description, and find_violations"
            )
        return detectors
    raise TypeError(
        "Import spec must resolve to a detector, detector iterable, or factory "
        "with detector_id, rule_class, description, and find_violations"
    )


def load_detectors(import_specs: Sequence[str]) -> list[ReviewRegressionDetector]:
    """Load detector instances from ``module:attribute`` import specs."""
    detectors: list[ReviewRegressionDetector] = []
    for spec in import_specs:
        if ":" not in spec:
            raise ValueError(f"Invalid detector spec {spec!r}; expected 'module:attribute'")
        module_name, attr_name = spec.split(":", 1)
        if not module_name or not attr_name:
            raise ValueError(f"Invalid detector spec {spec!r}; expected 'module:attribute'")
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            missing_module = exc.name
            if not isinstance(missing_module, str) or (
                missing_module != module_name and not module_name.startswith(f"{missing_module}.")
            ):
                raise
            raise ValueError(
                f"Invalid detector spec {spec!r}; expected 'module:attribute' resolving to "
                "a detector, detector iterable, or factory with detector_id, rule_class, "
                "description, and find_violations"
            ) from exc
        try:
            target = getattr(module, attr_name)
        except AttributeError as exc:
            raise ValueError(
                f"Invalid detector spec {spec!r}; expected 'module:attribute' resolving to "
                "a detector, detector iterable, or factory with detector_id, rule_class, "
                "description, and find_violations"
            ) from exc
        loaded = target() if callable(target) and not _is_detector(target) else target
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
