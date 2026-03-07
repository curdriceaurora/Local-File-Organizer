# PR Workflow Master - Executive Reference

**Purpose**: Single entry point for PR workflow execution. Tells you which state you're in and what to do next.

**Context-optimized**: ~300 lines. Load this to navigate workflow; link to detailed protocols for execution.

---

## Quick State Reference

### Where Are You?

```
┌─ INITIAL: Have fixes ready, about to push
├─ MONITORING: PR pushed, watching for feedback (webhook-driven)
├─ PAUSED: Issues found, executing fixes (→ PR Review Response Protocol)
├─ CHECKING: About to commit, verifying no new feedback
├─ BLOCKED: Can't proceed, waiting for external action
├─ READY TO MERGE: All conditions met (auto-merge enabled)
└─ MERGED: Done ✅
```

**Find your state above, then follow the guidance.**

---

## State Definitions & Actions

### INITIAL
**When**: PR ready to push with fixes
**Duration**: Seconds
**Your Action**:
- Have all fixes applied locally
- Ready to commit and push
**Next**: → PAUSED (execute PR Review Response Protocol Steps 1-6)

---

### PAUSED
**When**: Executing PR Review Response Protocol
**Duration**: 10-30 min depending on fixes
**What You're Doing**:
- Step 1: Extract findings
- Step 2: Verify & categorize (APPLY/SKIP/CLARIFY/DEFER)
- Step 3: Apply fixes locally
- Step 4: Run quality gates (pre-commit → code-reviewer → simplify)
- Step 5: Prepare commit

**Before Step 5 (Commit)**: Transition to CHECKING

**Details**: See `.claude/rules/pr-review-response-protocol.md`

---

### CHECKING
**When**: About to commit, before pushing
**Duration**: <1 min
**Your Action**:
1. Query GitHub for new feedback (comments, approvals, status)
2. Compare against what you saw when entering PAUSED
3. If new findings: Return to PAUSED (add to current batch, restart Steps 2-4)
4. If no new findings: Proceed to commit & push

**Purpose**: Catch feedback posted while you were fixing (race condition prevention)

**After successful push** (fresh CI triggered): → MONITORING

---

### MONITORING
**When**: PR pushed, watching for status
**Duration**: Until merge
**Triggered By**: Webhooks (not manual polling)
**What You're Watching**:
- CI status (passing/failing/running)
- New comments from reviewers
- Approval received
- Review progress
- Rate limits (continue monitoring without action if limited)

**Checklist Every Webhook Event**:
- [ ] CI passing?
- [ ] Any new comments?
- [ ] Any approvals?
- [ ] Review progress?

**What Triggers State Changes**:
- Issue detected (CI fail, new comments, merge conflict) → PAUSED
- Merge conditions met → READY TO MERGE
- Unresolvable issue (waiting for clarification, unresponsive reviewer) → BLOCKED

**Details**: See `.claude/rules/pr-monitoring-protocol.md`

---

### BLOCKED
**When**: PR can't progress without external action
**Examples**:
- CLARIFY finding awaiting reviewer response (no timeout)
- Merge conflict (requires rebase)
- Reviewer unresponsive (requires escalation)
- Rate limit (requires reset)

**Your Action**:
- **For CLARIFY**: Post comment, wait for response
- **For merge conflict**: Rebase on main, resolve, push → return to MONITORING
- **For unresponsive reviewer**: Post reminder, escalate if needed
- **For rate limit**: Continue monitoring without API calls, resume when reset

**After Resolution**: Return to appropriate state (usually MONITORING or PAUSED)

---

### READY TO MERGE
**When**: All merge conditions met
**Conditions**:
- ✅ CI passing
- ✅ All comments resolved:
  - APPLY findings: Fixed in commits
  - SKIP findings: Replied (explained why skipped)
  - CLARIFY findings: Resolved (got clarification + addressed)
  - DEFER findings: Replied (GitHub issue created + linked)
- ✅ 1 reviewer approval
- ✅ No "requested changes" status

**Your Action**:
- Enable auto-merge (GitHub handles rest)
- Receive notification when merged

---

### MERGED
**When**: PR successfully merged
**Status**: Workflow complete ✅
**What's Next**: Start new PR cycle or move to next task

---

## Transition Rules at a Glance

| From | Trigger | To | Action |
|------|---------|----|----|
| INITIAL | Push with fixes | PAUSED | Execute PR Review Response |
| PAUSED | Before commit check | CHECKING | Verify no new feedback |
| CHECKING | No new feedback | Push & fresh CI | MONITORING (via webhook) |
| CHECKING | New feedback found | PAUSED | Re-add findings, restart fixes |
| MONITORING | Issue detected | PAUSED | Execute PR Review Response |
| MONITORING | Merge conditions met | READY TO MERGE | Enable auto-merge |
| MONITORING | Unresolvable issue | BLOCKED | Escalate/wait |
| BLOCKED | Issue resolved | Back to MONITORING or PAUSED | Resume workflow |
| READY TO MERGE | Auto-merge triggered | MERGED | Done ✅ |

