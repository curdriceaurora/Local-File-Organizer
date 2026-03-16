# PR Monitoring Protocol

**Purpose**: Track PR status from push through merge, detect issues early, and coordinate with PR Review Response Protocol.

## Core Principle

Monitor continuously but avoid reactive decisions. When issues are detected, pause monitoring, invoke the review response protocol, then resume when fresh activity appears.

---

## Monitoring Lifecycle

```
Push PR
  ↓
START Monitoring (5-10 min checks)
  ↓
[Detect Issue?]
  ├─ YES → PAUSE Monitoring
  │        Invoke PR Review Response Protocol
  │        (Address findings, run quality gates, commit & push)
  │        Fresh CI triggered
  │        RESUME Monitoring
  │
  └─ NO → Continue checking
           ↓
         [Merge Conditions Met?]
           ├─ YES → TERMINATE Monitoring, Merge PR ✅
           └─ NO → Check again in 5-10 min
```

---

## Step 1: Start Monitoring

**When**: Immediately after pushing to PR (end of PR Review Response Protocol)

**Initial State**:
- PR pushed with fixes
- CI running or queued
- Waiting for reviewer feedback
- Monitoring interval: Every 5-10 minutes

---

## Step 2: Check Status (Every 5-10 Minutes)

Use this formal checklist on each monitoring cycle:

### Monitoring Checklist

- [ ] **CI Status**
  - Passing?
  - Failing?
  - Still running?
  - Rate limited?

- [ ] **New Comments**
  - Any new review comments?
  - Any replies to threads?
  - CodeRabbit/Copilot finished reviewing?

- [ ] **Reviewer Approval**
  - Approved?
  - Requested changes?
  - Still reviewing?

- [ ] **Line-by-Line Review Progress**
  - Reviewer actively reviewing (cursor moving)?
  - Review paused?
  - Review complete?

### Rate Limit Handling

If CodeRabbit/Copilot hit rate limits during monitoring:
- Continue monitoring (don't stop)
- Don't trigger additional API calls
- Watch for manual reviewer activity instead
- Resume normal tool usage when limit resets

---

## Step 3: Assess Findings

Based on checklist results, decide on action:

### Scenario A: All Clear ✅
- CI passing
- No new comments
- No approval yet (normal)
- Review still in progress

**Action**: Continue monitoring, check again in 5-10 minutes

### Scenario B: Issue Detected ⚠️
- CI failing (related to your changes)
- OR new comments requiring fixes
- OR reviewer stuck/blocked
- OR merge conflict

**Action**: PAUSE monitoring → See "Pause Monitoring" section below

### Scenario C: Ready to Merge ✅
- CI passing
- All review comments resolved (APPLY fixes applied, SKIP/CLARIFY/DEFER addressed)
- 1 reviewer approval received

**Action**: TERMINATE monitoring → Merge PR

---

## Step 4: Pause Monitoring (When Issue Detected)

When an issue requires action:

### CI Failure (Related to Your Changes)

1. Investigate root cause
2. Understand what failed and why
3. Invoke **PR Review Response Protocol** (full Steps 1-6)
   - Treat CI failure as new findings
   - Extract, verify, fix, run quality gates, commit, push
4. Fresh CI run triggered
5. Resume monitoring (see "Resume Monitoring" below)

### New Comments Received

Wait for reviewer to complete their review (don't interrupt mid-review).

Once reviewer finishes reviewing (all comments posted):
1. Invoke **PR Review Response Protocol** (Steps 1-2 to verify findings)
2. Categorize as APPLY, SKIP, CLARIFY, or DEFER
3. Execute Steps 3-6 (apply fixes, run gates, commit, push)
4. Fresh CI run triggered
5. Resume monitoring

### Reviewer Stuck/No Activity for Extended Time

1. Post a comment on PR: "Friendly reminder - ready for your review whenever you get a chance"
2. Resume monitoring (don't pause)
3. Continue checking until response or merge conditions met

### Merge Conflict

1. Fetch latest main: `git fetch origin main`
2. Rebase on main: `git rebase origin/main`
3. Resolve conflicts
4. Re-run quality gates (pre-commit validation minimum)
5. Force push: `git push --force-with-lease origin <branch>`
6. Resume monitoring (fresh CI run will be triggered)

---

## Step 5: Resume Monitoring

When PR Review Response Protocol completes and fresh CI is triggered:

1. Reset monitoring checklist
2. Resume 5-10 minute check cycles
3. Look for:
   - New CI run to complete
   - Reviewer re-review if comments were addressed
   - Any new issues to surface

Continue from Step 2 (Check Status)

---

## Step 6: Merge Conditions

Terminate monitoring and merge when ALL of these are true:

- [ ] **CI Passing**: All status checks green
- [ ] **Comments Resolved**:
  - All APPLY fixes applied (evident in commits)
  - All SKIP findings replied (explained why skipped)
  - All CLARIFY findings replied (clarification received and resolved)
  - All DEFER findings replied (GitHub issue created and linked)
- [ ] **Approval**: At least 1 reviewer approved
- [ ] **No Pending Changes**: No "requested changes" status from any reviewer

Once all conditions met:

```bash
# Verify merge is safe
git status  # Should be clean

# Merge (preferred: squash or standard merge per project)
# Use GitHub UI or CLI

# Post-merge
# Monitoring is TERMINATED ✅
```

---

## Monitoring State Reference

### Active Monitoring
- Checking every 5-10 minutes
- Running through checklist
- Looking for issues or merge readiness
- Can detect problems early

### Paused Monitoring
- PR Review Response Protocol is executing
- Not checking PR status
- Focused on fixing issues
- Will resume when fresh CI triggered

### Terminated Monitoring
- PR merged
- No more checks needed
- Move to next PR

---

## Timeline Expectations

- **Initial push to first check**: Immediately (within 5 min)
- **Ongoing checks**: Every 5-10 minutes continuously
- **Monitor duration**: Until merge conditions met
- **Total time**: Depends on reviewer response time, CI speed, and issue complexity
  - Best case: 30-60 minutes (quick CI, quick review, approval)
  - Normal case: 1-2 hours (reviewer still reviewing)
  - Worst case: Several hours (multiple issues found, multiple cycles)

---

## Integration with Workflow

This protocol works with:

1. **PR Review Response Protocol** (.claude/rules/pr-review-response-protocol.md)
   - Pauses monitoring when invoked
   - Triggers fresh monitoring on push

2. **Quality Gates** (CLAUDE.md)
   - Validates fixes before push
   - Ensures high quality PR that passes CI

3. **CCPM Tracking** (CLAUDE.md)
   - Use `/pm:issue-sync` to update progress while monitoring
   - Document blockers/delays

---

## Common Issues & Resolution

| Issue | Detection | Action |
|-------|-----------|--------|
| **CI Timeout** | Still running after 30+ min | Check CI logs, restart if needed |
| **Flaky Test** | Test passes then fails then passes | Document, create follow-up issue |
| **Rate Limit** | Copilot/CodeRabbit not reviewing | Continue monitoring, wait for reset |
| **Reviewer Unresponsive** | No activity for 24+ hours | Post comment, escalate to team lead |
| **Merge Conflict** | Merge blocked by conflict | Rebase main, resolve, force-push |
| **Approval + CI Fail** | Approved but new CI failure | Investigate, fix with review response, re-push |

---

**Last Updated**: 2026-03-07
**Status**: Active enforcement
**Key Rule**: Monitor continuously, pause to fix, resume when fresh activity, terminate at merge
