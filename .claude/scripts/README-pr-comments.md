# pr-comments-complete Script

A workaround for the `/pr-comments` skill limitation that fetches ALL PR comments including review comments.

## Problem

The built-in `/pr-comments` skill only fetches PR-level comments and misses:
- CodeRabbit review threads
- Copilot review comments
- Inline code review comments with diff context
- Review states (APPROVED, CHANGES_REQUESTED, COMMENTED)

See: https://github.com/anthropics/claude-code/issues/31687

## Solution

This script comprehensively fetches:
1. **PR-Level Comments** - General discussion comments
2. **Inline Review Comments** - Code review feedback with file/line context
3. **Review Summary** - Review state and summary by reviewer

## Usage

```bash
# Run on current PR (must be on a PR branch)
bash .claude/scripts/pr-comments-complete.sh

# Run on specific PR
bash .claude/scripts/pr-comments-complete.sh 642

# Save to file for review
bash .claude/scripts/pr-comments-complete.sh 642 > /tmp/pr-642-comments.md
```

## Output Format

```
## PR #642 Comments - Complete

### PR-Level Comments
[General comments on the PR]

### Review Comments (Inline)
@reviewer file.ts#L42:
```diff
[diff_hunk with changes]
```
> Comment text

### Review Summary
**CHANGES_REQUESTED** - @coderabbitai (2026-03-07)
[Review summary]
```

## Requirements

- `gh` CLI installed and authenticated
- `jq` for JSON parsing

## Key Differences from `/pr-comments`

| Feature | `/pr-comments` | `pr-comments-complete.sh` |
|---------|----------------|---------------------------|
| PR-level comments | ✅ | ✅ |
| Review comments | ❌ | ✅ |
| Diff context | ❌ | ✅ |
| Review state | ❌ | ✅ |
| File/line numbers | ❌ | ✅ |
| Structured output | Basic | Comprehensive |

## When to Use

- When `/pr-comments` misses code review findings
- Before responding to PR feedback
- When analyzing multiple review threads
- For comprehensive PR audit before merging
