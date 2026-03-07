# PR Workflow State Machine

**Purpose**: Define the states and transitions in the PR lifecycle, clarifying when to invoke PR Review Response Protocol vs PR Monitoring Protocol.

---

## State Diagram

```
┌─────────────┐
│   INITIAL   │ (PR created and ready to push)
└──────┬──────┘
       │ Push with fixes
       ↓
┌─────────────────────────────────────────────────┐
│          MONITORING STATE                       │
│  (Check every 5-10 min)                         │
│  • CI status                                    │
│  • New comments                                 │
│  • Reviewer approval                            │
│  • Review progress                              │
└────┬──────────────────────┬────────────────────┘
     │ Issue detected       │ Merge conditions
     │ (CI fail, new        │ met
     │  comments, blocked)  │
     │                      ↓
     │              ┌──────────────────┐
     │              │  READY TO MERGE  │
     │              │ (All conditions)  │
     │              └────────┬─────────┘
     │                       │ Merge PR
     │                       ↓
     │              ┌──────────────────┐
     │              │     MERGED ✅    │
     │              │ (Workflow done)  │
     │              └──────────────────┘
     │
     ↓
┌──────────────────────────────────────────────────┐
│         PAUSED STATE                             │
│ Invoke: PR Review Response Protocol              │
│                                                  │
│ Step 1: Extract findings                         │
│ Step 2: Verify & categorize (APPLY/SKIP/etc)    │
│ Step 3: Apply fixes locally                      │
│ Step 4: Run quality gates                        │
│         ↓                                        │
│ TRANSITION: Before commit → Check Monitoring    │
└──────────┬───────────────────────────────────────┘
           │
           ↓
┌─────────────────────────────────────────────────┐
│   CHECKING STATE (before commit)                │
│                                                 │
│ Check GitHub for new feedback:                  │
│ • Any new comments from reviewer?               │
│ • Any approvals?                                │
│ • Any status changes?                           │
└────┬──────────────────┬─────────────────────────┘
     │ New feedback     │ No new feedback
     │ found            │
     │                  ↓
     │         ┌────────────────────┐
     │         │ Step 5: Commit     │
     │         │ Step 6: Push       │
     │         └────────┬───────────┘
     │                  │ Git push → Fresh CI
     │                  │ triggered
     │                  ↓
     │         ┌────────────────────────┐
     │         │ MONITORING (Resume)    │
     │         │ Resume status checks   │
     │         └────────────────────────┘
     │
     ↓
┌────────────────────────────────────────────────┐
│ New findings detected                          │
│ (comments, CI failure, requests)               │
│                                                │
│ Extract new findings                           │
│ Add to existing batch                          │
│ Re-run Steps 2-6 of PR Review Response         │
│ (repeat cycle)                                 │
└────────────┬─────────────────────────────────┘
             │ Cycle again
             └─→ CHECKING STATE (before next commit)
```

---

## States in Detail

### 1. INITIAL
**When**: PR created and ready to push fixes
**What you're doing**: Executing PR Review Response Protocol (Steps 1-6)
**Next**: Push → MONITORING

### 2. MONITORING
**When**: PR pushed, waiting for CI and review feedback
**Duration**: Continuous, checking every 5-10 minutes with formal checklist
**Active Checks**:
- CI status (passing/failing/running)?
- New comments from reviewer?
- Approval received?
- Review progress (actively reviewing)?

**What triggers state changes**:
- Issue detected → PAUSED
- Merge conditions met → READY TO MERGE
- Blocker found (merge conflict, unresponsive reviewer) → BLOCKED

### 3. PAUSED
**When**: Issue detected during monitoring
**What to do**: Invoke PR Review Response Protocol (full Steps 1-6)
**Issues that trigger pause**:
- CI failure (related to your changes)
- New review comments (after reviewer finishes reviewing)
- Merge conflict
- Rate limits (continue monitoring without pausing)

**Inside PAUSED: Before Commit Check**
Before executing Step 5 (Commit), transition to CHECKING state:
1. Check GitHub for any new feedback
2. If new findings exist: Add to current batch, re-run Steps 2-4
3. If no new findings: Proceed with commit

