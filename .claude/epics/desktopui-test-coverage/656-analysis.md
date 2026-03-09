---
issue: 656
title: Audit Test-Generation PR Review Comments — Anti-Pattern Ruleset
analyzed: 2026-03-08T02:53:46Z
estimated_hours: 6
parallelization_factor: 2.0
status: closed
updated: 2026-03-09T06:06:50Z
---

# Parallel Work Analysis: Issue #656

## Overview

280 reviewer findings across 7 test PRs are classified. 103/280 are bucketed into 10 named anti-patterns. The remaining 177 (OTHER) need manual triage. Three patterns (WRONG_PATCH_TARGET, BRITTLE_ASSERTION, RESOURCE_LEAK) are confirmed but not yet documented in `memory/test-generation-patterns.md`. A pre-commit checklist and improvement measurement step follow.

## Parallel Streams

### Stream A: OTHER Bucket Triage
**Scope**: Manually sample 40–50 comments from the OTHER bucket in PRs #605 (100 findings) and #635 (49 findings) to surface uncategorized patterns.
**Files**:
- `.claude/epics/desktopui-test-coverage/updates/656/other-bucket-findings.md` (new)
- `memory/test-generation-patterns.md` (append new patterns found)
**Agent Type**: fullstack-specialist
**Can Start**: immediately
**Estimated Hours**: 3
**Dependencies**: none

### Stream B: Pattern Documentation
**Scope**: Add the 3 confirmed-but-undocumented patterns to `memory/test-generation-patterns.md` with before/after examples. These are already evidenced in the frequency table — no triage needed first.
**Files**:
- `memory/test-generation-patterns.md`
**Agent Type**: fullstack-specialist
**Can Start**: immediately
**Estimated Hours**: 1.5
**Dependencies**: none (known patterns are evidence-backed already)

### Stream C: Pre-Commit Checklist
**Scope**: Add a self-check section to `memory/test-generation-patterns.md` (or a new `memory/test-generation-checklist.md`) covering the top 3 root-cause patterns: MISSING_CALL_VERIFY, WEAK_ASSERTION, WRONG_PAYLOAD.
**Files**:
- `memory/test-generation-patterns.md` (new section)
**Agent Type**: fullstack-specialist
**Can Start**: after Stream B completes (needs final pattern list)
**Estimated Hours**: 1
**Dependencies**: Stream B

### Stream D: Improvement Measurement Plan
**Scope**: Define the classifier re-run protocol — how to measure finding rate on the next test PR after ruleset update. Document the baseline (280 findings / 7 PRs = 40/PR avg) and methodology in the issue.
**Files**:
- `.claude/epics/desktopui-test-coverage/updates/656/measurement-plan.md` (new)
**Agent Type**: fullstack-specialist
**Can Start**: immediately
**Estimated Hours**: 0.5
**Dependencies**: none

## Coordination Points

### Shared Files
- `memory/test-generation-patterns.md` — Streams A, B, C all write to this file
  - **Mitigation**: B writes first (known patterns), A appends (new patterns from triage), C adds checklist section last
  - Sequential within the file; A and B can run in parallel on separate sections

### Sequential Requirements
1. Stream B completes → Stream C can finalize checklist (needs complete pattern list)
2. Stream A completes → verify no duplication with Stream B additions

## Conflict Risk Assessment
- **Low Risk**: Stream D works in a separate new file
- **Low Risk**: Stream B works on clearly identified missing sections
- **Medium Risk**: Stream A may surface patterns that overlap with B's additions — review before merging

## Parallelization Strategy

**Recommended Approach**: Hybrid

- Launch Streams A, B, D simultaneously
- Start Stream C when Stream B completes
- Review Stream A output before closing issue (may require additional doc updates)

## Expected Timeline

With parallel execution:
- Wall time: ~3 hours (Stream A is the bottleneck)
- Total work: 6 hours
- Efficiency gain: ~50%

Without parallel execution:
- Wall time: 6 hours

## Priority Order (if sequential)

1. **Stream B** — highest immediate value, known gaps, fast to complete
2. **Stream A** — highest discovery value, surfaces unknown patterns
3. **Stream C** — depends on B; checklist codifies the final ruleset
4. **Stream D** — measurement plan, can be deferred last

## Notes

- PR #605 (100 findings) is the single highest-value target for OTHER bucket triage — 36% of all findings
- MISSING_CALL_VERIFY + WEAK_ASSERTION + WRONG_PAYLOAD = 40% of all findings; root cause is "testing execution, not behavior"
- The checklist (Stream C) should reduce top-3 patterns by requiring mock arg verification on every new test
