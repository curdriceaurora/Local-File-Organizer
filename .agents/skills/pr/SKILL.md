# /pr - Complete PR Lifecycle Skill

Automates the full pull request workflow from feature branch through merge.

## Usage

```
/pr fix/issue-123-description
```

## Workflow (Automated, All Steps Required)

1. **Ensure on feature branch** (NEVER main)
   - Verify branch name matches `feature/*` or `fix/*` pattern
   - If not, create a new branch: `git checkout -b fix/issue-XXX-description`

2. **Run all tests**
   - Execute full test suite: `pytest tests/ -x -q`
   - If tests fail, fix issues and re-run
   - Do NOT proceed until all tests pass

3. **Run pre-commit checks**
   - `ruff check --fix .` and `ruff format .`
   - Fix any remaining violations
   - Do NOT proceed until all checks pass

4. **Commit changes**
   - Use conventional commit message format
   - Reference the issue number in the message
   - Example: `git commit -m "fix: address issue #123 - description"`

5. **Push to branch**
   - Push immediately: `git push origin <branch>`
   - Never push directly to main

6. **Create PR**
   - Use `gh pr create` with title and body
   - Include summary of changes
   - Link to related issues
   - Example title: "fix: description of fix (#123)"

7. **Monitor CI status**
   - Wait for GitHub Actions to complete
   - If any checks fail, diagnose and push fixes
   - Do NOT declare done until CI is green

8. **Address review comments** (if any)
   - Read all comments
   - Apply fixes, test, and commit
   - Push changes
   - Reply to comments and resolve threads
   - Wait for second CI pass

9. **Merge PR**
   - Use squash merge for cleaner history
   - Confirm all checks are green
   - Verify review approvals (if required)

## Critical Rules

- ❌ NEVER skip test execution
- ❌ NEVER push directly to main
- ❌ NEVER declare "done" until all steps verified
- ❌ NEVER merge with failing CI checks
- ✅ DO commit after every change
- ✅ DO push after every commit
- ✅ DO wait for full CI to pass

## Example Output

```
✅ Branch: fix/issue-620-codecov
✅ Tests: All 10,600 tests passed (127s)
✅ Lint: ruff check clean
✅ Commit: "fix: skip codecov on PR events"
✅ Push: origin/fix/issue-620-codecov
✅ PR: https://github.com/curdriceaurora/Local-File-Organizer/pull/622
✅ CI: All checks passing
Ready to merge
```