### 4. CHECKING (Before Commit)
**When**: You're about to commit fixes, about to push
**Purpose**: Catch new feedback that arrived during PR Review Response execution
**Process**:
1. Query GitHub for new comments/approvals/status changes
2. Compare against what you saw at start of PAUSED
3. If new feedback: Return to PAUSED (re-add to findings)
4. If no new feedback: Proceed to commit & push

**Why**: Prevents pushing a fix that conflicts with reviewer feedback posted while you were working

### 5. BLOCKED
**When**: PR can't progress without external action
**Examples**:
- Waiting for clarification (CLARIFY finding, still waiting)
- Merge conflict (requires rebase + push)
- Reviewer unresponsive for extended time
- Rate limit (continue monitoring but can't take action)

**What to do**:
- For clarification: Post comment, wait
- For merge conflict: Rebase, resolve, push (goes back to MONITORING)
- For unresponsive reviewer: Escalate, post reminder

### 6. READY TO MERGE
**When**: All conditions met
**Merge Conditions**:
- ✅ CI passing
- ✅ All comments resolved:
  - APPLY fixes applied (in commits)
  - SKIP findings replied (explained why)
  - CLARIFY findings resolved (got clarification + addressed)
  - DEFER findings replied (GitHub issue created + linked)
- ✅ 1 reviewer approval
- ✅ No "requested changes" status

**Next**: Merge PR

### 7. MERGED
**When**: PR successfully merged
**Workflow**: Complete ✅

---

## Transition Rules

### MONITORING → PAUSED
**Triggered by**: Issue detected on checklist
- [ ] CI failed (related to your changes)
- [ ] New comments from reviewer (after review complete)
- [ ] Merge conflict
- [ ] Reviewer requested changes

**Action**: Invoke PR Review Response Protocol

### PAUSED → CHECKING
**Triggered by**: About to commit (Step 5 of PR Review Response)
**Action**: Query GitHub for new feedback
- If found: Restart PAUSED (re-add to findings, re-run Steps 2-4)
- If not found: Proceed to commit

### CHECKING → MONITORING
**Triggered by**: Successful push (fresh CI triggered)
**Action**: Resume monitoring with new CI run
**Verification**: Confirm new CI run started before resuming (use Run data, not timers)

### MONITORING → BLOCKED
**Triggered by**: Unresolvable issue detected
- Waiting for CLARIFY response (no timeout)
- Merge conflict (requires rebase)
- Reviewer unresponsive (escalate)
- Rate limit (continue monitoring without action)

**Action**: Take appropriate resolution step

### BLOCKED → PAUSED or MONITORING
**Triggered by**: Blocker resolved
- Clarification received → Add to findings, return to PAUSED
- Merge conflict resolved → Push, return to MONITORING
- Reviewer responsive → Resume normal flow

### MONITORING → READY TO MERGE
**Triggered by**: All merge conditions met
**Verification Checklist**:
- [ ] CI passing
- [ ] All comments resolved (APPLY/SKIP/CLARIFY/DEFER addressed)
- [ ] 1 reviewer approval
- [ ] No "requested changes"

**Action**: Merge PR

### Any State → BLOCKED
**Special case**: Rate limit during monitoring
**Action**: Continue monitoring but don't trigger API calls
**Status**: Quasi-BLOCKED (not stuck, just limited)
**Recovery**: Resume normal actions when rate limit resets

---

## Protocol Invocation Rules

### When to invoke PR Review Response Protocol
**From**: MONITORING (issue detected) or PAUSED (continue/restart)
**Entry Point**: Step 1 (Extract findings)
**Exit Point**: Step 6 (Push) → Transition to CHECKING before commit

### When to invoke PR Monitoring Protocol
**From**: INITIAL (after push) or CHECKING (after push with no new findings)
**Entry Point**: Start monitoring at 5-10 min intervals
**Exit Point**: Either READY TO MERGE or issue detected (→ PAUSED)

### When to invoke CHECKING
**From**: PAUSED (before commit step)
**Purpose**: Catch new feedback before pushing
**Decision**:
- New feedback found → Return to PAUSED (re-add findings)
- No new feedback → Proceed with commit

---

## Example Flows

### Happy Path (No Issues)
```
INITIAL
  ↓ (PR Review Response Steps 1-6)
PAUSED
  ↓ (Before commit check)
CHECKING (No new feedback)
  ↓ (Commit & push, fresh CI)
MONITORING (5-10 min checks)
  ↓ (All merge conditions met)
READY TO MERGE
  ↓ (Merge)
MERGED ✅
```
**Time**: 30 min - 2 hours (depends on CI speed, reviewer response)

### With CI Failure
```
MONITORING (CI fails)
  ↓ (Issue detected)
PAUSED (Invoke review response for CI failure)
  ↓ (Extract failure as finding)
  ↓ (Fix, run quality gates)
CHECKING (Before commit check)
  ↓ (No new feedback from reviewer)
  ↓ (Commit & push, fresh CI)
MONITORING (5-10 min checks)
  ↓ (CI passes this time)
  ↓ (All merge conditions met)
READY TO MERGE
  ↓ (Merge)
MERGED ✅
```

### With Review Comments + CI Failure
```
MONITORING (Both CI fail AND new comments)
  ↓ (Issue detected, both treated as findings)
PAUSED (Invoke review response)
  ↓ (Extract both findings: CI failure + comments)
  ↓ (Verify both, fix all together)
CHECKING (Before commit check)
  ↓ (No new additional feedback)
  ↓ (Commit & push, fresh CI)
MONITORING (5-10 min checks)
  ↓ (CI passes, comments addressed)
READY TO MERGE
  ↓ (Merge)
MERGED ✅
```

### Blocked by Clarification
```
MONITORING (New comments)
  ↓ (Issue detected, one is CLARIFY)
PAUSED (Invoke review response)
  ↓ (Step 2: Mark one as CLARIFY, others as APPLY)
  ↓ (Step 3-4: Fix APPLY items)
  ↓ (Step 5-6: Reply asking for clarification, push)
MONITORING (5-10 min checks)
  ↓ (Still waiting for clarification)
BLOCKED (Waiting for reviewer response)
  ↓ (Reviewer responds with clarification)
  ↓ (Add as new finding, restart review response)
PAUSED
  ↓ (Extract clarification as APPLY finding)
CHECKING (Before commit)
MONITORING (Commit & push)
  ↓ (All conditions met)
READY TO MERGE
  ↓ (Merge)
MERGED ✅
```

---

## Handoff Checklist

### When Exiting MONITORING → PAUSED
- [ ] Issue clearly identified (CI fail, comments, or conflict)
- [ ] Issue logged or documented
- [ ] Ready to invoke PR Review Response Protocol

### When Exiting PAUSED → CHECKING
- [ ] All fixes applied and verified locally
- [ ] Quality gates (simplify, code-reviewer, pre-commit) passed
- [ ] About to commit

### When Exiting CHECKING → MONITORING
- [ ] Checked GitHub for new feedback (before commit)
- [ ] Committed and pushed successfully
- [ ] Confirmed new CI run started (via Run data)
- [ ] Ready to resume monitoring

### When Exiting MONITORING → READY TO MERGE
- [ ] Verified all merge conditions on checklist
- [ ] No blockers or BLOCKED state
- [ ] Ready to merge

---

## Key Principles

1. **Clear State**: Always know which state you're in
2. **Explicit Transitions**: Don't drift between states
3. **Before-Commit Check**: Always check monitoring before pushing (CHECKING state)
4. **One Finding Batch**: Combine all findings from multiple sources into one PR Review Response cycle
5. **No Partial Merges**: All findings must be addressed (APPLY/SKIP/CLARIFY/DEFER)
6. **Rate Limits**: Continue monitoring without action if rate limited

---

**Last Updated**: 2026-03-07
**Status**: Active enforcement
**Key Rule**: Know your state, follow the transitions, check before commit

