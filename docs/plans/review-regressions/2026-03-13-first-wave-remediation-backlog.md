# First-Wave Legacy Review Regression Backlog (Issue #782)

Date: `2026-03-13`  
Epic: `#776`  
Task: `#782`  
Audit artifact: `docs/plans/review-regressions/2026-03-13-first-wave-audit.json`

## Why This Document Exists

`#782` owns the first full-repo scan and the reconciled remediation backlog.
This document is the implementation-ready backlog derived directly from the
stored audit artifact.

## Pitfalls Up Front

- The current forward guard for weak mock-call assertions is intentionally
  changed-file scoped (`tests/ci/test_weak_test_assertions.py`), so historical
  findings on `main` are expected and should not be misclassified as a detector
  bug.
- Zero findings in a rule class (`security`, `correctness`) do **not** mean that
  class can be dropped from future scans; it means this scan found no open
  backlog for those detectors.
- Every finding must be mapped to exactly one gap class so totals reconcile and
  remediation priority remains unambiguous.

## Audit Command

```bash
python3 -m file_organizer.review_regressions.audit \
  --root . \
  --detector file_organizer.review_regressions.security:SECURITY_DETECTORS \
  --detector file_organizer.review_regressions.correctness:CORRECTNESS_DETECTORS \
  --detector file_organizer.review_regressions.test_quality:TEST_QUALITY_DETECTORS
```

## Reconciliation Metadata

<!-- REVIEW_REGRESSION_BACKLOG_METADATA_START -->
```json
{
  "audit_artifact": "docs/plans/review-regressions/2026-03-13-first-wave-audit.json",
  "audit_finding_total": 16,
  "classified_finding_total": 16,
  "classification_totals": {
    "legacy-only gap": 16,
    "forward-gap and legacy-gap": 0
  },
  "rule_class_totals": {
    "security": 0,
    "correctness": 0,
    "test-quality": 16
  },
  "severity_totals": {
    "high": 0,
    "medium": 16,
    "low": 0
  }
}
```
<!-- REVIEW_REGRESSION_BACKLOG_METADATA_END -->

## Rule-Class Summary

| Rule class | Findings | Gap category split | Severity split |
| --- | ---: | --- | --- |
| `security` | 0 | `legacy-only gap`: 0, `forward-gap and legacy-gap`: 0 | high: 0, medium: 0, low: 0 |
| `correctness` | 0 | `legacy-only gap`: 0, `forward-gap and legacy-gap`: 0 | high: 0, medium: 0, low: 0 |
| `test-quality` | 16 | `legacy-only gap`: 16, `forward-gap and legacy-gap`: 0 | high: 0, medium: 16, low: 0 |

## Risk-Ordered Remediation Sequence

1. `tests/tui/test_methodology_view_coverage.py` (7 findings)
1. `tests/tui/test_undo_history_view_coverage.py` (3 findings)
1. `tests/tui/test_audio_view.py` (2 findings)
1. `tests/integration/test_fallback_no_ollama.py` (2 findings)
1. `tests/tui/test_analytics_view_coverage.py` and `tests/test_web_organize_routes.py` (1 each)

Priority rationale: backlog concentration is highest in TUI coverage tests, so
converting those first removes nearly two-thirds of open weak-assertion risk in
one remediation wave.

## Classified Backlog

All findings below are from rule class `test-quality` and rule
`weak-mock-call-count-lower-bound`. Gap classification is `legacy-only gap`
because current forward enforcement intentionally blocks only new/changed test
diffs, not historical assertions already present on `main`.

| Fingerprint | Rule class | Rule id | Location | Subsystem/module | Severity | Gap category |
| --- | --- | --- | --- | --- | --- | --- |
| `957ced271c2a06c5` | `test-quality` | `weak-mock-call-count-lower-bound` | `tests/integration/test_fallback_no_ollama.py:118` | `tests/integration` | medium | `legacy-only gap` |
| `8753adf0aff13cad` | `test-quality` | `weak-mock-call-count-lower-bound` | `tests/integration/test_fallback_no_ollama.py:173` | `tests/integration` | medium | `legacy-only gap` |
| `ed646ffcafd634ba` | `test-quality` | `weak-mock-call-count-lower-bound` | `tests/test_web_organize_routes.py:102` | `tests/web` | medium | `legacy-only gap` |
| `ee074d2d0b7cc083` | `test-quality` | `weak-mock-call-count-lower-bound` | `tests/tui/test_analytics_view_coverage.py:106` | `tests/tui` | medium | `legacy-only gap` |
| `52487eb5fcc51d72` | `test-quality` | `weak-mock-call-count-lower-bound` | `tests/tui/test_audio_view.py:554` | `tests/tui` | medium | `legacy-only gap` |
| `00cd41fbcd87a119` | `test-quality` | `weak-mock-call-count-lower-bound` | `tests/tui/test_audio_view.py:626` | `tests/tui` | medium | `legacy-only gap` |
| `708ffb044865e624` | `test-quality` | `weak-mock-call-count-lower-bound` | `tests/tui/test_methodology_view_coverage.py:140` | `tests/tui` | medium | `legacy-only gap` |
| `382806faa50d3d3c` | `test-quality` | `weak-mock-call-count-lower-bound` | `tests/tui/test_methodology_view_coverage.py:166` | `tests/tui` | medium | `legacy-only gap` |
| `7f0015ad6610bfb8` | `test-quality` | `weak-mock-call-count-lower-bound` | `tests/tui/test_methodology_view_coverage.py:191` | `tests/tui` | medium | `legacy-only gap` |
| `f23f52f1f53d116d` | `test-quality` | `weak-mock-call-count-lower-bound` | `tests/tui/test_methodology_view_coverage.py:209` | `tests/tui` | medium | `legacy-only gap` |
| `2a50d66f8820c8ea` | `test-quality` | `weak-mock-call-count-lower-bound` | `tests/tui/test_methodology_view_coverage.py:239` | `tests/tui` | medium | `legacy-only gap` |
| `db2b05a96b5d0bca` | `test-quality` | `weak-mock-call-count-lower-bound` | `tests/tui/test_methodology_view_coverage.py:260` | `tests/tui` | medium | `legacy-only gap` |
| `baa8a7b54afe6daa` | `test-quality` | `weak-mock-call-count-lower-bound` | `tests/tui/test_methodology_view_coverage.py:277` | `tests/tui` | medium | `legacy-only gap` |
| `816481d1de235764` | `test-quality` | `weak-mock-call-count-lower-bound` | `tests/tui/test_undo_history_view_coverage.py:204` | `tests/tui` | medium | `legacy-only gap` |
| `11636e0c595bf8da` | `test-quality` | `weak-mock-call-count-lower-bound` | `tests/tui/test_undo_history_view_coverage.py:277` | `tests/tui` | medium | `legacy-only gap` |
| `f1eef9e6c7e35513` | `test-quality` | `weak-mock-call-count-lower-bound` | `tests/tui/test_undo_history_view_coverage.py:347` | `tests/tui` | medium | `legacy-only gap` |

## Acceptance-Criteria Check

- [x] Stored first-wave full-repo audit artifact exists.
- [x] Every finding appears in exactly one backlog bucket.
- [x] Backlog totals reconcile exactly to audit totals.
- [x] Every finding is assigned exactly one gap category.
- [x] Backlog includes rule class and fingerprint references for each finding.
