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

---

## Step 4: Run Full Quality Gate Sequence

All three gates are MANDATORY. Execute in order:

```bash
/simplify                     # Review changes for efficiency/reuse (REQUIRED)
/code-reviewer                # Validate changes against standards (REQUIRED)
bash .claude/scripts/pre-commit-validation.sh  # Must pass (REQUIRED)
```

### Quality Gate Expectations

**If /simplify is unavailable**: Hard blocker - cannot proceed without it

**If /code-reviewer is unavailable**: Hard blocker - cannot proceed without it

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

## Step 5B: Resolve Review Threads via GraphQL (Mandatory)

**CRITICAL**: After pushing fixes, ALL review threads related to APPLY findings MUST be marked as resolved using GraphQL mutations. `gh` CLI cannot do this.

### Why This is Required

- Marking threads as resolved indicates findings have been addressed
- Leaving threads "resolved" manually on GitHub doesn't work - need GraphQL
- Reviewers check thread resolution status to gauge PR readiness
- Without resolution, threads stay open and create noise

### Resolution Process

```bash
TOKEN=$(gh auth token)
PR_NUM=644

# First, fetch all unresolved threads to get their IDs
curl -s -X POST https://api.github.com/graphql \
  -H "Authorization: token $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "{ repository(owner: \"curdriceaurora\", name: \"Local-File-Organizer\") { pullRequest(number: '$PR_NUM') { reviewThreads(first: 50) { nodes { id isResolved } } } } }"
  }' | jq '.data.repository.pullRequest.reviewThreads.nodes[] | select(.isResolved == false) | .id' > /tmp/thread_ids.txt

# Then resolve each thread
while read THREAD_ID; do
  curl -s -X POST https://api.github.com/graphql \
    -H "Authorization: token $TOKEN" \
    -H "Content-Type: application/json" \
    -d "{
      \"query\": \"mutation { resolveReviewThread(input: {threadId: \\\"$THREAD_ID\\\"}) { thread { isResolved } } }\"
    }"
  echo "✓ Resolved thread $THREAD_ID"
done < /tmp/thread_ids.txt
```

### Verify Resolution

```bash
# Check that all threads are resolved
TOKEN=$(gh auth token)

curl -s -X POST https://api.github.com/graphql \
  -H "Authorization: token $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "{ repository(owner: \"curdriceaurora\", name: \"Local-File-Organizer\") { pullRequest(number: '$PR_NUM') { reviewThreads(first: 50) { nodes { isResolved } } } } }"
  }' | jq '.data.repository.pullRequest.reviewThreads.nodes | map(.isResolved) | {total: length, resolved: (map(select(.)) | length), unresolved: (map(select(. | not)) | length)}'

# Should show: all threads resolved, unresolved = 0
```

### Why GraphQL (Not gh CLI)

| Operation | gh CLI | GraphQL |
|-----------|--------|---------|
| Fetch reviews | ✅ Works | ✅ Works |
| Fetch comments | ⚠️ Limited | ✅ Works |
| Resolve threads | ❌ Cannot do | ✅ Works |
| Batch operations | ❌ Sequential | ✅ Parallel |

The `gh` CLI has no command to resolve review threads. GraphQL mutations are the only way.

---

## Step 6: Do NOT Create Iterative Monitoring Loop

After pushing and resolving comment threads, do NOT:
- ❌ Create background scripts to monitor review status
- ❌ Iteratively fix issues as they appear in re-review
- ❌ Push partial fixes and hope for the best
- ❌ Monitor and wait for CI/review feedback to guide next fixes

Instead:
- ✅ Trust that running quality gates locally caught issues before pushing
- ✅ Trust that GraphQL thread resolution properly marks findings as addressed
- ✅ Verification comes from local testing and GraphQL resolution, not iterative PR reviews
- ✅ PR review feedback should be minimal if quality gates ran properly

### Outcome Verification (After Comment Resolution)

After push + GraphQL thread resolution, the PR review process has these requirements:
- CI must pass
- All review threads resolved (APPLY findings) via GraphQL mutations
- SKIP/CLARIFY/DEFER findings replied to (separate comment)
- 1 reviewer approval
- Review decision: APPROVED

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
