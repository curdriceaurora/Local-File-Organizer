# Permissions & Workflows

## 🚀 Agent Permissions

### Auto-Approved
- ✅ All file operations (read, write, delete) in `~/Projects/`
- ✅ All bash commands & git operations (commit, push, branch)
- ✅ All test executions (via `test-and-log.sh`)
- ✅ Modifying configuration files (`pyproject.toml`, etc.)

### Prohibited
- ❌ Pushing directly to `main` (Use PRs)
- ❌ Force pushing or modifying `.git/` directly
- ❌ Committing secrets or API keys
- ❌ Using placeholder dates (Must use `date -u`)

## 🔄 Git & CCPM Workflow

### Git Standards
- **Feature Branches**: `feature/task-XX-description`
- **Sprint Branches**: `sprint/YYYY-qN-weeksN-N`
- **Worktrees**: Create `../worktree-name` for parallel work.
- **Remote Check**: ALWAYS check `git remote get-url origin` before write ops.

### CCPM Maintenance (Required)
You must create/update daily logs in `.claude/epics/sprint-*/daily-logs/`.
- **Morning**: Check yesterday's log.
- **Evening**: Create daily log with REAL progress data.
- **Sync**: Keep GitHub issues 100% synced with local progress using PM tools.

### Frontmatter Standards
```yaml
---
name: descriptive-name
created: 2026-01-23T09:00:00Z  # Fixed creation time
updated: 2026-01-23T14:30:00Z  # Updated on every edit
status: backlog|in-progress|completed
---
