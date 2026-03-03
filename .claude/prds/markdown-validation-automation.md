---
name: markdown-validation-automation
description: Automated markdown linting in pre-commit to eliminate recurring PR review churn on formatting issues
status: backlog
created: 2026-03-02T15:25:59Z
---

# PRD: Markdown Validation Automation

## Executive Summary

Add automated markdown linting to the pre-commit validation pipeline to catch formatting issues (heading spacing, trailing whitespace, bare code fences) before they reach PR review. This eliminates the recurring churn of fix-up commits addressing CodeRabbit findings — currently averaging 8+ dedicated fix commits for MD022 alone.

## Problem Statement

Markdown formatting issues in `.claude/` PM files and `docs/` are consistently caught by CodeRabbit during PR review, requiring follow-up fix commits that slow down development velocity. The current pre-commit validation script (`pre-commit-validation.sh`) has strong Python checks but minimal markdown coverage — only broken links and `docs/`-specific formatting. The 1,200+ markdown files in `.claude/` have zero formatting validation.

**Evidence of churn:**

- 8 separate commits fixing MD022 (heading spacing) across multiple PRs
- 10+ commits fixing trailing whitespace in markdown
- An MD022 check was implemented in commit `a939ed8` but stranded on a different branch and never merged

**Why now:** Every PR involving markdown files triggers the same review cycle: submit, get CodeRabbit comments on formatting, push fix commit, re-review. This is a solved problem with the right tooling.

## User Stories

### US-1: Developer commits markdown changes

**As a** developer editing `.claude/` or `docs/` markdown files,
**I want** formatting issues caught at pre-commit time,
**So that** my PRs pass CodeRabbit review on the first attempt.

**Acceptance Criteria:**

- Pre-commit blocks on MD022 violations (missing blank lines around headings)
- Pre-commit blocks on trailing whitespace in markdown
- Pre-commit blocks on bare code fences without language annotation
- Clear error messages with file:line and fix instructions
- Frontmatter blocks and code blocks are correctly skipped (no false positives)

### US-2: Developer runs full markdown lint

**As a** developer wanting to check all markdown files at once,
**I want** a pymarkdown configuration that matches project conventions,
**So that** I can fix all violations before submitting a PR.

**Acceptance Criteria:**

- `pymarkdown` available via `.pre-commit-config.yaml` hook and `pip install -e ".[dev]"`
- `.pymarkdown.json` config at project root with project-appropriate rules
- Running `pymarkdown scan .` produces zero violations after cleanup
- Rules that conflict with project conventions (line length, inline HTML) are disabled

## Requirements

### Functional Requirements

#### FR-1: pymarkdownlnt integration (single source of truth for markdown formatting)

Add pymarkdownlnt as a pre-commit hook (pure Python, no Node.js required):

1. **`.pymarkdown.json` configuration**
   - Enable: MD001, MD009, MD012, MD022, MD031, MD032, MD040, MD047
   - Disable: MD013 (line length), MD033 (inline HTML), MD041 (first line heading — frontmatter), MD024 (duplicate headings — common in CCPM tracking)

2. **`pyproject.toml` dev dependency**
   - Add `pymarkdownlnt` to `[project.optional-dependencies]` dev group

3. **`.pre-commit-config.yaml` hook**
   - Add `jackdewinter/pymarkdown` hook
   - Scope to `*.md` files
   - Runs on staged files only

#### FR-2: Consolidate existing bash checks (remove redundancy)

Remove checks from `pre-commit-validation.sh` that pymarkdownlnt now covers:

1. **Remove bare code fence check** (Section 7a-2, lines ~199-208)
   - Currently scoped to `docs/` only — pymarkdownlnt MD040 covers all `.md` files
   - Removing eliminates duplicate maintenance

2. **Keep broken link check** (Section 7)
   - pymarkdownlnt does not validate link targets — bash check remains necessary

3. **Keep docs/-specific checks** (Section 7a-2: no frontmatter, first line heading)
   - These enforce `docs/`-specific conventions that pymarkdownlnt rules would conflict with globally

#### FR-3: One-time cleanup

Fix all existing violations across `.claude/` and `docs/` so the gates are clean from day one.

### Non-Functional Requirements

- **No false positives**: Frontmatter `---` lines, code block content, and markdown inside code examples must be correctly excluded
- **Python-only tooling**: pymarkdownlnt is pure Python — no Node.js required
- **No duplicate checks**: Each formatting rule lives in exactly one place (pymarkdownlnt or bash, not both)

## Success Criteria

| Metric | Target |
|--------|--------|
| MD022 fix-up commits per PR | 0 (down from 1-3) |
| Markdown-related CodeRabbit comments per PR | 0 |
| Pre-commit false positive rate on markdown | 0% |
| Existing violation count after cleanup | 0 |

## Constraints & Assumptions

- **Assumption**: pymarkdownlnt installs cleanly via pip (requires Python 3.10+, we use 3.11+)
- **Constraint**: No Node.js dependency — use Python-native tooling only
- **Constraint**: Must not break existing pre-commit flow — new checks added after existing ones

## Out of Scope

- Markdown formatting auto-fix (developers fix manually based on error output)
- Prose linting (grammar, style — tools like vale/write-good)
- Link validation beyond local files (no HTTP link checking)
- Markdown table formatting enforcement
- Custom markdownlint rules

## Dependencies

- **Internal**: `.claude/scripts/pre-commit-validation.sh` — consolidation target (remove redundant bare fence check)
- **Internal**: `.pre-commit-config.yaml` — hook configuration
- **External**: `pymarkdownlnt` PyPI package (via pip and pre-commit hook)
