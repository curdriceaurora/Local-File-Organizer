# PR #832 Review-Comment Class Audit

## Scope

- PR: `curdriceaurora/Local-File-Organizer#832`
- Head SHA audited: `c14a558817bd7f734fc544e8f2696177a6549411`
- Diff audited: `origin/main...HEAD`
- Files in diff:
  - `src/file_organizer/cli/benchmark.py`
  - `tests/ci/test_benchmark_contracts.py`
  - `tests/ci/test_benchmark_testproof_guardrails.py`
  - `docs/plans/review-regressions/2026-03-15-issue-813-pr4-benchmark-testproof-guardrails.md`

## Input Review Corpus

- Source: all top-level PR review comments (`in_reply_to_id == null`) on PR #832.
- Count: 18 top-level findings.
- Normalized into 11 unique issue classes (duplicates merged by intent).

## Audit Method

1. Extracted and normalized all PR review comments into unique issue classes.
2. Audited the entire PR diff for each class using direct code inspection.
3. Ran focused validation suite:
   - `pytest tests/ci/test_benchmark_contracts.py tests/ci/test_benchmark_testproof_guardrails.py -q --no-cov`
4. Ran targeted adversarial probes for unresolved-risk classes.

## Class Matrix

| Class ID | Issue Class | Related Comment IDs | Status | Evidence |
|---|---|---:|---|---|
| C1 | Contract tests must enforce full benchmark schema, not key presence only | 2937121116 | PASS | `tests/ci/test_benchmark_contracts.py:57-77`, `:102-113` call `validate_benchmark_payload(...)` and assert typed/non-negative metrics. |
| C2 | `degraded`/`degradation_reasons` semantic consistency must be enforced | 2937185950 | PASS | `src/file_organizer/cli/benchmark.py:191-218` enforces bool type + bidirectional invariant. |
| C3 | Empty-input JSON path must preserve suite classification semantics | 2937226662 | PASS | `src/file_organizer/cli/benchmark.py:991-1014` classifies empty outcome before emit. |
| C4 | Empty-input JSON path with `--compare` must still attach comparison output | 2937226662, 2937359103 | PASS | `src/file_organizer/cli/benchmark.py:1006-1012` attaches compare output; contract test uses empty input dir at `tests/ci/test_benchmark_contracts.py:320-338`. |
| C5 | `pytest.raises(match=...)` should use raw regex string literal | 2937226665 | PASS | `tests/ci/test_benchmark_contracts.py:194` uses `match=r"degraded.*degradation_reasons"`. |
| C6 | Delegation guardrail must require structured non-empty payload | 2937117559, 2937121118, 2937139798 | PASS | `tests/ci/test_benchmark_testproof_guardrails.py:120-142`, plus matrix coverage at `:314-340`. |
| C7 | Processed-count guardrail must bind to direct suite-run result variable | 2937217703 | PASS | `tests/ci/test_benchmark_testproof_guardrails.py:145-190` tracks assigned `_run_audio_suite` result names only. |
| C8 | Cleanup guardrail must enforce ordered pre/post state, receiver correlation, and every cleanup call | 2937139799, 2937217706, 2937226679, 2937360999 | PASS | Receiver-aware + per-cleanup validation at `tests/ci/test_benchmark_testproof_guardrails.py:206-261`; adversarial matrix at `:434-539`. |
| C9 | AST guardrails must ignore nested defs/classes (including wrapped in top-level control flow) | 2937226675, 2937359101 | PASS | Nested defs/classes skipped in walker at `tests/ci/test_benchmark_testproof_guardrails.py:86-117`; dedicated tests at `:342-367`. |
| C10 | AST guardrails must prune unreachable constant-false branches broadly (`if 0`, `if ""`, `if None`, etc.) | 2937368967, 2937380600 | **FAIL** | Current pruning handles only bool constants (`isinstance(test.value, bool)`) at `tests/ci/test_benchmark_testproof_guardrails.py:94-98`. Probe shows bypass: `_has_mock_assert_called_once_with(...)` returns `True` for assertion under `if 0:`. |
| C11 | Guardrail function lookup must target actually collected test definitions, not arbitrary class methods | 2937380603 | **FAIL** | `_find_function(...)` scans all classes at `tests/ci/test_benchmark_testproof_guardrails.py:20-30`; probe confirms it accepts same-named method in non-test class. |

## Validation Output

- `pytest tests/ci/test_benchmark_contracts.py tests/ci/test_benchmark_testproof_guardrails.py -q --no-cov`
  - Result: `59 passed in 2.26s`

## Targeted Repro Evidence For Failing Classes

### C10 Repro (`if 0` still counted)

Observed behavior with current guardrail helpers:

- Input:
  - Function body containing `if 0: mocked_io_suite.assert_called_once_with([candidate])`
- Result:
  - `_has_mock_assert_called_once_with(...)` returns `True`
- Why it fails:
  - Walker prunes only `ast.Constant(bool)` and traverses other constant-falsy tests.

### C11 Repro (non-collected class method accepted)

Observed behavior with current `_find_function(...)`:

- Input:
  - Module containing only:
    - `class Helper:`
    - `def test_audio_suite_warns_when_falling_back_to_io(self): ...`
- Result:
  - `_find_function(...)` returns that class method.
- Why it fails:
  - Helper does not restrict class search to pytest-collected test classes.

## Summary

- Unique issue classes audited: **11**
- Passing classes: **9**
- Failing classes: **2** (`C10`, `C11`)
- Current unresolved review threads align with failing classes.
