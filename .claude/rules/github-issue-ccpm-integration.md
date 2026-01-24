# GitHub Issue CCPM Integration Rule

## Purpose
Ensure all GitHub issues are automatically tracked in the CCPM system at creation time to maintain synchronization between GitHub and CCPM project management.

## When This Rule Applies

This rule MUST be followed when:
- Creating new GitHub issues via `gh issue create`
- Issues are created from code review comments
- Technical debt items are identified
- Feature requests are created
- Bug reports are filed

## Required Steps at Issue Creation

### Step 1: Determine Epic Association

Before creating the issue, identify which epic it belongs to:

```bash
# List available epics
ls -1 .claude/epics/

# Common epic mapping:
# - Testing issues → testing-qa
# - Code quality → appropriate feature epic (e.g., phase-3-feature-expansion)
# - New features → feature-specific epic
# - Performance → performance-optimization
# - Documentation → documentation
```

### Step 2: Create Issue with CCPM Context

When creating the issue, include CCPM tracking information in the body:

```bash
gh issue create --repo curdriceaurora/Local-File-Organizer \
  --title "[Category] Issue Title" \
  --body "$(cat <<'EOF'
## Description
[Issue description]

## Files Affected
- path/to/file.py

## CCPM Tracking
**Epic**: epic-name
**Task**: #XX (if applicable)
**Priority**: High/Medium/Low
**Effort Estimate**: X-Y hours

## Related
- PR #XX
- Issue #XX
EOF
)" \
  --label "enhancement"
```

### Step 3: Update Epic Tracking Document

Immediately after creating the issue, update the epic's tracking:

```bash
# Get the issue number
ISSUE_NUM=$(gh issue list --repo curdriceaurora/Local-File-Organizer --limit 1 --json number --jq '.[0].number')

# Update epic tracking file
# Option A: Create/update technical-debt-tracking.md
echo "
**Issue #${ISSUE_NUM}: [Title]**
- **Priority**: Medium
- **Epic**: epic-name
- **Status**: Open
- **Created**: $(date -u +"%Y-%m-%d")
- **GitHub**: https://github.com/curdriceaurora/Local-File-Organizer/issues/${ISSUE_NUM}
- **Effort**: X-Y hours
" >> .claude/epics/[epic-name]/technical-debt-tracking.md

# Option B: Create task file if part of planned work
# Create .claude/epics/[epic-name]/XXX.md with proper frontmatter
```

### Step 4: Add CCPM Comment to Issue

Add a comment linking back to CCPM:

```bash
gh issue comment ${ISSUE_NUM} --repo curdriceaurora/Local-File-Organizer --body "**CCPM Tracking**

Epic: [epic-name]
Task: #XX (if applicable)
Tracking Document: .claude/epics/[epic-name]/tracking-file.md

This issue is tracked in the CCPM system."
```

## Implementation Template

Complete workflow for creating a CCPM-tracked issue:

```bash
#!/bin/bash

# Configuration
REPO="curdriceaurora/Local-File-Organizer"
EPIC_NAME="phase-3-feature-expansion"
TASK_NUM="38"
ISSUE_TITLE="[Code Quality] Fix something"
ISSUE_BODY="Description of issue..."
PRIORITY="Medium"
EFFORT="2-3 hours"

# Step 1: Create the issue
ISSUE_URL=$(gh issue create --repo ${REPO} \
  --title "${ISSUE_TITLE}" \
  --body "$(cat <<EOF
${ISSUE_BODY}

## CCPM Tracking
**Epic**: ${EPIC_NAME}
**Task**: #${TASK_NUM}
**Priority**: ${PRIORITY}
**Effort Estimate**: ${EFFORT}
EOF
)" \
  --label "enhancement")

# Extract issue number
ISSUE_NUM=$(echo ${ISSUE_URL} | grep -oE '[0-9]+$')

# Step 2: Update CCPM tracking document
TRACKING_FILE=".claude/epics/${EPIC_NAME}/technical-debt-tracking.md"
CURRENT_DATE=$(date -u +"%Y-%m-%d")

if [ ! -f "${TRACKING_FILE}" ]; then
  # Create new tracking file
  cat > "${TRACKING_FILE}" <<TRACKING_EOF
---
name: technical-debt-tracking
title: Technical Debt Tracking
epic: ${EPIC_NAME}
created: $(date -u +"%Y-%m-%dT%H:%M:%SZ")
updated: $(date -u +"%Y-%m-%dT%H:%M:%SZ")
status: active
---

# Technical Debt Tracking - ${EPIC_NAME}

## Issues
TRACKING_EOF
fi

# Append issue to tracking file
cat >> "${TRACKING_FILE}" <<ISSUE_EOF

**Issue #${ISSUE_NUM}: ${ISSUE_TITLE}**
- **Priority**: ${PRIORITY}
- **Epic**: ${EPIC_NAME}
- **Task**: ${TASK_NUM}
- **Status**: Open
- **Created**: ${CURRENT_DATE}
- **GitHub**: ${ISSUE_URL}
- **Effort**: ${EFFORT}
ISSUE_EOF

# Step 3: Add CCPM comment to issue
gh issue comment ${ISSUE_NUM} --repo ${REPO} --body "**CCPM Tracking**

Epic: ${EPIC_NAME}
Task: #${TASK_NUM}
Tracking Document: ${TRACKING_FILE}

This issue is tracked in the CCPM system."

# Step 4: Commit CCPM updates
git add "${TRACKING_FILE}"
git commit -m "CCPM: Track issue #${ISSUE_NUM} in ${EPIC_NAME}"

echo "✅ Issue #${ISSUE_NUM} created and tracked in CCPM"
echo "   GitHub: ${ISSUE_URL}"
echo "   CCPM: ${TRACKING_FILE}"
```

