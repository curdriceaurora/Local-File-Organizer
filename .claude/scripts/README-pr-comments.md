# pr-comments-complete Script

A workaround for the `/pr-comments` skill limitation that fetches ALL PR comments including review comments using **GraphQL for efficiency**.

## Problem

The built-in `/pr-comments` skill only fetches PR-level comments and misses:
- CodeRabbit review threads
- Copilot review comments
- Inline code review comments with diff context
- Review states (APPROVED, CHANGES_REQUESTED, COMMENTED)

See: https://github.com/anthropics/claude-code/issues/31687

## Solution

This script comprehensively fetches in a **single GraphQL query**:
1. **PR-Level Comments** - General discussion comments
2. **Inline Review Comments** - Code review feedback with file/line context
3. **Review Summary** - Review state and summary by reviewer

### Why GraphQL?

Using GraphQL instead of REST API provides:
- ✅ **Single query** instead of 3+ REST calls
- ✅ **Better efficiency** - only fetch what you need
- ✅ **Lower rate limit usage** - one API call vs multiple
- ✅ **Cleaner pagination** - handle nested data naturally
- ✅ **Atomic operation** - all data fetched consistently

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
**@user** - 2026-03-07

Comment text here

---

### Review Comments (Inline)
**@reviewer** - path/to/file.ts#L42

```diff
[diff_hunk with changes]
```

> Detailed comment about this code section

---

### Review Summary
**CHANGES_REQUESTED** - @coderabbitai (2026-03-07)

Summary of review findings

Review comments:
  - path/to/file.ts#L42: Specific inline comment
  - path/to/file.ts#L50: Another inline comment

---
```

## Requirements

- `gh` CLI installed and authenticated
- `jq` for JSON parsing
- GitHub GraphQL API access (standard with `gh`)

## GraphQL Query Details

The script uses a single GraphQL query that fetches:

```graphql
query($owner: String!, $repo: String!, $number: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $number) {
      # Issue comments (PR discussion)
      comments(first: 100) {
        nodes { author { login } createdAt body }
      }
      # Review comments (inline code feedback)
      reviewComments(first: 100) {
        nodes { author { login } path line diffHunk body createdAt }
      }
      # Reviews (with state and nested comments)
      reviews(first: 100) {
        nodes {
          author { login } state submittedAt body
          comments(first: 100) {
            nodes { path line diffHunk body }
          }
        }
      }
    }
  }
}
```

## Key Differences from `/pr-comments`

| Feature | `/pr-comments` | `pr-comments-complete.sh` |
|---------|----------------|---------------------------|
| PR-level comments | ✅ | ✅ |
| Review comments | ❌ | ✅ |
| Diff context | ❌ | ✅ |
| Review state | ❌ | ✅ |
| File/line numbers | ❌ | ✅ |
| API efficiency | REST (3+ calls) | GraphQL (1 query) |
| Structured output | Basic | Comprehensive |
| Rate limit usage | Higher | Lower |

## Performance

- **GraphQL single query** instead of 3+ REST API calls
- **Typical execution**: < 2 seconds for PRs with 50+ comments
- **Rate limit impact**: 1 point per execution vs 3+ points for REST

## When to Use

- When `/pr-comments` misses code review findings
- Before responding to PR feedback
- When analyzing multiple review threads
- For comprehensive PR audit before merging
- When API rate limits are a concern

## Troubleshooting

### "API rate limit exceeded"
- GraphQL reduces rate limit usage, but if still hitting limits:
  - Wait for rate limit reset
  - Reduce first/100 pagination parameter in GraphQL query

### "jq: command not found"
- Install jq: `brew install jq` (macOS) or `apt-get install jq` (Linux)

### "gh: command not found"
- Install GitHub CLI: https://cli.github.com/
- Authenticate: `gh auth login`
