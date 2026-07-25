# Canonical mock-decay worklist (#1685, epic #1678)

`worklist.jsonl` is THE living tracker for the epic's repair waves. It
supersedes and replaces the raw detector snapshots (`reports/patch_liveness/`
and `reports/mock_quality/`, deleted in the PR that added this file; git
history preserves them). Regenerate from fresh detector runs with
`scripts/ci/triage_mock_findings.py`.

## Classification (2026-07-25 baseline)

| Action | Tests | Files | Meaning |
| :--- | ---: | ---: | :--- |
| `add-assertion` | 132 | 23 | Param statically unused but mock LIVE at runtime — reached, never asserted |
| `retarget-or-overreach` | 162 | 90 | Param referenced/configured but mock never accessed — drift (#1671) or over-patching |
| `narrow-fixture` | 135 | 13 | Same target dead across ≥5 distinct tests in one file — fixture/autouse over-scoping |
| `delete-or-retarget` | 20 | 10 | Unused AND dead — pure ghost patch |
| `untracked-review` | 1,153 | — | Non-mock replacements (deduped); `status: deferred` until the enforcement phase |

## Row lifecycle

Repair-wave PRs flip rows from `status: open` to `status: fixed` (or
`status: allowlisted` with a `# noqa: unused-patch-argument` marker —
the syntax the rail's suppression parser actually reads — or the
enforcement-phase `allow_unaccessed_patches` pytest marker). The file
only shrinks in open-row count; it is **deleted at the Wave-4
enforcement flip** once no `open` rows remain. Nothing here survives
into the epic→main diff.

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
