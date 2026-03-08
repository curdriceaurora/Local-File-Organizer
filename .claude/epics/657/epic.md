---
name: full-project-pr-review-audit
status: in-progress
created: 2026-03-08T12:40:25Z
updated: 2026-03-08T12:40:25Z
github: https://github.com/curdriceaurora/Local-File-Organizer/issues/657
prd: epic-657
---

# Epic: Full-Project PR Review Audit — Classify All Code-Generation Anti-Patterns

## Overview

A data-driven audit of **1,830 reviewer findings across 115 PRs** to classify every anti-pattern
by work type, quantify frequency, and produce an actionable ruleset that eliminates churn before
it reaches review. 947 findings (52%) are unclassified and represent the primary research target.

## Dataset

- PRs analyzed: 115 (PRs #84–#655)
- Reviewer findings: 1,830 (CodeRabbit + GitHub Copilot)
- Classified: 883 (48%)
- Unclassified: 947 (52%)

## Distribution by Work Type

| Work Type | Findings | % |
|-----------|---------|---|
| TEST      | 634     | 34% |
| FEATURE   | 590     | 32% |
| DOCS      | 343     | 18% |
| FIX       | 142     | 8% |
| CI        | 84      | 5% |
| REFACTOR  | 35      | 2% |

## Phases

1. **Phase 1** — Triage unclassified bucket (PRs #605, #562, #175)
2. **Phase 2** — Update generation rulesets (test, feature, docs, CI, cross-cutting)
3. **Phase 3** — Pre-generation checklists (embedded in Phase 2 tasks)
4. **Phase 4** — Measurement framework

## Priority (by frequency × severity)

1. D5 WRONG_FORMAT (139) — markdown lint before commit
2. D1 INACCURATE_CLAIM (94) — source-first docs discipline
3. T2 MISSING_CALL_VERIFY (93) — mock arg assertions
4. F4 SECURITY_VULN (74) — security boundary checklist
5. F3 THREAD_SAFETY (64) — concurrency checklist
6. F2 TYPE_ANNOTATION (63) — mypy strict from day one

## Tasks Created

- [ ] 001.md — Triage PR #605 (tests, 100 findings) (parallel: true)
- [ ] 002.md — Triage PR #562 (feature, 95 findings) (parallel: true)
- [ ] 003.md — Triage PR #175 (docs, 100 findings) (parallel: true)
- [ ] 004.md — Update test-generation-patterns.md T3–T10 (parallel: true)
- [ ] 005.md — Create feature-generation-patterns.md F1–F8 (parallel: true)
- [ ] 006.md — Update docs generation rules D1–D6 + markdown lint (parallel: true)
- [ ] 007.md — Create ci-generation-patterns.md C1–C6 (parallel: true)
- [ ] 008.md — Update code-quality-validation.md with G1–G5 (parallel: true)
- [ ] 009.md — Incorporate Phase 1 triage into rulesets (depends: 001–008)
- [ ] 010.md — Measurement framework and baseline metrics (depends: 009)

Total tasks: 10
Parallel tasks: 8 (001–008)
Sequential tasks: 2 (009–010)
Estimated total effort: 20–30 hours
