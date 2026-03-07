# PR Merge Troubleshooting Guide

**Purpose**: Diagnose and resolve common PR merge blocking issues, particularly the "Cannot update this protected ref" error caused by stale branches.

---

## Quick Diagnosis: 5-Second Test

```bash
# Run this when merge is blocked
gh pr view <PR_NUM> --json mergeStateStatus,mergeable
```

**Problem Signs:**
```json
{
  "mergeStateStatus": "BLOCKED",
  "mergeable": "MERGEABLE"
}
```

↑ This combination = **stale branch issue** (not permissions)

---

## Issue 1: "Cannot Update Protected Ref" + BLOCKED State

### Symptoms
- Error: `X Pull request is not mergeable: the base branch policy prohibits the merge`
- mergeStateStatus: `BLOCKED`
- mergeable: `MERGEABLE`
- All CI checks passing
- Approval granted

### Root Cause
PR branch is based on an older commit of main. Another PR merged and moved main ahead. GitHub's branch protection requires PR to be up-to-date before merge.

### Diagnosis

**Step 1: Verify branch is behind main**

```bash
# Get PR's base commit (when PR was created)
PR_BASE=$(gh pr view <PR_NUM> --json baseRefOid -q '.baseRefOid[0:8]')

# Get current main HEAD
MAIN_HEAD=$(git log main --oneline -1 | awk '{print $1}')

echo "PR based on:  $PR_BASE"
echo "Main now at:  $MAIN_HEAD"

# If different → main moved ahead → branch is stale
```

**Step 2: Verify it's not a permissions issue**

```bash
# Check branch protection settings
gh api repos/$(git config --get remote.origin.url | sed 's|.*github.com[:/]||' | sed 's|.git$||')/branches/main/protection \
  --jq '.required_pull_request_reviews.required_approving_review_count'

# Should return a number (we have APPROVED) → permissions OK
```

### Resolution

**One-command fix:**

```bash
gh pr update-branch <PR_NUM>
```

This automatically:
1. Fetches latest main
2. Rebases PR branch on main
3. Force-pushes rebased branch
4. Triggers CI re-run

**Verify resolution:**

```bash
# Wait 1-2 minutes for CI to start, then check
gh pr view <PR_NUM> --json mergeStateStatus

# Should change from BLOCKED → MERGEABLE once CI passes
```

---

## Issue 2: Required Status Checks Not Completing

### Symptoms
- mergeStateStatus: `BLOCKED`
- Some status checks still `IN_PROGRESS` after 10+ minutes
- No error message, just stuck

### Diagnosis

```bash
# Check which checks are not done
gh pr view <PR_NUM> --json statusCheckRollup | \
  jq '.statusCheckRollup[] | select(.status != "COMPLETED") | {name, status}'
```

### Resolution

**Option A: Wait for slow checks**
- Test suites can take 5-15 minutes
- Check GitHub Actions tab to see progress
- Some checks are environment-specific (CodeQL, security scans)

**Option B: Re-trigger if hung**
```bash
# If a check hasn't moved in 10+ minutes
gh pr update-branch <PR_NUM>  # Forces CI re-run
```

---

## Issue 3: Review Requirements Not Met

### Symptoms
- mergeStateStatus: `BLOCKED`
- Review decision: not APPROVED or CHANGES_REQUESTED

### Diagnosis

```bash
# Check review status
gh pr view <PR_NUM> --json reviewDecision,reviews

# Expected: reviewDecision == "APPROVED"
```

### Resolution

**If APPROVED but still blocked:**
- Usually a caching issue - wait 30 seconds and retry
- Or dismiss stale reviews if branch was updated

**If not APPROVED:**
- Need to address review findings
- See: `pr-review-response-protocol.md`

---

## Merge Troubleshooting Checklist

Run in order when merge is blocked:

