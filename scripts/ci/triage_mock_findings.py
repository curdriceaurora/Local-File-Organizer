#!/usr/bin/env python3
"""Merge mock-decay detector outputs into the canonical triage worklist (#1685).

Joins the dynamic patch-liveness report (#1681) with the static
unused-patch-argument report (#1682) at (file, test) granularity and
classifies every finding by repair action:

- ``add-assertion``     — statically unused param, but the mock was LIVE at
                          runtime: the code under test reaches the patch and
                          the test simply never asserts the contract.
- ``delete-or-retarget``— unused param AND dead mock: a pure ghost patch;
                          remove it, or retarget if the sibling tests show
                          the target moved.
- ``retarget-or-overreach`` — param referenced (usually configured) but the
                          mock never accessed at runtime: the #1671 drift
                          signature, or a patch applied to a code path the
                          test never reaches. Needs per-site code reading.
- ``narrow-fixture``    — the same target is dead across >= FIXTURE_SPREAD
                          tests in one file: fixture/autouse over-scoping;
                          scope the fixture down or allowlist as an
                          intentional suppressor.

Untracked (non-mock) patches are carried through unclassified as
``untracked-review`` for the enforcement phase.

Usage: python scripts/ci/triage_mock_findings.py <dead.jsonl> <unused.jsonl> \
           <untracked.jsonl> <out.jsonl>
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

FIXTURE_SPREAD = 5

#: Conftest autouse fixtures that suppress a setup check for *every* test in
#: the suite. They are deliberate, reviewed, and permanent — and because they
#: are autouse they are attributed to all ~22.5k tests, so they arrive as 99.6%
#: of the raw dead findings (51,125 of 51,308 on 2026-08-07). Carrying them
#: into the worklist buries the ~180 rows that describe real decay under a
#: 20,000-row wall, which is why the epic's inputs were filtered by hand.
#:
#: Encoding the filter here is what makes regeneration reproducible: running
#: the documented recipe against a raw report used to yield a 21,908-row
#: worklist instead of the curated ~1,600-row artifact. ``build_worklist``
#: reports what it drops (see ``suppressed``) so the exclusion is never silent.
AUTOUSE_SUPPRESSORS = frozenset(
    {
        "file_organizer.cli.organize._check_setup_completed",
        "FileOrganizerApp._check_setup_needed",
    }
)


def _test_name(nodeid: str) -> str:
    return nodeid.split("::")[-1].split("[")[0]


def load_jsonl(path: Path) -> list[dict]:
    """Read one detector report."""
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def build_worklist(
    dead: list[dict],
    unused: list[dict],
    untracked: list[dict],
    prior: list[dict] | None = None,
) -> list[dict]:
    """Join detector outputs and classify each (file, test) finding.

    ``prior`` (a previous worklist) carries ``allowlisted`` statuses forward
    across regenerations — intentional suppressors keep appearing dead in
    fresh detector runs. ``fixed`` rows are NOT carried: a repaired test
    stops being flagged, so if its key reappears, that is a regression and
    the row reopens.
    """
    # An ``undecidable`` finding is not decay: the plugin could not observe
    # access because the test assigned attributes onto the mock. Route it to
    # the untracked bucket no matter which input file it arrived in — the
    # caller splits the plugin report by hand, and one mis-split would put
    # load-bearing patches into an enforced backlog.
    misrouted = [d for d in dead if d.get("status") == "undecidable"]
    if misrouted:
        dead = [d for d in dead if d.get("status") != "undecidable"]
        untracked = [*untracked, *misrouted]

    dead = [d for d in dead if d["target"] not in AUTOUSE_SUPPRESSORS]

    # Spread is counted over distinct tests, not raw findings — otherwise
    # FIXTURE_SPREAD parametrizations of one test would fake fixture noise.
    distinct_sites = {(d["file"], d["target"], _test_name(d["nodeid"])) for d in dead}
    fixture_sites = {
        site
        for site, n in Counter((f, t) for f, t, _ in distinct_sites).items()
        if n >= FIXTURE_SPREAD
    }
    allowlisted_keys = {
        (p["file"], p["test"], p["action"]) for p in prior or [] if p.get("status") == "allowlisted"
    }

    dead_by_key: dict[tuple[str, str], list[dict]] = {}
    for d in dead:
        dead_by_key.setdefault((d["file"], _test_name(d["nodeid"])), []).append(d)
    unused_by_key: dict[tuple[str, str], list[dict]] = {}
    for u in unused:
        unused_by_key.setdefault((u["file"], u["test"]), []).append(u)

    rows = []
    for key in sorted(set(dead_by_key) | set(unused_by_key)):
        file, test = key
        dead_rows = dead_by_key.get(key, [])
        unused_rows = unused_by_key.get(key, [])
        targets = sorted({d["target"] for d in dead_rows})
        params = sorted({u["param"] for u in unused_rows})

        if any((file, t) in fixture_sites for t in targets):
            action = "narrow-fixture"
        elif dead_rows and unused_rows:
            action = "delete-or-retarget"
        elif unused_rows:
            action = "add-assertion"
        else:
            action = "retarget-or-overreach"

        rows.append(
            {
                "file": file,
                "test": test,
                "line": min([d["line"] for d in dead_rows] + [u["line"] for u in unused_rows]),
                "action": action,
                "sources": sorted(
                    (["liveness"] if dead_rows else []) + (["static"] if unused_rows else [])
                ),
                "dead_targets": targets,
                "unused_params": params,
                "status": ("allowlisted" if (file, test, action) in allowlisted_keys else "open"),
            }
        )

    seen_untracked: set[tuple[str, str, str]] = set()
    for u in untracked:
        identity = (u["file"], _test_name(u["nodeid"]), u["target"])
        if identity in seen_untracked:
            continue
        seen_untracked.add(identity)
        rows.append(
            {
                "file": u["file"],
                "test": _test_name(u["nodeid"]),
                "line": u["line"],
                "action": "untracked-review",
                "sources": ["liveness"],
                "dead_targets": [u["target"]],
                "unused_params": [],
                # Allowlisted on sight, not deferred. What survives here is
                # explicit-new patches whose replacement carries no
                # observable surface at all: constants (``patch(target,
                # True)``, ``patch(target, tmp_path)``), classes, exception
                # types, modules and instances. A bool being read leaves no
                # trace, and ``except``/``isinstance`` need the real object,
                # so no amount of triage resolves them; deferring them just
                # regrows the backlog on every regeneration.
                #
                # Function replacements used to land here too. Issue #1719
                # made them observable in the plugin, which moved them out of
                # this bucket entirely — see ``_wrap_callable``.
                "status": "allowlisted",
            }
        )
    return rows


def main() -> int:
    """CLI entry point."""
    if len(sys.argv) not in (5, 6):
        print(__doc__, file=sys.stderr)
        return 2
    dead, unused, untracked, out = (Path(a) for a in sys.argv[1:5])
    prior = load_jsonl(Path(sys.argv[5])) if len(sys.argv) == 6 else None
    dead_rows = load_jsonl(dead)
    rows = build_worklist(dead_rows, load_jsonl(unused), load_jsonl(untracked), prior=prior)

    # Never let the autouse exclusion pass unremarked: a run that silently
    # drops 51k findings looks identical to one where the detector broke.
    suppressed = sum(1 for d in dead_rows if d["target"] in AUTOUSE_SUPPRESSORS)
    if suppressed:
        print(
            f"note: excluded {suppressed} dead findings from "
            f"{len(AUTOUSE_SUPPRESSORS)} autouse suppressors",
            file=sys.stderr,
        )
    with out.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
    summary = Counter(r["action"] for r in rows)
    for action, n in summary.most_common():
        print(f"{n:5d}  {action}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
