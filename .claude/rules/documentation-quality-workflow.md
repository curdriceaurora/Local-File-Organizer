# Documentation Quality Workflow

**Goal**: Zero documentation errors in code review through prevention-first approach.

## Quick Reference: Prevention → Verification

```
┌─────────────────────────────────────────────────────────────┐
│ START: Document Generation Task                             │
└────────────────────────┬────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────┐
│ PHASE 1: Generation Checklist                               │
│ .claude/rules/documentation-generation-checklist.md         │
│                                                              │
│ Before writing ANYTHING:                                    │
│ ✓ Find source of truth (pyproject.toml, workflows, src/)   │
│ ✓ Extract actual values (grep, ast-grep)                   │
│ ✓ Verify methods exist (before documenting)                │
│ ✓ List contradictions upfront (resolve before writing)     │
│ ✓ Validate section ranges (define, then check)             │
│ ✓ Create verification list (every claim gets checkbox)      │
└────────────────────────┬────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────┐
│ PHASE 2: Write Documentation                                │
│ Use source-first approach                                   │
│                                                              │
│ For each section:                                           │
│ 1. Read actual source code                                  │
│ 2. Extract real values (don't assume)                       │
│ 3. Copy examples from test files                            │
│ 4. Include verification tags [VERIFIED in: file:linenum]    │
│ 5. Check contradictions every 3-4 sections                  │
│ 6. Validate section membership                              │
│ 7. Run live verification (grep/ast-grep in real-time)       │
└────────────────────────┬────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────┐
│ PHASE 3: Pre-Submission Review                              │
│                                                              │
│ Complete checklist:                                         │
│ ✓ Every claim has source reference                          │
│ ✓ Every example from actual test file                       │
│ ✓ Every feature claim verified                              │
│ ✓ No contradictions                                         │
│ ✓ All section entries match ranges                          │
│ ✓ All links point to actual files                           │
└────────────────────────┬────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────┐
│ PHASE 4: Pre-Commit Validation (AUTOMATED)                  │
│ bash .claude/scripts/pre-commit-validation.sh               │
│                                                              │
│ Runs:                                                       │
│ ✓ Coverage gate verification (74% → 95%)                    │
│ ✓ Method example validation                                 │
│ ✓ Contradiction detection                                   │
│ ✓ Percentage range checks                                   │
│ ✓ Section categorization                                    │
│ ✓ Feature claim verification                                │
│ ✓ Config reference validation                               │
│ ✓ Markdown linting                                          │
│ ✓ Link validation                                           │
└────────────────────────┬────────────────────────────────────┘
                         ↓
           ┌─────────────┴──────────────┐
           ↓                            ↓
      PASSES              ❌ FAILS (Fix and retry)
           ↓                            ↓
           ↓         ┌──────────────────┘
           ↓         ↓
           ├─────────┤
           ↓
┌─────────────────────────────────────────────────────────────┐
│ PHASE 5: Commit & Push                                      │
│                                                              │
│ git add <doc-files>                                         │
│ git commit -m "docs: [description]"                         │
│ git push origin <branch>                                    │
└────────────────────────┬────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────┐
│ RESULT: Code Review (Should be zero findings!)              │
│                                                              │
│ If reviewer finds issues:                                   │
│ ✓ You missed something (both checklists should prevent it)  │
│ ✓ Fix and re-run both checklists before pushing again       │
│ ✓ Update checklists if new pattern discovered              │
└─────────────────────────────────────────────────────────────┘
```

---

## The Two Checklists

### 1. Generation Checklist (PREVENTION)
**File**: `.claude/rules/documentation-generation-checklist.md`
**When**: While writing documentation
**Goal**: Prevent errors from being generated

**Key Phases**:
- Phase 1: Pre-writing discovery (verify all sources)
- Phase 2: Writing with embedded checks (source-first approach)
- Phase 3: Pre-finalization review (comprehensive validation)
- Phase 4: AI prompt template (guidance for doc requests)

**Key Questions**:
- Where is this value in actual code/config?
- Does this method actually exist?
- Does this contradict anything I wrote earlier?
- Is this entry in the right section?
- Is this feature actually implemented?

### 2. Verification Checklist (CATCHING ERRORS)
**File**: `.claude/rules/documentation-verification.md`
**When**: During pre-commit validation (automated) + manual review
**Goal**: Catch any errors that slipped through generation

