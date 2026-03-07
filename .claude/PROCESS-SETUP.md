# Complete PR Workflow Process Setup

**Status**: Ready to implement (all three phases)
**Last Updated**: 2026-03-06
**Objective**: Enable fully autonomous coding work with zero manual process friction

---

## Overview

This document describes the three phases that enable autonomous PR execution without manual monitoring overhead:

1. **Phase 1: Pre-Commit Validation** ✅ Complete
   - Automated checks prevent bad code from ever reaching GitHub
   - ~750 lines of validation rules built into `.claude/scripts/pre-commit-validation.sh`
   - Status: Running on every commit to catch issues locally

2. **Phase 2: Auto-Merge Configuration** ✅ Complete
   - GitHub automatically merges PRs when conditions are met
   - Merge method: Squash (clean history) + auto-delete branch
   - Status: Configured and ready

3. **Phase 3: Webhook Monitoring** 🔧 Ready to Deploy
   - Local webhook receiver listens for GitHub events
   - Proactive notifications instead of manual polling
   - Status: Scripts created, ready for GitHub configuration

---

## Phase 1: Pre-Commit Validation ✅

**What It Does**: Runs before every commit to prevent bad code from reaching GitHub.

**Location**: `.claude/scripts/pre-commit-validation.sh` (758 lines)

**Validation Checks** (in order):

1. **Branch Verification** (2 sec)
   - Confirms you're on correct branch
   - Checks for CCPM tracking awareness
   - Warns if issue tracking not started

2. **Build Artifact Detection** (1 sec)
   - Blocks `.coverage`, `*.bak`, `*.pyc`, `*.pyo` files
   - Prevents bloat in repository

3. **Absolute Path Detection** (1 sec)
   - Blocks hardcoded paths like `/Users/username/...`
   - Enforces relative paths for portability

4. **Python Pattern Validation** (2 sec)
   - Dict-style dataclass access (❌ `if "field" in obj`)
   - Bracket access on dataclasses (❌ `obj["field"]`)
   - Known anti-patterns from code review

5. **Linting** (ruff check) (10-30 sec)
   - Code style and lint rules
   - Type annotations in `src/` files

6. **Type Checking** (mypy) (10-30 sec)
   - Full type safety validation
   - Uses strict mode

7. **Code Quality Requirements** (advisory)
   - Detects significant changes (>50 lines)
   - Requires `/simplify` and `/code-reviewer` quality gates
   - Prevents pushing untested code

8. **Markdown Validation** (5-10 sec)
   - Link verification (no broken links)
   - Markdown linting (MD022, MD040, etc.)
   - Docs format conformity

9. **Documentation Content Verification** (10-20 sec)
   - Verifies coverage percentage claims
   - Checks method examples exist in code
   - Detects contradictions

10. **Test Execution** (10-60 sec depending on count)
    - Runs tests for modified modules
    - Validates mock @patch targets
    - Runs security-focused tests
    - Runs CLI docs accuracy tests

11. **Datetime Timezone Safety** (2 sec)
    - Blocks naive `datetime.now()`
    - Blocks deprecated `utcnow()`
    - Enforces UTC timezone safety

**When It Runs**:
```bash
bash .claude/scripts/pre-commit-validation.sh  # Before every commit
```

**What If It Fails**:
1. Read the error message (clear instructions provided)
2. Fix the violation
3. Re-stage files: `git add <files>`
4. Run validation again
5. When it passes, commit

**Integration**: Automatically called by git pre-commit hook (if `.pre-commit-config.yaml` installed)

---

## Phase 2: Auto-Merge Configuration ✅

**What It Does**: Automatically merges PR when conditions are met (no manual action needed).

**Configuration** (already applied):
```bash
gh repo edit \
  --enable-auto-merge \
  --enable-squash-merge \
  --delete-branch-on-merge
```

**Auto-Merge Conditions** (built into GitHub):
- ✅ All status checks pass (CI)
- ✅ 1 reviewer approval
- ✅ No requested changes
- ✅ All conversations resolved (or dismissed)

**Merge Method**: Squash (clean single commit per PR)

**Branch Cleanup**: Automatic (branch deleted after merge)

**How to Enable Auto-Merge on a PR**:
```bash
# Via GitHub UI:
1. Go to PR
2. Click "Enable auto-merge"
3. Confirm squash merge method

# Via gh CLI:
gh pr merge <PR_NUMBER> --auto --squash
```

