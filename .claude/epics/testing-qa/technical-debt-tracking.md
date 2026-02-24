---
name: technical-debt-tracking
title: Technical Debt Tracking for testing-qa
epic: testing-qa
created: 2026-02-17T15:07:09Z
updated: 2026-02-23T20:40:00Z
status: active
---

# Technical Debt Tracking - testing-qa

## Tooling & Infrastructure

**Issue #330: [Tech Debt] Remove deprecated code-rabbit Claude Code skill**
- **Priority**: Low
- **Epic**: testing-qa
- **Status**: Open
- **Created**: 2026-02-17
- **GitHub**: https://github.com/curdriceaurora/Local-File-Organizer/issues/330
- **Effort**: 15-30 minutes
- **Description**: Remove dead `.claude/commands/code-rabbit.md` skill file and worktree copies; no production code impact
- **Notes**: Historical references to CodeRabbit in logs/epics/scripts are intentional — only the active skill command needs removal

## Summary

**Total Issues**: 1
- **High Priority**: 0
- **Medium Priority**: 0
- **Low Priority**: 1

**Total Effort Estimate**: 15-30 minutes

## Tracking Updates

- **2026-02-17**: Issue #330 created; code-rabbit removal tracked as low-priority tech debt under testing-qa epic
- **2026-02-23**: Issue #444 completed; semantic validation for test logic and docstring accuracy delivered
- **2026-02-23**: Issue #449 created; tracks cleanup of ~1,600 pre-existing ruff D violations exposed by #444

**Issue #444: chore: add semantic validation for test logic and docstring accuracy**
- **Priority**: Medium
- **Epic**: testing-qa
- **Status**: Closed
- **Created**: 2026-02-23
- **Closed**: 2026-02-23
- **GitHub**: https://github.com/curdriceaurora/Local-File-Organizer/issues/444
- **Effort**: 4-6 hours
- **Related**: #442 (complementary - tooling enforcement vs semantic validation)
- **Deliverables**: `tests/docs/test_cli_docs_helpers.py` (38 tests), `TestMetavarAlignment`, pre-commit CLI docs trigger, ruff D rules

**Issue #449: chore: clean up ~1,600 pre-existing ruff D (pydocstyle) violations**
- **Priority**: Low
- **Epic**: testing-qa
- **Status**: Open
- **Created**: 2026-02-23
- **GitHub**: https://github.com/curdriceaurora/Local-File-Organizer/issues/449
- **Effort**: 4-8 hours
- **Related**: #444 (ruff D rules added in that issue)
- **Notes**: ~1,043 D212 violations are auto-fixable; remainder needs manual docstring authoring

**Issue #451: docs: document 23 CLI parameters missing from cli-reference.md** ✅
- **Priority**: Medium
- **Epic**: testing-qa
- **Status**: Closed (merged PR #452, 2026-02-23)
- **Created**: 2026-02-23
- **GitHub**: https://github.com/curdriceaurora/Local-File-Organizer/issues/451
- **Effort**: 2-3 hours
- **Related**: #444 (regex fix exposed gaps), #449 (separate ruff D violations)
- **Notes**: `KNOWN_PARAM_DOC_GAPS` in test_cli_docs_accuracy.py must be removed once all 23 params are documented
