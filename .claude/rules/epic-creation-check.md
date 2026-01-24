# Epic Creation Check Rule

## Purpose
Prevent duplication of epics by checking for existing epics before creating new ones.

## When This Rule Applies

This rule MUST be followed before:
- Creating a new PRD (`/pm:prd-new`)
- Creating a new epic (`/pm:prd-parse`)
- Decomposing an epic (`/pm:epic-decompose`)
- Any operation that creates new epic planning artifacts

## Check Procedure

### Step 1: List Existing Epics
Before creating any new epic or PRD, always list existing epics:

```bash
# List all epic directories
ls -1 .claude/epics/

# Or get a detailed view
find .claude/epics -name "epic.md" -exec dirname {} \; | sed 's|.claude/epics/||'
```

### Step 2: Review Epic Names and Purposes
For each existing epic found, check:
```bash
# Read epic frontmatter and title
head -15 .claude/epics/{epic-name}/epic.md
```

Look for:
- Epic name/title
- Description/overview
- Related GitHub issue
- Status (open, in-progress, completed)
- Key components or scope

### Step 3: Check for Overlap

**Ask yourself**:
1. Does an epic already exist for this topic?
2. Would the new work fit better as tasks in an existing epic?
3. Is there partial overlap that should be consolidated?
4. Is the existing epic marked as "completed" but could be reopened?

### Step 4: Decision Matrix

| Scenario | Action |
|----------|--------|
| **Exact match found** | Use existing epic, don't create new |
| **Partial overlap** | Ask user: "Extend existing epic X or create separate epic?" |
| **Related but distinct** | Create new epic, document relationship |
| **No match** | Safe to create new epic |
| **Completed epic needs work** | Ask user: "Reopen epic X or create new?" |

## Example Scenarios

### Scenario 1: Exact Match ✅
```
User: "Create epic for unit testing"
Agent finds: .claude/epics/testing-qa/epic.md (status: open)
Action:
  - Show user: "Found existing epic: testing-qa"
  - Ask: "Use existing epic or create new?"
  - Recommend: "Suggest /pm:epic-decompose testing-qa"
```

### Scenario 2: Partial Overlap ⚠️
```
User: "Create epic for database testing"
Agent finds: .claude/epics/testing-qa/epic.md (includes all testing)
Action:
  - Show user: "Found related epic: testing-qa (covers all testing)"
  - Ask: "Add database testing tasks to existing epic or create separate epic?"
  - Recommend: Extend existing epic
```

### Scenario 3: Completed Epic 🔄
```
User: "Create epic for additional testing"
Agent finds: .claude/epics/testing-qa/epic.md (status: completed)
Action:
  - Show user: "Found completed epic: testing-qa"
  - Ask: "Reopen and extend testing-qa or create new epic?"
  - Suggest: Check if new work is Phase 2 of same epic
```

### Scenario 4: No Match 🆕
```
User: "Create epic for desktop app"
Agent finds: No epics related to desktop/UI
Action:
  - Confirm: No overlap found
  - Proceed: Create new epic
```

## Implementation in Commands

### In `/pm:prd-new` Command
Add this step BEFORE creating the PRD:
```bash
echo "Checking for existing epics..."
existing_epics=$(ls -1 .claude/epics/)
echo "Found epics: $existing_epics"
# Show to user and ask if they want to proceed
```

### In `/pm:prd-parse` Command
Add this step BEFORE parsing the PRD into an epic:
```bash
epic_name="${FEATURE_NAME}"
if [ -d ".claude/epics/${epic_name}" ]; then
  echo "⚠️ Epic already exists: ${epic_name}"
  echo "View it with: /pm:epic-show ${epic_name}"
  # Ask user if they want to overwrite or use different name
  exit 1
fi
```

### In `/pm:epic-decompose` Command
Already checks for existing epic directory - this is good!
Enhancement: Also suggest related epics that might need the same decomposition.

## User Communication

When duplication is detected, use this format:

```
⚠️ Found existing epic that may overlap: {epic-name}

Epic: {title}
Status: {status}
GitHub Issue: #{number}
Description: {brief overview}

Options:
1. Use existing epic: /pm:epic-decompose {epic-name}
2. View epic details: /pm:epic-show {epic-name}
3. Create separate epic (if truly distinct)

Which would you like to do?
```

## Benefits

1. **Avoids Duplication**: Prevents multiple epics for the same work
2. **Maintains Coherence**: Keeps related work together
3. **Saves Time**: Leverages existing planning
4. **Cleaner Structure**: Reduces epic sprawl
5. **Better Tracking**: GitHub issues stay consolidated

## Edge Cases

### Multiple Related Epics
Some topics may genuinely need multiple epics (e.g., "Testing Phase 1" vs "Testing Phase 2"):
- Allow this if epics are phased or have different timelines
- Ensure clear naming convention (testing-phase-1, testing-phase-2)
- Document relationship between epics

### Archived/Completed Epics
- Completed epics can be reopened if more work is needed
- Consider creating "V2" epic for major new iterations
- Archive old epic directory if completely superseded

### Ambiguous Names
If epic names are unclear:
- Read the full epic.md file
- Check GitHub issue for context
- Better to ask user than assume

## Validation Checklist

Before creating a new epic, confirm:
- [ ] Listed all existing epics in `.claude/epics/`
- [ ] Read titles and descriptions of potentially related epics
- [ ] Checked GitHub issues for related work
- [ ] Confirmed no exact match exists
- [ ] Confirmed no significant overlap exists
- [ ] If overlap found, discussed with user
- [ ] Documented relationship to other epics (if any)

## Rule Priority

**Priority**: HIGH - Apply this rule BEFORE creating any epic artifacts

**Automation**: This check should become part of the standard preflight for all epic-related commands.

---

**Last Updated**: 2026-01-24T04:18:42Z
**Related Rules**:
- `frontmatter-operations.md` - Epic frontmatter standards
- `github-operations.md` - GitHub issue synchronization
