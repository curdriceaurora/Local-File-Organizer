# Canonical mock-decay worklist (#1685, epic #1678)

`worklist.jsonl` is THE living tracker for the epic's repair waves. It
supersedes and replaces the raw detector snapshots (`reports/patch_liveness/`
and `reports/mock_quality/`, deleted in the PR that added this file; git
history preserves them). Regenerate from fresh detector runs with
`scripts/ci/triage_mock_findings.py`.

## Classification (final state, 2026-08-03)

| Action | Tests | Files | Meaning |
| :--- | ---: | ---: | :--- |
| `add-assertion` | 166 fixed | 24 | Param statically unused but mock LIVE at runtime — reached, never asserted |
| `retarget-or-overreach` | 92 fixed / 60 allowlisted | 85 | Param referenced/configured but mock never accessed — drift (#1671) or over-patching |
| `narrow-fixture` | 129 fixed / 6 allowlisted | 13 | Same target dead across ≥5 distinct tests in one file — fixture/autouse over-scoping |
| `delete-or-retarget` | 30 fixed | 10 | Unused AND dead — pure ghost patch |
| `untracked-review` | 1,153 allowlisted | 87 | Non-mock replacements (deduped) — `status: allowlisted` on sight, see below |

**417 fixed, 1,219 allowlisted, 0 open.** The counts above are the drained
state; the 2026-07-25 baseline was 132/162/135/20 open.

`untracked-review` rows are allowlisted by the generator rather than
deferred. They are explicit-new patches — `patch(target, True)`,
`patch(target, tmp_path)`, `patch(target, real_function)` — whose
replacement is not a Mock, so `classify_mock` returns `untracked` and
liveness is undecidable *by construction*, not decayed. No amount of triage
resolves them; a bool being read leaves no trace. Deferring them regrew the
same 1,153-row backlog on every regeneration.

## Row lifecycle

Repair-wave PRs flip rows from `status: open` to `status: fixed` (or
`status: allowlisted` with a `# noqa: unused-patch-argument` marker —
the syntax the rail's suppression parser actually reads — or the
enforcement-phase `allow_unaccessed_patches` pytest marker). The file
only shrinks in open-row count.

**This file is NOT deleted at the enforcement flip.** That was the original
plan, written when the expectation was that every row would end up `fixed`.
It did not survive contact: 1,219 of 1,636 rows are `allowlisted` —
intentional suppressors and undecidable-by-construction patches — and those
must be carried into every future regeneration (see below), or the backlog
regrows. The worklist is the allowlist of record and ships to `main`.

## Regeneration semantics

Regenerating from fresh detector runs is safe mid-epic, with two rules:

- `fixed` rows vanish naturally — a repaired test stops being flagged by
  the detectors, so its row simply doesn't reappear. A `fixed` row whose
  key DOES reappear is a regression and correctly reopens.
- `allowlisted` rows must be carried forward (intentional suppressors
  keep appearing dead): pass the previous worklist as the optional fifth
  argument — `triage_mock_findings.py <dead> <unused> <untracked> <out>
  <prior-worklist>`.

## Repair bar (from #1683)

Every repair is hand-mutation-checked: break the guarded contract in
source, confirm the repaired test fails, restore, confirm green.
