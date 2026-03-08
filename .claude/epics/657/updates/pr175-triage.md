---
created: 2026-03-08T13:00:00Z
updated: 2026-03-08T13:00:00Z
pr: 175
task: 003
---

# PR #175 Triage Report

PR #175 — Phase 3 documentation sprint (10 new doc files, ~6,500 lines, plus test
placeholder files).

## Summary

- **Total comments fetched**: 106 (64 CodeRabbit, 19 Copilot inline, 19 Copilot review + 4 review-level)
- **Substantive findings classified**: 106 (all inline comments from bots were substantive)
- **D5 WRONG_FORMAT dominance**: 19/106 = **17.9%** — does NOT dominate as expected; D1 and G4 tie at 18% each
- **New pattern candidates identified**: 4

## Pattern Tally

| Pattern ID | Name | Count | Example (truncated) |
|------------|------|-------|---------------------|
| D1 | INACCURATE_CLAIM | 22 | "PARAConfig parameters don't match actual implementation" |
| G4 | UNUSED_CODE | 22 | "Import of 'Path' is not used" |
| D5 | WRONG_FORMAT | 19 | "Fix markdown formatting: missing blank lines around fenced code blocks" |
| D3 | BROKEN_EXAMPLE | 12 | "import path uses `file_organizer` but should be `file_organizer_v2`" |
| D2 | STALE_REFERENCE | 10 | "Fix broken cross-reference — ../api/smart-suggestions-api.md doesn't exist" |
| D6 | CONTRADICTION | 8 | "Fixture directory names are inconsistent across sections" |
| C3 | CACHE_MISCONFIG | 3 | "Link extraction regex is incorrect and will miss most links" |
| T1 | WEAK_ASSERTION | 2 | "`expected_category` defined but never verified in assertion" |
| T3 | WRONG_PAYLOAD | 2 | "Assertion assumes dict return type but `extract()` returns AudioMetadata object" |
| T4 | BROAD_EXCEPTION | 1 | "Catching `Exception` will skip real regressions and hide failures" |
| T9 | RESOURCE_LEAK | 1 | "Test named `test_concurrent_access_simulation` but is not true concurrency" |
| **Total** | | **102** | |

> Note: 4 unclassified comments were trivial auto-generated metadata rows (CodeRabbit fingerprinting lines).

## D5 Sub-Categories (Markdown Rule Breakdown)

| Rule | Count | Notes |
|------|-------|-------|
| blank-lines (MD031) | 17 | Missing blank line before/after fenced code blocks — pervasive across all 10 doc files |
| heading-level (MD036) | 1 | Bold text used as heading (`**CAD Files**`) instead of proper `###` |
| code-fence (nested) | 1 | Nested code block inside outer markdown code block in bug report template |

**Finding**: D5 does NOT dominate PR #175 at only 17.9%. The actual dominant patterns are D1 INACCURATE_CLAIM and G4 UNUSED_CODE, each at ~20.8%. This is likely because the documentation was AI-generated without verifying the actual Python API, producing pervasive wrong class names, parameter names, and enum values.

## D1 Sub-Category Breakdown

| Sub-Category | Count | Example |
|---|---|---|
| undocumented-impl-status-cli | 6 | CLI commands documented without noting unimplemented status |
| wrong-enum-value | 4 | `PARACategory.PROJECTS` should be `PARACategory.PROJECT` |
| class-method-not-exist | 4 | `JohnnyDecimalConfig` class does not exist; `full_number` property is actually `formatted_number` |
| wrong-param-name | 3 | `PARAConfig(enable_learning=True)` — parameter doesn't exist |
| feature-not-implemented | 3 | `detect_file_type()`, `get_format_info()` functions not in codebase |
| referenced-item-not-exist | 2 | `organization-api.md` referenced but doesn't exist |

## G4 Sub-Category Breakdown

| Sub-Category | Count | Example |
|---|---|---|
| unused-import | 17 | `from pathlib import Path` added to placeholder test files but never used |
| unused-variable | 3 | `result = engine.evaluate(file_path)` assigned but never used |
| unused-loop-variable | 1 | Loop variable `i` not used in loop body |
| bak-file-committed | 1 | `116.md.bak` committed to version control |

## D3 Sub-Category Breakdown

| Sub-Category | Count | Example |
|---|---|---|
| wrong-import-path | 12 | All examples use `from file_organizer.methodologies...` but package is `file_organizer_v2` |

**Finding**: All 12 D3 findings are the same root cause — the entire documentation suite uses the wrong package name (`file_organizer` instead of `file_organizer_v2`). This is a single systemic error generating 12 individual comments.

## D2 Sub-Category Breakdown

