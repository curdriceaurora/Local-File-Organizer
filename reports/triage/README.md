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
| `retarget-or-overreach` | 158 | 89 | Param referenced/configured but mock never accessed — drift (#1671) or over-patching |
| `narrow-fixture` | 139 | 14 | Same target dead across ≥5 tests in one file — fixture/autouse over-scoping |
| `delete-or-retarget` | 20 | 10 | Unused AND dead — pure ghost patch |
| `untracked-review` | 1,244 | — | Non-mock replacements; `status: deferred` until the enforcement phase |

## Row lifecycle

Repair-wave PRs flip rows from `status: open` to `status: fixed` (or
`status: allowlisted` with a `# noqa: unused-patch-argument` /
`allow_unaccessed_patches` marker in the test). The file only shrinks in
open-row count; it is **deleted at the Wave-4 enforcement flip** once no
`open` rows remain. Nothing here survives into the epic→main diff.

## Repair bar (from #1683)

Every repair is hand-mutation-checked: break the guarded contract in
source, confirm the repaired test fails, restore, confirm green.
