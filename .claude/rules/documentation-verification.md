# Documentation Verification Rule

## Purpose

Prevent documentation errors before they reach code review by verifying that docs match reality and contain valid, tested examples.

## Automated Checks (pre-commit-validation.sh)

The pre-commit validation script includes comprehensive documentation verification that catches:

### 1. **Coverage Gate Claims**
**Check**: Verifies percentage claims match actual CI configuration

- ❌ Detects: "74% CI gate" (outdated)
- ✅ Expects: "95% code coverage" or "95% docstring coverage"
- **Source of Truth**: `pyproject.toml` (`cov-fail-under=95`)

**Why**: Documented CI gates must match actual enforcement, or developers follow wrong targets

### 2. **Method/Function Examples**
**Check**: Validates that documented examples reference actual code

- ❌ Rejects: `TextProcessor.extract_text()` if method doesn't exist in codebase
- ✅ Accepts: Methods verified in `src/` files
- **Source of Truth**: Actual class definitions in codebase

**Why**: Non-existent methods cause copy-paste errors and confusion

### 3. **Contradictory Statements**
**Check**: Detects logical contradictions within same document

- ❌ Rejects: "✅ Complete" AND "0% coverage, not implemented" (same feature)
- ✅ Requires: Consistent status across all mentions
- **Source of Truth**: Status should match coverage and completion state

**Why**: Contradictions mislead readers about actual state

### 4. **Realistic Coverage Percentages**
**Check**: Validates percentage values are within valid range

- ❌ Rejects: "150% coverage" or negative percentages
- ✅ Accepts: 0-100 range only
- **Source of Truth**: Coverage is percentage-based (0-100)

**Why**: Invalid percentages indicate copy-paste errors or misunderstanding

### 5. **Section Categorization**
**Check**: Verifies entries match their section labels

- ❌ Rejects: "Medium Coverage (70-89%)" section with 52% or 91% entries
- ✅ Accepts: All entries within stated range
- **Source of Truth**: Section header defines acceptable range

**Why**: Mismatched categorization confuses readers about significance

### 6. **Feature Claims**
**Check**: Validates features mentioned in docs actually exist

- ❌ Rejects: "Coverage badges in README" if README doesn't have them
- ✅ Accepts: Claims only for features that exist
- **Source of Truth**: Actual README.md or codebase

**Why**: False claims about features waste time and create confusion

### 7. **Configuration References**
**Check**: Validates referenced config files exist

- ❌ Rejects: References to `.github/workflows/ci.yml` if file doesn't exist
- ✅ Accepts: Only references to actual files
- **Source of Truth**: Actual files in repository

**Why**: Broken references break documentation's utility

## Manual Verification Checklist

Before committing documentation changes, manually verify:

### Accuracy Checks

- [ ] **Coverage Thresholds**
  - CI gate is 95% (code) and 95% (docstrings)
  - Matches `pyproject.toml --cov-fail-under`
  - PR vs main behavior differs (PR doesn't enforce)

- [ ] **Method/Class Examples**
  - All methods exist in codebase
  - All class names are correct
  - Copy examples from actual test files
  - Run examples locally to verify they work

- [ ] **CI/CD Behavior**
  - PRs run `-m "ci"` tests only (no coverage gate)
  - Main pushes enforce 95% coverage gate
  - Workflows match actual `.github/workflows/ci.yml`

- [ ] **Metrics Consistency**
  - Summary percentages match detailed metrics
  - Coverage ranges have no outliers
  - All percentages are 0-100

### Completeness Checks

- [ ] **No Contradictions**
  - Feature can't be "complete" and "0% coverage"
  - Module can't be "implemented" and "not implemented"
  - Status must match reality

- [ ] **Claims Verified**
  - "Coverage badges in README" → README has them
  - "Tests for feature X" → tests actually exist
  - "90% module coverage" → code shows 90%

- [ ] **References Valid**
  - Config file paths exist
  - Link targets exist
  - Workflow names match actual workflows

### Clarity Checks

- [ ] **Distinguish Metrics**
  - Docstring coverage vs code coverage (they're different!)
  - CI gate enforcement vs current measurements
  - Phase A/B coverage vs Phase C (deferred)

- [ ] **Document Context**
  - Why changed? (not just what changed)
  - What's the source of truth? (file/config reference)
  - What can change? (vs what's stable)

## Common Issues & Fixes

### Issue: "Coverage from 12% to 96.8%"
**Problem**: Ambiguous - is it code or docstrings?
**Fix**: "Docstring coverage from 12% to 96.8%"

### Issue: "74% CI gate"
**Problem**: Outdated - actual is 95%
**Fix**: Check `pyproject.toml`, update to actual value

### Issue: Method doesn't exist
**Problem**: Copy-pasted from memory or different project
**Fix**: Grep codebase for actual method, use real example

### Issue: "Medium Coverage (70-89%)" contains 52% entry
**Problem**: Mismatched categorization
**Fix**: Move 52% to "Low Coverage (<70%)" section

### Issue: "✅ Complete" + "0% coverage"
**Problem**: Contradictory
**Fix**: Either mark as deferred OR implement it

## Implementation in Workflow

### Before Creating PR

1. **Run automated checks:**
   ```bash
   bash .claude/scripts/pre-commit-validation.sh
   ```

2. **Manual verification:**
   - Go through checklist above
   - Verify against source files
   - Test code examples

3. **Ask critical questions:**
   - Is every percentage claim verified against actual code/config?
   - Does every code example actually exist and work?
   - Are there contradictions between sections?
   - Does my summary match the detailed findings?

### After Review Comments

If reviewers flag documentation issues:

1. **Don't assume they're wrong** - verify against source
2. **Apply the fix upfront** - don't iterate back-and-forth
3. **Update checklist if needed** - if review caught something new, add to this list

## Benefits

✅ **Prevents churn**: Catches issues locally before code review
✅ **Saves time**: No iterative back-and-forth on accuracy
✅ **Improves quality**: Documentation users trust the accuracy
✅ **Reduces confusion**: Clear metrics and consistent statements
✅ **Maintains credibility**: Claims that are verified

## Key Principles

1. **Verify claims against reality** - Don't assume, check actual code/config
2. **Test examples before documenting** - Copy from real test files
3. **Consistency matters** - Contradiction confuses readers
4. **Source of truth is code** - Docs must match, not vice versa
5. **Clarity over brevity** - Distinguish docstring vs code coverage
6. **Completeness** - All claims have supporting evidence

## Related Rules

- `.claude/rules/code-quality-validation.md` - Code verification patterns
- `.claude/rules/quick-validation-checklist.md` - Quick reference
- `.claude/scripts/pre-commit-validation.sh` - Automated enforcement
- `CLAUDE.md` - Project standards

---

**Last Updated**: 2026-03-07
**Status**: Active enforcement in pre-commit-validation.sh
