#!/bin/bash

##############################################################################
# pr-comments-complete: Fetch all PR comments including review comments
#
# This script works around limitations in the built-in /pr-comments skill
# by fetching both PR-level comments AND review comments with full context.
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
# Section 1: PR-Level Comments
##############################################################################

echo "### PR-Level Comments"
echo ""

COMMENTS=$(gh api /repos/"$OWNER"/"$REPO_NAME"/issues/"$PR_NUMBER"/comments 2>/dev/null || echo "[]")

if [ "$COMMENTS" = "[]" ] || [ -z "$COMMENTS" ]; then
  echo "No PR-level comments found."
else
  echo "$COMMENTS" | jq -r '.[] |
    "**@\(.user.login)** - \(.created_at | sub("T.*"; ""))\n\n\(.body)\n\n---\n"'
fi

echo ""

##############################################################################
# Section 2: Review Comments (Inline Code Comments)
##############################################################################

echo "### Review Comments (Inline)"
echo ""

REVIEW_COMMENTS=$(gh api /repos/"$OWNER"/"$REPO_NAME"/pulls/"$PR_NUMBER"/comments 2>/dev/null || echo "[]")

if [ "$REVIEW_COMMENTS" = "[]" ] || [ -z "$REVIEW_COMMENTS" ]; then
  echo "No inline review comments found."
else
  echo "$REVIEW_COMMENTS" | jq -r '.[] |
    "**@\(.user.login)** - \(.path)#L\(.line)\n\n```diff\n\(.diff_hunk)\n```\n\n> \(.body)\n\n---\n"'
fi

echo ""

##############################################################################
# Section 3: Review Summary (by reviewer and state)
##############################################################################

echo "### Review Summary"
echo ""

REVIEWS=$(gh api /repos/"$OWNER"/"$REPO_NAME"/pulls/"$PR_NUMBER"/reviews 2>/dev/null || echo "[]")

if [ "$REVIEWS" = "[]" ] || [ -z "$REVIEWS" ]; then
  echo "No reviews found."
else
  echo "$REVIEWS" | jq -r '.[] |
    "**\(.state)** - @\(.user.login) (\(.submitted_at | sub("T.*"; "")))\n\n\(.body // "(no body)")\n\n---\n"'
fi

echo ""
echo "---"
echo ""
echo "✅ All comments retrieved successfully"
