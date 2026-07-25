# Patch-liveness reports (#1681, epic #1678)

Canonical detector output for triage (#1685). Generated 2026-07-25 on
`epic/1678-mock-decay` @ `5831c415` with:

```bash
FO_PATCH_LIVENESS_REPORT=<path> python -m pytest tests/ -n auto -q --no-cov
```

then merging the per-worker `<path>.gw*` files and sorting by (file, line).

## Files

- `2026-07-25-dead.jsonl` — 470 rows: patches whose mock recorded zero
  accesses during the test that installed them. 185 distinct
  (file, target) sites across 105 test files.
- `2026-07-25-untracked.jsonl` — 1,244 rows: non-mock replacements
  (`patch(..., <plain value>)`) that cannot be liveness-tracked.

## Exclusions

Two conftest-wide autouse suppressor targets were filtered out of the
dead list — they appear on virtually every test (51,085 of 51,555 raw
dead rows) and are intentional global suppressors, the canonical
`allowlist-intentional` case for triage:

- `file_organizer.cli.organize._check_setup_completed`
- `FileOrganizerApp._check_setup_needed`

Raw (unfiltered) output is reproducible with the command above.

## Lifecycle — WIP artifact, removed at delivery

These files are **frozen scaffolding for the epic, not permanent repo
fixtures**. They are never regenerated or updated in place:

1. **Now**: frozen snapshot, pinned to the commit above. Do not refresh
   it against newer commits — ad-hoc re-runs go to scratch/CI artifacts.
2. **Triage (#1685)**: consumes this snapshot and produces the classified
   worklist. The triage PR **deletes this directory** — the snapshot is
   superseded and git history preserves it.
3. **Repair waves**: the classified worklist is the only living file; it
   only shrinks as batches land.
4. **Enforcement flip (Wave 4)**: worklist empty → deleted as well. The
   invariant then lives in the CI gate (enforce mode fails new dead
   patches) and in per-test `allow_unaccessed_patches` markers — no data
   file to maintain.

Net effect on the epic→main integration PR: none — added and deleted on
the epic branch, so these files never appear in the final merged diff.

## Caveats

- A "dead" row is a *candidate*, not a verdict: patches that exist to
  suppress side effects and `assert_not_called()`-style tests legitimately
  record zero accesses. Classification into repair actions is triage's job
  (#1685).
- Rows are per test×patch instance; dedupe on (file, target) for
  site-level counts.
