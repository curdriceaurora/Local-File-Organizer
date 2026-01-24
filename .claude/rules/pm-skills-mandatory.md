# PM Skills Mandatory Usage

**CRITICAL RULE:** All project management and GitHub issue operations MUST use PM skills.

## Core Principle

**NEVER manually create or update GitHub issues, PRs, or CCPM tracking documents.**
**ALWAYS use the PM skills designed for these operations.**

## Mandatory PM Skills

### Issue Management

| Task | Required Skill | Manual Operation |
|------|----------------|------------------|
| Start work on issue | `/pm:issue-start {number}` | ❌ FORBIDDEN |
| Update issue progress | `/pm:issue-sync {number}` | ❌ FORBIDDEN |
| Close completed issue | `/pm:issue-close {number}` | ❌ FORBIDDEN |
| View issue details | `/pm:issue-show {number}` | ✅ Optional |
| List issue status | `/pm:issue-status` | ✅ Optional |

### Epic Management

| Task | Required Skill | Manual Operation |
|------|----------------|------------------|
| Decompose epic to tasks | `/pm:epic-decompose {name}` | ❌ FORBIDDEN |
| Sync epic to GitHub | `/pm:epic-sync {name}` | ❌ FORBIDDEN |
| View epic status | `/pm:epic-show {name}` | ✅ Optional |
| Update epic status | `/pm:epic-status {name}` | ❌ FORBIDDEN |

### PRD Management

| Task | Required Skill | Manual Operation |
|------|----------------|------------------|
| Create PRD | `/pm:prd-new {name}` | ❌ FORBIDDEN |
| Parse PRD to epic | `/pm:prd-parse {name}` | ❌ FORBIDDEN |
| Update PRD status | `/pm:prd-status` | ❌ FORBIDDEN |

### Synchronization

| Task | Required Skill | Manual Operation |
|------|----------------|------------------|
| Sync all CCPM state | `/pm:sync` | ❌ FORBIDDEN |
| Import from GitHub | `/pm:import` | ❌ FORBIDDEN |

## Why PM Skills Are Mandatory

### 1. Consistency
- PM skills maintain consistent formatting across all issues
- Standard comment structure for progress updates
- Uniform frontmatter metadata

### 2. CCPM Synchronization
- Automatic sync between local CCPM state and GitHub
- Frontmatter updates with proper timestamps
- Progress calculation and epic status updates

### 3. Audit Trail
- Sync markers prevent duplicate comments
- Timestamp tracking for all operations
- Complete history of changes

### 4. Repository Safety
- Built-in protection against wrong repository operations
- Validation of remote URLs before GitHub operations
- Prevents accidental modifications to template repos

### 5. Data Integrity
- Proper frontmatter validation
- Consistent datetime formatting (ISO 8601)
- Relative path standards enforced

## Forbidden Manual Operations

### ❌ DO NOT Create Tracking Documents Manually

```bash
# WRONG - Manual tracking document
cat > .claude/epics/phase-3/pr92-tracking.md << 'EOF'
---
title: PR #92
status: open
---
# Manual tracking document
EOF
```

Instead, use:
```bash
# RIGHT - Use PM skill
/pm:issue-sync 92
```

### ❌ DO NOT Post GitHub Comments Manually

```bash
# WRONG - Direct GitHub CLI
gh issue comment 43 --body "Progress update"
```

Instead, use:
```bash
# RIGHT - Use PM skill
/pm:issue-sync 43
```

### ❌ DO NOT Create Issues Manually

```bash
# WRONG - Direct GitHub CLI
gh issue create --title "New feature" --body "Description"
```

Instead, use:
```bash
# RIGHT - Use PM skill
# First create local task, then sync
/pm:issue-sync {task_number}
```

### ❌ DO NOT Update Frontmatter Manually

```bash
# WRONG - Manual frontmatter edit
---
updated: 2026-01-24  # Wrong format!
completion: 50%      # Manual guess
---
```

Instead, use:
```bash
# RIGHT - Use PM skill (auto-updates frontmatter)
/pm:issue-sync {issue_number}
```

## Allowed Manual Operations

### ✅ Read-Only GitHub Queries

```bash
# Allowed - Read-only operations
gh issue view 43
gh issue list
gh pr view 92
gh pr list
```

### ✅ Local File Reading

```bash
# Allowed - Reading local CCPM files
cat .claude/epics/phase-3/updates/43/progress.md
ls .claude/epics/
```

### ✅ Git Operations (Non-CCPM)

```bash
# Allowed - Regular git operations for code
git add src/
git commit -m "feat: add feature"
git push
```

## Enforcement

**Claude agents MUST:**
1. Check this rule before ANY GitHub issue operation
2. Use PM skills for ALL issue/epic/PRD management
3. NEVER create tracking documents manually
4. NEVER post GitHub comments without PM skills

**Violations:**
- Creating manual tracking documents → Delete and recreate with PM skills
- Posting direct GitHub comments → Use `/pm:issue-sync` instead
- Manual frontmatter updates → Use PM skills to regenerate

## Quick Reference

**Working on an issue?**
```bash
/pm:issue-start 43    # Start tracking
# ... do work ...
/pm:issue-sync 43     # Sync progress
# ... more work ...
/pm:issue-sync 43     # Sync again
# ... work complete ...
/pm:issue-close 43    # Close issue
```

**Working on an epic?**
```bash
/pm:prd-parse epic-name       # Create epic from PRD
/pm:epic-decompose epic-name  # Break into tasks
/pm:epic-sync epic-name       # Sync to GitHub
/pm:epic-status epic-name     # Update status
```

**Need to view status?**
```bash
/pm:issue-show 43       # View issue details
/pm:issue-status        # List all issues
/pm:epic-show epic-name # View epic details
/pm:status              # View all status
```

## Related Rules

- `.claude/rules/github-operations.md` - GitHub CLI patterns (for PM skill internals)
- `.claude/rules/frontmatter-operations.md` - Frontmatter standards
- `.claude/rules/datetime.md` - Timestamp requirements
- `.claude/rules/path-standards.md` - Path formatting

---

**Remember:** PM skills exist to make your life easier and maintain consistency.
Use them! Don't fight them!
