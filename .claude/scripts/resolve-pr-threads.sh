#!/usr/bin/env bash

##############################################################################
# resolve-pr-threads.sh - Resolve GitHub PR review threads with optional replies
#
# Usage:
#   resolve-pr-threads.sh <PR_NUMBER> [--replies <JSON_FILE>] [--dry-run]
#
# Examples:
#   # Resolve all unresolved threads without replies
#   resolve-pr-threads.sh 627
#
#   # Resolve threads with replies from JSON file
#   resolve-pr-threads.sh 627 --replies replies.json
#
#   # Preview what would be resolved without making changes
#   resolve-pr-threads.sh 627 --dry-run
#
# Replies file format (JSON):
#   {
#     "THREAD_ID_1": "Reply text here",
#     "THREAD_ID_2": "Another reply"
#   }
#
# Or simpler format - replies in order of thread appearance:
#   [
#     "First reply for first unresolved thread",
#     "Second reply for second thread",
#     ...
#   ]
##############################################################################

set -euo pipefail

# Configuration
REPO_OWNER="curdriceaurora"
REPO_NAME="Local-File-Organizer"
DRY_RUN=false
REPLIES_FILE=""

# Color output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Parse arguments
if [[ $# -lt 1 ]]; then
  echo "❌ Usage: $0 <PR_NUMBER> [--replies <FILE>] [--dry-run]"
  echo ""
  echo "Examples:"
  echo "  $0 627"
  echo "  $0 627 --replies replies.json"
  echo "  $0 627 --dry-run"
  exit 1
fi

PR_NUMBER="$1"
shift || true

while [[ $# -gt 0 ]]; do
  case "$1" in
    --replies)
      REPLIES_FILE="$2"
      shift 2 || { echo "❌ --replies requires an argument"; exit 1; }
      ;;
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    *)
      echo "❌ Unknown option: $1"
      exit 1
      ;;
  esac
done

# Validate PR number
if ! [[ "$PR_NUMBER" =~ ^[0-9]+$ ]]; then
  echo "❌ Invalid PR number: $PR_NUMBER"
  exit 1
fi

# Validate PR exists
echo "🔍 Fetching PR #$PR_NUMBER..."
if ! gh pr view "$PR_NUMBER" --repo "$REPO_OWNER/$REPO_NAME" > /dev/null 2>&1; then
  echo "❌ PR #$PR_NUMBER not found in $REPO_OWNER/$REPO_NAME"
  exit 1
fi

# Get all unresolved threads
echo "📋 Fetching unresolved threads..."
THREADS=$(gh api graphql -f query='query {
  repository(owner: "'$REPO_OWNER'", name: "'$REPO_NAME'") {
    pullRequest(number: '$PR_NUMBER') {
      reviewThreads(first: 100) {
        nodes {
          id
          isResolved
          comments(first: 1) {
            nodes {
              body
            }
          }
        }
      }
    }
  }
}' --jq '.data.repository.pullRequest.reviewThreads.nodes | map(select(.isResolved == false) | .id) | .[]' 2>&1)

if [[ -z "$THREADS" ]]; then
  echo "✅ No unresolved threads found for PR #$PR_NUMBER"
  exit 0
fi

# Convert to array
THREAD_ARRAY=($THREADS)
THREAD_COUNT=${#THREAD_ARRAY[@]}

echo -e "${BLUE}Found $THREAD_COUNT unresolved thread(s)${NC}"
echo ""

# Load replies if provided
# Use temp file as associative map (bash 3.2 compatible — no declare -A)
REPLIES_TMPDIR=$(mktemp -d)
trap 'rm -rf "$REPLIES_TMPDIR"' EXIT
if [[ -n "$REPLIES_FILE" ]]; then
  if [[ ! -f "$REPLIES_FILE" ]]; then
    echo "❌ Replies file not found: $REPLIES_FILE"
    exit 1
  fi

  echo "📄 Loading replies from: $REPLIES_FILE"

  # Try to parse as JSON object (thread_id -> reply_text)
  if grep -q '"' "$REPLIES_FILE" && grep -q ':' "$REPLIES_FILE"; then
    # Likely a JSON object with thread IDs as keys
    # Store each reply as a file named by thread ID (bash 3.2 compatible)
    while IFS= read -r thread_id && IFS= read -r reply_text; do
      if [[ -n "$thread_id" && -n "$reply_text" ]]; then
        printf '%s' "$reply_text" > "$REPLIES_TMPDIR/$thread_id"
      fi
    done < <(jq -r 'to_entries[] | (.key, .value)' "$REPLIES_FILE" 2>/dev/null || true)
  fi
fi

# Process each thread
RESOLVED_COUNT=0
SKIPPED_COUNT=0

i=0
for THREAD_ID in "${THREAD_ARRAY[@]}"; do
  i=$((i + 1))
  THREAD_NUM=$i

  echo -e "${YELLOW}[$THREAD_NUM/$THREAD_COUNT]${NC} Thread: $THREAD_ID"

  # Add reply if provided (lookup via tmpdir file)
  if [[ -f "$REPLIES_TMPDIR/$THREAD_ID" ]]; then
    REPLY=$(cat "$REPLIES_TMPDIR/$THREAD_ID")
    echo "  ↳ Adding reply: ${REPLY:0:60}..."

    if [[ "$DRY_RUN" != "true" ]]; then
      if gh api graphql -f query='mutation {
        addPullRequestReviewThreadReply(input: {pullRequestReviewThreadId: "'$THREAD_ID'", body: "'"${REPLY}"'"}) {
          comment {
            id
          }
        }
      }' > /dev/null 2>&1; then
        echo "  ✓ Reply added"
      else
        echo "  ⚠️  Failed to add reply"
      fi
    fi
  fi

  # Resolve thread
  echo "  ↳ Resolving thread..."

  if [[ "$DRY_RUN" != "true" ]]; then
    if gh api graphql -f query='mutation {
      resolveReviewThread(input: {threadId: "'$THREAD_ID'"}) {
        thread {
          isResolved
        }
      }
    }' --jq '.data.resolveReviewThread.thread.isResolved' > /dev/null 2>&1; then
      echo -e "  ${GREEN}✓ Resolved${NC}"
      ((RESOLVED_COUNT++))
    else
      echo "  ❌ Failed to resolve"
      ((SKIPPED_COUNT++))
    fi
  else
    echo "  [DRY RUN] Would resolve"
    ((RESOLVED_COUNT++))
  fi
done

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [[ "$DRY_RUN" == "true" ]]; then
  echo -e "${YELLOW}[DRY RUN]${NC} Would resolve: $RESOLVED_COUNT threads"
else
  echo -e "${GREEN}✅ Resolved: $RESOLVED_COUNT threads${NC}"
fi
if [[ $SKIPPED_COUNT -gt 0 ]]; then
  echo -e "${RED}⚠️  Skipped: $SKIPPED_COUNT threads${NC}"
fi
echo ""
