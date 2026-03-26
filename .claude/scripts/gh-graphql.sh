#!/usr/bin/env bash

##############################################################################
# gh-graphql.sh - Unified GitHub GraphQL operations for PR workflows
#
# Wraps all GraphQL queries and mutations behind named subcommands so that
# a single Bash permission entry covers every operation.
#
# Usage:
#   bash .claude/scripts/gh-graphql.sh <command> [args...]
#
# Commands:
#   pr-comments <PR_NUMBER>                       Fetch all PR comments
#   pr-threads  <PR_NUMBER>                       List unresolved review threads
#   pr-reviews  <PR_NUMBER>                       Fetch all reviews with comments
#   resolve-thread <THREAD_ID>                    Resolve a single review thread
#   reply-thread <THREAD_ID> <BODY>               Reply to a review thread
#   resolve-all <PR_NUMBER> [--replies FILE] [--dry-run]
#                                                 Resolve all unresolved threads
#
# Examples:
#   bash .claude/scripts/gh-graphql.sh pr-comments 965
#   bash .claude/scripts/gh-graphql.sh pr-threads 965
#   bash .claude/scripts/gh-graphql.sh resolve-all 965 --dry-run
#   bash .claude/scripts/gh-graphql.sh resolve-all 965 --replies replies.json
##############################################################################

set -euo pipefail

# Derive repo owner/name from git remote
REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null || echo "")
if [[ -z "$REPO" ]]; then
    echo "Error: cannot determine repo. Run from inside a git repo with a GitHub remote." >&2
    exit 1
fi
OWNER="${REPO%%/*}"
REPO_NAME="${REPO##*/}"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

##############################################################################
# Helpers
##############################################################################

require_pr_number() {
    if [[ -z "${1:-}" ]] || ! [[ "$1" =~ ^[0-9]+$ ]]; then
        echo "Error: valid PR number required" >&2
        exit 1
    fi
}

##############################################################################
# pr-comments — Fetch all PR comments (discussion + inline + reviews)
##############################################################################

cmd_pr_comments() {
    local pr_number="$1"
    require_pr_number "$pr_number"

    read -r -d '' QUERY <<'GQL' || true
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
GQL

    RESPONSE=$(gh api graphql \
        --field owner="$OWNER" \
        --field repo="$REPO_NAME" \
        --field number="$pr_number" \
        --raw-field query="$QUERY" 2>/dev/null \
        || echo '{"errors":[{"message":"GraphQL query failed"}]}')

    echo "## PR #$pr_number Comments"
    echo ""

    echo "### PR-Level Comments"
    echo ""
    if echo "$RESPONSE" | jq -e '.data.repository.pullRequest.comments.nodes | length > 0' >/dev/null 2>&1; then
        echo "$RESPONSE" | jq -r '.data.repository.pullRequest.comments.nodes[] |
            "**@\(.author.login)** - \(.createdAt | sub("T.*"; ""))\n\n\(.body)\n\n---\n"'
    else
        echo "No PR-level comments found."
    fi
    echo ""

    echo "### Review Comments (Inline)"
    echo ""
    if echo "$RESPONSE" | jq -e '.data.repository.pullRequest.reviewComments.nodes | length > 0' >/dev/null 2>&1; then
        echo "$RESPONSE" | jq -r '.data.repository.pullRequest.reviewComments.nodes[] |
            "**@\(.author.login)** - \(.path)#L\(.line)\n\n```diff\n\(.diffHunk)\n```\n\n> \(.body)\n\n---\n"'
    else
        echo "No inline review comments found."
    fi
    echo ""

    echo "### Review Summary"
    echo ""
    if echo "$RESPONSE" | jq -e '.data.repository.pullRequest.reviews.nodes | length > 0' >/dev/null 2>&1; then
        echo "$RESPONSE" | jq -r '.data.repository.pullRequest.reviews.nodes[] |
            "**\(.state)** - @\(.author.login) (\(.submittedAt | sub("T.*"; "")))\n\n\(.body // "(no summary body)")\n\n---\n"'
    else
        echo "No reviews found."
    fi
}

