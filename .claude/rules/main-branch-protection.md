# Main Branch Protection Rules

**Purpose**: Prevent accidental direct commits/pushes to main. All changes must go through pull requests.

**Status**: ✅ Enforced on GitHub

---

## Protection Rules

| Rule | Status | Details |
|------|--------|---------|
| **Require PRs** | ✅ Enforced | Cannot push directly to main |
| **Require Approval** | ✅ Enforced | 1 reviewer approval required |
| **Dismiss Stale Reviews** | ✅ Enforced | Approvals reset when new commits added |
| **Block Force Pushes** | ✅ Enforced | Cannot `git push --force` to main |
| **Block Deletions** | ✅ Enforced | Cannot delete main branch |
| **Linear History** | ❌ Not enforced | Merge commits allowed |

---

## What This Prevents

### ❌ This will be rejected:
```bash
git checkout main
git commit -m "direct commit"
git push origin main
# ERROR: protected branch
```

### ❌ This will be rejected:
```bash
git checkout main
git push origin --force main
# ERROR: force pushes blocked
```

### ❌ This will be rejected:
```bash
git branch -D main
git push origin :main
# ERROR: cannot delete main
```

---

## Correct Workflow

### ✅ This is the only way to merge:

```bash
# 1. Create feature branch
git checkout -b feature/issue-123-description

# 2. Make changes and commit
git add .
git commit -m "feat: description"
git push origin feature/issue-123-description

# 3. Create PR on GitHub
gh pr create --title "Feat: description"

# 4. Get approval
# (CodeRabbit or human reviewer approves)

# 5. Merge through GitHub UI
# (click "Merge pull request" button)
# OR use CLI
gh pr merge 123 --auto --squash
```

---

## Emergency Bypass (For Admins Only)

If you're an admin and absolutely must bypass protection:

```bash
# Temporarily disable protection
REPO=$(git remote get-url origin | sed 's|.*github.com/||' | sed 's|\.git$||')
gh api repos/$REPO/branches/main/protection -X DELETE

# Make your change
git push origin main

# Re-enable protection
gh api repos/$REPO/branches/main/protection -X PUT \
  --input /tmp/branch_protection.json
```

**⚠️ Do not do this lightly. Protection exists for a reason.**

---

## How It Protects You

### Before (Unprotected):
- Could accidentally commit to main
- Direct pushes bypassed all reviews
- No approval requirement
- History could be force-pushed over

### After (Protected):
- Must create PR for any changes
- Requires at least 1 approval
- Cannot force-push to overwrite history
- Clear audit trail of all changes
- Automated tools (CodeRabbit) can review

---

## Configuration Details

Applied via GitHub API:

```json
{
  "required_pull_request_reviews": {
    "dismiss_stale_reviews": true,
    "require_code_owner_reviews": false,
    "required_approving_review_count": 1
  },
  "required_status_checks": null,
  "restrictions": null,
  "enforce_admins": false,
  "required_linear_history": false,
  "allow_force_pushes": false,
  "allow_deletions": false
}
```

---

## Testing Branch Protection

To verify it's working:

```bash
# Try to push directly to main (should fail)
git checkout main
echo "test" > test.txt
git add test.txt
git commit -m "test"
git push origin main

# Expected error:
# remote: fatal: refusing to allow an admins excluded user to create/update to protected ref main
# OR
# remote: error: GH006: Protected branch rule violations found
```

---

**Last Updated**: 2026-03-06
**Type**: GitHub Branch Protection Configuration
**Scope**: Protects main branch from accidental commits
