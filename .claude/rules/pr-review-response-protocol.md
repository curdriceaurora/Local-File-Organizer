# PR Review Response Protocol

**Purpose**: Eliminate iterative churn by extracting all findings upfront and fixing them in a single pass.

## Core Principle

**Do not iterate one comment at a time.** Extract ALL findings upfront, fix all of them locally in a single pass, then push once. Iterative monitoring loops cause churn.

---

## Step 1: Extract All Findings Upfront (Mandatory GraphQL Sourcing)

**CRITICAL**: Comments MUST be sourced via GraphQL, not gh CLI. The `gh` CLI cannot retrieve all review threads reliably.

### 1A: Fetch All Comments Using GraphQL

```bash
TOKEN=$(gh auth token)

curl -s -X POST https://api.github.com/graphql \
  -H "Authorization: token $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "{ repository(owner: \"OWNER\", name: \"REPO\") { pullRequest(number: PR_NUM) { reviews(first: 50) { nodes { author { login } state comments(first: 100) { nodes { body path line } } } } } } }"
  }' | jq '.data.repository.pullRequest.reviews.nodes[] | {author: .author.login, state, comments: .comments.nodes[]}'
```

Save complete output to file for reference.

### 1B: Organize All Findings

1. **Read ALL comments in one session** (don't monitor incrementally)
2. **Extract from ALL reviewers**: CodeRabbit, Copilot, human reviewers
3. Copy each comment verbatim into a temporary checklist (e.g., `/tmp/pr-findings.txt`)
4. **Document the thread IDs** for later resolution via GraphQL (see Step 6)
5. Do NOT start fixing until you have the complete list
6. **Scope is frozen at this point**: If new comments arrive while you're fixing, complete the current batch and treat new findings as a separate PR review cycle
7. Example: "Found 5 issues: #1 (thread-ID-1) mock mismatch, #2 (thread-ID-2) weak assertion..."

---

## Step 2: Verify Each Finding Against Current Code

For each comment, decide what action to take using this decision matrix:

### Decision Matrix

**APPLY** - Fix this in the current PR
- Finding is clearly valid and actionable
- Belongs in this PR (not separate work)
- Include in Step 3 fixes

**SKIP** - Don't fix this
- Finding is invalid or already addressed
- Reply to reviewer: Explain why it's skipped (e.g., "Already added in commit ABC")
- Mark thread as addressed

**CLARIFY** - Don't understand the concern
- Reviewer's intent is unclear
- Reply asking for clarification
- Continue with other fixes while waiting for response
- Return to Step 2 when you get clarification

**DEFER** - Valid but belongs in separate PR
- Finding is valid but too complex or out of scope
- Create GitHub issue with exact details from reviewer's comment
- Reply to reviewer: "Valid point, created issue #XXX for this"
- Don't include in current PR

### Verification Process

For each finding:

1. Locate the exact code line mentioned
2. Read the implementation being tested
3. Verify if the finding is actually valid or already fixed
4. Document your decision: "Issue #2 (weak assertion) - APPLY: assertion only checks text exists, should verify full plan structure"
5. Categorize as APPLY, SKIP, CLARIFY, or DEFER using the matrix above

---

## Step 3: Apply All Valid Fixes in One Local Pass

1. **NO pushing between fixes** — batch all changes locally
2. Fix all APPLY items in the order they appear
3. For each fix:
   - Update the code
   - Verify locally by running applicable unit tests for that change
   - Don't push yet
4. Don't push until ALL APPLY fixes are applied

### Verification by Fix Type

- **Test code changes**: Run the specific test file
- **Implementation changes**: Run unit tests for that module
- **Config/environment changes**: Manual verification or related tests
- **Linting/style fixes**: Syntax check is sufficient

### Call-Site Verification (REQUIRED for security/validation fixes)

When the fix adds a validation guard (e.g., `__setattr__`, `__post_init__`, input sanitization,
path-traversal check), the fix is only complete if ALL call sites respect the invariant — not just
the file you edited.

Before marking a security/validation fix done:

```bash
# 1. Find every place in src/ that touches the validated field/method
rg "context\.category\s*=|context\.filename\s*=" src/ --type py
rg "_active_models\[" src/ --type py

# 2. For each result: does the assignment go THROUGH the validated path,
#    or does it bypass it (e.g., via object.__setattr__, direct dict store, etc.)?

# 3. Only reply "✅ Fixed" after verifying ALL call sites pass through the guard.
```

**Root cause of PR #749 re-review cycle**: `StageContext.__post_init__` was added but
`analyzer.py` and `preprocessor.py` assigned `context.category = ...` directly after
construction, bypassing `__post_init__`. The fix was incomplete. Call-site verification
would have caught this before push.

---

## Step 4: Run Quality Gate Sequence

Execute in order (fail fast — cheap checks first):

```bash
# Step 4a: Pre-commit validation (REQUIRED — deterministic, fast)
bash .claude/scripts/pre-commit-validation.sh

# Step 4b: Code reviewer (REQUIRED — logic, design, consistency)
/code-reviewer

# Step 4c: Simplify (OPTIONAL — run when touching shared utilities or extractable helpers)
/simplify

# Step 4d: Audit (OPTIONAL — run when touching auth, file paths, or new public APIs)
/audit
```

### Quality Gate Expectations

**If /code-reviewer is unavailable**: Hard blocker — cannot proceed without it

**If /simplify or /audit is unavailable**: Skip and proceed.

**If /code-reviewer suggests refactoring**: Include it in this PR (don't defer)
- It's part of the quality gate validation
- Incorporate the suggestions into your fixes
- Re-run validation after refactoring

**If pre-commit validation fails**:
1. Review the failures (lint, type, format, test issues)
2. Auto-fix what's fixable (e.g., `ruff format . --fix`)
3. Manually fix what needs investigation
4. Re-run validation
5. Repeat until it passes
6. Do NOT proceed to Step 5 until validation passes

---

## Step 5: Commit and Push Once

```bash
git add <all fixed files>
git commit -m "fix: address PR review findings

- [Finding 1 description]: [how you fixed it]
- [Finding 2 description]: [how you fixed it]
- [Finding N description]: [how you fixed it]"

git push origin <branch>
```

### Commit Message Guidelines

- **Format**: Start with `fix: address PR review findings`
- **Body**: List each APPLY finding with:
  - What the reviewer found
  - How you fixed it
- **Not included**: SKIP, CLARIFY, or DEFER items (those are handled separately as replies on the PR)
- **Length**: Concise but specific - reviewers should understand what was changed and why

---

## Step 5B: Resolve Review Threads (Automated)

**CRITICAL**: After pushing fixes, ALL review threads related to APPLY findings MUST be marked as resolved. Use the automated script instead of manual commands.

### Why This is Required

- Marking threads as resolved indicates findings have been addressed
- Reviewers check thread resolution status to gauge PR readiness
- Without resolution, threads stay open and create noise
- Automated script eliminates manual GraphQL mutations and repetition

### Automated Resolution via Script

Use the dedicated script that automates the entire thread resolution process:

```bash
.claude/scripts/resolve-pr-threads.sh <PR_NUMBER> --replies <replies.json>
```

**The script handles:**
1. ✅ Fetching all unresolved threads
2. ✅ Adding your replies to each thread (optional)
3. ✅ Resolving all threads via GraphQL
4. ✅ Reporting summary of resolved threads

### Quick Start: Three Usage Patterns

**Pattern 1: Resolve without replies**
```bash
.claude/scripts/resolve-pr-threads.sh 627
```

**Pattern 2: Resolve with replies from JSON**
```bash
# Create replies.json with your responses
cat > replies.json << 'EOF'
{
  "THREAD_ID_1": "✅ Fixed: Description of fix",
  "THREAD_ID_2": "✅ Fixed: Another fix"
}
EOF

.claude/scripts/resolve-pr-threads.sh 627 --replies replies.json
```

**Pattern 3: Preview before executing (dry-run)**
```bash
.claude/scripts/resolve-pr-threads.sh 627 --replies replies.json --dry-run
```

### Example Workflow

```bash
# 1. Make all fixes locally
# 2. Commit and push
git push origin my-branch

# 3. Create replies.json with your responses (optional)
# 4. Resolve all threads with the script
.claude/scripts/resolve-pr-threads.sh 627 --replies replies.json

# 5. All threads now resolved with your replies visible
```

### Documentation

For complete documentation, examples, and troubleshooting:
- See: `.claude/scripts/THREAD_RESOLUTION_GUIDE.md`
- Template: `.claude/scripts/example-replies.json`

---

## Step 6: Verify PR is Ready (No Iterative Loops)

After Steps 1-5B are complete (commit pushed, threads resolved via script), do NOT:
- ❌ Create background scripts to monitor review status
- ❌ Iteratively fix issues as they appear in re-review
- ❌ Push partial fixes and hope for the best
- ❌ Monitor and wait for CI/review feedback to guide next fixes

Instead:
- ✅ Trust that running quality gates locally caught issues before pushing (Step 4)
- ✅ Trust that the automated script properly resolved all threads (Step 5B)
- ✅ Verification comes from local testing and thread resolution, not iterative PR reviews
- ✅ PR review feedback should be minimal if quality gates and thread resolution ran properly

### Verification Checklist (Steps Complete)

After completing all steps of this protocol:

- [x] Step 1: All findings extracted and categorized
- [x] Step 2: Each finding verified against code
- [x] Step 3: All APPLY fixes applied locally
- [x] Step 4: All quality gates passed (pre-commit → code-reviewer → simplify)
- [x] Step 5: Commit created and pushed
- [x] Step 5B: Threads resolved via automated script (with optional replies)
- [x] Step 6: This verification

### PR Status After Protocol Completion

Once all steps complete, the PR should have:
- ✅ Fresh CI run triggered (after push)
- ✅ All review threads resolved (showing address of findings)
- ✅ Consolidated comment with fixes (if replies used in Step 5B)
- ✅ Code quality gates previously validated locally
- ⏳ Awaiting CI completion and reviewer approval

**Expected outcome**: Minimal additional review feedback, clean merge when CI passes.

If CI fails or new issues appear despite quality gates passing, treat as a NEW PR review cycle (return to Step 1).

### Summary of Required Actions

| Step | Action | Tool |
|------|--------|------|
| 1A | Extract comments | GraphQL query |
| 1B | Document threads | Manual organization |
| 2 | Verify findings | Manual code review |
| 3 | Apply fixes | Git |
| 4 | Run quality gates | Bash/CLI |
| 5 | Commit & push | Git |
| 5B | Resolve threads | GraphQL mutation |
| 6 | Wait for approval | Monitor (no loops) |

---

## What This Avoids

### Bad Pattern (causes churn)

```text
Push initial code
→ Wait for CodeRabbit comments
→ Find comment #1, fix it, push
→ Find comment #2, fix it, push
→ Find comment #3, fix it, push
→ Result: 3 commits, multiple PR activity, verification delay
```

### Good Pattern (clean merge)

```text
Extract all 3 comments at once
→ Fix all 3 locally in one pass
→ Run quality gates
→ Single commit, single push
→ Result: Clean PR history, confident merge
```

---

## Example: PR #635

### Before (wrong)
- Push initial tests
- Monitor for CodeRabbit comments
- Find mock issue, push fix
- Find assertion issue, push fix
- Find environment isolation issue, push fix
- Result: Multiple corrections, multiple pushes

### After (correct)
- Extract all 5 findings upfront
- Verify each against code
- Fix all 5 in one local pass (including helper extraction improvement)
- Run /simplify, /code-reviewer, pre-commit validation
- Single push (commit bbe606a)
- Result: Clean approval and merge

---

## Integration with Workflow

This protocol is part of the larger development workflow:

1. **Task Execution** (CLAUDE.md) - Complete all steps before declaring done
2. **Quality Gates** (CLAUDE.md) - Run in order: Simplify → Code Review → Pre-Commit
3. **PR Review Response** (this file) - Respond to review with single-pass strategy
4. **CCPM Tracking** (CLAUDE.md) - Track progress with /pm:issue-sync

---

**Last Updated**: 2026-03-07
**Status**: Active enforcement
**Key Rule**: Single-pass fix, not iterative correction
