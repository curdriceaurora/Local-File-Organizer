# Documentation Generation Checklist

**Purpose**: Prevent documentation errors BEFORE writing, not after verification.

## Phase 1: Pre-Writing Discovery (MANDATORY)

Before writing ANY documentation, complete these discovery steps:

> **D1 Rule** (94 findings — #2 in dataset): Read the actual implementation file BEFORE writing any claim about a method, command, or feature. Never document from memory.

### Step 1A: Identify All Source of Truth

For any claim you plan to make, identify where it's verified in actual code:

| Type of Claim | Source of Truth | How to Verify |
|---------------|-----------------|---------------|
| Coverage gates | `pyproject.toml` | `grep cov-fail-under` |
| CI behavior | `.github/workflows/ci.yml` | Read actual workflow |
| Method exists | `src/file_organizer/...` | `grep "def method_name"` or `ast-grep` |
| Feature exists | Actual codebase | `ls`, `grep`, or test imports |
| Threshold/limit | Code config files | Check actual values |
| Integration points | Integration tests | Read actual test setup |
| Any method/feature claim | `src/file_organizer/` | `grep "def method_name"` or `rg "class ClassName"` |

**Rule**: If you can't find it in source, don't claim it.

### Step 1B: Extract Actual Values (Don't Assume)

Never assume values - always extract from source:

**❌ Wrong approach:**
```
"I remember the coverage gate is... probably 95%"
→ Write "95% CI gate"
```

**✅ Right approach:**
```bash
grep cov-fail-under pyproject.toml
→ Confirm "95" in output
→ Write "95% code coverage gate (enforced via pytest --cov-fail-under=95)"
```

### Step 1C: Verify Method Examples Exist

**Before** writing ANY code example:

```bash
# Search for actual method
rg "def extract_text|def process_file" src/file_organizer/

# Read the actual implementation
cat src/file_organizer/services/text_processor.py | grep -A 5 "def process_file"

# Check method signature
ast-grep --pattern 'def process_file($$$)' --lang python src/

# Verify in test files
grep -l "process_file" tests/**/*.py
```

**Rule**: Copy method signatures from actual code, not memory.

### Step 1D: Document Contradictions Upfront

Before writing, list any statements that could contradict:

```markdown
## Pre-write Contradiction Check

Claim 1: "Updater module is complete"
- Source: [cite evidence]
- Coverage: Check if truly 0% or incomplete

Claim 2: "0% coverage, not implemented"
- Source: [cite evidence]
- Status: Check actual implementation

Decision: [Choose which is true, justify]
```

**Rule**: Can't claim "complete" AND "0% coverage" for same feature.

### Step 1E: Validate Section Ranges

If creating categorized tables, decide ranges FIRST:

```markdown
## Coverage Categorization (BEFORE WRITING)

- High Coverage: 90-100%
- Medium Coverage: 70-89%
- Low Coverage: 50-69%
- Very Low Coverage: 0-49%

[List all modules and assign to ranges]
[Verify NO OUTLIERS exist in wrong section]
```

**Rule**: Define ranges, then validate every entry matches.

### Step 1F: List Feature Claims to Verify

Before mentioning any feature, create a verification list:

```markdown
## Claims to Verify (BEFORE WRITING)

- [ ] "Coverage badges in README" → Check README.md
- [ ] "Tests for feature X" → Find actual test files
- [ ] "90% module coverage" → Verify against coverage report
- [ ] "CI gate enforces 95%" → Verify against .github/workflows/ci.yml
```

**Rule**: Every claim gets a checkbox and source before finalizing.

---

## Phase 2: Writing With Embedded Checks

### Guideline 2A: Use Source-First Writing

**For every section, follow this order:**

1. **Read actual source code** (pyproject.toml, workflows, src/, tests/)
2. **Extract real values** (don't paraphrase, quote actual code)
3. **Create examples from test files** (copy, don't recreate)
4. **Document only what exists** (no assumptions)

**Example:**
```markdown
# BAD: Written from memory
The CI gate ensures at least 74% coverage on PRs.

# GOOD: Written from source
The CI gate enforces 95% code coverage via:
- pytest --cov-fail-under=95 (from pyproject.toml, line XX)
- Applied on main branch pushes only
- PRs run limited suite via: pytest -m "ci" (no coverage threshold)
```

### Guideline 2B: Embed Verification into Examples

When documenting a method, include verification:

```markdown
## TextProcessor.process_file()

[VERIFIED in: src/file_organizer/services/text_processor.py, lines XX-YY]
[TESTED in: tests/services/test_text_processor.py]

### Example
[COPIED from actual test: tests/services/test_text_processor.py, line ZZ]

def test_text_processor(tmp_path):
    processor = TextProcessor()
    test_file = tmp_path / "test.txt"
    test_file.write_text("Sample content")
    result = processor.process_file(test_file)  # ✓ Real method, tested
    assert result is not None
```

**Rule**: Every code example should reference actual test file it came from.

### Guideline 2C: Create Contradiction Detection Checkpoints

After major sections, stop and check:

```markdown
## ✓ Contradiction Check (Every 3-4 sections)

Does this section contradict anything above?
- Does it claim "complete" when "0% coverage" elsewhere?
- Does it reference methods that don't exist?
- Does it claim features already marked "not implemented"?

Current contradictions found: [list]
Resolved: [yes/no]
```

### Guideline 2D: Validate Section Entry Membership

After writing each categorized section, verify:

```markdown
## Coverage Categories - VERIFICATION

### Medium Coverage (70-89%) ✓ VERIFIED
- routers/auth: 85% ✓ (in range)
- routers/search: 86% ✓ (in range)
- middleware: 84% ✓ (in range)

### High Coverage (90%+) ✓ VERIFIED
- utils: 90% ✓ (in range)
- models: 97% ✓ (in range)

Outliers found: 0
Status: ✓ All entries verified
```

**Rule**: Don't publish section until every entry is verified.

### Guideline 2E: Run Live Checks as You Write

**Use grep/ast-grep to verify claims in real-time:**

```bash
# Before claiming method exists:
rg "def extract_text" src/ || echo "METHOD DOES NOT EXIST"

# Before claiming feature in README:
grep -i "coverage.*badge" README.md || echo "NOT IN README"

# Before claiming CI gate:
grep "cov-fail-under" pyproject.toml || echo "NOT ENFORCED"
```

**Rule**: Keep terminal open, verify each claim immediately.

---

## Phase 3: Pre-Finalization Review

### Step 0 (MANDATORY — run FIRST): Markdown Lint Validation

```bash
# Run pymarkdown on every .md file you modified
pymarkdown scan <your-doc-file.md>
```

- **Zero violations required** before proceeding to commit
- This catches D5 WRONG_FORMAT — the #1 finding across the entire 1,830-finding dataset (139 occurrences)
- Common violations: heading level skips, missing blank lines around code blocks, nested code fences
- Auto-fix most issues: fix heading levels manually; add blank lines around code blocks; remove nested fences

### Checklist 3A: Complete Source Verification

Before submitting documentation:

```markdown
## Final Source Verification Checklist

- [ ] Every percentage claim has a line number reference
  Example: "95% code coverage (pyproject.toml:42, cov-fail-under=95)"

- [ ] Every method example comes from actual test file
  Example: "from tests/services/test_text_processor.py, line 125"

- [ ] Every feature claim references actual file
  Example: "Coverage badge shown in README.md, line 15"

- [ ] No contradictions exist
  - Checked: "complete" vs "0% coverage"
  - Checked: "implemented" vs "not implemented"
  - Checked: "feature exists" vs "planned for Phase C"

- [ ] All section ranges verified
  - Extracted all entries
  - Checked each against section range
  - Found and resolved outliers

- [ ] All config references exist
  - Verified .github/workflows/ci.yml exists
  - Verified pyproject.toml sections exist
  - Verified referenced files are current

- [ ] All code examples tested
  - Run example locally
  - Verified against actual codebase
  - Confirmed methods exist
```

### Checklist 3B: Consistency Review

```markdown
## Internal Consistency Checklist

- [ ] Summary matches detailed findings
- [ ] All percentages are in valid range (0-100)
- [ ] Status is consistent (can't be "complete" and "0%")
- [ ] Feature claims match actual implementation
- [ ] CI behavior description matches actual workflow
- [ ] Method examples match actual codebase
- [ ] Links target actual files
- [ ] Metrics align (docstring vs code coverage distinguished)
```

---

## Phase 4: AI/Human Prompt Template

When asking AI to generate documentation:

```markdown
# Documentation Generation Request

## Pre-Writing Requirements (MUST COMPLETE FIRST)

1. **Source of Truth Verification**
   - Coverage gate: Check pyproject.toml for cov-fail-under value
   - CI behavior: Read .github/workflows/ci.yml for actual gates
   - Methods: Grep src/ for actual method signatures
   - Features: Verify in actual codebase

2. **Extract Actual Values**
   - Don't assume values—extract them
   - Reference line numbers and actual config
   - Quote from actual source when possible

3. **Example Sourcing**
   - Every code example must come from actual test files
   - Include file path and line number
   - Verify the example actually runs

4. **Contradiction Prevention**
   - List any claims that could contradict
   - Resolve before writing
   - Document the resolution

## Writing Guidelines

- Use source-first approach: Read code FIRST, then document
- Include verification tags: [VERIFIED in: file:linenum]
- Reference actual examples: [FROM: test_file.py:linenum]
- Validate section membership: [IN RANGE: 70-89%]
- Embed consistency checks every 3-4 sections

## Pre-Submission Validation

Before finalizing:
- [ ] Every numerical claim has a source reference
- [ ] Every code example is from actual test files
- [ ] Every feature claim references actual code
- [ ] No contradictions detected
- [ ] All section entries match their ranges
- [ ] All links point to actual files

## Output Format

Include verification metadata:

\`\`\`markdown
# Testing Guide

[VERIFIED SOURCES]
- Coverage gate: pyproject.toml, line 42 (cov-fail-under=95)
- CI workflow: .github/workflows/ci.yml
- Examples from: tests/services/test_text_processor.py

[CONTRADICTIONS CHECK]
No internal contradictions detected

[SECTION RANGES]
All coverage entries verified to match stated ranges
\`\`\`
```

---

## Prevention Summary

### Root Cause Analysis

| Error | Root Cause | Prevention |
|-------|-----------|-----------|
| 74% vs 95% gates | Didn't verify actual config | Run `grep cov-fail-under` first |
| Non-existent methods | Assumed from memory | `grep "def method_name"` before writing |
| Contradictions | Didn't read full document | Contradiction checklist before writing |
| Wrong categories | Didn't validate ranges | Validate each entry against range |
| False feature claims | Assumed features exist | Check actual README/code before claiming |

### Prevention Workflow

```
Write Request
    ↓
Phase 1: Discovery (extract all sources)
    ↓
Phase 2: Source-first writing (read code, then document)
    ↓
Phase 3: Pre-finalization review (verify all claims)
    ↓
Phase 4: Run automated validation
    ↓
Submit Documentation
```

### Key Principle

**"Never generate a documentation claim without first verifying it in actual source code."**

This prevents 90% of documentation errors from being generated in the first place.

---

## Integration with Pre-Commit Validation

- **Generation time**: Use this checklist while writing
- **Commit time**: Automated validation in pre-commit-validation.sh catches anything missed
- **Together**: Prevents errors from being written + catches any that slip through

**Target**: Zero documentation corrections in code review.

---

**Last Updated**: 2026-03-07
**Status**: Active enforcement via checklist + pre-commit validation
