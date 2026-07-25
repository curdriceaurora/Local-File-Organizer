# Static mock-quality reports (#1682, epic #1678)

Canonical static-detector output for triage (#1685). Generated 2026-07-25
on `epic/1678-mock-decay` @ `fe9b11ba` with the `unused-patch-argument`
guardrail (`scripts/ci/guardrails/check_unused_patch_argument.py`).

## Files

- `2026-07-25-unused-patch-args.jsonl` — 231 rows: `@patch`-injected test
  parameters never referenced in the test body. 162 distinct tests across
  29 test files. Replaces the inspection report's unverified "289".

ruff `PGH005` (uncalled `assert_*` properties) was enabled in the same PR
and found **zero** existing violations — that half of the rail is purely
preventive.

## Lifecycle — WIP artifact, removed at delivery

Same contract as `reports/patch_liveness/README.md`: frozen snapshot,
consumed by triage (#1685) into the classified worklist, **deleted by the
triage PR**, with the worklist itself deleted at the Wave-4 enforcement
flip. Nothing here survives into the epic→main integration diff. Ad-hoc
re-runs: `python scripts/ci/guardrails/check_unused_patch_argument.py`.

## Enforcement state

- Commit-time: pre-commit hook `unused-patch-argument` fails only on
  violations in staged-diff lines (new decay blocked; backlog non-blocking).
- CI: `rails.toml` entry in **advisory** mode; flipped to enforce at Wave 4
  once the worklist is drained.