| Sub-Category | Count | Example |
|---|---|---|
| missing-referenced-file | 5 | `../api/smart-suggestions-api.md` doesn't exist; `organization-api.md` not present |
| placeholder-url | 3 | `your-org` placeholder in community support URLs and GitHub Issues links |
| broken-link | 2 | Cross-reference to non-existent docs files |

## D6 Sub-Category Breakdown

| Sub-Category | Count | Example |
|---|---|---|
| fixture-path-mismatch | 2 | `audio`, `video`, `johnny` in one section vs `audio_samples`, `video_samples`, `johnny_decimal` elsewhere |
| class-signature-mismatch | 2 | `AreaDefinition(area_range=(10,19))` in example but constructor takes `area_range_start`, `area_range_end` |
| general | 2 | Audio metadata test uses dict-style check inconsistently with AudioMetadata object |
| estimate-mismatch | 1 | Top-level estimate says 32 hours, timeline totals 36-44 hours |
| format-label-mismatch | 1 | Code loads `.json` file but comment says "Load from YAML" |

## UNKNOWN Findings (New Pattern Candidates)

### Candidate U1: UNDOCUMENTED_IMPL_STATUS (new sub-pattern of D1)

**Count**: 6 occurrences (comments 75, 76, 80, 82, 83, 89, 90, 91 — after reclassification)
**Description**: Docs show CLI commands as usable examples without marking them as planned/unimplemented, misleading users about what works in current release.
**Example**: "Multiple CLI commands are documented (e.g., `file-organizer jd init`, `file-organizer jd assign`, `file-organizer jd batch-assign`) without clear indication of implementation status."
**Severity**: High — users will run documented commands that do nothing or error.
**Proposed pattern**: D1-CLI_IMPL_STATUS — document current status of all CLI commands shown.

### Candidate U2: SYSTEMIC_PACKAGE_NAME_ERROR (amplified D3)

**Count**: 12 occurrences (all D3 findings in this PR)
**Description**: A single wrong package name (`file_organizer` vs `file_organizer_v2`) propagated through all documentation, generating one D3 finding per code example. This is a single root cause inflating the D3 count by 10x.
**Example**: "The import path uses `file_organizer` but should be `file_organizer_v2` to match the actual package structure. This appears throughout all documentation files."
**Proposed pattern**: D3-SYSTEMIC — root-cause deduplication; when N D3 findings share one root cause, count as 1 systemic error rather than N independent errors.

### Candidate U3: PLACEHOLDER_TEST_IMPORTS (G4 amplifier)

**Count**: 17 unused import findings across test placeholder files
**Description**: Test placeholder files were created with boilerplate imports (`Path`, `Mock`, `patch`, `datetime`, etc.) that the placeholder tests don't use. All flagged by Copilot as lint errors.
**Example**: "Import of 'Path' is not used. Import of 'Mock' is not used. Import of 'patch' is not used."
**Root Cause**: Placeholder test file template includes all common test imports rather than only what's needed.
**Proposed pattern**: G4-PLACEHOLDER_IMPORTS — placeholder tests should start with minimal imports.

### Candidate U4: SCRIPT_CORRECTNESS (new C-class pattern distinct from C3)

**Count**: 3 occurrences (comments 98, 100, 101)
**Description**: Pre-commit shell scripts embedded in documentation contain code bugs — incorrect regex, missing `read -r`, glob patterns that don't recurse into subdirectories. These are not CI configuration errors (C3) but script implementation bugs in documentation examples.
**Example**: "Link extraction regex `'\]\([^)]*\)'` won't match markdown links correctly. The pattern tries to match `](...)` but the character class excludes `)` which is required."
**Proposed pattern**: C6-SCRIPT_BUG (new) — distinguishing CI configuration errors (C3) from actual bugs in shell scripts shown in documentation.

## Key Findings for Epic 657

1. **D5 does not dominate PR #175**: At 17.9%, it ties with D1 and G4. For future docs PRs, expect D1 INACCURATE_CLAIM to be highest risk when docs are AI-generated without API verification.

2. **G4 UNUSED_CODE is docs-PR-specific**: The 22 G4 findings mostly came from placeholder test files, not docs files. If test placeholders are excluded, D1 + D3 + D5 dominate the pure documentation findings.

3. **Systemic errors inflate counts**: The 12 D3 findings are one root cause (wrong package name). The 17 G4 unused-import findings are one root cause (boilerplate test template). Deduplicating by root cause: 106 comments → ~65 distinct issues.

4. **All D3 findings share one fix**: Replacing `file_organizer` → `file_organizer_v2` throughout all doc examples resolves all 12 D3 findings simultaneously.

5. **API verification is the dominant gap**: D1 (22 findings) + D3 (12 findings) = 34 findings that would be caught by running `python3 -c "from file_organizer_v2... import ..."` against each code example before committing.