```bash
# 1. Check merge state (KEY INDICATOR)
echo "=== Merge State ==="
gh pr view 644 --json mergeStateStatus,mergeable,reviewDecision

# 2. Check if branch is stale
echo "=== Branch Staleness ==="
PR_BASE=$(gh pr view 644 --json baseRefOid -q '.baseRefOid[0:8]')
MAIN_HEAD=$(git log main --oneline -1 | awk '{print $1}')
echo "PR base: $PR_BASE | Main head: $MAIN_HEAD"

# 3. Check status checks
echo "=== Status Checks ==="
gh pr view 644 --json statusCheckRollup | \
  jq '.statusCheckRollup[] | {name, status, conclusion}' | head -20

# 4. Check reviews
echo "=== Reviews ==="
gh pr view 644 --json reviewDecision,reviews -q '{decision: .reviewDecision, count: (.reviews | length)}'

# 5. If branch is stale, fix it
if [ "$PR_BASE" != "$MAIN_HEAD" ]; then
  echo "=== FIXING STALE BRANCH ==="
  gh pr update-branch 644
  echo "✅ Rebase triggered - waiting for CI..."
fi
```

---

## Automated Merge Workflow (Safe)

Use this shell function for reliable merges:

```bash
pr_merge_safe() {
  local pr_num=$1

  echo "🔍 Checking PR #$pr_num..."

  # Get current state
  local state=$(gh pr view $pr_num --json mergeStateStatus,mergeable -q '.mergeStateStatus + "," + .mergeable')
  local merge_state=$(echo $state | cut -d',' -f1)
  local mergeable=$(echo $state | cut -d',' -f2)

  # Check if blocked due to stale branch
  if [ "$merge_state" = "BLOCKED" ] && [ "$mergeable" = "MERGEABLE" ]; then
    echo "⚠️  Branch is stale - updating..."
    gh pr update-branch $pr_num
    echo "⏳ Waiting for CI (120 seconds)..."
    sleep 120
  fi

  # Check final state before merge
  local final_state=$(gh pr view $pr_num --json mergeStateStatus -q '.mergeStateStatus')
  if [ "$final_state" = "BLOCKED" ]; then
    echo "❌ PR still blocked - cannot merge"
    echo "Run: gh pr view $pr_num --json mergeStateStatus,mergeable"
    return 1
  fi

  # Merge
  echo "✅ Merging PR #$pr_num..."
  gh pr merge $pr_num --squash
}

# Usage:
pr_merge_safe 644
```

---

## Prevention: Pre-Merge Checklist

Before running `gh pr merge`:

```bash
#!/bin/bash
PR_NUM=$1

# Get base commit when PR was created
PR_BASE=$(gh pr view $PR_NUM --json baseRefOid -q '.baseRefOid[0:8]')

# Get current main
MAIN_HEAD=$(git log main --oneline -1 | awk '{print $1}')

# If different, update first
if [ "$PR_BASE" != "$MAIN_HEAD" ]; then
  echo "📌 PR is behind main ($PR_BASE vs $MAIN_HEAD)"
  echo "Updating branch before merge..."
  gh pr update-branch $PR_NUM
  echo "✅ Update queued - CI will re-run"
  exit 0
fi

echo "✅ Branch is current - safe to merge"
```

---

## Real-World Example: PR #644

**Timeline:**
1. PR #644 created based on commit `bdc9d51` (main at that time)
2. PR #643 merged → main moved to `314fb72`
3. Attempted merge of #644 → Error: "Cannot update protected ref"
4. Diagnostic: mergeStateStatus=BLOCKED, mergeable=MERGEABLE
5. Solution: `gh pr update-branch 644`
6. Result: ✅ Merged successfully after CI re-run

**Key Learning:** The branch was "technically mergeable" (no conflicts, all checks passed) but GitHub's protection rule required it to be based on current main → BLOCKED state until updated.

---

## Integration with PR Workflow

**Add to `pr-workflow-master.md` Merge Checklist:**

```markdown
Before merging (READY_TO_MERGE state):
1. ✅ CI all passing
2. ✅ Reviews approved
3. ✅ Branch is up-to-date with main
   - Run: gh pr update-branch <PR_NUM> if behind
   - Wait for CI to re-run (1-2 min)
4. ✅ Final check: gh pr view <PR_NUM> --json mergeStateStatus
5. ✅ Then: gh pr merge <PR_NUM> --squash
```

---

## References

- `pr-review-response-protocol.md` - Handling review comments
- `pr-workflow-master.md` - Complete PR workflow
- `pr-monitoring-protocol.md` - Monitoring PR after push
- GitHub Docs: [Branch Protection](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches)

---

**Last Updated**: 2026-03-07
**Status**: Active (based on PR #644 merge experience)
**Related Issue**: "Cannot update this protected ref" diagnostic