##############################################################################
# pr-threads — List unresolved review threads
##############################################################################

cmd_pr_threads() {
    local pr_number="$1"
    require_pr_number "$pr_number"

    gh api graphql -f query='query {
      repository(owner: "'"$OWNER"'", name: "'"$REPO_NAME"'") {
        pullRequest(number: '"$pr_number"') {
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
    }' --jq '.data.repository.pullRequest.reviewThreads.nodes[] | select(.isResolved == false) | {id, preview: .comments.nodes[0].body[:80]}'
}

##############################################################################
# pr-reviews — Fetch all reviews with comments
##############################################################################

cmd_pr_reviews() {
    local pr_number="$1"
    require_pr_number "$pr_number"

    gh api graphql -f query='query {
      repository(owner: "'"$OWNER"'", name: "'"$REPO_NAME"'") {
        pullRequest(number: '"$pr_number"') {
          reviews(first: 50) {
            nodes {
              author { login }
              state
              comments(first: 100) {
                nodes {
                  body
                  path
                  line
                }
              }
            }
          }
        }
      }
    }' --jq '.data.repository.pullRequest.reviews.nodes[] | {author: .author.login, state, comments: .comments.nodes}'
}

##############################################################################
# resolve-thread — Resolve a single review thread
##############################################################################

cmd_resolve_thread() {
    local thread_id="${1:-}"
    if [[ -z "$thread_id" ]]; then
        echo "Error: thread ID required" >&2
        exit 1
    fi

    gh api graphql -f query='mutation {
      resolveReviewThread(input: {threadId: "'"$thread_id"'"}) {
        thread { isResolved }
      }
    }' --jq '.data.resolveReviewThread.thread.isResolved'
}

##############################################################################
# reply-thread — Reply to a review thread
##############################################################################

cmd_reply_thread() {
    local thread_id="${1:-}"
    local body="${2:-}"
    if [[ -z "$thread_id" || -z "$body" ]]; then
        echo "Error: thread ID and body required" >&2
        echo "Usage: $0 reply-thread <THREAD_ID> <BODY>" >&2
        exit 1
    fi

    # Use --raw-field to safely pass the body without shell interpretation
    gh api graphql \
        --raw-field query='mutation($threadId: ID!, $body: String!) {
          addPullRequestReviewThreadReply(input: {pullRequestReviewThreadId: $threadId, body: $body}) {
            comment { id }
          }
        }' \
        -f threadId="$thread_id" \
        -f body="$body" \
        --jq '.data.addPullRequestReviewThreadReply.comment.id'
}

##############################################################################
# resolve-all — Resolve all unresolved threads (with optional replies)
##############################################################################

