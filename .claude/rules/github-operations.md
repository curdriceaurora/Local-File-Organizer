# GitHub Operations Rule

Standard patterns for GitHub operations using PM skills and CLI.

## ⚠️ MANDATORY: Use PM Skills for Issue Operations

**NEVER manually create or update GitHub issues using `gh` commands directly.**
**ALWAYS use the PM skills instead.**

### Required PM Skills

| Operation | Use This Skill | Direct `gh` Command |
|-----------|----------------|---------------------|
| Create new issue from task | `/pm:issue-sync {task_number}` | ❌ **FORBIDDEN** |
| Update existing issue | `/pm:issue-sync {issue_number}` | ❌ **FORBIDDEN** |
| Post progress updates | `/pm:issue-sync {issue_number}` | ❌ **FORBIDDEN** |
| Close completed issue | `/pm:issue-close {issue_number}` | ❌ **FORBIDDEN** |
| Start work on issue | `/pm:issue-start {issue_number}` | ❌ **FORBIDDEN** |
| View issue status | `/pm:issue-show {issue_number}` | ✅ Allowed |
| List issues | `/pm:issue-status` | ✅ Allowed |

### Why PM Skills Are Mandatory

1. **Consistent Tracking**: PM skills maintain local CCPM state in sync with GitHub
2. **Audit Trail**: Automatic progress tracking and sync markers
3. **Frontmatter Management**: Proper timestamp and metadata updates
4. **Repository Safety**: Built-in protection against wrong repo operations
5. **Standardized Format**: Consistent comment formatting across all issues

### When Direct `gh` Commands Are Allowed

**Read-only operations only:**
- `gh issue view {number}` - View issue details
- `gh issue list` - List issues
- `gh pr view {number}` - View PR details
- `gh pr list` - List PRs

**Everything else MUST use PM skills.**

### Example: Wrong vs Right

❌ **WRONG - Manual GitHub operations:**
```bash
# Creating issue manually
gh issue create --title "New feature" --body "Description"

# Updating issue manually
gh issue comment 43 --body "Progress update"

# This bypasses CCPM tracking!
```

✅ **RIGHT - Using PM skills:**
```bash
# Start working on an issue (creates local tracking)
/pm:issue-start 43

# Sync progress to GitHub (posts comment + updates CCPM)
/pm:issue-sync 43

# Close issue when complete (updates CCPM + closes on GitHub)
/pm:issue-close 43
```

## Standard Patterns for PM Skills (Reference Only)

## CRITICAL: Repository Protection (For PM Skill Internal Use)

**NOTE:** This section is for PM skill implementation only. End users should use PM skills, not these commands directly.

**Before ANY direct GitHub operation that creates/modifies issues or PRs:**

```bash
# Check if remote origin is the CCPM template repository
remote_url=$(git remote get-url origin 2>/dev/null || echo "")
if [[ "$remote_url" == *"automazeio/ccpm"* ]] || [[ "$remote_url" == *"automazeio/ccpm.git"* ]]; then
  echo "❌ ERROR: You're trying to sync with the CCPM template repository!"
  echo ""
  echo "This repository (automazeio/ccpm) is a template for others to use."
  echo "You should NOT create issues or PRs here."
  echo ""
  echo "To fix this:"
  echo "1. Fork this repository to your own GitHub account"
  echo "2. Update your remote origin:"
  echo "   git remote set-url origin https://github.com/YOUR_USERNAME/YOUR_REPO.git"
  echo ""
  echo "Or if this is a new project:"
  echo "1. Create a new repository on GitHub"
  echo "2. Update your remote origin:"
  echo "   git remote set-url origin https://github.com/YOUR_USERNAME/YOUR_REPO.git"
  echo ""
  echo "Current remote: $remote_url"
  exit 1
fi
```

This check MUST be performed in ALL commands that:
- Create issues (`gh issue create`)
- Edit issues (`gh issue edit`)
- Comment on issues (`gh issue comment`)
- Create PRs (`gh pr create`)
- Any other operation that modifies the GitHub repository

## Authentication (Reference)

**NOTE:** PM skills handle authentication checks automatically.

For direct commands (read-only operations), don't pre-check authentication:

```bash
gh {command} || echo "❌ GitHub CLI failed. Run: gh auth login"
```

## Common Operations (Reference for PM Skills Implementation)

**NOTE:** These patterns are for PM skill internal implementation only.
**Users must call PM skills instead of using these commands directly.**

### Get Issue Details (Read-only - Allowed)
```bash
gh issue view {number} --json state,title,labels,body
```

### Create Issue (FORBIDDEN - Use /pm:issue-sync instead)
```bash
# ❌ DO NOT USE THIS DIRECTLY
# Use /pm:issue-sync {task_number} instead
#
# This is shown for PM skill implementation reference only:
remote_url=$(git remote get-url origin 2>/dev/null || echo "")
REPO=$(echo "$remote_url" | sed 's|.*github.com[:/]||' | sed 's|\.git$||')
[ -z "$REPO" ] && REPO="user/repo"
gh issue create --repo "$REPO" --title "{title}" --body-file {file} --label "{labels}"
```

### Update Issue (FORBIDDEN - Use /pm:issue-sync instead)
```bash
# ❌ DO NOT USE THIS DIRECTLY
# Use /pm:issue-sync {issue_number} instead
#
# This is shown for PM skill implementation reference only:
gh issue edit {number} --add-label "{label}" --add-assignee @me
```

### Add Comment (FORBIDDEN - Use /pm:issue-sync instead)
```bash
# ❌ DO NOT USE THIS DIRECTLY
# Use /pm:issue-sync {issue_number} instead
#
# This is shown for PM skill implementation reference only:
remote_url=$(git remote get-url origin 2>/dev/null || echo "")
REPO=$(echo "$remote_url" | sed 's|.*github.com[:/]||' | sed 's|\.git$||')
[ -z "$REPO" ] && REPO="user/repo"
gh issue comment {number} --repo "$REPO" --body-file {file}
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
