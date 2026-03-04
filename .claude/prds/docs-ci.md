---
name: docs-ci
description: Automate PR review churn reduction via markdown linting, link validation, and accuracy tests in CI
status: backlog
created: 2026-03-04T20:49:52Z
---

# PRD: docs-ci

## Executive Summary

PR #588 retrospective showed 46 inline review comments across 6 rounds — most were preventable with automated CI checks. This epic adds markdown linting, link validation, and accuracy test coverage to catch documentation errors before human review, targeting a reduction from 6 review rounds to 1.

## Problem Statement

Documentation PRs in this repo generate disproportionate review churn. PR #588 required 6 review rounds and 6 fix commits for issues that automation could have caught before the first human reviewer saw the PR:

- **67% of comments** were structural/lint violations (missing H1s, heading hierarchy, bare code fences, broken links) — all catchable by `markdownlint` and `markdown-link-check`
- **25% were content drift** — wrong file paths, renamed classes, stale marker names — catchable by accuracy tests in `tests/docs/`
- **8% were omissions** — new extras or markers added to `pyproject.toml` without updating docs — catchable by sync-check tests

Without CI automation, every documentation PR requires multiple human review rounds to catch what machines could verify instantly.

## User Stories

### Primary Persona: Claude Agent / Developer authoring docs PRs

**Story 1**: As a developer submitting a docs PR, I want CI to block on markdown lint violations before any human reviews my PR, so that I fix formatting issues in my local loop rather than across multiple review rounds.

*Acceptance Criteria:*
- `markdownlint` runs on all `**/*.md` files in CI
- MD001 (heading hierarchy), MD022 (blank lines), MD040 (code fence language), MD041 (H1 first) are enforced
- CI fails with a clear report before any reviewer is notified

**Story 2**: As a developer, I want CI to validate that all relative links in docs resolve to real files, so that I catch broken references immediately on push.

*Acceptance Criteria:*
- `markdown-link-check` runs on all docs
- Relative links are checked against the filesystem
- Broken links cause CI failure with specific file/line report

**Story 3**: As a developer, I want CI to verify that file paths, class names, and pytest markers mentioned in docs actually exist in the codebase, so that content drift is caught before merge.

*Acceptance Criteria:*
- `tests/docs/test_doc_file_paths.py` checks that paths mentioned in docs exist on disk
- `tests/docs/test_doc_symbols.py` checks that class/function names in docs exist in source
- `tests/docs/test_pyproject_sync.py` checks that extras and markers in `pyproject.toml` appear in relevant docs

**Story 4**: As a developer adding a new optional dependency group or pytest marker, I want a test to fail if I forget to document it, so that omissions are caught automatically.

*Acceptance Criteria:*
- Adding a key to `[project.optional-dependencies]` without updating `docs/setup/dependencies.md` causes test failure
- Adding a marker to `[tool.pytest.ini_options]` without updating `docs/testing/testing-strategy.md` causes test failure

## Requirements

### Functional Requirements

**FR-1: Markdown linting in CI (P0)**
- Add `.github/workflows/docs-lint.yml` using `DavidAnson/markdownlint-cli2-action@v17`
- Glob: `**/*.md`
- Rules enforced: MD001, MD022, MD040, MD041
- Runs on: push, pull_request

**FR-2: Link validation in CI (P0)**
- Add `.github/workflows/docs-link-check.yml`
- Validate all relative links in `docs/**/*.md` and root `*.md` files
- Skip external URLs (rate limits / flakiness)
- Runs on: push, pull_request

**FR-3: File path existence test (P1)**
- `tests/docs/test_doc_file_paths.py`
- Extract file path references from docs using regex
- Assert each referenced path exists in the repo filesystem
- Target references: `core/organizer.py`, `src/file_organizer/`, etc.

**FR-4: Symbol name existence test (P1)**
- `tests/docs/test_doc_symbols.py`
- Extract class/function names documented in architecture and setup docs
- Assert each symbol is importable or exists via `ast-grep` search
- Target symbols: `SuggestionEngine`, `DeviceType`, etc.

**FR-5: pyproject.toml extras sync check (P1)**
- `tests/docs/test_pyproject_sync.py`
- Read `[project.optional-dependencies]` keys from `pyproject.toml`
- Assert each key appears in `docs/setup/dependencies.md`

**FR-6: pytest marker sync check (P2)**
- Extend `tests/docs/test_pyproject_sync.py` or separate file
- Read `markers` from `[tool.pytest.ini_options]` in `pyproject.toml`
- Assert each marker name appears in `docs/testing/testing-strategy.md`

**FR-7: New-file template (P2)**
- `docs/_template.md` with correct structure:
  - H1 title at top
  - `##` for subsections (not `###`)
  - Blank lines around all headings
  - Language specifiers on all code fences

### Non-Functional Requirements

- CI checks must complete in under 2 minutes
- No new runtime dependencies on the main package
- Test files follow existing `tests/docs/` conventions
- CI workflows use pinned action versions for reproducibility

## Success Criteria

| Metric | Current | Target |
|--------|---------|--------|
| Review rounds per docs PR | 6 (PR #588) | ≤ 1 |
| Lint/structural comments per PR | ~24 | 0 (caught by CI) |
| Content drift comments per PR | ~9 | 0 (caught by tests) |
| Time to first clean CI run | N/A | < 2 min |

**Primary KPI**: Next documentation PR passes review in ≤ 1 round with 0 structural or lint comments.

## Constraints & Assumptions

- GitHub Actions is the CI platform (already in use)
- `markdownlint-cli2-action` is Node-based but runs only in CI (no local Node requirement added)
- Accuracy tests run against the local filesystem, so they work in CI without special setup
- `pyproject.toml` is the single source of truth for extras and markers

## Out of Scope

- External link validation (too flaky for CI)
- Auto-fixing markdown violations in CI (report only)
- Replacing the existing `pymarkdown` pre-commit hook (complementary, not replacement)

## Dependencies

- **Internal**: `tests/docs/` directory (already exists with `test_code_examples.py`, `test_cli_docs_accuracy.py`)
- **Internal**: `pyproject.toml` (source of truth for extras/markers)
- **External**: `DavidAnson/markdownlint-cli2-action@v17` (GitHub Action)
- **External**: `markdown-link-check` or equivalent link checker action
- **Related epic**: `markdown-validation-automation` (pre-commit side; this epic covers CI side)

## Implementation Plan

### Phase 1 — P0: CI Workflows (2 files, ~20 lines total)

1. `.github/workflows/docs-lint.yml`
2. `.github/workflows/docs-link-check.yml`

**Estimated effort**: 1 hour. Eliminates ~19 of 46 PR #588 comments (53%).

### Phase 2 — P1: Accuracy Tests (3 files, ~65 lines total)

1. `tests/docs/test_doc_file_paths.py`
2. `tests/docs/test_doc_symbols.py`
3. `tests/docs/test_pyproject_sync.py`

**Estimated effort**: 2–3 hours. Eliminates recurring content drift and omission comments.

### Phase 3 — P2: Template & Marker Check (2 files)

1. `docs/_template.md`
2. Marker sync check (extend test_pyproject_sync.py)

**Estimated effort**: 30 minutes.

**Total effort**: 3–5 hours across 7 files.
