# Design: Docs CI Remaining Issues (#597, #598, #599)

## Overview

Three remaining issues from the docs-ci epic (PR #595 CodeRabbit review feedback).
Issues #597 and #599 are combined into a single implementation since they affect the
same file with overlapping concerns.

## Work Item A: Section-anchored matching (#597 + #599)

**File**: `tests/docs/test_pyproject_sync.py`

**Problem**: Current `re.search(rf"\b{re.escape(extra)}\b", content)` searches the
entire document. Short names like `docs`, `dev`, `unit` can match unrelated prose,
masking genuine omissions.

**Solution**: Add `_extract_section(content, heading)` helper that extracts markdown
content from a heading to the next same-level heading (or EOF). Apply word-boundary
regex within the extracted section only.

- `test_extra_documented`: search within "Optional Dependencies" section
- `test_marker_documented`: search within "Test Markers" section

**Acceptance criteria**:
- Word-boundary matching scoped to relevant doc section
- Tests still pass
- False positive risk eliminated for short names

## Work Item B: Pin GitHub Actions SHAs (#598)

**Files**: `.github/workflows/docs-lint.yml`, `.github/workflows/docs-link-check.yml`

**Problem**: Mutable tag refs (`@v4`, `@v17`, `@v2`) can be force-moved by upstream
maintainers, creating a supply-chain risk.

**Solution**:
- Replace each mutable tag with its current 40-char commit SHA
- Add `permissions: contents: read` to each job
- Keep tag as inline comment for readability: `@SHA  # v4.3.1`

**Actions to pin**:
- `actions/checkout@v4`
- `DavidAnson/markdownlint-cli2-action@v17`
- `lycheeverse/lychee-action@v2`

## Implementation Strategy

Two independent streams, can be done in parallel:
- Stream A: `test_pyproject_sync.py` changes
- Stream B: workflow YAML changes

Both are on `main` — create a single feature branch for all three issues.
