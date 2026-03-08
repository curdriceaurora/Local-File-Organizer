# Measurement Framework — Epic 657

**Date**: 2026-03-08
**Purpose**: Track whether the new anti-pattern rulesets reduce reviewer findings in subsequent PRs.

---

## Baseline Metrics (Pre-Ruleset, from Issue #657 Audit)

| Work Type | Total Findings | Est. PR Count | Findings/PR (baseline) |
|-----------|---------------|---------------|------------------------|
| TEST | 634 | ~40 | **15.9** |
| FEATURE | 590 | ~35 | **16.9** |
| DOCS | 343 | ~20 | **17.2** |
| CI | 84 | ~10 | **8.4** |
| REFACTOR | 35 | ~8 | **4.4** |
| FIX | 142 | ~30 | **4.7** |

**Overall baseline**: 1,830 findings across 115 PRs = **15.9 findings/PR average**

---

## Target Post-Ruleset Metrics

| Work Type | Target Findings/PR | Improvement Goal |
|-----------|-------------------|------------------|
| TEST | ≤ 8 | 50% reduction |
| FEATURE | ≤ 8 | 53% reduction |
| DOCS | ≤ 9 | 48% reduction |
| CI | ≤ 4 | 52% reduction |
| REFACTOR | ≤ 2 | 55% reduction |

**Overall target**: ≤ 8 findings/PR average

---

## Priority Patterns by Expected Impact

| Rank | Pattern | Baseline Count | Why High Impact |
|------|---------|---------------|-----------------|
| 1 | D5 WRONG_FORMAT | 139 | Single `pymarkdown scan` command prevents all 139 |
| 2 | G1 ABSOLUTE_PATH | 53 | Single `git diff --cached | grep` check catches before commit |
| 3 | T1 WEAK_ASSERTION | 54 | Pre-commit self-check question prevents at generation time |
| 4 | D1 INACCURATE_CLAIM | 94 | Source-first discipline enforced in Phase 1 of doc checklist |
| 5 | T2 MISSING_CALL_VERIFY | 93 | "Would test catch uncalled mock?" question at generation time |
| 6 | F4 SECURITY_VULN | 74 | Security boundary checklist before every new route |

---

## Measurement Protocol

### Step 1: Classify New PRs

After each PR review cycle, classify all CodeRabbit + Copilot findings using the classifier prompt.

Run for the next 5 test PRs and 3 feature PRs after this epic merges.

### Step 2: Record in Tracking Table

| PR # | Work Type | Finding Count | Findings/PR | vs Baseline | Notes |
|------|-----------|--------------|-------------|-------------|-------|
| (first post-epic test PR) | TEST | — | — | — | — |
| ... | ... | — | — | — | — |

### Step 3: Compare

After 5 test PRs + 3 feature PRs:
- Calculate average findings/PR for each type
- Compare to baseline (15.9 TEST, 16.9 FEATURE)
- Mark patterns where reduction is evident

### Step 4: Evaluate Ruleset Gaps

For every UNKNOWN finding in new PRs:
- Is it truly new? → Add to appropriate ruleset
- Is it an existing pattern that wasn't caught? → Strengthen the checklist/detection command

---

## Measurement Trigger

This measurement protocol activates when epic/657 merges to main. The first 5 test PRs
and 3 feature PRs after that date become the measurement cohort.

**Target evaluation date**: ~4–6 weeks after merge (time for enough PRs to accumulate)

---

## Ruleset Effectiveness Tracking

| Ruleset | Patterns | Expected Impact | Measurement Status |
|---------|----------|----------------|-------------------|
| test-generation-patterns.md | 20 | 50% reduction in TEST findings | Pending |
| feature-generation-patterns.md | F1–F9 | 53% reduction in FEATURE findings | Pending |
| docs-generation-patterns.md | D1–D7 | 48% reduction in DOCS findings | Pending |
| ci-generation-patterns.md | C1–C6 | 52% reduction in CI findings | Pending |
| code-quality-validation.md (G1–G5) | 5 | Reduces cross-cutting by ~25% | Pending |
