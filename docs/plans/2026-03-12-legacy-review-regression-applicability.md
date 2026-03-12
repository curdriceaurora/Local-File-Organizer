# Legacy Review Regression Applicability Review

Issue: `#777`  
Epic: `#776`  
Date: `2026-03-12`

## Purpose

Determine whether the legacy review-regression eradication epic is applicable to
the current `main` branch by evaluating the three first-wave rule classes
against the current forward guardrail baseline.

This review is intentionally limited to applicability and gap classification. It
does not implement detectors, remediate findings, or change CI enforcement.

## Inputs Reviewed

- `.pre-commit-config.yaml`
- `.claude/scripts/pre-commit-validation.sh`
- `tests/ci/test_path_security_contract.py`
- `tests/ci/test_prefetch_contracts.py`
- `tests/ci/test_review_regressions.py`
- `tests/ci/test_traceback_logging_guard.py`
- `tests/ci/test_weak_test_assertions.py`
- `docs/developer/guardrails.md`
- Epic inputs referenced by `#776`: `#766`, `#657`, `#656`

## Status Definitions

Each first-wave rule class must be assigned exactly one status:

- `forward-covered with legacy risk`
- `forward-partially-covered with legacy risk`
- `not forward-covered`
- `not applicable`

## Applicability Review

| Rule class | Current forward coverage | Legacy-risk evidence on current `main` | Status |
| --- | --- | --- | --- |
| Security: path-safety and validation-bypass violations | Forward enforcement exists, but it is narrow and surface-specific. `tests/ci/test_path_security_contract.py` constrains direct `Path(...)` usage only within `src/file_organizer/api` and `src/file_organizer/web`, and it relies on an explicit allowlist plus specific CodeQL suppression expectations. | Existing allowlisted path-handling snippets and existing `codeql[py/path-injection]` suppressions show reviewed exception surfaces already exist in `main`. There is no repo-wide detector or audit artifact proving zero legacy findings for the rest of the codebase. Validation-bypass coverage also exists only as specific regression tests, not as a first-wave detector pack. | `forward-partially-covered with legacy risk` |
| Correctness: known review-derived invariant/regression patterns | Forward enforcement exists for several specific patterns: `tests/ci/test_review_regressions.py` covers a small set of review-derived regressions, `tests/ci/test_prefetch_contracts.py` covers the prefetch public contract, and `tests/ci/test_traceback_logging_guard.py` covers traceback-preservation logging behavior. | The current controls are regression-specific, not class-wide. They prove protection for known cases that have already been encoded, but there is no general correctness detector pack or full-repo audit entrypoint to establish that earlier review-derived invariant violations have been eradicated from `main`. | `forward-partially-covered with legacy risk` |
| Test quality: weak assertions that do not prove behavior | Forward enforcement exists for one high-confidence subtype only. `tests/ci/test_weak_test_assertions.py` blocks new or changed tests that use weak mock `call_count` lower bounds in a small set of exact forms. | Current `main` still contains legacy-style weak assertions outside the changed-file guard, for example in `tests/tui/test_audio_view.py`, `tests/tui/test_methodology_view_coverage.py`, `tests/tui/test_undo_history_view_coverage.py`, `tests/test_web_organize_routes.py`, and `tests/integration/test_fallback_no_ollama.py`. The existing guard is intentionally forward-only and does not prove the historical backlog is clean. | `forward-partially-covered with legacy risk` |

## Binary Conclusion

`epic applicable`

## Why The Epic Is Applicable

The epic is applicable because:

1. All three first-wave rule classes have some forward coverage, but none has a
   repo-wide zero-finding proof.
2. At least one first-wave class has already demonstrated legacy findings in
   `main`: the weak-assertion class still has historical violations outside the
   changed-file guard.
3. The current forward guardrails are deliberately optimized to stop new churn,
   not to certify that historical backlog has been eradicated.

That means the remaining tasks in `#776` are not redundant. They are the lane
that converts partial forward protection into a full backfill audit, classified
backlog, and zero-finding steady state for the first-wave classes.

## Go / No-Go Decision

Go.

Downstream implementation work may proceed because the applicability review
conclusion is `epic applicable`.

## Implications For Downstream Tasks

- `#778` should build a reusable audit entrypoint rather than embedding
  one-off logic in each detector.
- `#779`, `#780`, and `#781` should treat the current forward guardrails as the
  reference baseline, not as proof that legacy backlog is already zero.
- `#782` must produce the first repo-wide classified backlog artifact.
- `#783` through `#786` should assume that at least one class already has real
  backlog on `main`, and potentially more once detector packs are in place.
