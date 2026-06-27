# CI-Rail Framework (advisory → enforce)

**Purpose**: A uniform way to author CI "rails" (mechanical guard checks) and
roll them out safely — advisory first (warn, never block), then enforce (block)
once the code they guard has merged. Stood up by WP-0.1 (#1222); populated by
WP-6.x of the fo-core pull-back plan.

## Pieces

| Piece | Path | Role |
|-------|------|------|
| Registry | `.claude/ci-rails.toml` | Declares each rail (`name`, `command`, `mode`, `description`). |
| Runner | `.claude/scripts/ci_rails.py` | Runs the rails; advisory failures warn, enforce failures fail. |
| Hook | `ci-rails` in `.pre-commit-config.yaml` | Runs the runner at commit time. |
| Tests | `tests/ci/test_ci_rails_framework.py` | Locks the advisory/enforce semantics. |

At WP-0.1 the registry is **empty**, so the runner is a no-op (exit 0).

## Adding a rail (WP-6.x)

1. Write the check script (convention: `.claude/scripts/check_<thing>.py`,
   exit non-zero on violation).
2. Register it in `.claude/ci-rails.toml` as **advisory**:

   ```toml
   [[rail]]
   name = "safedir-required"
   command = ["python", ".claude/scripts/check_safedir_required.py"]
   mode = "advisory"
   description = "Flags raw open() on caller-supplied paths."
   ```

3. Land it. Advisory rails surface warnings without blocking anyone.

## Flipping a rail to enforce

Once the guarded code has merged and the repo is clean, change that rail's
`mode` to `"enforce"`. A non-zero exit then fails `ci-rails`.

## Running

```bash
python .claude/scripts/ci_rails.py             # honor each rail's mode
python .claude/scripts/ci_rails.py --list      # show the registry
python .claude/scripts/ci_rails.py --enforce-all  # CI: treat all rails as enforce
```

## References

- `docs/internal/fo-core-pullback-implementation-plan.md` — Phase 6 (WP-6.x rails)
- `docs/internal/wp-0.1-retargeting-checklist.md` — porting checklist

---
**Last Updated**: 2026-06-27
**Status**: Active (advisory framework; 11 rails registered — see SECURITY.md's lint-rail table for the full list and status of each)
