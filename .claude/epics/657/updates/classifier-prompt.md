# PR Finding Classifier Prompt

Use this prompt to classify CodeRabbit/Copilot review findings against the pattern catalog.

---

## Classifier Prompt Template

```
You are classifying a PR reviewer finding against the anti-pattern catalog from epic #657.

Finding text:
"""
{PASTE REVIEWER COMMENT HERE}
"""

PR work type (TEST / FEATURE / DOCS / CI / REFACTOR / FIX): {TYPE}

Classify this finding as one of:

TEST patterns: T1 WEAK_ASSERTION, T2 MISSING_CALL_VERIFY, T3 WRONG_PAYLOAD,
  T4 BROAD_EXCEPTION, T5 GLOBAL_STATE_LEAK, T6 PERMISSIVE_FILTER,
  T7 WRONG_PATCH_TARGET, T8 BRITTLE_ASSERTION, T9 RESOURCE_LEAK,
  T10 DEAD_TEST_CODE, T11+ see memory/test-generation-patterns.md

FEATURE patterns: F1 MISSING_ERROR_HANDLING, F2 TYPE_ANNOTATION, F3 THREAD_SAFETY,
  F4 SECURITY_VULN, F5 HARDCODED_VALUE, F6 API_CONTRACT_BROKEN,
  F7 RESOURCE_NOT_CLOSED, F8 WRONG_ABSTRACTION, F9 DYNAMIC_IMPORT_ANTIPATTERN

DOCS patterns: D1 INACCURATE_CLAIM, D2 STALE_REFERENCE, D3 BROKEN_EXAMPLE,
  D4 MISSING_SECTION, D5 WRONG_FORMAT, D6 CONTRADICTION, D7 SCRIPT_BUG

CI patterns: C1 FLAKY_GATE, C2 WRONG_TRIGGER, C3 CACHE_MISCONFIG,
  C4 COVERAGE_GATE, C5 SECRET_EXPOSURE, C6 SLOW_WORKFLOW

Cross-cutting (any work type): G1 ABSOLUTE_PATH, G2 LOGGING_FORMAT,
  G3 IMPORT_ORDER, G4 UNUSED_CODE, G5 NAMING_CONVENTION

UNKNOWN: does not fit any pattern above

Output format:
Pattern: {ID} {NAME}
Confidence: HIGH / MEDIUM / LOW
Reason: one sentence
```

---

## Batch Classification Command

To classify all findings from a PR in one pass:

```bash
# Fetch all review comments from a PR
gh api repos/curdriceaurora/Local-File-Organizer/pulls/{PR_NUM}/comments \
  --paginate --jq '.[].body' > /tmp/pr-comments.txt

# Count substantive comments (exclude short acknowledgements)
grep -c "." /tmp/pr-comments.txt

# Then paste the file content into the classifier prompt above
```

---

## Recording Results

After classifying, append to the measurement tracking table in `measurement-framework.md`.
