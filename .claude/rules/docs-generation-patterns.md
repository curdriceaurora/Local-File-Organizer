# Docs Generation Anti-Patterns

Reference ruleset for writing documentation that passes PR review without correction.
Sourced from CodeRabbit and Copilot review comments — 343 classified docs findings (115 PRs, issues #84–#655).

**Frequency baseline**: 343 classified findings — ~17 findings per docs PR average.

**Priority by frequency:**

1. D5 WRONG_FORMAT (139) — #1 finding in entire 1,830-finding dataset
2. D1 INACCURATE_CLAIM (94) — #2 finding overall
3. D2 STALE_REFERENCE (65)
4. D4 MISSING_SECTION (36)
5. D6 CONTRADICTION (29)
6. D3 BROKEN_EXAMPLE (~20)

---

## Pre-Generation Checklist (MANDATORY before writing any doc)

- [ ] Run `pymarkdown scan <file>` after writing — must pass before commit (catches D5)
- [ ] Read the actual implementation file BEFORE documenting any method or feature (prevents D1)
- [ ] Copy code examples from actual test files, not from memory (prevents D3)
- [ ] Search for all mentions of the feature before writing — resolve contradictions first (prevents D6)

---

## Pattern D1: INACCURATE_CLAIM — 94 findings (#2 overall)

**What it is**: Documented behavior doesn't match implementation — method/command doesn't exist, parameter name wrong, feature not yet built.

**Bad**:

```markdown
### Using TextProcessor

Call `TextProcessor.extract_text(file_path)` to extract content.
```

*(Method is actually `process_file()`, not `extract_text()`)*

**Good**:

```bash
# BEFORE writing: verify the method exists
grep "def " src/file_organizer/services/text_processor.py
# → def process_file(self, file_path: Path) -> str:
```

```markdown
### Using TextProcessor

Call `TextProcessor.process_file(file_path)` to extract content.
```

**Pre-generation check**: For every method, command, or parameter documented, run `grep "def method_name"` or `grep "command_name"` in the codebase FIRST.

---

## Pattern D2: STALE_REFERENCE — 65 findings

**What it is**: References to removed features, old class names, deprecated APIs, old file paths. Common after refactors.

**Detection**:

```bash
# Find references to old class name
grep -r "OldClassName" docs/
# Find references to moved file
grep -r "old/path/to/module" docs/
```

**Pre-generation check**: Before referencing any existing component, verify it still exists at the path/name you expect.

---

## Pattern D3: BROKEN_EXAMPLE — ~20 findings

**What it is**: Code snippets in docs that don't run — wrong import path, wrong method signature, outdated API.

**Prevention**:

```bash
# Test every code example before committing
python3 -c "
from file_organizer.services.text_processor import TextProcessor
processor = TextProcessor()
# ... example code here
"
```

**Rule**: Copy examples directly from test files. Reference the test file:

```markdown
# Example (from tests/services/test_text_processor.py, line 45)
```

---

## Pattern D4: MISSING_SECTION — 36 findings

**What it is**: Feature exists in code but is completely absent from docs; required parameter not documented.

**Detection**:

```bash
# Find public methods not mentioned in docs
grep "def " src/file_organizer/services/my_service.py | grep -v "^#" | grep -v "__"
# Compare with docs mentions
grep "def_name\|method_name" docs/
```

---

## Pattern D5: WRONG_FORMAT — 139 findings (HIGHEST FREQUENCY IN ENTIRE DATASET)

**What it is**: Markdown lint failures. Every single type of docs PR generates these. Completely preventable by running `pymarkdown scan` before commit.

**Most common sub-violations:**

| Sub-pattern | Count | Example |
|-------------|-------|---------|
| heading-level | high | `#### Subheading` directly under `## Section` (skips h3) |
| blank-lines | high | No blank line before/after code block |
| code-fence | medium | Nested ` ``` ` inside another ` ``` ` block |
| table-format | medium | Misaligned `\|` columns or missing header separator |
| list-indent | lower | Inconsistent indentation in nested lists |

**Fix**: Run `pymarkdown scan <file>` — it lists every violation with line number.

```bash
# Run before every doc commit
pymarkdown scan docs/my-doc.md
# Must show 0 violations before committing
```

**Correct heading hierarchy:**

```markdown
# H1 — document title (one per file)
## H2 — major section
### H3 — subsection
#### H4 — sub-subsection
```

Never skip levels (h2 → h4 is invalid).

**Blank lines around code blocks (required):**

```markdown
Some text here.

\`\`\`python
code here
\`\`\`

Next paragraph.
```

---

## Pattern D6: CONTRADICTION — 29 findings

**What it is**: Two sections of the same doc disagree — e.g., says feature is "complete" in one place and "planned" in another; coverage percentage differs between summary and table.

**Pre-generation check**: After writing each major section, search the document for any contradicting statements:

```bash
grep -n "complete\|planned\|TODO\|not yet\|coming soon" docs/my-doc.md
```

**Rule**: A feature cannot be "✅ Complete" and also "⚠️ Planned for Phase C" in the same document. Resolve before committing.

---

## Pattern D7: SCRIPT_BUG — 4 findings (Phase 1 triage — PR #175)

**What it is**: Shell scripts embedded in documentation have code bugs — wrong regex, missing `read -r`, non-recursive globs, or incorrect variable quoting. Distinct from D3 BROKEN_EXAMPLE (which is about API/import errors); D7 is script logic bugs that won't work as described.

**Bad**:
```bash
# BAD — non-recursive glob misses nested files
for f in /path/to/files/*.py; do ...

# BAD — missing read -r causes backslash interpretation
while read line; do ...

# BAD — unquoted variable causes word splitting
rm -f $MY_VAR

# BAD — wrong regex (forgot to escape dot)
if [[ "$filename" =~ .*\.py ]]; then  # . matches any char
```

**Good**:
```bash
# GOOD — recursive glob with ** and globstar
shopt -s globstar
for f in /path/to/files/**/*.py; do ...

# GOOD — read -r prevents backslash interpretation
while IFS= read -r line; do ...

# GOOD — quoted variable
rm -f "$MY_VAR"

# GOOD — escaped dot in regex
if [[ "$filename" =~ .*\.py$ ]]; then
```

**Pre-generation check**: For every shell script in documentation, run it locally before committing. Use `shellcheck` for automated detection:
```bash
shellcheck your_script.sh
```

---

## Rule of Thumb

Before committing any documentation:

1. **D5**: `pymarkdown scan <file>` — must show 0 violations
2. **D1**: Every method/command documented was verified in source code
3. **D3**: Every code example was copied from a test file and tested locally
4. **D6**: Grep for contradictory status markers and resolve them
5. **D7**: Every shell script in docs passes `shellcheck` locally