cmd_resolve_all() {
    local pr_number="$1"
    require_pr_number "$pr_number"
    shift

    local dry_run=false
    local replies_file=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --replies)
                replies_file="$2"
                shift 2 || { echo "Error: --replies requires an argument" >&2; exit 1; }
                ;;
            --dry-run)
                dry_run=true
                shift
                ;;
            *)
                echo "Error: unknown option: $1" >&2
                exit 1
                ;;
        esac
    done

    # Validate PR exists
    if ! gh pr view "$pr_number" > /dev/null 2>&1; then
        echo "Error: PR #$pr_number not found" >&2
        exit 1
    fi

    # Fetch unresolved thread IDs
    echo -e "${BLUE}Fetching unresolved threads for PR #$pr_number...${NC}"
    local threads
    threads=$(gh api graphql -f query='query {
      repository(owner: "'"$OWNER"'", name: "'"$REPO_NAME"'") {
        pullRequest(number: '"$pr_number"') {
          reviewThreads(first: 100) {
            nodes {
              id
              isResolved
              comments(first: 1) { nodes { body } }
            }
          }
        }
      }
    }' --jq '.data.repository.pullRequest.reviewThreads.nodes | map(select(.isResolved == false) | .id) | .[]' 2>&1)

    if [[ -z "$threads" ]]; then
        echo -e "${GREEN}No unresolved threads found.${NC}"
        return 0
    fi

    local thread_array=($threads)
    local total=${#thread_array[@]}
    echo -e "${BLUE}Found $total unresolved thread(s)${NC}"

    # Load replies (bash 3.2 compatible — use temp dir instead of associative array)
    local replies_tmpdir
    replies_tmpdir=$(mktemp -d)
    trap 'rm -rf "$replies_tmpdir"' EXIT

    if [[ -n "$replies_file" ]]; then
        if [[ ! -f "$replies_file" ]]; then
            echo "Error: replies file not found: $replies_file" >&2
            exit 1
        fi
        echo "Loading replies from: $replies_file"
        while IFS= read -r tid && IFS= read -r rtxt; do
            if [[ -n "$tid" && -n "$rtxt" ]]; then
                printf '%s' "$rtxt" > "$replies_tmpdir/$tid"
            fi
        done < <(jq -r 'to_entries[] | (.key, .value)' "$replies_file" 2>/dev/null || true)
    fi

    # Process threads
    local resolved=0 failed=0 i=0
    for tid in "${thread_array[@]}"; do
        i=$((i + 1))
        echo -e "${YELLOW}[$i/$total]${NC} $tid"

        # Reply if available
        if [[ -f "$replies_tmpdir/$tid" ]]; then
            local reply
            reply=$(cat "$replies_tmpdir/$tid")
            echo "  -> Reply: ${reply:0:60}..."
            if [[ "$dry_run" != "true" ]]; then
                if cmd_reply_thread "$tid" "$reply" > /dev/null 2>&1; then
                    echo "  -> Reply added"
                else
                    echo "  -> Failed to add reply"
                fi
            fi
        fi

        # Resolve
        if [[ "$dry_run" != "true" ]]; then
            if cmd_resolve_thread "$tid" > /dev/null 2>&1; then
                echo -e "  ${GREEN}Resolved${NC}"
                resolved=$((resolved + 1))
            else
                echo -e "  ${RED}Failed${NC}"
                failed=$((failed + 1))
            fi
        else
            echo "  [DRY RUN] Would resolve"
            resolved=$((resolved + 1))
        fi
    done

    echo ""
    if [[ "$dry_run" == "true" ]]; then
        echo -e "${YELLOW}[DRY RUN]${NC} Would resolve: $resolved threads"
    else
        echo -e "${GREEN}Resolved: $resolved threads${NC}"
    fi
    if [[ $failed -gt 0 ]]; then
        echo -e "${RED}Failed: $failed threads${NC}"
    fi
}

##############################################################################
# Main dispatch
##############################################################################

COMMAND="${1:-}"
shift || true

case "$COMMAND" in
    pr-comments)
        cmd_pr_comments "${1:-}"
        ;;
    pr-threads)
        cmd_pr_threads "${1:-}"
        ;;
    pr-reviews)
        cmd_pr_reviews "${1:-}"
        ;;
    resolve-thread)
        cmd_resolve_thread "${1:-}"
        ;;
    reply-thread)
        cmd_reply_thread "${1:-}" "${2:-}"
        ;;
    resolve-all)
        cmd_resolve_all "$@"
        ;;
    *)
        echo "Usage: $0 <command> [args...]"
        echo ""
        echo "Commands:"
        echo "  pr-comments <PR>                          Fetch all PR comments"
        echo "  pr-threads  <PR>                          List unresolved threads"
        echo "  pr-reviews  <PR>                          Fetch reviews with comments"
        echo "  resolve-thread <THREAD_ID>                Resolve a single thread"
        echo "  reply-thread <THREAD_ID> <BODY>           Reply to a thread"
        echo "  resolve-all <PR> [--replies FILE] [--dry-run]"
        echo "                                            Resolve all unresolved threads"
        exit 1
        ;;
esac
