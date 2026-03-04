---
name: docs-ci
status: backlog
created: 2026-03-04T20:51:18Z
updated: 2026-03-04T21:12:56Z
progress: 0%
prd: .claude/prds/docs-ci.md
github: https://github.com/curdriceaurora/Local-File-Organizer/issues/589
---

# Epic: docs-ci

## Overview

Add CI automation to eliminate the recurring documentation PR review churn identified in the PR #588 retrospective. Two GitHub Actions workflows (markdown linting + link validation) handle structural issues. Two `tests/docs/` accuracy tests and a new-file template handle content drift and omission issues. Together they convert ~40 of 46 historical review comments into automated failures caught before human review.

## Architecture Decisions

- **CI workflows over pre-commit only**: Pre-commit hooks run locally but not in CI. Adding GitHub Actions ensures enforcement even when contributors bypass hooks. Complements existing `markdown-validation-automation` epic (pre-commit side).
- **Accuracy tests in `tests/docs/`**: Leverages existing test infrastructure. Tests run in the same pytest suite as the rest of the project — no new framework or runner needed.
- **`pyproject.toml` as single source of truth**: Tests read extras and markers directly from `pyproject.toml` rather than hardcoding values. Auto-adapts when new extras/markers are added.
- **No auto-fix in CI**: CI reports violations; developers fix locally. Keeps CI deterministic.
- **markdownlint-cli2 (Node) in CI only**: Acceptable tradeoff — runs in CI GitHub Actions, not added to local Python dev environment.

## Technical Approach

### CI Workflows (2 files)

**`.github/workflows/docs-lint.yml`**
- Trigger: push, pull_request (all branches)
- Action: `DavidAnson/markdownlint-cli2-action@v17`
- Glob: `docs/**/*.md` and `*.md`
- Rules: MD001, MD022, MD040, MD041

**`.github/workflows/docs-link-check.yml`**
- Trigger: push, pull_request
- Action: link checker (e.g., `gaurav-nelson/github-action-markdown-link-check` or `lycheeverse/lychee-action`)
- Scope: relative links only (skip `http://`, `https://`)
- Config: ignore external URLs to avoid flakiness

### Accuracy Tests (extend `tests/docs/`)

**`tests/docs/test_doc_file_paths.py`**
- Regex-extract path references from `docs/**/*.md`
- Filter to paths that look like repo-relative file paths (e.g., `core/organizer.py`, `src/file_organizer/`)
- `assert Path(repo_root / path).exists()` for each

**`tests/docs/test_pyproject_sync.py`**
- Read `[project.optional-dependencies]` keys via `tomllib`/`tomli`
- Assert each key appears in `docs/setup/dependencies.md`
- Read `markers` from `[tool.pytest.ini_options]`
- Assert each marker name appears in `docs/testing/testing-strategy.md`

**`docs/_template.md`**
- Reference template for new doc files
- Correct H1, `##` subsections, blank lines, language-tagged fences

## Implementation Strategy

**Phase 1 (P0)** — CI workflows: highest ROI, lowest effort. Two small YAML files eliminate all structural/lint review comments.

**Phase 2 (P1)** — Accuracy tests: file path + pyproject sync checks. Prevent content drift from reaching review.

**Phase 3 (P2)** — Template: one markdown file, no code. Makes correct structure the default for new docs.

## Task Breakdown Preview

- [ ] Task 1: Add markdown linting CI workflow (docs-lint.yml)
- [ ] Task 2: Add link validation CI workflow (docs-link-check.yml)
- [ ] Task 3: Add file path existence test (test_doc_file_paths.py)
- [ ] Task 4: Add pyproject.toml sync tests for extras + markers (test_pyproject_sync.py)
- [ ] Task 5: Add new-file template (docs/_template.md)

## Dependencies

- **Internal**: `.github/workflows/` directory (exists)
- **Internal**: `tests/docs/` directory (exists — `test_code_examples.py`, `test_cli_docs_accuracy.py`)
- **Internal**: `pyproject.toml` with `[project.optional-dependencies]` and `[tool.pytest.ini_options]`
- **External**: `DavidAnson/markdownlint-cli2-action@v17` (GitHub Action, Node-based)
- **External**: Link checker GitHub Action (TBD — lychee or markdown-link-check)
- **Related**: `markdown-validation-automation` epic (pre-commit hooks, complementary)

## Success Criteria (Technical)

- `docs-lint.yml` CI check runs and blocks PRs with MD001/MD022/MD040/MD041 violations
- `docs-link-check.yml` CI check runs and blocks PRs with broken relative links
- `test_doc_file_paths.py` fails if a doc references a non-existent file path
- `test_pyproject_sync.py` fails if `pyproject.toml` extras or markers are not documented
- All new tests pass in CI against the current codebase
- Next documentation PR requires ≤1 review round

## Estimated Effort

- **Task 1** (docs-lint.yml): 30 min
- **Task 2** (docs-link-check.yml): 30 min
- **Task 3** (test_doc_file_paths.py): 1 hour
- **Task 4** (test_pyproject_sync.py): 1 hour
- **Task 5** (docs/_template.md): 15 min

**Total**: ~3.25 hours | 7 files created/modified

## Tasks Created

- [ ] #590 - Add markdown linting CI workflow (parallel: true)
- [ ] #591 - Add link validation CI workflow (parallel: true)
- [ ] #592 - Add file path existence test (parallel: true)
- [ ] #593 - Add pyproject.toml sync tests (parallel: true)
- [ ] #594 - Add new-file template for docs (parallel: true)

Total tasks: 5
Parallel tasks: 5
Sequential tasks: 0
Estimated total effort: 3.25 hours