**Typical Flow**:
1. Push PR → CI starts running
2. Code review happens → Reviewer approves
3. All conditions met → Click "Enable auto-merge"
4. GitHub waits for final CI pass → Auto-merges
5. Branch auto-deleted

**Benefit**: No manual merge action needed. Fire and forget.

---

## Phase 3: Webhook Monitoring 🔧

**What It Does**: Listens for GitHub events and alerts you proactively (no manual polling).

**Components**:

### 3a. Webhook Receiver Script

**Location**: `.claude/scripts/webhook-receiver.py` (180 lines)

**What It Listens For**:
- PR opened/reopened/synchronized
- Review submitted (approved/changes requested)
- Comments from reviewers (especially CodeRabbit)
- CI workflow completion (pass/fail)

**What It Does**:
- Prints clear notifications to terminal
- Logs events to `.claude/logs/webhook.log`
- Suggests next action for each event
- Verifies GitHub webhook signatures (security)

**Running It**:
```bash
python3 .claude/scripts/webhook-receiver.py

# Output:
# 🚀 Webhook Receiver Started
# Listening on: http://localhost:9000/webhook
# Logs: .claude/logs/webhook.log
#
# (will stay running, shows events as they arrive)
```

### 3b. Setup Script

**Location**: `.claude/scripts/setup-webhook.sh` (interactive setup)

**What It Does**:
1. Generates webhook secret (for security)
2. Saves secret to `~/.claude/webhook-secret`
3. Provides GitHub webhook configuration instructions
4. Explains local vs remote setup

**Run Setup**:
```bash
bash .claude/scripts/setup-webhook.sh
```

**Output**: Step-by-step instructions to configure webhook in GitHub

### 3c. GitHub Webhook Configuration

**Setup Location**: `https://github.com/YOUR_ORG/YOUR_REPO/settings/hooks`

**Configuration Values**:

```
Payload URL:
  Local:   http://localhost:9000/webhook
  Remote:  https://xxxx-xx-xxx-xxx.ngrok.io/webhook

Content type: application/json

Secret: (generated by setup-webhook.sh)

Events to trigger on:
  ✓ Pull requests
  ✓ Pull request reviews
  ✓ Issue comments
  ✓ Workflow runs

Active: ✓
```

**Remote Access** (if webhook receiver not on same machine):
```bash
# In separate terminal:
ngrok http 9000

# Copy the ngrok URL into GitHub webhook Payload URL
# Example: https://xxxx-xx-xxx-xxx.ngrok.io/webhook
```

### Event Handling

When events arrive, webhook receiver displays:

**PR Opened/Reopened**:
```
============================================================
PR #123 OPENED
Title: Add new feature
URL: https://github.com/...

Action: /pm:issue-start 123 (if not already tracking)
============================================================
```

**PR Approved**:
```
============================================================
✅ PR #123 APPROVED
Reviewer: @john-doe

Action: Check merge conditions (CI passing? All comments resolved?)
============================================================
```

**Code Review Comments** (from CodeRabbit, Copilot):
```
============================================================
🤖 CODE REVIEW from @CodeRabbit on PR #123

Action: /pm:issue-start 123 to address findings
============================================================
```

**CI Passed**:
```
============================================================
✅ CI PASSED on PR #123

Action: Check if ready to merge:
  - CI passing? ✅
  - All comments resolved?
  - 1 approval received?

If YES to all: Enable auto-merge on PR
============================================================
```

**CI Failed**:
```
============================================================
❌ CI FAILED on PR #123

Action: /pm:issue-start 123 to fix CI failure
============================================================
```

---

## Complete Workflow (All Three Phases)

### Before You Start (One-Time Setup)

```bash
# Step 1: Set up webhook
bash .claude/scripts/setup-webhook.sh

# Step 2: Configure webhook in GitHub (instructions printed above)
# Copy webhook secret from ~/.claude/webhook-secret
# Go to GitHub repo settings → Webhooks → Add webhook
# Fill in: Payload URL, Secret, Events
# Save

# Step 3: Start webhook receiver (keep running)
python3 .claude/scripts/webhook-receiver.py
```

### During Development (Every Day)

**1. Start coding on feature**:
```bash
git checkout main && git pull
git checkout -b feature/issue-123-description
# ... make changes ...
```

