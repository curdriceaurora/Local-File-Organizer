# WP-0.1 — Re-targeting Checklist

**Part of:** #1221 · Phase 0 · WP-0.1 (#1222)
**Companion to:** `fo-core-pullback-implementation-plan.md`,
`fo-core-fork-evaluation.md`

The fork (`curdriceaurora/fo-core`) uses a flat `src/X` layout. This repo's
package root is `src/file_organizer/`. Every ported work package must re-target
the fork's layout onto ours. This checklist makes that mechanical and reviewable
(the "Layout drift" risk in the plan's risk register).

## Package root (confirmed)

This repo's package root **stays** `src/file_organizer/`. WP-0.1 introduces no
runtime change and does not move or rename the package.

## Layout mapping

| Fork (source) | This repo (target) |
|---------------|--------------------|
| `src/X/...` | `src/file_organizer/X/...` |
| `tests/...` | `tests/...` (unchanged; tests travel with their module) |
| `scripts/check_*.py` (rails) | `.claude/scripts/check_*.py` (rails live here) |

## Per-module porting checklist

For each module a work package ports:

- [ ] Move `src/X/<mod>.py` → `src/file_organizer/X/<mod>.py`.
- [ ] Rewrite intra-package imports: `from X...` → `from file_organizer.X...`
      and `import X...` → `import file_organizer.X...`.
- [ ] Re-scope any pre-commit hook / CI-rail path glob: `^src/` →
      `^src/file_organizer/`.
- [ ] Port the module's tests (preserve `review_regressions/` security tests —
      never drop them) and confirm they pass.
- [ ] Respect the module's integration coverage floor
      (`[tool.coverage.floors.integration]` in `pyproject.toml`).
- [ ] Add a CHANGELOG entry under `[Unreleased]`.
- [ ] `bash .claude/scripts/pre-commit-validation.sh` green; `/code-reviewer`
      clean.
- [ ] One PR per work package.

## Out of scope (permanently)

The fork-dropped surfaces — `api/`, `web/`, `desktop/`, `tui/`, `client/`,
`plugins/`, `deploy/` — are **not** re-targeted. The original keeps them and the
fork offers no improvements there.

## Scaffolding stood up by WP-0.1

- **CI-rail framework (advisory)** — `.claude/ci-rails.toml` +
  `.claude/scripts/ci_rails.py` + the `ci-rails` pre-commit hook. Empty registry
  = no-op now; WP-6.x adds rails. See `.claude/rules/ci-rails.md`.
- **Test skeletons** — `tests/security/`, `tests/smoke/`, `tests/extras/` with
  their markers registered in `pyproject.toml`.

---
**Last Updated**: 2026-06-20
