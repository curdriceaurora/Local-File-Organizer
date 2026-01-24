# Pull Request Strategy

## Project Context - Personal Fork

**This is a personal fork/standalone project:**
- Repository: `curdriceaurora/Local-File-Organizer`
- All PRs are **within your own fork**: `feature-branch → main` (same repo)
- **NOT** creating PRs to upstream: `QiuYannnn/Local-File-Organizer` is read-only reference
- This is YOUR project, work stays in YOUR repository

## Core Principle

**PRs are created at the CCPM task/epic level, NOT at sprint level.**

This ensures:
- Manageable PR sizes (< 1,000 LOC per PR)
- Focused reviews on specific features
- Faster merge cycles
- Easier rollback if issues found
- Better commit history granularity

## PR Granularity

### ✅ Create PR For:

1. **Individual Tasks** (when complete)
   - Task #42: Audio Model implementation
   - Task #43: Audio format support
   - Issue #50: Preference tracking database

2. **Small Epics** (when all tasks complete)
   - Epic: Phase 3 Audio Processing (if < 1,500 LOC)
   - Epic: Basic deduplication (if < 1,500 LOC)

3. **Technical Debt Fixes** (by category)
   - Fix: Input validation across codebase
   - Fix: File locking for concurrent access
   - Fix: Misleading format support claims

4. **Documentation Updates** (standalone)
   - Docs: Update API reference
   - Docs: Add migration guide

### ❌ Don't Create PR For:

1. **Entire Sprints** (too large)
   - ❌ Sprint 2026 Q1 Complete (would be 10,000+ LOC)

2. **Multiple Unrelated Features** (hard to review)
   - ❌ Audio + Preferences + Video + PARA (mixed concerns)

3. **Incomplete Work** (not ready)
   - ❌ Half-implemented features
   - ❌ Code without tests

## PR Size Guidelines

| Size | LOC Range | Review Time | Acceptable? |
|------|-----------|-------------|-------------|
| **Tiny** | < 100 | 10 min | ✅ Ideal |
| **Small** | 100-300 | 30 min | ✅ Good |
| **Medium** | 300-800 | 1 hour | ✅ Acceptable |
| **Large** | 800-1,500 | 2-3 hours | ⚠️ Limit to epics |
| **Huge** | 1,500+ | 4+ hours | ❌ Split into smaller PRs |

## PR Workflow

### When to Create PR

**Trigger Events**:
1. Task is complete with tests passing
2. Documentation is updated
3. CCPM daily log updated
4. GitHub issue ready to close
5. Code reviewed internally (if applicable)

**Before Creating PR**:
```bash
# 1. Ensure all tests pass
pytest

# 2. Ensure code quality
ruff check src/
mypy src/

# 3. Update CCPM
# - Mark task as complete in daily log
# - Update execution-status.md

# 4. Create descriptive commit
git commit -m "Task #42: Audio Model implementation

Complete AudioModel with faster-whisper integration..."

# 5. Push to feature branch
git push origin feature/task-42-audio-model
```

### PR Template

```markdown
## Task/Epic

**CCPM Reference**: Task #42 / Epic: Phase 3 Audio

**GitHub Issue**: Closes #42

## Summary

Brief description of what this PR accomplishes (2-3 sentences).

## Changes

- **Added**: List new files/features
- **Modified**: List changed files
- **Removed**: List deleted code

## Testing

- [x] Unit tests added (X new tests)
- [x] All tests passing locally
- [x] Manual testing complete
- [x] Coverage: XX%

## Documentation

- [x] Code docstrings updated
- [x] README updated (if applicable)
- [x] CCPM daily log updated
- [x] GitHub issue updated

## Review Checklist

- [x] Code follows style guidelines
- [x] No TODOs or FIXMEs left
- [x] Error handling implemented
- [x] Type hints on all functions
- [x] No security vulnerabilities introduced

## Screenshots/Demo

(If applicable)

---

🤖 Generated with [Claude Code](https://claude.com/claude-code)
```

### PR Naming Convention

**Format**: `[Type] Task #XX: Brief description`

**Examples**:
- `[Feature] Task #42: Audio transcription with faster-whisper`
- `[Fix] Issue #75: Add file locking for concurrent access`
- `[Epic] Phase 3: Audio processing complete`
- `[Docs] Update API reference for v2.0`
- `[Refactor] Extract common validation logic`

### PR Labels

Apply appropriate labels:
- `type: feature` - New functionality
- `type: bugfix` - Bug fixes
- `type: refactor` - Code improvements
- `type: docs` - Documentation only
- `type: test` - Test additions
- `size: small` - < 300 LOC
- `size: medium` - 300-800 LOC
- `size: large` - 800-1,500 LOC
- `priority: high` - Needs quick review
- `sprint: 2026-q1` - Sprint tracking