---

## Decision Matrix Quick Reference

### When categorizing findings in PAUSED state:

| Category | Definition | What to Do |
|----------|-----------|-----------|
| **APPLY** | Valid, in-scope, fix it now | Include in current PR fixes |
| **SKIP** | Invalid or already addressed | Reply: explain why skipped |
| **CLARIFY** | Don't understand the concern | Reply: ask for clarification, continue fixing others |
| **DEFER** | Valid but out of scope | Create GitHub issue, reply with link |

---

## Quality Gates Order

When in PAUSED state, Step 4 (Quality Gates):

```
Step 4a: bash .claude/scripts/pre-commit-validation.sh (REQUIRED - fast)
  ↓ Fix violations until passing

Step 4b: /code-reviewer (REQUIRED - medium)
  ↓ Address findings

Step 4c: /simplify (OPTIONAL - suggestions)
  ↓ Include valuable suggestions, defer rest
```

**Philosophy**: Fail fast on cheap checks before expensive ones.

---

## Workflow Checklist

### Before pushing (end of PAUSED):
- [ ] All APPLY findings fixed
- [ ] All quality gates passed (pre-commit, code-reviewer, simplify)
- [ ] Commit message documents findings
- [ ] Ready to push

### Before merge (READY TO MERGE):
- [ ] CI passing
- [ ] All findings addressed (APPLY/SKIP/CLARIFY/DEFER)
- [ ] 1 reviewer approval
- [ ] No requested changes

---

## When to Reference Detailed Protocols

| Situation | Reference |
|-----------|-----------|
| "I have findings to fix" | PR Review Response Protocol (Steps 1-6) |
| "What should I watch while PR is open?" | PR Monitoring Protocol (checklist & scenarios) |
| "What decisions do I make?" | PR Review Response - Decision Matrix |
| "Why did I transition states?" | This Master document - Transition Rules |
| "I'm stuck, where am I?" | This Master document - State Definitions |
| "Merge is blocked" | PR Merge Troubleshooting (diagnosis & resolution) |

---

## Common Questions

**Q: PR pushed, now what?**
A: You're in MONITORING. Watch for webhooks. When issue detected → PAUSED. When ready to merge → READY TO MERGE.

**Q: New comments from reviewer, what do I do?**
A: Webhook notifies you. You're in MONITORING → PAUSED (invoke PR Review Response). Extract findings, fix, push. Back to MONITORING.

**Q: Before I commit my fixes, what should I check?**
A: You're about to leave PAUSED → CHECKING. Check GitHub for new feedback. If found, add to findings and restart. If not, commit and push.

**Q: CI failed, what now?**
A: Issue detected in MONITORING → PAUSED. Investigate failure, apply as finding, fix with quality gates, commit, push. Back to MONITORING.

**Q: Can I merge now?**
A: Are ALL conditions met? CI passing, comments resolved, approval received, no requested changes? If yes → enable auto-merge. If no → continue monitoring.

**Q: How long until PR merges?**
A: Depends on CI speed (2-5 min) and reviewer response time (5-60 min). Once auto-merge enabled → GitHub handles merge automatically.

**Q: Rate limit hit, what happens?**
A: Continue monitoring but don't trigger API calls. Check GitHub UI manually. When limit resets, resume normal workflow.

**Q: Merge blocked with "Cannot update this protected ref"?**
A: Usually means PR branch is behind main (another PR merged after yours was created). Run `gh pr update-branch <PR_NUM>` to rebase on latest main, wait for CI to re-run (1-2 min), then merge. See PR Merge Troubleshooting guide for full diagnosis.

---

## Quick Reference Links

**Detailed Protocols** (reference when needed, not during navigation):
- [PR Review Response Protocol](.claude/rules/pr-review-response-protocol.md) - Full Steps 1-6, detailed decision matrix
- [PR Monitoring Protocol](.claude/rules/pr-monitoring-protocol.md) - Full checklist, detailed scenarios
- [PR Workflow State Machine](.claude/rules/pr-workflow-state-machine.md) - Complete state machine, example flows

**Improvement Guidance** (for future enhancement):
- [PR Workflow Conformance](.claude/rules/pr-workflow-conformance.md) - Industry standards evaluation, improvement roadmap

---

## Key Principles

1. **Always know your state** - Refer to State Definitions if unsure
2. **Transitions are explicit** - Don't drift, follow Transition Rules
3. **Before-commit check prevents race conditions** - CHECKING state catches late feedback
4. **APPLY only for in-scope** - DEFER things that don't belong in this PR
5. **Parallel issues, one batch** - Multiple findings go through one PR Review Response cycle
6. **Rate limits don't block monitoring** - Continue watching GitHub, just can't use API

---

**Last Updated**: 2026-03-07
**Type**: Navigation & Reference (load this during workflow)
**Context Load**: ~300 lines (optimize Claude token usage)
**Detailed Protocols**: Link to when needed

