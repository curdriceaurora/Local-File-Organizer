---
name: markdown-validation-automation
status: in-progress
created: 2026-03-02T15:30:54Z
updated: 2026-03-02T16:15:03Z
progress: 0%
prd: .claude/prds/markdown-validation-automation.md
github: https://github.com/curdriceaurora/Local-File-Organizer/issues/565
---

# Epic: Markdown Validation Automation

## Overview

Add pymarkdownlnt (Python-native) as the single source of truth for markdown formatting validation via a `.pre-commit-config.yaml` hook. Consolidate the existing bash pre-commit script by removing the bare code fence check (now redundant with pymarkdownlnt MD040). No Node.js dependency. Includes a one-time cleanup of existing violations.

## Architecture Decisions

- **Single-layer approach**: pymarkdownlnt handles all markdown formatting rules. No duplicate bash checks — each rule lives in exactly one place.
- **Python-native tooling**: Use pymarkdownlnt (pip install) instead of markdownlint-cli (npm). Stays in the Python ecosystem.
- **Consolidate, don't extend**: Remove the existing bare code fence check from `pre-commit-validation.sh` (pymarkdownlnt MD040 covers it for all `.md` files). Keep only bash checks for things pymarkdownlnt can't do (broken links, docs/-specific conventions).
- **Conservative rule config**: Start with 8 high-value rules enabled (MD001, MD009, MD012, MD022, MD031, MD032, MD040, MD047), disable noisy rules (line length, inline HTML, duplicate headings). Can tighten later.

## Technical Approach

### pymarkdownlnt Integration

- `.pymarkdown.json` at project root with enabled/disabled rule set
- `pymarkdownlnt` added to `pyproject.toml` dev dependencies
- `.pre-commit-config.yaml` hook using `jackdewinter/pymarkdown`
- Scoped to `**/*.md`

### Bash Script Consolidation

In `.claude/scripts/pre-commit-validation.sh`:
- **Remove**: Bare code fence check in Section 7a-2 (lines ~199-208) — pymarkdownlnt MD040 covers this for all `.md` files
- **Keep**: Broken link check (Section 7) — pymarkdownlnt doesn't validate link targets
- **Keep**: docs/-specific checks (no frontmatter, first line heading) — docs/-specific conventions

### One-Time Cleanup

Run `pymarkdown scan` across `.claude/` and `docs/`, fix all violations in a single commit so gates are clean from day one.

## Task Breakdown Preview

- [ ] Task 1: Create .pymarkdown.json config, add pymarkdownlnt to pyproject.toml, add hook to .pre-commit-config.yaml
- [ ] Task 2: Remove redundant bare code fence check from pre-commit-validation.sh
- [ ] Task 3: Fix all existing markdown violations across .claude/ and docs/
- [ ] Task 4: Verify end-to-end — pymarkdown catches violations, zero false positives, no regression

## Dependencies

- **Internal**: `.claude/scripts/pre-commit-validation.sh` — consolidation target (remove redundant check)
- **Internal**: `.pre-commit-config.yaml` — hook configuration
- **External**: `pymarkdownlnt` PyPI package (pip install, Python-native)

## Success Criteria (Technical)

- `pymarkdown scan .` passes with zero violations after cleanup
- Bare code fence check removed from `pre-commit-validation.sh` (no duplicate maintenance)
- Zero false positives on frontmatter `---` lines and code block content
- No regression on existing Python validation checks or remaining bash markdown checks

## Estimated Effort

- **Total**: 2-3 hours
- **Task 1** (pymarkdown config + pyproject.toml + hook): 30 minutes
- **Task 2** (bash consolidation): 15 minutes — just removing a code block
- **Task 3** (cleanup): 1-2 hours — bulk of work, many files to fix
- **Task 4** (verification): 30 minutes
- **Critical path**: Task 3 (cleanup) is the longest, but straightforward

## Tasks Created

- [ ] #566 - pymarkdown config and pre-commit hook setup (parallel: false)
- [ ] #567 - Remove redundant bare code fence check from pre-commit script (parallel: false, depends: #566)
- [ ] #568 - Fix all existing markdown violations (parallel: true, depends: #566)
- [ ] #569 - End-to-end verification (parallel: false, depends: #566, #567, #568)

Total tasks: 4
Parallel tasks: 1
Sequential tasks: 3
Estimated total effort: 2.75 hours