**2. Before committing** (Phase 1):
```bash
# Pre-commit validation runs automatically (or manually):
bash .claude/scripts/pre-commit-validation.sh

# If passes:
git add <files>
git commit -m "fix: description"
git push origin feature/issue-123-description
```

**3. Create PR and push**:
```bash
gh pr create --title "Fix: description" --body "..."
```

**4. Monitoring happens passively** (Phase 3):
- Webhook receiver is running (separate terminal)
- Events print to terminal as they happen
- You're notified of approvals, CI status, comments
- No manual checking needed

**5. When ready to merge** (Phase 2):
- If all conditions met, enable auto-merge
- GitHub automatically merges when CI passes
- Branch auto-deleted

**6. Done** ✅
- No manual monitoring
- No manual merging
- Zero friction

---

## Time Savings Summary

### Before (Manual Monitoring)
- Monitor PR every 5-10 min manually
- Wait for CI results
- Check for new comments
- Wait for approval
- Click merge button
- Delete branch
- **Total attention**: ~30-60 min per PR

### After (Three-Phase Process)
- Pre-commit validation catches issues locally (before push)
- Webhook receiver alerts you to events
- Auto-merge handles merge automatically
- **Total attention**: ~2 min active time
- **80% reduction in friction**

---

## Troubleshooting

### Issue: Pre-Commit Validation Fails

**Solution**: Read the error message. It tells you exactly how to fix it.

```bash
# Example error:
❌ Found dict-style access on dataclass

# Solution:
Fix: Use hasattr(obj, 'field') and obj.field is not None

# Then:
git add <files>
bash .claude/scripts/pre-commit-validation.sh  # Re-run
```

### Issue: Webhook Receiver Not Receiving Events

**Check**:
1. Is receiver running? (should see "Listening on..." message)
2. Is GitHub webhook configured? (check repo settings → hooks)
3. Is payload URL correct?
4. Check webhook recent deliveries (GitHub shows errors)

**Fix**:
```bash
# Restart receiver
python3 .claude/scripts/webhook-receiver.py

# Check logs
tail -f .claude/logs/webhook.log
```

### Issue: Auto-Merge Not Triggering

**Check**:
1. Are ALL conditions met?
   - CI passing? ✅
   - 1 approval? ✅
   - No requested changes? ✅
   - All comments resolved? ✅

2. Did you click "Enable auto-merge"?

**Fix**:
```bash
# Manually check:
gh pr view <PR_NUMBER>

# Manually merge if needed:
gh pr merge <PR_NUMBER> --squash
```

---

## Reference

**Configuration Files**:
- `.claude/scripts/pre-commit-validation.sh` — Phase 1 validation
- `.claude/scripts/webhook-receiver.py` — Phase 3 receiver
- `.claude/scripts/setup-webhook.sh` — Phase 3 setup
- `~/.claude/webhook-secret` — Phase 3 security

**Documentation**:
- `.claude/rules/pr-workflow-master.md` — Navigation guide
- `.claude/rules/pr-review-response-protocol.md` — Finding categorization
- `.claude/rules/pr-monitoring-protocol.md` — Manual monitoring reference
- `.claude/rules/pr-workflow-state-machine.md` — State definitions

**GitHub Configuration**:
- Repository settings → Webhooks → Configure for Phase 3
- Repository settings → Auto-merge → Already enabled

---

## Next Steps

### To Enable Phase 3 (Webhook Monitoring):

```bash
# 1. Run setup
bash .claude/scripts/setup-webhook.sh

# 2. Follow the instructions to configure GitHub webhook
# (takes ~2 minutes in GitHub settings)

# 3. Start the receiver
python3 .claude/scripts/webhook-receiver.py

# 4. Keep it running in a separate terminal while coding
```

### After Setup is Complete:

You're ready for tomorrow. Start any new PR work with:

```bash
git checkout -b feature/issue-XXX-description
# ... code ...
bash .claude/scripts/pre-commit-validation.sh
git commit
git push
gh pr create
# ... webhook receiver alerts you to events ...
# ... when ready, enable auto-merge ...
# ... GitHub merges automatically ...
```

---

**Result**: Complete, autonomous PR workflow. No manual friction. No monitoring overhead. Clean, fast, efficient.

---

**Last Updated**: 2026-03-06T16:45:00Z