## Tracking Document Structure

### Technical Debt Tracking

For code review findings and technical debt:

```markdown
---
name: technical-debt-tracking
title: Technical Debt Tracking for [Epic]
epic: epic-name
created: YYYY-MM-DDTHH:MM:SSZ
updated: YYYY-MM-DDTHH:MM:SSZ
status: active
---

# Technical Debt Tracking - [Epic Name]

## From PR #XX ([Feature Name])

### Category (e.g., Code Quality Issues)

**Issue #XX: [Title]**
- **Priority**: High/Medium/Low
- **Epic**: epic-name
- **Task**: #XX (if applicable)
- **Status**: Open/In Progress/Closed
- **Created**: YYYY-MM-DD
- **GitHub**: https://github.com/[repo]/issues/XX
- **Description**: Brief description
- **Files**: List of affected files
- **Effort**: X-Y hours
- **Dependencies**: Any dependencies

## Summary

**Total Issues**: N
- **High Priority**: N
- **Medium Priority**: N
- **Low Priority**: N

**Total Effort Estimate**: X-Y hours

## Tracking Updates

- **YYYY-MM-DD**: Updates and progress notes
```

### Feature Request Tracking

For new feature requests:

```markdown
**Issue #XX: [Feature Name]**
- **Type**: Feature Request
- **Epic**: epic-name
- **Priority**: High/Medium/Low
- **Status**: Backlog
- **Created**: YYYY-MM-DD
- **GitHub**: https://github.com/[repo]/issues/XX
- **Description**: Brief description
- **Acceptance Criteria**:
  - [ ] Criterion 1
  - [ ] Criterion 2
- **Effort**: X-Y days
- **Dependencies**: List dependencies
```

## Epic Execution Status Updates

When issues are created for an active epic, also update the execution-status.md:

```bash
# Update epic execution status
EXEC_STATUS=".claude/epics/${EPIC_NAME}/execution-status.md"

# Add to "Known Issues" or "Technical Debt" section
echo "
### Technical Debt Identified

- Issue #${ISSUE_NUM}: ${ISSUE_TITLE} (${PRIORITY} priority, ${EFFORT})
  - Tracking: technical-debt-tracking.md
  - Status: Open
" >> ${EXEC_STATUS}
```

## Validation Checklist

Before considering issue creation complete:

- [ ] Issue created in GitHub with proper labels
- [ ] CCPM tracking information in issue body
- [ ] Epic identified and documented
- [ ] Tracking document updated (technical-debt-tracking.md or similar)
- [ ] CCPM comment added to GitHub issue
- [ ] CCPM changes committed to repository
- [ ] Epic execution-status.md updated (if applicable)
- [ ] Issue linked to related PR/commit (if applicable)

## Benefits

1. **Bidirectional Sync**: GitHub ↔ CCPM always synchronized
2. **No Lost Work**: All issues tracked in CCPM from day one
3. **Better Planning**: Effort estimates and priorities captured
4. **Audit Trail**: Clear linkage between issues and epics
5. **Team Visibility**: Everyone sees CCPM context in GitHub

## Common Issue Categories

### Code Quality Issues
- **Epic**: Usually the feature epic where found
- **Labels**: `enhancement`, `code-quality`
- **Tracking**: `technical-debt-tracking.md`

### Feature Requests
- **Epic**: Feature-specific or `backlog`
- **Labels**: `enhancement`, `feature-request`
- **Tracking**: Epic task files or backlog

### Bug Reports
- **Epic**: Related feature epic
- **Labels**: `bug`
- **Tracking**: Bug tracking or epic execution-status

### Documentation
- **Epic**: `documentation`
- **Labels**: `documentation`
- **Tracking**: Documentation epic files

## Rule Priority

**Priority**: HIGH - This rule ensures CCPM and GitHub stay synchronized

**Enforcement**: Required for all issue creation operations

**Automation**: Consider creating a helper script or alias for issue creation that automatically handles CCPM tracking

---

**Last Updated**: 2026-01-24T04:45:24Z
**Related Rules**:
- `github-operations.md` - GitHub CLI operations
- `frontmatter-operations.md` - CCPM metadata standards
- `datetime.md` - Timestamp requirements
