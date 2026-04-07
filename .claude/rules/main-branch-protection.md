# Main Branch Protection Rules

All changes to `main` must go through a pull request. Direct pushes, force pushes, and deletions are blocked by GitHub branch protection.

## Enforced Rules

| Rule | Status |
|------|--------|
| Require PRs (no direct push) | ✅ Enforced |
| Require 1 reviewer approval | ✅ Enforced |
| Dismiss stale reviews on new commits | ✅ Enforced |
| Block force pushes to main | ✅ Enforced |
| Block main branch deletion | ✅ Enforced |
| Linear history | ❌ Not enforced (merge commits allowed) |

## Correct Workflow

```bash
git checkout -b feature/issue-123-description
# ... make changes ...
git commit -m "feat: description"
git push origin feature/issue-123-description
gh pr create
# After approval + CI:
gh pr merge <PR> --squash
```

## Emergency Bypass

Admin-only. Never bypass without explicit authorization. See `gh api repos/<owner>/<repo>/branches/main/protection` for config management.

---
**Last Updated**: 2026-04-07
