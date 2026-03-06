# /checklist - Delivery Checklist Execution Skill

Manages delivery checklist workflows with strict step verification and self-audit.

## Usage

```
/checklist
```

Executes all unchecked items in the active delivery checklist file.

## Workflow (Mandatory Step Verification)

1. **Read the delivery checklist**
   - Locate active checklist file in `.claude/` directory
   - Parse all items with their status (checked/unchecked)

2. **For each unchecked item:**
   a. **Print the item**
      - "Working on item #X: [item name]"

   b. **Execute the item**
      - Follow the implementation steps in the item
      - Implement changes across all affected files

   c. **Verify before marking complete**
      - Run all relevant tests
      - Confirm tests pass
      - Check that files were created/modified
      - Verify code review is done (if required)
      - Confirm coverage gates pass (if applicable)
      - If verification fails, fix the issue before proceeding

   d. **Mark complete ONLY after verification**
      - Update checklist: `- [x] Item name`
      - Commit changes: `git add checklist.md && git commit -m "checklist: complete item X"`
      - Push: `git push origin <branch>`

3. **After all items are complete:**
   - Run final self-audit
   - Re-read the entire checklist
   - Verify every item has `[x]` and was actually completed
   - If any item is incomplete or verification failed, fix it
   - Do NOT declare done if audit fails

4. **Commit final updates**
   - `git commit -m "checklist: all items complete and verified"`
   - `git push origin <branch>`

## Item Format in Checklist

```markdown
# Delivery Checklist - Phase 3

## Tier 1: Core Features
- [ ] Implement search API endpoint
  - Run full test suite
  - Coverage must be ≥90%
  - Deploy to staging

- [x] Add database schema
  - Schema created in migrations/
  - All tests pass
  - PR reviewed and merged
```

## Critical Rules

- ❌ NEVER skip the code review step
- ❌ NEVER skip the coverage gate step
- ❌ NEVER mark items complete without verification
- ❌ NEVER declare "All done" without final self-audit
- ❌ NEVER skip the self-audit step
- ✅ DO verify tests actually pass before marking complete
- ✅ DO commit and push after each item
- ✅ DO verify coverage gates if applicable
- ✅ DO perform final self-audit before declaring done

## Verification Checklist Per Item

For each item, verify:
- [ ] Tests are written and passing (not skipped)
- [ ] Code review comments addressed
- [ ] Coverage gates pass (if required)
- [ ] Files exist and contain expected changes
- [ ] No lint violations
- [ ] Commit was created and pushed
- [ ] Item is truly complete (not placeholder)

## Example Output

```
📋 Delivery Checklist - Phase 3

Working on item #1: Implement search API endpoint
  ✅ Changes complete
  ✅ Tests written (47 tests, 0 skipped)
  ✅ All tests passing (2.3s)
  ✅ Coverage: 94% (meets ≥90% gate)
  ✅ Code review: All comments addressed
  ✅ Commit: "feat: add search API endpoint (#215)"
  ✅ Pushed to feature/phase-3

Working on item #2: Add rate limiting
  ✅ Changes complete
  ✅ Tests: 15 tests, all passing
  ✅ Coverage: 92%
  ✅ Commit: "feat: implement rate limiting (#216)"
  ✅ Pushed

🔍 Self-Audit:
  ✅ Item #1 marked complete and verified
  ✅ Item #2 marked complete and verified
  ✅ Item #3 marked complete and verified
  ✅ All items have tests
  ✅ All tests passing
  ✅ Coverage ≥90%

✨ All checklist items complete and verified. Ready to merge.
```

## No Early Exits

Do NOT say "All done" or declare completion until:
1. Every item in the checklist is marked `[x]`
2. Every item has been verified (tests pass, review done, coverage ok)
3. Final self-audit has been completed and passed
4. All changes have been committed and pushed