**Automated Checks**:
- Coverage gate claims vs actual config
- Method examples vs codebase
- Contradictions vs logic
- Percentages vs valid ranges
- Section categorization vs content
- Feature claims vs reality
- Config references vs actual files

**Manual Checks** (if needed):
- Summary vs details match?
- All links valid?
- All examples tested?
- Any contradictions?

---

## Common Documentation Errors & Prevention

| Error | Generation Prevention | Verification Catch |
|-------|----------------------|-------------------|
| "74% CI gate" | Run `grep cov-fail-under` BEFORE writing | Auto-check: detects "74%" |
| `TextProcessor.extract_text()` | Run `grep "def extract_text"` BEFORE writing | Auto-check: validates methods exist |
| "Complete" + "0% coverage" | List contradictions BEFORE writing | Auto-check: contradiction detection |
| "Medium (70-89%)" with 52% | Validate entry BEFORE adding | Auto-check: range validation |
| "Coverage badges in README" | Check README BEFORE claiming | Auto-check: feature verification |
| Breaking code examples | Copy from test files, not memory | Auto-check: part of doc verification |

---

## Implementation Checklist

To implement this workflow on a project:

### Setup Phase

```bash
# 1. Add generation checklist
cp .claude/rules/documentation-generation-checklist.md <project>

# 2. Add verification checklist
cp .claude/rules/documentation-verification.md <project>

# 3. Update pre-commit-validation.sh with section 7a-3
# (Already done in this project)

# 4. Create quick reference (this file)
cp .claude/rules/documentation-quality-workflow.md <project>

# 5. Onboard team
# Show: generation checklist (how to write docs right)
# Show: verification checklist (what automation catches)
# Show: workflow (the full process)
```

### Per-Document Workflow

```bash
# 1. Start document task
# Read: .claude/rules/documentation-generation-checklist.md
# Complete: Phases 1-3

# 2. Write documentation
# Use: source-first approach
# Embed: verification tags

# 3. Before committing
bash .claude/scripts/pre-commit-validation.sh
# Should see: "✓ Documentation content verification passed"

# 4. Commit
git add <doc-files>
git commit -m "docs: [description]"
```

---

## Expected Results

### With Both Checklists

**Before**: PR #642 had 24+ Copilot findings + CodeRabbit findings
- 74% vs 95% gates
- Non-existent method examples
- Contradictory statements
- Mismatched section categorization
- False feature claims

**After**: Documentation errors prevented during writing
- Generation checklist catches issues BEFORE writing
- Pre-commit validation catches anything missed
- Code review has zero documentation findings

### Metrics

| Metric | Before | After |
|--------|--------|-------|
| Doc errors in review | 24+ | 0 |
| Review iterations needed | 3+ | 1 |
| Time to merge | 2+ hours | 30 min |
| Author confidence | Low | High |

---

## Key Principles

1. **Prevention > Verification**
   - Better to prevent errors during writing
   - Verification catches mistakes, prevention stops them

2. **Source-First Documentation**
   - Read actual code FIRST
   - Then document SECOND
   - Never document from memory

3. **Every Claim Needs a Source**
   - "95% coverage" → pyproject.toml:42
   - "process_file() method" → src/.../file.py:123
   - "Coverage in README" → README.md:45

4. **Automated + Manual**
   - Automated: catches known patterns
   - Manual: catches contextual errors
   - Together: comprehensive coverage

5. **Shift Left**
   - Prevention (during writing) > Verification (pre-commit)
   - Pre-commit > Code review
   - Earliest point catches most issues

---

## For AI/Claude Code Users

When asking for documentation generation:

```markdown
Use this workflow:
1. Complete documentation-generation-checklist.md Phases 1-3
2. Follow "source-first writing" approach
3. Include verification metadata
4. Run pre-commit-validation.sh
5. Only commit if validation passes

This ensures zero documentation errors in code review.
```

---

## References

- `.claude/rules/documentation-generation-checklist.md` - How to write docs correctly
- `.claude/rules/documentation-verification.md` - What automated validation checks
- `.claude/scripts/pre-commit-validation.sh` - Automated enforcement (section 7a-3)
- `CLAUDE.md` - Project-wide standards

---

**Last Updated**: 2026-03-07
**Status**: Active enforcement
**Goal**: Zero documentation errors in code review
