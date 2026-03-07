#!/bin/bash

##############################################################################
# pr-comments-complete: Fetch all PR comments including review comments
#
# This script works around limitations in the built-in /pr-comments skill
# by fetching PR-level comments, review comments, and reviews in a single
# GraphQL query for efficiency.
#
# Usage:
#   bash .claude/scripts/pr-comments-complete.sh [PR_NUMBER]
#   bash .claude/scripts/pr-comments-complete.sh 642
##############################################################################

set -euo pipefail

# Get PR number from argument or current branch
PR_NUMBER="${1:-}"

if [ -z "$PR_NUMBER" ]; then
  # Try to get from current PR if on a PR branch
  PR_NUMBER=$(gh pr view --json number -q .number 2>/dev/null || echo "")
  if [ -z "$PR_NUMBER" ]; then
    echo "❌ Usage: $0 <PR_NUMBER>" >&2
    echo "Or run from a branch with an associated PR" >&2
    exit 1
  fi
fi

# Get repo info
REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner)
OWNER=$(echo "$REPO" | cut -d/ -f1)
REPO_NAME=$(echo "$REPO" | cut -d/ -f2)

echo "## PR #$PR_NUMBER Comments - Complete"
echo ""

##############################################################################
# Fetch all data via single GraphQL query for efficiency
##############################################################################

# Build GraphQL query as a string (avoiding quote issues)
read -r -d '' GRAPHQL_QUERY <<'QUERY' || true
query($owner: String!, $repo: String!, $number: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $number) {
      comments(first: 100) {
        nodes {
          author { login }
          createdAt
          body
        }
      }
      reviewComments(first: 100) {
        nodes {
          author { login }
          path
          line
          diffHunk
          body
          createdAt
        }
      }
      reviews(first: 100) {
        nodes {
          author { login }
          state
          submittedAt
          body
          comments(first: 100) {
            nodes {
              path
              line
              diffHunk
              body
            }
          }
        }
      }
    }
  }
}
QUERY

# Execute GraphQL query (pass PR_NUMBER as integer, not string)
RESPONSE=$(gh api graphql \
  --field owner="$OWNER" \
  --field repo="$REPO_NAME" \
  --field number="$PR_NUMBER" \
  --raw-field query="$GRAPHQL_QUERY" 2>/dev/null || echo '{"errors":[{"message":"GraphQL query failed"}]}')

##############################################################################
# Section 1: PR-Level Comments
##############################################################################

echo "### PR-Level Comments"
echo ""

if echo "$RESPONSE" | jq -e '.data.repository.pullRequest.comments.nodes | length > 0' >/dev/null 2>&1; then
  echo "$RESPONSE" | jq -r '.data.repository.pullRequest.comments.nodes[] |
    "**@\(.author.login)** - \(.createdAt | sub("T.*"; ""))\n\n\(.body)\n\n---\n"'
else
  echo "No PR-level comments found."
fi

echo ""

##############################################################################
# Section 2: Review Comments (Inline Code Comments)
##############################################################################

echo "### Review Comments (Inline)"
echo ""

if echo "$RESPONSE" | jq -e '.data.repository.pullRequest.reviewComments.nodes | length > 0' >/dev/null 2>&1; then
  echo "$RESPONSE" | jq -r '.data.repository.pullRequest.reviewComments.nodes[] |
    "**@\(.author.login)** - \(.path)#L\(.line)\n\n```diff\n\(.diffHunk)\n```\n\n> \(.body)\n\n---\n"'
else
  echo "No inline review comments found."
fi

echo ""

##############################################################################
# Section 3: Review Summary (by reviewer and state)
##############################################################################

echo "### Review Summary"
echo ""

if echo "$RESPONSE" | jq -e '.data.repository.pullRequest.reviews.nodes | length > 0' >/dev/null 2>&1; then
  echo "$RESPONSE" | jq -r '.data.repository.pullRequest.reviews.nodes[] |
    "**\(.state)** - @\(.author.login) (\(.submittedAt | sub("T.*"; "")))\n\n\(.body // "(no summary body)")\n\nReview comments:\n\(.comments.nodes | if length > 0 then (.[] | "  - \(.path)#L\(.line): \(.body)") | join("\n") else "(no inline comments in this review)" end)\n\n---\n"'
else
  echo "No reviews found."
fi

echo ""
echo "---"
echo ""
echo "✅ All comments retrieved successfully (via GraphQL single query)"
