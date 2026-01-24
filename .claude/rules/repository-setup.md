# Repository Setup - Personal Fork

## Quick Reference

**This is a personal fork/standalone project. All work stays in YOUR repository.**

## Git Remotes

```bash
# Current configuration (verify with: git remote -v)
origin   = https://github.com/curdriceaurora/Local-File-Organizer.git   # YOUR FORK
upstream = https://github.com/QiuYannnn/Local-File-Organizer.git        # Original (read-only)
```

## Critical Rules

### ✅ DO (Always)

1. **Push to origin (your fork)**
   ```bash
   git push origin feature-branch-name
   git push origin main
   ```

2. **Create PRs within your fork**
   ```bash
   # PR: feature-branch → main (same repo)
   FULL_REPO="curdriceaurora/Local-File-Organizer"
   gh pr create --repo "$FULL_REPO" \
     --base main \
     --head feature-branch-name
   ```

3. **Create issues in your fork**
   ```bash
   FULL_REPO="curdriceaurora/Local-File-Organizer"
   gh issue create --repo "$FULL_REPO" \
     --title "Issue title" \
     --body "Issue description"
   ```

4. **Always specify your repo explicitly**
   ```bash
   # In all gh commands
   FULL_REPO="curdriceaurora/Local-File-Organizer"
   gh issue list --repo "$FULL_REPO"
   gh pr list --repo "$FULL_REPO"
   gh issue view 42 --repo "$FULL_REPO"
   ```

### ❌ DON'T (Never)

1. **Never push to upstream**
   ```bash
   # ❌ WRONG - Never do this
   git push upstream any-branch
   ```

2. **Never create PRs to upstream**
   ```bash
   # ❌ WRONG - This would create PR to original repo
   gh pr create --repo "QiuYannnn/Local-File-Organizer" ...
   ```

3. **Never create issues on upstream**
   ```bash
   # ❌ WRONG - Issues go to your fork only
   gh issue create --repo "QiuYannnn/Local-File-Organizer" ...
   ```

4. **Never use upstream as base for PRs**
   ```bash
   # ❌ WRONG - PR should be within your fork
   gh pr create --base upstream/main --head origin/feature
   ```

## Typical Workflow

### Creating a Feature

```bash
# 1. Start from main in your fork
git checkout main
git pull origin main

# 2. Create feature branch
git checkout -b feature/task-42-audio-model

# 3. Make changes, commit
git add ...
git commit -m "Task #42: Audio Model implementation"

# 4. Push to your fork (origin)
git push origin feature/task-42-audio-model

# 5. Create PR in your fork (feature → main, same repo)
FULL_REPO="curdriceaurora/Local-File-Organizer"
gh pr create --repo "$FULL_REPO" \
  --base main \
  --head feature/task-42-audio-model \
  --title "[Feature] Task #42: Audio transcription" \
  --body "Description of changes"
```

### Merging a Feature

```bash
# After PR is approved:

# 1. Merge PR via GitHub UI or:
gh pr merge {pr-number} --repo "$FULL_REPO" --squash

# 2. Update local main
git checkout main
git pull origin main

# 3. Delete feature branch (optional)
git branch -d feature/task-42-audio-model
git push origin --delete feature/task-42-audio-model
```

## Why This Setup?

**Personal fork advantages:**
- Full control over your repository
- Can experiment without affecting upstream
- Clean commit history in your fork
- Can customize for your needs
- Independent from upstream changes

**Upstream as reference:**
- Pull updates if needed (optional)
- Reference for original implementation
- Not actively syncing unless you choose to

## Syncing with Upstream (Optional)

**Only if you want to pull upstream changes:**

```bash
# Fetch upstream updates
git fetch upstream

# Merge into your main (optional, only if you want updates)
git checkout main
git merge upstream/main

# Resolve conflicts if any, then push to your fork
git push origin main
```

**Note**: This is OPTIONAL. You can keep your fork completely independent.

## Constants for Scripts

Use these constants in all GitHub operations:

```bash
# In all scripts and commands:
OWNER="curdriceaurora"
REPO="Local-File-Organizer"
FULL_REPO="curdriceaurora/Local-File-Organizer"

# Example usage:
gh issue create --repo "$FULL_REPO" ...
gh pr create --repo "$FULL_REPO" --base main --head feature-branch ...
gh issue list --repo "$FULL_REPO"
```

## Verification Commands

```bash
# Verify your current setup:
echo "=== Git Remotes ==="
git remote -v

echo -e "\n=== Current Branch ==="
git branch --show-current

echo -e "\n=== Remote Branches ==="
git branch -r | head -10

echo -e "\n=== GitHub CLI Default Repo ==="
gh repo view

# Should show:
# origin   = curdriceaurora/Local-File-Organizer
# upstream = QiuYannnn/Local-File-Organizer (optional)
```

## Troubleshooting

### If you accidentally push to upstream:

**Don't panic!** Upstream is likely protected and will reject the push.

```bash
# Verify where you pushed
git log --oneline origin/main | head -5
git log --oneline upstream/main | head -5

# If you need to undo a push to origin:
git push origin +main^:main  # Revert last commit on origin/main
```

### If PRs go to wrong repo:

**Always specify --repo explicitly:**

```bash
# Check open PRs
gh pr list --repo "curdriceaurora/Local-File-Organizer"

# If PR is on wrong repo, close it and recreate:
gh pr close {number} --repo "wrong-repo"
gh pr create --repo "curdriceaurora/Local-File-Organizer" ...
```

## Summary

**Golden Rules:**
1. ✅ All commits → origin (your fork)
2. ✅ All PRs → within your fork (feature → main)
3. ✅ All issues → your fork
4. ❌ Never touch upstream (read-only)
5. ✅ Always use `--repo curdriceaurora/Local-File-Organizer`

**This is YOUR project. Work freely in YOUR repository.** 🚀