## PR Review Process

### Self-Review Before Creating PR

1. **Read your own diff** completely
2. **Check for**:
   - Debug code left in
   - Commented-out code
   - Console.log/print statements
   - Hardcoded values
   - Missing error handling
3. **Verify**:
   - All tests pass
   - Code coverage adequate
   - Documentation complete
   - CCPM updated

### After PR Created

1. **Request Review** (if team members available)
2. **Link to GitHub Issue** (use "Closes #XX")
3. **Update CCPM**: Note PR created in daily log
4. **Monitor CI**: Ensure automated checks pass

### Merging

**Merge Strategy**: Squash and merge (default)
- Keeps main branch history clean
- One commit per PR on main
- Detailed history preserved in PR

**After Merge**:
1. Delete feature branch
2. Update CCPM execution-status.md
3. Close linked GitHub issues
4. Update sprint tracking

## Sprint Integration

### During Sprint (Days 1-28)

**Daily/Weekly PRs**:
- Create PR when task completes
- Don't wait for sprint end
- Merge approved PRs continuously

**Example Timeline**:
- Day 2: PR for Task #42 (Audio Model)
- Day 2: PR for Issue #50 (Preference DB)
- Day 3: PR for Task #43 (Audio formats)
- Day 4: PR for Issue #51 (Pattern learning)
- ...
- Day 28: Final sprint summary PR (documentation only)

### Sprint Branch Usage

**Sprint branch** (`sprint/2026-q1-weeks1-4`):
- **Purpose**: Integration and testing branch
- **NOT**: The branch that gets PR'd to main

**Workflow**:
```bash
# Feature branches created from main (in YOUR fork)
git checkout main
git checkout -b feature/task-42-audio-model

# Work and commit
git add ...
git commit -m "Task #42: ..."

# Push to origin (your fork)
git push origin feature/task-42-audio-model

# Create PR to main in YOUR fork (same repo)
FULL_REPO="curdriceaurora/Local-File-Organizer"
gh pr create --repo "$FULL_REPO" \
  --base main \
  --head feature/task-42-audio-model \
  --title "[Feature] Task #42: Audio Model" \
  --body-file pr-body.md
```

**Sprint branch is for**:
- Collecting commits during sprint
- Daily work tracking
- Integration testing
- Worktree coordination

**Individual PRs go**:
- From feature branch → main
- As soon as task is complete
- Small, focused changes

## Multi-Task PRs

When multiple small related tasks completed:

**Acceptable to Combine**:
- Multiple bug fixes in same module
- Related documentation updates
- Small refactoring tasks

**Example**:
```markdown
[Fix] Issues #75, #77, #78: Technical debt batch

- #75: File locking for backup manifest
- #77: Remove misleading .doc support
- #78: Add chunk_size validation

Total: ~400 LOC, 3 related fixes
```

**Maximum**: 3-4 tiny tasks per PR

## Special Cases

### Hotfixes

Critical bugs found in production:
1. Create branch from main: `hotfix/critical-bug`
2. Fix with minimal changes
3. Fast-track PR review
4. Merge immediately
5. Backport to sprint branch if needed

### Breaking Changes

If PR introduces breaking changes:
1. Label: `breaking-change`
2. Document in CHANGELOG
3. Update migration guide
4. Notify team
5. Consider feature flag

### Large Epics

If epic > 1,500 LOC, split into:
1. PR 1: Core infrastructure
2. PR 2: Feature implementation
3. PR 3: Tests and documentation
4. PR 4: Integration and examples

Each PR should be independently reviewable.

## Enforcement

**CCPM Integration**:
- Daily log must note when PR created
- Execution status updated after merge
- GitHub sync tracker updated
- Sprint velocity measured by merged PRs

**Violations to Avoid**:
- ❌ Waiting until Day 28 to create first PR
- ❌ Creating PR with 10+ files changed unrelated
- ❌ Merging without tests
- ❌ Not updating CCPM after PR merge

## Benefits

This strategy provides:
- **Faster feedback**: Reviews happen within hours, not days
- **Lower risk**: Small changes easier to test and rollback
- **Better history**: Clear commit messages per feature
- **Continuous integration**: Features merge as completed
- **Team efficiency**: Multiple PRs reviewed in parallel
- **Quality control**: Focused reviews catch more issues

---

**Summary**: Create PRs at task/epic granularity (< 1,000 LOC), merge continuously throughout sprint, don't dump entire sprint in one massive PR.
