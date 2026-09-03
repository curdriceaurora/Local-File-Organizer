#!/usr/bin/env python3
"""Filter a combined coverage run down to a per-marker view (issue #1767).

CI used to run three separate pytest invocations to feed diff-cover, the
unit floor gate, and the integration floor gate — each re-running most of
the same test functions under a different `-m` marker filter. This script
lets CI run pytest *once*, with `--cov-branch --cov-context=test` recording
which test (by nodeid) hit which line/branch, and then reconstructs the
per-marker view each gate needs from that single `.coverage` database.

It writes the same `coverage json` shape check_module_coverage_floor.py and
check-integration-floors.py already read (`data["files"][path]["summary"]`
with num_statements/num_branches/covered_lines/covered_branches) — a
drop-in replacement for what a dedicated `pytest -m <marker> --cov-report=
json:...` run used to produce. Those two scripts, and the floor tables in
pyproject.toml, are unchanged.

How it works:
  1. Collect (never execute) the tests matching `--markers`, in-process via
     pytest's API, to get the exact nodeid set for that marker expression.
     This has to be nodeid-exact rather than a directory/filename regex:
     some files apply `unit`/`integration` per test function rather than
     per module, so a handful of files contribute tests to both views.
  2. Build ONE combined regex alternating every (escaped) nodeid and pass
     it as a single-element list to CoverageData.set_query_contexts().
     Passing one pattern per nodeid instead blows past SQLite's default
     "expression tree too large" limit (~1000) once there are more than a
     few hundred nodeids -- set_query_contexts() ORs its patterns together
     as separate SQL clauses, but a single regex can alternate as many
     branches as re allows, so folding all nodeids into one pattern stays
     under that limit no matter how large the suite gets.
  3. Generate a `coverage json` report against that filtered view.

Usage:
    python scripts/coverage/split_coverage_by_context.py \
        --data-file .coverage --markers unit --out .coverage-unit.json

    python scripts/coverage/split_coverage_by_context.py \
        --data-file .coverage --markers "integration or conformance" \
        --out .coverage-integration.json --min-combined 76.5
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import re
import sys
from pathlib import Path

import coverage
import pytest

# Context strings recorded with --cov-context=test look like
# "<nodeid>|run", "<nodeid>|setup", or "<nodeid>|teardown" -- match the
# nodeid followed by any of those phase suffixes.
_CONTEXT_PHASE_SEP = "|"


class _NodeIdCollector:
    """pytest plugin that records collected nodeids without running them."""

    def __init__(self) -> None:
        self.nodeids: list[str] = []

    # trylast=True: the builtin "mark" plugin's own pytest_collection_modifyitems
    # implementation is what actually deselects items that don't match `-m`.
    # Without trylast, plugin registration order can run this hook first,
    # capturing every collected item before -m has filtered anything out.
    @pytest.hookimpl(trylast=True)
    def pytest_collection_modifyitems(self, items: list[pytest.Item]) -> None:
        """Record the final (post -m deselection) list of collected nodeids."""
        self.nodeids = [item.nodeid for item in items]


def collect_nodeids(markers: str, tests_dir: str) -> list[str]:
    """Return the nodeids pytest would select for a marker expression.

    Collection-only: no test bodies run, so this is seconds even for a
    suite with tens of thousands of tests.
    """
    collector = _NodeIdCollector()
    # Collection prints one line per collected nodeid by default; we already
    # get the exact list from the plugin hook, so keep CI logs quiet.
    with contextlib.redirect_stdout(io.StringIO()):
        exit_code = pytest.main(
            [
                tests_dir,
                "--collect-only",
                "-q",
                "--strict-markers",
                "--override-ini=addopts=",
                "-m",
                markers,
                "-p",
                "no:cacheprovider",
            ],
            plugins=[collector],
        )
    # ExitCode.OK (0) or ExitCode.NO_TESTS_COLLECTED (5) are both fine here --
    # a marker expression matching nothing is a caller error we report below,
    # not a pytest failure.
    if exit_code not in (0, 5):
        print(
            f"ERROR: pytest --collect-only -m {markers!r} exited {exit_code}",
            file=sys.stderr,
        )
        sys.exit(1)
    return collector.nodeids


def build_context_pattern(nodeids: list[str]) -> str:
    """One regex alternating every nodeid, anchored to the phase separator."""
    escaped = "|".join(re.escape(n) for n in nodeids)
    return rf"^(?:{escaped})\{_CONTEXT_PHASE_SEP}"


def compute_combined_percent(totals: dict) -> float | None:
    """Combined line+branch coverage percent, matching check-*-floors.py."""
    total = totals.get("num_statements", 0) + totals.get("num_branches", 0)
    if total == 0:
        return None
    hits = totals.get("covered_lines", 0) + totals.get("covered_branches", 0)
    return hits / total * 100


def main(argv: list[str] | None = None) -> None:
    """Filter --data-file down to --markers' view and write it to --out."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-file", default=".coverage")
    parser.add_argument(
        "--markers", required=True, help='pytest -m expression, e.g. "integration or conformance"'
    )
    parser.add_argument("--out", required=True, dest="out_path")
    parser.add_argument("--tests-dir", default="tests")
    parser.add_argument("--pyproject", default="pyproject.toml")
    parser.add_argument(
        "--min-combined",
        type=float,
        default=None,
        help="Fail if the filtered view's combined line+branch coverage is below this percent",
    )
    args = parser.parse_args(argv)

    if not Path(args.data_file).exists():
        print(f"ERROR: coverage data file not found: {args.data_file}", file=sys.stderr)
        sys.exit(1)

    nodeids = collect_nodeids(args.markers, args.tests_dir)
    if not nodeids:
        print(
            f"ERROR: no tests collected for marker expression {args.markers!r} -- "
            "refusing to produce a (misleadingly empty) coverage report",
            file=sys.stderr,
        )
        sys.exit(1)

    pattern = build_context_pattern(nodeids)

    # contexts= must be passed to json_report() itself, not applied by
    # mutating cov.get_data() beforehand -- json_report() rebuilds its own
    # filtered view from the contexts it's given and ignores query-context
    # state set on the CoverageData object ahead of time.
    cov = coverage.Coverage(data_file=args.data_file, config_file=args.pyproject)
    cov.load()
    cov.json_report(outfile=args.out_path, contexts=[pattern])

    # cov.json_report()'s return value is the overall *line* percent, not the
    # summary dict compute_combined_percent() expects -- read it back from
    # the JSON just written instead.
    with open(args.out_path) as f:
        report = json.load(f)
    combined = compute_combined_percent(report["totals"])

    print(
        f"Wrote {args.out_path}: {len(nodeids)} tests matched {args.markers!r}"
        + (f", combined coverage {combined:.2f}%" if combined is not None else "")
    )

    if args.min_combined is not None:
        if combined is None:
            print(
                "ERROR: no measured statements/branches to compute combined coverage",
                file=sys.stderr,
            )
            sys.exit(1)
        if combined < args.min_combined:
            print(
                f"FAILED: combined coverage {combined:.2f}% < required {args.min_combined}%",
                file=sys.stderr,
            )
            sys.exit(1)


if __name__ == "__main__":
    main()
