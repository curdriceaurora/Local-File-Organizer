# Canonical mock-decay worklist (#1685, epic #1678)

`worklist.jsonl` is THE living tracker for the epic's repair waves. It
supersedes and replaces the raw detector snapshots (`reports/patch_liveness/`
and `reports/mock_quality/`, deleted in the PR that added this file; git
history preserves them). Regenerate from fresh detector runs with
`scripts/ci/triage_mock_findings.py`.

## Classification (regenerated 2026-08-07, after #1719)

| Action | Tests | Meaning |
| :--- | ---: | :--- |
| `retarget-or-overreach` | 26 allowlisted | Param referenced/configured but mock never accessed — drift (#1671) or over-patching |
| `untracked-review` | 953 allowlisted | Replacements with no observable surface — see below |

**979 rows, all allowlisted, 0 open.** Regeneration is idempotent: running
the recipe below against a fresh detector run reproduces this file exactly.

The repair waves are finished, so `fixed` rows no longer appear — a repaired
test stops being flagged and its row simply does not come back. The rows that
remain are the ones that will always be reported: deliberate suppressors and
replacements nothing can observe. **This file is the allowlist of record.**

### What is left, and why it stays

`untracked-review` rows are allowlisted by the generator rather than
deferred. What survives here is replacements with no observable surface at
all: constants (`patch(target, True)`, `patch(target, tmp_path)`), classes,
exception types, modules and instances. A bool being read leaves no trace,
and `except`/`isinstance` need the real object.

Function replacements used to sit here too — 200 of them. #1719 made them
observable by wrapping them in a recording proxy (`_wrap_callable` in the
plugin), and **every single one turned out to be live**. That is the useful
result: the fixtures installing fake `initialize`/`__init__` functions are
load bearing, not decayed, and now that is measured rather than assumed.

The 26 `retarget-or-overreach` rows are intentional isolation on error
paths: a test exercises a failure branch, so the patched collaborator is
never constructed. Each already asserts the real contract on a child mock
(`service.execute.assert_not_called()`), and the parent reads dead precisely
because the guard worked.

## Row lifecycle

Repair-wave PRs flip rows from `status: open` to `status: fixed` (or
`status: allowlisted` with a `# noqa: unused-patch-argument` marker —
the syntax the rail's suppression parser actually reads — or the
enforcement-phase `allow_unaccessed_patches` pytest marker). The file
only shrinks in open-row count.

**This file is NOT deleted at the enforcement flip.** That was the original
plan, written when the expectation was that every row would end up `fixed`.
It did not survive contact: every remaining row is `allowlisted` —
intentional suppressors and unobservable replacements — and those must be
carried into every future regeneration (see below), or the backlog regrows.
The worklist is the allowlist of record and ships to `main`.

## Regeneration semantics

Full recipe, from a clean checkout:

```bash
FO_PATCH_LIVENESS_REPORT=/tmp/live.jsonl python -m pytest tests -q --no-cov \
    -n auto --ignore=tests/playwright --ignore=tests/e2e
```

Under xdist each worker writes `/tmp/live.jsonl.<worker>`. Concatenate them,
split by `status` into a dead file (`status == "dead"`) and an untracked file
(`status in {"untracked", "undecidable"}`), then:

```bash
python scripts/ci/triage_mock_findings.py \
    /tmp/dead.jsonl /tmp/unused.jsonl /tmp/untracked.jsonl \
    reports/triage/worklist.jsonl.new reports/triage/worklist.jsonl
```

`/tmp/unused.jsonl` is the static `unused-patch-argument` report, currently
empty — that rail finds nothing tree-wide.

Three rules make this reproducible:

- **Pass the prior worklist as the fifth argument.** `allowlisted` rows must
  be carried forward — intentional suppressors keep appearing dead — and
  without it the whole allowlist is lost.
- `fixed` rows vanish naturally: a repaired test stops being flagged, so its
  row does not reappear. A `fixed` row whose key DOES reappear is a
  regression and correctly reopens.
- **The generator excludes two conftest autouse suppressors**
  (`AUTOUSE_SUPPRESSORS` in the script). Being autouse, they are attributed
  to all ~22.5k tests and arrive as 99.6% of raw dead findings — 51,139 of
  51,173 on 2026-08-07. Before that exclusion was encoded, the documented
  recipe produced a 21,908-row worklist instead of this ~1,000-row artifact.
  The script prints how many rows it dropped, so the filter is never silent.

## Repair bar (from #1683)

Every repair is hand-mutation-checked: break the guarded contract in
source, confirm the repaired test fails, restore, confirm green.
