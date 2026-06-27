#!/usr/bin/env bash
# check-threshold-drift.sh — Detect stale coverage/docstring threshold references after
# pyproject.toml changes.  When the staged pyproject.toml has a different cov-fail-under
# value than the committed one, grep docs for the old value.
# Exit 0 = clean, 1 = stale references found.

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"

NEW_VAL=$(git show :pyproject.toml 2>/dev/null | grep -E 'cov-fail-under|fail_under' | grep -oE '[0-9]+' | head -1 || true)
OLD_VAL=$(git show HEAD:pyproject.toml 2>/dev/null | grep -E 'cov-fail-under|fail_under' | grep -oE '[0-9]+' | head -1 || true)

if [[ -z "$NEW_VAL" ]] || [[ -z "$OLD_VAL" ]] || [[ "$NEW_VAL" == "$OLD_VAL" ]]; then
  exit 0
fi

# Docs that use the old value outside what this check can reason about: a dated
# historical snapshot (must keep the number it reported at the time) and a
# meta-doc whose "95%" mentions are pedagogical examples, not state claims.
# Excluded by path so the content-based matching below stays precise elsewhere.
EXCLUDE_PATHS=(
  "$REPO_ROOT/docs/testing/coverage-report.md"
  "$REPO_ROOT/.claude/rules/documentation-generation-checklist.md"
  "$REPO_ROOT/docs/superpowers/plans/2026-04-07-docstring-completion-and-ratchet.md"
)

HITS=$(grep -rnE "\b${OLD_VAL}\b" \
  "$REPO_ROOT/docs/" \
  "$REPO_ROOT/README.md" \
  "$REPO_ROOT/CONTRIBUTING.md" \
  "$REPO_ROOT/.claude/rules/" \
  "$REPO_ROOT/.github/" \
  2>/dev/null \
  | grep -v "^Binary" \
  | awk -F: '
      {
        content = $0
        sub(/^[^:]+:[^:]+:/, "", content)
        lc = tolower(content)
        if ((lc ~ /cover|gate|threshold|fail.under/) && (lc !~ /docstring|interrogate/)) print
      }
    ' \
  || true)

for excluded in "${EXCLUDE_PATHS[@]}"; do
  HITS=$(printf '%s\n' "$HITS" | grep -v "^${excluded}:" || true)
done

if [[ -n "$HITS" ]]; then
  printf "ERROR: Coverage threshold changed from %s%% to %s%% but stale references remain:\n" "$OLD_VAL" "$NEW_VAL"
  printf "%s\n" "$HITS"
  printf "\nUpdate these before committing (C4 rule: grep-and-update all doc references).\n"
  exit 1
fi

exit 0
