# GitHub Operations Rule

Standard patterns for GitHub CLI operations across all commands.

## Project Context - Personal Fork

**This is a personal fork/standalone project:**

```bash
# Git remotes (already configured):
origin   = https://github.com/curdriceaurora/Local-File-Organizer.git   # YOUR FORK (all work here)
upstream = https://github.com/QiuYannnn/Local-File-Organizer.git        # Original repo (read-only)
```

**CRITICAL RULES**:
1. ✅ **All PRs go to YOUR FORK**: `curdriceaurora/Local-File-Organizer`
2. ✅ **All issues go to YOUR FORK**: `curdriceaurora/Local-File-Organizer`
3. ✅ **All commits push to origin**: Your fork
4. ❌ **NEVER push to upstream**: Original repo is read-only reference
5. ✅ **PRs are within your fork**: feature branch → main (same repo)

## Repository Constants

```bash
# Use these constants in all GitHub operations:
OWNER="curdriceaurora"
REPO="Local-File-Organizer"
FULL_REPO="curdriceaurora/Local-File-Organizer"

# Always specify repo explicitly:
gh issue create --repo "$FULL_REPO" ...
gh pr create --repo "$FULL_REPO" --base main --head feature-branch ...
```

## No Upstream Operations

**DO NOT**:
- Create PRs to upstream (QiuYannnn/Local-File-Organizer)
- Push branches to upstream
- Create issues on upstream
- This is a standalone personal project

**Upstream is only for**:
- Reading original repo for reference (if needed)
- Pulling updates (optional, only if user requests)

## Authentication

**Don't pre-check authentication.** Just run the command and handle failure:

```bash
gh {command} || echo "❌ GitHub CLI failed. Run: gh auth login"
```

## Common Operations

### Get Issue Details
```bash
# Always specify your fork
FULL_REPO="curdriceaurora/Local-File-Organizer"
gh issue view {number} --repo "$FULL_REPO" --json state,title,labels,body
```

### Create Issue
```bash
# Always specify your fork explicitly
FULL_REPO="curdriceaurora/Local-File-Organizer"
gh issue create --repo "$FULL_REPO" \
  --title "{title}" \
  --body-file {file} \
  --label "{labels}"
```

### Update Issue
```bash
# Update issue in your fork
FULL_REPO="curdriceaurora/Local-File-Organizer"
gh issue edit {number} --repo "$FULL_REPO" \
  --add-label "{label}" \
  --add-assignee @me
```

### Add Comment
```bash
# Add comment in your fork
FULL_REPO="curdriceaurora/Local-File-Organizer"
gh issue comment {number} --repo "$FULL_REPO" \
  --body-file {file}
```

### Create Pull Request
```bash
# PR within your fork: feature branch → main
FULL_REPO="curdriceaurora/Local-File-Organizer"
gh pr create --repo "$FULL_REPO" \
  --base main \
  --head feature-branch-name \
  --title "[Type] Brief description" \
  --body-file pr-body.md
```

## Error Handling

If any gh command fails:
1. Show clear error: "❌ GitHub operation failed: {command}"
2. Suggest fix: "Run: gh auth login" or check issue number
3. Don't retry automatically

## Important Notes

- **ALWAYS** check remote origin before ANY write operation to GitHub
- Trust that gh CLI is installed and authenticated
- Use --json for structured output when parsing
- Keep operations atomic - one gh command per action
- Don't check rate limits preemptively
